"""Analyse de la structure d'un classeur : feuilles, en-têtes, colonnes clés, cellules à remplir,
et propositions de correspondance avec le catalogue d'extractions."""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter

from .extractions import ExtractionCatalog

GRID_MAX_ROWS = 80
GRID_MAX_COLS = 26
DATA_MAX_ROWS = 5000
PLACEHOLDERS = {"?", "??", "tbd", "tbc", "a remplir", "a completer", "n/a ?", "xxx", "[a remplir]", "to be completed", "-"}
STOP_WORDS = {"de", "la", "le", "les", "du", "des", "d", "l", "en", "the", "of", "in", "a", "au", "aux", "par", "per", "et", "and"}


def norm(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return " ".join(value.split())


def tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if t not in STOP_WORDS and len(t) > 1}


def similarity(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = tokens(a), tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    contained = 0.85 if (f" {nb} " in f" {na} " or f" {na} " in f" {nb} ") and min(len(na), len(nb)) >= 3 else 0.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, contained, ratio * 0.9)


def display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y") if value.time() == datetime.min.time() else value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",") if abs(value) >= 1000 else f"{value:g}".replace(".", ",")
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and (not value.strip() or norm(value) in PLACEHOLDERS or value.strip() in PLACEHOLDERS))


def _is_highlight(cell: Cell) -> bool:
    fill = cell.fill
    if not fill or fill.fill_type != "solid":
        return False
    color = (fill.fgColor.rgb or "") if fill.fgColor is not None and fill.fgColor.type == "rgb" else ""
    color = str(color)[-6:].upper()
    return color in {"FFFF00", "FFFF99", "FFF2CC", "FFEB9C", "FFFFCC", "FFE699", "FFD966"}


def detect_header_row(rows: list[list[Any]]) -> int:
    """Index (1-based) de la ligne d'en-tête la plus plausible parmi les 30 premières."""
    best, best_score = 1, -1.0
    for index, row in enumerate(rows[:30], start=1):
        texts = [v for v in row if isinstance(v, str) and v.strip() and not re.fullmatch(r"[\d\s.,%-]+", v)]
        if len(texts) < 2:
            continue
        nxt = rows[index] if index < len(rows) else []
        follow = sum(1 for v in nxt if v not in (None, "")) / max(len(texts), 1)
        score = len(texts) + min(follow, 1.0) * 1.5 - 0.02 * index
        if score > best_score:
            best, best_score = index, score
    return best


def analyze_sheet(ws, ws_formulas, extractions: ExtractionCatalog, known_keys: dict[str, set[str]],
                  header_row: int | None = None) -> dict[str, Any]:
    max_row = min(ws.max_row or 1, DATA_MAX_ROWS)
    max_col = min(ws.max_column or 1, 200)
    values = [[ws.cell(r, c).value for c in range(1, max_col + 1)] for r in range(1, min(max_row, 40) + 1)]
    header_row = header_row or detect_header_row(values)

    headers = {c: ws.cell(header_row, c).value for c in range(1, max_col + 1)}
    last_data_row = header_row
    for r in range(max_row, header_row, -1):
        if any(ws.cell(r, c).value not in (None, "") for c in range(1, max_col + 1)):
            last_data_row = r
            break
    data_rows = list(range(header_row + 1, last_data_row + 1))

    # ----------------------------------------------------------------- colonnes clés
    key_candidates = []
    for c, header in headers.items():
        col_values = [ws.cell(r, c).value for r in data_rows]
        non_empty = [str(v).strip().upper() for v in col_values if not is_empty(v)]
        if not non_empty:
            continue
        for kt in extractions.key_types.values():
            header_score = max((similarity(str(header or ""), s) for s in [kt.label, *kt.synonyms]), default=0)
            pattern_ratio = sum(1 for v in non_empty if kt.pattern and kt.pattern.match(v)) / len(non_empty) if kt.pattern else 0
            known = known_keys.get(kt.id, set())
            known_ratio = sum(1 for v in non_empty if v in known) / len(non_empty) if known else 0
            score = 0.45 * header_score + 0.35 * pattern_ratio + 0.6 * known_ratio
            if score >= 0.4:
                key_candidates.append({
                    "column": get_column_letter(c), "index": c, "key_type": kt.id, "score": round(score, 3),
                    "recognized": sum(1 for v in non_empty if v in known), "total": len(non_empty),
                })
    key_candidates.sort(key=lambda k: k["score"], reverse=True)
    key = key_candidates[0] if key_candidates else None
    key_rows = [r for r in data_rows if key and not is_empty(ws.cell(r, key["index"]).value)] if key else []

    # ----------------------------------------------------------------- colonnes & propositions
    columns, targets = [], []
    used_extractions: set[str] = set()
    pool = extractions.for_key(key["key_type"]) if key else [e for e in extractions.extractions.values() if not e.problems]
    for c, header in headers.items():
        letter = get_column_letter(c)
        if header in (None, "") and all(ws.cell(r, c).value in (None, "") for r in data_rows[:50]):
            continue
        is_key = bool(key and key["index"] == c)
        rows_scope = key_rows or data_rows
        empty_cells = [r for r in rows_scope if is_empty(ws.cell(r, c).value) and not str(ws_formulas.cell(r, c).value or "").startswith("=")]
        formulas = sum(1 for r in rows_scope if str(ws_formulas.cell(r, c).value or "").startswith("="))
        highlighted = [r for r in rows_scope if _is_highlight(ws_formulas.cell(r, c))]
        suggestions = []
        if not is_key and header not in (None, ""):
            scored = []
            for e in pool:
                score = max(similarity(str(header), cand) for cand in [e.label, *e.synonyms])
                if score >= 0.5:
                    scored.append({"extraction": e.id, "label": e.label, "score": round(score, 3)})
            suggestions = sorted(scored, key=lambda s: s["score"], reverse=True)[:3]
        proposed = None
        if suggestions and suggestions[0]["score"] >= 0.62 and suggestions[0]["extraction"] not in used_extractions:
            proposed = suggestions[0]["extraction"]
            used_extractions.add(proposed)
        columns.append({
            "letter": letter, "index": c, "header": display(header), "is_key": is_key,
            "empty": len(empty_cells), "filled": len(rows_scope) - len(empty_cells) - formulas, "formulas": formulas,
            "highlighted": len(highlighted), "suggestions": suggestions, "proposed": proposed,
            "samples": [display(ws.cell(r, c).value) for r in rows_scope if not is_empty(ws.cell(r, c).value)][:3],
        })
        if not is_key and header not in (None, ""):
            for r in sorted(set(empty_cells) | set(highlighted)):
                targets.append(f"{letter}{r}")

    # ----------------------------------------------------------------- grille d'aperçu
    grid_cols = min(max_col, GRID_MAX_COLS)
    grid_rows = min(max(last_data_row, header_row), GRID_MAX_ROWS)
    grid = []
    for r in range(1, grid_rows + 1):
        row = []
        for c in range(1, grid_cols + 1):
            raw = ws.cell(r, c).value
            formula = str(ws_formulas.cell(r, c).value or "").startswith("=")
            row.append({"v": display(raw), "f": formula, "n": isinstance(raw, (int, float)) and not isinstance(raw, bool)})
        grid.append(row)

    return {
        "name": ws.title, "max_row": last_data_row, "max_col": max_col, "header_row": header_row,
        "data_rows": len(data_rows), "key": key, "key_candidates": key_candidates[:5], "key_rows": len(key_rows),
        "columns": columns, "targets": targets[:2000], "target_count": len(targets),
        "grid": {"rows": grid, "cols": [get_column_letter(c) for c in range(1, grid_cols + 1)],
                 "truncated_rows": last_data_row > grid_rows, "truncated_cols": max_col > grid_cols},
    }


def analyze_workbook(path: Path, extractions: ExtractionCatalog, known_keys: dict[str, set[str]],
                     overrides: dict[str, int] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    wb_values = load_workbook(path, data_only=True, read_only=False)
    wb_formulas = load_workbook(path, data_only=False, read_only=False)
    sheets = []
    for ws in wb_values.worksheets:
        if ws.sheet_state != "visible":
            continue
        sheets.append(analyze_sheet(ws, wb_formulas[ws.title], extractions, known_keys, overrides.get(ws.title)))
    best = max(sheets, key=lambda s: (bool(s["key"]), sum(1 for c in s["columns"] if c["proposed"]), s["target_count"]), default=None)
    return {"sheets": sheets, "suggested_sheet": best["name"] if best else None}
