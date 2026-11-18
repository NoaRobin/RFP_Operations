"""API « Remplir un RFI »."""
from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..data.access import DataError
from ..db import now_iso
from ..rfi.demo import demo_docx, demo_grid, demo_xlsx
from ..rfi.ontology import load_ontology
from ..rfi.precedents import get_bindings, get_index
from .documents import service_for
from ..rfi.service import (ALLOWED, RfiStore, _library, analyze, document_shares, document_text, generate, load_layout, search_funds,
                           suggest_funds)
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api/rfi")
MAX_UPLOAD = 25 * 1024 * 1024
MINUTES_PER_ANSWER = 2


def _store(s: AppState) -> RfiStore:
    return RfiStore(s.settings.data_dir / "rfi")


def _qvidian(s: AppState, enabled: bool = True):
    """Bibliothèque Qvidian du compléteur : la vraie (synchronisée) ; la démo seulement avec des données fictives.
    L'option « Qvidian » de l'écran la désactive. Le moteur de recherche (questions des anciens RFI) est préparé."""
    from .qvidian import service as qvidian_service

    if not enabled:
        return None
    try:
        svc = qvidian_service(s)
        snap = svc.rfi_snapshot(s.data.mode)
        if snap is not None:
            svc.search.get(snap, wait=False)  # questions des anciens RFI ↔ textes choisis : lues par suggest.py
        return snap
    except Exception:  # noqa: BLE001 - Qvidian absent ou illisible : le compléteur fonctionne sans
        return None


# Cache des cases déjà calculées, par document et contexte : choisir une réponse ne recalcule que cette case
# (avant : toute l'analyse — Fabric, précédents SharePoint, documents — soit ~40 s à chaque « Choisir »).
_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
MAX_CACHED = 6


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _cache_for(s: AppState, store: RfiStore, doc_id: str, body: "AnswerRequest", qvidian) -> dict:
    key = (doc_id, body.pid, body.isin, body.as_of or date.today().isoformat(), body.language, s.data.mode,
           _mtime(store.root / "library.json"), _mtime(store.root / "bindings.json"), get_index(store.root).store.count(),
           qvidian.meta().get("synced_at") if qvidian is not None else None, str(qvidian.path) if qvidian is not None else None)
    with _CACHE_LOCK:
        if body.fresh:  # « Analyser » : on repart de zéro (documents téléchargés entre-temps, Fabric mis à jour…)
            for k in [k for k in _CACHE if k[0] == doc_id]:
                del _CACHE[k]
        cache = _CACHE.get(key)
        if cache is None:
            cache = _CACHE[key] = {}
            while len(_CACHE) > MAX_CACHED:
                _CACHE.popitem(last=False)
        else:
            _CACHE.move_to_end(key)
    return cache


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
    shares = document_shares(s.data, layout)
    from ..rfi.service import _form_model

    form = _form_model(get_index(store.root), layout)
    qv = _qvidian(s)
    return {**store.meta(doc_id), "kind": layout.kind, "language": layout.language, "question_count": len(layout.slots),
            "dropdowns": sum(1 for s in layout.slots if s.options), "placeholders": sum(1 for s in layout.slots if s.state == "placeholder"),
            "isins": layout.isins[:50], "notes": layout.notes, "suggestions": suggestions, "shares": shares[:50],
            "multi_share": sum(1 for sh in shares if sh["questions"]) >= 2,
            "form_sources": form.public() if form is not None else [],
            "qvidian_available": qv is not None, "qvidian_count": int(qv.meta().get("count") or 0) if qv is not None else 0}


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
    maker = {"xlsx": demo_xlsx, "docx": demo_docx, "grid": demo_grid}.get(kind)
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
    language: str | None = Field(None, pattern="^(fr|en|es|it)$")
    overrides: dict[str, Any] = Field(default_factory=dict)  # id → concept | None (ne pas remplir) | {"text": …}
    overwrite: bool = False
    accept: list[str] = Field(default_factory=list)  # propositions « à vérifier » validées par l'utilisateur
    reusable: list[str] = Field(default_factory=list)  # réponses saisies réutilisables pour tous les fonds
    remember: bool = True
    fresh: bool = False  # True : ignorer le cache des cases (bouton « Analyser »)
    use_qvidian: bool = True  # bibliothèque Qvidian comme source (option de l'écran)
    highlight_missing: bool = False  # au téléchargement : cases sans réponse surlignées en jaune (à demander)


@router.post("/documents/{doc_id}/answers")
def answers(doc_id: str, body: AnswerRequest, s: AppState = Depends(state)):
    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    qvidian = _qvidian(s, body.use_qvidian)
    try:
        result = analyze(s.data, store, path, layout, body.pid, body.isin, body.as_of, body.language, body.overrides,
                         get_index(store.root), documents=service_for(s),
                         bindings=get_bindings(store.root), qvidian=qvidian, cache=_cache_for(s, store, doc_id, body, qvidian),
                         half_life=s.settings.qvidian.half_life_days)
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
        qvidian = _qvidian(s, body.use_qvidian)
        result = generate(s.data, store, doc_id, body.pid, body.isin, body.as_of, body.language, body.overrides, body.overwrite,
                          body.accept, user, remember=body.remember, reusable=body.reusable,
                          precedents=get_index(store.root), documents=service_for(s),
                          bindings=get_bindings(store.root), qvidian=qvidian, half_life=s.settings.qvidian.half_life_days,
                          cache=_cache_for(s, store, doc_id, body, qvidian), highlight_missing=body.highlight_missing)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    except DataError as error:
        raise bad_request(str(error), error.hint) from error
    # Trace dans l'historique (et le compteur de temps économisé)
    s.db.create_run(
        target_type="rfi", target_id="rfi", target_name=f"RFI — {meta['filename']}", user=user, params={
            "pid": body.pid, "isin": body.isin, "as_of": result["as_of"]}, status="success", started_at=now_iso(),
        finished_at=now_iso(), duration_ms=0, summary=f"{result['written']} réponse(s) remplie(s), version {result['version']}.",
        minutes_saved=round(MINUTES_PER_ANSWER * result["written"]), data_mode=s.data.mode,
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


# ------------------------------------------------------------------ aller-retour Copilot
@router.post("/documents/{doc_id}/copilot-pack")
def copilot_pack(doc_id: str, body: AnswerRequest, include_auto: bool = False, s: AppState = Depends(state)):
    from fastapi.responses import Response

    from ..rfi.copilot import build_pack
    from .documents import service_for

    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    docs_service = service_for(s)
    result = analyze(s.data, store, path, layout, body.pid, body.isin, body.as_of, body.language, body.overrides,
                     get_index(store.root), documents=docs_service, bindings=get_bindings(store.root))
    documents = []
    if docs_service is not None and body.isin:
        try:
            documents = docs_service.describe(body.isin)["documents"]
        except Exception:  # noqa: BLE001 - le pack reste utile sans PDF (Copilot est invité à les joindre)
            documents = []
    fund = ""
    if body.pid:
        try:
            fund = next((x["name"] for x in search_funds(s.data, "", limit=100000) if x["pid"] == body.pid), "")
        except DataError:
            fund = ""
    content = build_pack(result, fund, body.isin or "", documents, include_auto)
    name = f"Pack_Copilot_{Path(store.meta(doc_id)['filename']).stem[:40]}.zip"
    return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/documents/{doc_id}/copilot-answers")
async def copilot_answers(doc_id: str, file: UploadFile = File(...), pid: str | None = None, isin: str | None = None,
                          as_of: str | None = None, s: AppState = Depends(state)):
    from ..rfi.copilot import read_answers

    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    raw = await file.read()
    result = analyze(s.data, store, path, layout, pid, isin, as_of, None, None, get_index(store.root),
                     documents=service_for(s), bindings=get_bindings(store.root))
    try:
        return read_answers(raw, result, load_ontology(s.data.catalog))
    except Exception as error:  # noqa: BLE001
        raise bad_request("Classeur Copilot illisible.", type(error).__name__) from error


# ------------------------------------------------------------------ Copilot, voie simple : prompt à copier, réponse à coller
def _copilot_context(s: AppState, doc_id: str, body: "AnswerRequest"):
    from .documents import _names, service_for

    store = _store(s)
    try:
        path, layout = load_layout(store, doc_id)
    except FileNotFoundError as error:
        raise not_found("Ce RFI n'est plus là.") from error
    docs_service = service_for(s)
    qvidian = _qvidian(s)
    result = analyze(s.data, store, path, layout, body.pid, body.isin, body.as_of, body.language, body.overrides,
                     get_index(store.root), documents=docs_service, bindings=get_bindings(store.root), qvidian=qvidian,
                     cache=_cache_for(s, store, doc_id, body, qvidian), half_life=s.settings.qvidian.half_life_days)
    fund, share = _names(s, body.isin) if body.isin else ("", "")
    return result, fund, share, docs_service


class CopilotPromptRequest(AnswerRequest):
    include_auto: bool = False


@router.post("/documents/{doc_id}/copilot-prompt")
def copilot_prompt(doc_id: str, body: CopilotPromptRequest, s: AppState = Depends(state)):
    """Le prompt prêt à coller dans Copilot (par lots si besoin) et les PDF à lui joindre."""
    from ..rfi.copilot import build_prompts

    result, fund, share, docs_service = _copilot_context(s, doc_id, body)
    documents = []
    if docs_service is not None and body.isin:
        try:
            documents = docs_service.describe(body.isin, fund, share)["documents"]
        except Exception:  # noqa: BLE001 - sans PDF, le prompt reste utilisable (l'utilisateur les joint lui-même)
            documents = []
    out = build_prompts(result, fund, share, body.isin or "", documents, body.include_auto)
    out["documents"] = [{"kind": d.get("kind"), "title": d.get("title"), "name": Path(d.get("path") or "").name,
                         "download": f"/api/rfi/fund-documents/{body.isin}/file/{Path(d['path']).name}" if d.get("path") else "",
                         "url": d.get("url") or ""} for d in documents]
    out["fund"], out["share"] = fund, share
    return out


class CopilotReplyRequest(AnswerRequest):
    text: str
    labels: dict[str, str]


@router.post("/documents/{doc_id}/copilot-reply")
def copilot_reply(doc_id: str, body: CopilotReplyRequest, s: AppState = Depends(state)):
    """La réponse de Copilot collée telle quelle : lue, contrôlée, et montrée ligne à ligne avant d'être appliquée."""
    from ..rfi.copilot import parse_reply

    result, *_ = _copilot_context(s, doc_id, body)
    out = parse_reply(body.text, body.labels, result, load_ontology(s.data.catalog))
    if out["read"] == 0:
        raise bad_request("Aucune ligne « Q1 | réponse | source | confiance » trouvée dans le texte collé.",
                          "Collez toute la réponse de Copilot (le tableau). Si Copilot a répondu autrement, redemandez-lui « Réponds avec le tableau demandé ».")
    return out
