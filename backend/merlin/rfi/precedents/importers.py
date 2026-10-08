"""Import des précédents : bibliothèque de wording (lot 02) et RFI déjà répondus (SharePoint, dossier local).

Règles appliquées à l'import (guide du lot 02) :
  - provenance conservée (fichier, onglet, cellule question, cellule réponse, fonds, part, date) ;
  - réponse, commentaire, option de liste et case à cocher sont distingués ; un commentaire n'est jamais une réponse ;
  - blocs verticaux et options conditionnelles importés comme « à revoir » (kind block / choice), jamais réutilisés tels quels ;
  - anomalie d'identité (ISIN du fichier ≠ ISIN de la cellule, clé invalide) → réutilisation automatique bloquée ;
  - aucune valeur source corrigée ; auto_copy_allowed toujours faux.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..layout import detect
from ..values import to_date
from .identity import identity_problem, isin_valid, isins_in
from .model import Precedent
from .store import PrecedentStore

CHECK_MARKS = {"x", "☒", "☑", "✓", "✔", "■", "oui x", "x oui"}
LOT02_JSON = "Bibliotheque_Wording_RFI_Lot02.json"


def _kind(extraction: str, answer: Any, question: str) -> str:
    text = str(answer if answer is not None else "").strip().lower()
    if extraction.startswith("BLOC_VERTICAL"):
        return "block"
    if extraction.startswith("QUESTION_OPTION"):
        return "choice"
    if text in CHECK_MARKS:
        return "checkbox"
    return "answer"


def _iso(value: Any) -> str:
    d = to_date(value)
    return d.isoformat() if d else ""


def load_lot02(raw: bytes) -> dict[str, Any]:
    """Accepte le JSON seul ou le zip du pack (le JSON est cherché dedans)."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = next((n for n in zf.namelist() if n.endswith(LOT02_JSON)), None) or \
                next((n for n in zf.namelist() if n.lower().endswith(".json") and "biblioth" in n.lower()), None)
            if name is None:
                raise ValueError(f"{LOT02_JSON} introuvable dans l'archive")
            raw = zf.read(name)
    data = json.loads(raw.decode("utf-8-sig"))
    if "answer_examples" not in data:
        raise ValueError("Ce JSON n'est pas une bibliothèque de wording (clé answer_examples absente)")
    return data


def import_lot02(store: PrecedentStore, data: dict[str, Any]) -> dict[str, Any]:
    blocked_refs = {}
    for issue in data.get("identity_issues", []) or []:
        ref = issue.get("source_ref")
        if ref:
            blocked_refs[ref] = (f"anomalie d'identité signalée ({issue.get('issue', '?')}) : ISIN du nom de fichier "
                                 f"{issue.get('filename_isin', '?')} ≠ cellule {issue.get('cell', '?')} {issue.get('cell_value', '?')} — "
                                 "réutilisation automatique bloquée jusqu'à confirmation")
    by_file: dict[str, list[Precedent]] = {}
    for e in data["answer_examples"]:
        ctx = e.get("context") or {}
        isin = str(ctx.get("isin") or ctx.get("isin_in_cell") or ctx.get("retail_isin") or "").strip()
        reason = blocked_refs.get(e.get("source_ref", ""), "")
        if not reason and isin and not isin_valid(isin):
            reason = f"ISIN « {isin} » à clé invalide : identité à confirmer"
        p = Precedent(
            id=f"lot02:{e['example_id']}", origin="lot02", source_file=str(e.get("source_file") or "?"), question=str(e.get("question") or ""),
            answer_raw=e.get("answer_raw"), kind=_kind(str(e.get("extraction_method") or ""), e.get("answer_raw"), str(e.get("question") or "")),
            source_ref=str(e.get("source_ref") or ""), sheet=str(e.get("sheet") or ""), question_cell=str(e.get("question_cell") or ""),
            answer_cell=str(e.get("answer_cell") or ""), number_format=str(e.get("answer_number_format") or ""),
            comments=[{"cell": c.get("cell"), "value": c.get("value")} for c in (e.get("comments") or [])],
            shape=str(e.get("shape_observed") or ""), extraction=str(e.get("extraction_method") or ""),
            mapping_status=str(e.get("mapping_status") or ""), fund_name=str(ctx.get("fund_name") or ""),
            isin=isin, share_name=str(ctx.get("share_name") or ctx.get("retail_share_name") or ""),
            ref_date=_iso(ctx.get("reference_date_raw")), blocked=bool(reason), block_reason=reason, review_required=True,
        )
        if p.question.strip():
            by_file.setdefault(p.source_file, []).append(p)
    now = datetime.now().isoformat(timespec="seconds")
    total = 0
    for name, items in by_file.items():
        problem = next((p.block_reason for p in items if p.blocked), "")
        total += store.replace_source(name, "lot02", items, identity_problem=problem, imported_at=now)
    return {"imported": total, "files": len(by_file), "blocked": sum(1 for items in by_file.values() for p in items if p.blocked),
            "matrix_values_ignored": len(data.get("matrix_data") or []),
            "note": "Mesures historiques (matrix_data) non importées comme réponses : séries datées, non approuvées."}


def import_document(store: PrecedentStore, path: Path, origin: str, display_name: str | None = None, url: str = "",
                    modified: str = "") -> dict[str, Any]:
    """Un RFI déjà répondu (dossier « final ») : chaque case réellement remplie devient un précédent."""
    name = display_name or path.name
    layout = detect(path)
    problem = identity_problem(name, layout.isins)
    from_name = isins_in(name)
    isin = from_name[0] if from_name else (layout.isins[0] if len(set(layout.isins)) == 1 else "")
    items: list[Precedent] = []
    for slot in layout.slots:
        if slot.state != "answered" or not slot.existing.strip():
            continue
        sheet, _, cell = slot.location.rpartition("!")
        question = slot.question if not slot.parent else f"{slot.parent} — {slot.question}"
        items.append(Precedent(
            id=f"{origin}:{name}:{slot.location}", origin=origin, source_file=name, source_url=url, question=question,
            answer_raw=slot.existing, kind="checkbox" if slot.existing.strip().lower() in CHECK_MARKS else "answer",
            sheet=sheet, answer_cell=cell or slot.location, number_format=slot.number_format or "",
            comments=[{"cell": slot.comment_cell, "value": slot.comment}] if slot.comment else [],
            shape="", extraction=f"LAYOUT_{slot.layout.upper()}", isin=(slot.entity.get("isin") or isin),
            ref_date=modified[:10] if modified else "", blocked=bool(problem), block_reason=problem,
        ))
    store.replace_source(name, origin, items, url=url, identity_problem=problem, imported_at=datetime.now().isoformat(timespec="seconds"))
    return {"file": name, "imported": len(items), "identity_problem": problem, "isin": isin}
