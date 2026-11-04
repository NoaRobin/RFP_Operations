"""Dossier SharePoint synchronisé sur le poste (OneDrive) : aucune inscription d'application, droits de l'utilisateur."""
from __future__ import annotations

import os
import shutil
import sys
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


def long_path(path: Path) -> str:
    r"""Windows : au-delà de 260 caractères (arborescences SharePoint profondes), seul le préfixe \\?\ fonctionne."""
    text = str(path)
    if sys.platform != "win32" or text.startswith("\\\\?\\"):
        return text
    absolute = os.path.abspath(text)
    return "\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute


# Erreurs OneDrive « fichiers à la demande » : le fichier n'est pas encore sur le poste, ou le client OneDrive est occupé
ONEDRIVE_WINERRORS = {362, 389, 395, 396, 397, 398, 399, 400, 401, 403, 404, 405, 406, 407, 408, 409, 410, 32, 33}


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
        if not os.path.isdir(long_path(folder)):
            raise SourceError(f"Dossier introuvable : {path or '/'}")
        items = []
        try:
            with os.scandir(long_path(folder)) as it:  # scandir : une seule lecture du dossier, sans stat() par fichier sous Windows
                entries = list(it)
        except PermissionError as error:
            raise SourceError(f"Accès refusé au dossier {path or '/'}.", "Vos droits SharePoint ne couvrent pas ce dossier.") from error
        except OSError as error:
            raise SourceError(f"Dossier illisible : {path or '/'}", str(error)[:200], transient=True) from error
        for e in sorted(entries, key=lambda x: x.name.lower()):
            try:
                st = e.stat()
                is_dir = e.is_dir()
            except OSError:
                continue
            rel = f"{path}/{e.name}".strip("/")
            items.append(RemoteItem(id=rel, name=e.name, path=rel, is_folder=is_dir, url=(folder / e.name).as_uri(),
                                    modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), size=st.st_size))
        return items

    def download(self, item: RemoteItem, target: Path) -> Path:
        """Copie (l'original n'est jamais ouvert en écriture). Un fichier OneDrive « à la demande » est d'abord descendu
        par Windows : s'il ne l'est pas encore, l'erreur est marquée « à réessayer »."""
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        try:
            shutil.copyfile(long_path(self._resolve(item.path)), long_path(part))
            os.replace(part, target)
        except PermissionError as error:
            raise SourceError(f"{item.name} : fichier ouvert ou verrouillé.", "Fermez-le dans Excel / Word, il sera repris.", transient=True) from error
        except OSError as error:
            onedrive = getattr(error, "winerror", None) in ONEDRIVE_WINERRORS
            raise SourceError(f"{item.name} : copie impossible.",
                              "OneDrive n'a pas encore descendu ce fichier sur le poste (fichier « à la demande »)." if onedrive else str(error)[:200],
                              transient=True) from error
        finally:
            if part.exists():
                part.unlink(missing_ok=True)
        return target
