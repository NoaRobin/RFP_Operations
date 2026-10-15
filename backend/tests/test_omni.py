"""OMNI mensuel : vraie date d'inventaire, Holdings depuis Fabric au format du mois précédent, performances déposées,
rangement trimestriel sans écrasement, contrôle de la NET contre les VL JUMP. Données de démonstration uniquement."""
import time
from datetime import date

import pandas as pd

from test_api import wait_for


def _mock_month(data):
    d = data.query("SELECT MAX(h.DATE_INVENTAIRE) AS d FROM dbo.JUMP_portfolio_holdings h", {}).iloc[0]["d"]
    d = pd.Timestamp(d).date()
    return d.month, d.year


def test_period_uses_real_jump_inventory_date(client):
    from merlin.omni.period import build, last_weekday
    from merlin.state import get_state

    data = get_state().data
    month, year = _mock_month(data)
    p = build(data, month, year)
    assert p.closing_source == "JUMP" and p.closing.month == month
    assert build(None, 5, 2026).closing == last_weekday(2026, 5) == date(2026, 5, 29)


def test_headers_of_previous_month_are_mapped_to_fabric(client):
    from merlin.omni.holdings import map_headers
    from merlin.state import get_state

    columns = [c.name for c in get_state().data.catalog.table("JUMP_portfolio_holdings").columns]
    mapping, unmapped = map_headers(["Fonds", "Code ISIN", "Instrument", "Poids", "Colonne maison"], columns)
    assert mapping["Code ISIN"] == "CODE_ISIN_INSTRUMENT" and mapping["Poids"] == "POIDS_LIGNE_EXPO" and unmapped == ["Colonne maison"]


def test_omni_run_end_to_end(client, tmp_path, monkeypatch):
    from merlin.config import get_settings
    from merlin.omni import performance as PF
    from merlin.omni.period import build
    from merlin.state import get_state

    data = get_state().data
    month, year = _mock_month(data)
    p = build(data, month, year)
    settings = get_settings()
    inbox = settings.data_dir / "omni" / "depot"
    inbox.mkdir(parents=True, exist_ok=True)
    isins = data.query("SELECT DISTINCT a.CODE_ISIN_PART FROM dbo.JUMP_portfolio_aum a", {})["CODE_ISIN_PART"].tolist()[:3]
    # NET « juste » : recalculée comme le contrôle ; GROSS : contenu quelconque
    from merlin.rfi import perf as P
    from merlin.rfi.understand import Period as UP

    rows = []
    for isin in isins:
        nav = P.nav_frame(data.query("SELECT a.DATE_VL, a.VL_UNITAIRE, a.DIVIDEND_AMOUNT, a.COEFFICIENT_OST, a.VL_BENCH, a.NOM_BENCH FROM dbo.JUMP_portfolio_aum a "
                                     "WHERE a.CODE_ISIN_PART = :i AND a.DATE_VL <= :d ORDER BY a.DATE_VL", {"i": isin, "d": p.closing.isoformat()}))
        rows.append({"ISIN": isin, "Perf": P.period_return(P.adjusted_index(nav), UP("months", 1), p.closing, annualize=False).value / 100})
    pd.DataFrame(rows).to_excel(inbox / f"Monthly perf NET of fees_{p.yyyymmdd}.xlsx", index=False)
    pd.DataFrame(rows).to_excel(inbox / f"Monthly perf GROSS of fees_{p.yyyymmdd}.xlsx", index=False)
    assert PF.kind_of("Monthly perf NET of fees_20260731.xlsx") == "net" and PF.kind_of("Perf GROSS 07-2026.xlsx") == "gross"

    run = client.post("/api/automations/omni_mensuel/run", json={"params": {"mois": month, "annee": year, "outlook": False}}).json()
    done = wait_for(client, run["id"], timeout=120)
    assert done["status"] == "success", [e for e in done["events"] if e["type"] == "log"][-5:]
    summary = next(e for e in done["events"] if e["type"] == "summary")
    assert summary["metrics"]["statut"] == "OK"
    root = settings.data_dir / "omni" / str(year) / f"Q{p.quarter} {year}"
    assert (root / "Holdings" / f"Holdings {month}_{year}.xlsx").exists()
    assert (root / "Performances" / f"Monthly perf NET of fees_{p.yyyymmdd}.xlsx").exists()
    logs = " ".join(e.get("message", "") for e in done["events"] if e["type"] == "log")
    assert "concorde" in logs

    again = wait_for(client, client.post("/api/automations/omni_mensuel/run", json={"params": {"mois": month, "annee": year, "outlook": False}}).json()["id"], 120)
    assert "non écrasé" in " ".join(e.get("message", "") for e in again["events"] if e["type"] == "log")  # jamais d'écrasement silencieux
