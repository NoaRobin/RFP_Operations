"""Documents d'une part : recherche (sources par ordre de préférence), cache local, lecture, faits rattachés aux concepts.

Cache : data/rfi/documents/<ISIN>/ (PDF + index.json). Re-téléchargement si le cache a plus de 30 jours ou si
Product Info signale un DIC modifié depuis (PI_OUT_Share.Last_DIC_Modification_Date).
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..values import to_date
from . import extract_kid, extract_prospectus
from .finder import DocumentFinder
from .model import DocumentRef, Fact
from .text import pages_text

MAX_AGE = timedelta(days=30)


class DocumentService:
    def __init__(self, root: Path, finders: list[DocumentFinder], fund_names: list[str] | None = None):
        self.root = root
        self.finders = finders
        self.fund_names = fund_names or []
        self._lock = threading.Lock()
        self._facts: dict[str, tuple[dict[str, Fact], list[str], list[DocumentRef]]] = {}

    # ------------------------------------------------------------------ cache
    def _index_path(self, isin: str) -> Path:
        return self.root / isin.upper() / "index.json"

    def _cached(self, isin: str) -> list[DocumentRef]:
        p = self._index_path(isin)
        if not p.exists():
            return []
        try:
            return [DocumentRef(**d) for d in json.loads(p.read_text(encoding="utf-8"))]
        except (ValueError, TypeError):
            return []

    def _stale(self, refs: list[DocumentRef], last_kid: date | None) -> bool:
        if not refs:
            return True
        oldest = min((datetime.fromisoformat(r.fetched_at) for r in refs if r.fetched_at), default=None)
        if oldest is None or datetime.now() - oldest > MAX_AGE:
            return True
        kid_date = max((to_date(r.doc_date) for r in refs if r.kind == "kid" and r.doc_date), default=None)
        return bool(last_kid and kid_date and last_kid > kid_date)

    def documents(self, isin: str, fund_name: str = "", share_name: str = "", last_kid: date | None = None,
                  refresh: bool = False) -> tuple[list[DocumentRef], list[str]]:
        isin = isin.upper()
        notes: list[str] = []
        with self._lock:
            refs = self._cached(isin)
            if refresh or self._stale(refs, last_kid):
                fresh: list[DocumentRef] = []
                for finder in self.finders:
                    try:
                        found = finder.find(isin, fund_name, share_name)
                    except Exception as error:  # noqa: BLE001 - une source en panne n'arrête pas les autres
                        notes.append(f"{finder.name} : {type(error).__name__}")
                        continue
                    notes.extend(getattr(finder, "errors", [])[-2:])
                    for ref in found:
                        if any(r.kind == ref.kind for r in fresh) and ref.kind == "kid" and ref.lang not in ("", "fr", "en"):
                            continue
                        target = self.root / isin / f"{ref.kind}_{hashlib.sha1(ref.url.encode()).hexdigest()[:10]}.pdf"
                        try:
                            finder.fetch(ref, target)
                        except Exception as error:  # noqa: BLE001
                            notes.append(f"{ref.title} : téléchargement impossible ({error})")
                            continue
                        ref.path, ref.fetched_at = str(target), datetime.now().isoformat(timespec="seconds")
                        ref.sha = hashlib.sha256(target.read_bytes()).hexdigest()[:16]
                        fresh.append(ref)
                    if any(r.kind == "kid" for r in fresh):
                        break  # première source qui fournit le DIC : on s'arrête
                if fresh:
                    refs = fresh
                    self._index_path(isin).parent.mkdir(parents=True, exist_ok=True)
                    self._index_path(isin).write_text(json.dumps([r.to_dict() for r in refs], ensure_ascii=False, indent=1), encoding="utf-8")
                    self._facts.pop(isin, None)
                elif not refs:
                    notes.append("aucun DIC ni prospectus trouvé pour cette part")
        return refs, notes

    # ------------------------------------------------------------------ faits
    def facts(self, isin: str, fund_name: str = "", share_name: str = "", last_kid: date | None = None) -> tuple[dict[str, Fact], list[str], list[DocumentRef]]:
        isin = isin.upper()
        refs, notes = self.documents(isin, fund_name, share_name, last_kid)
        if isin in self._facts and not notes:
            return self._facts[isin]
        facts: dict[str, Fact] = {}
        problems = list(notes)
        for ref in sorted(refs, key=lambda r: (r.kind != "kid", r.lang not in ("fr", ""), r.fetched_at)):
            try:
                pages = pages_text(Path(ref.path))
            except Exception as error:  # noqa: BLE001
                problems.append(f"{ref.title} : PDF illisible ({type(error).__name__})")
                continue
            if ref.kind == "kid":
                found, issues = extract_kid.extract(pages, ref, isin)
            else:
                found, issues = extract_prospectus.extract(pages, ref, isin, fund_name, self.fund_names)
            problems.extend(f"{ref.title} : {i}" for i in issues)
            for k, v in found.items():
                facts.setdefault(k, v)
        result = (facts, problems, refs)
        self._facts[isin] = result
        return result

    def describe(self, isin: str, fund_name: str = "", share_name: str = "") -> dict[str, Any]:
        facts, problems, refs = self.facts(isin, fund_name, share_name)
        return {"isin": isin, "documents": [r.to_dict() for r in refs], "facts": [f.to_dict() for f in facts.values()],
                "problems": problems}
