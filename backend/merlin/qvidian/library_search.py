"""Recherche sémantique dans la bibliothèque Qvidian (instantané local) : le moteur hybride de merlin.search, plus ce
qui compte pour une réponse de RFP.

Score final = pertinence (lexical + sémantique + reranker) × (1 + 0,18 × popularité + 0,08 × récence d'usage)
              + accord de portée (société / stratégie / fonds / part, même fonds) + qualité (expiré, désactivé, défauts).
La popularité (TimesUsedCount, échelle logarithmique) et la récence départagent des réponses également pertinentes ;
elles ne font jamais remonter une réponse hors sujet. Un texte propre à un autre fonds que celui de la question est
nettement repoussé. Les versions d'un même texte sont regroupées (une famille = un résultat, variantes listées).
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..rfi.aggregate import recency, similarity, to_date
from ..search import neural
from ..search.engine import Doc, HybridIndex
from ..search.text import snippet
from .audit import audit
from .levels import SCOPE_LABELS, THEME_LABELS, FundNames, Level, classify, fund_folders, query_level
from .snapshot import Snapshot

POPULARITY, RECENCY = 0.18, 0.08
READY: dict[str, "LibrarySearch"] = {}  # moteur prêt par instantané (chemin) : lu par suggest.py sans jamais rien construire
FAMILY_SIMILARITY = 0.55
SORTS = {"pertinence", "utilisations", "recent", "modifie"}


@dataclass
class Filters:
    scope: list[str] | None = None
    theme: list[str] | None = None
    fund: list[str] | None = None
    folder: str | None = None
    language: str | None = None
    min_uses: int = 0
    include_disabled: bool = False
    include_expired: bool = True
    only_issues: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Filters":
        d = d or {}
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys and v not in (None, "", [])})


def _lang(c: dict[str, Any]) -> str:
    raw = f"{c.get('language') or ''} {c.get('lcid') or ''}".lower()
    if "1033" in raw or "2057" in raw or "english" in raw or "anglais" in raw:
        return "en"
    if "1036" in raw or "fran" in raw:
        return "fr"
    return "fr"


def _expired(c: dict[str, Any], today: date) -> bool:
    exp = to_date(c.get("expires"))
    return bool(c.get("expired")) or (exp is not None and exp < today)


class LibrarySearch:
    def __init__(self, snapshot: Snapshot, models_root: Path | None = None, extra_funds: list[str] | None = None,
                 encoder: neural.Encoder | None = None, reranker: neural.Reranker | None = None,
                 today: date | None = None, half_life: int = 365, progress=None):
        started = time.time()
        self.today = today or date.today()
        self.half_life = half_life
        self.rows = [c for c in snapshot.all()]
        self.by_id = {c["id"]: i for i, c in enumerate(self.rows)}
        paths = [c.get("folder_path") or "" for c in self.rows] + [f.get("path") or "" for f in snapshot.folders()]
        self.funds = FundNames(fund_folders(paths) + list(extra_funds or []))
        self.levels: list[Level] = [classify(c["title"], c.get("text") or "", c.get("folder_path") or "", self.funds, c.get("question") or "")
                                    for c in self.rows]
        report = audit(self.rows, today=self.today)
        self.issues = {it["id"]: it["issues"] for it in report["items"]}
        self.max_uses = max((c.get("times_used") or 0 for c in self.rows), default=0)
        docs = [Doc(c["id"], c["title"] or "", c.get("question") or "", c.get("text") or "",
                    f"{c.get('learned_terms') or ''} {c.get('assigned_terms') or ''}", c.get("folder_path") or "") for c in self.rows]
        vectors = neural.VectorCache(snapshot.path.with_name(f"{snapshot.path.stem}.{encoder.id}.vectors.npz")) if encoder is not None else None
        self.index = HybridIndex(docs, encoder, reranker, vectors, progress)
        self.engine = {"lexical": True, "encoder": encoder.id if encoder else None, "reranker": reranker.id if reranker else None,
                       "documents": len(self.rows), "build_seconds": round(time.time() - started, 2), "funds": self.funds.names}

    # ------------------------------------------------------------------ filtres
    def _allowed(self, f: Filters):
        def ok(i: int) -> bool:
            c, lv = self.rows[i], self.levels[i]
            if not f.include_disabled and not c.get("enabled", True):
                return False
            if not f.include_expired and _expired(c, self.today):
                return False
            if f.scope and lv.scope not in f.scope:
                return False
            if f.theme and not (set(f.theme) & set(lv.themes)):
                return False
            if f.fund and not (set(f.fund) & set(lv.funds)):
                return False
            if f.folder and not (c.get("folder_path") or "").startswith(f.folder):
                return False
            if f.language and _lang(c) != f.language:
                return False
            if f.min_uses and (c.get("times_used") or 0) < f.min_uses:
                return False
            if f.only_issues and not self.issues.get(c["id"]):
                return False
            return True
        return ok

    # ------------------------------------------------------------------ score métier
    def _business(self, i: int, ql: Level, qlang: str) -> tuple[float, float, list[str]]:
        """(multiplicateur, ajustement, raisons)."""
        c, lv = self.rows[i], self.levels[i]
        uses = c.get("times_used") or 0
        pop = math.log1p(uses) / math.log1p(self.max_uses) if self.max_uses else 0.0
        when = to_date(c.get("last_used")) or to_date(c.get("modified"))
        rec = recency(when, self.today, self.half_life)
        why: list[str] = []
        if uses:
            why.append(f"utilisé {uses} fois" + (f", dernièrement le {when.strftime('%d/%m/%Y')}" if to_date(c.get("last_used")) else ""))
        adj = 0.0
        if ql.funds:
            if set(ql.funds) & set(lv.funds):
                adj += 0.12
                why.append(f"même fonds ({', '.join(sorted(set(ql.funds) & set(lv.funds)))})")
            elif lv.funds:
                adj -= 0.28
                why.append(f"texte propre à un autre fonds ({', '.join(lv.funds)})")
            elif lv.scope == "societe":
                adj -= 0.03
        elif lv.funds and ql.scope in {"societe", "generique", "strategie"}:
            adj -= 0.06 if ql.scope != "generique" else 0.03  # question générale : la réponse d'un seul fonds convient moins
        if ql.scope != "generique" and ql.confidence >= 0.15 and ql.scope == lv.scope:
            adj += 0.05
            why.append(f"même niveau ({SCOPE_LABELS[lv.scope].lower()})")
        if ql.scope == "societe" and lv.scope in {"fonds", "part"}:
            adj -= 0.06
        if ql.scope == "part" and lv.scope == "part":
            adj += 0.04
        lang = _lang(c)
        if qlang == "en":
            adj += 0.04 if lang == "en" else -0.01
        elif lang == "en":
            adj -= 0.03
        if not c.get("enabled", True):
            adj -= 0.5
            why.append("désactivé")
        if _expired(c, self.today):
            adj -= 0.22
            why.append("expiré")
        issues = self.issues.get(c["id"], [])
        serious = [x for x in issues if x["severity"] == "haute"]
        if serious:
            adj -= min(0.3, 0.12 * len(serious))
            why.append(f"à corriger : {serious[0]['label'].lower()}")
        if not (c.get("text") or "").strip():
            adj -= 0.6
        return 1 + POPULARITY * pop + RECENCY * rec, adj, why

    # ------------------------------------------------------------------ recherche
    def search(self, query: str, filters: dict[str, Any] | None = None, sort: str = "pertinence", k: int = 20,
               rerank: bool = True) -> dict[str, Any]:
        f = Filters.from_dict(filters)
        allowed = self._allowed(f)
        sort = sort if sort in SORTS else "pertinence"
        if not query.strip():
            return self._browse(f, allowed, sort, k)
        q, cands = self.index.search(query, k=max(80, k * 4), allowed=allowed, rerank=rerank)
        ql = query_level(q.pivot, self.funds)
        scored = []
        for c in cands:
            mult, adj, why = self._business(c.index, ql, q.language)
            final = c.relevance * mult + adj
            scored.append((final, c, why))
        scored.sort(key=lambda t: -t[0])
        top = scored[0][0] if scored else 1.0
        scored = [s for s in scored if s[0] >= max(0.12, 0.25 * top)]
        if sort != "pertinence":
            key = {"utilisations": lambda t: (self.rows[t[1].index].get("times_used") or 0),
                   "recent": lambda t: str(self.rows[t[1].index].get("last_used") or ""),
                   "modifie": lambda t: str(self.rows[t[1].index].get("modified") or "")}[sort]
            scored = [s for s in scored if s[0] >= 0.5 * top]
            scored.sort(key=key, reverse=True)
        query_terms = set(q.vector) | set(q.seq)
        results = self._families([(s, c.index, c, why) for s, c, why in scored], query_terms, k)
        return {"query": query, "language": q.language, "pivot": q.pivot if q.pivot != query else None, "expansions": q.expansions,
                "level": ql.public(), "results": results, "total": len(scored), "timings": q.timings, "engine": self.engine,
                "facets": self._facets([c.index for _, c, _ in scored]), "sort": sort}

    def _browse(self, f: Filters, allowed, sort: str, k: int) -> dict[str, Any]:
        idx = [i for i in range(len(self.rows)) if allowed(i)]
        key = {"utilisations": lambda i: self.rows[i].get("times_used") or 0, "recent": lambda i: str(self.rows[i].get("last_used") or ""),
               "modifie": lambda i: str(self.rows[i].get("modified") or ""), "pertinence": lambda i: self.rows[i].get("times_used") or 0}[sort]
        idx.sort(key=key, reverse=True)
        items = []
        for i in idx:
            mult, adj, why = self._business(i, Level(), "fr")
            items.append((0.0, i, None, why))
        return {"query": "", "language": None, "pivot": None, "expansions": [], "level": Level().public(),
                "results": self._families(items, set(), k), "total": len(idx), "timings": {}, "engine": self.engine,
                "facets": self._facets(idx), "sort": sort}

    def _families(self, ranked: list[tuple[float, int, Any, list[str]]], query_terms: set[str], k: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        heads: list[tuple[int, dict[str, Any]]] = []
        top = ranked[0][0] if ranked and ranked[0][0] > 0 else 1.0
        for final, i, cand, why in ranked:
            c = self.rows[i]
            text = c.get("text") or ""
            family = next((h for j, h in heads if (self.rows[j]["title"] or "").strip().lower() == (c["title"] or "").strip().lower()
                           and similarity(self.rows[j].get("text") or "", text) >= FAMILY_SIMILARITY
                           or similarity(self.rows[j].get("text") or "", text) >= 0.8), None)
            if family is not None:
                family["variants"].append({"id": c["id"], "title": c["title"], "times_used": c.get("times_used") or 0,
                                           "last_used": c.get("last_used"), "modified": c.get("modified"), "expired": _expired(c, self.today)})
                continue
            if len(out) >= k:
                continue
            snip, spans = snippet(text, query_terms)
            item = {
                "id": c["id"], "title": c["title"], "question": c.get("question") or "", "folder_path": c.get("folder_path") or "",
                "snippet": snip, "highlights": spans, "text": text, "score": round(100 * max(final, 0.0) / (max(final, 0.0) + 0.3)) if cand else None,
                "relative": round(final / top, 3) if cand else None, "times_used": c.get("times_used") or 0,
                "last_used": c.get("last_used"), "modified": c.get("modified"), "enabled": c.get("enabled", True),
                "expired": _expired(c, self.today), "language": _lang(c), "type": c.get("type") or "",
                "level": self.levels[i].public(), "issues": self.issues.get(c["id"], []), "why": why, "variants": [],
            }
            if cand is not None:
                item["signals"] = {
                    "lexical": round(cand.scores.get("bm25", 0.0), 3), "semantic": round(cand.scores.get("dense", 0.0), 3) if "dense" in cand.scores else None,
                    "rerank": round(cand.rerank, 3) if cand.rerank is not None else None, "coverage": round(cand.coverage, 2),
                    "ranks": cand.ranks, "phrase": cand.phrase, "matched": sorted(cand.matched)[:12],
                }
                if cand.phrase:
                    item["why"] = ["expression exacte de la question"] + item["why"]
                if cand.rerank is not None and cand.rerank >= 0.5:
                    item["why"] = [f"lecture fine : répond à la question ({round(cand.rerank * 100)} %)"] + item["why"]
                elif "dense" in cand.ranks and cand.ranks["dense"] <= 3 and "bm25" not in cand.ranks:
                    item["why"] = ["même sens, d'autres mots"] + item["why"]
            heads.append((i, item))
            out.append(item)
        return out

    def _facets(self, idx: list[int]) -> dict[str, list[dict[str, Any]]]:
        def count(values) -> list[dict[str, Any]]:
            acc: dict[str, int] = {}
            for v in values:
                acc[v] = acc.get(v, 0) + 1
            return [{"value": k, "count": n} for k, n in sorted(acc.items(), key=lambda kv: -kv[1])]

        scope = count(self.levels[i].scope for i in idx)
        for s in scope:
            s["label"] = SCOPE_LABELS.get(s["value"], s["value"])
        theme = count(t for i in idx for t in self.levels[i].themes)
        for t in theme:
            t["label"] = THEME_LABELS.get(t["value"], t["value"])
        return {"scope": scope, "theme": theme, "fund": count(fd for i in idx for fd in self.levels[i].funds),
                "folder": count(((self.rows[i].get("folder_path") or "(racine)").split(" / ")[0]) for i in idx)[:12],
                "language": count(_lang(self.rows[i]) for i in idx)}

    # ------------------------------------------------------------------ contenu
    def describe(self, content_id: int, k: int = 6) -> dict[str, Any] | None:
        i = self.by_id.get(content_id)
        if i is None:
            return None
        similar = []
        for j, s in self.index.similar(i, k):
            c = self.rows[j]
            similar.append({"id": c["id"], "title": c["title"], "folder_path": c.get("folder_path") or "", "score": round(s, 3),
                            "times_used": c.get("times_used") or 0, "level": self.levels[j].public(),
                            "same_text": similarity(self.rows[i].get("text") or "", c.get("text") or "") >= FAMILY_SIMILARITY})
        return {"level": self.levels[i].public(), "issues": self.issues.get(content_id, []), "similar": similar,
                "popularity": round(math.log1p(self.rows[i].get("times_used") or 0) / math.log1p(self.max_uses), 3) if self.max_uses else 0.0}

    def overview(self) -> dict[str, Any]:
        idx = list(range(len(self.rows)))
        used = sorted(idx, key=lambda i: -(self.rows[i].get("times_used") or 0))
        return {"facets": self._facets(idx), "engine": self.engine,
                "top_used": [{"id": self.rows[i]["id"], "title": self.rows[i]["title"], "times_used": self.rows[i].get("times_used") or 0,
                              "level": self.levels[i].public()} for i in used[:8]],
                "never_used": sum(1 for c in self.rows if not c.get("times_used")),
                "uses_total": sum(c.get("times_used") or 0 for c in self.rows)}


class SearchManager:
    """Un moteur par instantané, reconstruit en arrière-plan quand l'instantané change ; le précédent sert en attendant."""

    def __init__(self, models_root: Path, encoder_id: str = neural.DEFAULT_ENCODER, use_reranker: bool = True, half_life: int = 365):
        self.models_root = models_root
        self.encoder_id = encoder_id
        self.use_reranker = use_reranker
        self.half_life = half_life
        self._engines: dict[str, tuple[tuple, LibrarySearch]] = {}
        self._building: dict[str, dict[str, Any]] = {}
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.downloads = neural.Downloads(models_root)
        self.extra_funds: list[str] = []

    # ------------------------------------------------------------------ modèles
    def _encoder(self):
        if not neural.available():
            return None
        for mid in [self.encoder_id] + [m for m, s in neural.MODELS.items() if s.kind == "encoder" and m != self.encoder_id]:
            if neural.installed(self.models_root, mid):
                if mid not in self._models:
                    try:
                        self._models[mid] = neural.Encoder(self.models_root, mid)
                    except Exception as error:  # noqa: BLE001 - modèle abîmé : on reste en lexical
                        self._models[mid] = None
                        self._models[f"{mid}:error"] = str(error)[:200]
                return self._models[mid]
        return None

    def _reranker(self):
        mid = neural.DEFAULT_RERANKER
        if not self.use_reranker or not neural.available() or not neural.installed(self.models_root, mid):
            return None
        if mid not in self._models:
            try:
                self._models[mid] = neural.Reranker(self.models_root, mid)
            except Exception as error:  # noqa: BLE001
                self._models[mid] = None
                self._models[f"{mid}:error"] = str(error)[:200]
        return self._models[mid]

    def models(self) -> list[dict[str, Any]]:
        out = []
        for mid, spec in neural.MODELS.items():
            state = self.downloads.state.get(mid, {})
            out.append({"id": mid, "kind": spec.kind, "label": spec.label, "size_mb": spec.size_mb, "license": spec.license,
                        "note": spec.note, "installed": neural.installed(self.models_root, mid), "active": bool(self._models.get(mid)),
                        "error": self._models.get(f"{mid}:error"), "download": state or None})
        return out

    # ------------------------------------------------------------------ moteurs
    @staticmethod
    def signature(snapshot: Snapshot) -> tuple:
        meta = snapshot.meta()
        return (str(snapshot.path), meta.get("synced_at"), meta.get("count"), meta.get("updated_at"))

    def get(self, snapshot: Snapshot, wait: bool = True) -> LibrarySearch:
        key = str(snapshot.path)
        sig = self.signature(snapshot) + (self._model_signature(),)
        current = self._engines.get(key)
        if current and current[0] == sig:
            return current[1]
        building = self._building.get(key)
        if current and building and building.get("running"):
            return current[1]  # un index plus complet se construit déjà
        if current and not wait:
            self._start_build(snapshot, sig)
            return current[1]
        # premier moteur : lexical tout de suite (quelques secondes au pire), sémantique en arrière-plan
        if not current:
            # Rien n'attend le chargement des modèles (quelques secondes) : index lexical immédiat, modèles en arrière-plan
            with self._lock:
                current = self._engines.get(key)
                if current:
                    return current[1]
                engine = LibrarySearch(snapshot, extra_funds=self.extra_funds, half_life=self.half_life)
                lexical_sig = self.signature(snapshot) + (("lexical",),)
                self._engines[key] = (lexical_sig, engine)
                READY[key] = engine
            if neural.available() and any(neural.installed(self.models_root, m) for m in neural.MODELS):
                self._start_build(snapshot, sig)
            else:
                self._engines[key] = (sig, engine)
            return engine
        self._start_build(snapshot, sig)
        return current[1]

    def _model_signature(self) -> tuple:
        """Modèles installés (sans les charger : la signature ne doit jamais faire attendre une requête)."""
        if not neural.available():
            return (None, None)
        enc = next((m for m in [self.encoder_id] + list(neural.MODELS) if neural.MODELS.get(m) and neural.MODELS[m].kind == "encoder"
                    and neural.installed(self.models_root, m) and self._models.get(m, True) is not None), None)
        rr = neural.DEFAULT_RERANKER if self.use_reranker and neural.installed(self.models_root, neural.DEFAULT_RERANKER) \
            and self._models.get(neural.DEFAULT_RERANKER, True) is not None else None
        return (enc, rr)

    def _start_build(self, snapshot: Snapshot, sig: tuple) -> None:
        key = str(snapshot.path)
        with self._lock:
            state = self._building.get(key)
            if state and (state.get("running") or (state.get("error") and state.get("sig") == sig)):
                return  # déjà en cours, ou déjà échoué pour ces mêmes données : l'index lexical reste servi
            self._building[key] = {"running": True, "message": "Préparation", "done": 0, "total": 0, "started": time.time(), "sig": sig}

        def progress(message: str, done: int, total: int) -> None:
            self._building[key].update(message=message, done=done, total=total)

        def run() -> None:
            try:
                engine = LibrarySearch(snapshot, extra_funds=self.extra_funds, half_life=self.half_life,
                                       encoder=self._encoder(), reranker=self._reranker(), progress=progress)
                self._engines[key] = (sig, engine)
                READY[key] = engine
                self._building[key].update(running=False, message="Prêt", seconds=round(time.time() - self._building[key]["started"], 1))
            except Exception as error:  # noqa: BLE001 - l'index lexical reste utilisable
                self._building[key].update(running=False, error=str(error)[:300])

        threading.Thread(target=run, name="qvidian-index", daemon=True).start()

    def status(self, snapshot: Snapshot) -> dict[str, Any]:
        key = str(snapshot.path)
        current = self._engines.get(key)
        building = {k: v for k, v in (self._building.get(key) or {}).items() if k != "sig"} or None
        return {"ready": current is not None, "engine": current[1].engine if current else None,
                "building": building, "neural_runtime": neural.available(), "models": self.models()}

    def reset_models(self) -> None:
        self._models.clear()


__all__ = ["LibrarySearch", "SearchManager", "Filters", "READY"]
