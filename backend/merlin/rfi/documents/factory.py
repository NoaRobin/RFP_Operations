"""Assemblage des sources de documents selon la configuration (un service par dossier de données)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ...config import FundDocumentSettings
from .finder import FolderDocumentFinder, WebsiteDocumentFinder
from .service import DocumentService


@lru_cache
def document_service(root: Path, settings: FundDocumentSettings, data_mode: str, fund_names: tuple[str, ...] = ()) -> DocumentService | None:
    if settings.mode == "off":
        return None
    finders = [FolderDocumentFinder(root / "uploads", "dépôt")]
    if settings.local_dir:
        finders.append(FolderDocumentFinder(Path(settings.local_dir), "dossier"))
    if settings.mode == "on" or (settings.mode == "auto" and data_mode == "fabric"):
        finders.append(WebsiteDocumentFinder(settings.site_url, settings.fund_path, settings.search_path))
    return DocumentService(root, finders, list(fund_names))
