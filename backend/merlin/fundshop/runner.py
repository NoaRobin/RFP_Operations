"""Exécution d'une liste : vérification du réseau, téléchargements en parallèle, écriture atomique, jamais d'écrasement
sans demande. Chaque ligne repart avec un statut et, en cas d'échec, la raison en clair et quoi faire."""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .catalog import doc_type
from .problems import DocumentProblem, Problem, problem
from .resolver import Resolver
from .shopping import Item

STRATEGY = {"mémorisée": "adresse déjà connue", "construite": "adresse déduite de Product Info", "page du fonds": "lien trouvé sur la page du fonds",
            "lien collé": "lien que vous avez donné"}


@dataclass
class Result:
    id: str
    isin: str
    fund: str
    part: str
    kind: str
    period: str
    status: str  # OK | DÉJÀ PRÉSENT | ÉCHEC
    title: str = ""  # phrase courte (ex. « Téléchargé », « Pas sur le site pour juillet 2026 »)
    why: str = ""
    fix: str = ""
    code: str = ""
    link: str = ""
    file: str = ""
    url: str = ""
    size: int = 0
    sha256: str = ""
    at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def fail(self, p: Problem, status: str = "ÉCHEC") -> "Result":
        self.status, self.title, self.why, self.fix, self.code, self.link = status, p.title, p.why, p.fix, p.code, p.link
        return self


def _write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, target)


def precheck(resolver: Resolver, dest: Path) -> Problem | None:
    """Avant de lancer 50 téléchargements : le dossier est-il accessible, le site joignable ? Une seule explication si non."""
    try:
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / ".rfp-test"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as error:
        return problem("dossier", path=str(dest), detail=str(error))
    ok, error, _ = resolver.net.check(resolver.docs_base + "/")
    if not ok and error is not None:
        return problem(error.code, host=error.host or urlparse(resolver.docs_base).netloc, detail=error.detail, link=resolver.docs_base)
    return None


def run_list(items: list[Item], resolver: Resolver, dest: Path, *, only_missing: bool = True, workers: int = 4,
             log: Callable[[str, str], None] = lambda level, msg: None, progress: Callable[[float], None] = lambda v: None,
             blocked: Problem | None = None) -> list[Result]:
    active = [i for i in items if i.active]

    def one(item: Item) -> Result:
        doc = doc_type(item.kind)
        p = item.period()
        res = Result(item.id, item.isin, item.fund, item.part, doc.label, p.label if doc.needs_month else "", "ÉCHEC",
                     at=datetime.now().isoformat(timespec="seconds"))
        try:
            target = dest / item.target_name()
        except ValueError:
            return res.fail(problem("mois", doc=doc.label))
        res.file = target.name
        if blocked is not None:
            return res.fail(blocked)
        if target.exists() and only_missing and not item.overwrite:
            res.size = target.stat().st_size
            return res.fail(problem("deja"), status="DÉJÀ PRÉSENT")
        ident = resolver.identity(item.isin, item.fund, item.part)
        try:
            found = resolver.find(ident, doc, p)
        except DocumentProblem as error:
            return res.fail(error.problem)
        try:
            _write(target, found.content)
        except OSError as error:
            return res.fail(problem("dossier", path=str(dest), detail=str(error)))
        res.status, res.title, res.url, res.size = "OK", "Téléchargé", found.url, len(found.content)
        res.why = STRATEGY.get(found.strategy, found.strategy) + (f" · {found.note}" if found.note else "")
        res.sha256 = hashlib.sha256(found.content).hexdigest()
        return res

    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for n, res in enumerate(pool.map(one, active), start=1):
            results.append(res)
            progress(n / max(1, len(active)))
            label = f"{res.fund or res.isin} · {res.kind}{' ' + res.period if res.period else ''}"
            if res.status == "OK":
                log("success", f"{label} → téléchargé ({res.why})")
            elif res.status == "DÉJÀ PRÉSENT":
                log("info", f"{label} → déjà dans le dossier")
            else:
                log("warning", f"{label} → {res.title}. {res.fix}")
    resolver.memory.save()
    return results


def save_last_run(root: Path, results: list[Result], destination: Path, network: str, blocked: Problem | None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now().isoformat(timespec="seconds"), "destination": str(destination), "network": network,
               "blocked": blocked.to_dict() if blocked else None, "results": [r.to_dict() for r in results]}
    tmp = root / "last_run.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(root / "last_run.json")


def load_last_run(root: Path) -> dict | None:
    path = root / "last_run.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
