"""Décision justifiée pour chaque case : ce qui a déjà été fait (précédents) face au modèle d'ontologie.

Pour une question, on cherche la même question dans les anciens RFI, puis on contrôle chaque réponse historique
contre Fabric pour le fonds qui l'avait reçue (même concept, même date quand la mesure est datée) :
  - concordance  → « repris de l'ancien » : la réponse proposée suit la même donnée que l'ancien RFI ;
  - discordance  → « incohérence » : on montre les deux, rien n'est écrit automatiquement ;
  - ontologie muette mais un précédent concorde avec une donnée Fabric → liaison déduite, proposée « à vérifier » ;
  - réponse identique pour plusieurs fonds, sans donnée propre au fonds → réponse de niveau société, « à vérifier » ;
  - paragraphe propre au fonds → modèle de rédaction paramétré si tous les faits sont expliqués, sinon simple référence ;
  - sinon → « modèle d'ontologie », avec la raison.
Jamais de copie automatique d'une valeur historique (auto_copy_allowed = faux).
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from ..layout import Slot, classify_cell
from ..match import match
from ..ontology import Concept, Ontology, norm
from ..render import choose_option, render
from ..understand import Understanding, understand
from ..values import Values, to_date
from .compare import NOT_ANSWERS, same
from .retrieval import Hit, PrecedentIndex
from .templates import FACT_CONCEPTS, Template, decompose, fill

FIRM = re.compile(r"(?<![a-z])(sdg|societe de gestion|management company|asset manager|groupe|group|actionnaire|shareholder|capital|"
                  r"signataire|signatory|pri|unpri|sanction|resultat|contact|formulaire|questionnaire|effectif|collaborateurs|"
                  r"employees|siege|firm|company|entreprise|politique de vote|voting policy|engagement policy)(?![a-z])")
NEGATIVE = re.compile(r"^(il n'y a pas|il n'y a aucun|aucun|aucune|neant|pas de|no |none|there is no|there are no|nothing)")
# Questions sur la société de gestion (organisation, conformité, risques, négociation…) : réponse rédigée réutilisable
FIRM_TOPIC = re.compile(r"(?<![a-z])(organisation|organization|la societe|votre societe|your firm|the firm|the company|the organisation|"
                        r"the group|le groupe|staff|employees|collaborateurs|effectifs?|compliance|conformite|deontolog|code of ethics|"
                        r"code of conduct|blanchiment|money laundering|anti-corruption|personal account|transactions personnelles|"
                        r"best execution|meilleure execution|brokers?|courtiers?|counterpart|contreparties|soft dollar|soft commission|"
                        r"trading desk|table de negociation|transmission des ordres|order transmission|disaster recovery|"
                        r"plan de continuite|business continuity|cyber|auditeur|external auditor|commissaire aux comptes de la societe|"
                        r"remuneration policy|politique de remuneration|cio|directeur des investissements|comite d'investissement|"
                        r"investment committee|risk management function|departement de gestion des risques|gestion des risques independant|"
                        r"controle interne|internal control|historique de la societe|history of the firm|actionnariat|shareholding)(?![a-z])")
SAME_QUESTION = 0.84
SAME_WORDING = 0.9  # même question à la formulation près (majorité des autres fonds)  # au-dessus : « même question »
MAX_CHECKED = 6  # précédents contrôlés dans Fabric par case
SOFT_FLAGS = ("non précisé", "autre lecture", "lecture indirecte")
LABELS = {
    "precedent_confirme": "Repris de l'ancien",
    "precedent_liaison": "Repris de l'ancien (liaison déduite)",
    "precedent_constant": "Repris de l'ancien (réponse société)",
    "precedent_habituel": "Repris de l'ancien (réponse habituelle)",
    "precedent_meme_fonds": "Repris de l'ancien (même fonds)",
    "modele_redaction": "Modèle de rédaction",
    "incoherence": "Incohérence",
    "ontologie": "Modèle d'ontologie",
    "aucun": "Sans réponse",
}


@dataclass
class Entity:
    pid: str | None
    isin: str | None
    name: str


@dataclass
class Check:
    hit: Hit
    entity: Entity | None
    result: str  # match | mismatch | unknown
    fabric: str | None = None
    evidence: str = ""

    def to_public(self) -> dict[str, Any]:
        return {**self.hit.to_public(), "check": self.result, "fabric": self.fabric, "evidence": self.evidence,
                "resolved": self.entity.name if self.entity else None}


@dataclass
class Decision:
    kind: str
    justification: str
    answer: str | None = None
    value: Any = None
    option: str | None = None
    status: str | None = None  # nouveau statut proposé pour la case (None : inchangé)
    concept: str | None = None
    precedents: list[dict[str, Any]] = field(default_factory=list)
    template: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": LABELS[self.kind], "justification": self.justification, "answer": self.answer,
                "concept": self.concept, "precedents": self.precedents, "template": self.template}


class FundResolver:
    """Retrouve dans Product Info le fonds d'un précédent (ISIN, sinon nom exact du fonds ou de la part)."""

    def __init__(self, directory: list[dict[str, Any]]):
        self.names: set[str] = set()  # tous les noms de fonds et de parts connus (texte propre à un fonds)
        self.by_isin: dict[str, Entity] = {}
        self.by_name: dict[str, Entity] = {}
        for item in directory:
            for s in item["shares"]:
                ent = Entity(item["pid"], s["isin"], s["name"] or item["name"])
                self.by_isin[s["isin"].upper()] = ent
                self.by_name.setdefault(norm(s["name"]), ent)
                self.names.add(norm(s["name"]))
            self.by_name.setdefault(norm(item["name"]), Entity(item["pid"], None, item["name"]))
            self.names.add(norm(item["name"]))

    def resolve(self, isin: str, fund_name: str, share_name: str) -> Entity | None:
        if isin and isin.upper() in self.by_isin:
            return self.by_isin[isin.upper()]
        for name in (share_name, fund_name):
            if name and norm(name) in self.by_name:
                return self.by_name[norm(name)]
        return None


def question_of(slot: Slot) -> str:
    return f"{slot.parent} {slot.question}" if slot.parent else slot.question


def _fund_key(h: Hit) -> str:
    p = h.precedent
    return (p.isin or norm(p.fund_name) or norm(p.share_name) or p.source_file).upper()


def _fund_specific(text: str, hits: list[Hit], names: set[str] | None = None) -> bool:
    t = norm(text)
    if names and any(len(n) >= 8 and n in t for n in names):
        return True
    for h in hits:
        for name in (h.precedent.fund_name, h.precedent.share_name):
            if name and len(name) >= 4 and norm(name) in t:
                return True
        if h.precedent.isin and h.precedent.isin.lower() in t:
            return True
    return bool(re.search(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b", text))


class PrecedentAdvisor:
    def __init__(self, ontology: Ontology, index: PrecedentIndex, resolver: FundResolver,
                 values_factory: Callable[[str | None, str | None, date], Values], as_of: date, lang: str,
                 current: Entity | None):
        self.ontology = ontology
        self.index = index
        self.resolver = resolver
        self.values_factory = values_factory
        self.as_of = as_of
        self.lang = lang
        self.current = current
        self._values: dict[tuple, Values] = {}

    # ------------------------------------------------------------------ outils
    def _vals(self, ent: Entity, when: date) -> Values:
        key = (ent.pid, ent.isin, when)
        if key not in self._values:
            self._values[key] = self.values_factory(ent.pid, ent.isin, when)
        return self._values[key]

    def _check(self, concept: Concept, u: Understanding, hit: Hit) -> Check:
        p = hit.precedent
        ent = self.resolver.resolve(p.isin, p.fund_name, p.share_name)
        if ent is None:
            return Check(hit, None, "unknown", evidence="fonds du précédent introuvable dans Product Info")
        if concept.scope == "share" and not ent.isin:
            return Check(hit, ent, "unknown", evidence="part du précédent non identifiée")
        when = to_date(p.ref_date) if (concept.computed and p.ref_date) else self.as_of
        if concept.computed and not p.ref_date:
            return Check(hit, ent, "unknown", evidence="date du précédent inconnue : mesure datée non comparable")
        vals = self._vals(ent, when or self.as_of)
        raw = vals.get(concept, u, self.lang)
        result = same(self.ontology, concept, raw.value, p.answer_raw)
        shown = render(self.ontology, concept, raw, u, self.lang, as_of=when).display if raw.value is not None else None
        note = "" if concept.computed else " (Product Info actuel : la donnée a pu changer depuis)" if result == "mismatch" else ""
        return Check(hit, ent, result, fabric=shown, evidence=(raw.evidence or "") + note)

    def _usable(self, hits: list[Hit]) -> list[Hit]:
        # consigne restée dans l'ancien document (« réponse binaire », « indiquer… ») : ce n'est pas une réponse
        return [h for h in hits if h.precedent.kind in {"answer", "checkbox"} and not h.precedent.blocked and not h.precedent.empty
                and norm(h.precedent.answer_text) not in NOT_ANSWERS and classify_cell(h.precedent.answer_text)[0] == "answered"]

    def _answer_key(self, text: str) -> str:
        v = self.ontology.vocab_value("yes_no", text)
        return f"__{v.id}" if v is not None else norm(text)

    def _public(self, hits: list[Hit], checks: dict[str, Check]) -> list[dict[str, Any]]:
        out = []
        for h in hits[:8]:
            c = checks.get(h.precedent.id)
            out.append(c.to_public() if c else {**h.to_public(), "check": None})
        return out

    # ------------------------------------------------------------------ décision
    def advise(self, slot: Slot, u: Understanding, row: dict[str, Any]) -> Decision:
        question = f"{slot.parent} — {slot.question}" if slot.parent else slot.question
        firm = self.ontology.concepts.get(row.get("concept") or "")
        if firm is not None and str(firm.source).startswith("precedent:"):
            return self._firm(slot, firm)
        hits = self.index.search(question, k=8)
        usable = self._usable(hits)
        concept = self.ontology.concepts.get(row.get("concept") or "")
        has_answer = row.get("answer") is not None and row.get("status") in {"auto", "review"}
        if not hits:
            if has_answer:
                return Decision("ontologie", "Modèle d'ontologie : aucun précédent comparable dans les anciens RFI.", concept=row.get("concept"))
            return Decision("aucun", "Ni l'ontologie ni les anciens RFI ne permettent de répondre.")

        checks: dict[str, Check] = {}
        if has_answer and concept is not None:
            for h in usable[:MAX_CHECKED]:
                checks[h.precedent.id] = self._check(concept, u, h)
            return self._with_ontology(row, concept, u, hits, checks)
        return self._without_ontology(slot, u, hits, usable, checks)

    def _with_ontology(self, row: dict[str, Any], concept: Concept, u: Understanding, hits: list[Hit], checks: dict[str, Check]) -> Decision:
        ok = [c for c in checks.values() if c.result == "match"]
        ko = [c for c in checks.values() if c.result == "mismatch"]
        public = self._public(hits, checks)
        answer = row.get("answer")
        if ko:
            c = ko[0]
            more = f" (et {len(ko) - 1} autre(s))" if len(ko) > 1 else ""
            return Decision("incoherence",
                            f"Incohérence : {c.hit.precedent.provenance()} répondait « {c.hit.precedent.answer_text[:80]} » alors que "
                            f"Fabric ({c.evidence}) donne « {c.fabric} » pour ce fonds-là{more}. Réponse proposée d'après le modèle "
                            f"d'ontologie : « {answer} » — à trancher.", status="review", concept=concept.id, precedents=public)
        if ok:
            funds = {(c.entity.pid, c.entity.isin) for c in ok if c.entity}
            c = ok[0]
            status = None
            if row.get("status") == "review" and len(funds) >= 2 and self._only_soft(row) and \
                    not self._alternative_also_fits(row, u, [c.hit for c in ok]):
                status = "auto"
            return Decision("precedent_confirme",
                            f"Repris de l'ancien : {c.hit.precedent.provenance()} répondait « {c.hit.precedent.answer_text[:80]} », "
                            f"qui est bien la donnée Fabric ({c.evidence}) de ce fonds-là ; même donnée pour ce fonds : « {answer} »"
                            + (f" — confirmé sur {len(funds)} fonds." if len(funds) > 1 else "."),
                            status=status, concept=concept.id, precedents=public)
        why = "précédents trouvés mais non vérifiables dans Fabric (fonds non retrouvé, date inconnue ou réponse non comparable)" \
            if hits else "aucun précédent comparable"
        return Decision("ontologie", f"Modèle d'ontologie : {why}.", concept=concept.id, precedents=public)

    @staticmethod
    def _only_soft(row: dict[str, Any]) -> bool:
        return all(any(s in i for s in SOFT_FLAGS) for i in row.get("issues", []))

    def _alternative_also_fits(self, row: dict[str, Any], u: Understanding, hits: list[Hit]) -> bool:
        for alt in row.get("alternatives", [])[:3]:
            concept = self.ontology.concepts.get(alt["concept"])
            if concept is None:
                continue
            if all(self._check(concept, u, h).result == "match" for h in hits):
                return True
        return False

    def _without_ontology(self, slot: Slot, u: Understanding, hits: list[Hit], usable: list[Hit], checks: dict[str, Check]) -> Decision:
        # 1. Liaison déduite : quelle donnée Fabric donnait la réponse historique ?
        decision = self._infer_binding(slot, u, usable, checks)
        if decision:
            return decision
        public = self._public(hits, checks)
        close = [h for h in usable if h.similarity >= SAME_QUESTION]
        # 2. Même fonds dans un ancien RFI
        if self.current is not None:
            mine = [h for h in close if (self.current.isin and h.precedent.isin.upper() == (self.current.isin or "").upper())]
            if mine:
                h = mine[0]
                return self._proposal("precedent_meme_fonds", slot, h.precedent.answer_text,
                                      f"Repris de l'ancien (même fonds) : {h.precedent.provenance()} répondait « {h.precedent.answer_text[:120]} ». "
                                      "Aucune donnée Fabric ne le confirme : à valider.", public)
        # 3. Ce que les autres fonds ont répondu à la même question : majorité calibrée, chiffrée dans la justification
        decision = self._majority(slot, question_of(slot), public)
        if decision is not None:
            return decision
        # 4. Réponse société rédigée (organisation, conformité, négociation…) : reprise de la plus récente, à relire
        firm_text = [h for h in close if FIRM_TOPIC.search(norm(question_of(slot))) and not _fund_specific(h.precedent.answer_text, [h], self._names())
                     and len(h.precedent.answer_text) > 3]
        if firm_text:
            h = max(firm_text, key=lambda x: (x.similarity, x.precedent.ref_date))
            dated = " Le texte contient des chiffres ou des dates : à mettre à jour." if re.search(r"\d", h.precedent.answer_text) else ""
            return self._proposal("precedent_constant", slot, h.precedent.answer_text,
                                  f"Repris de l'ancien : réponse société rédigée dans {h.precedent.provenance()} "
                                  f"(question {h.similarity:.0%} semblable). Texte de niveau société, reprise tel quel : à relire.{dated}",
                                  public)
        # 5. Paragraphe : modèle de rédaction paramétré
        narrative = [h for h in usable if h.precedent.shape == "NARRATIF" or len(h.precedent.answer_text) > 160]
        if narrative:
            return self._narrative(slot, u, narrative[0], public)
        if any(h.precedent.blocked for h in hits) and not usable:
            reason = next(h.precedent.block_reason for h in hits if h.precedent.blocked)
            return Decision("aucun", f"Précédents trouvés mais réutilisation bloquée : {reason}.", precedents=public)
        return Decision("aucun", "Précédents trouvés mais inutilisables tels quels (fonds différents, réponse propre au fonds, "
                                 "bloc ou option à revoir). À compléter.", precedents=public)

    def _names(self) -> set[str]:
        if not hasattr(self, "_names_cache"):
            names = set(self.resolver.names)
            names |= {norm(p.fund_name) for p in self.index.store.all() if p.fund_name} if self.index.store.count() < 50000 else set()
            names |= {norm(p.share_name) for p in self.index.store.all() if p.share_name} if self.index.store.count() < 50000 else set()
            self._names_cache = {n for n in names if n}
        return self._names_cache

    def _same_wording(self, a: str, b: str) -> bool:
        return norm(a) == norm(b) or any(h.precedent.question == b for h in self.index.search(a, k=20, min_similarity=SAME_WORDING))

    def _majority(self, slot: Slot, question: str, public: list[dict[str, Any]]) -> Decision | None:
        """Réponses des autres fonds à la même question (libellé quasi identique), regroupées par fonds.

        Règles (une proposition reste toujours « à vérifier ») :
          - majorité ≥ 75 % des fonds et ≥ 2 fonds ; un seul fonds : seulement pour un oui / non ou un libellé court ;
          - chiffre ou date : seulement pour une question société, réponse unanime et précédents datés de moins de 4 mois ;
          - « non applicable » : seulement s'il est unanime sur ≥ 3 fonds ;
          - jamais de texte qui cite le fonds d'origine (nom, ISIN).
        """
        same = [h for h in self._usable(self.index.search(question, k=60, min_similarity=SAME_WORDING))
                if len(h.precedent.answer_text) <= 160 and h.precedent.shape != "NARRATIF"]
        if self.current is not None and self.current.isin:
            same = [h for h in same if h.precedent.isin.upper() != self.current.isin.upper()] or same
        if not same:
            return None
        by_fund: dict[str, Hit] = {}
        for h in sorted(same, key=lambda h: h.precedent.ref_date, reverse=True):  # la réponse la plus récente de chaque fonds
            by_fund.setdefault(_fund_key(h), h)
        groups: dict[str, list[Hit]] = {}
        for h in by_fund.values():
            key = self._answer_key(h.precedent.answer_text)
            # coquilles (« Quotidiennne ») : même réponse, regroupée avec la variante la plus proche
            near = next((k for k in groups if not k.startswith("__") and not key.startswith("__")
                         and difflib.SequenceMatcher(None, k, key).ratio() >= 0.9), None)
            groups.setdefault(near or key, []).append(h)
        ranked = sorted(groups.values(), key=len, reverse=True)
        top, total = ranked[0], len(by_fund)
        share = len(top) / total
        text = Counter(h.precedent.answer_text.strip() for h in top).most_common(1)[0][0]  # la graphie majoritaire
        qn = norm(question)
        firm = bool(FIRM.search(qn)) and not re.search(r"commission|frais|fee|droit d", qn)
        na = norm(text).startswith(("non applicable", "not applicable", "sans objet", "n/a"))
        numeric = bool(re.search(r"\d", text))
        others = ", ".join(f"« {g[0].precedent.answer_text[:30]} » ×{len(g)}" for g in ranked[1:4])
        files = ", ".join(sorted({h.precedent.source_file for h in top})[:2])
        if _fund_specific(text, top, self._names()):
            return None
        if total > 1 and (len(top) < 2 or share < 0.75):
            return Decision("aucun", f"Les autres fonds divergent sur cette question (« {text[:30]} » ×{len(top)}, {others}) : "
                                     "réponse propre à chaque fonds, aucune donnée Fabric reconnue. À compléter.", precedents=public)
        if numeric:
            recent = all((d := to_date(h.precedent.ref_date)) is not None and abs((self.as_of - d).days) <= 122 for h in top)
            if not (firm and len(ranked) == 1 and len(top) >= 2 and recent):
                return None
        if na and not (len(ranked) == 1 and len(top) >= 3):
            return None
        if total == 1 and self.ontology.vocab_value("yes_no", text) is None:
            return None  # un seul autre fonds : preuve trop faible, sauf pour un oui / non (signalé)
        stats = f"{len(top)} fonds sur {total}" + (f" ({share:.0%}) ; autres réponses : {others}" if len(ranked) > 1 else "")
        if firm:
            return self._proposal("precedent_constant", slot, text,
                                  f"Repris de l'ancien : « {text[:80]} » répondu pour {stats} ({files}). Question de niveau société"
                                  + (f", donnée datée du {top[0].precedent.ref_date[:10]}" if numeric else "") + " : à valider.", public)
        caution = " Un seul précédent : à vérifier avec soin." if total == 1 else ""
        return self._proposal("precedent_habituel", slot, text,
                              f"Repris de l'ancien : « {text[:80]} » répondu pour {stats} ({files}). Question propre au fonds, "
                              f"aucune donnée Fabric pour la confirmer : à vérifier pour ce fonds.{caution}", public)

    def _firm(self, slot: Slot, concept: Concept) -> Decision:
        """Question de niveau société : on regroupe les anciens RFI par concept (toutes formulations, FR/EN)."""
        members = [p for p in self.index.concept_members(self.ontology, concept)
                   if p.kind in {"answer", "checkbox"} and not p.empty and classify_cell(p.answer_text)[0] == "answered"]
        blocked = [p for p in members if p.blocked]
        members = [p for p in members if not p.blocked]
        public = [{**p.to_public(), "similarity": 1.0, "check": None} for p in (members + blocked)[:8]]
        if not members:
            why = " (seuls des précédents à identité bloquée)" if blocked else ""
            return Decision("aucun", f"Question société ({concept.label(self.lang)}) : aucun ancien RFI exploitable{why}. À compléter.",
                            concept=concept.id, precedents=public)
        votes: dict[str, list] = {}
        for p in members:
            if concept.type == "bool":
                lead = re.split(r"[\s/,.;:()\-]+", norm(p.answer_text).strip())[0] if p.answer_text.strip() else ""
                v = self.ontology.vocab_value("yes_no", p.answer_text) or self.ontology.vocab_value("yes_no", lead) \
                    or (self.ontology.vocab_value("yes_no", "no") if NEGATIVE.match(norm(p.answer_text)) else None)
                if v is None:
                    continue  # paragraphe sans oui / non explicite : ni pour ni contre
                votes.setdefault(v.id, []).append(p)
            else:
                if len(p.answer_text) <= 120 and not re.search(r"\d", p.answer_text):
                    votes.setdefault(norm(p.answer_text), []).append(p)
        sources = lambda ps: len({p.source_file for p in ps})
        if len(votes) != 1:
            detail = ", ".join(f"« {ps[0].answer_text[:30]} » ×{sources(ps)}" for ps in votes.values()) or "réponses non interprétables"
            return Decision("aucun", f"Question société ({concept.label(self.lang)}) : les anciens RFI ne concordent pas ({detail}). À trancher.",
                            concept=concept.id, precedents=public)
        value, group = next(iter(votes.items()))
        files = sorted({p.source_file for p in group})
        if concept.type == "bool":
            vocab = self.ontology.vocab_value("yes_no", value)
            text = (vocab.fr if self.lang == "fr" else vocab.en) if vocab else group[0].answer_text
        else:
            text = group[0].answer_text
        # Formulation maison : si les autres fonds ont reçu une réponse rédigée à cette même question, on la reprend
        house = [p for p in group if self._same_wording(question_of(slot), p.question)]
        if house and not slot.options and len({norm(p.answer_text) for p in house}) == 1 and not re.search(r"\d", house[0].answer_text):
            text = house[0].answer_text
        if slot.options:
            texts = [text, group[0].answer_text] + ([vocab.fr, vocab.en] if concept.type == "bool" and vocab else [])
            option, _ = choose_option(slot.options, texts=texts, vocab=vocab if concept.type == "bool" else None,
                                      ontology=self.ontology, vocab_name="yes_no" if concept.type == "bool" else None)
            if option is None:
                return Decision("aucun", f"Anciens RFI : « {text} », mais cette réponse n'est pas dans la liste déroulante.",
                                concept=concept.id, precedents=public)
            text = option
        return Decision("precedent_constant",
                        f"Repris de l'ancien : « {text} » répondu dans {len(files)} questionnaire(s) ({', '.join(files[:3])}"
                        f"{'…' if len(files) > 3 else ''}), formulations différentes regroupées par le sens "
                        f"({concept.label(self.lang)}). Question société, aucune donnée Fabric : à vérifier.",
                        answer=text, value=text, option=text if slot.options else None, status="review", concept=concept.id,
                        precedents=public)

    def _proposal(self, kind: str, slot: Slot, text: str, justification: str, public: list[dict[str, Any]]) -> Decision:
        option = None
        if slot.options:
            option, _ = choose_option(slot.options, texts=[text], ontology=self.ontology)
            if option is None:
                return Decision("aucun", justification + " Mais cette réponse n'est pas dans la liste déroulante : rien n'est proposé.",
                                precedents=public)
        answer = option or text
        return Decision(kind, justification, answer=answer, value=answer, option=option, status="review", precedents=public)

    def _infer_binding(self, slot: Slot, u: Understanding, usable: list[Hit], checks: dict[str, Check]) -> Decision | None:
        resolvable = [h for h in usable if self.resolver.resolve(h.precedent.isin, h.precedent.fund_name, h.precedent.share_name)]
        if not resolvable:
            return None
        concepts: dict[str, Concept] = {}
        for h in resolvable[:3]:
            for cand in match(self.ontology, understand(self.ontology, h.precedent.question), limit=6):
                concepts.setdefault(cand.concept.id, cand.concept)
        for cand in match(self.ontology, u, limit=6):
            concepts.setdefault(cand.concept.id, cand.concept)
        winners = []
        for concept in concepts.values():
            results = [self._check(concept, u, h) for h in resolvable[:4]]
            ok = [r for r in results if r.result == "match"]
            if ok and not any(r.result == "mismatch" for r in results):
                winners.append((len({(r.entity.pid, r.entity.isin) for r in ok if r.entity}), concept, ok))
        if not winners:
            return None
        winners.sort(key=lambda w: -w[0])
        if len(winners) > 1 and winners[1][0] == winners[0][0]:
            return None  # deux données expliquent aussi bien l'ancien RFI : on ne choisit pas
        n, concept, ok = winners[0]
        if self.current is None:
            return None
        vals = self._vals(self.current, self.as_of)
        raw = vals.get(concept, u, self.lang)
        rendered = render(self.ontology, concept, raw, u, self.lang, number_format=slot.number_format, as_of=self.as_of)
        if rendered.display is None:
            return None
        for c in ok:
            checks[c.hit.precedent.id] = c
        c = ok[0]
        return Decision("precedent_liaison",
                        f"Repris de l'ancien : dans {c.hit.precedent.provenance()}, la réponse « {c.hit.precedent.answer_text[:80]} » "
                        f"correspondait à la donnée Fabric {c.evidence} ({concept.label(self.lang)}) de ce fonds-là"
                        + (f", vérifié sur {n} fonds" if n > 1 else "") + f". Même donnée pour ce fonds : « {rendered.display} ».",
                        answer=rendered.display, value=rendered.value, option=rendered.option, status="review", concept=concept.id,
                        precedents=self._public(usable, checks))

    def _narrative(self, slot: Slot, u: Understanding, hit: Hit, public: list[dict[str, Any]]) -> Decision:
        p = hit.precedent
        origin = self.resolver.resolve(p.isin, p.fund_name, p.share_name)
        if origin is None or self.current is None:
            return Decision("modele_redaction", f"Référence de style uniquement : {p.provenance()} (fonds d'origine non retrouvé "
                                                "dans Fabric, faits non décomposables). Ne pas recopier.", precedents=public)
        o_vals, c_vals = self._vals(origin, self.as_of), self._vals(self.current, self.as_of)
        facts: dict[str, tuple[Any, str | None]] = {}
        for cid in FACT_CONCEPTS:
            concept = self.ontology.concepts.get(cid)
            if concept is None or concept.problems:
                continue
            raw = o_vals.get(concept, u, self.lang)
            if raw.value is not None:
                facts[cid] = (raw.value, render(self.ontology, concept, raw, u, self.lang, as_of=self.as_of).display)
        template: Template = decompose(p.answer_text, facts, [p.fund_name, p.share_name, origin.name])

        def current(cid: str) -> str | None:
            concept = self.ontology.concepts[cid]
            raw = c_vals.get(concept, u, self.lang)
            return render(self.ontology, concept, raw, u, self.lang, as_of=self.as_of).display if raw.value is not None else None

        if not template.safe:
            reason = ("éléments propres au fonds d'origine non expliqués : " + ", ".join(template.residual)) if template.residual \
                else "aucun fait reconnu"
            return Decision("modele_redaction", f"Référence de style uniquement ({p.provenance()}) : {reason}. Ne pas recopier.",
                            precedents=public, template=template.text if template.params else None)
        text = fill(template, current)
        if text is None:
            return Decision("modele_redaction", f"Modèle de rédaction tiré de {p.provenance()}, mais une donnée manque pour ce fonds.",
                            precedents=public, template=template.text)
        return Decision("modele_redaction", f"Modèle de rédaction paramétré tiré de {p.provenance()} : faits remplacés par ceux de ce "
                                            f"fonds ({', '.join(template.params)}). Relire le texte fixe avant envoi.",
                        answer=text, value=text, status="review", precedents=public, template=template.text)


__all__ = ["PrecedentAdvisor", "FundResolver", "Decision", "Entity", "LABELS"]
