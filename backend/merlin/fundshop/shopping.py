"""La liste des documents à télécharger (« liste de courses ») : éditée dans l'app, ou remplie dans Excel puis importée.

Deux formats d'Excel sont lus :
- la liste vierge de l'app (template.py) : Part (choisie dans une liste), ISIN, Document, Mois, Remplacer, Nom du fichier ;
- l'ancienne « Liste de courses » : Fonds, Part, ISIN, Type de document, Mois demandé, Année, Nom final, Actif, Écraser.
Un mois relatif (« Mois précédent », « Il y a 2 mois ») est gardé tel quel : la même liste resservira chaque mois.
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
from .period import Period, month_spec, resolve

DEFAULT_NAME = "Rothschild & Co AM - {fonds} - {type}{mois}"
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")


def column_of(header: object) -> str | None:
    """En-tête Excel → champ (tolère les variantes : « Part (choisir dans la liste) », « Type de document »…)."""
    h = norm(header)
    rules = [("choix", "choice"), ("part choisir", "choice"), ("isin", "isin"), ("type de document", "kind"), ("document", "kind"),
             ("mois", "month"), ("annee", "year"), ("nom", "filename"), ("actif", "active"), ("ecraser", "overwrite"),
             ("remplacer", "overwrite"), ("fonds", "fund"), ("part", "part")]
    for prefix, key in rules:
        if h.startswith(prefix):
            return key
    return None


def parse_choice(label: object) -> tuple[str, str, str]:
    """« Fonds · Part (ISIN) » → (fonds, part, isin)."""
    text = str(label or "").strip()
    m = ISIN_RE.search(text.upper())
    isin = m.group(1) if m else ""
    head = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    fund, _, part = head.partition(" · ")
    return fund.strip(), part.strip(), isin


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
    """Lit la feuille « Liste de courses » (ou la première). Valeurs calculées par Excel (formules non réévaluées)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = next((w for w in wb.worksheets if norm(w.title) in {"liste de courses", "liste", "documents"}), wb.worksheets[0])
    rows = ws.iter_rows(values_only=True)
    header = [column_of(h) for h in next(rows, [])]
    items, errors = [], []
    for n, row in enumerate(rows, start=2):
        rec: dict[str, Any] = {}
        for k, v in zip(header, row):
            if k and k not in rec:
                rec[k] = v
        if not any(str(rec.get(k) or "").strip() for k in ("choice", "isin", "kind", "fund")):
            continue  # ligne vide (les colonnes pré-remplies « Non » et la formule ISIN ne comptent pas)
        try:
            fund, part, isin_from_choice = parse_choice(rec.get("choice")) if rec.get("choice") else ("", "", "")
            isin = str(rec.get("isin") or "").strip().upper()
            if not ISIN_RE.fullmatch(isin):
                isin = isin_from_choice
            if not ISIN_RE.fullmatch(isin or ""):
                raise ValueError("part non reconnue : choisissez-la dans la liste de la colonne A, ou tapez l'ISIN en colonne B")
            if not rec.get("kind"):
                raise ValueError("choisissez le document (colonne Document)")
            doc = doc_type(rec.get("kind"))
            month = ""
            if doc.needs_month:
                month = month_spec(rec.get("month"), rec.get("year"))
                if not month:
                    raise ValueError(f"« {doc.label} » change chaque mois : indiquez le mois (« Mois précédent » ou « juillet 2026 »)")
            items.append(Item(isin=isin, kind=doc.key, fund=str(rec.get("fund") or fund).strip(), part=str(rec.get("part") or part).strip(),
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
