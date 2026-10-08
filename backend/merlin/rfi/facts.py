"""Faits quantitatifs d'un fonds / d'une part : chargement du dictionnaire, calcul des valeurs, mise en forme."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..data.access import DataAccess, DataError
from ..data.catalog import Catalog

FACTS_FILE = Path(__file__).with_name("facts.yaml")
PRODUCT, SHARE = "pi_out_product_active", "PI_OUT_Share"


def norm(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("’", "'").replace("`", "'")
    return " ".join(re.sub(r"[^a-z0-9%'/+\-]+", " ", value).split())


@dataclass
class Fact:
    id: str
    label: str
    scope: str
    source: str
    format: str
    keywords: list[list[str]]
    exclude: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    jump_field: str | None = None

    @property
    def table(self) -> str | None:
        return None if self.source.startswith("jump:") else self.source.split(".")[0]

    @property
    def column(self) -> str | None:
        return None if self.source.startswith("jump:") else self.source.split(".", 1)[1]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "scope": self.scope, "format": self.format,
                "source": self.source if not self.jump_field else f"{self.source} · {self.jump_field}", "healthy": not self.problems}


@lru_cache
def load_facts(catalog: Catalog) -> dict[str, Fact]:
    raw = yaml.safe_load(FACTS_FILE.read_text(encoding="utf-8"))
    facts: dict[str, Fact] = {}
    for spec in raw["facts"]:
        fact = Fact(
            id=spec["id"], label=spec["label"], scope=spec["scope"], source=spec["source"], format=spec["format"],
            keywords=[[norm(t) for t in group] for group in spec.get("keywords", [])],
            exclude=[norm(t) for t in spec.get("exclude", [])], jump_field=spec.get("field"),
        )
        if fact.table:
            table = catalog.table(fact.table)
            if table is None or table.column(fact.column) is None:
                fact.problems.append(f"Colonne absente du catalogue : {fact.source}")
        facts[fact.id] = fact
    return facts


# --------------------------------------------------------------------------- requêtes JUMP
JUMP_QUERIES = {
    "fund_aum": """
        SELECT TOP 1 a.ACTIF_NET_TOTAL_EURO, a.ACTIF_NET_TOTAL_DEVISE_FONDS, a.DEVISE_FONDS, a.DATE_VL
        FROM dbo.JUMP_portfolio_aum a
        WHERE a.ID_PI_FONDS = :pid AND a.DATE_VL <= :as_of
        ORDER BY a.DATE_VL DESC""",
    "share_aum": """
        SELECT TOP 1 a.ACTIF_NET_DEVISE_PART, a.ACTIF_NET_PART_EURO, a.VL_UNITAIRE, a.NOMBRE_PARTS, a.DEVISE_VL, a.DATE_VL
        FROM dbo.JUMP_portfolio_aum a
        WHERE a.CODE_ISIN_PART = :isin AND a.DATE_VL <= :as_of
        ORDER BY a.DATE_VL DESC""",
    "share_classes": """
        SELECT COUNT(DISTINCT a.CODE_ISIN_PART) AS valeur
        FROM dbo.JUMP_portfolio_aum a
        WHERE a.ID_PI_FONDS = :pid AND a.DATE_VL = (
            SELECT MAX(b.DATE_VL) FROM dbo.JUMP_portfolio_aum b WHERE b.ID_PI_FONDS = :pid AND b.DATE_VL <= :as_of)""",
    "holdings": """
        SELECT h.NOM_INSTRUMENT, h.CLASSE_ACTIF, h.DEVISE_INSTRUMENT, h.TYPE_HOLDING, h.POIDS_LIGNE_EXPO, h.MONTANT_DEVISE_FONDS
        FROM dbo.JUMP_portfolio_holdings h
        WHERE h.ID_PI_FONDS = :pid AND h.DATE_INVENTAIRE = (
            SELECT MAX(i.DATE_INVENTAIRE) FROM dbo.JUMP_portfolio_holdings i
            WHERE i.ID_PI_FONDS = :pid AND i.DATE_INVENTAIRE <= :as_of)""",
}

EN_VALUES = {
    "oui": "Yes", "non": "No", "quotidienne": "Daily", "hebdomadaire": "Weekly", "mensuelle": "Monthly",
    "capitalisation": "Accumulation", "distribution": "Distribution", "opcvm": "UCITS", "fia": "AIF",
    "chaque jour ouvre": "Every business day", "tous souscripteurs": "All investors",
    "institutionnel": "Institutional", "actions": "Equities", "obligations": "Bonds", "monetaire": "Money market",
    "diversifie": "Multi-asset", "liquidites": "Cash", "zone euro": "Eurozone", "monde": "Global",
}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    try:
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or (isinstance(value, str) and not value.strip())


def as_percent(value: Any) -> float | None:
    """Taux Product Info : une valeur ≤ 0,05 est lue comme une fraction (0,015 → 1,5 %). Unité À CONFIRMER."""
    number = _num(value)
    if number is None:
        return None
    return number * 100 if 0 < abs(number) <= 0.05 else number


class FactValues:
    """Valeurs brutes des faits pour un fonds (pi_productid) et une part (ISIN), à une date d'arrêté."""

    def __init__(self, data: DataAccess, pid: str | None, isin: str | None, as_of: str):
        self.data, self.pid, self.isin, self.as_of = data, pid, isin, as_of
        self._rows: dict[str, dict[str, Any] | None] = {}
        self._jump: dict[str, Any] = {}
        self.errors: list[str] = []

    def _row(self, table: str, columns: list[str]) -> dict[str, Any] | None:
        if table in self._rows:
            return self._rows[table]
        key, value = ("pi_productid", self.pid) if table == PRODUCT else ("ISIN_Code", self.isin)
        if not value:
            self._rows[table] = None
            return None
        cols = ", ".join(f"t.{c}" for c in sorted(set(columns)))
        try:
            frame = self.data.query(f"SELECT TOP 1 {cols} FROM dbo.{table} t WHERE t.{key} = :k", {"k": value})
            self._rows[table] = frame.iloc[0].to_dict() if not frame.empty else None
        except DataError as error:
            self.errors.append(f"{table} : {error} {error.hint}")
            self._rows[table] = None
        return self._rows[table]

    def _jump_query(self, name: str):
        if name in self._jump:
            return self._jump[name]
        params = {"pid": self.pid, "isin": self.isin, "as_of": self.as_of}
        try:
            frame = self.data.query(JUMP_QUERIES[name], params)
        except DataError as error:
            self.errors.append(f"JUMP {name} : {error}")
            frame = None
        self._jump[name] = frame
        return frame

    def preload(self, facts: list[Fact]) -> None:
        for table in (PRODUCT, SHARE):
            cols = [f.column for f in facts if f.table == table and not f.problems]
            if cols:
                self._row(table, cols)

    def raw(self, fact: Fact) -> Any:
        if fact.problems:
            return None
        if fact.table:
            row = self._rows.get(fact.table) if fact.table in self._rows else self._row(fact.table, [fact.column])
            return None if row is None else row.get(fact.column)
        kind = fact.source.split(":", 1)[1]
        if kind in {"fund_aum", "share_aum", "share_classes"}:
            frame = self._jump_query(kind)
            if frame is None or frame.empty:
                return None
            return frame.iloc[0].get(fact.jump_field)
        holdings = self._jump_query("holdings")
        if holdings is None or holdings.empty:
            return None
        return _holdings_fact(kind, holdings)


def _weights(frame) -> Any:
    weights = frame["POIDS_LIGNE_EXPO"].map(_num).fillna(0.0)
    # Unité de POIDS_LIGNE_EXPO À CONFIRMER : fraction si la somme est proche de 1.
    return weights * 100 if 0 < weights.abs().sum() <= 1.5 else weights


def _holdings_fact(kind: str, frame) -> Any:
    frame = frame.copy()
    frame["poids"] = _weights(frame)
    securities = frame[frame["TYPE_HOLDING"].fillna("").str.upper() != "CASH"]
    if kind == "holdings_count":
        return int(len(securities))
    top = securities.sort_values("poids", ascending=False).head(10)
    if kind == "top10":
        return round(float(top["poids"].sum()), 2)
    if kind == "top10_list":
        return [(str(r.NOM_INSTRUMENT), float(r.poids)) for r in top.itertuples()]
    column = {"allocation_asset": "CLASSE_ACTIF", "allocation_currency": "DEVISE_INSTRUMENT"}[kind]
    grouped = frame.groupby(frame[column].fillna("Autres"))["poids"].sum().sort_values(ascending=False)
    return [(str(k), float(v)) for k, v in grouped.items() if abs(v) >= 0.05]


# --------------------------------------------------------------------------- mise en forme
UNIT_PATTERNS = [
    (re.compile(r"\b(?:md|mds|mrd|bn|bln|billions?|milliards?)\b|\(\s*(?:bn|md)\s*(?:€|eur|usd|\$)?\s*\)"), 1e9, {"fr": " Md", "en": " bn"}),
    (re.compile(r"\b(?:m€|meur|musd|m\$|mio|mn|mln|millions?|en m|in m)\b|\(\s*m\s*(?:€|eur|usd|\$)?\s*\)|€\s?m\b|eur\s?m\b|\bm\s?(?:€|eur)\b"), 1e6, {"fr": " M", "en": " m"}),
    (re.compile(r"\b(?:k€|keur|milliers|thousands?)\b"), 1e3, {"fr": " k", "en": " k"}),
]


def detect_scale(question_norm: str) -> tuple[float, str]:
    for pattern, scale, _ in UNIT_PATTERNS:
        if pattern.search(question_norm):
            return scale, ""
    return 1.0, ""


def fmt_number(value: float, decimals: int, lang: str) -> str:
    text = f"{value:,.{decimals}f}"
    if lang == "fr":
        text = text.replace(",", " ").replace(".", ",")
    return text


def translate(value: str, lang: str) -> str:
    if lang != "en":
        return value
    value = re.sub(r"\bJ\s*([+-])\s*(\d)", r"D\1\2", value)  # J+2 → D+2
    return EN_VALUES.get(norm(value), value)


def format_value(fact: Fact, raw: Any, lang: str = "fr", question_norm: str = "") -> tuple[str | None, Any]:
    """(texte affiché, valeur à écrire) ; (None, None) si aucune valeur."""
    if isinstance(raw, list):
        if not raw:
            return None, None
        if fact.id == "jump.top10_list":
            text = "; ".join(f"{name} ({fmt_number(w, 2, lang)} %)" for name, w in raw)
        else:
            text = "; ".join(f"{translate(name, lang)} {fmt_number(w, 1, lang)} %" for name, w in raw)
        return text, text
    if _empty(raw):
        return None, None
    if fact.format == "date":
        d = _date(raw)
        return (d.strftime("%d/%m/%Y"), d) if d else (str(raw), str(raw))
    if fact.format == "percent":
        number = as_percent(raw)
        if number is None:
            return str(raw), str(raw)
        if "bp" in question_norm.split() or "bps" in question_norm.split() or "point de base" in question_norm:
            return f"{fmt_number(number * 100, 0, lang)} bp", round(number * 100)
        wants_number = "%" in question_norm
        text = fmt_number(number, 2, lang) + ("" if wants_number else " %")
        return text, (round(number, 4) if wants_number else text)
    if fact.format in {"amount", "number"}:
        number = _num(raw)
        if number is None:
            return str(raw), str(raw)
        if fact.format == "amount":
            scale, _ = detect_scale(question_norm)
            scaled = number / scale
            decimals = 0 if scale == 1 else 1
            return fmt_number(scaled, decimals, lang), round(scaled, decimals)
        decimals = 0 if float(number).is_integer() else 2
        return fmt_number(number, decimals, lang), (int(number) if decimals == 0 else round(number, 4))
    if fact.format == "boolean":
        text = str(raw).strip()
        truthy = norm(text) in {"oui", "yes", "true", "1", "vrai"}
        falsy = norm(text) in {"non", "no", "false", "0", "faux"}
        if truthy or falsy:
            text = ("Oui" if truthy else "Non") if lang == "fr" else ("Yes" if truthy else "No")
        return text, text
    if fact.format == "time":
        text = str(raw).strip()
        return text, text
    text = translate(str(raw).strip(), lang)
    return text, text
