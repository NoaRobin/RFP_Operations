"""Rapprochement question → concept de l'ontologie. Déterministe, explicable, prudent.

Score d'un concept (0 à 1) :
  1. un terme du concept est présent (spécificité : nombre de mots) ;
  2. « require » satisfait, aucun terme d'exclusion ;
  3. facettes compatibles (une facette contraire écarte le concept ; une variante non par défaut est pénalisée) ;
  4. portée fonds / part cohérente ;
  5. type compatible avec la réponse attendue (liste déroulante, format de cellule, consigne, forme de la question) ;
  6. couverture : part des mots porteurs de sens de la question expliquée par le concept (une question plus large
     que le concept fait baisser la confiance).
Les drapeaux (ambiguïté, date citée, période par défaut…) empêchent le remplissage automatique : proposition « à vérifier ».
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ontology import Concept, Ontology, Term, norm, tokens
from .understand import Understanding, has_term

STRONG_SINGLE = {"sri", "srri", "ter", "ocf", "lei", "isin", "nav", "aum", "sfdr", "giin", "wkn", "sedol", "valor", "ric", "pea",
                 "gip", "hwm", "ucit", "opcvm", "etf", "finansol", "iznes", "allfund", "fundsettle", "clearstream", "euroclear",
                 "tabac", "tobacco", "ogm", "gmo", "fatca", "ombrelle", "umbrella", "depositaire", "depositary", "valorisateur",
                 "centralisateur", "custodian", "conservateur", "decimalisation", "gate", "swing", "domicile", "domiciliation",
                 "volatilite", "volatility", "drawdown", "retrocession", "cac", "vl", "encour", "nourricier", "feeder"}
PERIOD_WORDS = {"an", "ans", "annee", "year", "yr", "y", "moi", "mois", "month", "m", "ytd", "annualise", "annualisee",
                "annualised", "annualized", "cumule", "cumulee", "cumulative", "depui", "since", "creation", "inception",
                "lancement", "launch", "origine", "debut", "beginning", "pa", "p.a", "per", "annum", "1er", "janvier",
                "glissant", "rolling", "derniere", "dernier", "last", "past", "calendaire", "calendar", "civile"}


@dataclass
class Candidate:
    concept: Concept
    score: float
    term: str
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # empêchent l'automatique
    assert_value: str | None = None  # question oui/non sur une valeur de vocabulaire (« Le fonds est-il Article 8 ? »)

    def to_dict(self) -> dict:
        return {"concept": self.concept.id, "label": self.concept.label_fr, "score": round(self.score, 2), "term": self.term,
                "reasons": self.reasons, "flags": self.flags}


def _specificity(term: Term) -> float:
    words = term.specificity
    if len(term.parts) > 1:
        return min(0.88, 0.66 + 0.06 * words)
    if words == 1:
        w = term.parts[0][0]
        return 0.72 if (w in STRONG_SINGLE or len(w) >= 9) else 0.58
    return 0.78 if words == 2 else 0.86


def _vocab_mentions(ontology: Ontology, vocab: str, q: str) -> list[str]:
    hits = []
    for v in ontology.vocabularies.get(vocab, []):
        for s in v.synonyms:
            if len(s) < 3 and not s.isdigit():
                continue
            if s.isdigit() and vocab not in {"sri", "sfdr"}:
                continue
            if s.isdigit() and not re.search(rf"(?:article|art\.?|sri|srri|niveau|level|class|classe|categorie|category)\s*{s}\b", q):
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", q):
                hits.append(v.id)
                break
    return hits


def score_concept(ontology: Ontology, concept: Concept, u: Understanding) -> Candidate | None:
    seq = u.all_tokens
    reasons: list[str] = []
    flags: list[str] = []

    # 1. terme
    best: Term | None = None
    for term in concept.terms:
        if has_term(term, seq, prefix=True) and (best is None or _specificity(term) > _specificity(best)):
            best = term
    if best is None:
        return None
    score = _specificity(best)
    reasons.append(f"terme « {best.raw} »")

    # 2. exclusions, exigences
    for term in concept.exclude:
        if has_term(term, seq, prefix=True):
            return None
    if concept.require and not any(has_term(t, seq, prefix=True) for t in concept.require):
        return None
    for pseudo in getattr(concept, "pseudo_require", []):
        if pseudo == "period_mention" and u.period is None:
            return None
        if pseudo == "country_mention" and not u.countries:
            return None

    # 3. facettes
    for facet in set(u.facets) | set(u.context_facets) | set(concept.facets):
        q_vals = u.facets.get(facet)
        from_context = False
        if not q_vals and facet in u.context_facets:
            q_vals, from_context = u.context_facets[facet], True
        c_val = concept.facets.get(facet)
        if c_val and q_vals:
            if c_val not in q_vals:
                return None
            score += 0.04 if from_context else 0.08
            reasons.append(f"{facet} = {c_val}" + (" (contexte)" if from_context else ""))
        elif c_val and not q_vals:
            if facet in concept.default:
                reasons.append(f"{facet} par défaut : {c_val}")
                if concept.ambiguous:
                    flags.append(f"« {facet} » non précisé : lecture par défaut ({c_val}) à confirmer")
            else:
                score -= 0.3
        elif q_vals and not c_val:
            if facet == "subject":
                if concept.id.startswith("perf."):
                    return None  # mesure demandée sur l'indice, pas sur le fonds
                continue
            if facet not in {"currency_basis", "annualization"}:
                score -= 0.05

    # 4. portée (seulement si une variante de l'autre portée existe : « date de création » du fonds / de la part)
    scopes = set(u.scopes) or set(u.context_scopes)
    if not u.scopes and u.entity_scope and concept.scope == u.entity_scope:
        score += 0.12  # en-têtes de grille par part : libellés courts, portée certaine
        reasons.append("grille par part")
    if getattr(concept, "scope_sibling", False):
        if concept.scope == "fund" and "share" in scopes and "fund" not in scopes:
            score -= 0.12
        elif concept.scope == "share" and "fund" in scopes and "share" not in scopes:
            score -= 0.12

    # 5. type attendu
    expected, origin = u.expected, u.expected_from
    hard = origin in {"liste déroulante", "format de la cellule", "consigne"}
    assert_value = None
    if expected == "bool" and concept.type != "bool":
        mentions = _vocab_mentions(ontology, concept.vocab, u.q) if concept.vocab and concept.type == "enum" else []
        if len(mentions) == 1:
            assert_value = mentions[0]
            reasons.append(f"question fermée sur la valeur « {mentions[0]} »")
        elif hard:
            return None
        else:
            score -= 0.25
    elif expected == "date" and concept.type != "date":
        if hard:
            return None
        score -= 0.25
    elif expected == "percent" and concept.type not in {"percent", "list"}:
        if hard:
            return None
        score -= 0.2
    elif expected == "number" and concept.type not in {"percent", "number", "int", "amount", "enum"}:
        if hard:
            return None
        score -= 0.2
    elif expected in {"date", "percent", "number"} and concept.type == expected:
        score += 0.04
    if u.wants_percent and concept.type not in {"percent", "list"} and not u.options:
        score -= 0.12
    if u.asks_date and concept.type != "date" and not ({"date", "dates"} & best.words):
        score -= 0.3  # « depuis quand », « date d'obtention » : jamais un oui / non ni un montant
        flags.append("la question demande une date")
    if getattr(concept, "ask_bool", False) and expected != "bool":
        return None

    # 6. couverture de la question
    parts = [p for t in u.q_tokens for p in (t.split("-") if "-" in t and t not in best.words else [t])]
    content = [t for t in parts if t not in ontology.generic and not t.isdigit() and len(t) > 1]
    if content:
        explained = set(best.words)
        for term in concept.terms:
            if has_term(term, seq, prefix=True):
                explained |= term.words
        for t in concept.require:
            if has_term(t, seq, prefix=True):
                explained |= t.words
        for facet, values in u.facets.items():
            for value in values:
                for t in ontology.facets[facet][value]:
                    if has_term(t, seq):
                        explained |= t.words
        for terms in ontology.scope_terms.values():
            for t in terms:
                if has_term(t, seq):
                    explained |= t.words
        explained |= PERIOD_WORDS
        covered = sum(1 for t in content if t in explained or any(t.startswith(e) for e in explained if len(e) >= 5))
        coverage = covered / len(content)
        factor = 0.4 + 0.6 * min(1.0, coverage / 0.7)
        if factor < 0.99:
            reasons.append(f"couverture de la question {coverage:.0%}")
        score *= factor

    # 7. question qualitative
    if u.qualitative and not concept.qualitative_ok:
        score *= 0.35
        flags.append("question qualitative : un chiffre ne suffit sans doute pas")

    # 8. date ou année citée, différente de la date d'arrêté (concepts non calculés par période)
    if concept.computed and concept.source.startswith(("jump:", "perf:")):
        if u.explicit_date:
            reasons.append(f"mesure à la date citée ({u.explicit_date.strftime('%d/%m/%Y')})")
    elif u.explicit_date or u.calendar_years:
        flags.append("la question cite une date : vérifier qu'elle correspond à la date d'arrêté")

    return Candidate(concept, max(0.0, min(1.0, score)), best.raw, reasons, flags, assert_value)


def match(ontology: Ontology, u: Understanding, limit: int = 5) -> list[Candidate]:
    out = [c for c in (score_concept(ontology, concept, u) for concept in ontology.usable()) if c is not None and c.score > 0.2]
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:limit]


__all__ = ["Candidate", "match", "score_concept"]
