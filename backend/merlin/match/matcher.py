"""Rapprochement « même question ? » entre une question nouvelle et toutes les questions déjà tombées.

Une seule implémentation, utilisée par la recherche Qvidian ET par le compléteur RFI : la même question collée dans
l'un ou l'autre donne les mêmes questions passées, les mêmes probabilités, donc la même réponse.

Banque : chaque question des anciens RFI (SharePoint, lot 02, projets Qvidian), et chaque question type Qvidian, avec
ce qui y a été répondu (texte Qvidian choisi, réponse rédigée, fichier, date, fonds). Les doublons exacts (numérotation,
ponctuation, casse) sont fusionnés : 400 questionnaires × 50–200 questions donnent souvent 3 à 5 fois moins de
questions distinctes.

Pour une question :
1. **rappel** large et rapide : BM25 (+ thésaurus métier FR / EN), n-grammes de caractères (fautes, variantes), vecteurs
   E5 « rapides » (produit matriciel sur toute la banque, ~10 ms pour 100 000 questions) ; fusion par rangs (RRF) ;
2. **critères** par couple : sens (E5), lecture croisée (cross-encoder), couverture des mots rares dans les deux sens,
   n-grammes, concept de l'ontologie (même concept / concepts différents), conflits qui changent la question (nombres,
   années, périodes, ISIN, négation, oui/non contre « décrivez ») ;
3. **probabilité calibrée** (gradient boosting + isotonique, `gbdt.py`) apprise sur VOS anciens RFI : deux questions
   auxquelles l'équipe a répondu avec le même texte Qvidian (ou la même réponse rédigée) sont « la même » ;
   deux questions de concepts différents, ou aux réponses sans rapport, ne le sont pas ;
4. **cascade** : si le pack « Précis » est installé, seuls les cas où le rapide hésite (entre 10 % et 90 %) sont relus
   par les modèles lents — l'essentiel du temps reste celui du rapide.
Le sens seul ne suffit jamais : sans accord du concept, deux questions de concepts différents sont pénalisées.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Iterable

import numpy as np

from ..rfi.aggregate import similarity
from ..search.lexical import BM25F, CharNgrams, Field, query_vector
from ..search.text import fold, terms
from ..search.thesaurus import expand
from .gbdt import CalibratedModel

FAST = ["exact", "bm25_rel", "cov_q", "cov_c", "chars", "dense", "rerank", "concept", "concept_conf", "numbers", "isin",
        "negation", "qtype", "length", "rank"]
PRECISE = FAST + ["dense2", "rerank2"]
NUMBERING = re.compile(r"^\s*(?:(?:q(?:uestion)?|n°|no\.?)\s*\d+[a-z]?\s*[.):-]?\s+|\d+(?:\.\d+)*[.)]\s+|\d+(?:\.\d+)+\s+|[a-z][).]\s+)", re.I)
NUM = re.compile(r"(?<![a-z0-9.,])\d+(?:[.,]\d+)?")
ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
NEG = {"not", "no", "non", "pas", "sans", "without", "never", "jamais", "excluding", "hors", "except", "sauf", "aucun", "aucune", "none"}
YESNO = re.compile(r"^(is|are|does|do|did|has|have|can|could|will|would|should|was|were|est ce|est il|est elle|avez vous|existe t il|"
                   r"y a t il|disposez vous|etes vous|le fonds est|la societe a|es|son|tiene|hay|e |sono|ha |avete|esiste)\b")
LONG = 40
MIN_EXAMPLES = 100
EVIDENCE_CAP = 0.3
RERANK_TOP = 10
HALF_LIFE = 730  # jours : une question tombée il y a deux ans compte moitié moins qu'aujourd'hui


NUMBER_WORDS = {"un": 1, "une": 1, "one": 1, "uno": 1, "deux": 2, "two": 2, "dos": 2, "due": 2, "trois": 3, "three": 3, "tres": 3,
                "tre": 3, "cinq": 5, "five": 5, "cinco": 5, "cinque": 5, "dix": 10, "ten": 10, "diez": 10, "dieci": 10}
PERIOD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mois|months?|meses|mesi|ans?|annees?|years?|yrs?|anos?|anni|y)\b")


def numbers(text: str) -> frozenset[str]:
    """Nombres d'une question, périodes ramenées en années (« 12 mois » = « 1 an » = « one year ») : c'est ce qui
    distingue « performance 1 an » de « performance 3 ans »."""
    t = fold(text)
    t = re.sub(r"\b(" + "|".join(NUMBER_WORDS) + r")\b(?=\s+(?:mois|months?|meses|mesi|ans?|annees?|years?|anos?|anni)\b)",
               lambda m: str(NUMBER_WORDS[m.group(1)]), t)
    t = re.sub(r"\b(?:a|an|one)\s+(year|an)\b", r"1 \1", t)
    out = set()
    for m in PERIOD.finditer(t):
        n = float(m.group(1).replace(",", "."))
        out.add(f"{n / 12:g}y" if m.group(2).startswith("m") else f"{n:g}y")
    rest = PERIOD.sub(" ", t)
    out |= {x.replace(",", ".") for x in NUM.findall(rest)}
    return frozenset(out)


def key(question: str) -> str:
    """Clé de fusion : numérotation, ponctuation, accents et casse ignorés."""
    text = NUMBERING.sub("", question or "")
    return " ".join(re.sub(r"[^\w%]+", " ", fold(text)).split())


@dataclass
class Occurrence:
    question: str
    answer: str = ""
    file: str = ""
    date: str = ""
    fund: str = ""
    content_id: int | None = None
    origin: str = ""


@dataclass
class Entry:
    key: str
    text: str
    occ: list[Occurrence] = field(default_factory=list)

    @property
    def contents(self) -> set[int]:
        return {o.content_id for o in self.occ if o.content_id is not None}

    @property
    def files(self) -> set[str]:
        return {o.file for o in self.occ if o.file}


@dataclass
class Match:
    entry: Entry
    p: float
    features: dict[str, float]
    precise: bool = False

    def public(self) -> dict[str, Any]:
        e = self.entry
        last = max((o.date for o in e.occ if o.date), default="")
        return {"question": e.text, "p": round(self.p, 3), "files": len(e.files), "last": last, "contents": sorted(e.contents),
                "precise": self.precise, "examples": [{"file": o.file, "date": o.date, "fund": o.fund, "answer": (o.answer or "")[:300],
                                                        "content_id": o.content_id} for o in e.occ[:4]],
                "why": explain(self.features)}


def explain(f: dict[str, float]) -> list[str]:
    out = []
    if f.get("exact"):
        out.append("même question mot pour mot")
    if f.get("dense", -1) >= 0.9 or f.get("dense2", -1) >= 0.9:
        out.append("même sens")
    if f.get("concept") == 1:
        out.append("même concept de l'ontologie")
    if f.get("concept") == -1:
        out.append("concepts différents")
    if f.get("numbers") == 1:
        out.append("nombres ou périodes différents")
    if f.get("negation") == 1:
        out.append("négation différente")
    if f.get("qtype") == 1:
        out.append("oui / non contre question ouverte")
    if f.get("cov_q", 0) >= 0.85 and f.get("cov_c", 0) >= 0.85:
        out.append("mêmes mots importants")
    return out


def _recency(day: str, today: date) -> float:
    try:
        age = (today - date.fromisoformat(day[:10])).days
    except (ValueError, TypeError):
        return 0.5
    return 0.5 ** (max(0, age) / HALF_LIFE)


# ---------------------------------------------------------------------------------------------- banque
def build_bank(precedents: Iterable[Any], contents: Iterable[dict[str, Any]], links: Iterable[Any]) -> list[Entry]:
    by_pid = {getattr(l, "precedent_id", ""): l.content_id for l in links if getattr(l, "precedent_id", "")}
    entries: dict[str, Entry] = {}

    def add(question: str, occ: Occurrence) -> None:
        k = key(question)
        if len(k) < 4:
            return
        e = entries.get(k)
        if e is None:
            e = entries[k] = Entry(k, " ".join(question.split()))
        e.occ.append(occ)

    for p in precedents:
        if getattr(p, "blocked", False):
            continue
        raw = getattr(p, "answer_text", None) or getattr(p, "answer_raw", "")
        answer = raw if isinstance(raw, str) else str(raw or "")
        fund = getattr(p, "fund_name", "") or getattr(p, "isin", "") or ""
        add(p.question, Occurrence(p.question, answer, p.source_file, (getattr(p, "ref_date", "") or "")[:10], fund,
                                   by_pid.get(p.id), getattr(p, "origin", "")))
    for c in contents:
        if not c.get("enabled", True) or not (c.get("text") or "").strip():
            continue
        for q in {c.get("question") or "", c.get("title") or ""}:
            if q.strip():
                add(q, Occurrence(q, c.get("text") or "", "", (c.get("last_used") or "")[:10], "", c["id"], "qvidian"))
    return list(entries.values())


# ---------------------------------------------------------------------------------------------- moteur
class QuestionMatcher:
    def __init__(self, entries: list[Entry], encoder=None, reranker=None, precise_encoder=None, precise_reranker=None,
                 concept_of: Callable[[str], tuple[str, float] | None] | None = None, today: date | None = None,
                 vectors: Any = None):
        self.entries = entries
        self.today = today or date.today()
        self.encoder, self.reranker = encoder, reranker
        self.precise_encoder, self.precise_reranker = precise_encoder, precise_reranker
        self._concept_of = concept_of
        self.fast_model: CalibratedModel | None = None
        self.precise_model: CalibratedModel | None = None
        t0 = time.time()
        self.bm25 = BM25F([{"question": e.text} for e in entries], [Field("question", 1.0, 0.5)])
        self.ngrams = CharNgrams([e.text for e in entries]) if entries else None
        self.top_idf = max(self.bm25.idf.values(), default=1.0)
        self.terms = [set(terms(e.text)) for e in entries]
        self.by_key = {e.key: i for i, e in enumerate(entries)}
        self.matrix = None
        if encoder is not None and entries:
            self.matrix = self._encode_all(encoder, vectors)
        self.build_seconds = round(time.time() - t0, 2)
        self._cache: dict[str, list[Match]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ vecteurs
    def _encode_all(self, encoder, vectors) -> np.ndarray:
        from ..search.neural import VectorCache, text_hash

        cache = vectors if vectors is not None else VectorCache(None)
        keys = [text_hash("q:" + e.text) for e in self.entries]
        missing = cache.missing(keys)
        if missing:
            todo = {text_hash("q:" + e.text): e.text for e in self.entries}
            cache.put(missing, encoder.encode([todo[k] for k in missing], "query", batch=64))  # « query: » des deux côtés : symétrique
            cache.save(set(keys))
        return cache.matrix(keys).astype(np.float32)

    @lru_cache(maxsize=4096)
    def concept(self, text: str) -> tuple[str, float] | None:
        if self._concept_of is None:
            return None
        try:
            return self._concept_of(text)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------ rappel
    def candidates(self, question: str, k: int = 24, exclude: int | None = None, qvec: np.ndarray | None = None) -> list[tuple[int, int, float]]:
        """(entrée, rang, score BM25) : fusion par rangs des trois voies."""
        vec, seq = query_vector(question)
        if seq:
            extra, _, _ = expand(seq)
            for t, w in extra.items():
                vec[t] = max(vec.get(t, 0.0), w)
        lists = []
        bm = self.bm25.score(vec, 60) if vec else []
        lists.append((1.0, [h.index for h in bm]))
        if self.ngrams is not None:
            lists.append((0.5, [h.index for h in self.ngrams.score(question, 40)]))
        if self.matrix is not None and (qvec is not None or self.encoder is not None):
            qv = qvec if qvec is not None else self.encoder.encode([question], "query")[0]
            sims = self.matrix @ qv
            top = np.argpartition(-sims, min(60, len(sims) - 1))[:60]
            lists.append((1.2, [int(i) for i in top[np.argsort(-sims[top])]]))
        rrf: dict[int, float] = defaultdict(float)
        for w, ids in lists:
            for r, i in enumerate(ids):
                rrf[i] += w / (60 + r)
        exact = self.by_key.get(key(question))
        if exact is not None:
            rrf[exact] += 1.0
        bm_score = {h.index: h.score for h in bm}
        ranked = [i for i, _ in sorted(rrf.items(), key=lambda kv: -kv[1]) if i != exclude][:k]
        return [(i, r, bm_score.get(i, 0.0)) for r, i in enumerate(ranked)]

    # ------------------------------------------------------------------ critères
    def _coverage(self, a: set[str], b: set[str]) -> float:
        if not a:
            return 0.0
        w = {t: self.bm25.idf.get(t, self.top_idf) for t in a}
        return sum(v for t, v in w.items() if t in b) / (sum(w.values()) or 1.0)

    def features(self, question: str, cands: list[tuple[int, int, float]], qvec=None, precise: bool = False) -> np.ndarray:
        qk, qt = key(question), set(terms(question))
        q_nums, q_isin = numbers(question), set(ISIN.findall(question))
        q_neg, q_yes = bool(NEG & set(fold(question).split())), bool(YESNO.match(key(question)))
        q_con = self.concept(question)
        top_bm = max((s for _, _, s in cands), default=0.0) or 1.0
        texts = [self.entries[i].text for i, _, _ in cands]
        dense = (self.matrix[[i for i, _, _ in cands]] @ qvec) if (self.matrix is not None and qvec is not None and cands) else None
        rer = None
        if self.reranker is not None and texts:  # relecture croisée des 10 premiers seulement (même règle partout)
            head = [j for j, (_, rank, _) in enumerate(cands) if rank < RERANK_TOP]
            scores = self.reranker.score(question, [texts[j] for j in head]) if head else []
            rer = np.full(len(texts), np.nan)
            rer[head] = scores
        d2 = r2 = None
        if precise and texts:
            if self.precise_encoder is not None:
                vs = self.precise_encoder.encode([question] + texts, "query")
                d2 = vs[1:] @ vs[0]
            if self.precise_reranker is not None:
                r2 = self.precise_reranker.score(question, texts)
        rows = []
        for j, (i, rank, bm) in enumerate(cands):
            e, ct = self.entries[i], self.terms[i]
            c_nums, c_isin = numbers(e.text), set(ISIN.findall(e.text))
            c_con = self.concept(e.text)
            if q_con and c_con:
                concept = 1.0 if q_con[0] == c_con[0] else -1.0
                conf = min(q_con[1], c_con[1])
            else:
                concept, conf = 0.0, 0.0
            num_conflict = 0.0 if q_nums == c_nums else (1.0 if q_nums and c_nums else 0.5)
            isin = 0.0 if q_isin == c_isin else (1.0 if q_isin and c_isin else 0.5)
            row = [float(qk == e.key), bm / top_bm, self._coverage(qt, ct), self._coverage(ct, qt), similarity(question, e.text),
                   float(dense[j]) if dense is not None else math.nan, float(rer[j]) if rer is not None else math.nan,
                   concept, conf, num_conflict, isin, float(q_neg != bool(NEG & set(fold(e.text).split()))),
                   float(q_yes != bool(YESNO.match(e.key))), min(len(qt), len(ct)) / max(1, len(qt), len(ct)), 1 / (1 + rank)]
            if precise:
                row += [float(d2[j]) if d2 is not None else math.nan, float(r2[j]) if r2 is not None else math.nan]
            rows.append(row)
        return np.array(rows, dtype=np.float64).reshape(len(rows), len(PRECISE if precise else FAST))

    # ------------------------------------------------------------------ probabilité
    def prior(self, X: np.ndarray) -> np.ndarray:
        """Avant tout apprentissage (aucun ancien RFI rattaché) : règle prudente, jamais présentée comme calibrée."""
        dense = np.where(np.isnan(X[:, 5]), X[:, 4], X[:, 5])
        z = -7 + 3.5 * X[:, 2] + 3.5 * X[:, 3] + 4 * dense + 1.5 * X[:, 7] - 2.5 * X[:, 9] - 1.5 * X[:, 11] - 1 * X[:, 12] + 8 * X[:, 0]
        return 1 / (1 + np.exp(-z))

    @staticmethod
    def evidence(X: np.ndarray) -> np.ndarray:
        """Preuve directe : même texte, mots importants communs, n-grammes proches, sens très proche ou même concept."""
        dense = np.nan_to_num(X[:, 5], nan=-1.0)
        return (X[:, 0] == 1) | (np.minimum(X[:, 2], X[:, 3]) >= 0.5) | (X[:, 4] >= 0.6) | (dense >= 0.88) | (X[:, 7] == 1)

    def _guard(self, X: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Sans modèle appris (règle prudente) : sans preuve directe, probabilité plafonnée. Modèle appris : la
        calibration est faite séparément avec / sans preuve directe, donc déjà juste dans les deux cas."""
        if self.fast_model is not None:
            return p
        return np.where(self.evidence(X), p, np.minimum(p, EVIDENCE_CAP))

    def match(self, question: str, k: int = 8, min_p: float = 0.05, precise: bool | None = None) -> list[Match]:
        """Questions passées les plus probablement identiques, probabilité calibrée, avec leurs raisons."""
        q = " ".join((question or "").split())
        ck = f"{q}|{k}|{precise}"
        with self._lock:
            if ck in self._cache:
                return self._cache[ck]
        if not q or not self.entries:
            return []
        qvec = self.encoder.encode([q], "query")[0] if (self.matrix is not None and self.encoder is not None) else None
        cands = self.candidates(q, qvec=qvec)
        if not cands:
            return []
        X = self.features(q, cands, qvec)
        p = self.fast_model.predict(X, self.evidence(X)) if self.fast_model is not None else self._guard(X, self.prior(X))
        out = [Match(self.entries[i], float(p[j]), dict(zip(FAST, X[j]))) for j, (i, _, _) in enumerate(cands)]
        want = (self.precise_model is not None) if precise is None else (precise and self.precise_model is not None)
        unsure = [j for j, m in enumerate(out) if 0.1 < m.p < 0.9][:8]
        if want and unsure:  # cascade : seuls les cas douteux passent par les modèles lents
            sub = [cands[j] for j in unsure]
            Xp = self.features(q, sub, qvec, precise=True)
            pp = self.precise_model.predict(Xp, self.evidence(Xp))
            for n, j in enumerate(unsure):
                out[j] = Match(out[j].entry, float(pp[n]), dict(zip(PRECISE, Xp[n])), precise=True)
        out = sorted((m for m in out if m.p >= min_p), key=lambda m: -m.p)[:k]
        with self._lock:
            if len(self._cache) > 5000:
                self._cache.clear()
            self._cache[ck] = out
        return out

    def content_votes(self, question: str, k: int = 8) -> list[tuple[int, float, int, str]]:
        """Textes Qvidian choisis pour cette question : (contenu, probabilité, nb de RFI, question passée la plus proche).
        Probabilité combinée par « OU bruité » sur les questions passées (deux questions à 70 % → 91 %), récence comprise."""
        acc: dict[int, list[float]] = defaultdict(list)
        best: dict[int, tuple[float, str]] = {}
        files: dict[int, set[str]] = defaultdict(set)
        for m in self.match(question, k=12, min_p=0.2):
            # Les occurrences d'une même question passée ne sont pas des preuves indépendantes : la question passée vote
            # une fois, pour chaque texte, avec la part (récente) de ses réponses qui ont utilisé ce texte.
            share: dict[int, float] = defaultdict(float)
            total = 0.0
            for o in m.entry.occ:
                if o.content_id is None:
                    continue
                w = (0.5 + 0.5 * _recency(o.date, self.today)) if o.file else 0.5
                share[o.content_id] += w
                total += w
                if o.file:
                    files[o.content_id].add(o.file)
            for cid, w in share.items():
                acc[cid].append(m.p * w / total)
                if m.p > best.get(cid, (0.0, ""))[0]:
                    best[cid] = (m.p, m.entry.text)
        out = [(cid, 1 - float(np.prod([1 - min(0.999, w) for w in ws])), len(files[cid]), best[cid][1]) for cid, ws in acc.items()]
        return sorted(out, key=lambda t: (-t[1], -t[2]))[:k]

    # ------------------------------------------------------------------ apprentissage sur les anciens RFI
    def training_pairs(self, content_text: Callable[[int], str] | None = None, limit: int = 4000, k: int = 10):
        """Couples (question passée, candidat) étiquetés par ce que l'équipe a répondu ; les cas ambigus sont écartés."""
        rng = np.random.default_rng(11)
        order = rng.permutation(len(self.entries))
        X, Xp, y, groups = [], [], [], []
        fam: dict[tuple[int, int], bool] = {}

        def same_family(a: int, b: int) -> bool:
            if content_text is None:
                return False
            kk = (min(a, b), max(a, b))
            if kk not in fam:
                fam[kk] = similarity(content_text(a), content_text(b)) >= 0.55  # versions d'un même texte (seuil de history.py)
            return fam[kk]

        for i in order[:limit]:
            e = self.entries[i]
            qvec = None
            if self.matrix is not None:
                qvec = self.matrix[i]
            cands = self.candidates(e.text, k=k, exclude=int(i), qvec=qvec)
            labels = []
            for c, _, _ in cands:
                labels.append(self._label(e, self.entries[c], same_family))
            keep = [j for j, lab in enumerate(labels) if lab is not None]
            if not keep:
                continue
            sub = [cands[j] for j in keep]
            X.append(self.features(e.text, sub, qvec))
            if self.precise_encoder is not None or self.precise_reranker is not None:
                Xp.append(self.features(e.text, sub, qvec, precise=True))
            y += [labels[j] for j in keep]
            g = min(e.files) if e.files else f"q{i}"
            groups += [g] * len(keep)
        if not y:
            return None
        return (np.vstack(X), np.vstack(Xp) if Xp else None, np.array(y, dtype=np.float64), np.array(groups))

    def _label(self, a: Entry, b: Entry, same_family: Callable[[int, int], bool]) -> float | None:
        pos = neg = False
        ca, cb = a.contents, b.contents
        fa, fb = {o.fund for o in a.occ if o.fund}, {o.fund for o in b.occ if o.fund}
        other_funds = bool(fa and fb and not fa & fb)  # même question pour deux fonds : textes différents, question identique
        if ca and cb:
            if ca & cb:
                pos = True
            elif not other_funds and not any(same_family(x, y) for x in ca for y in cb):
                neg = True
        la = [o.answer for o in a.occ if len(o.answer or "") >= LONG][:4]
        lb = [o.answer for o in b.occ if len(o.answer or "") >= LONG][:4]
        con_a, con_b = self.concept(a.text), self.concept(b.text)
        same_period = numbers(a.text) == numbers(b.text)  # même concept mais « 1 an » / « 3 ans » : pas la même question
        same_concept = bool(con_a and con_b and con_a[0] == con_b[0] and min(con_a[1], con_b[1]) >= 0.7 and same_period)
        other_concept = bool(con_a and con_b and con_a[0] != con_b[0] and min(con_a[1], con_b[1]) >= 0.7)
        if la and lb:
            best = max(similarity(x, y) for x in la for y in lb)
            if best >= 0.92:
                pos = True
            elif best < 0.25 and not same_concept:
                neg = True
        if same_concept:
            pos = True
        if other_concept or (not same_period and numbers(a.text) and numbers(b.text)):
            neg = True
        if pos == neg:
            return None  # rien de sûr, ou signaux contraires : jamais appris
        return 1.0 if pos else 0.0

    def train(self, content_text: Callable[[int], str] | None = None, target: float = 0.95) -> dict[str, Any]:
        data = self.training_pairs(content_text)
        if data is None:
            return {"trained": False, "reason": "aucune question passée rattachée à une réponse"}
        X, Xp, y, groups = data
        if y.sum() < MIN_EXAMPLES or len(y) - y.sum() < MIN_EXAMPLES:  # trop peu pour apprendre sans se tromper avec aplomb
            return {"trained": False, "reason": f"trop peu d'exemples ({int(y.sum())} identiques, {int(len(y) - y.sum())} différentes)",
                    "pairs": int(len(y))}
        self.fast_model = CalibratedModel(FAST).fit(X, y, groups, target=target, strata=self.evidence(X))
        out = {"trained": True, "fast": self.fast_model.report}
        if Xp is not None:
            self.precise_model = CalibratedModel(PRECISE).fit(Xp, y, groups, target=target, strata=self.evidence(Xp))
            out["precise"] = self.precise_model.report
        with self._lock:
            self._cache.clear()
        return out

    def stats(self) -> dict[str, Any]:
        return {"questions": sum(len(e.occ) for e in self.entries), "distinct": len(self.entries),
                "files": len({f for e in self.entries for f in e.files}), "dense": self.matrix is not None,
                "reranker": self.reranker is not None, "precise": self.precise_model is not None,
                "calibrated": self.fast_model is not None, "build_seconds": self.build_seconds,
                "report": self.fast_model.report if self.fast_model else None,
                "precise_report": self.precise_model.report if self.precise_model else None}

    def __getstate__(self):
        state = self.__dict__.copy()
        for k in ("encoder", "reranker", "precise_encoder", "precise_reranker", "_concept_of", "_lock", "_cache"):
            state[k] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock, self._cache = threading.Lock(), {}


__all__ = ["QuestionMatcher", "Match", "Entry", "Occurrence", "build_bank", "key", "FAST", "PRECISE"]
