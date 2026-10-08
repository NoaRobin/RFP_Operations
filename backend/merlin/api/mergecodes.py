"""API Merge codes Qvidian."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..db import now_iso
from ..mergecodes.service import MergeStore, analyse, appliquer, demo_export, demo_referentiel, describe_referentiel, fichier
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api/mergecodes")
NEED_REF = ("Aucun référentiel « Années d'expérience » chargé.",
            "Déposez l'Excel « Années d'expérience - FR_EN pour Qvidian » (onglet Data) dans l'écran Merge codes.")


def _store(s: AppState) -> MergeStore:
    return MergeStore(s.settings.data_dir / "mergecodes")


@router.get("/referentiel")
def referentiel(s: AppState = Depends(state)) -> dict[str, Any]:
    store = _store(s)
    try:
        ref = store.referentiel()
    except Exception as error:  # noqa: BLE001
        raise bad_request("Le référentiel enregistré est illisible.", str(error)) from error
    return {"present": ref is not None, "meta": store.referentiel_meta(), **(describe_referentiel(ref) if ref else {})}


@router.post("/referentiel")
async def upload_referentiel(file: UploadFile = File(...), s: AppState = Depends(state)):
    content = await file.read()
    try:
        return {"present": True, **_store(s).save_referentiel(content, file.filename or "referentiel.xlsx")}
    except Exception as error:  # noqa: BLE001
        raise bad_request("Ce fichier n'est pas un référentiel valide.", f"Il faut l'onglet « Data » de l'Excel des merge codes. ({error})") from error


@router.post("/demo")
def demo(s: AppState = Depends(state), user: str = Depends(current_user)):
    store = _store(s)
    if store.referentiel_path.exists() is False:
        store.save_referentiel(demo_referentiel(), "referentiel_demo.xlsx")
    meta = store.save_document("Export_Qvidian_demo.docx", demo_export(), user)
    return analyse(store, meta["id"])


@router.post("/documents")
async def upload(file: UploadFile = File(...), s: AppState = Depends(state), user: str = Depends(current_user)):
    store = _store(s)
    content = await file.read()
    try:
        meta = store.save_document(file.filename or "export.docx", content, user)
    except ValueError as error:
        raise bad_request("Format non pris en charge.", "Exportez les textes Qvidian au format Word (.docx).") from error
    try:
        return analyse(store, meta["id"])
    except LookupError as error:
        raise bad_request(*NEED_REF) from error


class Decision(BaseModel):
    choix: str = Field("proposition", pattern="^(proposition|ignorer|code)$")
    proposition: int | None = None
    code: str | None = None


class ApplyRequest(BaseModel):
    decisions: list[Decision]


@router.post("/documents/{doc_id}/appliquer")
def apply(doc_id: str, body: ApplyRequest, s: AppState = Depends(state), user: str = Depends(current_user)):
    store = _store(s)
    try:
        meta = store.meta(doc_id)
        result = appliquer(store, doc_id, [d.model_dump() for d in body.decisions], user)
    except FileNotFoundError as error:
        raise not_found("Ce document n'est plus là.") from error
    except LookupError as error:
        raise bad_request(*NEED_REF) from error
    s.db.create_run(
        target_type="mergecodes", target_id="mergecodes", target_name=f"Merge codes — {meta['filename']}", user=user,
        params={}, status="success", started_at=now_iso(), finished_at=now_iso(), duration_ms=0,
        summary=f"{result['inseres']} merge code(s) inséré(s).", minutes_saved=result["inseres"], data_mode=s.data.mode,
    )
    base = f"/api/mergecodes/documents/{doc_id}/fichiers"
    return {**result, "document_url": f"{base}/{result['document']}", "rapport_url": f"{base}/{result['rapport']}"}


@router.get("/documents/{doc_id}/fichiers/{name}")
def download(doc_id: str, name: str, s: AppState = Depends(state)):
    try:
        return FileResponse(fichier(_store(s), doc_id, name), filename=name)
    except FileNotFoundError as error:
        raise not_found("Fichier introuvable.") from error
