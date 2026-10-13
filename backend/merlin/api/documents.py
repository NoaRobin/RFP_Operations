"""API « Documents officiels » : DIC PRIIPs et prospectus d'une part (recherche, dépôt, faits lus)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from ..data.access import DataError
from ..rfi.documents.factory import document_service
from ..rfi.documents.finder import classify
from ..rfi.service import fund_directory
from ..state import AppState
from .deps import bad_request, not_found, state

router = APIRouter(prefix="/api/rfi/fund-documents")
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
MAX_UPLOAD = 40 * 1024 * 1024


def service_for(s: AppState):
    try:
        names = tuple(i["name"] for i in fund_directory(s.data))
    except DataError:
        names = ()
    return document_service(s.settings.data_dir / "rfi" / "documents", s.settings.fund_documents, s.data.mode, names)


def _names(s: AppState, isin: str) -> tuple[str, str]:
    try:
        for item in fund_directory(s.data):
            for share in item["shares"]:
                if share["isin"] == isin:
                    return item["name"], share["name"]
    except DataError:
        pass
    return "", ""


def _check(isin: str) -> str:
    isin = isin.strip().upper()
    if not ISIN.match(isin):
        raise bad_request("ISIN invalide.", "12 caractères : 2 lettres, 9 caractères, 1 chiffre.")
    return isin


@router.get("/{isin}")
def describe(isin: str, refresh: bool = False, s: AppState = Depends(state)) -> dict[str, Any]:
    isin = _check(isin)
    svc = service_for(s)
    if svc is None:
        return {"isin": isin, "documents": [], "facts": [], "problems": ["documents officiels désactivés (FUND_DOCS=off)"]}
    fund, share = _names(s, isin)
    if refresh:
        svc.documents(isin, fund, share, refresh=True)
    return {**svc.describe(isin, fund, share), "fund": fund, "share": share}


@router.post("/{isin}")
async def upload(isin: str, file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    """Dépôt manuel d'un DIC ou d'un prospectus (repli si le site ne répond pas)."""
    isin = _check(isin)
    raw = await file.read()
    if len(raw) > MAX_UPLOAD or not raw.startswith(b"%PDF"):
        raise bad_request("Fichier refusé.", "Un PDF de 40 Mo au plus.")
    kind = classify(file.filename or "")
    kind = kind if kind != "other" else "kid"
    folder = s.settings.data_dir / "rfi" / "documents" / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{isin}_{kind}_{Path(file.filename or 'document.pdf').stem[:40]}.pdf").write_bytes(raw)
    svc = service_for(s)
    if svc is None:
        raise bad_request("Documents officiels désactivés.", "FUND_DOCS=off dans .env")
    fund, share = _names(s, isin)
    svc.documents(isin, fund, share, refresh=True)
    return {**svc.describe(isin, fund, share), "fund": fund, "share": share}


@router.get("/{isin}/file/{name}")
def download(isin: str, name: str, s: AppState = Depends(state)):
    isin = _check(isin)
    path = (s.settings.data_dir / "rfi" / "documents" / isin / Path(name).name)
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise not_found("Document introuvable.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
