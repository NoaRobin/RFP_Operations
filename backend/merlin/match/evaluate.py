"""Banc du rapprochement « même question ? » sur des questionnaires fictifs simulés.

    cd backend && python -m merlin.match.evaluate [--models ../data/models] [--precise]

Simule des années de due diligences (chaque questionnaire pose une partie des sujets, avec une formulation au hasard
et la réponse Qvidian du sujet), apprend sur cet historique, puis pose les formulations **jamais vues** : la bonne
réponse doit sortir en premier, et les probabilités doivent être justes (calibration mesurée hors apprentissage).
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .gbdt import metrics
from .matcher import QuestionMatcher, build_bank
from .service import concept_function

EVAL = Path(__file__).resolve().parents[2] / "tests" / "question_match_eval.yaml"


class _P:
    def __init__(self, i, question, answer, file, day):
        self.id, self.question, self.answer_raw, self.source_file, self.ref_date = i, question, answer, file, day
        self.origin, self.fund_name, self.isin, self.blocked = "sharepoint", "", "", False


class _L:
    def __init__(self, pid, cid):
        self.precedent_id, self.content_id = pid, cid


def simulate(topics: list[dict[str, Any]], files: int = 60, seed: int = 3, today: date = date(2026, 10, 1)):
    rng = np.random.default_rng(seed)
    contents = [{"id": 1000 + t["id"], "title": t["train"][0], "question": t["train"][0], "enabled": True,
                 "text": " ".join(t["train"]) + f" (texte type fictif {t['id']})"} for t in topics]
    precedents, links = [], []
    for f in range(files):
        day = (today - timedelta(days=int(rng.integers(0, 1500)))).isoformat()
        for t in topics:
            if rng.random() < 0.55:
                q = t["train"][int(rng.integers(0, len(t["train"])))]
                pid = f"F{f}:{t['id']}"
                precedents.append(_P(pid, q, contents[t["id"] - 1]["text"], f"DDQ_client_{f}.xlsx", day))
                links.append(_L(pid, 1000 + t["id"]))
    return contents, precedents, links


def run(models: Path | None = None, precise: bool = False, verbose: bool = False) -> dict[str, Any]:
    from ..search import neural

    topics = yaml.safe_load(EVAL.read_text(encoding="utf-8"))["topics"]
    contents, precedents, links = simulate(topics)
    enc = rr = enc2 = rr2 = None
    if models is not None and neural.available():
        enc = neural.Encoder(models, "e5-small") if neural.installed(models, "e5-small") else None
        rr = neural.Reranker(models, "rerank-mminilm") if neural.installed(models, "rerank-mminilm") else None
        if precise:
            big = next((m for m in ("e5-large", "e5-base") if neural.installed(models, m)), None)
            enc2 = neural.Encoder(models, big) if big else None
            rr2 = neural.Reranker(models, "rerank-bge-m3") if neural.installed(models, "rerank-bge-m3") else None
    t0 = time.time()
    m = QuestionMatcher(build_bank(precedents, contents, links), enc, rr, enc2, rr2, concept_function())
    trained = m.train(lambda cid: next(c["text"] for c in contents if c["id"] == cid))
    train_s = time.time() - t0
    ok, ps, ys, ms, rows = 0, [], [], [], []
    for t in topics:
        for q in t["test"]:
            t1 = time.time()
            votes = m.content_votes(q)
            ms.append((time.time() - t1) * 1000)
            top = votes[0][0] if votes else None
            ok += top == 1000 + t["id"]
            for mt in m.match(q, k=8, min_p=0.0):
                ps.append(mt.p)
                ys.append(float(1000 + t["id"] in mt.entry.contents))
            rows.append((t["id"], q, top, round(votes[0][1], 2) if votes else None))
    n = sum(len(t["test"]) for t in topics)
    report = {"questions": n, "top1": round(ok / n, 3), "held_out": metrics(np.array(ps), np.array(ys)),
              "train": trained.get("fast"), "precise": trained.get("precise"), "trained": trained.get("trained"),
              "ms_per_question": round(float(np.mean(ms)), 1), "train_seconds": round(train_s, 1), "bank": m.stats()["distinct"]}
    if verbose:
        for tid, q, top, p in rows:
            if top != 1000 + tid:
                print(f"  ✗ sujet {tid} « {q} » → {top} ({p})")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path)
    ap.add_argument("--precise", action="store_true")
    ap.add_argument("--details", action="store_true")
    a = ap.parse_args()
    r = run(a.models, a.precise, a.details)
    h = r["held_out"]
    print(f"top-1 {r['top1']:.3f} sur {r['questions']} formulations jamais vues · {r['ms_per_question']} ms / question · "
          f"apprentissage {r['train_seconds']} s")
    print(f"calibration hors apprentissage : ECE {h['ece']} · Brier {h['brier']} · AUC {h['auc']} · seuil {h['threshold']} "
          f"(précision {h['precision_at_threshold']}, rappel {h['recall_at_threshold']})")


if __name__ == "__main__":
    main()
