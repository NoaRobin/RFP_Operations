"""La liste des documents à télécharger (« liste de courses ») : éditée dans l'app, ou importée de l'Excel historique.

Colonnes reconnues (Excel) : Fonds, Part, ISIN, Type de document, Mois demandé, Année, Nom final, Actif, Écraser.
Le mois peut être relatif (« M-1 », « mois précédent ») : la même liste resservira chaque mois, en boucle.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from ..rfi.ontology import norm
from .catalog import doc_type
from .period import Period, resolve

DEFAULT_NAME = "Rothschild & Co AM - {fonds} - {type}{mois}"
COLUMNS = {"fonds": "fund", "part": "part", "isin": "isin", "type de document": "kind", "mois demande": "month", "annee": "year",
           "nom final": "filename", "actif": "active", "ecraser": "overwrite"}


@dataclass
class Item:
    isin: str
    kind: str  # clé de catalog.DOC_TYPES
    fund: str = ""
    part: str = ""
    month: str = ""  # « 2026-07 », « M-1 », « » (sans objet)
    filename: str = ""  # modèle ; vide = DEFAULT_NAME
    active: bool = True
    overwrite: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def period(self) -> Period:
        return resolve(self.month)

    def target_name(self) -> str:
        p = self.period()
        doc = doc_type(self.kind)
        template = self.filename or DEFAULT_NAME
        name = template.format(fonds=self.fund or self.isin, part=self.part, isin=self.isin, type=doc.short or doc.label,
                               mois=f" {p.mm_yyyy}" if doc.needs_month and p.month else "", mm=f"{p.month:02d}" if p.month else "",
                               aaaa=str(p.year or ""))
        name = re.sub(r'[<>:"/\\|?*]+', "-", name).strip().rstrip(".")
        return name if name.lower().endswith(".pdf") else name + ".pdf"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        try:
            d["target"] = self.target_name()
            d["period_label"] = self.period().label if doc_type(self.kind).needs_month else ""
        except ValueError as error:
            d["target"], d["error"] = "", str(error)
        return d


def _bool(value: Any, default: bool) -> bool:
    n = norm(value)
    if n in {"oui", "yes", "true", "vrai", "1", "x"}:
        return True
    if n in {"non", "no", "false", "faux", "0"}:
        return False
    return default


def from_excel(path: Path) -> tuple[list[Item], list[str]]:
    """Lit la feuille « Liste de courses » (ou la première) ; valeurs calculées par Excel (formules non réévaluées)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = next((w for w in wb.worksheets if norm(w.title) in {"liste de courses", "liste"}), wb.worksheets[0])
    rows = ws.iter_rows(values_only=True)
    header = [COLUMNS.get(norm(h)) for h in next(rows, [])]
    items, errors = [], []
    for n, row in enumerate(rows, start=2):
        rec = {k: v for k, v in zip(header, row) if k}
        if not any(v not in (None, "") for v in rec.values()):
            continue
        try:
            isin = str(rec.get("isin") or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin):
                raise ValueError(f"ISIN invalide « {isin or '—'} » (formule non calculée ? ouvrir et enregistrer le fichier dans Excel)")
            doc = doc_type(rec.get("kind"))
            month_raw = rec.get("month")
            if month_raw is not None and rec.get("year") and not re.search(r"\d{4}", str(month_raw)) and not hasattr(month_raw, "year"):
                month_raw = f"{month_raw} {rec.get('year')}"
            month = ""
            if doc.needs_month:
                p = resolve(month_raw)
                if not p.month:
                    raise ValueError("ce type exige un mois et une année")
                month = f"{p.year}-{p.month:02d}"
            items.append(Item(isin=isin, kind=doc.key, fund=str(rec.get("fund") or "").strip(), part=str(rec.get("part") or "").strip(),
                              month=month, filename=str(rec.get("filename") or "").strip(), active=_bool(rec.get("active"), True),
                              overwrite=_bool(rec.get("overwrite"), False)))
        except ValueError as error:
            errors.append(f"Ligne {n} : {error}")
    return items, errors


class ShoppingList:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> list[Item]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Item(**{k: v for k, v in r.items() if k in Item.__dataclass_fields__}) for r in raw]

    def save(self, items: list[Item]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
