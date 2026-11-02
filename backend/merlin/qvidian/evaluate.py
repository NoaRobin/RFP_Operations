"""Banc d'évaluation de la recherche Qvidian : nDCG@10, MRR@10, rappel@20, par configuration du moteur.

    python -m merlin.qvidian.evaluate [--models data/models] [--eval tests/qvidian_search_eval.yaml]

Sur le poste, avec la vraie bibliothèque, on peut écrire son propre fichier de questions (mêmes clés) : c'est la seule
mesure qui compte pour décider d'un réglage.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from ..search import neural
from ..search.engine import mrr, ndcg, recall
from .demo import DemoQvidian
from .library_search import LibrarySearch
from .snapshot import Snapshot, sync

EVAL = Path(__file__).resolve().parents[2] / "tests" / "qvidian_search_eval.yaml"
TODAY = date(2026, 10, 15)


def demo_snapshot(folder: Path) -> Snapshot:
    snap = Snapshot(folder / "eval_demo.sqlite")
    if snap.empty:
        sync(DemoQvidian(), snap, "demo")
    return snap


def demo_history(snap: Snapshot) -> dict:
    """Liens anciens RFI ↔ contenus de la démonstration (anciens questionnaires fictifs)."""
    from .history import History, build_links, demo_precedents

    links = build_links(snap.all(), demo_precedents({c["id"]: c for c in snap.all()}))
    h = History(snap.path.with_name("eval.history.json"))
    h.save(links, len(links), "eval")
    return h.by_content()


def run(engine: LibrarySearch, queries: list[dict[str, Any]], rerank: bool = True) -> dict[str, Any]:
    rows, started = [], time.time()
    for item in queries:
        gains = {int(k): float(v) for k, v in item["rel"].items()}
        res = engine.search(item["q"], k=20, rerank=rerank)
        ranked: list[int] = []
        for r in res["results"]:  # une famille de versions compte pour chacun de ses membres
            ranked.append(r["id"])
            ranked.extend(v["id"] for v in r["variants"])
        relevant = {d for d, g in gains.items() if g >= 2}
        rows.append({"q": item["q"], "ndcg": ndcg(ranked, gains, 10), "mrr": mrr(ranked, relevant, 10),
                     "recall": recall(ranked, set(gains), 20), "top": ranked[:3]})
    return {"ndcg@10": round(statistics.mean(r["ndcg"] for r in rows), 4), "mrr@10": round(statistics.mean(r["mrr"] for r in rows), 4),
            "recall@20": round(statistics.mean(r["recall"] for r in rows), 4),
            "ms_per_query": round((time.time() - started) * 1000 / max(len(rows), 1), 1), "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=None)
    parser.add_argument("--eval", type=Path, default=EVAL)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    queries = yaml.safe_load(args.eval.read_text(encoding="utf-8"))["queries"]
    with tempfile.TemporaryDirectory() as tmp:
        snap = demo_snapshot(Path(tmp))
        history = demo_history(snap)
        configs: list[tuple[str, Any, Any]] = [("lexical (BM25F + RM3 + thésaurus + n-grammes)", None, None)]
        if args.models and neural.available():
            for mid in ("e5-small", "e5-base"):
                if neural.installed(args.models, mid):
                    enc = neural.Encoder(args.models, mid)
                    configs.append((f"hybride + {mid}", enc, None))
                    if neural.installed(args.models, neural.DEFAULT_RERANKER):
                        configs.append((f"hybride + {mid} + reranker", enc, neural.Reranker(args.models)))
        for name, enc, rr in configs:
            for with_history in (False, True):
                engine = LibrarySearch(snap, encoder=enc, reranker=rr, today=TODAY, history=history if with_history else None)
                report = run(engine, queries)
                label = name + (" + historique" if with_history else "")
                print(f"{label:68s} nDCG@10 {report['ndcg@10']:.3f}  MRR@10 {report['mrr@10']:.3f}  "
                      f"rappel@20 {report['recall@20']:.3f}  {report['ms_per_query']:.0f} ms/question")
                if args.details:
                    for r in sorted(report["rows"], key=lambda r: r["ndcg"])[:12]:
                        print(f"    {r['ndcg']:.2f}  {r['q']}  → {r['top']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
