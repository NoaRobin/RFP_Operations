"""Génère un questionnaire RFP de démonstration à partir de la source de données courante."""
from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ..data.access import DataAccess

YELLOW = PatternFill("solid", fgColor="FFF2CC")
HEADER = PatternFill("solid", fgColor="1F3864")


def build_demo_questionnaire(data: DataAccess) -> bytes:
    parts = data.query(
        """
        SELECT TOP 14 a.CODE_ISIN_PART, a.NOM_PART, a.DEVISE_VL
        FROM dbo.JUMP_portfolio_aum a
        WHERE a.DATE_VL = (SELECT MAX(DATE_VL) FROM dbo.JUMP_portfolio_aum)
        ORDER BY a.ACTIF_NET_PART_EURO DESC
        """
    )
    instruments = data.query(
        """
        SELECT TOP 12 h.CODE_ISIN_INSTRUMENT, MAX(h.MONTANT_DEVISE_FONDS) AS m
        FROM dbo.JUMP_portfolio_holdings h
        WHERE h.CODE_ISIN_INSTRUMENT IS NOT NULL
          AND h.DATE_INVENTAIRE = (SELECT MAX(DATE_INVENTAIRE) FROM dbo.JUMP_portfolio_holdings)
        GROUP BY h.CODE_ISIN_INSTRUMENT
        ORDER BY m DESC
        """
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Fund Information"
    ws["A1"] = "Request for Proposal — Section 4 : Fund information (démonstration, données fictives)"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Merci de compléter les cellules en jaune. Date d'arrêté demandée : {date.today():%d/%m/%Y}"
    headers = ["Code ISIN", "Nom de la part", "Devise", "Encours de la part (EUR)", "Encours total du fonds (EUR)",
               "VL", "Date de VL", "Indice de référence", "Nombre de lignes", "Commentaire du gérant"]
    ws.append([])
    ws.append(headers)
    for cell in ws[4]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for index, row in enumerate(parts.itertuples(index=False)):
        name = row.NOM_PART if index % 4 == 0 else None  # quelques valeurs déjà présentes
        ccy = row.DEVISE_VL if index % 3 == 0 else None
        ws.append([row.CODE_ISIN_PART, name, ccy, None, None, None, None, "?" if index % 5 == 0 else None, None, None])
        for col in range(2, 10):
            if ws.cell(ws.max_row, col).value in (None, "?"):
                ws.cell(ws.max_row, col).fill = YELLOW
    ws.cell(ws.max_row + 2, 1, "Total encours (formule, ne pas modifier)")
    ws.cell(ws.max_row, 4, f"=SUM(D5:D{4 + len(parts)})")
    for letter, width in zip("ABCDEFGHIJ", (16, 42, 9, 22, 24, 12, 13, 34, 16, 30)):
        ws.column_dimensions[letter].width = width

    ws2 = wb.create_sheet("Top Holdings")
    ws2.append(["Top 10 holdings — please provide the details below"])
    ws2["A1"].font = Font(bold=True, size=13)
    ws2.append([])
    ws2.append(["ISIN instrument", "Security name", "Asset class", "Currency", "Bloomberg ticker"])
    for cell in ws2[3]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), HEADER
    for row in instruments.itertuples(index=False):
        ws2.append([row.CODE_ISIN_INSTRUMENT, None, None, None, None])
    for letter, width in zip("ABCDE", (18, 40, 16, 10, 22)):
        ws2.column_dimensions[letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
