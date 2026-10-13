"""Période d'un document : mois précis, ou relative (« mois précédent », « dernier disponible ») pour les envois en boucle."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime

from ..rfi.ontology import norm

MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


@dataclass(frozen=True)
class Period:
    month: int | None = None
    year: int | None = None

    @property
    def label(self) -> str:
        return f"{MONTHS_FR[self.month - 1]} {self.year}" if self.month and self.year else "—"

    @property
    def mm_yyyy(self) -> str:
        return f"{self.month:02d}-{self.year}" if self.month and self.year else ""

    @property
    def month_end(self) -> date | None:
        if not (self.month and self.year):
            return None
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])


def shift(today: date, months_back: int) -> Period:
    m = today.month - months_back
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    return Period(m, y)


def resolve(spec: object, today: date | None = None) -> Period:
    """« 2026-07 », « 07/2026 », « juillet 2026 », date Excel, « M-1 », « mois précédent », « dernier » (= M-1)."""
    today = today or date.today()
    if spec is None or norm(spec) in {"", "nan", "none", "nat"}:
        return Period()
    if isinstance(spec, (datetime, date)):
        return Period(spec.month, spec.year)
    text = norm(spec)
    m = re.fullmatch(r"m\s*-\s*(\d{1,2})", text)
    if m:
        return shift(today, int(m.group(1)))
    if text in {"mois precedent", "dernier", "dernier disponible", "derniere", "previous month", "latest"}:
        return shift(today, 1)
    m = re.match(r"(\d{4})-(\d{1,2})", text) or None
    if m:
        return Period(int(m.group(2)), int(m.group(1)))
    m = re.match(r"(\d{1,2})[/.-](\d{4})", text)
    if m:
        return Period(int(m.group(1)), int(m.group(2)))
    m = re.match(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
    if m:
        return Period(int(m.group(2)), int(m.group(3)))
    for i, name in enumerate(MONTHS, start=1):
        if text.startswith(name[:4]):
            y = re.search(r"(20\d{2})", text) or re.search(r"(\d{2})$", text)
            year = int(y.group(1)) if y and len(y.group(1)) == 4 else (2000 + int(y.group(1)) if y else today.year)
            return Period(i, year)
    raise ValueError(f"Mois non reconnu : {spec}")


def describe(spec: object) -> str:
    text = norm(spec)
    if re.fullmatch(r"m\s*-\s*\d{1,2}", text) or text in {"mois precedent", "dernier", "dernier disponible"}:
        return {"m-1": "mois précédent", "dernier": "mois précédent"}.get(text.replace(" ", ""), str(spec))
    return str(spec or "")
