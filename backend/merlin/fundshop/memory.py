"""Ce que l'app a appris du site : GUID de chaque part / fonds, colonne Product Info qui les porte, langues.

Fichier data/fundshop/learned.json (jamais committé). Peut être amorcé avec le CSV du script historique
(resultats_telechargement.csv : colonne url_source).
"""
from __future__ import annotations

import csv
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

URL = re.compile(r"https?://[^/\s]+/([A-Z0-9]+)_([0-9a-fA-F-]{36})_([A-Z]{2}_[A-Z]{2})(?:_(\d{8}))?\.pdf", re.I)
SHARE_PREFIXES = {"DIPR", "REPM"}


def parse_url(url: str) -> dict[str, str] | None:
    m = URL.search(url or "")
    if not m:
        return None
    prefix = m.group(1).upper()
    return {"prefix": prefix, "guid": m.group(2).lower(), "lang": m.group(3).upper(), "date": m.group(4) or "",
            "level": "share" if prefix in SHARE_PREFIXES else "product"}


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {"guids": {}, "id_column": {}, "langs": {}, "urls": {}, "pages": {}}
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                pass

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def guid(self, isin: str, level: str) -> str | None:
        return self.data["guids"].get(f"{isin.upper()}|{level}")

    def page(self, isin: str) -> str | None:
        return self.data["pages"].get(isin.upper())

    def remember_page(self, isin: str, url: str) -> None:
        with self._lock:
            self.data["pages"][isin.upper()] = url

    def url(self, isin: str, kind: str) -> str | None:
        entry = self.data["urls"].get(f"{isin.upper()}|{kind}")
        return entry.get("url") if entry else None

    def learn(self, isin: str, url: str, id_column: str | None = None, kind: str | None = None) -> None:
        info = parse_url(url)
        if not info:
            return
        with self._lock:
            self.data["guids"][f"{isin.upper()}|{info['level']}"] = info["guid"]
            if id_column:
                self.data["id_column"][info["level"]] = id_column
            if kind and kind.endswith(" en"):
                self.data["langs"][kind] = info["lang"]
            if kind:
                self.data["urls"][f"{isin.upper()}|{kind}"] = {"url": url, "at": datetime.now().isoformat(timespec="seconds")}

    def seed_from_csv(self, path: Path) -> int:
        """Résultats du script historique : chaque url_source réussie apprend le GUID de la part ou du fonds."""
        count = 0
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                url, isin = row.get("url_source") or "", (row.get("isin") or "").strip().upper()
                if isin and parse_url(url) and (row.get("statut") or "").upper().startswith("OK"):
                    self.learn(isin, url, kind=(row.get("type_document") or "").strip().lower() or None)
                    count += 1
        self.save()
        return count

    def stats(self) -> dict[str, Any]:
        guids = self.data["guids"]
        return {"shares": sum(1 for k in guids if k.endswith("|share")), "funds": sum(1 for k in guids if k.endswith("|product")),
                "pages": len(self.data["pages"]),
                "id_column": self.data["id_column"], "langs": self.data["langs"]}
