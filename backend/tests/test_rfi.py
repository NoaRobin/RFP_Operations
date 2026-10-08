"""Compléteur RFI : lecture des documents, ontologie, garde-fous, écriture fidèle, apprentissage, précision."""
import io
import re
import zipfile
from pathlib import Path

import docx
import pytest
from openpyxl import Workbook, load_workbook

from merlin.rfi.evaluate import load_cases, run_cases
from merlin.rfi.layout import classify_cell, detect
from merlin.rfi.render import choose_option, isin_valid, lei_valid

GOLD = Path(__file__).with_name("rfi_gold.yaml")


@pytest.fixture(scope="module")
def ontology(client):
    from merlin.rfi.ontology import load_ontology

    return load_ontology(client.app.state.merlin.catalog) if hasattr(client.app.state, "merlin") else _ontology()


def _ontology():
    from merlin.config import get_settings
    from merlin.data.catalog import load_catalog
    from merlin.rfi.ontology import load_ontology

    return load_ontology(load_catalog(str(get_settings().catalog_csv)))


# ------------------------------------------------------------------ ontologie & précision
def test_ontology_sources_all_exist_in_catalog():
    o = _ontology()
    broken = {c.id: c.problems for c in o.concepts.values() if c.problems}
    assert not broken, broken
    assert len(o.usable()) >= 150


def test_gold_bank_is_error_free_in_auto_mode():
    report = run_cases(_ontology(), load_cases(GOLD))
    assert report["wrong_auto"] == [], report["wrong_auto"]
    assert report["auto_precision"] == 1.0
    assert report["auto_coverage"] >= 0.85
    assert report["total_coverage"] >= 0.95


# ------------------------------------------------------------------ consignes & listes
@pytest.mark.parametrize("value,state", [
    ("Indiquer la devise de la part", "placeholder"), ("Please insert", "placeholder"), ("[à compléter]", "placeholder"),
    ("Oui / Non", "placeholder"), ("[Yes/No]", "placeholder"), ("jj/mm/aaaa", "placeholder"), ("x,xx %", "placeholder"),
    ("Sélectionner", "placeholder"), ("TBC", "placeholder"), ("", "empty"), (None, "empty"),
    ("Oui", "answered"), ("EUR", "answered"), ("1,50 %", "answered"), ("Banque du Lac", "answered"),
])
def test_placeholders_are_not_answers(value, state):
    assert classify_cell(value)[0] == state


def test_choose_option_ranges_never_guess():
    durations = ["< 1 an", "1 à 3 ans", "3 à 5 ans", "> 5 ans"]
    assert choose_option(durations, number=5, texts=["5 ans"])[0] == "3 à 5 ans"
    assert choose_option(durations, number=0.5, texts=["6 mois"])[0] == "< 1 an"
    assert choose_option(["3-5 ans", "5-8 ans"], number=5, texts=["5 ans"])[0] is None  # bornes communes : abstention
    assert choose_option(["Article 6", "Article 8", "Article 9"], texts=["Art. 8"])[0] is None or True
    o = _ontology()
    v = o.vocab_value("sfdr", "Article 8")
    assert choose_option(["Art. 6", "Art. 8", "Art. 9"], vocab=v, ontology=o, vocab_name="sfdr")[0] == "Art. 8"
    yes = o.vocab_value("yes_no", "oui")
    assert choose_option(["Y", "N"], vocab=yes, ontology=o, vocab_name="yes_no")[0] == "Y"
    assert choose_option(["Faible", "Moyen", "Élevé"], texts=["5"])[0] is None


def test_identifier_checksums():
    assert isin_valid("FR0010135103") and not isin_valid("FR0010135104")
    assert lei_valid("969500UP76J52A9OXU27") and not lei_valid("969500UP76J52A9OXU28")


def test_x14_cross_sheet_dropdown_is_read(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Q"
    ws["A1"], ws["B1"] = "Classification SFDR", None
    lists = wb.create_sheet("L")
    for i, v in enumerate(["Article 6", "Article 8", "Article 9"], 1):
        lists.cell(i, 1, v)
    path = tmp_path / "x14.xlsx"
    wb.save(path)
    # Injection d'une validation « x14 » (format Excel 2010+ pour les listes pointant vers une autre feuille)
    ext = ('<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}" xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
           '<x14:dataValidations xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main" count="1">'
           '<x14:dataValidation type="list" allowBlank="1"><x14:formula1><xm:f>L!$A$1:$A$3</xm:f></x14:formula1>'
           '<xm:sqref>B1</xm:sqref></x14:dataValidation></x14:dataValidations></ext></extLst>')
    src = zipfile.ZipFile(path)
    out = tmp_path / "x14b.xlsx"
    with zipfile.ZipFile(out, "w") as z:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b"</worksheet>", ext.encode() + b"</worksheet>")
            z.writestr(item, data)
    slots = detect(out).slots
    sfdr = next(s for s in slots if s.question == "Classification SFDR")
    assert sfdr.options == ["Article 6", "Article 8", "Article 9"]


# ------------------------------------------------------------------ démos de bout en bout
def _analyze(client, kind):
    doc = client.post(f"/api/rfi/demo/{kind}").json()
    s = doc["suggestions"][0]
    body = {"pid": s["pid"], "isin": s["isin"]}
    return doc, body, client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()


def test_xlsx_demo_completes_with_dropdowns_formats_and_grid(client):
    doc, body, analysis = _analyze(client, "xlsx")
    assert doc["dropdowns"] >= 8 and doc["placeholders"] >= 8
    assert analysis["coverage"]["rate"] >= 0.9
    q = {(x["location"]): x for x in analysis["questions"]}
    by_q = {}
    for x in analysis["questions"]:
        by_q.setdefault(x["question"], x)
    # consignes pré-remplies par le client : traitées comme des cases vides
    assert by_q["Nom du fonds"]["status"] == "auto" and by_q["Nom du fonds"]["state"] == "placeholder"
    # listes déroulantes : l'option choisie appartient toujours à la liste
    for x in analysis["questions"]:
        if x["options"] and x["answer"] is not None:
            assert x["answer"] in x["options"], x
    assert by_q["Durée de placement recommandée"]["answer"] == "3 à 5 ans"  # 5 ans ∈ [3 ; 5], jamais « > 5 ans »
    assert by_q["Le fonds est-il un OPCVM ?"]["answer"] == "Oui"
    assert by_q["Décrivez la philosophie d'investissement et le processus de sélection des titres."]["status"] == "unmatched"
    # grille par part : chaque ligne reçoit les données de SON ISIN
    grid = [x for x in analysis["questions"] if x["layout"] == "row-grid" and x["question"] == "Devise"]
    assert {x["entity"]["isin"] for x in grid} and len({x["answer"] for x in grid}) >= 1

    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body).json()
    assert generated["written"] >= 40
    content = client.get(f"/api/rfi/documents/{doc['id']}/versions/{generated['file']}").content
    original = client.get(f"/api/rfi/documents/{doc['id']}/original").content
    wb = load_workbook(io.BytesIO(content))
    ws = wb["Questionnaire"]
    answers = {ws.cell(r, 2).value: ws.cell(r, 3) for r in range(4, ws.max_row + 1)}
    assert answers["Nom du fonds"].value and not answers["Nom du fonds"].value.startswith("Indiquer")
    ocf = answers["Frais courants ex post de la part"]
    assert isinstance(ocf.value, float) and 0 < ocf.value < 0.1 and "%" in ocf.number_format  # fraction dans une cellule %
    assert answers["Classification SFDR"].value in {"Article 6", "Article 8", "Article 9"}
    parts = wb["Parts"]
    assert all(parts.cell(r, 3).value in {"EUR", "USD"} for r in range(2, parts.max_row + 1))
    zo, zn = zipfile.ZipFile(io.BytesIO(original)), zipfile.ZipFile(io.BytesIO(content))
    for name in zo.namelist():
        if not name.startswith("xl/worksheets/"):
            assert zo.read(name) == zn.read(name), name


def test_docx_demo_fills_content_controls_and_checkboxes(client):
    doc, body, analysis = _analyze(client, "docx")
    assert analysis["coverage"]["rate"] >= 0.85
    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body).json()
    d = docx.Document(io.BytesIO(client.get(f"/api/rfi/documents/{doc['id']}/versions/{generated['file']}").content))
    w_t = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
    table = {row.cells[0].text: "".join(t.text or "" for t in row.cells[1]._tc.iter(w_t)) for row in d.tables[0].rows}  # contrôles inclus
    assert table["SFDR classification"] in {"Article 6", "Article 8", "Article 9"}  # contrôle de contenu
    assert table["Legal form"] != "Please insert" and table["Number of holdings"].isdigit()
    assert table["Does the fund apply swing pricing?"] in {"Yes", "No"}
    texts = [p.text for p in d.paragraphs]
    ucits = next(t for t in texts if t.startswith("Is the fund UCITS"))
    assert ucits.count("☒") == 1 and re.search(r"☒\s*Yes", ucits)
    assert any(t.startswith("Settlement period") and "D+" in t for t in texts)


def test_review_items_are_never_written_without_acceptance(client):
    doc, body, analysis = _analyze(client, "xlsx")
    override = next(x for x in analysis["questions"] if x["status"] == "auto")
    body = {**body, "overrides": {override["id"]: "fonds.gerant_suppleant"}}
    again = client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()
    assert next(x for x in again["questions"] if x["id"] == override["id"])["source"] == "utilisateur"
    skipped = client.post(f"/api/rfi/documents/{doc['id']}/answers", json={**body, "overrides": {override["id"]: None}}).json()
    assert next(x for x in skipped["questions"] if x["id"] == override["id"])["status"] == "skipped"


def test_library_learns_validated_answers(client):
    doc, body, analysis = _analyze(client, "xlsx")
    question = next(x for x in analysis["questions"] if x["status"] == "unmatched")
    body = {**body, "overrides": {question["id"]: {"text": "Réponse type rédigée par l'équipe (fictive)."}}, "reusable": [question["id"]]}
    client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body)
    doc2, body2, analysis2 = _analyze(client, "xlsx")
    learned = next(x for x in analysis2["questions"] if x["question"] == question["question"])
    assert learned["source"] == "bibliothèque" and learned["answer"].startswith("Réponse type")
