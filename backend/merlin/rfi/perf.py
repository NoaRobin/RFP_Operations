"""Performances et risques d'une part, calculés à partir des VL JUMP.

Indice de performance repris d'App4everyone (rco/domain/analytics.py, adjusted_index) :
    r_t = (VL_t + dividende_t) × coefficient_OST_t / VL_{t−1} − 1
Dividendes réinvestis, opérations sur titres neutralisées. Une chaîne interrompue (rapport ≤ 0 ou non fini)
rend les mesures postérieures indisponibles : on ne fabrique jamais une performance.
Hypothèses JUMP À CONFIRMER (catalogue) : DIVIDEND_AMOUNT par part, COEFFICIENT_OST multiplicatif.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from .understand import Period

STALE_DAYS = 7  # au-delà, la dernière VL est jugée trop ancienne par rapport à la date d'arrêté


def _f(x: Any) -> float:
    if x is None or isinstance(x, bool):
        return float("nan")
    if isinstance(x, Decimal):
        return float(x) if x.is_finite() else float("nan")
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def nav_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Colonnes DATE_VL, VL_UNITAIRE, DIVIDEND_AMOUNT, COEFFICIENT_OST, VL_BENCH → série indexée par date."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "vl": frame["VL_UNITAIRE"].map(_f).to_numpy(),
        "div": frame["DIVIDEND_AMOUNT"].map(_f).to_numpy() if "DIVIDEND_AMOUNT" in frame else np.nan,
        "coef": frame["COEFFICIENT_OST"].map(_f).to_numpy() if "COEFFICIENT_OST" in frame else np.nan,
        "bench": frame["VL_BENCH"].map(_f).to_numpy() if "VL_BENCH" in frame else np.nan,
    }, index=pd.to_datetime(frame["DATE_VL"]).dt.normalize())
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[out["vl"].notna()]


def adjusted_index(nav: pd.DataFrame) -> pd.Series:
    vl = nav["vl"].to_numpy(dtype=float)
    div = np.nan_to_num(nav["div"].to_numpy(dtype=float), nan=0.0)
    coef = nav["coef"].to_numpy(dtype=float)
    coef = np.where(np.isnan(coef) | (coef == 0), 1.0, coef)
    prev = np.concatenate([[np.nan], vl[:-1]])
    prev[prev == 0.0] = np.nan
    ratio = (vl + div) * coef / prev
    if len(ratio):
        ratio[0] = 1.0
    bad = ~np.isfinite(ratio) | (ratio <= 0)
    stop = int(bad.argmax()) if bad.any() else len(ratio)
    out = np.full(len(ratio), np.nan)
    if stop:
        out[:stop] = 100 * np.cumprod(ratio[:stop])
    return pd.Series(out, index=nav.index)


def benchmark_index(nav: pd.DataFrame) -> pd.Series:
    b = nav["bench"].astype(float)
    return b.mask(b <= 0)


@dataclass
class PerfResult:
    value: float | None  # en % (points)
    start: date | None = None
    end: date | None = None
    note: str = ""  # raison d'indisponibilité ou précision
    stale: bool = False


def _start_date(period: Period, end: date) -> date | None:
    if period.kind == "ytd":
        return date(end.year - 1, 12, 31)
    if period.kind == "months":
        ts = pd.Timestamp(end) - pd.DateOffset(months=period.n)
        return ts.date()
    if period.kind == "years":
        ts = pd.Timestamp(end) - pd.DateOffset(years=period.n)
        return ts.date()
    if period.kind == "calendar" and period.year:
        return date(period.year - 1, 12, 31)
    return None


def _value_at(series: pd.Series, d: date) -> tuple[float | None, date | None]:
    sub = series[: pd.Timestamp(d)].dropna()
    if sub.empty:
        return None, None
    return float(sub.iloc[-1]), sub.index[-1].date()


def period_return(series: pd.Series, period: Period, as_of: date, annualize: bool) -> PerfResult:
    clean = series.dropna()
    if clean.empty:
        return PerfResult(None, note="aucune VL exploitable")
    first = clean.index[0].date()
    # Fin de période : date d'arrêté (ou 31/12 de l'année civile demandée)
    end_target = date(period.year, 12, 31) if period.kind == "calendar" and period.year else as_of
    # Une interruption de l'indice avant la fin rend la mesure indisponible.
    upto = series[: pd.Timestamp(end_target)]
    if upto.empty:
        return PerfResult(None, note="pas de VL à la date demandée")
    if np.isnan(upto.iloc[-1]):
        return PerfResult(None, note="indice de performance interrompu (rendement invalide)")
    v1, d1 = float(upto.iloc[-1]), upto.index[-1].date()
    stale = (end_target - d1).days > STALE_DAYS
    if period.kind == "inception":
        v0, d0 = float(clean.iloc[0]), first
    else:
        start = _start_date(period, end_target)
        if start is None:
            return PerfResult(None, note="période non reconnue")
        if first > start + timedelta(days=STALE_DAYS):
            return PerfResult(None, note=f"historique insuffisant (première VL le {first.strftime('%d/%m/%Y')})")
        v0, d0 = _value_at(series, start)
        if v0 is None:
            return PerfResult(None, note="pas de VL de départ")
    if not v0:
        return PerfResult(None, note="VL de départ nulle")
    r = v1 / v0 - 1
    if annualize:
        years = (d1 - d0).days / 365.25 if period.kind == "inception" else float(period.n if period.kind == "years" else period.n / 12)
        if years <= 1 or 1 + r <= 0:
            pass  # une période ≤ 1 an n'est jamais annualisée
        else:
            r = (1 + r) ** (1 / years) - 1
    return PerfResult(round(r * 100, 4), d0, d1, stale=stale)


def _window(series: pd.Series, as_of: date, years: float) -> pd.Series:
    start = pd.Timestamp(as_of) - pd.DateOffset(months=int(round(years * 12)))
    return series[start: pd.Timestamp(as_of)]


def _ppy(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 252.0
    gap = float(np.median(np.diff(index.values).astype("timedelta64[D]").astype(float)))
    return 52.0 if gap >= 5 else 252.0


def volatility(series: pd.Series, as_of: date, years: float) -> PerfResult:
    w = _window(series, as_of, years)
    if w.isna().any() or len(w) < 20:
        return PerfResult(None, note="historique insuffisant ou indice interrompu")
    first, last = w.index[0].date(), w.index[-1].date()
    if (first - (as_of - timedelta(days=int(365.25 * years)))).days > STALE_DAYS:
        return PerfResult(None, note=f"historique insuffisant (première VL le {first.strftime('%d/%m/%Y')})")
    r = w.pct_change().dropna().to_numpy()
    vol = float(np.std(r, ddof=1) * math.sqrt(_ppy(w.index)))
    return PerfResult(round(vol * 100, 4), first, last, stale=(as_of - last).days > STALE_DAYS)


def max_drawdown(series: pd.Series, as_of: date, years: float) -> PerfResult:
    w = _window(series, as_of, years)
    if w.isna().any() or len(w) < 20:
        return PerfResult(None, note="historique insuffisant ou indice interrompu")
    v = w.to_numpy()
    mdd = float((v / np.maximum.accumulate(v) - 1).min())
    return PerfResult(round(mdd * 100, 4), w.index[0].date(), w.index[-1].date())


def tracking_error(index: pd.Series, bench: pd.Series, as_of: date, years: float) -> PerfResult:
    w = _window(index, as_of, years)
    b = _window(bench, as_of, years).reindex(w.index).ffill()
    if w.isna().any() or b.isna().sum() > len(b) // 10 or len(w) < 20:
        return PerfResult(None, note="historique insuffisant (fonds ou indicateur)")
    diff = (w.pct_change() - b.pct_change()).dropna().to_numpy()
    if len(diff) < 20:
        return PerfResult(None, note="historique insuffisant")
    te = float(np.std(diff, ddof=1) * math.sqrt(_ppy(w.index)))
    return PerfResult(round(te * 100, 4), w.index[0].date(), w.index[-1].date())


__all__ = ["nav_frame", "adjusted_index", "benchmark_index", "period_return", "volatility", "max_drawdown",
           "tracking_error", "PerfResult"]
