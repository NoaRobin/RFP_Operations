"""Catalogue d'extractions de l'Atelier : chargement, validation, exécution."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..data.access import DataAccess
from ..data.catalog import Catalog

EXTRACTIONS_FILE = Path(__file__).with_name("extractions.yaml")

TEMPLATES = {
    "aum_latest": """
SELECT a.CODE_ISIN_PART AS cle, a.{column} AS valeur
FROM dbo.JUMP_portfolio_aum a
JOIN (
  SELECT CODE_ISIN_PART, MAX(DATE_VL) AS d
  FROM dbo.JUMP_portfolio_aum
  WHERE DATE_VL <= :as_of
  GROUP BY CODE_ISIN_PART
) m ON m.CODE_ISIN_PART = a.CODE_ISIN_PART AND m.d = a.DATE_VL
""",
    "instrument_latest": """
SELECT h.CODE_ISIN_INSTRUMENT AS cle, MAX(h.{column}) AS valeur
FROM dbo.JUMP_portfolio_holdings h
JOIN (
  SELECT CODE_ISIN_INSTRUMENT, MAX(DATE_INVENTAIRE) AS d
  FROM dbo.JUMP_portfolio_holdings
  WHERE DATE_INVENTAIRE <= :as_of AND CODE_ISIN_INSTRUMENT IS NOT NULL
  GROUP BY CODE_ISIN_INSTRUMENT
) m ON m.CODE_ISIN_INSTRUMENT = h.CODE_ISIN_INSTRUMENT AND m.d = h.DATE_INVENTAIRE
GROUP BY h.CODE_ISIN_INSTRUMENT
""",
}

EXCEL_FORMATS = {"amount": "#,##0", "number": "#,##0.00###", "date": "dd/mm/yyyy", "percent": "0.00%"}


@dataclass
class KeyType:
    id: str
    label: str
    synonyms: list[str]
    pattern: re.Pattern | None


@dataclass
class Extraction:
    id: str
    label: str
    group: str
    key: str
    format: str
    sql: str
    synonyms: list[str] = field(default_factory=list)
    source: str = ""
    caution: str | None = None
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "group": self.group, "key": self.key, "format": self.format,
            "synonyms": self.synonyms, "source": self.source, "caution": self.caution,
            "healthy": not self.problems, "problems": self.problems,
        }


@dataclass
class ExtractionCatalog:
    key_types: dict[str, KeyType]
    extractions: dict[str, Extraction]

    def for_key(self, key: str) -> list[Extraction]:
        return [e for e in self.extractions.values() if e.key == key and not e.problems]


@lru_cache
def get_extractions(catalog: Catalog) -> ExtractionCatalog:
    raw = yaml.safe_load(EXTRACTIONS_FILE.read_text(encoding="utf-8"))
    key_types = {
        key: KeyType(key, spec["label"], spec.get("synonyms", []), re.compile(spec["pattern"]) if spec.get("pattern") else None)
        for key, spec in raw["key_types"].items()
    }
    extractions: dict[str, Extraction] = {}
    for spec in raw["extractions"]:
        if spec.get("template"):
            sql = TEMPLATES[spec["template"]].format(column=spec["column"])
            table = "JUMP_portfolio_aum" if spec["template"] == "aum_latest" else "JUMP_portfolio_holdings"
            source = f"{table}.{spec['column']}"
        else:
            sql, source = spec["sql"], "Requête composée"
        extraction = Extraction(
            id=spec["id"], label=spec["label"], group=spec.get("group", "Divers"), key=spec["key"],
            format=spec.get("format", "text"), sql=sql, synonyms=spec.get("synonyms", []), source=source,
            caution=spec.get("caution"),
        )
        if extraction.key not in key_types:
            extraction.problems.append(f"Type de clé inconnu : {extraction.key}")
        extraction.problems += catalog.validate_sql(sql)
        extractions[extraction.id] = extraction
    return ExtractionCatalog(key_types, extractions)


def normalize_value(value: Any, fmt: str) -> Any:
    if value is None or (isinstance(value, float) and value != value):
        return None
    if fmt == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return value
    if fmt in {"amount", "number", "percent"}:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value
        return int(number) if number.is_integer() and fmt != "percent" else number
    return str(value) if not isinstance(value, str) else value


def run_extraction(data: DataAccess, extraction: Extraction, as_of: str) -> dict[str, Any]:
    frame = data.query(extraction.sql, {"as_of": as_of})
    if frame.empty:
        return {}
    return {
        str(k).strip().upper(): normalize_value(v, extraction.format)
        for k, v in zip(frame["cle"], frame["valeur"])
        if k is not None
    }
