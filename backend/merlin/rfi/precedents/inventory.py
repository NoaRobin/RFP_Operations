"""Inventaire du corpus de précédents : exemples utilisables, associations à revoir, concepts non couverts.

Agrégats uniquement (comptes, libellés de questions) : aucune valeur de réponse n'y figure. Ne prétend jamais que le
corpus est validé ni qu'il couvre tous les RFI : ces limites sont écrites dans le résultat.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..evaluate import classify
from ..ontology import Ontology, norm
from .compare import NOT_ANSWERS
from .store import PrecedentStore

_cache: dict[tuple[str, int], dict[str, Any]] = {}


def inventory(store: PrecedentStore, ontology: Ontology) -> dict[str, Any]:
    key = (str(store.path), store.version)
    if key in _cache:
        return _cache[key]
    items = store.all()
    usable, review = [], Counter()
    for p in items:
        reasons = []
        if p.blocked:
            reasons.append("identité à confirmer (réutilisation bloquée)")
        if p.kind == "block":
            reasons.append("bloc vertical candidat")
        if p.kind == "choice":
            reasons.append("option conditionnelle + commentaire")
        if p.empty or norm(p.answer_text) in NOT_ANSWERS:
            reasons.append("réponse vide ou « non communiqué »")
        if p.shape == "NON_APPLICABLE":
            reasons.append("« non applicable » : jamais généralisé")
        if p.shape == "NARRATIF":
            reasons.append("paragraphe propre au fonds : modèle de rédaction seulement")
        if p.mapping_status == "LIBELLE_EXACT_CANDIDAT":
            reasons.append("libellé exact candidat : pas une liaison SQL validée")
        for r in reasons:
            review[r] += 1
        if not reasons or reasons == ["libellé exact candidat : pas une liaison SQL validée"]:
            usable.append(p)

    by_question: dict[str, list] = defaultdict(list)
    for p in items:
        by_question[norm(p.question)].append(p)
    bands = Counter()
    uncovered: list[dict[str, Any]] = []
    covered = Counter()
    for qn, group in by_question.items():
        cid, band, score = classify(ontology, group[0].question)
        bands[band] += 1
        if band == "none":
            uncovered.append({"question": group[0].question.strip()[:160], "occurrences": len(group),
                              "funds": len({(p.isin or p.fund_name or p.source_file) for p in group}),
                              "files": len({p.source_file for p in group})})
        else:
            covered[cid] += len(group)
    uncovered.sort(key=lambda x: (-x["occurrences"], x["question"]))
    variants = [{"question": g[0].question.strip()[:160], "occurrences": len(g), "distinct_answers": len({norm(p.answer_text) for p in g})}
                for g in by_question.values() if len(g) > 1 and len({norm(p.answer_text) for p in g}) > 1]
    variants.sort(key=lambda x: -x["occurrences"])
    result = {
        "total": len(items), "unique_questions": len(by_question), "files": len(store.sources()),
        "usable": {"total": len(usable), "by_shape": dict(Counter(p.shape or "?" for p in usable)),
                   "by_origin": dict(Counter(p.origin for p in usable))},
        "to_review": dict(review.most_common()),
        "blocked_sources": [s for s in store.sources() if s.get("identity_problem")],
        "ontology_coverage": {"auto": bands["auto"], "review": bands["review"], "none": bands["none"]},
        "top_concepts": [{"concept": c, "label": ontology.concepts[c].label_fr if c in ontology.concepts else c, "entries": n}
                         for c, n in covered.most_common(15)],
        "uncovered": uncovered[:60], "uncovered_total": len(uncovered),
        "repeated_with_variants": variants[:20], "repeated_with_variants_total": len(variants),
        "limits": ["Réponses historiques non approuvées pour copie automatique (auto_copy_allowed = faux partout).",
                   "Le corpus contient des répétitions par fonds et des blocs candidats : ce ne sont pas des questions uniques.",
                   "Les correspondances de libellés ne sont pas des liaisons SQL validées.",
                   "Le corpus ne couvre pas tous les RFI 2026 ; aucune entrée n'est réputée validée."],
    }
    _cache[key] = result
    return result
