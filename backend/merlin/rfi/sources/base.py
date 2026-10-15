"""Contrat commun des sources de documents (principe d'inversion des dépendances : le navigateur ne connaît que lui)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

DOC_SUFFIXES = {".xlsx", ".xlsm", ".docx"}


@dataclass
class RemoteItem:
    id: str
    name: str
    path: str  # chemin relatif à la racine des due diligences, séparateur « / »
    is_folder: bool
    url: str = ""
    modified: str = ""
    size: int = 0

    @property
    def is_document(self) -> bool:
        return not self.is_folder and Path(self.name).suffix.lower() in DOC_SUFFIXES and not self.name.startswith("~$")

    def to_dict(self) -> dict:
        return asdict(self)


class SourceError(Exception):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


class DocumentSource(Protocol):
    name: str

    def status(self) -> dict: ...

    def children(self, path: str) -> list[RemoteItem]: ...

    def download(self, item: RemoteItem, target: Path) -> Path: ...
