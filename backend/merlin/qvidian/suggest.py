"""Réponses qualitatives tirées de Qvidian pour une question de RFI : les choix passés des équipes, agrégés.

1. Recherche plein texte dans l'instantané (titre = question type, question soumise, texte, termes appris).
2. On ne garde que les contenus dont la question ressemble vraiment à celle du RFI (similarité des mots porteurs).
3. Chaque contenu est un vote : utilisations (TimesUsedCount), dernière utilisation (DateLastUsed, sinon dernière
   modification), similarité de la question. Un contenu expiré compte peu ; un contenu désactivé ne compte pas.
4. `merlin.rfi.aggregate` regroupe les versions d'un même texte et classe les familles (récence × fréquence).
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from typing import Any

from ..rfi.aggregate import HALF_LIFE_DAYS, Choice, Vote, aggregate, to_date
from .snapshot import STOP, Snapshot

MIN_QUESTION_SIMILARITY = 0.45


def _tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    out = set()
    for w in re.findall(r"[a-z0-9]+", text):
        if len(w) <= 2 or w in STOP:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)  # pluriel simple
    return out


def question_similarity(a: str, b: str, idf: dict[str, float] | None = None) -> float:
    """Recouvrement des mots porteurs, pondéré par leur rareté dans la bibliothèque (« société » compte moins que « vote »)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    w = (lambda t: idf.get(t, max(idf.values(), default=1.0))) if idf else (lambda t: 1.0)
    inter = sum(w(t) for t in ta & tb)
    union = sum(w(t) for t in ta | tb)
    smaller = min(sum(w(t) for t in ta), sum(w(t) for t in tb))
    contained = 0.85 * inter / smaller if min(len(ta), len(tb)) >= 2 and smaller else 0.0
    return max(inter / union if union else 0.0, contained)


def idf_of(snapshot: Snapshot) -> dict[str, float]:
    key = (snapshot.path, snapshot.meta().get("synced_at"), snapshot.meta().get("count"))
    if _IDF.get("key") != key:
        docs = [_tokens(f"{c['title']} {c['question'] or ''}") for c in snapshot.all()]
        df: dict[str, int] = {}
        for d in docs:
            for t in d:
                df[t] = df.get(t, 0) + 1
        n = len(docs)
        _IDF.update(key=key, idf={t: math.log((n + 1) / (k + 1)) + 1 for t, k in df.items()})
    return _IDF["idf"]


_IDF: dict[str, Any] = {}


def votes(snapshot: Snapshot, question: str, k: int = 40, min_similarity: float = MIN_QUESTION_SIMILARITY,
          spread: float = 0.2) -> list[Vote]:
    """Contenus qui répondent à la même question : la similarité sert de filtre (proche de la meilleure), puis de poids."""
    idf = idf_of(snapshot)
    scored = []
    for c in snapshot.search(question, k=k):
        if not c["enabled"] or not (c["text"] or "").strip():
            continue
        sim = max(question_similarity(question, c["title"], idf), question_similarity(question, c["question"] or "", idf))
        if sim >= min_similarity:
            scored.append((sim, c))
    best = max((sim for sim, _ in scored), default=0.0)
    out = []
    for sim, c in scored:
        if sim < best - spread:
            continue  # une autre question de la bibliothèque correspond mieux : celle-ci n'est pas la même question
        expires = to_date(c["expires"])
        expired = c["expired"] or (expires is not None and expires < date.today())
        label = f"#{c['id']} · {c['title'][:70]}" + (f" · {c['folder_path']}" if c["folder_path"] else "")
        out.append(Vote(c["text"].strip(), "qvidian", label, weight=sim * (0.3 if expired else 1.0),
                        when=to_date(c["last_used"]) or to_date(c["modified"]), uses=max(c["times_used"], 1), ref=str(c["id"]),
                        check="expired" if expired else None))
    return out


def suggest(snapshot: Snapshot, question: str, today: date | None = None, half_life: int = HALF_LIFE_DAYS,
            min_share: float = 0.05) -> list[Choice]:
    """Familles de réponses classées ; les familles marginales (< 5 % du score) sont écartées."""
    choices = aggregate(votes(snapshot, question), today=today, half_life=half_life)
    return [c for i, c in enumerate(choices) if i == 0 or c.share >= min_share]


def explain(choice: Choice) -> dict[str, Any]:
    out = choice.public()
    out["contents"] = [v.ref for v in choice.votes]
    return out


__all__ = ["suggest", "votes", "question_similarity", "explain", "MIN_QUESTION_SIMILARITY"]
