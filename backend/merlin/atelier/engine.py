"""Application d'une recette : calcul des changements (aperçu) et écriture d'une nouvelle version."""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import column_index_from_string

from ..data.access import DataAccess
from .analyzer import display, is_empty
from .extractions import EXCEL_FORMATS, get_extractions, run_extraction

RECIPE_STEPS = ["Lecture du classeur", "Extractions Fabric", "Calcul des valeurs", "Écriture de la nouvelle version"]
CHANGE_FILL = PatternFill("solid", fgColor="E8DDFB")


class RecipeError(ValueError):
    pass


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= max(1e-6, abs(float(b)) * 1e-9)
    if hasattr(a, "date") and isinstance(b, date):
        a = a.date()
    return str(a).strip() == str(b).strip()


def compute_changes(data: DataAccess, workbook_path: Path, recipe: dict[str, Any], log=None) -> dict[str, Any]:
    catalog = get_extractions(data.catalog)
    sheet = recipe.get("sheet")
    key_col = recipe.get("key_column")
    header_row = int(recipe.get("header_row") or 1)
    mappings = recipe.get("mappings") or []
    as_of = recipe.get("as_of") or date.today().isoformat()
    overwrite = bool(recipe.get("overwrite", False))
    if not sheet or not key_col:
        raise RecipeError("Choisissez une feuille et une colonne clé.")
    if not mappings:
        raise RecipeError("Aucune correspondance : glissez au moins une extraction sur une colonne.")

    wb_values = load_workbook(workbook_path, data_only=True)
    wb_formulas = load_workbook(workbook_path, data_only=False)
    if sheet not in wb_values.sheetnames:
        raise RecipeError(f"Feuille introuvable : {sheet}")
    ws, wsf = wb_values[sheet], wb_formulas[sheet]
    key_index = column_index_from_string(key_col)

    rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        value = ws.cell(r, key_index).value
        if not is_empty(value):
            rows.append((r, str(value).strip().upper()))

    lookups: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        extraction = catalog.extractions.get(mapping["extraction"])
        if extraction is None:
            raise RecipeError(f"Extraction inconnue : {mapping['extraction']}")
        if extraction.id not in lookups:
            lookups[extraction.id] = run_extraction(data, extraction, as_of)
            if log:
                log.info("%s : %d valeur(s) trouvée(s)", extraction.label, len(lookups[extraction.id]))

    changes, stats = [], {"fill": 0, "overwrite": 0, "conflict": 0, "unchanged": 0, "not_found": 0, "protected": 0}
    for mapping in mappings:
        extraction = catalog.extractions[mapping["extraction"]]
        col_index = column_index_from_string(mapping["column"])
        lookup = lookups[extraction.id]
        for r, key in rows:
            before = ws.cell(r, col_index).value
            after = lookup.get(key)
            if str(wsf.cell(r, col_index).value or "").startswith("="):
                status = "protected"
            elif after is None:
                status = "not_found"
            elif is_empty(before):
                status = "fill"
            elif _same(before, after):
                status = "unchanged"
            else:
                status = "overwrite" if overwrite else "conflict"
            stats[status] += 1
            changes.append({
                "cell": f"{mapping['column']}{r}", "row": r, "column": mapping["column"], "key": key,
                "extraction": extraction.id, "format": extraction.format, "status": status,
                "before": display(before), "after": display(after),
                "raw_after": after.isoformat() if isinstance(after, date) else after,
            })
    return {"sheet": sheet, "as_of": as_of, "rows": len(rows), "changes": changes, "stats": stats}


def write_version(workbook_path: Path, target: Path, recipe: dict[str, Any], result: dict[str, Any]) -> int:
    keep_vba = workbook_path.suffix.lower() == ".xlsm"
    wb = load_workbook(workbook_path, keep_vba=keep_vba)
    ws = wb[result["sheet"]]
    highlight = bool(recipe.get("highlight_changes", False))
    written = 0
    for change in result["changes"]:
        if change["status"] not in {"fill", "overwrite"}:
            continue
        cell = ws[change["cell"]]
        value = change["raw_after"]
        if change["format"] == "date" and isinstance(value, str):
            value = date.fromisoformat(value[:10])
        cell.value = value
        fmt = EXCEL_FORMATS.get(change["format"])
        if fmt and cell.number_format in ("General", None):
            cell.number_format = fmt
        if highlight:
            cell.fill = CHANGE_FILL
        written += 1
    wb.save(target)
    return written


def run_recipe(ctx, recipe: dict[str, Any], workbook_dir: Path) -> None:
    from .store import AtelierStore

    meta = json.loads((workbook_dir / "meta.json").read_text(encoding="utf-8"))
    original = AtelierStore.original_path(workbook_dir)
    recipe = {**recipe, "as_of": recipe.get("as_of") or date.today().isoformat()}

    with ctx.step("Lecture du classeur"):
        ctx.log.info("Classeur : %s — feuille « %s »", meta["filename"], recipe.get("sheet"))
        ctx.log.info("Date d'arrêté : %s", recipe["as_of"])

    with ctx.step("Extractions Fabric"):
        result = compute_changes(ctx.data, original, recipe, log=ctx.log)

    with ctx.step("Calcul des valeurs"):
        s = result["stats"]
        ctx.log.info("%d à remplir, %d à remplacer, %d identiques, %d sans valeur, %d conflits laissés intacts, %d formules protégées",
                     s["fill"], s["overwrite"], s["unchanged"], s["not_found"], s["conflict"], s["protected"])
        if s["not_found"]:
            ctx.log.warning("%d cellule(s) sans valeur dans Fabric : vérifiez les clés concernées.", s["not_found"])

    with ctx.step("Écriture de la nouvelle version"):
        from .store import AtelierStore as _S

        target, number = _S(workbook_dir.parent.parent).next_version_path(workbook_dir, meta["filename"])
        written = write_version(original, target, recipe, result)
        info = {"version": number, "run_id": ctx.job_id, "recipe_id": recipe.get("id"), "recipe_name": recipe.get("name"),
                "as_of": recipe["as_of"], "written": written, "by": ctx.user, "stats": result["stats"]}
        target.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        copy = ctx.output_dir / target.name
        shutil.copy2(target, copy)
        ctx.register_file(copy, "excel", f"Version {number} — {meta['filename']}")
        ctx.log.success("Version %d écrite : %d cellule(s) mises à jour. L'original est intact.", number, written)
        changed = [c for c in result["changes"] if c["status"] in {"fill", "overwrite", "conflict", "not_found"}]
        if changed:
            import pandas as pd

            journal = pd.DataFrame([{"Cellule": c["cell"], "Clé": c["key"], "Extraction": c["extraction"],
                                     "Avant": c["before"], "Après": c["after"], "Statut": c["status"]} for c in changed])
            ctx.show_table(journal, "Journal des modifications")
            ctx.save_excel({"Journal": journal}, f"journal_{target.stem}.xlsx", label="Journal des modifications")
    ctx.set_summary(f"Version {number} générée : {written} cellule(s) remplie(s).", written=written, version=number)
