"""Écriture de fichiers Excel propres (en-têtes stylés, largeurs ajustées, formats)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="2A1B4D")
HEADER_FONT = Font(bold=True, color="F3E3B5")


def write_frames_to_excel(sheets: dict[str, pd.DataFrame], path: Path, number_formats: dict[str, str]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, frame in sheets.items():
        ws = wb.create_sheet(title=str(sheet_name)[:31] or "Feuille")
        columns = [str(c) for c in frame.columns]
        ws.append(columns)
        for row in frame.itertuples(index=False, name=None):
            ws.append([None if (isinstance(v, float) and v != v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in row])
        for cell in ws[1]:
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        if columns:
            ws.auto_filter.ref = ws.dimensions
        for index, name in enumerate(columns, start=1):
            letter = get_column_letter(index)
            sample = [len(name)] + [len(str(v)) for v in frame.iloc[:200, index - 1].tolist()] if len(frame) else [len(name)]
            ws.column_dimensions[letter].width = min(max(sample) + 2, 60)
            fmt = number_formats.get(name)
            if fmt:
                for cell in ws[letter][1:]:
                    cell.number_format = fmt
    if not wb.sheetnames:
        wb.create_sheet("Résultat")
    wb.save(path)
