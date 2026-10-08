"""Recherche hybride des précédents : BM25 (FTS5) pour le rappel, puis reclassement fin.

Similarité finale = mélange de :
  - cosinus TF-IDF sur trigrammes de caractères (robuste aux fautes, accents, pluriels, « Frais de gestion » ≈ « frais gestion ») ;
  - Jaccard sur les mots porteurs de sens (évite « date de création du fonds » ≈ « date de création de la stratégie ») ;
  - embeddings sémantiques si un modèle est installé (stratégie interchangeable, voir Embedder).
"""
from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..ontology import norm, stem, tokens
from .model import Precedent
from .store import PrecedentStore

STOP = {"de", "du", "des", "la", "le", "les", "l", "d", "un", "une", "et", "ou", "en", "au", "aux", "a", "pour", "par", "sur", "dans",
        "avec", "est", "il", "elle", "y", "t", "quel", "quelle", "quels", "quelles", "votre", "vos", "ce", "cette", "the", "of", "a",
        "an", "and", "or", "to", "for", "in", "on", "is", "are", "what", "which", "your", "does", "do", "please", "indiquer",
        "veuillez", "merci", "s", "si", "oui", "non", "yes", "no", "vous", "nous", "pouvez", "can", "you"}


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """Embeddings multilingues locaux (facultatif : MERLIN_RFI_EMBEDDER=<modèle sentence-transformers>)."""

    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self.name = model
        self._model = SentenceTransformer(model)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)


def default_embedder() -> Embedder | None:
    model = os.environ.get("MERLIN_RFI_EMBEDDER", "").strip()
    if not model:
        return None
    try:
        return SentenceTransformerEmbedder(model)
    except Exception:  # noqa: BLE001 - bibliothèque absente : on reste sur le lexical
        return None


def _grams(text: str) -> Counter:
    t = f"  {text}  "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


def content_words(text: str) -> set[str]:
    return {stem(w) for w in tokens(norm(text)) if w not in STOP and len(w) > 1 and not w.isdigit()}


@dataclass
class Hit:
    precedent: Precedent
    similarity: float

    def to_public(self) -> dict:
        return {**self.precedent.to_public(), "similarity": round(self.similarity, 3)}


class PrecedentIndex:
    """Index en mémoire reconstruit quand le stockage change."""

    def __init__(self, store: PrecedentStore, embedder: Embedder | None = None):
        self.store = store
        self.embedder = embedder
        self._version = -1
        self._idf: dict[str, float] = {}
        self._vecs: dict[str, tuple[dict[str, float], float]] = {}
        self._emb: dict[str, np.ndarray] = {}
        self._words: dict[str, set[str]] = {}

    def _refresh(self) -> None:
        if self._version == self.store.version and self._vecs:
            return
        questions = self.store.questions()
        df: Counter = Counter()
        grams = {}
        for pid, q in questions:
            g = _grams(q)
            grams[pid] = g
            df.update(g.keys())
        n = max(1, len(questions))
        self._idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self._vecs = {pid: self._vector(g) for pid, g in grams.items()}
        self._words = {pid: content_words(q) for pid, q in questions}
        self._emb = {}
        if self.embedder is not None and questions:
            uniq = list(dict.fromkeys(q for _, q in questions))
            mat = self.embedder.encode(uniq)
            by_q = dict(zip(uniq, mat))
            self._emb = {pid: by_q[q] for pid, q in questions}
        self._version = self.store.version

    def _vector(self, grams: Counter) -> tuple[dict[str, float], float]:
        vec = {g: (1 + math.log(c)) * self._idf.get(g, 1.0) for g, c in grams.items()}
        return vec, math.sqrt(sum(v * v for v in vec.values())) or 1.0

    def similarity(self, a: str, pid: str, qvec: tuple[dict[str, float], float], qwords: set[str], qemb: np.ndarray | None) -> float:
        vec, nrm = self._vecs[pid]
        qv, qn = qvec
        small, big = (qv, vec) if len(qv) < len(vec) else (vec, qv)
        cos = sum(w * big.get(g, 0.0) for g, w in small.items()) / (qn * nrm)
        words = self._words.get(pid, set())
        jac = len(qwords & words) / len(qwords | words) if (qwords or words) else 0.0
        lexical = 0.65 * cos + 0.35 * jac
        if qemb is not None and pid in self._emb:
            return 0.5 * lexical + 0.5 * float(np.dot(qemb, self._emb[pid]))
        return lexical

    def search(self, question: str, k: int = 8, min_similarity: float = 0.72) -> list[Hit]:
        self._refresh()
        if not self._vecs:
            return []
        qn = norm(question)
        candidates = [pid for pid, _ in self.store.bm25(qn)]
        if not candidates:
            return []
        qvec = self._vector(_grams(qn))
        qwords = content_words(qn)
        qemb = self.embedder.encode([qn])[0] if self.embedder is not None else None
        scored = sorted(((self.similarity(qn, pid, qvec, qwords, qemb), pid) for pid in candidates if pid in self._vecs), reverse=True)
        keep = [(s, pid) for s, pid in scored if s >= min_similarity][: k * 3]
        precedents = {p.id: p for p in self.store.get([pid for _, pid in keep])}
        return [Hit(precedents[pid], s) for s, pid in keep if pid in precedents][: k * 3]
