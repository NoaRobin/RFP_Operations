"""Banc de rejeu : mesurer le compléteur sur de vrais questionnaires déjà répondus.

Pour chaque (fichier, fonds) d'une bibliothèque de wording, on cache ses réponses, on rejoue le questionnaire avec
tous les autres précédents, puis on compare chaque proposition à ce qui avait été répondu :
  - couverture : part des questions qui reçoivent une proposition (automatique ou à vérifier) ;
  - concordance : part des propositions identiques à la réponse historique (même valeur, même oui / non, coquilles
    tolérées), séparément pour l'ontologie (données Fabric) et pour les précédents.
Avec Fabric, le fonds rejoué est retrouvé par son ISIN : la concordance de l'ontologie devient une vraie mesure de
justesse. En mode démo, les valeurs sont fictives : seule la concordance des précédents a un sens.

  cd backend && python -m merlin.rfi.replay chemin/Bibliotheque_Wording_RFI_Lot02.json [--limit 10]

Le rapport (agrégats, aucune valeur) est écrit dans data/rfi/replay_report.json — jamais committé.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from ..config import get_settings
from ..data.access import build_data_access
from .layout import classify_cell, detect
from .ontology import load_ontology, norm
from .precedents import PrecedentIndex, PrecedentStore
from .precedents.compare import NOT_ANSWERS, parse_number
from .precedents.importers import import_lot02, load_lot02
from .service import RfiStore, analyze, fund_directory

ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}\d")


def _unit(e: dict[str, Any]) -> tuple[str, str]:
    c = e.get("context") or {}
    return e["source_file"], str(c.get("isin") or c.get("retail_isin") or c.get("isin_in_cell") or c.get("fund_name") or "")


def _family(name: str) -> str:
    n = norm(name)
    for key, label in (("suivi qualitatif", "Suivi qualitatif"), ("axa", "AXA"), ("ddq", "DDQ"), ("esg", "Questionnaires ESG"),
                       ("due diligence", "Due diligence société"), ("data", "Fiches DATA")):
        if key in n:
            return label
    return "Formulaires de référencement" if n.startswith("r-co") else "Autres"


def agree(ontology, proposed: Any, historical: Any) -> bool:
    if proposed is None or historical is None:
        return False
    a, b = norm(proposed), norm(historical)
    if a == b or (a and b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.9):
        return True
    ya, yb = ontology.vocab_value("yes_no", proposed), ontology.vocab_value("yes_no", historical)
    if ya is not None and yb is not None:
        return ya.id == yb.id
    na, nb = parse_number(proposed), parse_number(historical)
    if na is not None and nb is not None:
        return any(abs(na - nb * s) <= max(0.011, 0.01 * abs(na)) for s in (1, 100, 0.01))
    return False


def replay(corpus: dict[str, Any], limit: int | None = None, verbose: bool = True) -> dict[str, Any]:
    settings = get_settings()
    data = build_data_access()
    ontology = load_ontology(data.catalog)
    directory = fund_directory(data)
    by_isin = {s["isin"].upper(): f["pid"] for f in directory for s in f["shares"]}
    demo = directory[0] if directory else None
    blocked_refs = {i.get("source_ref") for i in corpus.get("identity_issues") or []}
    examples = corpus["answer_examples"]
    units: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in examples:
        units[_unit(e)].append(e)
    totals: Counter = Counter()
    families: dict[str, Counter] = defaultdict(Counter)
    unresolved = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for n, (key, items) in enumerate(sorted(units.items())):
            if limit is not None and n >= limit:
                break
            if any(e.get("source_ref") in blocked_refs for e in items):
                continue  # identité à confirmer : pas de rejeu
            questions = []
            for e in items:
                answer = str(e.get("answer_raw") if e.get("answer_raw") is not None else "").strip()
                if not str(e.get("question") or "").strip() or str(e.get("extraction_method", "")).startswith(("BLOC", "QUESTION_OPTION")):
                    continue
                if not answer or norm(answer) in NOT_ANSWERS or norm(answer).startswith("ne pas remplir") or classify_cell(answer)[0] != "answered":
                    continue
                if norm(e["question"]) not in {norm(q["question"]) for q in questions}:
                    questions.append(e)
            if not questions:
                continue
            store = PrecedentStore(root / f"u{n}.sqlite")
            import_lot02(store, {**corpus, "answer_examples": [e for e in examples if _unit(e) != key]})
            wb = Workbook()
            ws = wb.active
            ws.append(["Question", "Réponse"])
            for e in questions:
                ws.append([e["question"], None])
            path = root / f"u{n}.xlsx"
            wb.save(path)
            isin = key[1].upper() if ISIN.fullmatch(key[1].upper()) else None
            pid = by_isin.get(isin or "")
            share = isin if pid else None
            if pid is None:
                unresolved += 1
                pid, share = (demo["pid"], demo["shares"][0]["isin"] if demo["shares"] else None) if demo else (None, None)
            result = analyze(data, RfiStore(root / "rfi"), path, detect(path), pid, share, date.today().isoformat(), None, None,
                             PrecedentIndex(store), precedent_isin=isin)
            by_q = {norm(q["question"]): q for q in result["questions"]}
            fam = families[_family(key[0])]
            for e in questions:
                q = by_q.get(norm(e["question"]))
                c = Counter(questions=1)
                if q is None:
                    c["not_read"] += 1
                elif q.get("answer") is not None and q["status"] in {"auto", "review"}:
                    origin = "precedent" if q.get("source") == "précédent" else "ontology"
                    ok = agree(ontology, q.get("answer"), e.get("answer_raw"))
                    c.update({"proposed": 1, f"{origin}_proposed": 1, f"{origin}_agree": int(ok), f"{q['status']}": 1,
                              f"{q['status']}_agree": int(ok)})
                totals.update(c)
                fam.update(c)
            if verbose:
                print(f"  {n + 1:3}/{len(units)} {key[0][:40]:40} {key[1][:14]:14} {fam['proposed']}/{fam['questions']}", file=sys.stderr)

    def rates(c: Counter) -> dict[str, Any]:
        q = c["questions"] or 1
        return {"questions": c["questions"], "coverage": round(c["proposed"] / q, 3),
                "ontology_coverage": round(c["ontology_proposed"] / q, 3),
                "precedent_coverage": round(c["precedent_proposed"] / q, 3),
                "ontology_agreement": round(c["ontology_agree"] / c["ontology_proposed"], 3) if c["ontology_proposed"] else None,
                "precedent_agreement": round(c["precedent_agree"] / c["precedent_proposed"], 3) if c["precedent_proposed"] else None,
                "auto_agreement": round(c["auto_agree"] / c["auto"], 3) if c["auto"] else None}

    report = {"date": date.today().isoformat(), "mode": data.mode, "seconds": round(time.time() - t0),
              "units_unresolved_in_fabric": unresolved, "total": rates(totals),
              "families": {k: rates(v) for k, v in sorted(families.items(), key=lambda kv: -kv[1]["questions"])},
              "note": ("Mode démo : valeurs Fabric fictives, la concordance de l'ontologie n'est pas significative."
                       if data.mode != "fabric" else "Fabric : concordance mesurée sur les valeurs réelles.")}
    out = settings.data_dir / "rfi" / "replay_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["file"] = str(out)
    return report


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Banc de rejeu du compléteur RFI sur une bibliothèque de wording")
    parser.add_argument("corpus", type=Path, help="Bibliotheque_Wording_RFI_*.json ou le .zip du pack")
    parser.add_argument("--limit", type=int, default=None, help="nombre maximal de (fichier, fonds) rejoués")
    args = parser.parse_args(argv)
    report = replay(load_lot02(args.corpus.read_bytes()), args.limit)
    t = report["total"]
    pct = lambda v: "—" if v is None else f"{v:.1%}"
    print(f"\nMode {report['mode']} · {t['questions']} questions rejouées · {report['seconds']} s")
    print(f"Couverture {pct(t['coverage'])} (ontologie {pct(t['ontology_coverage'])}, précédents {pct(t['precedent_coverage'])})")
    print(f"Concordance : précédents {pct(t['precedent_agreement'])} · ontologie {pct(t['ontology_agreement'])} · automatiques {pct(t['auto_agreement'])}")
    for name, f in report["families"].items():
        print(f"  {name:32} {f['questions']:5} questions · couverture {pct(f['coverage'])} · concordance précédents {pct(f['precedent_agreement'])}")
    print(report["note"])
    print(f"Rapport : {report['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
