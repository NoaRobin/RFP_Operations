"""Documents officiels : lecture du DIC PRIIPs, recherche sur le site, recoupement avec Fabric. Données fictives (QZ…)."""
import io
from datetime import date

import httpx
from openpyxl import Workbook

from pdfgen import kid_lines, make_pdf


def _funds(client):
    funds = {f["pid"]: f for f in client.get("/api/rfi/funds").json()}
    a = funds["PI-700"]
    return a["pid"], a["shares"][0]["isin"], a["name"]


def _write_kid(folder, isin, **kw):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"DIC_{isin}_FR.pdf"
    path.write_bytes(make_pdf(kid_lines(isin, "Part fictive", **kw)))
    return path


def test_kid_extraction_reads_regulated_fields(tmp_path):
    from merlin.rfi.documents.extract_kid import extract
    from merlin.rfi.documents.model import DocumentRef
    from merlin.rfi.documents.text import pages_text

    path = _write_kid(tmp_path, "QZ2228LUXT99")
    facts, problems = extract(pages_text(path), DocumentRef("QZ2228LUXT99", "kid", "DIC"), "QZ2228LUXT99")
    assert not problems
    values = {k: f.value for k, f in facts.items()}
    assert values["kid.sri"] == 3 and values["kid.rhp"] == "5 ans" and values["kid.date"] == "2026-02-15"
    assert values["kid.entry_costs"] == 2.0 and values["kid.exit_costs"] == 0.0  # « pas de coûts de sortie » explicite
    assert values["kid.ongoing_costs"] == 1.35 and values["kid.transaction_costs"] == 0.12 and values["kid.performance_fee"] == 0.0
    assert facts["kid.ongoing_costs"].page == 2 and "1,35" in facts["kid.ongoing_costs"].snippet


def test_kid_of_another_share_is_refused(tmp_path):
    from merlin.rfi.documents.extract_kid import extract
    from merlin.rfi.documents.model import DocumentRef
    from merlin.rfi.documents.text import pages_text

    path = _write_kid(tmp_path, "QZYM908XINV7")
    facts, problems = extract(pages_text(path), DocumentRef("QZ2228LUXT99", "kid", "DIC"), "QZ2228LUXT99")
    assert facts == {} and "absent" in problems[0]


def test_website_finder_follows_fund_page_to_share_documents(tmp_path):
    from merlin.rfi.documents.finder import WebsiteDocumentFinder

    isin = "QZ2228LUXT99"
    pdf = make_pdf(kid_lines(isin, "Part fictive"))
    pages = {
        "https://site.test/en/our-funds/avalon-actions-europe/": '<a href="/en/our-funds/avalon-actions-europe/c-eur/">C EUR</a>'
                                                               '<a href="/en/our-funds/avalon-actions-europe/i-eur/">I EUR</a>',
        "https://site.test/en/our-funds/avalon-actions-europe/c-eur/": f"<p>ISIN {isin}</p><a href='/stock/file/kid-c-fr.pdf'>DIC PRIIPs (FR)</a>"
                                                                     "<a href='/stock/file/prospectus.pdf'>Prospectus</a><a href='/stock/file/report.pdf'>Reporting</a>",
        "https://site.test/en/our-funds/avalon-actions-europe/i-eur/": "<p>ISIN QZYM908XINV7</p><a href='/stock/file/kid-i.pdf'>KID</a>",
    }

    def get(url):
        if url.endswith(".pdf"):
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(200 if url in pages else 404, text=pages.get(url, ""), headers={"content-type": "text/html"})

    finder = WebsiteDocumentFinder("https://site.test", get=get)
    refs = finder.find(isin, "Avalon Actions Europe", "C EUR")
    kinds = {r.kind: r for r in refs}
    assert set(kinds) == {"kid", "prospectus"} and "kid-i" not in kinds["kid"].url and kinds["kid"].lang == "fr"
    target = finder.fetch(kinds["kid"], tmp_path / "kid.pdf")
    assert target.read_bytes().startswith(b"%PDF")


def test_prospectus_reads_only_the_requested_sub_fund(tmp_path):
    from merlin.rfi.documents.extract_prospectus import extract
    from merlin.rfi.documents.model import DocumentRef
    from merlin.rfi.documents.text import pages_text

    isins = [f"QZ00000000{i:02d}" for i in range(10)]
    pdf = make_pdf([
        ["Prospectus de la SICAV fictive", "Parts : " + ", ".join(isins)],
        ["Compartiment Alpha Imaginaire", "Centralisation des ordres chaque jour avant 11h00.", "Règlement à J+2.",
         "Frais de gestion financière : 1,50 % TTC maximum.", "Dépositaire : Banque du Lac"],
        ["Compartiment Beta Imaginaire", "Centralisation des ordres chaque jour avant 14h30.", "Règlement à J+3.",
         "Frais de gestion financière : 0,80 % TTC maximum."],
    ])
    path = tmp_path / "prospectus.pdf"
    path.write_bytes(pdf)
    facts, problems = extract(pages_text(path), DocumentRef(isins[0], "prospectus", "Prospectus"), isins[0], "Compartiment Beta Imaginaire",
                              ["Compartiment Alpha Imaginaire", "Compartiment Beta Imaginaire"])
    values = {k: f.value for k, f in facts.items()}
    assert values["prospectus.cutoff"] == "14:30" and values["prospectus.settlement"] == "J+3"
    assert values["prospectus.max_management_fee"] == 0.8 and "prospectus.depositary" not in values  # section Alpha ignorée
    _, missing = extract(pages_text(path), DocumentRef(isins[0], "prospectus", "P"), "QZ9999999999", "Fonds Inconnu", [])
    assert missing


def test_document_confirms_contradicts_or_fills_fabric(tmp_path, client):
    from merlin.rfi.documents.finder import FolderDocumentFinder
    from merlin.rfi.documents.service import DocumentService
    from merlin.rfi.layout import detect
    from merlin.rfi.ontology import load_ontology
    from merlin.rfi.service import RfiStore, analyze
    from merlin.rfi.understand import understand
    from merlin.rfi.values import Values
    from merlin.state import get_state

    pid, isin, _ = _funds(client)
    data = get_state().data
    o = load_ontology(data.catalog)
    vals = Values(data, o, pid, isin, date.today())
    fabric_ongoing = vals.get(o.concepts["part.frais_courants_ex_ante"], understand(o, "Frais courants ex ante"), "fr").value
    fabric_sri = vals.get(o.concepts["fonds.sri"], understand(o, "SRI"), "fr").value
    other_sri = 1 if str(fabric_sri) != "1" else 2
    docs = tmp_path / "docs"
    ongoing = f"{float(fabric_ongoing):.2f}".replace(".", ",") if fabric_ongoing is not None else "1,35"
    _write_kid(docs, isin, sri=other_sri, ongoing=ongoing, transaction="0,12")
    service = DocumentService(tmp_path / "cache", [FolderDocumentFinder(docs)])

    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    for q in ["Frais courants ex ante de la part", "Indicateur synthétique de risque (SRI)", "Coûts de transaction indiqués dans le DIC"]:
        ws.append([q, None])
    path = tmp_path / "rfi.xlsx"
    wb.save(path)
    r = analyze(data, RfiStore(tmp_path / "rfi"), path, detect(path), pid, isin, date.today().isoformat(), None, None, documents=service)
    by_q = {q["question"]: q for q in r["questions"]}

    ocf = by_q["Frais courants ex ante de la part"]
    if fabric_ongoing is not None:
        assert any("confirmé par le DIC" in x for x in ocf["reasons"]) and any(s.get("check") == "match" for s in ocf["sources"])
    sri = by_q["Indicateur synthétique de risque (SRI)"]  # Fabric et DIC divergent : jamais automatique
    assert sri["status"] == "review" and any("incohérence" in i for i in sri["issues"])
    costs = by_q["Coûts de transaction indiqués dans le DIC"]
    if costs["source"] == "document":  # Fabric vide en démo : repris du DIC, cité, à vérifier
        assert costs["status"] == "review" and "DIC du 15/02/2026, p. 2" in costs["evidence"]
