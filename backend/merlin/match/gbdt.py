"""Classifieur calibré « même question ? », en numpy seul (aucune dépendance lourde, quelques secondes d'entraînement).

1. **Gradient boosting** d'arbres de décision (Newton, perte logistique, histogrammes par quantiles, régularisation L2,
   feuilles minimales, arrêt précoce sur une validation) : capte les interactions (« sens très proche MAIS nombres
   différents » = autre question : « performance 1 an » ≠ « performance 3 ans »).
2. **Calibration isotonique** (PAV) sur des prédictions hors échantillon (validation croisée par groupes : un même
   questionnaire n'est jamais à la fois appris et mesuré) : « 90 % » veut dire « 9 fois sur 10 c'était la même question ».
   Repli Platt si trop peu d'exemples.
3. **Seuil à risque contrôlé** : le plus petit seuil dont la borne basse (Wilson, 95 %) de la précision mesurée reste
   au-dessus de la cible (95 % par défaut). Au-dessus : « même question » ; en dessous : proposé, jamais affirmé.
Valeurs manquantes (modèle non installé) : NaN, branche apprise par l'arbre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MISSING = -9.0


def _prep(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    return np.where(np.isnan(X), MISSING, X)


@dataclass
class Tree:
    feature: list[int] = field(default_factory=list)
    threshold: list[float] = field(default_factory=list)
    left: list[int] = field(default_factory=list)
    right: list[int] = field(default_factory=list)
    value: list[float] = field(default_factory=list)

    def predict(self, X: np.ndarray) -> np.ndarray:
        node = np.zeros(len(X), dtype=np.int64)
        for _ in range(16):
            f = np.array(self.feature)[node]
            leaf = f < 0
            if leaf.all():
                break
            th = np.array(self.threshold)[node]
            go_left = X[np.arange(len(X)), np.maximum(f, 0)] <= th
            nxt = np.where(go_left, np.array(self.left)[node], np.array(self.right)[node])
            node = np.where(leaf, node, nxt)
        return np.array(self.value)[node]


class GBDT:
    def __init__(self, n_trees: int = 200, depth: int = 3, lr: float = 0.08, min_leaf: int = 12, l2: float = 2.0, bins: int = 32):
        self.n_trees, self.depth, self.lr, self.min_leaf, self.l2, self.bins = n_trees, depth, lr, min_leaf, l2, bins
        self.trees: list[Tree] = []
        self.base = 0.0

    def _cuts(self, X: np.ndarray) -> list[np.ndarray]:
        cuts = []
        for j in range(X.shape[1]):
            col = X[:, j]
            q = np.unique(np.quantile(col, np.linspace(0, 1, self.bins + 1)[1:-1]))
            cuts.append(q)
        return cuts

    def _grow(self, X, g, h, idx, cuts, depth, tree) -> int:
        node = len(tree.value)
        G, H = g[idx].sum(), h[idx].sum()
        tree.feature.append(-1); tree.threshold.append(0.0); tree.left.append(-1); tree.right.append(-1)  # noqa: E702
        tree.value.append(float(-G / (H + self.l2)))
        if depth == 0 or len(idx) < 2 * self.min_leaf:
            return node
        parent = G * G / (H + self.l2)
        best = (0.0, -1, 0.0)
        for j, cj in enumerate(cuts):
            if not len(cj):
                continue
            col = X[idx, j]
            pos = np.searchsorted(cj, col, side="left")
            gs = np.bincount(pos, weights=g[idx], minlength=len(cj) + 1).cumsum()[:-1]
            hs = np.bincount(pos, weights=h[idx], minlength=len(cj) + 1).cumsum()[:-1]
            ns = np.bincount(pos, minlength=len(cj) + 1).cumsum()[:-1]
            ok = (ns >= self.min_leaf) & (len(idx) - ns >= self.min_leaf)
            if not ok.any():
                continue
            gain = gs ** 2 / (hs + self.l2) + (G - gs) ** 2 / (H - hs + self.l2) - parent
            gain = np.where(ok, gain, -np.inf)
            k = int(np.argmax(gain))
            if gain[k] > best[0]:
                best = (float(gain[k]), j, float(cj[k]))
        if best[1] < 0 or best[0] < 1e-6:
            return node
        _, j, th = best
        mask = X[idx, j] <= th
        tree.feature[node], tree.threshold[node] = j, th
        tree.left[node] = self._grow(X, g, h, idx[mask], cuts, depth - 1, tree)
        tree.right[node] = self._grow(X, g, h, idx[~mask], cuts, depth - 1, tree)
        return node

    def fit(self, X: np.ndarray, y: np.ndarray, X_val: np.ndarray | None = None, y_val: np.ndarray | None = None) -> "GBDT":
        X, y = _prep(X), np.asarray(y, dtype=np.float64)
        p0 = min(max(y.mean(), 1e-3), 1 - 1e-3)
        self.base = math.log(p0 / (1 - p0))
        cuts = self._cuts(X)
        raw = np.full(len(y), self.base)
        best_loss, best_n, val_raw = math.inf, 0, None
        if X_val is not None:
            X_val = _prep(X_val)
            val_raw = np.full(len(y_val), self.base)
        for t in range(self.n_trees):
            p = 1 / (1 + np.exp(-raw))
            g, h = p - y, np.maximum(p * (1 - p), 1e-6)
            tree = Tree()
            self._grow(X, g, h, np.arange(len(y)), cuts, self.depth, tree)
            tree.value = [v * self.lr for v in tree.value]
            self.trees.append(tree)
            raw += tree.predict(X)
            if val_raw is not None:
                val_raw += tree.predict(X_val)
                pv = np.clip(1 / (1 + np.exp(-val_raw)), 1e-6, 1 - 1e-6)
                loss = float(-np.mean(y_val * np.log(pv) + (1 - y_val) * np.log(1 - pv)))
                if loss < best_loss - 1e-5:
                    best_loss, best_n = loss, t + 1
                elif t + 1 - best_n >= 25:
                    break
        if val_raw is not None and best_n:
            self.trees = self.trees[:best_n]
        return self

    def raw(self, X: np.ndarray) -> np.ndarray:
        X = _prep(X)
        out = np.full(len(X), self.base)
        for tree in self.trees:
            out += tree.predict(X)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"base": self.base, "trees": [t.__dict__ for t in self.trees]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GBDT":
        m = cls()
        m.base = d["base"]
        m.trees = [Tree(**t) for t in d["trees"]]
        return m


# ---------------------------------------------------------------------------------------------- calibration
class Isotonic:
    """Régression isotonique (pool adjacent violators) : score brut → probabilité, croissante, mesurée."""

    def __init__(self, x: list[float] | None = None, y: list[float] | None = None):
        self.x, self.y = x or [], y or []

    def fit(self, s: np.ndarray, t: np.ndarray) -> "Isotonic":
        order = np.argsort(s)
        s, t = np.asarray(s)[order], np.asarray(t, dtype=np.float64)[order]
        blocks: list[list[float]] = []  # [somme y, poids, x min, x max]
        for xi, yi in zip(s, t):
            blocks.append([yi, 1.0, xi, xi])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
                a, b = blocks[-2], blocks.pop()
                a[0] += b[0]; a[1] += b[1]; a[3] = b[3]  # noqa: E702
        xs, ys = [], []
        for sy, w, lo, hi in blocks:
            v = (sy + 0.5) / (w + 1.0)  # lissage de Laplace léger : jamais 0 ni 1 absolus
            xs += [float(lo), float(hi)]
            ys += [v, v]
        self.x, self.y = xs, ys
        return self

    def __call__(self, s: np.ndarray) -> np.ndarray:
        if not self.x:
            return 1 / (1 + np.exp(-np.asarray(s)))
        return np.interp(s, self.x, self.y)


class Platt:
    def __init__(self, a: float = 1.0, b: float = 0.0):
        self.a, self.b = a, b

    def fit(self, s: np.ndarray, t: np.ndarray) -> "Platt":
        a, b = 1.0, 0.0
        for _ in range(200):
            p = 1 / (1 + np.exp(-(a * s + b)))
            ga, gb = np.sum((p - t) * s), np.sum(p - t)
            w = p * (1 - p) + 1e-9
            haa, hab, hbb = np.sum(w * s * s) + 1e-6, np.sum(w * s), np.sum(w) + 1e-6
            det = haa * hbb - hab * hab
            if abs(det) < 1e-12:
                break
            a -= (hbb * ga - hab * gb) / det
            b -= (haa * gb - hab * ga) / det
        self.a, self.b = float(a), float(b)
        return self

    def __call__(self, s: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-(self.a * np.asarray(s) + self.b)))


def wilson_low(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def metrics(p: np.ndarray, y: np.ndarray, target: float = 0.95) -> dict[str, Any]:
    p, y = np.asarray(p, dtype=np.float64), np.asarray(y, dtype=np.float64)
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    pos, neg = y.sum(), len(y) - y.sum()
    auc = 0.5
    if pos and neg:  # AUC = probabilité qu'un vrai couple soit mieux classé qu'un faux
        ranks = np.argsort(np.argsort(p)) + 1
        auc = float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))
    bins = []
    ece = 0.0
    for lo in np.linspace(0, 0.9, 10):
        m = (p >= lo) & (p < lo + 0.1 if lo < 0.9 else p <= 1.0)
        if m.sum():
            conf, acc = float(p[m].mean()), float(y[m].mean())
            ece += m.sum() / len(p) * abs(conf - acc)
            bins.append({"from": round(float(lo), 1), "n": int(m.sum()), "predicted": round(conf, 3), "observed": round(acc, 3)})
    threshold, kept = 1.0, 0
    for t in sorted(set(np.round(p, 3)), reverse=True):  # plus petit seuil dont la précision reste garantie
        m = p >= t
        if m.sum() and wilson_low(int(y[m].sum()), int(m.sum())) >= target:
            threshold, kept = float(t), int(m.sum())
    m = p >= threshold
    return {"pairs": int(len(y)), "positives": int(pos), "auc": round(auc, 4), "brier": round(float(np.mean((p - y) ** 2)), 4),
            "logloss": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 4), "ece": round(float(ece), 4),
            "threshold": round(threshold, 3), "target": target,
            "precision_at_threshold": round(float(y[m].mean()), 4) if m.sum() else None,
            "recall_at_threshold": round(float(y[m].sum() / pos), 4) if pos and m.sum() else 0.0, "covered": kept, "reliability": bins}


class CalibratedModel:
    """GBDT + calibration, entraîné et mesuré par validation croisée par groupes (questionnaire)."""

    def __init__(self, features: list[str]):
        self.features = features
        self.model: GBDT | None = None
        self.calibrator: Isotonic | Platt = Platt()
        self.strata: dict[str, Isotonic | Platt] = {}  # calibration propre à chaque strate (avec / sans preuve directe)
        self.report: dict[str, Any] = {}

    @staticmethod
    def _cal(oof: np.ndarray, y: np.ndarray) -> "Isotonic | Platt":
        few = min(y.sum(), len(y) - y.sum()) < 40
        return (Platt() if few else Isotonic()).fit(oof, y)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, folds: int = 5, target: float = 0.95,
            strata: np.ndarray | None = None) -> "CalibratedModel":
        X, y, groups = np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64), np.asarray(groups)
        uniq = np.unique(groups)
        rng = np.random.default_rng(7)
        fold_of = {g: i % folds for i, g in enumerate(rng.permutation(uniq))}
        fid = np.array([fold_of[g] for g in groups])
        oof = np.zeros(len(y))
        for k in range(folds):
            tr, te = fid != k, fid == k
            if not te.any() or len(np.unique(y[tr])) < 2:
                continue
            inner = rng.random(tr.sum()) < 0.15  # arrêt précoce sur une part de l'apprentissage, jamais sur la mesure
            Xt, yt = X[tr], y[tr]
            m = GBDT().fit(Xt[~inner], yt[~inner], Xt[inner], yt[inner]) if inner.sum() > 20 else GBDT(n_trees=80).fit(Xt, yt)
            oof[te] = m.raw(X[te])
        few = min(y.sum(), len(y) - y.sum()) < 40
        self.calibrator = self._cal(oof, y)
        cal = self.calibrator(oof)
        self.strata = {}
        if strata is not None:
            strata = np.asarray(strata).astype(bool)
            for name, mask in (("1", strata), ("0", ~strata)):
                if mask.sum() >= 30 and 0 < y[mask].sum() < mask.sum():
                    self.strata[name] = self._cal(oof[mask], y[mask])
                    cal[mask] = self.strata[name](oof[mask])
                elif mask.sum():
                    self.strata[name] = Platt(0.0, float(np.log((y[mask].sum() + 0.5) / (mask.sum() - y[mask].sum() + 0.5))))
                    cal[mask] = self.strata[name](oof[mask])
        self.report = {**metrics(cal, y, target), "calibration": ("Platt" if few else "isotonique") + (" par strate" if self.strata else ""),
                       "folds": folds, "groups": int(len(uniq))}
        inner = rng.random(len(y)) < 0.15
        self.model = GBDT().fit(X[~inner], y[~inner], X[inner], y[inner]) if inner.sum() > 20 else GBDT(n_trees=80).fit(X, y)
        self.report["trees"] = len(self.model.trees)
        return self

    def predict(self, X: np.ndarray, strata: np.ndarray | None = None) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("modèle non entraîné")
        raw = self.model.raw(X)
        out = self.calibrator(raw)
        if strata is not None and self.strata:
            strata = np.asarray(strata).astype(bool)
            for name, mask in (("1", strata), ("0", ~strata)):
                if name in self.strata and mask.any():
                    out[mask] = self.strata[name](raw[mask])
        return out

    def to_dict(self) -> dict[str, Any]:
        cal = {"kind": "isotonic", "x": self.calibrator.x, "y": self.calibrator.y} if isinstance(self.calibrator, Isotonic) \
            else {"kind": "platt", "a": self.calibrator.a, "b": self.calibrator.b}
        def enc(c):
            return {"kind": "isotonic", "x": c.x, "y": c.y} if isinstance(c, Isotonic) else {"kind": "platt", "a": c.a, "b": c.b}
        return {"features": self.features, "model": self.model.to_dict() if self.model else None, "calibrator": cal,
                "strata": {k: enc(v) for k, v in self.strata.items()}, "report": self.report}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalibratedModel":
        m = cls(d["features"])
        m.model = GBDT.from_dict(d["model"]) if d.get("model") else None
        c = d["calibrator"]
        m.calibrator = Isotonic(c["x"], c["y"]) if c["kind"] == "isotonic" else Platt(c["a"], c["b"])
        m.strata = {k: (Isotonic(v["x"], v["y"]) if v["kind"] == "isotonic" else Platt(v["a"], v["b"])) for k, v in d.get("strata", {}).items()}
        m.report = d.get("report", {})
        return m


__all__ = ["GBDT", "Isotonic", "Platt", "CalibratedModel", "metrics", "wilson_low"]
