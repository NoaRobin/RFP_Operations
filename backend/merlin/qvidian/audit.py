"""Carte des erreurs de la bibliothèque Qvidian : contrôles déterministes, lisibles, réglables dans rules.yaml.

Catégories : code informatique dans le texte, texte à compléter, texte dépassé (termes, dates anciennes, non relu),
contenu expiré, doublon, langue, jamais utilisé, et les constats de l'analyse IA (Copilot) quand elle a été faite.
La carte croise les dossiers de la bibliothèque et les catégories : chaque case donne le nombre de contenus touchés.
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..rfi.aggregate import norm, shingles, similarity, to_date

RULES_PATH = Path(__file__).with_name("rules.yaml")
CATEGORIES = [
    ("code", "Code informatique", "haute"),
    ("provisoire", "À compléter", "haute"),
    ("expire", "Expiré", "haute"),
    ("depasse", "Texte dépassé", "moyenne"),
    ("langue", "Langue", "moyenne"),
    ("doublon", "Doublon", "basse"),
    ("inutilise", "Peu ou pas utilisé", "basse"),
    ("ia", "Analyse IA", "moyenne"),
]
LABEL = {k: label for k, label, _ in CATEGORIES}
SEVERITY = {k: sev for k, _, sev in CATEGORIES}
MONTHS = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|" \
         "january|february|march|april|may|june|july|august|september|october|november|december"
DATED = re.compile(rf"(?:\b\d{{1,2}}[/.-]\d{{1,2}}[/.-]((?:19|20)\d{{2}})\b)|(?:\b(?:{MONTHS})\s+((?:19|20)\d{{2}})\b)|"
                   rf"(?:\b(?:fin|end|as of|as at|au|at)\s+((?:19|20)\d{{2}})\b)|(?:\b[QT][1-4]\s*((?:19|20)\d{{2}})\b)", re.I)
FR_WORDS = set("le la les des du de et est une un pour dans sur avec par au aux nous notre nos sont qui que".split())
EN_WORDS = set("the and is are of to for in on with by our we which that this be has have".split())


@lru_cache(maxsize=4)
def _rules(path: str, mtime: float) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for group in ("code_informatique", "a_completer", "termes_depasses"):
        for rule in raw.get(group) or []:
            rule["re"] = re.compile(rule["motif"], re.I | re.M if group != "code_informatique" else re.M)
    return raw


def rules(path: Path = RULES_PATH) -> dict[str, Any]:
    return _rules(str(path), path.stat().st_mtime)


def _excerpt(text: str, m: re.Match, width: int = 50) -> str:
    start, end = max(m.start() - width, 0), min(m.end() + width, len(text))
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")


def language_of(text: str) -> str | None:
    words = re.findall(r"[a-zà-ÿ]+", (text or "").lower())
    if len(words) < 12:
        return None
    fr, en = sum(w in FR_WORDS for w in words), sum(w in EN_WORDS for w in words)
    if fr >= 3 and fr > 2 * en:
        return "fr"
    if en >= 3 and en > 2 * fr:
        return "en"
    return None


def check(c: dict[str, Any], today: date, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Constats d'un contenu (hors doublons, qui demandent de comparer les contenus entre eux)."""
    out: list[dict[str, Any]] = []
    seuils = cfg.get("seuils") or {}
    text = c.get("text") or ""
    visible = f"{c.get('title') or ''}\n{text}"

    def add(category: str, message: str, excerpt: str = "", severity: str | None = None) -> None:
        out.append({"category": category, "label": LABEL[category], "severity": severity or SEVERITY[category], "message": message,
                    "excerpt": excerpt})

    seen: set[str] = set()
    for rule in cfg.get("code_informatique") or []:
        m = rule["re"].search(visible)
        if m and rule["raison"] not in seen:
            seen.add(rule["raison"])
            add("code", rule["raison"], _excerpt(visible, m))
    if not text.strip() and (c.get("type") or "").lower() not in {"slide", "file", "fichier"}:
        add("provisoire", "texte vide (contenu Q&A sans réponse lisible)")
    for rule in cfg.get("a_completer") or []:
        m = rule["re"].search(text)
        if m:
            add("provisoire", rule["raison"], _excerpt(text, m))
            break
    for rule in cfg.get("termes_depasses") or []:
        m = rule["re"].search(visible)
        if m:
            add("depasse", rule["raison"], _excerpt(visible, m))
    years = [int(y) for m in DATED.finditer(text) for y in m.groups() if y]
    if years and max(years) <= today.year - int(seuils.get("date_ancienne_annees", 2)):
        m = next(DATED.finditer(text))
        add("depasse", f"chiffre ou fait daté de {max(years)}", _excerpt(text, m))
    modified = to_date(c.get("modified"))
    if modified and (today - modified).days > 365 * int(seuils.get("non_relu_annees", 3)):
        add("depasse", f"non modifié depuis le {modified.strftime('%d/%m/%Y')}", severity="basse")
    expires = to_date(c.get("expires"))
    if c.get("expired") or (expires and expires < today):
        add("expire", f"expiré{' le ' + expires.strftime('%d/%m/%Y') if expires else ''}" + (" et encore activé" if c.get("enabled") else ""))
    elif expires and (expires - today).days <= int(seuils.get("expire_bientot_jours", 30)):
        add("expire", f"expire le {expires.strftime('%d/%m/%Y')}", severity="basse")
    expected = (cfg.get("langues") or {}).get(c.get("lcid"))
    found = language_of(text)
    if expected and found and expected != found:
        add("langue", f"texte en {'anglais' if found == 'en' else 'français'}, langue déclarée : {c.get('language') or c.get('lcid')}")
    created, last_used = to_date(c.get("created")), to_date(c.get("last_used"))
    if not c.get("times_used") and created and (today - created).days > int(seuils.get("jamais_utilise_jours", 365)):
        add("inutilise", f"jamais utilisé depuis sa création ({created.strftime('%d/%m/%Y')})")
    elif last_used and (today - last_used).days > 365 * int(seuils.get("pas_utilise_annees", 3)):
        add("inutilise", f"pas utilisé depuis le {last_used.strftime('%d/%m/%Y')}")
    return out


def duplicates(contents: list[dict[str, Any]], threshold: float = 0.85, common: int = 50) -> dict[int, list[int]]:
    """Textes quasi identiques dans des contenus différents (index inversé de suites de mots, sans comparer tout à tout)."""
    sh = {c["id"]: shingles(c["text"]) for c in contents if len(norm(c.get("text") or "")) >= 40}
    index: dict[str, list[int]] = {}
    for cid, s in sh.items():
        for g in s:
            index.setdefault(g, []).append(cid)
    pairs: dict[tuple[int, int], int] = {}
    for ids in index.values():
        if 1 < len(ids) <= common:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1
    by_id = {c["id"]: c for c in contents}
    out: dict[int, list[int]] = {}
    for (a, b), n in pairs.items():
        if n >= 3 and similarity(by_id[a]["text"], by_id[b]["text"]) >= threshold:
            out.setdefault(a, []).append(b)
            out.setdefault(b, []).append(a)
    return out


def group_of(path: str, depth: int = 2) -> str:
    parts = [p.strip() for p in (path or "").split("/") if p.strip()]
    return " / ".join(parts[:depth]) or "(racine)"


def audit(contents: list[dict[str, Any]], today: date | None = None, ai: dict[str, Any] | None = None,
          cfg: dict[str, Any] | None = None, depth: int = 2) -> dict[str, Any]:
    today = today or date.today()
    cfg = cfg or rules()
    dup = duplicates(contents, float((cfg.get("seuils") or {}).get("doublon_similarite", 0.85)))
    by_id = {c["id"]: c for c in contents}
    items = []
    for c in contents:
        issues = check(c, today, cfg)
        if c["id"] in dup:
            others = sorted(dup[c["id"]])
            issues.append({"category": "doublon", "label": LABEL["doublon"], "severity": SEVERITY["doublon"],
                           "message": "même texte que " + ", ".join(f"#{o} ({by_id[o]['title'][:40]})" for o in others[:3]), "excerpt": "",
                           "others": others})
        for f in (ai or {}).get(str(c["id"]), {}).get("findings", []):
            if (ai or {})[str(c["id"])].get("revision") in (None, c.get("revision")):
                issues.append({"category": "ia", "label": LABEL["ia"], "severity": f.get("severity") or "moyenne",
                               "message": f"{f.get('kind') or 'IA'} : {f.get('problem')}", "excerpt": "", "fix": f.get("fix") or ""})
        items.append({"id": c["id"], "title": c["title"], "folder_path": c.get("folder_path") or "", "group": group_of(c.get("folder_path"), depth),
                      "enabled": c.get("enabled"), "times_used": c.get("times_used"), "last_used": c.get("last_used"),
                      "modified": c.get("modified"), "revision": c.get("revision"), "issues": issues, "text": (c.get("text") or "")[:600]})
    groups: dict[str, dict[str, Any]] = {}
    for it in items:
        g = groups.setdefault(it["group"], {"group": it["group"], "total": 0, "counts": {k: 0 for k, *_ in CATEGORIES}, "with_issues": 0})
        g["total"] += 1
        cats = {i["category"] for i in it["issues"]}
        g["with_issues"] += bool(cats)
        for k in cats:
            g["counts"][k] += 1
    categories = [{"key": k, "label": label, "severity": sev, "count": sum(1 for it in items if any(i["category"] == k for i in it["issues"]))}
                  for k, label, sev in CATEGORIES]
    return {"today": today.isoformat(), "contents": len(items), "with_issues": sum(1 for it in items if it["issues"]),
            "categories": categories, "groups": sorted(groups.values(), key=lambda g: g["group"]),
            "items": sorted(items, key=lambda it: (-len(it["issues"]), it["id"]))}


__all__ = ["audit", "check", "duplicates", "rules", "CATEGORIES", "language_of", "group_of"]
