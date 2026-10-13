"""Période OMNI : mois, trimestre et date d'arrêté réelle (dernière date d'inventaire JUMP du mois)."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from ..data.access import DataAccess, DataError
from ..rfi.values import to_date

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


@dataclass(frozen=True)
class OmniPeriod:
    month: int
    year: int
    closing: date
    closing_source: str  # « JUMP » ou « calcul (dernier jour ouvré) »

    @property
    def quarter(self) -> int:
        return (self.month - 1) // 3 + 1

    @property
    def yyyymmdd(self) -> str:
        return self.closing.strftime("%Y%m%d")

    @property
    def label(self) -> str:
        return f"{MONTHS_FR[self.month - 1]} {self.year}"

    def previous(self) -> tuple[int, int]:
        return (12, self.year - 1) if self.month == 1 else (self.month - 1, self.year)


def last_weekday(year: int, month: int) -> date:
    d = date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def previous_month(today: date) -> tuple[int, int]:
    first = today.replace(day=1) - timedelta(days=1)
    return first.month, first.year


def build(data: DataAccess | None, month: int | None, year: int | None, today: date | None = None) -> OmniPeriod:
    if (month is None) != (year is None):
        raise ValueError("Mois et année vont ensemble.")
    if month is None:
        month, year = previous_month(today or date.today())
    if not 1 <= int(month) <= 12:
        raise ValueError("Le mois doit être compris entre 1 et 12.")
    month, year = int(month), int(year)
    first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if data is not None:
        try:
            frame = data.query("SELECT MAX(h.DATE_INVENTAIRE) AS d FROM dbo.JUMP_portfolio_holdings h "
                               "WHERE h.DATE_INVENTAIRE >= :first AND h.DATE_INVENTAIRE <= :last",
                               {"first": first.isoformat(), "last": last.isoformat()})
            d = to_date(frame.iloc[0]["d"]) if len(frame) else None
            if d is not None:
                return OmniPeriod(month, year, d, "JUMP")
        except DataError:
            pass
    return OmniPeriod(month, year, last_weekday(year, month), "calcul (dernier jour ouvré)")
