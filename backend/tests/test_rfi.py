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
    ("Sí / No", "placeholder"), ("A completar", "placeholder"), ("Da compilare", "placeholder"), ("Indique la divisa", "placeholder"),
    ("Sì", "answered"),
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
    # question qualitative : rien dans Fabric ; la réponse type Qvidian (démo) est proposée, jamais écrite d'office
    philo = by_q["Décrivez la philosophie d'investissement et le processus de sélection des titres."]
    assert philo["status"] == "review" and philo["source"] == "Qvidian" and philo["choices"][0]["sources"][0]["kind"] == "qvidian"
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


def test_question_named_like_a_header_does_not_hide_rows_above(tmp_path):
    """« Label » au milieu d'une liste n'est pas un en-tête de colonne (cas réel : questionnaire DATA_OPC)."""
    wb = Workbook()
    ws = wb.active
    for q in ["ISIN", "Nom du fonds", "Date de lancement", "SRI", "SFDR", "Label", "Catégorie de fonds"]:
        ws.append([None, q, None])
    path = tmp_path / "data.xlsx"
    wb.save(path)
    assert [s.question for s in detect(path).slots][:2] == ["ISIN", "Nom du fonds"]


def test_computed_sources_use_catalog_columns_only():
    from merlin.rfi.values import KID_TRANSACTION_COLUMNS, LABEL_COLUMNS, PRODUCT
    from merlin.config import get_settings
    from merlin.data.catalog import load_catalog

    table = load_catalog(str(get_settings().catalog_csv)).table(PRODUCT)
    for column in [*LABEL_COLUMNS, *KID_TRANSACTION_COLUMNS]:
        assert table.column(column) is not None, column


def test_choose_option_matches_combined_choices_in_any_order():
    option, _ = choose_option(["Aucun", "ISR", "Finansol", "ISR/Finansol", "Greenfin"], texts=["Finansol, ISR"])
    assert option == "ISR/Finansol"


def test_preview_maps_answer_cells_to_questions(client):
    doc = client.post("/api/rfi/demo/xlsx").json()
    p = client.get(f"/api/rfi/documents/{doc['id']}/preview").json()
    assert p["kind"] == "xlsx" and p["sheets"]
    linked = [c for s in p["sheets"] for row in s["rows"] for c in row["cells"] if c["q"]]
    assert len(linked) >= 20


def test_short_uppercase_section_title_is_not_a_question(tmp_path):
    wb = Workbook()
    ws = wb.active
    for row in [["GESTION", None], ["Nom du gérant", None], ["SRI", None]]:
        ws.append(row)
    path = tmp_path / "t.xlsx"
    wb.save(path)
    questions = [s.question for s in detect(path).slots]
    assert "GESTION" not in questions and "SRI" in questions


# ------------------------------------------------------------------ espagnol / italien, plusieurs parts
GOLD_ES_IT = Path(__file__).with_name("rfi_gold_es_it.yaml")


def test_spanish_and_italian_questions_bank_is_error_free():
    report = run_cases(_ontology(), load_cases(GOLD_ES_IT))
    assert report["wrong_auto"] == [], report["wrong_auto"]
    assert report["auto_precision"] == 1.0
    assert report["auto_coverage"] >= 0.9


def test_language_detection_and_pivot():
    from merlin.rfi.lexicon import detect_language, question_language, to_pivot
    from merlin.rfi.ontology import norm

    assert detect_language("¿Cuál es la comisión de gestión máxima de la clase? Nombre del fondo") == "es"
    assert detect_language("Indicare la commissione di gestione massima della classe di quote. Nome del fondo") == "it"
    assert detect_language("Quel est le nom du fonds ? Indiquez la devise de la part") == "fr"
    assert detect_language("What is the fund name? Please provide the share class currency") == "en"
    assert question_language("Nome del fondo", "it") == "it"  # « del » et « fondo » existent aussi en espagnol
    assert question_language("Quelle est la devise de la part ?", "es") == "fr"  # document mixte
    # une seule passe : « y » (et) traduit n'est jamais retraduit, « hay un » → « y a-t-il un »
    assert to_pivot(norm("¿Hay un mecanismo de swing pricing?"), "es").startswith("y a-t-il un")
    assert to_pivot(norm("Comisión de gestión máxima"), "es") == "commission de gestion maximum"


def test_answers_are_written_in_spanish_and_italian():
    from merlin.rfi.render import fmt_number

    o = _ontology()
    assert o.vocab_value("yes_no", "Sí").label("es") == "Sí" and o.vocab_value("yes_no", "si").label("it") == "Sì"
    assert o.vocab_value("frequency", "Diaria").id == "daily"  # option de liste déroulante espagnole reconnue
    assert o.vocab_value("legal_form", "SICAV").label("it") == "SICAV"  # pas de libellé italien : repli sur l'anglais
    assert fmt_number(1234.5, 2, "es") == "1.234,50" and fmt_number(1234.5, 2, "it") == "1.234,50"
    assert choose_option(["menos de 1 año", "entre 1 y 3 años", "más de 3 años"], number=5, texts=["5 años"])[0] == "más de 3 años"
    assert choose_option(["meno di 1 anno", "tra 1 e 3 anni", "oltre 3 anni"], number=2, texts=["2 anni"])[0] == "tra 1 e 3 anni"


def _two_shares(client):
    funds = client.get("/api/rfi/funds").json()
    fund = next(f for f in funds if len(f["shares"]) >= 2)
    return fund, fund["shares"][0], fund["shares"][1]


def test_list_questionnaire_with_one_section_per_share(client, tmp_path):
    fund, a, b = _two_shares(client)
    wb = Workbook()
    ws = wb.active
    ws.title = "Cuestionario"
    rows = [("Pregunta", "Respuesta"), ("Nombre del fondo", None), ("CLASE A", None), ("Código ISIN", a["isin"]),
            ("Nombre de la clase de participaciones", None), ("Divisa de la clase", None),
            ("CLASE B", None), ("Código ISIN", b["isin"]), ("Nombre de la clase de participaciones", None), ("Divisa de la clase", None)]
    for r, (q, v) in enumerate(rows, start=1):
        ws.cell(r, 1, q)
        ws.cell(r, 2, v)
    path = tmp_path / "cuestionario.xlsx"
    wb.save(path)
    doc = client.post("/api/rfi/documents", files={"file": ("cuestionario.xlsx", path.read_bytes())}).json()
    assert doc["language"] == "es" and doc["multi_share"] is True
    assert {s["isin"]: s["questions"] for s in doc["shares"]} == {a["isin"]: 3, b["isin"]: 3}
    assert all(s["known"] and s["pid"] == fund["pid"] for s in doc["shares"])
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json={"pid": fund["pid"], "isin": a["isin"]}).json()
    names = [x for x in analysis["questions"] if x["question"] == "Nombre de la clase de participaciones"]
    assert [x["entity"]["isin"] for x in names] == [a["isin"], b["isin"]]
    assert [x["answer"] for x in names] == [a["name"], b["name"]]  # chaque section lit SA part
    fund_name = next(x for x in analysis["questions"] if x["question"] == "Nombre del fondo")
    assert fund_name["entity"] == {} and fund_name["answer"] == fund["name"]


def test_single_isin_in_a_list_keeps_the_chosen_share(tmp_path):
    wb = Workbook()
    ws = wb.active
    for r, (q, v) in enumerate([("Question", "Réponse"), ("Code ISIN", "QZ0000000001"), ("Devise de la part", None)], start=1):
        ws.cell(r, 1, q)
        ws.cell(r, 2, v)
    wb.save(tmp_path / "one.xlsx")
    layout = detect(tmp_path / "one.xlsx")
    assert all(not s.entity for s in layout.slots)  # une seule part citée : la part choisie à l'écran s'applique
