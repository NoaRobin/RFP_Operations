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
from ..rfi.sources.sync import SharePointSync, cache_name, retry
from ..state import AppState
from .deps import bad_request, state

router = APIRouter(prefix="/api/rfi")
MAX_UPLOAD = 60 * 1024 * 1024
_graph: dict[str, GraphSharePointSource] = {}
_syncs: dict[str, SharePointSync] = {}


def _import_item(s: AppState):
    """Un document SharePoint → précédents, rangé sous son chemin complet (clé unique)."""
    store = get_index(_root(s)).store

    def run(path: Path, item: RemoteItem, key: str) -> dict[str, Any]:
        if key != item.name:
            store.replace_source(item.name, "sharepoint", [])  # ancienne clé (nom seul, risquait d'écraser un homonyme)
        return import_document(store, path, "sharepoint", display_name=key, url=item.url, modified=item.modified)
    return run


def _sync(s: AppState) -> SharePointSync:
    key = str(_root(s))
    if key not in _syncs:
        def done() -> None:  # nouvelles questions : liens anciens RFI ↔ textes Qvidian, puis index de recherche
            from ..qvidian.service import get_service

            get_service(s.settings.qvidian, s.settings.data_dir).rebuild_history(background=True)
        _syncs[key] = SharePointSync(_root(s) / "sharepoint", _import_item(s), on_done=done)
    return _syncs[key]


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
def sharepoint_final(path: str, fund: str = "", source: str | None = None, s: AppState = Depends(state)):
    return _guard(_nav(s, source).final_documents, path, fund)


class ImportRequest(BaseModel):
    path: str  # dossier de la due diligence
    fund: str = ""  # filtre : dossier du fonds quand la due diligence en contient plusieurs
    source: str | None = None


@router.post("/sharepoint/import")
def sharepoint_import(body: ImportRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Télécharge les documents du dossier « final » (copie locale) et en fait des précédents."""
    nav = _nav(s, body.source)
    listing = _guard(nav.final_documents, body.path, body.fund)
    cache = _root(s) / "sharepoint" / "files"
    importer = _import_item(s)
    results = []
    for doc in listing["documents"]:
        item = RemoteItem(**{k: v for k, v in doc.items() if k != "fund"})
        target = cache / cache_name(item.path)
        try:
            retry(lambda: nav.source.download(item, target))
            results.append({**importer(target, item, item.path), "file": item.name})
        except Exception as error:  # noqa: BLE001 - un document illisible n'arrête pas les autres
            results.append({"file": item.name, "imported": 0, "error": f"{error} {getattr(error, 'hint', '')}".strip()[:300]})
    return {"final_path": listing["final_path"], "documents": results, "imported": sum(r.get("imported", 0) for r in results),
            "hint": listing.get("hint", "")}


class SyncRequest(BaseModel):
    source: str | None = None
    years: list[int] = []
    full: bool = False  # tout relire (sinon : seulement les documents nouveaux ou modifiés)


@router.post("/sharepoint/sync")
def sharepoint_sync(body: SyncRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Toutes les due diligences, toutes les années, en arrière-plan (suivre avec GET /sharepoint/sync)."""
    source = _source(s, body.source)
    st = source.status()
    if not st.get("ready"):
        raise bad_request("SharePoint n'est pas joignable.", st.get("hint", ""))
    _sync(s).start(source, body.years or None, body.full)
    return _sync(s).status()


@router.get("/sharepoint/sync")
def sharepoint_sync_status(s: AppState = Depends(state)) -> dict[str, Any]:
    return _sync(s).status()


@router.post("/sharepoint/sync/stop")
def sharepoint_sync_stop(s: AppState = Depends(state)) -> dict[str, Any]:
    _sync(s).stop()
    return _sync(s).status()


# ------------------------------------------------------------------ liaisons apprises
def _bindings(s: AppState):
    from ..rfi.precedents import get_bindings

    return get_bindings(_root(s))


@router.get("/precedents/bindings")
def bindings_list(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return [b.to_dict() for b in _bindings(s).all()]


@router.post("/precedents/bindings/build")
def bindings_build(s: AppState = Depends(state)) -> dict[str, Any]:
    """Apprend, sur les anciens RFI, quelle colonne Fabric (ou quel champ du DIC) avait été répondue pour chaque question."""
    from collections import Counter

    from ..data.access import DataError
    from ..rfi.precedents.advisor import FundResolver
    from ..rfi.precedents.bindings import BindingMiner
    from ..rfi.service import fund_directory
    from .documents import service_for

    try:
        miner = BindingMiner(s.data, load_ontology(s.data.catalog), get_index(_root(s)).store, FundResolver(fund_directory(s.data)),
                             service_for(s))
        built = miner.build()
    except DataError as error:
        raise bad_request(str(error), error.hint) from error
    _bindings(s).save(built)
    return {"total": len(built), "by_status": dict(Counter(b.status for b in _bindings(s).all()))}


class BindingStatus(BaseModel):
    id: str
    status: str


@router.post("/precedents/bindings/status")
def bindings_status(body: BindingStatus, s: AppState = Depends(state)) -> dict[str, Any]:
    if body.status not in {"validated", "rejected", "candidate"}:
        raise bad_request("Statut inconnu.", "validated, rejected ou candidate")
    b = _bindings(s).set_status(body.id, body.status)
    if b is None:
        raise bad_request("Liaison introuvable.", "Reconstruisez les liaisons.")
    return b.to_dict()
