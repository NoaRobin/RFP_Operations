"""API « Remplir un RFI »."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..data.access import DataError
from ..db import now_iso
from ..rfi.demo import demo_docx, demo_xlsx
from ..rfi.ontology import load_ontology
from ..rfi.precedents import get_bindings, get_index
from .documents import service_for
from ..rfi.service import ALLOWED, RfiStore, _library, analyze, document_text, generate, load_layout, search_funds, suggest_funds
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api/rfi")
MAX_UPLOAD = 25 * 1024 * 1024
MINUTES_PER_ANSWER = 2


def _store(s: AppState) -> RfiStore:
    return RfiStore(s.settings.data_dir / "rfi")


def _describe(s: AppState, doc_id: str) -> dict[str, Any]:
    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    except Exception as error:  # noqa: BLE001
        raise bad_request("Impossible de lire ce document.", f"Est-il protégé par mot de passe ou corrompu ? ({type(error).__name__})") from error
    try:
        suggestions = suggest_funds(s.data, document_text(path))
    except DataError:
        suggestions = []
    return {**store.meta(doc_id), "kind": layout.kind, "language": layout.language, "question_count": len(layout.slots),
            "dropdowns": sum(1 for s in layout.slots if s.options), "placeholders": sum(1 for s in layout.slots if s.state == "placeholder"),
            "isins": layout.isins[:50], "notes": layout.notes, "suggestions": suggestions}


@router.get("/facts")
def facts(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return [c.to_dict() for c in load_ontology(s.catalog).usable()]


@router.get("/ontology")
def ontology(s: AppState = Depends(state)) -> dict[str, Any]:
    o = load_ontology(s.catalog)
    return {"concepts": [c.to_dict() for c in o.concepts.values()], "vocabularies": {k: len(v) for k, v in o.vocabularies.items()},
            "library": _library(_store(s)).stats()}


@router.get("/funds")
def funds(q: str = "", s: AppState = Depends(state)) -> list[dict[str, Any]]:
    try:
        return search_funds(s.data, q)
    except DataError as error:
        raise bad_request(str(error), error.hint) from error


@router.get("/documents")
def recent(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return _store(s).recent()


@router.post("/documents")
async def upload(file: UploadFile = File(...), s: AppState = Depends(state), user: str = Depends(current_user)):
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise bad_request("Fichier trop volumineux (25 Mo maximum).")
    try:
        meta = _store(s).save(file.filename or "rfi.xlsx", content, user)
    except ValueError as error:
        raise bad_request(f"Format non pris en charge ({error}).", f"Formats acceptés : {', '.join(sorted(ALLOWED))}. Un .doc ou .xls ? Enregistrez-le d'abord au format moderne.") from error
    return _describe(s, meta["id"])


@router.post("/demo/{kind}")
def demo(kind: str, s: AppState = Depends(state), user: str = Depends(current_user)):
    maker = {"xlsx": demo_xlsx, "docx": demo_docx}.get(kind)
    if maker is None:
        raise not_found("Démo inconnue.")
    name, content = maker(s.data)
    meta = _store(s).save(name, content, user)
    return _describe(s, meta["id"])


@router.get("/documents/{doc_id}")
def describe(doc_id: str, s: AppState = Depends(state)):
    return _describe(s, doc_id)


class AnswerRequest(BaseModel):
    pid: str | None = None
    isin: str | None = None
    as_of: str | None = None
    language: str | None = Field(None, pattern="^(fr|en)$")
    overrides: dict[str, Any] = Field(default_factory=dict)  # id → concept | None (ne pas remplir) | {"text": …}
    overwrite: bool = False
    accept: list[str] = Field(default_factory=list)  # propositions « à vérifier » validées par l'utilisateur
    reusable: list[str] = Field(default_factory=list)  # réponses saisies réutilisables pour tous les fonds
    remember: bool = True


@router.post("/documents/{doc_id}/answers")
def answers(doc_id: str, body: AnswerRequest, s: AppState = Depends(state)):
    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    try:
        result = analyze(s.data, store, path, layout, body.pid, body.isin, body.as_of, body.language, body.overrides,
                         get_index(store.root), documents=service_for(s),
                         bindings=get_bindings(store.root))
        for row in result["questions"]:
            row.pop("_value", None)
        return result
    except DataError as error:
        raise bad_request(str(error), error.hint) from error


@router.post("/documents/{doc_id}/generate")
def generate_version(doc_id: str, body: AnswerRequest, s: AppState = Depends(state), user: str = Depends(current_user)):
    store = _store(s)
    try:
        meta = store.meta(doc_id)
        result = generate(s.data, store, doc_id, body.pid, body.isin, body.as_of, body.language, body.overrides, body.overwrite,
                          body.accept, user, remember=body.remember, reusable=body.reusable,
                          precedents=get_index(store.root), documents=service_for(s),
                         bindings=get_bindings(store.root))
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    except DataError as error:
        raise bad_request(str(error), error.hint) from error
    # Trace dans l'historique (et le compteur de temps économisé)
    s.db.create_run(
        target_type="rfi", target_id="rfi", target_name=f"RFI — {meta['filename']}", user=user, params={
            "pid": body.pid, "isin": body.isin, "as_of": result["as_of"]}, status="success", started_at=now_iso(),
        finished_at=now_iso(), duration_ms=0, summary=f"{result['written']} réponse(s) remplie(s), version {result['version']}.",
        minutes_saved=MINUTES_PER_ANSWER * result["written"], data_mode=s.data.mode,
    )
    return {**result, "download": f"/api/rfi/documents/{doc_id}/versions/{result['file']}"}


@router.get("/documents/{doc_id}/versions/{name}")
def download(doc_id: str, name: str, s: AppState = Depends(state)):
    store = _store(s)
    try:
        folder = store.folder(doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    path = (folder / "versions" / name).resolve()
    if path.parent != (folder / "versions").resolve() or not path.exists():
        raise not_found("Version introuvable.")
    return FileResponse(path, filename=name)


@router.get("/documents/{doc_id}/preview")
def preview_document(doc_id: str, s: AppState = Depends(state)):
    from ..rfi.preview import preview

    try:
        path, layout = load_layout(_store(s), doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    return preview(path, layout)


@router.get("/documents/{doc_id}/original")
def original(doc_id: str, s: AppState = Depends(state)):
    store = _store(s)
    try:
        return FileResponse(store.original(doc_id), filename=store.meta(doc_id)["filename"])
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error


__all__ = ["router", "date"]
