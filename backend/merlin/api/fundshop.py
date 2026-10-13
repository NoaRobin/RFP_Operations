"""API « Documents des fonds » : la liste à télécharger, l'import de l'Excel historique, un essai à l'unité."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..fundshop.catalog import DOC_TYPES, doc_type
from ..fundshop.resolver import DocumentNotFound
from ..fundshop.service import destination, memory, resolver, shopping_list
from ..fundshop.shopping import DEFAULT_NAME, Item, from_excel
from ..state import AppState
from .deps import bad_request, not_found, state

router = APIRouter(prefix="/api/fundshop")


class ItemIn(BaseModel):
    isin: str
    kind: str
    fund: str = ""
    part: str = ""
    month: str = ""
    filename: str = ""
    active: bool = True
    overwrite: bool = False
    id: str | None = None


def _item(body: ItemIn) -> Item:
    try:
        doc = doc_type(body.kind)
    except ValueError as error:
        raise bad_request(str(error)) from error
    data = body.model_dump(exclude_none=True)
    data["kind"], data["isin"] = doc.key, body.isin.strip().upper()
    item = Item(**data)
    try:
        item.target_name()
    except ValueError as error:
        raise bad_request(str(error), "Mois : 2026-07, M-1 (mois précédent)…") from error
    return item


@router.get("")
def overview(s: AppState = Depends(state)) -> dict[str, Any]:
    dest = destination(s.settings)
    items = shopping_list(s.settings).load()
    return {"items": [dict(i.to_dict(), present=(dest / i.to_dict().get("target", "")).exists() if i.to_dict().get("target") else False) for i in items],
            "types": [{"key": d.key, "label": d.label, "needs_month": d.needs_month, "direct": bool(d.prefix)} for d in DOC_TYPES.values()],
            "destination": str(dest), "default_name": DEFAULT_NAME, "memory": memory(s.settings).stats()}


@router.put("")
def replace(items: list[ItemIn], s: AppState = Depends(state)) -> dict[str, Any]:
    shopping_list(s.settings).save([_item(i) for i in items])
    return overview(s)


@router.post("/import")
async def import_excel(file: UploadFile = File(...), replace_all: bool = False, s: AppState = Depends(state)) -> dict[str, Any]:
    raw = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "liste.xlsx"
        path.write_bytes(raw)
        try:
            items, errors = from_excel(path)
        except Exception as error:  # noqa: BLE001
            raise bad_request("Excel illisible.", type(error).__name__) from error
    store = shopping_list(s.settings)
    current = [] if replace_all else store.load()
    keys = {(i.isin, i.kind, i.month) for i in current}
    added = [i for i in items if (i.isin, i.kind, i.month) not in keys]
    store.save(current + added)
    return {**overview(s), "imported": len(added), "errors": errors}


@router.post("/learn-csv")
async def learn_csv(file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    """Amorce la mémoire des adresses avec resultats_telechargement.csv du script historique."""
    raw = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "resultats.csv"
        path.write_bytes(raw)
        mem = memory(s.settings)
        count = mem.seed_from_csv(path)
    return {"learned": count, "memory": mem.stats()}


class TryIn(BaseModel):
    isin: str
    kind: str
    month: str = ""


@router.post("/try")
def try_one(body: TryIn, s: AppState = Depends(state)) -> dict[str, Any]:
    """Cherche un document sans l'enregistrer dans la liste (adresse directe seulement : rapide)."""
    item = _item(ItemIn(isin=body.isin, kind=body.kind, month=body.month))
    res, _ = resolver(s.settings, s.data, with_browser=False)
    try:
        found = res.find(res.identity(item.isin), doc_type(item.kind), item.period(), allow_browser=False)
    except DocumentNotFound as error:
        return {"found": False, "detail": str(error)}
    res.memory.save()
    return {"found": True, "url": found.url, "strategy": found.strategy, "size": len(found.content), "note": found.note}


@router.get("/file/{name}")
def download(name: str, s: AppState = Depends(state)):
    path = destination(s.settings) / Path(name).name
    if not path.exists():
        raise not_found("Fichier introuvable.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
