"""Un précédent = une réponse historique avec sa provenance complète (fichier, onglet, cellules, fonds, part, date)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# Nature de ce qui a été lu dans la case réponse : jamais confondues (règle du lot 02)
KINDS = {"answer", "comment", "choice", "checkbox", "block"}


@dataclass
class Precedent:
    id: str
    origin: str  # lot02 | sharepoint | dossier | atelier
    source_file: str
    question: str
    answer_raw: Any
    kind: str = "answer"
    source_ref: str = ""
    source_url: str = ""
    sheet: str = ""
    question_cell: str = ""
    answer_cell: str = ""
    number_format: str = ""
    comments: list[dict[str, Any]] = field(default_factory=list)  # [{cell, value}] : jamais lus comme une réponse
    shape: str = ""  # TEXTE_COURT | NUMERIQUE | BOOLEEN_LIBELLE | NARRATIF | NON_APPLICABLE | DATE
    extraction: str = ""
    mapping_status: str = ""
    fund_name: str = ""
    isin: str = ""
    share_name: str = ""
    ref_date: str = ""  # ISO si connue
    blocked: bool = False  # réutilisation automatique interdite (anomalie d'identité…)
    block_reason: str = ""
    review_required: bool = True
    auto_copy_allowed: bool = False  # toujours faux : une réponse historique n'est pas approuvée pour copie

    @property
    def answer_text(self) -> str:
        value = self.answer_raw
        if value is None:
            return ""
        return str(value).strip()

    @property
    def empty(self) -> bool:
        return self.answer_text == ""

    def provenance(self) -> str:
        where = f"{self.sheet}!{self.answer_cell}" if self.sheet and self.answer_cell else (self.answer_cell or self.sheet)
        who = self.fund_name or self.share_name or self.isin or "fonds non identifié"
        when = f", {self.ref_date[:10]}" if self.ref_date else ""
        return f"{self.source_file} · {where} · {who}{when}"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["answer_raw"] = json.dumps(self.answer_raw, ensure_ascii=False, default=str)
        row["comments"] = json.dumps(self.comments, ensure_ascii=False, default=str)
        row["blocked"] = int(self.blocked)
        row["review_required"] = int(self.review_required)
        row["auto_copy_allowed"] = 0
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Precedent":
        data = {k: row[k] for k in cls.__dataclass_fields__ if k in row}
        data["answer_raw"] = json.loads(row["answer_raw"]) if row.get("answer_raw") else None
        data["comments"] = json.loads(row["comments"]) if row.get("comments") else []
        data["blocked"] = bool(row.get("blocked"))
        data["review_required"] = bool(row.get("review_required", 1))
        data["auto_copy_allowed"] = False
        return cls(**data)

    def to_public(self) -> dict[str, Any]:
        return {"id": self.id, "origin": self.origin, "file": self.source_file, "url": self.source_url, "sheet": self.sheet,
                "question_cell": self.question_cell, "answer_cell": self.answer_cell, "question": self.question,
                "answer": self.answer_text, "kind": self.kind, "shape": self.shape, "fund": self.fund_name,
                "isin": self.isin, "share": self.share_name, "date": self.ref_date[:10] if self.ref_date else "",
                "comments": [c.get("value") for c in self.comments if str(c.get("value") or "").strip()],
                "blocked": self.blocked, "block_reason": self.block_reason, "provenance": self.provenance()}
