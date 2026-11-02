"""Modifications en masse dans Qvidian, protégées par un mot de passe.

Lecture seule par défaut. Une modification se fait en deux temps :
1. « Prévisualiser » (sans mot de passe) : liste avant / après pour chaque contenu, avec les avertissements ;
2. « Appliquer » (mot de passe QVIDIAN_WRITE_PASSWORD) : chaque contenu est relu dans Qvidian juste avant l'écriture.
   Un contenu en alerte (extrait par quelqu'un, modifié depuis la synchronisation, droit d'édition absent, texte d'un
   contenu fichier) est laissé de côté, sauf si l'on coche « Passer en force » (même mot de passe).
Chaque lot est journalisé (avant / après) dans data/qvidian/journal.jsonl et peut être annulé, avec le mot de passe.
Opération utilisée : libraryContentDetailsUpdate(contentIDs, ContentUpdates) — exemple « Bulk Update » du test UI.
"""
from __future__ import annotations

import hmac
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .client import QvidianError, html_to_text

MAX_ITEMS = 500
CHUNK = 50
LOCK_AFTER = 5
LOCK_SECONDS = 300


ACTIONS = {
    "disable": "Désactiver",
    "enable": "Réactiver",
    "expire": "Fixer la date d'expiration",
    "alert": "Poser une alerte",
    "clear_alert": "Retirer l'alerte",
    "comment": "Remplacer le commentaire",
    "replace_title": "Rechercher / remplacer dans le titre",
    "replace_text": "Rechercher / remplacer dans le texte",
    "set_text": "Réécrire le texte d'un contenu",
    "move": "Déplacer vers un dossier",
    "add_terms": "Ajouter des termes de recherche",
    "undo": "Annulation d'un lot",  # interne : construit par undo_plan
}
UNIFORM = {"disable", "enable", "expire", "alert", "clear_alert", "comment", "move"}  # même changement pour tous : un seul appel par paquet


class WriteGuard:
    """Mot de passe d'écriture (variable d'environnement, jamais dans le code) ; verrou après 5 essais faux."""

    def __init__(self, secret: str):
        self.secret = secret or ""
        self.failures = 0
        self.locked_until = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    @property
    def locked(self) -> int:
        return max(int(self.locked_until - time.time()), 0)

    def verify(self, password: str | None) -> None:
        if not self.configured:
            raise QvidianError("ecriture", "Écriture désactivée : aucun mot de passe d'écriture n'est défini.",
                               "Ajoutez QVIDIAN_WRITE_PASSWORD=… dans le fichier .env du poste puis relancez l'app.")
        with self._lock:
            if self.locked:
                raise QvidianError("verrou", f"Trop d'essais : réessayez dans {self.locked} s.", "Sécurité contre les essais au hasard.")
            if not hmac.compare_digest((password or "").encode("utf-8"), self.secret.encode("utf-8")):
                self.failures += 1
                if self.failures >= LOCK_AFTER:
                    self.failures, self.locked_until = 0, time.time() + LOCK_SECONDS
                raise QvidianError("mot-de-passe", "Mot de passe incorrect.", "Rien n'a été modifié dans Qvidian.")
            self.failures = 0


@dataclass
class Item:
    id: int
    title: str
    field: str
    before: Any
    after: Any
    revision: int = 0
    warnings: list[str] = field(default_factory=list)
    shown_before: str = ""
    shown_after: str = ""

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "field": self.field, "before": self.shown_before or _show(self.before),
                "after": self.shown_after or _show(self.after), "warnings": self.warnings}


@dataclass
class Plan:
    id: str
    action: str
    params: dict[str, Any]
    items: list[Item]
    unchanged: list[int]
    created: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "action": self.action, "label": ACTIONS[self.action], "params": self.params,
                "items": [i.public() for i in self.items], "unchanged": self.unchanged,
                "warnings": sum(1 for i in self.items if i.warnings)}


def _show(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "activé" if value else "désactivé"
    return str(value)


def _replace(text: str, find: str, repl: str, case: bool) -> str:
    return re.sub(re.escape(find), lambda _: repl, text or "", flags=0 if case else re.I)


def make_plan(contents: list[dict[str, Any]], action: str, params: dict[str, Any]) -> Plan:
    if action not in ACTIONS or action == "undo":
        raise QvidianError("qvidian", f"Action inconnue : {action}")
    if len(contents) > MAX_ITEMS:
        raise QvidianError("qvidian", f"{len(contents)} contenus : {MAX_ITEMS} au maximum par lot.", "Filtrez la sélection.")
    items, unchanged = [], []
    find, repl, case = str(params.get("find") or ""), str(params.get("replace") or ""), bool(params.get("case"))
    if action in {"replace_title", "replace_text"} and not find:
        raise QvidianError("qvidian", "Indiquez le texte à rechercher.")
    for c in contents:
        rev = c.get("revision") or 0
        if action in {"disable", "enable"}:
            after = action == "enable"
            item = Item(c["id"], c["title"], "Enabled", c.get("enabled"), after, rev) if c.get("enabled") != after else None
        elif action == "expire":
            when = str(params.get("date") or "")[:10] or None
            if when:
                date.fromisoformat(when)
            item = Item(c["id"], c["title"], "DateToExpire", c.get("expires"), when, rev) if c.get("expires") != when else None
        elif action == "alert":
            text = str(params.get("text") or "").strip()
            if not text:
                raise QvidianError("qvidian", "Indiquez le texte de l'alerte.")
            item = Item(c["id"], c["title"], "AlertText", c.get("alert_text") or "", text, rev) if (c.get("alert_text") or "") != text else None
        elif action == "clear_alert":
            item = Item(c["id"], c["title"], "AlertText", c.get("alert_text") or "", "", rev) if (c.get("alert_text") or c.get("alert_active")) else None
        elif action == "comment":
            text = str(params.get("text") or "")
            item = Item(c["id"], c["title"], "Comments", c.get("comments") or "", text, rev) if (c.get("comments") or "") != text else None
        elif action == "replace_title":
            after = _replace(c["title"], find, repl, case)
            item = Item(c["id"], c["title"], "Title", c["title"], after, rev) if after != c["title"] else None
        elif action == "move":
            target = int(params.get("folder_id") or 0)
            if target <= 0:
                raise QvidianError("qvidian", "Choisissez le dossier de destination.")
            label = str(params.get("folder_label") or target)
            item = Item(c["id"], c["title"], "LibraryFolderID", c.get("folder_id"), target, rev,
                        shown_before=c.get("folder_path") or str(c.get("folder_id") or "—"), shown_after=label) if c.get("folder_id") != target else None
        elif action == "add_terms":
            new = [t.strip() for t in re.split(r"[,;\n]", str(params.get("text") or "")) if t.strip()]
            if not new:
                raise QvidianError("qvidian", "Indiquez au moins un terme (séparés par des virgules).")
            current = [t.strip() for t in re.split(r"[,;\n]", c.get("learned_terms") or "") if t.strip()]
            merged = current + [t for t in new if t.lower() not in {x.lower() for x in current}]
            item = Item(c["id"], c["title"], "LearnedTerms", ", ".join(current), ", ".join(merged), rev) if merged != current else None
        elif action == "set_text":
            if len(contents) != 1:
                raise QvidianError("qvidian", "La réécriture d'un texte se fait contenu par contenu.", "Sélectionnez un seul contenu.")
            text = str(params.get("text") or "")
            if not text.strip():
                raise QvidianError("qvidian", "Le nouveau texte est vide.")
            raw = c.get("raw_text") or c.get("text") or ""
            item = Item(c["id"], c["title"], "ContentText", raw, text, rev, shown_before=html_to_text(raw)[:4000],
                        shown_after=html_to_text(text)[:4000]) if text != raw else None
            if item is not None and not c.get("inline_edit"):
                item.warnings.append("contenu fichier (Word…) : la mise à jour du texte par l'API n'est pas confirmée par la "
                                     "documentation — à tester d'abord sur un contenu")
        else:  # replace_text : sur le texte brut (mise en forme conservée), montré en texte visible
            raw = c.get("raw_text") or c.get("text") or ""
            after = _replace(raw, find, repl, case)
            item = None
            if after != raw:
                item = Item(c["id"], c["title"], "ContentText", raw, after, rev, shown_before=_excerpt_change(html_to_text(raw), find, case),
                            shown_after=_excerpt_change(html_to_text(after), repl, True))
                if not c.get("inline_edit"):
                    item.warnings.append("contenu fichier (Word…) : la mise à jour du texte par l'API n'est pas confirmée par la "
                                         "documentation — à tester d'abord sur un contenu")
        if item is None:
            unchanged.append(c["id"])
            continue
        if c.get("checked_out"):
            item.warnings.append(f"extrait (en cours de modification) par {c.get('checked_out_by') or 'quelqu’un'}")
        items.append(item)
    return Plan(uuid.uuid4().hex[:12], action, params, items, unchanged)


def _excerpt_change(text: str, needle: str, case: bool, width: int = 70) -> str:
    m = re.search(re.escape(needle), text, 0 if case else re.I) if needle else None
    if not m:
        return text[:2 * width]
    start, end = max(m.start() - width, 0), min(m.end() + width, len(text))
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def _changes(item: Item, value: Any) -> dict[str, Any]:
    if item.field == "AlertText":
        return {"AlertText": value or "", "AlertEnabled": bool(value)}
    if item.field == "DateToExpire":
        return {"DateToExpire": date.fromisoformat(value) if value else None}
    if item.field == "LibraryFolderID":
        return {"LibraryFolderID": int(value or 0)}
    return {item.field: value}


class Journal:
    def __init__(self, path: Path):
        self.path = path

    def add(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def all(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def get(self, batch: str) -> dict[str, Any] | None:
        return next((e for e in reversed(self.all()) if e.get("batch") == batch), None)


def apply(client, plan: Plan, force: bool, user: str, journal: Journal, source: str, undo_of: str | None = None) -> dict[str, Any]:
    """Relit chaque contenu dans Qvidian, écrit, journalise. Retourne le détail ligne à ligne."""
    results: list[dict[str, Any]] = []
    ready: list[Item] = []
    for item in plan.items:
        warnings = list(item.warnings)
        try:
            fresh = client.content(item.id)
        except QvidianError as error:
            results.append({"id": item.id, "ok": False, "skipped": False, "error": error.message})
            continue
        if fresh.get("checked_out") and not any("extrait" in w for w in warnings):
            warnings.append(f"extrait par {fresh.get('checked_out_by') or 'quelqu’un'}")
        if item.revision and fresh.get("revision") and fresh["revision"] != item.revision:
            warnings.append(f"modifié dans Qvidian depuis la synchronisation (révision {item.revision} → {fresh['revision']})")
        if fresh.get("edit_perm") is False and getattr(client, "mode", "") != "demo":
            warnings.append("votre compte n'a pas le droit de modifier ce contenu")
        if warnings and not force:
            results.append({"id": item.id, "ok": False, "skipped": True, "error": "; ".join(warnings)})
            continue
        ready.append(item)
    if plan.action in UNIFORM and ready:
        changes = _changes(ready[0], ready[0].after)
        for i in range(0, len(ready), CHUNK):
            chunk = ready[i:i + CHUNK]
            try:
                problems = {p["id"]: p for p in client.update_details([it.id for it in chunk], changes)}
            except QvidianError as error:
                results.extend({"id": it.id, "ok": False, "skipped": False, "error": error.message} for it in chunk)
                continue
            for it in chunk:
                p = problems.get(it.id)
                results.append({"id": it.id, "ok": p is None, "skipped": False,
                                "error": f"codes d'erreur Qvidian : {', '.join(p['errors'])}" if p else ""})
    else:
        for it in ready:
            try:
                problems = client.update_details([it.id], _changes(it, it.after))
                results.append({"id": it.id, "ok": not problems, "skipped": False,
                                "error": f"codes d'erreur Qvidian : {', '.join(problems[0]['errors'])}" if problems else ""})
            except QvidianError as error:
                results.append({"id": it.id, "ok": False, "skipped": False, "error": error.message})
    ok_ids = {r["id"] for r in results if r["ok"]}
    batch = uuid.uuid4().hex[:10]
    journal.add({"batch": batch, "at": datetime.now().isoformat(timespec="seconds"), "user": user, "source": source,
                 "action": plan.action, "label": ACTIONS[plan.action], "force": force, "undo_of": undo_of,
                 "items": [{"id": it.id, "title": it.title, "field": it.field, "before": it.before, "after": it.after, "ok": it.id in ok_ids}
                           for it in plan.items]})
    return {"batch": batch, "written": len(ok_ids), "skipped": sum(1 for r in results if r["skipped"]),
            "failed": sum(1 for r in results if not r["ok"] and not r["skipped"]), "results": results}


def undo_plan(entry: dict[str, Any]) -> Plan:
    """Plan inverse d'un lot journalisé : chaque champ écrit reprend sa valeur d'avant."""
    items = [Item(i["id"], i["title"], i["field"], i["after"], i["before"]) for i in entry["items"] if i.get("ok")]
    return Plan(uuid.uuid4().hex[:12], "undo", {"undo": entry["batch"]}, items, [])  # une écriture par contenu


__all__ = ["WriteGuard", "make_plan", "apply", "undo_plan", "Journal", "Plan", "ACTIONS"]
