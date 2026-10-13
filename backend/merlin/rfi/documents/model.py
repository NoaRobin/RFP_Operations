"""Objets partagés : un document trouvé, un fait lu dans un document."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentRef:
    isin: str
    kind: str  # kid | prospectus | other
    title: str
    url: str = ""  # page ou PDF d'origine
    path: str = ""  # copie locale (cache)
    lang: str = ""
    source: str = ""  # site | dossier | dépôt
    fetched_at: str = ""
    doc_date: str = ""  # date du document lue dans le PDF (ISO)
    sha: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Fact:
    field: str  # kid.sri, kid.ongoing_costs, prospectus.cutoff_subscription…
    value: Any
    page: int
    snippet: str
    doc: DocumentRef | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        kind = {"kid": "DIC", "prospectus": "Prospectus"}.get(self.doc.kind, "Document") if self.doc else "Document"
        date = f" du {self.doc.doc_date[8:10]}/{self.doc.doc_date[5:7]}/{self.doc.doc_date[:4]}" if self.doc and self.doc.doc_date else ""
        return f"{kind}{date}, p. {self.page}"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "value": self.value, "page": self.page, "snippet": self.snippet, "citation": self.citation,
                "url": self.doc.url if self.doc else "", "kind": self.doc.kind if self.doc else "", "notes": self.notes}
