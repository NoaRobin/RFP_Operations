"""Atelier Excel branché sur le modèle du compléteur RFI : ontologie, langues, plusieurs parts, classeur transposé."""
import hashlib
import io

from openpyxl import Workbook, load_workbook

from merlin.main import get_state
from test_api import wait_for


def _fund_with_shares(client, n=2):
    fund = next(f for f in client.get("/api/rfi/funds").json() if len(f["shares"]) >= n)
    return fund, fund["shares"][:n]


def _upload(client, wb, name):
    buffer = io.BytesIO()
    wb.save(buffer)
    return client.post("/api/atelier/workbooks", files={"file": (name, buffer.getvalue())}).json()


def test_ontology_concepts_are_offered_in_the_palette(client):
    items = client.get("/api/atelier/extractions").json()["extractions"]
    onto = [e for e in items if e["id"].startswith("onto:")]
    assert len(onto) >= 150 and all(e["key"] == "isin_part" for e in onto)
    assert any(e["id"] == "onto:part.frais_gestion_max" and e["healthy"] for e in onto)


def test_rows_of_isins_with_spanish_headers_use_the_rfi_model(client):
    fund, shares = _fund_with_shares(client, 2)
    wb = Workbook()
    ws = wb.active
    ws.title = "Clases"
    ws.append(["Código ISIN", "Nombre de la clase de participaciones", "Nombre del fondo", "Divisa de la clase"])
    for s in shares:
        ws.append([s["isin"], None, None, None])
    analysis = _upload(client, wb, "clases.xlsx")
    sheet = analysis["sheets"][0]
    assert sheet["orientation"] == "rows" and sheet["language"] == "es" and sheet["key"]["column"] == "A"
    proposed = {c["letter"]: c["proposed"] for c in sheet["columns"] if c["proposed"]}
    # extraction Fabric directe quand l'en-tête la désigne nettement, sinon concept de l'ontologie RFI
    assert proposed["B"] == "onto:part.nom" and proposed["C"] in {"onto:fonds.nom", "fonds.nom_fonds"}
    assert proposed["D"] in {"onto:part.devise", "aum.devise_vl"}
    recipe = {"name": "es", "workbook_id": analysis["id"], "sheet": "Clases", "header_row": 1, "key_column": "A",
              "key_type": "isin_part", "mappings": [{"column": k, "extraction": v} for k, v in proposed.items()]}
    preview = client.post("/api/atelier/preview", json=recipe).json()
    by_cell = {c["cell"]: c for c in preview["changes"]}
    for row, s in enumerate(shares, start=2):  # chaque ligne lit SA part, et le fonds de cette part
        assert by_cell[f"B{row}"]["after"] == s["name"] and by_cell[f"B{row}"]["status"] == "fill"
        assert by_cell[f"C{row}"]["after"] == fund["name"]
    assert preview["language"] == "es"


def test_transposed_sheet_one_column_per_isin(client):
    fund, shares = _fund_with_shares(client, 2)
    wb = Workbook()
    ws = wb.active
    ws.title = "Classi"
    ws.append(["Dati", *[s["isin"] for s in shares]])
    ws.append(["Nome della classe di quote", None, None])
    ws.append(["Nome del fondo", None, "valore già presente"])
    ws.append(["Commento libero del cliente", None, None])
    analysis = _upload(client, wb, "classi.xlsx")
    folder = get_state().store.workbook_dir(analysis["id"])
    original = next(folder.glob("original.*"))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    sheet = analysis["sheets"][0]
    assert sheet["orientation"] == "columns" and sheet["key_row"] == 1 and sheet["label_column"] == "A"
    assert sheet["isin_columns"] == ["B", "C"] and sheet["language"] == "it"
    proposed = {c["letter"]: c["proposed"] for c in sheet["columns"] if c["proposed"]}
    assert proposed["#2"] == "onto:part.nom" and proposed["#3"] in {"onto:fonds.nom", "fonds.nom_fonds"}
    assert "#4" not in proposed  # le commentaire libre n'est rattaché à rien
    recipe = {"name": "it", "workbook_id": analysis["id"], "sheet": "Classi", "header_row": 1, "orientation": "columns",
              "key_row": 1, "label_column": "A", "key_column": "A",
              "mappings": [{"column": k, "extraction": v} for k, v in proposed.items()]}
    preview = client.post("/api/atelier/preview", json=recipe).json()
    by_cell = {c["cell"]: c for c in preview["changes"]}
    assert by_cell["B2"]["after"] == shares[0]["name"] and by_cell["C2"]["after"] == shares[1]["name"]
    assert by_cell["B3"]["status"] == "fill" and by_cell["C3"]["status"] == "conflict"  # jamais écrasé sans le demander
    run = client.post("/api/atelier/run", json=recipe).json()
    assert wait_for(client, run["id"])["status"] == "success"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    version = client.get(f"/api/atelier/workbooks/{analysis['id']}").json()["versions"][0]
    written = load_workbook(io.BytesIO(client.get(f"/api/atelier/workbooks/{analysis['id']}/versions/{version['name']}").content))["Classi"]
    assert written["C2"].value == shares[1]["name"] and written["C3"].value == "valore già presente"


def test_unknown_isin_is_reported_not_guessed(client):
    wb = Workbook()
    ws = wb.active
    ws.append(["ISIN", "Share class name"])
    ws.append(["QZ0000000000", None])
    analysis = _upload(client, wb, "unknown.xlsx")
    recipe = {"name": "x", "workbook_id": analysis["id"], "sheet": analysis["sheets"][0]["name"], "header_row": 1, "key_column": "A",
              "key_type": "isin_part", "mappings": [{"column": "B", "extraction": "onto:part.nom"}]}
    change = client.post("/api/atelier/preview", json=recipe).json()["changes"][0]
    assert change["status"] == "not_found" and "inconnu" in change["note"]
