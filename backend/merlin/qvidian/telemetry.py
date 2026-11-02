"""Optimisation des appels Qvidian : mesure de chaque appel, cache des lectures, limiteur de débit, relances.

- Télémétrie : par opération SOAP, nombre d'appels, erreurs, latence (p50 / p95), octets reçus, réponses servies par
  le cache, relances ; les 200 derniers appels pour l'écran « API & moteur ». Jamais le contenu ni le jeton.
- Cache TTL des lectures idempotentes (détail d'un contenu, aperçu HTML d'une révision, dossiers, permissions) ;
  invalidé contenu par contenu après une écriture.
- Limiteur de débit (seau à jetons) partagé par tous les fils : la synchronisation parallèle ne sature jamais le serveur.
- Relances des lectures seulement (délai dépassé, réseau), deux au plus, attente exponentielle avec gigue.
"""
from __future__ import annotations

import random
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Callable

READ_CACHE_TTL = {  # opération → durée de vie (secondes) ; None = TTL par défaut du réglage
    "libraryContentDetailsGet": None, "libraryFoldersGetList": 600, "libraryFolderGetTop": 600, "HasPermissions": 600,
    "libraryContentPreviewHTMLGet": 3600,  # par révision : immuable
}
WRITE_OPS = {"libraryContentDetailsUpdate"}
RETRY_CODES = {"delai", "reseau"}


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo), 1)


class Telemetry:
    def __init__(self, keep: int = 200, window: int = 500):
        self._lock = threading.Lock()
        self.ops: dict[str, dict[str, Any]] = {}
        self.recent: deque = deque(maxlen=keep)
        self.window = window
        self.started = time.time()

    def record(self, op: str, ms: float, ok: bool = True, code: str | None = None, bytes_in: int = 0, cached: bool = False,
               retries: int = 0) -> None:
        with self._lock:
            s = self.ops.setdefault(op, {"calls": 0, "errors": 0, "cached": 0, "retries": 0, "bytes_in": 0, "lat": deque(maxlen=self.window)})
            s["calls"] += 1
            s["errors"] += 0 if ok else 1
            s["cached"] += 1 if cached else 0
            s["retries"] += retries
            s["bytes_in"] += bytes_in
            if not cached:
                s["lat"].append(ms)
            self.recent.append({"at": time.strftime("%H:%M:%S"), "op": op, "ms": round(ms, 1), "ok": ok, "code": code,
                                "cached": cached, "bytes": bytes_in, "retries": retries})

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = []
            for op, s in self.ops.items():
                lat = list(s["lat"])
                rows.append({"op": op, "calls": s["calls"], "errors": s["errors"], "cached": s["cached"], "retries": s["retries"],
                             "kb_in": round(s["bytes_in"] / 1024, 1), "p50_ms": _percentile(lat, 0.5), "p95_ms": _percentile(lat, 0.95),
                             "avg_ms": round(sum(lat) / len(lat), 1) if lat else 0.0})
            rows.sort(key=lambda r: -r["calls"])
            calls = sum(r["calls"] for r in rows)
            cached = sum(r["cached"] for r in rows)
            errors = sum(r["errors"] for r in rows)
            network = [x for r in self.ops.values() for x in r["lat"]]
            return {"since": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.started)), "calls": calls, "errors": errors,
                    "cached": cached, "cache_rate": round(cached / calls, 3) if calls else 0.0,
                    "error_rate": round(errors / calls, 3) if calls else 0.0, "p50_ms": _percentile(network, 0.5),
                    "p95_ms": _percentile(network, 0.95), "kb_in": round(sum(r["kb_in"] for r in rows), 1),
                    "operations": rows, "recent": list(reversed(self.recent))[:60]}

    def reset(self) -> None:
        with self._lock:
            self.ops.clear()
            self.recent.clear()
            self.started = time.time()


class TtlCache:
    def __init__(self, ttl: float = 300, size: int = 5000):
        self.ttl, self.size = ttl, size
        self._data: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> tuple[bool, Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return False, None
            expires, value = item
            if expires < time.time():
                self._data.pop(key, None)
                return False, None
            self._data.move_to_end(key)
            return True, value

    def put(self, key: tuple, value: Any, ttl: float | None = None) -> None:
        if (ttl if ttl is not None else self.ttl) <= 0:
            return
        with self._lock:
            self._data[key] = (time.time() + (ttl if ttl is not None else self.ttl), value)
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def invalidate(self, match: Callable[[tuple], bool] | None = None) -> int:
        with self._lock:
            keys = [k for k in self._data if match is None or match(k)]
            for k in keys:
                self._data.pop(k, None)
            return len(keys)

    def __len__(self) -> int:
        return len(self._data)


class RateLimiter:
    """Seau à jetons : `rate` appels par seconde en moyenne, rafales de `burst`."""

    def __init__(self, rate: float = 8.0, burst: int = 16):
        self.rate, self.burst = max(rate, 0.1), max(burst, 1)
        self.tokens = float(self.burst)
        self.stamp = time.monotonic()
        self.waited = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> float:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.stamp) * self.rate)
            self.stamp = now
            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            wait = (1 - self.tokens) / self.rate
            self.tokens = 0.0
            self.stamp = now + wait
            self.waited += wait
        time.sleep(wait)
        return wait


def backoff(attempt: int, base: float = 0.5, cap: float = 6.0) -> float:
    return min(cap, base * 2 ** attempt) * (0.5 + random.random() / 2)


__all__ = ["Telemetry", "TtlCache", "RateLimiter", "READ_CACHE_TTL", "WRITE_OPS", "RETRY_CODES", "backoff"]
