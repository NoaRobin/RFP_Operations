"""Exécution d'une liste : téléchargements HTTP en parallèle, navigateur en dernier recours (un seul, séquentiel),
écriture atomique, jamais d'écrasement sans demande, résultat par ligne."""
from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .catalog import doc_type
from .resolver import DocumentNotFound, Resolver
from .shopping import Item


@dataclass
class Result:
    id: str
    isin: str
    fund: str
    kind: str
    period: str
    status: str  # OK | DÉJÀ PRÉSENT | ÉCHEC | IGNORÉ
    detail: str
    file: str = ""
    url: str = ""
    strategy: str = ""
    size: int = 0
    sha256: str = ""
    at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, target)


def run_list(items: list[Item], resolver: Resolver, dest: Path, *, only_missing: bool = True, workers: int = 4,
             log: Callable[[str, str], None] = lambda level, msg: None, progress: Callable[[float], None] = lambda v: None) -> list[Result]:
    active = [i for i in items if i.active]
    results: dict[str, Result] = {}
    pending_browser: list[Item] = []

    def base(item: Item) -> Result:
        doc = doc_type(item.kind)
        p = item.period()
        return Result(item.id, item.isin, item.fund, doc.label, p.label if doc.needs_month else "", "ÉCHEC", "",
                      at=datetime.now().isoformat(timespec="seconds"))

    def one(item: Item, allow_browser: bool) -> Result:
        res = base(item)
        try:
            target = dest / item.target_name()
            res.file = str(target)
            if target.exists() and only_missing and not item.overwrite:
                res.status, res.detail, res.size = "DÉJÀ PRÉSENT", "fichier déjà présent (non écrasé)", target.stat().st_size
                return res
            doc = doc_type(item.kind)
            ident = resolver.identity(item.isin, item.fund, item.part)
            found = resolver.find(ident, doc, item.period(), allow_browser=allow_browser)
            _write(target, found.content)
            res.status, res.url, res.strategy, res.size = "OK", found.url, found.strategy, len(found.content)
            res.sha256 = hashlib.sha256(found.content).hexdigest()
            res.detail = f"adresse {found.strategy}" + (f" · {found.note}" if found.note else "")
        except DocumentNotFound as error:
            res.detail = str(error)
        except ValueError as error:
            res.status, res.detail = "IGNORÉ", str(error)
        except OSError as error:
            res.detail = f"écriture impossible : {error}"
        return res

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for item, res in zip(active, pool.map(lambda i: one(i, allow_browser=False), active)):
            done += 1
            progress(done / max(1, len(active)) * (0.8 if resolver.browser else 1.0))
            if res.status == "ÉCHEC" and resolver.browser is not None:
                pending_browser.append(item)
                continue
            results[item.id] = res
            log("success" if res.status == "OK" else "info" if res.status != "ÉCHEC" else "warning",
                f"{res.fund or res.isin} · {res.kind} {res.period} → {res.status} ({res.detail})")
    for n, item in enumerate(pending_browser, start=1):  # navigateur : un document à la fois
        res = one(item, allow_browser=True)
        results[item.id] = res
        progress(0.8 + 0.2 * n / len(pending_browser))
        log("success" if res.status == "OK" else "warning", f"{res.fund or res.isin} · {res.kind} {res.period} → {res.status} ({res.detail})")
    resolver.memory.save()
    return [results[i.id] for i in active if i.id in results]
