"""Mesure de la qualité du compléteur : précision des réponses automatiques et taux de couverture.

Deux usages :
  1. banc d'essai de formulations (tests/rfi_gold.yaml) : chaque question a son concept attendu, ou `null` quand
     elle ne doit JAMAIS être remplie automatiquement (piège) ;
  2. RFI réels validés : chaque génération écrit un fichier « …_rempli_vN.gold.json » ; on peut rejouer le moteur
     dessus après une évolution de l'ontologie :  python -m merlin.rfi.evaluate data/rfi/<id>/versions/<fichier>.gold.json

Indicateurs (au seuil automatique) :
  - précision automatique = réponses automatiques correctes / réponses automatiques  → objectif 100 %
  - couverture automatique = réponses automatiques correctes / questions répondables
  - couverture totale = (automatiques + à vérifier correctes) / questions répondables
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .match import match
from .ontology import Ontology
from .understand import understand

AUTO = 0.70
MIN_SCORE = 0.45
MARGIN = 0.08


@dataclass
class Outcome:
    question: str
    expected: str | None
    predicted: str | None
    band: str  # auto | review | none
    score: float

    @property
    def correct(self) -> bool:
        return self.predicted == self.expected


def classify(ontology: Ontology, question: str, options: list[str] | None = None, hint: str = "", context: str = "",
             entity_scope: str | None = None) -> tuple[str | None, str, float]:
    """(concept prédit, bande, score) sans accès aux données : bande « auto » si aucune réserve sémantique."""
    u = understand(ontology, question, options=options, hint=hint, context=context, entity_scope=entity_scope)
    cands = match(ontology, u)
    if not cands or cands[0].score < MIN_SCORE:
        return None, "none", cands[0].score if cands else 0.0
    best = cands[0]
    ambiguous = any(c.score >= best.score - MARGIN and c.concept.id != best.concept.id for c in cands[1:])
    band = "auto" if best.score >= AUTO and not best.flags and not ambiguous else "review"
    return best.concept.id, band, best.score


def run_cases(ontology: Ontology, cases: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = []
    for case in cases:
        predicted, band, score = classify(ontology, case["q"], case.get("options"), case.get("hint", ""), case.get("context", ""),
                                          case.get("entity"))
        outcomes.append(Outcome(case["q"], case.get("concept"), predicted, band, score))
    auto = [o for o in outcomes if o.band == "auto"]
    answerable = [o for o in outcomes if o.expected]
    wrong_auto = [o for o in auto if not o.correct]
    reviewed_ok = [o for o in outcomes if o.band == "review" and o.correct and o.expected]
    return {
        "cases": len(outcomes),
        "auto": len(auto),
        "auto_precision": round(1 - len(wrong_auto) / len(auto), 4) if auto else 1.0,
        "auto_coverage": round(sum(1 for o in auto if o.correct and o.expected) / len(answerable), 4) if answerable else 0.0,
        "total_coverage": round((sum(1 for o in auto if o.correct and o.expected) + len(reviewed_ok)) / len(answerable), 4) if answerable else 0.0,
        "wrong_auto": [o.__dict__ for o in wrong_auto],
        "missed": [o.__dict__ for o in outcomes if o.expected and not o.correct],
        "outcomes": outcomes,
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


def _main(argv: list[str]) -> int:
    from ..config import get_settings as load_settings
    from ..data.catalog import load_catalog
    from .ontology import load_ontology

    settings = load_settings()
    ontology = load_ontology(load_catalog(str(settings.catalog_csv)))
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2] / "tests" / "rfi_gold.yaml"
    if path.suffix == ".json":
        gold = json.loads(path.read_text(encoding="utf-8"))
        cases = [{"q": a["question"], "concept": a["concept"]} for a in gold["answers"] if a.get("concept")]
    else:
        cases = load_cases(path)
    report = run_cases(ontology, cases)
    print(f"Questions : {report['cases']}  ·  automatiques : {report['auto']}")
    print(f"Précision automatique : {report['auto_precision']:.1%}  ·  couverture automatique : {report['auto_coverage']:.1%}"
          f"  ·  couverture totale (avec « à vérifier ») : {report['total_coverage']:.1%}")
    for o in report["wrong_auto"]:
        print(f"  ✗ AUTO ERRONÉ  {o['question']!r} → {o['predicted']} (attendu {o['expected']}, score {o['score']:.2f})")
    for o in report["missed"]:
        print(f"  · manqué      {o['question']!r} → {o['predicted']} [{o['band']}] (attendu {o['expected']})")
    return 1 if report["wrong_auto"] else 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
