"""Aperçu d'un questionnaire pour l'atelier de revue : la feuille telle que le client l'a construite (valeurs seulement),
avec, pour chaque case réponse, l'identifiant de la question correspondante."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries

from .layout import Layout

MAX_ROWS, MAX_COLS = 400, 14


def _text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value).strip()[:300]


def preview(path: Path, layout: Layout) -> dict[str, Any]:
    by_cell: dict[str, str] = {}
    for slot in layout.slots:
        if "!" in slot.location:
            by_cell[slot.location] = slot.id
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        # Word : liste des paragraphes et tableaux repérés (le rendu fidèle reste le fichier lui-même)
        return {"kind": "docx", "sheets": [], "items": [{"id": s.id, "label": s.question, "location": s.location} for s in layout.slots]}
    wb = load_workbook(path, read_only=False, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        used_rows = [int(re.sub(r"\D", "", loc.split("!")[1]) or 0) for loc in by_cell if loc.startswith(ws.title + "!")]
        max_row = min(max([ws.max_row or 1] + used_rows), MAX_ROWS)
        max_col = min(ws.max_column or 1, MAX_COLS)
        merged = {}
        for rng in ws.merged_cells.ranges:
            c1, r1, c2, r2 = range_boundaries(str(rng))
            if r1 <= max_row and c1 <= max_col:
                merged[f"{get_column_letter(c1)}{r1}"] = [min(c2, max_col) - c1 + 1, min(r2, max_row) - r1 + 1]
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        if (r, c) != (r1, c1):
                            merged.setdefault("__hidden__", []).append(f"{get_column_letter(c)}{r}")
        rows = []
        for r in range(1, max_row + 1):
            cells = []
            for c in range(1, max_col + 1):
                ref = f"{get_column_letter(c)}{r}"
                cells.append({"ref": ref, "v": _text(ws.cell(r, c).value), "q": by_cell.get(f"{ws.title}!{ref}")})
            if any(cell["v"] or cell["q"] for cell in cells):
                rows.append({"r": r, "cells": cells})
        widths = [min(48, max(8, int((ws.column_dimensions[get_column_letter(c)].width or 10)))) for c in range(1, max_col + 1)]
        hidden = set(merged.pop("__hidden__", []))
        sheets.append({"name": ws.title, "columns": [get_column_letter(c) for c in range(1, max_col + 1)], "widths": widths,
                       "rows": rows, "merged": merged, "hidden": sorted(hidden),
                       "questions": sum(1 for loc in by_cell if loc.startswith(ws.title + "!"))})
    sheets.sort(key=lambda s: -s["questions"])
    return {"kind": "xlsx", "sheets": sheets, "items": []}
