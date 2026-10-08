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

import re
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
SAME_QUESTION = 0.84  # au-dessus : « même question »
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
        self.by_isin: dict[str, Entity] = {}
        self.by_name: dict[str, Entity] = {}
        for item in directory:
            for s in item["shares"]:
                ent = Entity(item["pid"], s["isin"], s["name"] or item["name"])
                self.by_isin[s["isin"].upper()] = ent
                self.by_name.setdefault(norm(s["name"]), ent)
            self.by_name.setdefault(norm(item["name"]), Entity(item["pid"], None, item["name"]))

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


def _fund_specific(text: str, hits: list[Hit]) -> bool:
    t = norm(text)
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
        # 3. Réponse identique pour plusieurs fonds : niveau société, ou pratique habituelle (jamais un chiffre, une date,
        #    un « non applicable » : propres au fonds et à la date)
        short = [h for h in close if h.precedent.shape not in {"NUMERIQUE", "DATE", "NARRATIF", "NON_APPLICABLE"}
                 and len(h.precedent.answer_text) <= 160]
        if short:
            answers: dict[str, list[Hit]] = {}
            for h in short:
                answers.setdefault(self._answer_key(h.precedent.answer_text), []).append(h)
            if len(answers) == 1:
                group = next(iter(answers.values()))
                funds = {_fund_key(h) for h in group}
                text = group[0].precedent.answer_text
                files = ", ".join(sorted({h.precedent.source_file for h in group})[:3])
                reusable = not _fund_specific(text, group) and not re.search(r"\d", text) and \
                    not norm(text).startswith(("non applicable", "not applicable", "sans objet"))
                if len(funds) >= 2 and reusable:
                    qn = norm(question_of(slot))
                    if FIRM.search(qn) and not re.search(r"commission|frais|fee|droit d", qn):
                        return self._proposal("precedent_constant", slot, text,
                                              f"Repris de l'ancien : réponse identique « {text[:80]} » pour {len(funds)} fonds ({files}). "
                                              "Question de niveau société, sans donnée Fabric associée : à valider.", public)
                    return self._proposal("precedent_habituel", slot, text,
                                          f"Repris de l'ancien : « {text[:80]} » a été répondu pour {len(funds)} autres fonds ({files}). "
                                          "Question propre au fonds et aucune donnée Fabric pour la confirmer : à vérifier pour ce fonds.",
                                          public)
            elif len(answers) > 1:
                variants = ", ".join(f"« {v[0].precedent.answer_text[:40]} » ×{len(v)}" for v in list(answers.values())[:4])
                return Decision("aucun", f"Les anciens RFI divergent sur cette question ({variants}) : réponse propre à chaque "
                                         "fonds, aucune donnée Fabric reconnue. À compléter.", precedents=public)
        # 4. Paragraphe : modèle de rédaction paramétré
        narrative = [h for h in usable if h.precedent.shape == "NARRATIF" or len(h.precedent.answer_text) > 160]
        if narrative:
            return self._narrative(slot, u, narrative[0], public)
        if any(h.precedent.blocked for h in hits) and not usable:
            reason = next(h.precedent.block_reason for h in hits if h.precedent.blocked)
            return Decision("aucun", f"Précédents trouvés mais réutilisation bloquée : {reason}.", precedents=public)
        return Decision("aucun", "Précédents trouvés mais inutilisables tels quels (fonds différents, réponse propre au fonds, "
                                 "bloc ou option à revoir). À compléter.", precedents=public)

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
