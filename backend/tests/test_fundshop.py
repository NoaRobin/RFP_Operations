"""Documents des fonds : adresse directe, mémoire, lien collé, explications en clair, liste Excel vierge, mois relatifs.
Réseau simulé, identifiants et ISIN fictifs (QZ…)."""
import io
from datetime import date

from openpyxl import Workbook, load_workbook

from pdfgen import kid_lines, make_pdf

SHARE_GUID = "11111111-2222-3333-4444-555555555555"
PRODUCT_GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISIN = "QZ2228LUXT99"
OTHER = "QZYM908XINV7"
BASE = "https://docs.test"


class FakeData:
    """Product Info minimal : la part et le fonds avec leurs GUID Dynamics."""
    mode = "mock"

    def query(self, sql, params):
        import pandas as pd

        if "PI_OUT_Share" in sql:
            return pd.DataFrame([{"pi_shareid": SHARE_GUID, "Id": "not-a-guid", "ProductID": "P1", "Share_Name": "Fonds Fictif C EUR"}])
        return pd.DataFrame([{"pi_productid": PRODUCT_GUID, "Id": None, "Product_Global_ID": None, "Product_Name": "Fonds Fictif"}])


class FakeNet:
    """Site simulé : une table d'adresses ; `down` simule un réseau bloqué."""
    active = "test"

    def __init__(self, served: dict[str, bytes], down: str | None = None):
        self.served, self.down, self.calls = served, down, []

    def get(self, url):
        from merlin.fundshop.net import NetError, Reply

        self.calls.append(url)
        if self.down:
            raise NetError(self.down, "simulé", "docs.test")
        if url in self.served:
            body = self.served[url]
            return Reply(200, body, "application/pdf" if body.startswith(b"%PDF") else "text/html", url)
        return Reply(404, b"<!doctype html>", "text/html", url)

    def check(self, url):
        try:
            return True, None, self.get(url).status
        except Exception as error:  # noqa: BLE001
            return False, error, 0


def resolver(tmp_path, served, data=FakeData(), down=None):
    from merlin.fundshop.memory import Memory
    from merlin.fundshop.resolver import Resolver

    return Resolver(data, Memory(tmp_path / "learned.json"), net=FakeNet(served, down), docs_base=BASE, site_base="https://site.test/fonds/")


def kid(isin=ISIN):
    return make_pdf(kid_lines(isin, "Fonds Fictif C EUR"))


def test_relative_months_are_kept_for_the_loop():
    from merlin.fundshop.period import month_spec, resolve

    today = date(2026, 10, 13)
    assert (resolve("M-1", today).month, resolve("M-1", today).year) == (9, 2026)
    assert resolve("M-10", today).year == 2025 and resolve("il y a 2 mois", today).month == 8
    assert month_spec("Mois précédent") == "M-1" and month_spec("Il y a 3 mois") == "M-3"
    assert month_spec("juillet 2026") == "2026-07" and month_spec("juillet", 2025) == "2025-07"


def test_direct_address_from_product_info_is_learned(tmp_path):
    from merlin.fundshop.catalog import doc_type
    from merlin.fundshop.period import Period

    report = make_pdf([[f"Reporting mensuel fictif - ISIN {ISIN}"] + [f"Ligne fictive {n}" for n in range(30)]])
    served = {f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid(), f"{BASE}/REPM_{SHARE_GUID}_FR_FR_20260731.pdf": report,
              f"{BASE}/PROS_{PRODUCT_GUID}_FR_FR.pdf": make_pdf([["Prospectus fictif"] + [f"Article {n}" for n in range(40)]])}
    res = resolver(tmp_path, served)
    ident = res.identity(ISIN)
    found = res.find(ident, doc_type("dic"), Period())
    assert found.strategy == "construite" and found.url.endswith(f"DIPR_{SHARE_GUID}_FR_FR.pdf")
    assert res.memory.data["id_column"]["share"] == "PI_OUT_Share.pi_shareid"  # la bonne colonne est apprise
    assert res.find(ident, doc_type("prospectus"), Period()).url.endswith(f"PROS_{PRODUCT_GUID}_FR_FR.pdf")
    assert res.find(ident, doc_type("reporting mensuel"), Period(7, 2026)).url.endswith("_20260731.pdf")
    res2 = resolver(tmp_path, served, data=None)  # sans Fabric : la mémoire suffit
    res2.memory = res.memory
    assert res2.find(res2.identity(ISIN), doc_type("dic"), Period()).strategy == "mémorisée"


def test_failures_are_explained_in_plain_words(tmp_path):
    from merlin.fundshop.catalog import doc_type
    from merlin.fundshop.period import Period
    from merlin.fundshop.problems import DocumentProblem

    def why(res, kind="dic", period=Period()):
        try:
            res.find(res.identity(ISIN, "Fonds Fictif"), doc_type(kind), period)
        except DocumentProblem as error:
            return error.problem
        raise AssertionError("aurait dû échouer")

    # réseau bloqué : on le dit, avec quoi faire
    p = why(resolver(tmp_path, {}, down="proxy"))
    assert p.code == "proxy" and "Edge" in p.fix
    # aucune adresse connue (rien ne répond) : on explique comment donner le lien une fois
    p = why(resolver(tmp_path, {}, data=None))
    assert p.code == "adresse-inconnue" and "J'ai le lien" in p.fix and p.link.startswith("https://site.test/fonds/fonds-fictif")
    # PDF d'une autre part : refusé, et son adresse est retenue pour l'autre part
    res = resolver(tmp_path, {f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid(OTHER)})
    p = why(res)
    assert p.code == "autre-part" and OTHER in p.why and res.memory.guid(OTHER, "share") == SHARE_GUID
    # adresse connue mais mois pas encore publié : « pas sur le site » + quand réessayer
    res = resolver(tmp_path, {f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid()})
    res.find(res.identity(ISIN), doc_type("dic"), Period())
    p = why(res, "reporting mensuel", Period(9, 2026))
    assert p.code == "absent" and "septembre 2026" in p.title and "mois suivant" in p.fix
    # mois manquant
    assert why(res, "reporting mensuel", Period()).code == "mois"


def test_pasted_link_teaches_the_whole_share(tmp_path):
    from merlin.fundshop.catalog import doc_type
    from merlin.fundshop.period import Period

    report = make_pdf([[f"Reporting fictif {ISIN}"] + [f"Ligne {n}" for n in range(30)]])
    served = {f"{BASE}/REPM_{SHARE_GUID}_FR_FR_20260630.pdf": report, f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid()}
    res = resolver(tmp_path, served, data=None)
    msg = res.learn_link(ISIN, f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf")
    assert "cette part" in msg
    assert res.find(res.identity(ISIN), doc_type("reporting mensuel"), Period(6, 2026)).strategy == "mémorisée"
    # le lien d'un DIC d'une autre part est refusé, avec la raison
    res2 = resolver(tmp_path, {f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid(OTHER)}, data=None)
    try:
        res2.learn_link(ISIN, f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf")
        raise AssertionError("lien d'une autre part accepté")
    except ValueError as error:
        assert OTHER in str(error)
    assert "page du fonds" in res.learn_link(ISIN, "https://site.test/fonds/fonds-fictif/").lower()


def test_blank_template_roundtrip_and_run(tmp_path):
    from merlin.fundshop.runner import precheck, run_list
    from merlin.fundshop.shopping import from_excel
    from merlin.fundshop.template import build

    directory = [{"name": "Fonds Fictif", "shares": [{"isin": ISIN, "name": "C EUR"}, {"isin": OTHER, "name": "I EUR"}]}]
    wb = load_workbook(io.BytesIO(build(directory)))
    ws = wb["Liste de courses"]
    assert [c.value for c in ws[1]][:4] == ["Part (choisir dans la liste)", "ISIN", "Document", "Mois"]
    assert wb["Parts"].max_row == 3 and ws.data_validations.dataValidation
    ws["A2"], ws["C2"] = f"Fonds Fictif · C EUR ({ISIN})", "DIC"
    ws["A3"], ws["C3"], ws["D3"] = f"Fonds Fictif · C EUR ({ISIN})", "Reporting mensuel", "Mois précédent"
    ws["B4"], ws["C4"] = "PAS-UN-ISIN", "DIC"
    path = tmp_path / "liste.xlsx"
    wb.save(path)
    items, errors = from_excel(path)
    assert len(items) == 2 and items[0].fund == "Fonds Fictif" and items[0].part == "C EUR"
    assert items[1].month == "M-1"  # le relatif est gardé : la liste resservira chaque mois
    assert len(errors) == 1 and "Ligne 4" in errors[0]

    res = resolver(tmp_path, {f"{BASE}/DIPR_{SHARE_GUID}_FR_FR.pdf": kid()})
    dest = tmp_path / "docs"
    assert precheck(res, dest) is None
    results = {r.kind: r for r in run_list(items, res, dest)}
    assert results["DIC"].status == "OK" and results["DIC"].title == "Téléchargé"
    assert results["Reporting mensuel"].status == "ÉCHEC" and results["Reporting mensuel"].fix
    again = {r.kind: r for r in run_list(items, res, dest)}
    assert again["DIC"].status == "DÉJÀ PRÉSENT" and "Remplacer" in again["DIC"].fix  # jamais d'écrasement sans demande


def test_blocked_network_gives_one_clear_reason(tmp_path):
    from merlin.fundshop.runner import precheck, run_list
    from merlin.fundshop.shopping import Item

    res = resolver(tmp_path, {}, down="certificat")
    blocked = precheck(res, tmp_path / "docs")
    assert blocked.code == "certificat" and "run.bat" in blocked.fix
    out = run_list([Item(isin=ISIN, kind="dic")], res, tmp_path / "docs", blocked=blocked)
    assert out[0].code == "certificat" and out[0].status == "ÉCHEC"


def test_old_shopping_list_format_still_reads(tmp_path):
    from merlin.fundshop.shopping import from_excel

    wb = Workbook()
    ws = wb.active
    ws.title = "Liste de courses"
    ws.append(["Fonds", "Part", "ISIN", "Type de document", "Mois demandé", "Année", "Nom final", "Écraser"])
    ws.append(["Fonds Fictif", "C EUR", ISIN, "Reporting mensuel", "juillet", 2026, "", "Oui"])
    path = tmp_path / "old.xlsx"
    wb.save(path)
    items, errors = from_excel(path)
    assert not errors and items[0].month == "2026-07" and items[0].overwrite


def test_memory_seeds_from_historical_results(tmp_path):
    from merlin.fundshop.memory import Memory

    csv = tmp_path / "resultats.csv"
    csv.write_text("ligne;fonds;isin;type_document;statut;url_source\n"
                   f"2;Fonds Fictif;{ISIN};dic;OK;https://docs.example/DIPR_{SHARE_GUID}_FR_FR.pdf\n"
                   f"3;Fonds Fictif;{ISIN};prospectus;OK;https://docs.example/PROS_{PRODUCT_GUID}_FR_FR.pdf\n"
                   f"4;Fonds Fictif;{ISIN};prospectus;ÉCHEC;\n", encoding="utf-8-sig")
    mem = Memory(tmp_path / "m.json")
    assert mem.seed_from_csv(csv) == 2
    assert mem.guid(ISIN, "share") == SHARE_GUID and mem.guid(ISIN, "product") == PRODUCT_GUID


def test_fundshop_api(client):
    r = client.put("/api/fundshop", json=[{"isin": ISIN, "kind": "Reporting mensuel", "fund": "Fonds Fictif", "month": "M-1"}]).json()
    assert r["items"][0]["kind"] == "reporting mensuel" and r["items"][0]["period_label"]
    assert client.put("/api/fundshop", json=[{"isin": ISIN, "kind": "Inconnu"}]).status_code == 400
    blank = client.get("/api/fundshop/template.xlsx")
    assert blank.status_code == 200 and load_workbook(io.BytesIO(blank.content))["Parts"].max_row > 1
    mine = load_workbook(io.BytesIO(client.get("/api/fundshop/template.xlsx?with_list=true").content))["Liste de courses"]
    assert mine["C2"].value == "Reporting mensuel" and mine["D2"].value == "Mois précédent"
    bad = client.post("/api/fundshop/link", json={"isin": ISIN, "url": "https://ailleurs.example/x"})
    assert bad.status_code == 400 and "ni un PDF" in bad.json()["detail"]["message"]
