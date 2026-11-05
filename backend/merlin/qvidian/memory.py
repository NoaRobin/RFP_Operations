"""Mémoire des réponses : ce que l'équipe a déjà répondu, et ce que cela vaut.

Lit trois sources déjà sur le poste, sans appel à Qvidian :
- l'historique (questions des anciens RFI ↔ texte Qvidian choisi, `history.py`) ;
- la banque des questions déjà tombées (`merlin/match`) ;
- l'instantané de la bibliothèque (usage, dates, expiration, niveau).

Produit : couverture (part des questions passées qui ont un texte Qvidian), réutilisation dans le temps, textes
« piliers » (les plus réutilisés), questions récurrentes sans texte (textes à créer), textes très utilisés mais vieux
(à rafraîchir en priorité), textes jamais utilisés (à archiver ?). Tout est expliqué et cliquable ; rien n'est écrit.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any


def _d(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def memory(contents: list[dict[str, Any]], links: list[Any], matcher: Any = None, today: date | None = None,
           levels: dict[int, str] | None = None) -> dict[str, Any]:
    today = today or date.today()
    by_id = {c["id"]: c for c in contents}
    levels = levels or {}
    files_by_content: dict[int, set[str]] = defaultdict(set)
    questions_by_content: dict[int, Counter] = defaultdict(Counter)
    last_by_content: dict[int, str] = {}
    timeline: Counter = Counter()
    modes: Counter = Counter()
    for l in links:
        if l.content_id not in by_id:
            continue
        files_by_content[l.content_id].add(l.file)
        questions_by_content[l.content_id][l.question] += 1
        if l.date and l.date > last_by_content.get(l.content_id, ""):
            last_by_content[l.content_id] = l.date
        if l.date:
            timeline[l.date[:7]] += 1
        modes[l.mode] += 1
    rfis = {l.file for l in links if l.file}

    def card(cid: int, **extra: Any) -> dict[str, Any]:
        c = by_id[cid]
        return {"id": cid, "title": c.get("title", ""), "folder_path": c.get("folder_path") or "", "rfis": len(files_by_content.get(cid, ())),
                "times_used": c.get("times_used") or 0, "last_rfi": last_by_content.get(cid, ""), "modified": (c.get("modified") or "")[:10],
                "level": levels.get(cid, ""), "questions": [q for q, _ in questions_by_content.get(cid, Counter()).most_common(3)], **extra}

    pillars = sorted(files_by_content, key=lambda cid: (-len(files_by_content[cid]), -(by_id[cid].get("times_used") or 0)))[:12]
    stale = []
    for cid in files_by_content:
        c = by_id[cid]
        mod = _d(c.get("modified"))
        age = (today - mod).days if mod else None
        if len(files_by_content[cid]) >= 2 and ((age is not None and age > 365) or c.get("expired")):
            stale.append(card(cid, age_days=age, expired=bool(c.get("expired"))))
    stale.sort(key=lambda x: (-x["rfis"], -(x["age_days"] or 0)))
    unused = [card(c["id"]) for c in contents if c.get("enabled") and not (c.get("times_used") or 0) and c["id"] not in files_by_content]

    # Questions déjà tombées : couvertes par un texte Qvidian, ou récurrentes sans texte (à créer)
    bank = {"questions": 0, "distinct": 0, "covered": 0, "rate": None, "orphans": []}
    if matcher is not None and getattr(matcher, "entries", None):
        rfi_entries = [e for e in matcher.entries if any(o.file for o in e.occ)]
        covered = [e for e in rfi_entries if e.contents]
        orphans = sorted((e for e in rfi_entries if not e.contents and len(e.files) >= 2), key=lambda e: -len(e.files))
        bank = {"questions": sum(len([o for o in e.occ if o.file]) for e in rfi_entries), "distinct": len(rfi_entries),
                "covered": len(covered), "rate": round(len(covered) / len(rfi_entries), 3) if rfi_entries else None,
                "orphans": [{"question": e.text, "rfis": len(e.files), "last": max((o.date for o in e.occ if o.date), default=""),
                             "answers": [o.answer[:240] for o in e.occ if (o.answer or "").strip()][:2]} for e in orphans[:20]]}
    level_mix = Counter(levels.get(cid, "") or "?" for cid in files_by_content)
    months = sorted(timeline)[-24:]
    return {
        "today": today.isoformat(),
        "rfis": len(rfis), "links": len(links), "texts_reused": len(files_by_content),
        "library": len(contents), "reuse_rate": round(len(files_by_content) / len(contents), 3) if contents else 0.0,
        "modes": dict(modes), "levels": dict(level_mix), "bank": bank,
        "timeline": [{"month": m, "answers": timeline[m]} for m in months],
        "pillars": [card(cid) for cid in pillars], "stale": stale[:15], "unused": unused[:30], "unused_total": len(unused),
    }


__all__ = ["memory"]
