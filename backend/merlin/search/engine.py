"""Moteur hybride générique : plusieurs recherches indépendantes, fusionnées, puis relues.

1. Question : racines + bigrammes, expansion par le thésaurus métier, langue (es / it → pivot français).
2. Rappel (jusqu'à 100 candidats par voie) :
   - BM25F à champs pondérés, puis RM3 (rétroaction sur les meilleurs documents) ;
   - n-grammes de caractères (fautes, dérivations, sigles) ;
   - vecteurs denses multilingues (si un encodeur est installé), texte découpé en passages, score = meilleur passage.
3. Fusion par rangs réciproques pondérée (RRF, k = 60) : insensible aux échelles de score de chaque voie.
4. Relecture des 30 premiers : cross-encoder (si installé) + couverture de la question par le titre / la question
   type + expression exacte. La couche métier (merlin.qvidian.library_search) ajoute portée, fonds, utilisations.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .lexical import BM25F, DEFAULT_FIELDS, CharNgrams, Field, Hit, query_vector
from .neural import Encoder, Reranker, VectorCache, text_hash
from .text import fold, terms
from .thesaurus import expand

RRF_K = 60
WEIGHTS = {"bm25": 1.0, "dense": 1.1, "ngram": 0.35, "history": 1.4}  # history : questions des anciens RFI qui ont reçu ce texte
RERANK_DEPTH = int(os.environ.get("MERLIN_RERANK_DEPTH", "20"))  # 20 = même qualité que 30, 30 % plus rapide (mesuré)
RERANK_MODE = "rrf"  # fusion par rangs : première passe + reranker (mesuré : la plus robuste)
RERANK_WEIGHT = 0.8
CHUNK_WORDS, CHUNK_OVERLAP, MAX_CHUNKS = 160, 40, 4


@dataclass
class Doc:
    id: Any
    title: str = ""
    question: str = ""
    text: str = ""
    terms: str = ""
    folder: str = ""
    asked: list[str] = field(default_factory=list)  # questions des anciens RFI auxquelles ce texte a répondu

    def fields(self) -> dict[str, str]:
        return {"title": self.title, "question": self.question if fold(self.question) != fold(self.title) else "",
                "text": self.text, "terms": self.terms, "folder": self.folder, "asked": "\n".join(self.asked)}


@dataclass
class Candidate:
    index: int
    rrf: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    matched: set[str] = field(default_factory=set)
    coverage: float = 0.0  # part de la question (pondérée par la rareté) retrouvée dans le titre / la question type / une question passée
    text_coverage: float = 0.0
    phrase: bool = False
    rerank: float | None = None
    relevance: float = 0.0


@dataclass
class QueryInfo:
    text: str
    language: str
    pivot: str
    seq: list[str]
    vector: dict[str, float]
    expansions: list[str]
    equivalents: list = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def _chunks(doc: Doc) -> list[str]:
    head = " — ".join(x for x in (doc.title, doc.question if fold(doc.question) != fold(doc.title) else "") if x)
    asked = [f"{q}\n{(doc.text or '')[:600]}" for q in doc.asked[:6]]  # chaque question passée : un passage de plus
    words = (doc.text or "").split()
    if len(words) <= CHUNK_WORDS:
        return [f"{head}\n{doc.text}".strip()] + asked
    out, start = [], 0
    while start < len(words) and len(out) < MAX_CHUNKS:
        piece = " ".join(words[start:start + CHUNK_WORDS])
        out.append(f"{head}\n{piece}" if not out else f"{head} (suite)\n{piece}")
        start += CHUNK_WORDS - CHUNK_OVERLAP
    return out + asked


class HybridIndex:
    def __init__(self, docs: list[Doc], encoder: Encoder | None = None, reranker: Reranker | None = None,
                 vectors: VectorCache | None = None, progress: Callable[[str, int, int], None] | None = None):
        started = time.time()
        self.docs = docs
        self.bm25 = BM25F([d.fields() for d in docs], fields=DEFAULT_FIELDS + [Field("asked", 2.8, 0.4)])
        # Questions passées : une voie de recherche à part (une question = un document, rattaché au texte choisi)
        self.asked_owner: list[int] = [i for i, d in enumerate(docs) for _ in d.asked]
        self.asked = BM25F([{"title": q} for d in docs for q in d.asked], fields=[Field("title", 1.0, 0.5)]) if self.asked_owner else None
        self.asked_terms = [set(terms(" ".join(d.asked))) for d in docs]
        self.asked_sets = [[set(terms(q)) for q in d.asked] for d in docs]
        self.ngrams = CharNgrams([f"{d.title} {d.question} {(d.text or '')[:400]}" for d in docs])
        self.title_terms = [set(terms(f"{d.title} {d.question}")) for d in docs]
        self.text_terms = [set(terms(d.text or "")) for d in docs]
        self.encoder, self.reranker = encoder, reranker
        self.chunk_doc: list[int] = []
        self.matrix: np.ndarray | None = None
        if encoder is not None:
            chunks, owners = [], []
            for i, d in enumerate(docs):
                for c in _chunks(d):
                    chunks.append(c)
                    owners.append(i)
            keys = [f"{encoder.id}:{text_hash(c)}" for c in chunks]
            cache = vectors if vectors is not None else VectorCache()
            todo = cache.missing(keys)
            if todo:
                by_key = dict(zip(keys, chunks))
                for start in range(0, len(todo), 64):
                    part = todo[start:start + 64]
                    cache.put(part, encoder.encode([by_key[k] for k in part], "passage"))
                    if progress:
                        progress("Indexation sémantique", min(start + 64, len(todo)), len(todo))
                cache.save(set(keys))  # un fichier par modèle : les textes disparus sont oubliés
            self.matrix = cache.matrix(keys) if keys else None
            self.chunk_doc = owners
        self.build_seconds = round(time.time() - started, 2)

    def __getstate__(self) -> dict:
        """Index enregistrable sur disque (rechargé en ~1 s au lieu d'être reconstruit) : sans les sessions ONNX, rattachées après."""
        state = self.__dict__.copy()
        state["encoder"], state["reranker"] = None, None
        return state

    # ------------------------------------------------------------------ question
    def analyse(self, text: str) -> QueryInfo:
        from ..rfi.lexicon import question_language, to_pivot
        from ..rfi.ontology import norm

        lang = question_language(text)
        pivot = to_pivot(norm(text), lang) if lang in {"es", "it"} else text
        vector, seq = query_vector(pivot)
        extra, matched, equivalents = expand(seq)
        for t, w in extra.items():
            vector[t] = max(vector.get(t, 0.0), w)
        return QueryInfo(text, lang, pivot, seq, vector, matched, equivalents)

    # ------------------------------------------------------------------ recherche
    def search(self, text: str, k: int = 50, allowed: Callable[[int], bool] | None = None, rerank: bool = True,
               rm3: bool = True, depth: int = 100) -> tuple[QueryInfo, list[Candidate]]:
        q = self.analyse(text)
        t0 = time.time()
        lists: dict[str, list[Hit]] = {}
        if q.vector:
            first = self.bm25.score(q.vector, depth)
            if rm3 and len(q.seq) <= 12 and len(first) >= 3:
                first = self.bm25.score(self.bm25.rm3(q.vector, first), depth)
            lists["bm25"] = first
        lists["ngram"] = self.ngrams.score(q.pivot, depth)
        if self.asked is not None and q.vector and q.seq:
            # Une question passée ne compte que si elle couvre vraiment la question posée (mots rares d'abord) :
            # un mot commun (« société », « gestion ») ne suffit pas à rattacher un texte choisi pour autre chose.
            content = list(dict.fromkeys(q.seq))
            top_idf = max(self.bm25.idf.values(), default=1.0)
            weight = {t: self.bm25.idf.get(t, top_idf) for t in content}  # mot absent du corpus : le plus informatif
            total = sum(weight.values()) or 1.0
            flat = [qs for sets in self.asked_sets for qs in sets]
            best: dict[int, float] = {}
            for h in self.asked.score(q.vector, depth * 2):
                cover = sum(weight[t] for t in content if t in flat[h.index]) / total
                if cover < 0.5:
                    continue
                d = self.asked_owner[h.index]
                best[d] = max(best.get(d, 0.0), h.score * cover)
            if best:
                lists["history"] = [Hit(i, s) for i, s in sorted(best.items(), key=lambda kv: -kv[1])[:depth]]
        q.timings["lexical_ms"] = round((time.time() - t0) * 1000, 1)
        if self.encoder is not None and self.matrix is not None and len(self.chunk_doc):
            t1 = time.time()
            qv = self.encoder.encode([q.text], "query")[0]
            sims = self.matrix @ qv
            best: dict[int, float] = {}
            for ci, s in enumerate(sims):
                d = self.chunk_doc[ci]
                if s > best.get(d, -1.0):
                    best[d] = float(s)
            ranked = sorted(best.items(), key=lambda kv: -kv[1])[:depth]
            lists["dense"] = [Hit(i, s) for i, s in ranked]
            q.timings["dense_ms"] = round((time.time() - t1) * 1000, 1)

        cands: dict[int, Candidate] = {}
        for name, hits in lists.items():
            w = WEIGHTS.get(name, 0.5)
            for rank, h in enumerate(hits, start=1):
                if allowed is not None and not allowed(h.index):
                    continue
                c = cands.setdefault(h.index, Candidate(h.index))
                c.rrf += w / (RRF_K + rank)
                c.ranks[name] = rank
                c.scores[name] = h.score
                c.matched |= h.matched
        ordered = sorted(cands.values(), key=lambda c: -c.rrf)[: max(k, RERANK_DEPTH)]
        self._features(q, ordered)
        if rerank and self.reranker is not None and ordered:
            t2 = time.time()
            head = ordered[:RERANK_DEPTH]
            passages = [self._passage(c.index) for c in head]
            for c, s in zip(head, self.reranker.score(q.text, passages)):
                c.rerank = float(s)
            q.timings["rerank_ms"] = round((time.time() - t2) * 1000, 1)
        top_rrf = max((c.rrf for c in ordered), default=1.0) or 1.0
        for c in ordered:
            base = c.rrf / top_rrf
            lexical = 0.6 * c.coverage + 0.25 * c.text_coverage + (0.15 if c.phrase else 0.0)
            c.relevance = (0.6 * base + 0.4 * lexical) if self.encoder is not None else (0.5 * base + 0.5 * lexical)
        reranked = [c for c in ordered if c.rerank is not None]
        if reranked:
            lo, hi = min(c.relevance for c in reranked), max(c.relevance for c in reranked)
            mode = os.environ.get("MERLIN_RERANK_MODE", RERANK_MODE)
            first = sorted(reranked, key=lambda c: -c.relevance)
            by_ce = sorted(reranked, key=lambda c: -(c.rerank or 0.0))
            r1 = {c.index: r for r, c in enumerate(first, start=1)}
            r2 = {c.index: r for r, c in enumerate(by_ce, start=1)}
            mean = sum(c.rerank or 0.0 for c in reranked) / len(reranked)
            for c in reranked:
                if mode == "blend50":
                    c.relevance = 0.5 * c.rerank + 0.5 * c.relevance
                elif mode == "blend30":
                    c.relevance = 0.3 * c.rerank + 0.7 * c.relevance
                elif mode == "rrf":
                    c.relevance = 1 / (10 + r1[c.index]) + RERANK_WEIGHT / (10 + r2[c.index])
                else:  # centered : le reranker déplace un résultat de ±0,3 au plus autour de la moyenne
                    c.relevance = c.relevance + 0.35 * (c.rerank - mean)
            if mode == "rrf":  # rangs fusionnés ramenés sur l'échelle de la première passe (seuils et score affiché inchangés)
                values = [c.relevance for c in reranked]
                vlo, vhi = min(values), max(values)
                for c in reranked:
                    c.relevance = lo + (hi - lo) * ((c.relevance - vlo) / (vhi - vlo) if vhi > vlo else 1.0)
        ordered.sort(key=lambda c: -c.relevance)
        q.timings["total_ms"] = round((time.time() - t0) * 1000, 1)
        return q, ordered[:k]

    def _passage(self, i: int) -> str:
        d = self.docs[i]
        head = d.title if fold(d.question) == fold(d.title) or not d.question else f"{d.title} — {d.question}"
        return f"{head}\n{(d.text or '')[:1500]}"

    def _features(self, q: QueryInfo, cands: list[Candidate]) -> None:
        """Couverture de la question (mots rares d'abord) dans la question type et dans le texte, en comptant comme
        couvert un mot dont un équivalent du thésaurus est présent (« benchmark » ↔ « indicateur de référence »)."""
        content = [t for t in dict.fromkeys(q.seq)]
        weight = {t: self.bm25.idf.get(t, max(self.bm25.idf.values(), default=1.0)) for t in content}
        total = sum(weight.values()) or 1.0
        phrase = " ".join(q.seq)

        def covered(bag: set[str]) -> float:
            hit = {t for t in content if t in bag}
            for own, others in q.equivalents:
                if any(all(t in bag for t in other) for other in others):
                    hit |= set(own)
            return sum(weight[t] for t in content if t in hit) / total

        for c in cands:
            past = max((covered(t) for t in self.asked_sets[c.index]), default=0.0)
            c.coverage = max(covered(self.title_terms[c.index]), past)
            c.text_coverage = covered(self.text_terms[c.index])
            if len(q.seq) >= 2:
                d = self.docs[c.index]
                c.phrase = phrase in " ".join(terms(f"{d.title} {d.question}")) or phrase in " ".join(terms(d.text or ""))

    def similar(self, i: int, k: int = 8) -> list[tuple[int, float]]:
        """Contenus proches d'un contenu (sens si encodeur, sinon vocabulaire)."""
        if self.matrix is not None and self.encoder is not None:
            rows = [ci for ci, d in enumerate(self.chunk_doc) if d == i]
            if rows:
                v = self.matrix[rows].mean(axis=0)
                v = v / (np.linalg.norm(v) or 1.0)
                sims = self.matrix @ v
                best: dict[int, float] = {}
                for ci, s in enumerate(sims):
                    d = self.chunk_doc[ci]
                    if d != i and s > best.get(d, -1):
                        best[d] = float(s)
                return sorted(best.items(), key=lambda kv: -kv[1])[:k]
        d = self.docs[i]
        q, _ = query_vector(f"{d.title} {d.question} {(d.text or '')[:600]}")
        hits = [h for h in self.bm25.score(q, k + 1) if h.index != i][:k]
        top = hits[0].score if hits else 1.0
        return [(h.index, round(h.score / top, 3)) for h in hits]


def ndcg(ranked: list[Any], gains: dict[Any, float], k: int = 10) -> float:
    dcg = sum(gains.get(doc, 0.0) / math.log2(r + 2) for r, doc in enumerate(ranked[:k]))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(r + 2) for r, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def mrr(ranked: list[Any], relevant: set[Any], k: int = 10) -> float:
    for r, doc in enumerate(ranked[:k], start=1):
        if doc in relevant:
            return 1 / r
    return 0.0


def recall(ranked: list[Any], relevant: set[Any], k: int = 20) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


__all__ = ["HybridIndex", "Doc", "Candidate", "QueryInfo", "ndcg", "mrr", "recall", "WEIGHTS", "RRF_K"]
