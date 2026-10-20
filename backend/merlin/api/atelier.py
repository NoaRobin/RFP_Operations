"""API de l'Atelier Excel."""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..atelier.analyzer import analyze_workbook
from ..atelier.demo import build_demo_questionnaire
from ..atelier.engine import RecipeError, compute_changes
from ..atelier.extractions import get_extractions
from ..atelier.ontology_bridge import ontology_for, palette
from ..atelier.store import ALLOWED_SUFFIXES, AtelierStore
from ..data.access import DataError
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api/atelier")
MAX_UPLOAD = 25 * 1024 * 1024
_known: dict[str, Any] = {"at": 0.0, "keys": {}}


def known_keys(s: AppState) -> dict[str, set[str]]:
    """ISIN connus du Lakehouse, pour reconnaître la colonne clé d'un questionnaire (cache 10 min)."""
    if time.time() - _known["at"] > 600:
        try:
            parts = s.data.query("SELECT DISTINCT CODE_ISIN_PART AS k FROM dbo.JUMP_portfolio_aum WHERE CODE_ISIN_PART IS NOT NULL")
            instruments = s.data.query(
                "SELECT DISTINCT CODE_ISIN_INSTRUMENT AS k FROM dbo.JUMP_portfolio_holdings WHERE CODE_ISIN_INSTRUMENT IS NOT NULL"
            )
            _known["keys"] = {
                "isin_part": {str(k).upper() for k in parts["k"]},
                "isin_instrument": {str(k).upper() for k in instruments["k"]},
            }
            _known["at"] = time.time()
        except DataError:
            _known["keys"] = {}
    return _known["keys"]


def _workbook(s: AppState, workbook_id: str):
    try:
        folder = s.store.workbook_dir(workbook_id)
    except FileNotFoundError as error:
        raise not_found("Ce classeur n'est plus dans l'atelier.") from error
    return folder, AtelierStore.original_path(folder)


def _analysis(s: AppState, workbook_id: str, overrides: dict[str, int] | None = None,
              orientations: dict[str, str] | None = None) -> dict[str, Any]:
    folder, original = _workbook(s, workbook_id)
    try:
        analysis = analyze_workbook(original, get_extractions(s.catalog), known_keys(s), overrides, ontology_for(s.data), orientations)
    except Exception as error:  # fichier corrompu, protégé par mot de passe…
        raise bad_request("Impossible de lire ce classeur.", f"Est-il protégé par mot de passe ou corrompu ? ({type(error).__name__})") from error
    return {**s.store.meta(workbook_id), **analysis}


@router.get("/extractions")
def extractions(s: AppState = Depends(state)) -> dict[str, Any]:
    catalog = get_extractions(s.catalog)
    # Extractions Fabric directes, puis tout le modèle du compléteur RFI (concepts de l'ontologie, valeur lue par ISIN)
    return {
        "key_types": [{"id": k.id, "label": k.label} for k in catalog.key_types.values()],
        "extractions": [e.to_dict() for e in catalog.extractions.values()] + palette(ontology_for(s.data)),
    }


@router.get("/workbooks")
def list_workbooks(s: AppState = Depends(state)):
    return s.store.list_workbooks()


@router.post("/workbooks")
async def upload(file: UploadFile = File(...), s: AppState = Depends(state), user: str = Depends(current_user)):
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise bad_request("Fichier trop volumineux (25 Mo maximum).", "Supprimez les onglets inutiles ou envoyez une version allégée.")
    try:
        meta = s.store.save_upload(file.filename or "classeur.xlsx", content, user)
    except ValueError as error:
        raise bad_request(
            f"Format non pris en charge ({error}).",
            f"Formats acceptés : {', '.join(sorted(ALLOWED_SUFFIXES))}. Enregistrez le fichier au format Excel moderne.",
        ) from error
    return _analysis(s, meta["id"])


@router.post("/demo")
def demo(s: AppState = Depends(state), user: str = Depends(current_user)):
    content = build_demo_questionnaire(s.data)
    meta = s.store.save_upload(f"Questionnaire_RFP_demo_{date.today():%Y%m%d}.xlsx", content, user)
    return _analysis(s, meta["id"])


@router.get("/workbooks/{workbook_id}")
def get_workbook(workbook_id: str, sheet: str | None = None, header_row: int | None = None, orientation: str | None = None,
                 s: AppState = Depends(state)):
    overrides = {sheet: header_row} if sheet and header_row else None
    orientations = {sheet: orientation} if sheet and orientation in {"rows", "columns"} else None
    return _analysis(s, workbook_id, overrides, orientations)


@router.delete("/workbooks/{workbook_id}")
def delete_workbook(workbook_id: str, s: AppState = Depends(state)):
    _workbook(s, workbook_id)
    s.store.delete_workbook(workbook_id)
    return {"ok": True}


@router.get("/workbooks/{workbook_id}/original")
def download_original(workbook_id: str, s: AppState = Depends(state)):
    folder, original = _workbook(s, workbook_id)
    return FileResponse(original, filename=s.store.meta(workbook_id)["filename"])


@router.get("/workbooks/{workbook_id}/versions/{name}")
def download_version(workbook_id: str, name: str, s: AppState = Depends(state)):
    folder, _ = _workbook(s, workbook_id)
    path = (folder / "versions" / name).resolve()
    if path.parent != (folder / "versions").resolve() or not path.exists():
        raise not_found("Version introuvable.")
    return FileResponse(path, filename=name)


class Mapping(BaseModel):
    column: str = Field(pattern=r"^(?:[A-Z]{1,3}|#\d{1,6})$")  # colonne, ou ligne « #n » d'un classeur transposé
    extraction: str  # extraction Fabric ou concept de l'ontologie RFI (« onto:<concept> »)


class RecipeBody(BaseModel):
    id: str | None = None
    name: str = "Recette sans nom"
    workbook_id: str
    sheet: str
    header_row: int = Field(ge=1)
    key_column: str = Field("", pattern=r"^(?:[A-Z]{1,3}|#\d{1,6})?$")
    key_type: str = "isin_part"
    orientation: str = Field("rows", pattern="^(rows|columns)$")  # columns : une colonne par ISIN (ligne clé)
    key_row: int | None = Field(None, ge=1)
    label_column: str | None = Field(None, pattern=r"^[A-Z]{1,3}$")
    language: str | None = Field(None, pattern="^(fr|en|es|it)$")
    as_of: str | None = None
    overwrite: bool = False
    highlight_changes: bool = False
    mappings: list[Mapping]


@router.post("/preview")
def preview(body: RecipeBody, s: AppState = Depends(state)):
    _, original = _workbook(s, body.workbook_id)
    try:
        return compute_changes(s.data, original, body.model_dump())
    except RecipeError as error:
        raise bad_request(str(error)) from error
    except DataError as error:
        raise bad_request(str(error), error.hint) from error


@router.post("/run")
def run(body: RecipeBody, s: AppState = Depends(state), user: str = Depends(current_user)):
    folder, _ = _workbook(s, body.workbook_id)
    if not body.mappings:
        raise bad_request("Aucune correspondance définie.", "Glissez au moins une extraction sur une colonne.")
    return s.jobs.submit_recipe(body.model_dump(), folder, user)


@router.get("/recipes")
def list_recipes(s: AppState = Depends(state)):
    recipes = s.store.list_recipes()
    for recipe in recipes:
        try:
            recipe["workbook"] = s.store.meta(recipe["workbook_id"])["filename"]
        except FileNotFoundError:
            recipe["workbook"] = None
    return recipes


@router.post("/recipes")
def save_recipe(body: RecipeBody, s: AppState = Depends(state), user: str = Depends(current_user)):
    _workbook(s, body.workbook_id)
    return s.store.save_recipe(body.model_dump(exclude_none=True), user)


@router.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: str, s: AppState = Depends(state)):
    try:
        return s.store.get_recipe(recipe_id)
    except FileNotFoundError as error:
        raise not_found("Recette introuvable.") from error


@router.post("/recipes/{recipe_id}/run")
def run_recipe(recipe_id: str, s: AppState = Depends(state), user: str = Depends(current_user)):
    try:
        recipe = s.store.get_recipe(recipe_id)
    except FileNotFoundError as error:
        raise not_found("Recette introuvable.") from error
    folder, _ = _workbook(s, recipe["workbook_id"])
    return s.jobs.submit_recipe({**recipe, "as_of": None}, folder, user)


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, s: AppState = Depends(state)):
    s.store.delete_recipe(recipe_id)
    return {"ok": True}
