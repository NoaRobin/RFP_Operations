"""API « Précédents » : corpus des anciens RFI (bibliothèque de wording, SharePoint) et inventaire."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from ..rfi.ontology import load_ontology
from ..rfi.precedents import get_index
from ..rfi.precedents.importers import import_document, import_lot02, load_lot02
from ..rfi.precedents.inventory import inventory
from ..rfi.sources.base import RemoteItem, SourceError
from ..rfi.sources.graph import GraphSharePointSource
from ..rfi.sources.local import LocalFolderSource, discover
from ..rfi.sources.navigator import DueDiligenceNavigator
from ..state import AppState
from .deps import bad_request, state

router = APIRouter(prefix="/api/rfi")
MAX_UPLOAD = 60 * 1024 * 1024
_graph: dict[str, GraphSharePointSource] = {}


def _root(s: AppState) -> Path:
    return s.settings.data_dir / "rfi"


def _source(s: AppState, kind: str | None = None):
    sp = s.settings.sharepoint
    if kind != "local" and sp.graph_configured:
        key = sp.client_id
        if key not in _graph:
            _graph[key] = GraphSharePointSource(sp, _root(s) / "graph_token_cache.bin")
        return _graph[key]
    local = Path(sp.local_dir) if sp.local_dir else discover(sp.root)
    return LocalFolderSource(local)


def _nav(s: AppState, kind: str | None) -> DueDiligenceNavigator:
    return DueDiligenceNavigator(_source(s, kind))


def _guard(fn, *args):
    try:
        return fn(*args)
    except SourceError as error:
        raise bad_request(str(error), error.hint) from error


# ------------------------------------------------------------------ corpus
@router.get("/precedents")
def precedents_status(s: AppState = Depends(state)) -> dict[str, Any]:
    store = get_index(_root(s)).store
    return {**store.stats(), "sources_list": store.sources()[:50], "embedder": getattr(get_index(_root(s)).embedder, "name", None)}


@router.get("/precedents/inventory")
def precedents_inventory(s: AppState = Depends(state)) -> dict[str, Any]:
    return inventory(get_index(_root(s)).store, load_ontology(s.data.catalog))


@router.get("/precedents/search")
def precedents_search(q: str, s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return [h.to_public() for h in get_index(_root(s)).search(q, k=10, min_similarity=0.5)]


@router.post("/precedents/wording")
async def precedents_import_wording(file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise bad_request("Fichier trop volumineux.", "60 Mo maximum.")
    try:
        data = load_lot02(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise bad_request("Bibliothèque de wording illisible.", str(error)) from error
    return import_lot02(get_index(_root(s)).store, data)


@router.post("/precedents/document")
async def precedents_import_document(file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    raw = await file.read()
    name = Path(file.filename or "rfi.xlsx").name
    if Path(name).suffix.lower() not in {".xlsx", ".xlsm", ".docx"}:
        raise bad_request("Format non pris en charge.", "Excel (.xlsx, .xlsm) ou Word (.docx).")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_bytes(raw)
        try:
            return import_document(get_index(_root(s)).store, path, "atelier", display_name=name)
        except Exception as error:  # noqa: BLE001
            raise bad_request("Document illisible.", type(error).__name__) from error


# ------------------------------------------------------------------ SharePoint
@router.get("/sharepoint/status")
def sharepoint_status(s: AppState = Depends(state)) -> dict[str, Any]:
    sp = s.settings.sharepoint
    graph = _source(s).status() if sp.graph_configured else None
    local = _source(s, "local").status()
    return {"site": sp.site_url, "root": sp.root, "graph": graph, "local": local,
            "active": "graph" if graph and graph.get("ready") else ("local" if local.get("ready") else None)}


@router.get("/sharepoint/due-diligences")
def sharepoint_due_diligences(year: int | None = None, q: str = "", source: str | None = None, s: AppState = Depends(state)):
    nav = _nav(s, source)
    return _guard(nav.search, q) if q.strip() else _guard(nav.due_diligences, year)


@router.get("/sharepoint/final")
def sharepoint_final(path: str, source: str | None = None, s: AppState = Depends(state)):
    return _guard(_nav(s, source).final_documents, path)


class ImportRequest(BaseModel):
    path: str  # dossier de la due diligence
    source: str | None = None


@router.post("/sharepoint/import")
def sharepoint_import(body: ImportRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Télécharge les documents du dossier « final » (copie locale) et en fait des précédents."""
    nav = _nav(s, body.source)
    listing = _guard(nav.final_documents, body.path)
    store = get_index(_root(s)).store
    cache = _root(s) / "sharepoint"
    results = []
    for doc in listing["documents"]:
        item = RemoteItem(**doc)
        target = cache / item.path
        try:
            _guard(nav.source.download, item, target)
            results.append(import_document(store, target, "sharepoint", display_name=item.name, url=item.url, modified=item.modified))
        except Exception as error:  # noqa: BLE001 - un document illisible n'arrête pas les autres
            results.append({"file": item.name, "imported": 0, "error": getattr(error, "hint", "") or type(error).__name__})
    return {"final_path": listing["final_path"], "documents": results, "imported": sum(r.get("imported", 0) for r in results),
            "hint": listing.get("hint", "")}
