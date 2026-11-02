"""Forme des réponses (anciens RFI du même questionnaire), surlignage des réponses à demander, apprentissage par
l'historique (questions des anciens RFI ↔ textes Qvidian choisis), rappel multilingue vérifié des précédents."""
import io
import os
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import docx
import pytest
from openpyxl import Workbook, load_workbook

from merlin.qvidian.demo import DemoQvidian
from merlin.qvidian.history import History, build_links, demo_precedents
from merlin.qvidian.library_search import LibrarySearch
from merlin.qvidian.snapshot import Snapshot, sync
from merlin.rfi.form import FormModel, apply, consensus, features
from merlin.rfi.layout import Slot
from merlin.rfi.service import _apply_form
from merlin.rfi.writer import write

TODAY = date(2026, 10, 15)


@dataclass
class P:
    id: str
    question: str
    answer_text: str
    source_file: str
    ref_date: str = "2025-01-01"
    kind: str = "answer"
    blocked: bool = False
    fund_name: str = ""
    origin: str = "sharepoint"


QUESTIONS = ["Is the fund UCITS compliant?", "Management fee (%)", "Fund inception date", "Fund name", "Describe the ESG policy"]
ESG = "Our ESG policy integrates environmental, social and governance criteria at each step of the analysis, with exclusions."


def _old_rfis() -> list[P]:
    out = []
    for k, (file, day) in enumerate([("DDQ_Client_2024.xlsx", "2024-03-01"), ("DDQ_Client_2025.xlsx", "2025-03-01"), ("DDQ_Client_2026.xlsx", "2026-03-01")]):
        answers = ["YES", f"1.{k}0%", f"2019-0{k + 1}-15", f"Imaginary Fund {k}", ESG]
        out += [P(f"{file}:{i}", q, a, file, day) for i, (q, a) in enumerate(zip(QUESTIONS, answers))]
    out += [P("other:1", "Totally different question", "Oui", "Autre.xlsx")]
    return out


# ------------------------------------------------------------------ forme
def test_features_and_consensus():
    assert features("YES")[0] == "bool" and features("1,35 %") == ("percent", {"sep": ",", "decimals": 2, "space": True})
    assert features("2025-12-31") == ("date", {"format": "yyyy-mm-dd"})
    spec = consensus([("1.10%", "a"), ("1.20%", "b"), ("1,5 %", "c")])
    assert spec.kind == "percent" and spec.style == {"sep": ".", "decimals": 2, "space": False} and spec.support == 2
    assert consensus([("Oui", "a")]) is None  # une seule réponse : pas de consensus
    assert apply(spec, "1,35 %", "1,35 %") == ("1.35%", "1.35%")
    assert apply(spec, "1,35 %", 0.0135) is None  # cellule au format % : Excel garde la forme du client


def test_same_questionnaire_gives_the_form_of_the_answers():
    model = FormModel(_old_rfis(), QUESTIONS + ["Une question en plus"])
    assert [s.file for s in model.sources] == ["DDQ_Client_2024.xlsx", "DDQ_Client_2025.xlsx", "DDQ_Client_2026.xlsx"]
    slot = Slot(id="x1", question="Is the fund UCITS compliant?", location="Q!B2", target={"sheet": "Q", "cell": "B2"}, state="empty")
    row = {"status": "auto", "answer": "Oui", "_value": "Oui", "source": "ontologie", "reasons": []}
    out = _apply_form(row, slot, model)
    assert out["answer"] == "YES" and "forme reprise de 3 anciens RFI" in out["reasons"][-1]
    fee = _apply_form({"status": "auto", "answer": "0,80 %", "_value": "0,80 %", "source": "ontologie", "reasons": []},
                      Slot(id="x2", question="Management fee (%)", location="Q!B3", target={}, state="empty"), model)
    assert fee["answer"] == "0.80%"
    when = _apply_form({"status": "auto", "answer": "01/02/2020", "_value": "01/02/2020", "source": "ontologie", "reasons": []},
                       Slot(id="x3", question="Fund inception date", location="Q!B4", target={}, state="empty"), model)
    assert when["answer"] == "2020-02-01"
    # Réponse rédigée identique dans plusieurs anciens RFI du même questionnaire : proposée « à vérifier », jamais écrite d'office
    esg = _apply_form({"status": "unmatched", "answer": None, "source": "ontologie", "reasons": [], "issues": []},
                      Slot(id="x4", question="Describe the ESG policy", location="Q!B6", target={}, state="empty"), model)
    assert esg["status"] == "review" and esg["answer"] == ESG and esg["source"] == "précédent"
    # Une réponse Qvidian ou saisie ne change jamais de forme
    mine = _apply_form({"status": "auto", "answer": "Oui", "source": "réponse saisie", "reasons": []}, slot, model)
    assert mine["answer"] == "Oui"


def test_a_different_questionnaire_is_not_used():
    assert not FormModel(_old_rfis(), ["Quel est le nom du gérant ?", "Devise de la part", "Frais courants"]).sources


# ------------------------------------------------------------------ réponses à demander, surlignées en jaune
def test_missing_answers_are_highlighted_in_yellow_xlsx(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Q"
    for r, q in enumerate(["Question", "Fund name", "Benchmark", "Number of staff"], start=1):
        ws.cell(r, 1, q)
    src, out = tmp_path / "q.xlsx", tmp_path / "out.xlsx"
    wb.save(src)
    write(src, out, [({"sheet": "Q", "cell": "B2"}, "Fonds Imaginaire", [])], highlight=[{"sheet": "Q", "cell": "B3"}, {"sheet": "Q", "cell": "B4"}])
    got = load_workbook(out)["Q"]
    assert got["B2"].value == "Fonds Imaginaire" and got["B2"].fill.fgColor.rgb != "FFFFFF00"
    assert got["B3"].fill.fgColor.rgb == "FFFFFF00" and got["B4"].fill.fgColor.rgb == "FFFFFF00" and got["B3"].value is None
    assert got["A3"].fill.fgColor.rgb != "FFFFFF00"  # la question n'est jamais touchée
    zo, zn = zipfile.ZipFile(src), zipfile.ZipFile(out)
    for name in zo.namelist():
        if not name.startswith("xl/worksheets/") and name != "xl/styles.xml":
            assert zo.read(name) == zn.read(name), name


def test_missing_answers_are_highlighted_in_word(tmp_path):
    d = docx.Document()
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(1, 0).text = "Fund name", "Benchmark"
    d.add_paragraph("Name of the depositary:")
    src, out = tmp_path / "q.docx", tmp_path / "out.docx"
    d.save(src)
    write(src, out, [], highlight=[{"type": "cell", "table": 0, "row": 1, "col": 1}, {"type": "inline", "paragraph": 0}])
    got = docx.Document(str(out))
    assert 'w:fill="FFFF00"' in got.tables[0].cell(1, 1)._tc.xml
    assert "[à compléter]" in got.paragraphs[0].text


def test_generate_api_highlights_and_lists_what_to_ask(client):
    doc = client.post("/api/rfi/demo/xlsx").json()
    s = doc["suggestions"][0]
    body = {"pid": s["pid"], "isin": s["isin"], "highlight_missing": True, "use_qvidian": False}
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()
    assert analysis["qvidian_used"] is False and all(x["source"] != "Qvidian" for x in analysis["questions"])
    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body).json()
    assert generated["highlighted"] == len(generated["to_ask"]) and generated["highlighted"] >= 1
    content = client.get(f"/api/rfi/documents/{doc['id']}/versions/{generated['file']}").content
    wb = load_workbook(io.BytesIO(content))
    yellow = [c.coordinate for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.fill and c.fill.fgColor.rgb == "FFFFFF00"]
    assert len(yellow) == generated["highlighted"]
    assert client.get(f"/api/rfi/documents/{doc['id']}").json()["qvidian_available"] is True


# ------------------------------------------------------------------ historique : anciens RFI ↔ textes Qvidian
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    snap = Snapshot(tmp_path_factory.mktemp("hist") / "demo.sqlite")
    sync(DemoQvidian(), snap, "demo")
    links = build_links(snap.all(), demo_precedents({c["id"]: c for c in snap.all()}))
    history = History(snap.path.with_name("demo.history.json"))
    history.save(links, len(links), "test")
    return snap, history


def test_old_answers_are_linked_to_the_qvidian_text_chosen(demo):
    snap, history = demo
    by = history.by_content()
    assert by[1021]["files"] == 5 and "Main shareholders of the management company" in by[1021]["questions"]
    # réponse « reprise » : le texte Qvidian complété d'une phrase
    text = snap.get(1031)["text"]
    links = build_links(snap.all(), [P("x", "Contingency plan?", text + " Un second site est en cours d'étude.", "RFI.xlsx")])
    assert links and links[0].content_id == 1031 and links[0].mode in {"version", "repris"}
    assert not build_links(snap.all(), [P("y", "Q?", "Une réponse sans aucun rapport avec la bibliothèque de démonstration.", "RFI.xlsx")])


def test_search_is_led_by_the_questions_of_old_rfis(demo):
    snap, history = demo
    engine = LibrarySearch(snap, today=TODAY, history=history.by_content())
    top = engine.search("Main shareholders")["results"][0]
    assert top["id"] == 1021 and top["history"]["files"] == 5 and any("choisi dans 5 anciens RFI" in w for w in top["why"])
    # un texte choisi pour d'autres questions n'est pas promu sur une question sans rapport
    assert engine.search("Heure limite de centralisation des ordres")["results"][0]["id"] == 1047
    assert engine.history_matches("Main shareholders of the management company")[0][0] == 1021


def test_history_api(client):
    summary = client.post("/api/qvidian/history/rebuild").json()
    assert summary["links"] >= 20 and summary["top"][0]["files"] >= 4
    res = client.post("/api/qvidian/search", json={"q": "Business continuity arrangements", "k": 3}).json()
    assert res["results"][0]["id"] in {1031, 1062} and res["results"][0]["history"]


@pytest.mark.skipif(not os.environ.get("MERLIN_TEST_MODELS"), reason="modèles ONNX non fournis (MERLIN_TEST_MODELS=dossier)")
def test_precedent_in_another_language_is_found_only_with_the_same_concept(tmp_path):
    from merlin.config import get_settings
    from merlin.data.catalog import load_catalog
    from merlin.rfi.ontology import load_ontology
    from merlin.rfi.precedents.model import Precedent
    from merlin.rfi.precedents.retrieval import PrecedentIndex
    from merlin.rfi.precedents.store import PrecedentStore
    from merlin.rfi.precedents.advisor import PrecedentAdvisor
    from merlin.rfi.understand import understand
    from merlin.search.neural import Encoder

    store = PrecedentStore(tmp_path / "p.sqlite")
    store.replace_source("old.xlsx", "sharepoint", [
        Precedent("a", "sharepoint", "old.xlsx", "Fund inception date", "15/01/2019"),
        Precedent("b", "sharepoint", "old.xlsx", "Date de création de la stratégie", "01/01/2010")])
    index = PrecedentIndex(store, None, Encoder(Path(os.environ["MERLIN_TEST_MODELS"]), "e5-small"))
    ontology = load_ontology(load_catalog(str(get_settings().catalog_csv)))
    advisor = PrecedentAdvisor(ontology, index, None, lambda *a: None, TODAY, "fr", None)
    u = understand(ontology, "Date de création du fonds")
    found = advisor._same_concept_elsewhere("Date de création du fonds", ontology.concepts["fonds.date_creation"], u, set())
    assert [h.precedent.id for h in found] == ["a"]  # la traduction oui, la voisine « stratégie » non
