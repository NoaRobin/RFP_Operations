"""La « liste de courses » vierge (ou pré-remplie avec la liste actuelle) à compléter dans Excel puis réimporter.

Onglet « Liste de courses » : la part se choisit dans une liste déroulante (l'ISIN se remplit tout seul), le document et
le mois aussi. Onglet « Parts » : le référentiel (Product Info). Onglet « Aide » : le mode d'emploi en quelques lignes.
"""
from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .catalog import DOC_TYPES
from .period import RELATIVE_LABELS
from .shopping import Item

HEADERS = ["Part (choisir dans la liste)", "ISIN", "Document", "Mois", "Remplacer le fichier existant", "Nom du fichier (facultatif)"]
ROWS = 300
YELLOW = PatternFill("solid", fgColor="FFD23F")
GREY = PatternFill("solid", fgColor="F2F0EA")


def choice_label(fund: str, share: str, isin: str) -> str:
    return f"{fund} · {share} ({isin})" if share else f"{fund} ({isin})"


def build(directory: list[dict[str, Any]], items: list[Item] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Liste de courses"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = YELLOW
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 32
    for col, width in zip("ABCDEF", (52, 16, 24, 20, 16, 44)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    parts = wb.create_sheet("Parts")
    parts.append(["Choix", "Fonds", "Part", "ISIN"])
    for cell in parts[1]:
        cell.font = Font(bold=True)
        cell.fill = GREY
    labels: dict[str, str] = {}
    for fund in directory:
        for share in fund.get("shares", []):
            label = choice_label(fund["name"], share.get("name", ""), share["isin"])
            labels[share["isin"]] = label
            parts.append([label, fund["name"], share.get("name", ""), share["isin"]])
    for col, width in zip("ABCD", (60, 36, 30, 16)):
        parts.column_dimensions[col].width = width
    last = max(parts.max_row, 2)

    # Lignes déjà dans l'app (export) ; sinon une liste vide prête à remplir
    for n, item in enumerate(items or [], start=2):
        doc = DOC_TYPES[item.kind]
        ws.cell(n, 1, labels.get(item.isin) or choice_label(item.fund or item.isin, item.part, item.isin))
        ws.cell(n, 3, doc.label)
        ws.cell(n, 4, RELATIVE_LABELS.get(item.month, item.month) if doc.needs_month else "")
        ws.cell(n, 5, "Oui" if item.overwrite else "Non")
        ws.cell(n, 6, item.filename)
    for n in range(2, ROWS + 2):  # l'ISIN se déduit de la part choisie (on peut aussi le taper à la main)
        if ws.cell(n, 2).value is None:
            ws.cell(n, 2, f'=IFERROR(INDEX(Parts!$D$2:$D${last},MATCH(A{n},Parts!$A$2:$A${last},0)),"")')
        if ws.cell(n, 5).value is None:
            ws.cell(n, 5, "Non")

    def validation(formula: str, col: str, prompt: str, strict: bool) -> None:
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=strict, showInputMessage=True,
                            promptTitle=HEADERS["ABCDEF".index(col)][:32], prompt=prompt[:255])
        if not strict:
            dv.errorStyle = "information"
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{ROWS + 1}")

    if parts.max_row > 1:
        validation(f"Parts!$A$2:$A${last}", "A", "Tapez les premières lettres du fonds puis choisissez la part.", strict=False)
    validation('"' + ",".join(d.label for d in DOC_TYPES.values()) + '"', "C", "Le document à télécharger.", strict=True)
    validation('"' + ",".join(RELATIVE_LABELS.values()) + '"', "D",
               "Pour les reportings. « Mois précédent » : idéal en boucle. Ou tapez un mois précis : juillet 2026.", strict=False)
    validation('"Oui,Non"', "E", "Oui : le fichier déjà présent dans le dossier est remplacé.", strict=True)

    aide = wb.create_sheet("Aide")
    lines = [
        ("Liste de courses — mode d'emploi", True),
        ("1. Colonne A : choisissez la part dans la liste (tapez le début du nom du fonds). L'ISIN se remplit tout seul.", False),
        ("   Vous pouvez aussi laisser A vide et taper l'ISIN directement en colonne B.", False),
        ("2. Colonne C : le document (DIC, Prospectus, Reporting mensuel, documents SFDR…).", False),
        ("3. Colonne D : seulement pour les reportings. « Mois précédent » = toujours le dernier mois écoulé (parfait pour "
         "programmer la liste chaque mois). Ou un mois précis : « juillet 2026 ».", False),
        ("4. Colonne E : « Oui » pour remplacer un fichier déjà téléchargé. Colonne F : nom du fichier, si vous voulez autre "
         "chose que le nom par défaut.", False),
        ("5. Enregistrez, puis dans l'app : Documents → « Importer un Excel ».", False),
        ("Exemple : Fonds Exemple · C EUR (QZ0000000001) | Reporting mensuel | Mois précédent | Non", False),
    ]
    for n, (text, bold) in enumerate(lines, start=1):
        cell = aide.cell(n, 1, text)
        cell.font = Font(bold=bold, size=13 if bold else 11)
        cell.alignment = Alignment(wrap_text=True)
    aide.column_dimensions["A"].width = 120

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
