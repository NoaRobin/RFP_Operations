"""Dossier SharePoint synchronisé sur le poste (OneDrive) : aucune inscription d'application, droits de l'utilisateur."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from .base import RemoteItem, SourceError


def discover(root_name: str, home: Path | None = None) -> Path | None:
    """Cherche « <Organisation>\\<Site> - Documents\\<racine> » dans le profil (dossiers synchronisés OneDrive)."""
    home = home or Path(os.environ.get("USERPROFILE") or Path.home())
    try:
        tops = [p for p in home.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return None
    for top in tops:
        direct = top / root_name
        if direct.is_dir():
            return direct
        try:
            for lib in top.iterdir():
                candidate = lib / root_name
                if lib.is_dir() and candidate.is_dir():
                    return candidate
        except OSError:
            continue
    return None


class LocalFolderSource:
    name = "dossier synchronisé"

    def __init__(self, root: Path | None):
        self.root = root

    def status(self) -> dict:
        ok = self.root is not None and self.root.is_dir()
        return {"source": self.name, "ready": ok, "root": str(self.root) if self.root else None,
                "hint": "" if ok else "Synchronisez la bibliothèque SharePoint (bouton « Synchroniser ») ou renseignez SHAREPOINT_LOCAL_DIR."}

    def _resolve(self, path: str) -> Path:
        if self.root is None:
            raise SourceError("Aucun dossier synchronisé trouvé.", self.status()["hint"])
        target = (self.root / path).resolve()
        if self.root.resolve() not in (target, *target.parents):
            raise SourceError("Chemin hors du dossier des due diligences.")
        return target

    def children(self, path: str) -> list[RemoteItem]:
        folder = self._resolve(path)
        if not folder.is_dir():
            raise SourceError(f"Dossier introuvable : {path or '/'}")
        items = []
        for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
            try:
                st = p.stat()
            except OSError:
                continue
            rel = f"{path}/{p.name}".strip("/")
            items.append(RemoteItem(id=rel, name=p.name, path=rel, is_folder=p.is_dir(), url=p.as_uri(),
                                    modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), size=st.st_size))
        return items

    def download(self, item: RemoteItem, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._resolve(item.path), target)  # copie : l'original n'est jamais ouvert en écriture
        return target
