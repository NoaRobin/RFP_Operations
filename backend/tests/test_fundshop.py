"""Documents des fonds : adresse directe depuis Product Info, mémoire, vérification de l'ISIN, liste, mois relatifs.
Site simulé, identifiants et ISIN fictifs (QZ…)."""
from datetime import date
from pathlib import Path

import httpx
from openpyxl import Workbook

from pdfgen import kid_lines, make_pdf

SHARE_GUID = "11111111-2222-3333-4444-555555555555"
PRODUCT_GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISIN = "QZ2228LUXT99"


class FakeData:
    """Product Info minimal : la part et le fonds avec leurs GUID Dynamics."""
    mode = "mock"

    def query(self, sql, params):
        import pandas as pd

        if "PI_OUT_Share" in sql:
            return pd.DataFrame([{"pi_shareid": SHARE_GUID, "Id": "not-a-guid", "ProductID": "P1", "Share_Name": "Fonds Fictif C EUR"}])
        return pd.DataFrame([{"pi_productid": PRODUCT_GUID, "Id": None, "Product_Global_ID": None, "Product_Name": "Fonds Fictif"}])


def fake_site(served: dict[str, bytes], calls: list[str]):
    def get(url):
        calls.append(url)
        if url in served:
            return httpx.Response(200, content=served[url], headers={"content-type": "application/pdf"})
        return httpx.Response(404, text="<!doctype html>", headers={"content-type": "text/html"})
    return get


def test_period_specs_support_relative_months():
    from merlin.fundshop.period import resolve

    today = date(2026, 10, 13)
    assert (resolve("M-1", today).month, resolve("M-1", today).year) == (9, 2026)
    assert resolve("M-10", today).year == 2025 and resolve("M-10", today).month == 12
    assert resolve("juillet 2026", today).month == 7 and resolve("2026-07", today).month == 7
    assert resolve("mois précédent", today).month == 9 and resolve("", today).month is None


def test_direct_address_from_product_info_is_learned(tmp_path):
    from merlin.fundshop.catalog import doc_type
    from merlin.fundshop.memory import Memory
    from merlin.fundshop.period import Period
    from merlin.fundshop.resolver import Resolver

    base = "https://docs.test"
    kid = make_pdf(kid_lines(ISIN, "Fonds Fictif C EUR"))
    report = make_pdf([[f"Reporting mensuel fictif - ISIN {ISIN}"] + [f"Ligne de commentaire fictive numéro {n}" for n in range(30)]])
    served = {f"{base}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid, f"{base}/REPM_{SHARE_GUID}_FR_FR_20260731.pdf": report,
              f"{base}/PROS_{PRODUCT_GUID}_FR_FR.pdf": make_pdf([["Prospectus fictif"] + [f"Article {n} fictif" for n in range(40)]])}
    calls: list[str] = []
    mem = Memory(tmp_path / "learned.json")
    res = Resolver(FakeData(), mem, get=fake_site(served, calls), docs_base=base, site_base="https://site.test/")
    ident = res.identity(ISIN)
    found = res.find(ident, doc_type("dic"), Period())
    assert found.strategy == "construite" and found.url.endswith(f"DIPR_{SHARE_GUID}_FR_FR.pdf")
    assert mem.data["id_column"]["share"] == "PI_OUT_Share.pi_shareid"  # la bonne colonne est apprise
    assert res.find(ident, doc_type("prospectus"), Period()).url.endswith(f"PROS_{PRODUCT_GUID}_FR_FR.pdf")
    rep = res.find(ident, doc_type("reporting mensuel"), Period(7, 2026))
    assert rep.url.endswith("_20260731.pdf")
    calls.clear()
    res2 = Resolver(None, mem, get=fake_site(served, calls), docs_base=base)  # sans Fabric : la mémoire suffit
    assert res2.find(res2.identity(ISIN), doc_type("dic"), Period()).strategy == "apprise" and len(calls) == 1


def test_pdf_of_another_share_is_refused(tmp_path):
    from merlin.fundshop.catalog import doc_type
    from merlin.fundshop.memory import Memory
    from merlin.fundshop.period import Period
    from merlin.fundshop.resolver import DocumentNotFound, Resolver

    base = "https://docs.test"
    served = {f"{base}/DIPR_{SHARE_GUID}_FR_FR.pdf": make_pdf(kid_lines("QZYM908XINV7", "Autre part"))}
    res = Resolver(FakeData(), Memory(tmp_path / "m.json"), get=fake_site(served, []), docs_base=base, site_base="https://site.test/")
    try:
        res.find(res.identity(ISIN), doc_type("dic"), Period())
        raise AssertionError("un DIC d'une autre part ne doit jamais être accepté")
    except DocumentNotFound:
        pass


def test_shopping_list_from_excel_and_run(tmp_path):
    from merlin.fundshop.memory import Memory
    from merlin.fundshop.resolver import Resolver
    from merlin.fundshop.runner import run_list
    from merlin.fundshop.shopping import from_excel

    wb = Workbook()
    ws = wb.active
    ws.title = "Liste de courses"
    ws.append(["Fonds", "Part", "ISIN", "Type de document", "Mois demandé", "Année", "Nom final", "Écraser"])
    ws.append(["Fonds Fictif", "C EUR", ISIN, "DIC PRIIPS", None, None, "Fonds Fictif - DIC", None])
    ws.append(["Fonds Fictif", "C EUR", ISIN, "Reporting mensuel", "juillet 2026", 2026, "", None])
    ws.append(["Fonds Fictif", "C EUR", "PAS-UN-ISIN", "DIC", None, None, "", None])
    path = tmp_path / "liste.xlsx"
    wb.save(path)
    items, errors = from_excel(path)
    assert len(items) == 2 and len(errors) == 1 and "ISIN invalide" in errors[0]
    assert items[1].target_name() == "Rothschild & Co AM - Fonds Fictif - Reporting 07-2026.pdf"

    base = "https://docs.test"
    served = {f"{base}/DIPR_{SHARE_GUID}_FR_FR.pdf": make_pdf(kid_lines(ISIN, "Fonds Fictif C EUR"))}
    res = Resolver(FakeData(), Memory(tmp_path / "m.json"), get=fake_site(served, []), docs_base=base, site_base="https://site.test/")
    dest = tmp_path / "docs"
    results = run_list(items, res, dest)
    by_kind = {r.kind: r for r in results}
    assert by_kind["DIC"].status == "OK" and (dest / "Fonds Fictif - DIC.pdf").read_bytes().startswith(b"%PDF")
    assert by_kind["Reporting mensuel"].status == "ÉCHEC" and by_kind["Reporting mensuel"].detail
    again = run_list(items, res, dest)
    assert {r.kind: r.status for r in again}["DIC"] == "DÉJÀ PRÉSENT"  # jamais d'écrasement sans demande


def test_memory_seeds_from_historical_results(tmp_path):
    from merlin.fundshop.memory import Memory

    csv = tmp_path / "resultats.csv"
    csv.write_text("ligne;fonds;isin;type_document;statut;url_source\n"
                   f"2;Fonds Fictif;{ISIN};dic;OK;https://docs.am.eu.rothschildandco.com/DIPR_{SHARE_GUID}_FR_FR.pdf\n"
                   f"3;Fonds Fictif;{ISIN};prospectus;OK;https://docs.am.eu.rothschildandco.com/PROS_{PRODUCT_GUID}_FR_FR.pdf\n"
                   f"4;Fonds Fictif;{ISIN};prospectus;ÉCHEC;\n", encoding="utf-8-sig")
    mem = Memory(tmp_path / "m.json")
    assert mem.seed_from_csv(csv) == 2
    assert mem.guid(ISIN, "share") == SHARE_GUID and mem.guid(ISIN, "product") == PRODUCT_GUID


def test_fundshop_api_roundtrip(client):
    r = client.put("/api/fundshop", json=[{"isin": ISIN, "kind": "Reporting mensuel", "fund": "Fonds Fictif", "month": "M-1"}]).json()
    assert r["items"][0]["kind"] == "reporting mensuel" and r["items"][0]["period_label"]
    assert any(t["key"] == "dic" for t in r["types"])
    bad = client.put("/api/fundshop", json=[{"isin": ISIN, "kind": "Inconnu"}])
    assert bad.status_code == 400
