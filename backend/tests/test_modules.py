"""RFI, merge codes Qvidian et suivi d'activité (données fictives)."""
import io
import zipfile

import docx
from openpyxl import load_workbook


def test_rfi_xlsx_fills_same_workbook(client):
    doc = client.post("/api/rfi/demo/xlsx").json()
    suggestion = doc["suggestions"][0]
    assert suggestion["reason"].startswith("ISIN")
    body = {"pid": suggestion["pid"], "isin": suggestion["isin"]}
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()
    by_text = {q["text"]: q for q in analysis["questions"]}
    assert by_text["Forme juridique"]["status"] == "fill"
    assert by_text["Classification SFDR"]["fact"] == "fund.sfdr"
    assert by_text["Encours du fonds (en M€)"]["fact"] == "jump.fund_aum_eur"
    assert by_text["Nom du fonds"]["status"] == "existing"  # jamais écrasé par défaut
    assert any(q["status"] == "unmatched" and q["text"].startswith("Décrivez") for q in analysis["questions"])

    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body).json()
    assert generated["written"] >= 15
    content = client.get(generated["download"]).content
    original = client.get(f"/api/rfi/documents/{doc['id']}/original").content
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    answers = {ws.cell(r, 2).value: ws.cell(r, 3).value for r in range(4, ws.max_row + 1)}
    assert answers["Forme juridique"]
    assert ws.cell(5, 3).fill.fgColor.rgb.endswith("FFF2CC")  # mise en forme conservée
    # toutes les parties du fichier hors feuilles sont recopiées à l'identique
    zo, zn = zipfile.ZipFile(io.BytesIO(original)), zipfile.ZipFile(io.BytesIO(content))
    for name in zo.namelist():
        if not name.startswith("xl/worksheets/"):
            assert zo.read(name) == zn.read(name), name


def test_rfi_docx(client):
    doc = client.post("/api/rfi/demo/docx").json()
    s = doc["suggestions"][0]
    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json={"pid": s["pid"], "isin": s["isin"]}).json()
    d = docx.Document(io.BytesIO(client.get(generated["download"]).content))
    table = {row.cells[0].text: row.cells[1].text for row in d.tables[0].rows}
    assert table["Legal form"] and table["Number of holdings"].isdigit()
    texts = [p.text for p in d.paragraphs]
    assert any(t.startswith("Subscription cut-off time: ") and len(t) > 30 for t in texts)
    assert any("D+" in t for t in texts if t.startswith("Settlement period"))


def test_rfi_override_and_skip(client):
    doc = client.post("/api/rfi/demo/xlsx").json()
    s = doc["suggestions"][0]
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json={"pid": s["pid"], "isin": s["isin"]}).json()
    q = next(q for q in analysis["questions"] if q["status"] == "fill")
    again = client.post(f"/api/rfi/documents/{doc['id']}/answers",
                        json={"pid": s["pid"], "isin": s["isin"], "overrides": {q["id"]: None}}).json()
    assert next(x for x in again["questions"] if x["id"] == q["id"])["status"] == "skipped"


def test_mergecodes_demo(client):
    analysis = client.post("/api/mergecodes/demo").json()
    assert len(analysis["candidats"]) == 6
    decisions = [{"choix": "proposition", "proposition": 1}] * 5 + [{"choix": "ignorer"}]
    result = client.post(f"/api/mergecodes/documents/{analysis['id']}/appliquer", json={"decisions": decisions}).json()
    assert result["inseres"] == 5
    d = docx.Document(io.BytesIO(client.get(result["document_url"]).content))
    assert "<<XPINDUS_VLac>>" in "\n".join(p.text for p in d.paragraphs)
    assert client.get(result["rapport_url"]).status_code == 200


def test_suivi_mounted(client):
    assert client.get("/suivi/").status_code == 200
    assert client.get("/suivi/api/meta").json()["source"]["mode"] == "demo"


def test_fabric_status(client):
    status = client.get("/api/fabric").json()
    assert status["mode"] == "mock" and status["client"] == "mssql-python"
    bad = client.post("/api/fabric/connect", json={"server": "", "user": "x"})
    assert bad.status_code == 400
