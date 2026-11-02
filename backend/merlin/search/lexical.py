"""Index lexicaux en mémoire : BM25F (champs pondérés, bigrammes) avec rétroaction RM3, et n-grammes de caractères.

BM25F (Robertson & Zaragoza) : la fréquence d'un terme est d'abord normalisée champ par champ (longueur du champ),
pondérée (titre / question > termes appris > texte > dossier), puis saturée une seule fois — c'est la variante qui
reste la référence lexicale des bancs d'essai (BEIR, MIRACL). Les bigrammes de racines récompensent les expressions
exactes (« frais de gestion ») sans index de positions.

RM3 (Lavrenko & Croft ; Abdul-Jaleel et al.) : les meilleurs documents d'une première passe enrichissent la question
de leurs termes les plus caractéristiques ; gain classique sur les questions courtes.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .text import bigrams, char_ngrams, terms

K1 = 1.2


@dataclass
class Field:
    name: str
    weight: float
    b: float = 0.75


DEFAULT_FIELDS = [Field("title", 3.0, 0.5), Field("question", 2.5, 0.5), Field("terms", 1.6, 0.3),
                  Field("text", 1.0, 0.75), Field("folder", 0.6, 0.3)]


@dataclass
class Hit:
    index: int
    score: float
    matched: set[str] = field(default_factory=set)


class BM25F:
    def __init__(self, docs: list[dict[str, str]], fields: list[Field] | None = None, bigram_weight: float = 0.6):
        self.fields = fields or DEFAULT_FIELDS
        self.n = len(docs)
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.doc_terms: list[Counter] = []
        lengths: dict[str, list[int]] = {f.name: [] for f in self.fields}
        analysed: list[dict[str, list[str]]] = []
        for d in docs:
            per = {}
            for f in self.fields:
                seq = terms(d.get(f.name) or "")
                per[f.name] = seq
                lengths[f.name].append(len(seq))
            analysed.append(per)
        avg = {k: (sum(v) / len(v) if v and sum(v) else 1.0) for k, v in lengths.items()}
        for i, per in enumerate(analysed):
            tf: dict[str, float] = defaultdict(float)
            bag: Counter = Counter()
            for f in self.fields:
                seq = per[f.name]
                if not seq:
                    continue
                norm = 1 - f.b + f.b * len(seq) / avg[f.name]
                for t, c in Counter(seq).items():
                    tf[t] += f.weight * c / norm
                for t, c in Counter(bigrams(seq)).items():
                    tf[t] += bigram_weight * f.weight * c / norm
                bag.update(seq)
            for t, value in tf.items():
                self.postings[t].append((i, value))
            self.doc_terms.append(bag)
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def score(self, query: dict[str, float], k: int = 100) -> list[Hit]:
        acc: dict[int, float] = defaultdict(float)
        matched: dict[int, set[str]] = defaultdict(set)
        for t, qw in query.items():
            plist = self.postings.get(t)
            if not plist:
                continue
            idf = self.idf[t]
            for i, tf in plist:
                acc[i] += qw * idf * tf * (K1 + 1) / (tf + K1)
                if "_" not in t:
                    matched[i].add(t)
        best = sorted(acc.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(i, s, matched[i]) for i, s in best]

    def rm3(self, query: dict[str, float], hits: list[Hit], fb_docs: int = 8, fb_terms: int = 10, weight: float = 0.35) -> dict[str, float]:
        """Question enrichie : termes fréquents dans les meilleurs documents et rares ailleurs (pondérés par le score)."""
        top = hits[:fb_docs]
        if len(top) < 2:
            return dict(query)
        total = sum(h.score for h in top) or 1.0
        mass: dict[str, float] = defaultdict(float)
        for h in top:
            bag = self.doc_terms[h.index]
            size = sum(bag.values()) or 1
            for t, c in bag.items():
                mass[t] += (h.score / total) * (c / size) * self.idf.get(t, 0.0)
        for t in query:
            mass.pop(t, None)
        extra = sorted(mass.items(), key=lambda kv: -kv[1])[:fb_terms]
        if not extra:
            return dict(query)
        top_mass = extra[0][1] or 1.0
        out = dict(query)
        for t, m in extra:
            out[t] = max(out.get(t, 0.0), weight * m / top_mass)
        return out


def query_vector(text: str) -> tuple[dict[str, float], list[str]]:
    """{terme: poids} d'une question : racines (1,0), bigrammes (0,7) ; et la séquence des racines."""
    seq = terms(text)
    q: dict[str, float] = {}
    for t in seq:
        q[t] = q.get(t, 0.0) + 1.0
    for t in bigrams(seq):
        q[t] = max(q.get(t, 0.0), 0.7)
    return q, seq


class CharNgrams:
    """TF-IDF cosinus sur n-grammes de caractères (titre + question + début du texte)."""

    def __init__(self, texts: list[str], n: int = 4):
        self.n = n
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        counts = [Counter(char_ngrams(t, n)) for t in texts]
        df: Counter = Counter()
        for c in counts:
            df.update(c.keys())
        size = len(texts)
        self.idf = {g: math.log((size + 1) / (k + 1)) + 1 for g, k in df.items()}
        for i, c in enumerate(counts):
            vec = {g: (1 + math.log(v)) * self.idf[g] for g, v in c.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            for g, v in vec.items():
                self.postings[g].append((i, v / norm))

    def score(self, text: str, k: int = 100) -> list[Hit]:
        c = Counter(char_ngrams(text, self.n))
        vec = {g: (1 + math.log(v)) * self.idf[g] for g, v in c.items() if g in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        acc: dict[int, float] = defaultdict(float)
        for g, v in vec.items():
            for i, w in self.postings[g]:
                acc[i] += v / norm * w
        best = sorted(acc.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(i, s) for i, s in best]


__all__ = ["BM25F", "CharNgrams", "Field", "Hit", "query_vector", "DEFAULT_FIELDS"]
