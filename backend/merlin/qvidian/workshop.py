"""Atelier de la bibliothèque (QviAPI) : doublons et versions, fraîcheur et dates de révision proposées, banque des
questions déjà tombées, export d'une sélection. Lecture seule : rien n'est écrit dans Qvidian (les modifications
passent toujours par la vue Modifier, avec prévisualisation et mot de passe).
"""
from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import Any

from .audit import duplicates

DATED = re.compile(r"\b(?:au|at|as of|en date du|arrêté au)\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\b(?:19|20)\d{2}\b", re.I)
FIGURES = re.compile(r"\d[\d  .,]*\s*(?:%|€|eur\b|usd\b|m€|md€|millions?|milliards?|bn\b|mn\b)|\b(?:encours|aum|actifs sous gestion|assets under management|headcount|effectif|collaborateurs|employees)\b", re.I)
REGULATORY = re.compile(r"\b(?:sfdr|priips|ucits|opcvm|mifid|aifmd|taxonomie|taxonomy|amf|esma|règlement|regulation|pai)\b", re.I)


def _d(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def _quarter_end_after(d: date) -> date:
    q_end = [date(d.year, 3, 31), date(d.year, 6, 30), date(d.year, 9, 30), date(d.year, 12, 31)]
    nxt = next((x for x in q_end if x > d), date(d.year + 1, 3, 31))
    return nxt + timedelta(days=30)  # un mois après l'arrêté : le temps que les chiffres soient publiés


def review_date(c: dict[str, Any], today: date) -> tuple[date, str]:
    """Date de révision proposée, avec sa raison : chiffres datés → après le prochain arrêté trimestriel ;
    réglementation → un an ; texte de présentation → deux ans. Toujours à partir de la dernière modification."""
    text = f"{c.get('title') or ''} {c.get('text') or ''}"
    base = _d(c.get("modified")) or _d(c.get("created")) or today
    if DATED.search(text) or FIGURES.search(text):
        return _quarter_end_after(base), "chiffres ou dates dans le texte : à revoir après le prochain arrêté trimestriel"
    if REGULATORY.search(text):
        return base + timedelta(days=365), "réglementation citée : à revoir chaque année"
    return base + timedelta(days=730), "texte de présentation : à relire tous les deux ans"


def freshness(contents: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    rows = []
    for c in contents:
        if not c.get("enabled", True):
            continue
        expires = _d(c.get("expires"))
        proposed, why = review_date(c, today)
        due = min(d for d in (expires, proposed) if d is not None)
        days = (due - today).days
        state = "en retard" if days < 0 or c.get("expired") else "30 jours" if days <= 30 else "90 jours" if days <= 90 else "plus tard"
        rows.append({"id": c["id"], "title": c.get("title", ""), "folder_path": c.get("folder_path") or "", "times_used": c.get("times_used") or 0,
                     "modified": (c.get("modified") or "")[:10], "expires": expires.isoformat() if expires else None,
                     "proposed": proposed.isoformat(), "why": why, "due": due.isoformat(), "days": days, "state": state,
                     "no_expiry": expires is None})
    rows.sort(key=lambda r: (r["days"], -r["times_used"]))
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("en retard", "30 jours", "90 jours", "plus tard")}
    return {"today": today.isoformat(), "counts": counts, "without_expiry": sum(1 for r in rows if r["no_expiry"]), "items": rows}


def families(contents: list[dict[str, Any]], threshold: float = 0.85) -> list[dict[str, Any]]:
    """Doublons et versions d'un même texte, regroupés ; le texte à garder = le plus utilisé, puis le plus récent."""
    by_id = {c["id"]: c for c in contents}
    dup = duplicates(contents, threshold)
    seen: set[int] = set()
    out = []
    for cid, others in dup.items():
        if cid in seen:
            continue
        group = {cid, *others}
        stack = list(others)
        while stack:  # fermeture : A ~ B ~ C forment une seule famille
            x = stack.pop()
            for y in dup.get(x, []):
                if y not in group:
                    group.add(y)
                    stack.append(y)
        seen |= group
        members = sorted((by_id[i] for i in group if i in by_id), key=lambda c: (c.get("times_used") or 0, c.get("modified") or ""), reverse=True)
        keep = members[0]["id"]
        out.append({"keep": keep, "size": len(members), "uses": sum(c.get("times_used") or 0 for c in members),
                    "members": [{"id": c["id"], "title": c.get("title", ""), "folder_path": c.get("folder_path") or "", "times_used": c.get("times_used") or 0,
                                 "modified": (c.get("modified") or "")[:10], "enabled": c.get("enabled", True), "keep": c["id"] == keep,
                                 "text": (c.get("text") or "")[:400]} for c in members]})
    return sorted(out, key=lambda f: (-f["size"], -f["uses"]))


def question_bank(matcher: Any, contents_by_id: dict[int, dict[str, Any]], q: str = "", only: str = "", limit: int = 200) -> dict[str, Any]:
    """Questions des anciens RFI, les plus posées d'abord : couvertes (texte Qvidian choisi) ou non."""
    if matcher is None:
        return {"ready": False, "items": [], "total": 0}
    from ..search.text import fold

    needle = fold(q).strip()
    items = []
    for e in matcher.entries:
        files = e.files
        if not files:
            continue  # question type Qvidian sans ancien RFI
        if needle and needle not in fold(e.text):
            continue
        covered = bool(e.contents)
        if only == "covered" and not covered or only == "orphan" and covered:
            continue
        items.append({"question": e.text, "rfis": len(files), "last": max((o.date for o in e.occ if o.date), default=""),
                      "funds": sorted({o.fund for o in e.occ if o.fund})[:4],
                      "contents": [{"id": cid, "title": contents_by_id.get(cid, {}).get("title", "")} for cid in sorted(e.contents)][:4],
                      "covered": covered, "variants": len(e.occ)})
    items.sort(key=lambda x: (-x["rfis"], x["question"]))
    return {"ready": True, "total": len(items), "items": items[:limit]}


def export_xlsx(contents: list[dict[str, Any]], levels: dict[int, str] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Sélection Qvidian"
    ws.append(["ID", "Titre", "Question type", "Texte", "Dossier", "Niveau", "Utilisations", "Dernière utilisation", "Modifié", "Expiration"])
    for c in contents:
        ws.append([c["id"], c.get("title", ""), c.get("question") or "", c.get("text") or "", c.get("folder_path") or "", (levels or {}).get(c["id"], ""),
                   c.get("times_used") or 0, (c.get("last_used") or "")[:10], (c.get("modified") or "")[:10], (c.get("expires") or "")[:10]])
    for col, w in zip("ABCDEFGHIJ", (8, 40, 40, 90, 34, 12, 12, 16, 12, 12)):
        ws.column_dimensions[col].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["freshness", "families", "question_bank", "export_xlsx", "review_date"]
