"""Précédents : import avec provenance, blocage d'identité, recherche, contrôle Fabric, décision justifiée.

Uniquement des fonds et ISIN fictifs (préfixe QZ, données de démonstration)."""
import io
import json

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

from merlin.rfi.precedents.identity import identity_problem
from merlin.rfi.precedents.templates import decompose, fill

A, B, C = ("PI-700", "QZ2228LUXT99", "Avalon Actions Europe"), ("PI-701", "QZYM908XINV7", "Brocéliande Crédit Haut Rendement"), \
    ("PI-702", "QZXNJIKST194", "Camelot Multi-Actifs Patrimoine")


def _example(n, question, answer, fund, ref="ref-ok", shape="TEXTE_COURT", comments=None):
    return {"example_id": f"T{n:04d}", "source_ref": ref, "source_file": f"Suivi fictif {ref}.xlsx", "sheet": "Data",
            "question_cell": f"B{n}", "question": question, "answer_cell": f"C{n}", "answer_raw": answer, "answer_number_format": "General",
            "comments": comments or [], "context": {"isin": fund[1], "fund_name": fund[2], "reference_date_raw": "2026-03-31T00:00:00"},
            "shape_observed": shape, "extraction_method": "COLONNES_EXPLICITES", "mapping_status": "A_RAPPROCHER",
            "reuse_status": "EXEMPLE_HISTORIQUE_NON_APPROUVE", "auto_copy_allowed": False, "review_required": True}


def _corpus():
    ex = [
        _example(1, "Frais courants de la part", "1,61 %", B), _example(2, "Frais courants de la part", "1,79%", C),
        _example(3, "Dépositaire", "Banque Imaginaire du Nord", B),
        _example(4, "Signataire PRI", "OUI", B), _example(5, "Signataire PRI", "OUI", C),
        _example(6, "Politique de vote publiée", "OUI", B, ref="ref-anomalie"), _example(7, "Politique de vote publiée", "OUI", C, ref="ref-anomalie"),
        _example(8, "Nombre de comités d'investissement par an", "12", B), _example(9, "Nombre de comités d'investissement par an", "4", C),
        _example(10, "Présentation synthétique du support", f"{B[2]} est un fonds Article 8 géré par Société de Gestion Fictive.", B, shape="NARRATIF"),
        _example(11, "Engagement actionnarial", "", B, comments=[{"cell": "D11", "value": ""}]),
    ]
    return {"metadata": {"version": "test"}, "answer_examples": ex, "matrix_data": [],
            "identity_issues": [{"source_ref": "ref-anomalie", "sheet": "Data", "cell": "B4", "issue": "ISIN_FILENAME_CELL_DIFFERENT",
                                 "filename_isin": "QZ0000000000", "cell_value": "QZ0000000001"}]}


def _rfi() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire"
    ws.append(["Question", "Réponse"])
    for q in ["Frais courants de la part", "Dépositaire", "Signataire PRI", "Politique de vote publiée",
              "Nombre de comités d'investissement par an", "Présentation synthétique du support", "Engagement actionnarial"]:
        ws.append([q, None])
    dv = DataValidation(type="list", formula1='"OUI,NON"')
    ws.add_data_validation(dv)
    dv.add("B4")
    dv.add("B5")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_identity_anomaly_is_flagged_never_corrected():
    assert identity_problem("Questionnaire QZ2228LUXT99.xlsx", ["QZ2228LUXT99"]) == ""
    assert "différent" in identity_problem("Questionnaire QZ2228LUXT99.xlsx", ["QZYM908XINV7"])
    assert "clé" in identity_problem("x.xlsx", ["QZ2228LUXT98"])


def test_narrative_template_only_when_every_fact_is_explained():
    facts = {"fonds.nom": (B[2], B[2]), "fonds.sfdr": ("Article 8", "Article 8")}
    t = decompose(f"{B[2]} est un fonds Article 8.", facts, [B[2]])
    assert t.safe and t.params == ["fonds.nom", "fonds.sfdr"]
    assert fill(t, {"fonds.nom": A[2], "fonds.sfdr": "Article 9"}.get) == f"{A[2]} est un fonds Article 9."
    unsafe = decompose(f"{B[2]} affiche 4,2 % depuis le 31/12/2025.", facts, [B[2]])
    assert not unsafe.safe and unsafe.residual  # chiffre et date propres au fonds d'origine : simple référence de style


def _bind_funds(client):
    """ISIN fictifs du jeu de démonstration (ils dépendent de la date de génération du mock)."""
    global A, B, C
    funds = {f["pid"]: f for f in client.get("/api/rfi/funds").json()}
    A, B, C = [(pid, funds[pid]["shares"][0]["isin"], funds[pid]["name"]) for pid in ("PI-700", "PI-701", "PI-702")]


def test_precedents_drive_justified_decisions(client):
    _bind_funds(client)
    imported = client.post("/api/rfi/precedents/wording", files={"file": ("lib.json", json.dumps(_corpus()).encode(), "application/json")}).json()
    assert imported["imported"] == 11 and imported["blocked"] == 2
    found = client.get("/api/rfi/precedents/search", params={"q": "frais courants part"}).json()
    assert found and found[0]["question"] == "Frais courants de la part" and found[0]["provenance"]

    doc = client.post("/api/rfi/documents", files={"file": ("rfi_test.xlsx", _rfi(), "application/octet-stream")}).json()
    body = {"pid": A[0], "isin": A[1], "as_of": "2026-06-30"}
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()
    by_q = {x["question"]: x for x in analysis["questions"]}

    fees = by_q["Frais courants de la part"]  # ontologie + 2 précédents concordants avec Fabric
    assert fees["precedent"]["kind"] == "precedent_confirme" and "Repris de l'ancien" in fees["precedent"]["justification"]
    assert all(p["check"] == "match" for p in fees["precedent"]["precedents"] if p["check"])

    custodian = by_q["Dépositaire"]  # l'ancien RFI ne dit pas ce que dit Fabric : incohérence, jamais automatique
    assert custodian["precedent"]["kind"] == "incoherence" and custodian["status"] == "review"

    pri = by_q["Signataire PRI"]  # réponse société identique sur 2 fonds : proposée, à valider, dans la liste
    assert pri["precedent"]["kind"] == "precedent_constant" and pri["status"] == "review" and pri["answer"] == "OUI"

    vote = by_q["Politique de vote publiée"]  # anomalie d'identité : réutilisation bloquée
    assert vote["answer"] is None and all(p["blocked"] for p in vote["precedent"]["precedents"])
    assert "bloquée" in vote["precedent"]["justification"]

    committees = by_q["Nombre de comités d'investissement par an"]  # réponses divergentes selon le fonds
    assert committees["answer"] is None and "divergent" in committees["precedent"]["justification"]

    pitch = by_q["Présentation synthétique du support"]  # modèle paramétré : faits du fonds courant, jamais ceux de l'ancien
    assert pitch["precedent"]["kind"] == "modele_redaction" and pitch["answer"] and pitch["answer"].startswith(A[2])
    assert B[2] not in pitch["answer"] and pitch["status"] == "review"

    empty = by_q["Engagement actionnarial"]  # commentaire vide : jamais transformé en « NON »
    assert empty["answer"] is None

    inv = client.get("/api/rfi/precedents/inventory").json()
    assert inv["total"] == 11 and inv["usable"]["total"] >= 6 and inv["to_review"]
    assert any("identité" in k for k in inv["to_review"]) and inv["limits"]
    assert "answer" not in json.dumps(inv["uncovered"])  # agrégats : aucune valeur de réponse dans l'inventaire

    generated = client.post(f"/api/rfi/documents/{doc['id']}/generate", json=body).json()
    written = {r["question"] for r in generated["questions"] if r["status"] == "auto"}
    assert "Signataire PRI" not in written and "Dépositaire" not in written  # rien d'historique n'est écrit sans validation


def test_sharepoint_navigation_year_rfi_final(tmp_path):
    from merlin.rfi.precedents.importers import import_document
    from merlin.rfi.precedents.store import PrecedentStore
    from merlin.rfi.sources.local import LocalFolderSource, discover
    from merlin.rfi.sources.navigator import DueDiligenceNavigator

    root = tmp_path / "Organisation fictive" / "Site - Documents" / "1 - Appels d'offres - Due diligence"
    (root / "2026" / "RFI" / "DD Assureur Imaginaire" / "Travail").mkdir(parents=True)
    final = root / "2025" / "RFI" / "DD Banque Fictive" / "Final"
    final.mkdir(parents=True)
    (root / "2024 - archives").mkdir()
    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    ws.append(["Société de gestion", "Société de Gestion Fictive"])
    ws.append(["Code ISIN", B[1]])
    wb.save(final / f"Questionnaire {B[1]}.xlsx")
    (final / "~$Questionnaire.xlsx").write_bytes(b"lock")

    assert discover("1 - Appels d'offres - Due diligence", tmp_path) == root
    nav = DueDiligenceNavigator(LocalFolderSource(root), start_year=2026)
    assert [y for y, _ in nav.years()] == [2026, 2025, 2024]
    assert nav.due_diligences()["year"] == 2026
    found = nav.search("banque fictive")  # absent en 2026 : cherché en 2025 (« 2026 ou moins »)
    assert found["year"] == 2025 and found["folders"][0]["name"] == "DD Banque Fictive"
    listing = nav.final_documents(found["folders"][0]["path"])
    assert [d["name"] for d in listing["documents"]] == [f"Questionnaire {B[1]}.xlsx"]  # fichier verrou ignoré
    assert nav.final_documents(nav.due_diligences()["folders"][0]["path"])["final_path"] is None

    store = PrecedentStore(tmp_path / "p.sqlite")
    result = import_document(store, final / f"Questionnaire {B[1]}.xlsx", "sharepoint")
    assert result["imported"] >= 1 and not result["identity_problem"]
    p = store.all()[0]
    assert p.origin == "sharepoint" and p.answer_cell and p.isin == B[1] and not p.auto_copy_allowed


def test_firm_question_groups_precedents_by_meaning_not_wording(tmp_path, client):
    from datetime import date

    from merlin.rfi.layout import detect
    from merlin.rfi.precedents import PrecedentIndex, PrecedentStore
    from merlin.rfi.precedents.importers import import_lot02
    from merlin.rfi.service import RfiStore, analyze

    _bind_funds(client)
    corpus = {"answer_examples": [
        _example(1, "Signataire PRI", "OUI", B, ref="r1"),
        _example(2, "Est-ce que l'Asset Manager est signataire des PRI ?", "Oui", C, ref="r2"),
        _example(3, "Is the fund management company a UNPRI signatory?", "Yes", B, ref="r3"),
        _example(4, "La société de gestion est-elle signataire des PRI ?", "La société est signataire depuis longtemps.", C, ref="r4"),
    ], "identity_issues": []}
    index = PrecedentIndex(PrecedentStore(tmp_path / "p.sqlite"))
    import_lot02(index.store, corpus)
    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    ws.append(["Êtes-vous signataire des Principes pour l'Investissement Responsable (PRI) ?", None])
    dv = DataValidation(type="list", formula1='"OUI,NON"')
    ws.add_data_validation(dv)
    dv.add("B2")
    path = tmp_path / "rfi.xlsx"
    wb.save(path)
    from merlin.state import get_state

    data = get_state().data
    r = analyze(data, RfiStore(tmp_path / "rfi"), path, detect(path), A[0], A[1], date.today().isoformat(), None, None, index)
    q = r["questions"][0]
    assert q["status"] == "review" and q["answer"] == "OUI" and q["precedent"]["kind"] == "precedent_constant"
    assert "3 questionnaire" in q["precedent"]["justification"]  # le paragraphe sans oui/non ne compte ni pour ni contre


def test_jump_found_by_isin_when_pi_fund_id_differs(client):
    from datetime import date

    from merlin.rfi.ontology import load_ontology
    from merlin.rfi.understand import understand
    from merlin.rfi.values import Values
    from merlin.state import get_state

    _bind_funds(client)
    data = get_state().data
    o = load_ontology(data.catalog)
    v = Values(data, o, "ID-PI-INCONNU", A[1], date.today())
    raw = v.get(o.concepts["jump.encours_fonds"], understand(o, "Encours du fonds"), "fr")
    assert raw.value is not None, (raw, v.errors)


def test_sharepoint_due_diligence_with_one_folder_per_fund(tmp_path):
    from merlin.rfi.sources.local import LocalFolderSource
    from merlin.rfi.sources.navigator import DueDiligenceNavigator

    root = tmp_path / "1 - Appels d'offres - Due diligence"
    dd = root / "2026" / "RFI" / "Questionnaires Assureur Fictif"
    for fund in ("Fonds Imaginaire Alpha", "Fonds Imaginaire Beta"):
        for step in ("Original", "Working", "Final"):
            (dd / fund / step).mkdir(parents=True)
        Workbook().save(dd / fund / "Original" / "vierge.xlsx")
        Workbook().save(dd / fund / "Final" / f"Questionnaire {fund}.xlsx")
    nav = DueDiligenceNavigator(LocalFolderSource(root), start_year=2026)
    path = nav.due_diligences()["folders"][0]["path"]
    listing = nav.final_documents(path)
    assert len(listing["funds"]) == 2 and len(listing["documents"]) == 2
    assert all("Original" not in d["path"] for d in listing["documents"])
    beta = nav.final_documents(path, "beta")
    assert [d["fund"] for d in beta["documents"]] == ["Fonds Imaginaire Beta"]


def test_firm_narrative_reused_unless_it_names_a_fund(tmp_path, client):
    from datetime import date

    from merlin.rfi.layout import detect
    from merlin.rfi.precedents import PrecedentIndex, PrecedentStore
    from merlin.rfi.precedents.importers import import_lot02
    from merlin.rfi.service import RfiStore, analyze
    from merlin.state import get_state

    _bind_funds(client)
    text = "La société dispose d'une politique de meilleure exécution revue chaque année par la Conformité (texte fictif)."
    corpus = {"answer_examples": [
        {**_example(1, "Quelle politique mettez-vous en œuvre pour assurer la meilleure exécution des ordres ?", text, B, ref="r1", shape="NARRATIF")},
        {**_example(2, "Décrivez votre plan de continuité d'activité", f"Le plan couvre notamment {B[2]}.", B, ref="r2", shape="NARRATIF")},
    ], "identity_issues": []}
    index = PrecedentIndex(PrecedentStore(tmp_path / "p.sqlite"))
    import_lot02(index.store, corpus)
    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    ws.append(["Quelle politique mettez vous en œuvre pour assurer la meilleure exécution des ordres ?", None])
    ws.append(["Décrivez votre plan de continuité d'activité.", None])
    path = tmp_path / "ddq.xlsx"
    wb.save(path)
    r = analyze(get_state().data, RfiStore(tmp_path / "rfi"), path, detect(path), A[0], A[1], date.today().isoformat(), None, None, index)
    best, bcp = r["questions"]
    assert best["answer"] == text and best["status"] == "review" and "à relire" in best["precedent"]["justification"]
    # le texte cite un fonds : jamais repris tel quel ; au mieux modèle paramétré avec le nom du fonds courant
    assert bcp["precedent"]["kind"] == "modele_redaction" and B[2] not in (bcp["answer"] or "")


def test_replay_bench_measures_coverage_and_agreement(client):
    from merlin.rfi.replay import replay

    _bind_funds(client)
    report = replay(_corpus(), verbose=False)
    total = report["total"]
    assert total["questions"] >= 8 and 0 < total["coverage"] <= 1
    assert total["precedent_agreement"] is None or 0 <= total["precedent_agreement"] <= 1
    assert "answer" not in json.dumps(report["families"])  # agrégats uniquement


def test_computed_seniority_and_anti_dilution(client):
    from datetime import date

    from merlin.rfi.ontology import load_ontology
    from merlin.rfi.understand import understand
    from merlin.rfi.values import Values, years_threshold
    from merlin.state import get_state

    assert years_threshold("A-t-il un track record de plus d'1 an ?") == 1
    assert years_threshold("Ancienneté du gérant principal > 3 ans") == 3
    assert years_threshold("Track record") is None
    _bind_funds(client)
    data = get_state().data
    o = load_ontology(data.catalog)
    v = Values(data, o, A[0], A[1], date.today())
    q = "A-t-il un track record de plus d'1 an ?"
    assert v.get(o.concepts["fonds.track_record"], understand(o, q), "fr").value in {"yes", "no"}
    raw = v.get(o.concepts["part.mecanisme_anti_dilution"], understand(o, "Mécanisme anti-dilution ?"), "fr")
    assert raw.value in {"yes", "no", None} and "Swing_Pricing" in raw.evidence


def test_bindings_learn_which_column_was_answered(tmp_path, client):
    """Question que l'ontologie ne lit pas, répondue pour 5 fonds avec la valeur d'une même colonne Fabric."""
    from datetime import date

    from merlin.rfi.layout import detect
    from merlin.rfi.precedents import PrecedentIndex, PrecedentStore
    from merlin.rfi.precedents.advisor import FundResolver
    from merlin.rfi.precedents.bindings import BindingIndex, BindingMiner
    from merlin.rfi.precedents.importers import import_lot02
    from merlin.rfi.ontology import load_ontology
    from merlin.rfi.service import RfiStore, analyze, fund_directory
    from merlin.state import get_state

    data = get_state().data
    directory = fund_directory(data)
    tickers = data.query("SELECT s.ISIN_Code, s.Bloomberg_Ticker FROM dbo.PI_OUT_Share s", {})
    by_isin = dict(zip(tickers["ISIN_Code"], tickers["Bloomberg_Ticker"]))
    funds = [(f["pid"], f["shares"][0]["isin"], f["name"]) for f in directory if f["shares"] and by_isin.get(f["shares"][0]["isin"])][:6]
    current, others = funds[0], funds[1:]
    examples = [_example(i, "Code maison du support", by_isin[f[1]], f, ref=f"t{i}") for i, f in enumerate(others, start=1)]
    examples += [_example(10 + i, "Le support est-il suivi par l'équipe ?", "Oui", f, ref=f"u{i}") for i, f in enumerate(others, start=1)]
    store = PrecedentStore(tmp_path / "p.sqlite")
    import_lot02(store, {"answer_examples": examples, "identity_issues": []})
    ontology = load_ontology(data.catalog)
    built = BindingMiner(data, ontology, store, FundResolver(directory)).build()
    by_q = {b.question: b for b in built}
    code = by_q["Code maison du support"]
    assert code.target == "PI_OUT_Share.Bloomberg_Ticker" and code.support == 5 and code.rate == 1.0 and code.status == "candidate"
    weak = by_q.get("Le support est-il suivi par l'équipe ?")
    assert weak is None or not weak.usable  # même réponse partout : rien ne prouve la colonne

    index = BindingIndex(tmp_path / "bindings.json")
    index.save(built)
    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    ws.append(["Code maison du support", None])
    path = tmp_path / "rfi.xlsx"
    wb.save(path)
    r = analyze(data, RfiStore(tmp_path / "rfi"), path, detect(path), current[0], current[1], date.today().isoformat(), None, None,
                PrecedentIndex(store), bindings=index)
    q = r["questions"][0]
    assert q["answer"] == by_isin[current[1]] and q["status"] == "auto" and q["source"] == "liaison apprise"
    assert any("5 fonds sur 5" in reason for reason in q["reasons"])
    index.set_status(code.id, "rejected")
    again = analyze(data, RfiStore(tmp_path / "rfi"), path, detect(path), current[0], current[1], date.today().isoformat(), None, None,
                    PrecedentIndex(store), bindings=index)
    assert again["questions"][0]["source"] != "liaison apprise"  # une liaison rejetée n'est plus utilisée
