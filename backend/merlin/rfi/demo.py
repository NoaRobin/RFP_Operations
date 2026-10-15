"""RFI de démonstration réalistes (fictifs), construits comme ceux des clients :
cases pré-remplies de consignes (« Indiquer… », « [à compléter] », « Oui / Non », « jj/mm/aaaa »), listes déroulantes
(en dur et vers un onglet caché), cellule au format pourcentage, grille « une ligne par part », et côté Word :
liste déroulante (contrôle de contenu), cases à cocher « ☐ Yes ☐ No », espaces réservés.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from ..data.access import DataAccess
from .service import fund_directory

INK, FILL = "1C355E", "FFF2CC"

# (question, consigne pré-remplie, liste déroulante, format de nombre)
QUESTIONS_FR: list[tuple[str, str | None, str | None, str | None]] = [
    ("IDENTIFICATION DU FONDS", None, None, None),
    ("Nom du fonds", "Indiquer le nom complet du fonds", None, None),
    ("Code ISIN de la part proposée", "{isin}", None, None),
    ("Forme juridique", "Sélectionner", '"FCP,SICAV,Compartiment de SICAV,Autre"', None),
    ("Le fonds est-il un OPCVM ?", None, '"Oui,Non"', None),
    ("Pays de domiciliation", "Indiquer le pays", None, None),
    ("Date de lancement du fonds", "jj/mm/aaaa", None, None),
    ("Devise de référence du fonds", None, "Listes!$A$1:$A$4", None),
    ("Classification SFDR", None, "Listes!$B$1:$B$3", None),
    ("Le fonds dispose-t-il du label ISR ?", "Oui / Non", None, None),
    ("Indicateur synthétique de risque (SRI, de 1 à 7)", None, '"1,2,3,4,5,6,7"', None),
    ("Durée de placement recommandée", None, '"< 1 an,1 à 3 ans,3 à 5 ans,> 5 ans"', None),
    ("GESTION", None, None, None),
    ("Nom du gérant principal", "Indiquer Prénom NOM", None, None),
    ("Dépositaire", "[à compléter]", None, None),
    ("Commissaire aux comptes", "[à compléter]", None, None),
    ("Fréquence de valorisation", None, '"Quotidienne,Hebdomadaire,Mensuelle"', None),
    ("FRAIS DE LA PART", None, None, None),
    ("Frais courants ex post de la part", None, None, "0.00%"),
    ("Frais de gestion financière maximum (%)", "x,xx %", None, None),
    ("Commission de surperformance", None, '"Oui,Non"', None),
    ("Droits d'entrée maximum", None, None, None),
    ("Affectation des résultats", None, "Listes!$C$1:$C$3", None),
    ("Délai de règlement des rachats", "Indiquer J+n", None, None),
    ("ENCOURS, PERFORMANCE ET RISQUE", None, None, None),
    ("Encours du fonds au dernier mois (M€)", None, None, None),
    ("Performance de la part sur 1 an glissant (%)", None, None, None),
    ("Volatilité de la part sur 1 an (%)", None, None, None),
    ("Nombre de lignes en portefeuille", None, None, None),
    ("ESG", None, None, None),
    ("Le fonds exclut-il le tabac ?", None, '"Oui,Non"', None),
    ("Part minimale d'investissements durables (%)", None, None, None),
    ("DISTRIBUTION", None, None, None),
    ("Pays d'enregistrement de la part", "Lister les pays", None, None),
    ("Décrivez la philosophie d'investissement et le processus de sélection des titres.", None, None, None),
]

GRID_HEADERS = ["ISIN", "Nom de la part", "Devise", "Frais courants (%)", "Minimum de souscription initiale", "Date de lancement de la part", "Affectation des résultats"]


def _fund(data: DataAccess) -> tuple[str, str, str, list[dict]]:
    for item in fund_directory(data):
        if len(item["shares"]) >= 2:
            share = item["shares"][0]
            return item["name"], share["isin"], share["name"], item["shares"]
    item = next((i for i in fund_directory(data) if i["shares"]), None)
    if item:
        return item["name"], item["shares"][0]["isin"], item["shares"][0]["name"], item["shares"]
    return "Fonds de démonstration", "QZ0000000000", "Part C", []


def demo_xlsx(data: DataAccess) -> tuple[str, bytes]:
    fund, isin, _, shares = _fund(data)
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire"
    ws["A1"] = f"Questionnaire de sélection — Consultant Fictif — {fund} (démonstration, données fictives)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:D1")
    ws.append([])
    ws.append(["Réf.", "Question", "Réponse", "Commentaires"])
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=INK)
    lists = wb.create_sheet("Listes")
    for i, v in enumerate(["EUR", "USD", "GBP", "CHF"], 1):
        lists.cell(i, 1, v)
    for i, v in enumerate(["Article 6", "Article 8", "Article 9"], 1):
        lists.cell(i, 2, v)
    for i, v in enumerate(["Capitalisation", "Distribution", "Mixte"], 1):
        lists.cell(i, 3, v)
    lists.sheet_state = "hidden"
    n = 0
    for text, prefill, dropdown, number_format in QUESTIONS_FR:
        if text.isupper():
            ws.append(["", text, "", ""])
            ws.cell(ws.max_row, 2).font = Font(bold=True)
            continue
        n += 1
        ws.append([f"{n}", text, prefill.format(isin=isin) if prefill else None, None])
        answer = ws.cell(ws.max_row, 3)
        answer.fill = PatternFill("solid", fgColor=FILL)
        if prefill and prefill != "{isin}":
            answer.font = Font(italic=True, color="808080")
        if number_format:
            answer.number_format = number_format
        if dropdown:
            dv = DataValidation(type="list", formula1=dropdown, allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(answer.coordinate)
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 62
    ws.column_dimensions["C"].width = 38
    ws.column_dimensions["D"].width = 30
    for row in ws.iter_rows(min_row=4):
        row[1].alignment = Alignment(wrap_text=True)

    grid = wb.create_sheet("Parts", 1)
    grid.append(GRID_HEADERS)
    for cell in grid[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=INK)
    for share in shares[:3]:
        grid.append([share["isin"]] + [None] * (len(GRID_HEADERS) - 1))
    for col in "ABCDEFG":
        grid.column_dimensions[col].width = 24
    buffer = io.BytesIO()
    wb.save(buffer)
    return f"RFI_demo_{isin}.xlsx", buffer.getvalue()


def _sdt_dropdown(options: list[str], placeholder: str) -> str:
    items = "".join(f'<w:listItem w:displayText="{o}" w:value="{o}"/>' for o in options)
    return (f'<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:sdtPr><w:showingPlcHdr/>'
            f'<w:dropDownList><w:listItem w:displayText="Choose an item." w:value=""/>{items}</w:dropDownList></w:sdtPr>'
            f'<w:sdtContent><w:r><w:rPr><w:color w:val="808080"/></w:rPr><w:t>{placeholder}</w:t></w:r></w:sdtContent></w:sdt>')


def demo_docx(data: DataAccess) -> tuple[str, bytes]:
    import docx
    from docx.oxml import parse_xml
    from docx.shared import Pt

    fund, isin, share, _ = _fund(data)
    d = docx.Document()
    d.add_heading("Request for Information — Due diligence questionnaire (demo, fictitious data)", level=1)
    d.add_paragraph(f"Fund: {fund} — share class {share} ({isin})")
    d.add_heading("1. General information", level=2)
    table = d.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Question"
    table.rows[0].cells[1].text = "Answer"
    rows = [
        ("Fund name", fund),
        ("Legal form", "Please insert"),
        ("Fund launch date", "[DD/MM/YYYY]"),
        ("Base currency", "Please specify"),
        ("SFDR classification", None),  # liste déroulante (contrôle de contenu)
        ("Lead portfolio manager", "Please insert"),
        ("Custodian", "[Please insert]"),
        ("Ongoing charges (OCF, %)", "x.xx%"),
        ("Minimum initial investment", "Please insert"),
        ("Fund AUM (EUR m)", "Please insert"),
        ("Number of holdings", ""),
        ("Does the fund apply swing pricing?", "[Yes/No]"),
        ("Please describe your ESG integration approach in detail.", ""),
    ]
    for text, answer in rows:
        row = table.add_row()
        row.cells[0].text = text
        if answer is None:
            p = row.cells[1].paragraphs[0]
            p._p.append(parse_xml(_sdt_dropdown(["Article 6", "Article 8", "Article 9"], "Choose an item.")))
        else:
            row.cells[1].text = answer
    d.add_heading("2. Dealing", level=2)
    d.add_paragraph("Is the fund UCITS compliant?  ☐ Yes  ☐ No")
    d.add_paragraph("Distribution policy:  ☐ Accumulation  ☐ Distribution")
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
