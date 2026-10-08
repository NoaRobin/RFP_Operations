"""RFI de démonstration (Excel et Word), fictifs, citant un fonds du référentiel courant."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ..data.access import DataAccess
from .service import fund_directory

QUESTIONS_FR = [
    ("Identification", None),
    ("Nom du fonds", "{fund}"),
    ("Code ISIN de la part", "{isin}"),
    ("Forme juridique", None),
    ("Domicile du fonds", None),
    ("Date de création du fonds", None),
    ("Devise de référence du fonds", None),
    ("Classification SFDR", None),
    ("Indicateur de risque (SRI)", None),
    ("Acteurs", None),
    ("Nom du gérant principal", None),
    ("Dépositaire", None),
    ("Commissaire aux comptes", None),
    ("Caractéristiques de la part", None),
    ("Frais de gestion financière (%)", None),
    ("Frais courants", None),
    ("Droits d'entrée maximum", None),
    ("Souscription initiale minimum (EUR)", None),
    ("Heure limite de souscription (cut-off)", None),
    ("Affectation des résultats", None),
    ("Encours et portefeuille", None),
    ("Encours du fonds (en M€)", None),
    ("Date de l'encours", None),
    ("Nombre de lignes en portefeuille", None),
    ("Poids des 10 premières lignes (%)", None),
    ("Décrivez le processus d'investissement du fonds et la philosophie de l'équipe de gestion.", None),
]

QUESTIONS_EN = [
    ("Fund name", "{fund}"),
    ("Legal form", None),
    ("Fund launch date", None),
    ("Base currency", None),
    ("SFDR classification", None),
    ("Lead portfolio manager", None),
    ("Custodian", None),
    ("Management fee", None),
    ("Ongoing charges (OCF)", None),
    ("Minimum investment", None),
    ("Fund AUM (EUR m)", None),
    ("Number of holdings", None),
    ("Please describe your ESG integration approach in detail.", None),
]


def _first_fund(data: DataAccess) -> tuple[str, str, str]:
    for item in fund_directory(data):
        if item["shares"]:
            share = item["shares"][0]
            return item["name"], share["isin"], share["name"]
    return "Fonds de démonstration", "QZ0000000000", "Part C"


def demo_xlsx(data: DataAccess) -> tuple[str, bytes]:
    fund, isin, _ = _first_fund(data)
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire"
    ws["A1"] = "Request for Information — questionnaire consultant (démonstration, données fictives)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:C1")
    ws.append([])
    ws.append(["N°", "Question", "Réponse"])
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1C355E")
    n = 0
    for text, answer in QUESTIONS_FR:
        if answer is None and text in {"Identification", "Acteurs", "Caractéristiques de la part", "Encours et portefeuille"}:
            ws.append(["", text.upper(), ""])
            ws.cell(ws.max_row, 2).font = Font(bold=True)
            continue
        n += 1
        ws.append([n, text, answer.format(fund=fund, isin=isin) if answer else None])
        ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor="FFF2CC")
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["C"].width = 40
    for row in ws.iter_rows(min_row=4):
        row[1].alignment = Alignment(wrap_text=True)
    buffer = io.BytesIO()
    wb.save(buffer)
    return f"RFI_demo_{isin}.xlsx", buffer.getvalue()


def demo_docx(data: DataAccess) -> tuple[str, bytes]:
    import docx
    from docx.shared import Pt

    fund, isin, share = _first_fund(data)
    d = docx.Document()
    d.add_heading("Request for Information — Due diligence (demo, fictitious data)", level=1)
    d.add_paragraph(f"Fund: {fund} — share class {share} ({isin})")
    d.add_heading("1. General information", level=2)
    table = d.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Question"
    table.rows[0].cells[1].text = "Answer"
    for text, answer in QUESTIONS_EN:
        row = table.add_row()
        row.cells[0].text = text
        row.cells[1].text = answer.format(fund=fund) if answer else ""
    d.add_heading("2. Dealing", level=2)
    d.add_paragraph("Subscription cut-off time:")
    d.add_paragraph("Settlement period: ____________")
    d.add_paragraph("What is the share class currency?")
    d.add_paragraph("")
    for p in d.paragraphs:
        for r in p.runs:
            r.font.size = Pt(11)
    buffer = io.BytesIO()
    d.save(buffer)
    return f"RFI_demo_{isin}.docx", buffer.getvalue()
