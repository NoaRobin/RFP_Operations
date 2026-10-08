"""Navigation métier dans les due diligences : année (2026, sinon les années précédentes) → RFI → dossier de la
due diligence → « final » → documents. Ne dépend que du contrat DocumentSource."""
from __future__ import annotations

import re
from datetime import date

from ..ontology import norm
from .base import DocumentSource, RemoteItem, SourceError

YEAR = re.compile(r"^(20\d{2})\b")


class DueDiligenceNavigator:
    def __init__(self, source: DocumentSource, start_year: int | None = None):
        self.source = source
        self.start_year = start_year or date.today().year

    def years(self) -> list[tuple[int, RemoteItem]]:
        """Années disponibles, de la plus récente (≤ année de départ) à la plus ancienne."""
        out = []
        for item in self.source.children(""):
            m = YEAR.match(item.name.strip())
            if item.is_folder and m and int(m.group(1)) <= self.start_year:
                out.append((int(m.group(1)), item))
        return sorted(out, key=lambda x: -x[0])

    @staticmethod
    def _pick(items: list[RemoteItem], word: str) -> RemoteItem | None:
        folders = [i for i in items if i.is_folder]
        exact = [i for i in folders if norm(i.name) == word]
        if exact:
            return exact[0]
        loose = [i for i in folders if re.search(rf"(?<![a-z]){word}(?![a-z])", norm(i.name))]
        return loose[0] if len(loose) == 1 else (loose[0] if loose else None)

    def rfi_folder(self, year_item: RemoteItem) -> RemoteItem | None:
        return self._pick(self.source.children(year_item.path), "rfi")

    def due_diligences(self, year: int | None = None) -> dict:
        """Dossiers de due diligence de l'année demandée ; sans année : 2026, sinon la première année antérieure qui en a."""
        years = self.years()
        if not years:
            raise SourceError("Aucun dossier d'année trouvé sous la racine des due diligences.")
        tried = []
        for y, item in years:
            if year is not None and y != year:
                continue
            tried.append(y)
            rfi = self.rfi_folder(item)
            if rfi is None:
                continue
            folders = [i for i in self.source.children(rfi.path) if i.is_folder]
            if folders or year is not None:
                return {"year": y, "rfi_path": rfi.path, "folders": [f.to_dict() for f in folders], "tried": tried,
                        "years": [yy for yy, _ in years]}
        return {"year": year, "rfi_path": None, "folders": [], "tried": tried, "years": [yy for yy, _ in years]}

    def search(self, text: str) -> dict:
        """Cherche une due diligence par nom, en 2026 puis dans les années précédentes (« 2026 ou moins »)."""
        words = [w for w in norm(text).split() if len(w) > 1]
        years = self.years()
        for y, item in years:
            rfi = self.rfi_folder(item)
            if rfi is None:
                continue
            hits = [i for i in self.source.children(rfi.path) if i.is_folder and all(w in norm(i.name) for w in words)]
            if hits:
                return {"year": y, "folders": [h.to_dict() for h in hits], "years": [yy for yy, _ in years]}
        return {"year": None, "folders": [], "years": [yy for yy, _ in years]}

    def final_documents(self, folder_path: str) -> dict:
        """Documents du sous-dossier « final » (et d'un niveau en dessous)."""
        children = self.source.children(folder_path)
        final = self._pick(children, "final")
        if final is None:
            final = next((i for i in children if i.is_folder and "final" in norm(i.name)), None)
        if final is None:
            return {"final_path": None, "documents": [], "hint": "Aucun sous-dossier « final » dans cette due diligence."}
        docs: list[RemoteItem] = []
        for item in self.source.children(final.path):
            if item.is_document:
                docs.append(item)
            elif item.is_folder:
                docs.extend(i for i in self.source.children(item.path) if i.is_document)
        return {"final_path": final.path, "documents": [d.to_dict() for d in docs], "hint": "" if docs else "Le dossier « final » est vide."}
