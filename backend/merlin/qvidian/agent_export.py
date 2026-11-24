"""Export de la bibliothèque Qvidian vers un dossier lu par un agent (Copilot M365 : dossier SharePoint synchronisé).

Deux modes :
- « texts » (défaut) : un fichier Word par texte, rangé par dossier Qvidian de premier niveau. Un dossier SharePoint
  compte pour une seule source de l'agent ; la recherche tombe sur le texte exact et son identifiant.
- « bundles » : 20 fichiers Word au plus (un par thème), chaque texte sous son propre titre. Pour un agent limité à
  20 fichiers.
Chaque texte porte en tête ses métadonnées (identifiant, statut, dates, niveau, fonds, utilisations) et les questions
de RFI auxquelles il a déjà répondu : c'est ce qui fait retrouver le bon texte à partir d'une question de client.

Incrémental : `_merlin_export.json` (dans le dossier) garde l'empreinte de chaque fichier ; seuls les fichiers dont le
contenu a changé sont réécrits (écriture atomique), et seuls des fichiers écrits par cet export sont retirés. Lecture
seule pour Qvidian ; rien d'autre n'est touché dans le dossier.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .levels import FundNames, classify, fund_folders

MANIFEST = "_merlin_export.json"
FORMAT = 1  # à augmenter si la présentation des fichiers change (tout est alors réécrit)
MAX_BUNDLES = 20
MODES = {"texts", "bundles"}

INSTRUCTIONS = """Tu es l'assistant de l'équipe RFP. Tes connaissances sont les réponses types de la bibliothèque Qvidian, \
tenues à jour automatiquement.
Chaque texte commence par une fiche : « Identifiant Qvidian », « Statut », « Dernière modification », « Niveau », \
« Fonds », « Utilisations », puis « Questions de RFI déjà posées » et la « Réponse ».

Règles :
1. Réponds uniquement à partir de ces textes. Si aucun ne répond, dis-le : n'invente jamais un chiffre, une date ou un nom.
2. Cite toujours l'identifiant Qvidian (ex. C1041) et la date de dernière modification de chaque texte utilisé.
3. Entre plusieurs textes proches, préfère le plus récent, puis le plus utilisé. Signale les contradictions.
4. Un texte au statut « expiré » ne se propose qu'en dernier recours, en le disant clairement.
5. Respecte le niveau : un texte « fonds » ou « part » ne vaut que pour le fonds ou la part cités dans sa fiche ; ne \
l'applique jamais à un autre fonds.
6. Réponds dans la langue de la question. Reprends le texte tel quel quand il convient ; sinon dis ce que tu as adapté.
7. Les chiffres (encours, performances, effectifs) datent de la dernière modification du texte : rappelle de les vérifier."""


def _safe(name: str, limit: int) -> str:
    """Nom de fichier ou de dossier accepté par Windows, OneDrive et SharePoint, court (chemins longs)."""
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = re.sub(r'[\\/:*?"<>|#%&{}~\x00-\x1f]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit].rstrip(" .") or "Sans titre"


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _is_expired(c: dict[str, Any], today: str) -> bool:
    return bool(c.get("expired")) or bool(_day(c.get("expires")) and _day(c.get("expires")) < today)


def _fiche(c: dict[str, Any], level, history: dict[str, Any] | None, today: str) -> list[tuple[str, str]]:
    public = level.public()
    rows = [("Identifiant Qvidian", f"C{c['id']}"),
            ("Statut", "expiré" if _is_expired(c, today) else "actif"),
            ("Dossier Qvidian", c.get("folder_path") or "—"),
            ("Langue", c.get("language") or "—"),
            ("Niveau", public["scope_label"]),
            ("Fonds", ", ".join(public["funds"]) or "—"),
            ("ISIN", ", ".join(public["isins"]) or "—"),
            ("Thèmes", ", ".join(public["theme_labels"]) or "—"),
            ("Dernière modification", _day(c.get("modified")) or "—"),
            ("Expire le", _day(c.get("expires")) or "—"),
            ("Utilisations", str(c.get("times_used") or 0)),
            ("Dernière utilisation", _day(c.get("last_used")) or "—")]
    if history and history.get("questions"):
        files = history.get("files") or 0
        count = files if isinstance(files, int) else len(files)
        rows.append(("Choisi dans d'anciens RFI", f"{count} fichier(s), dernier le {history.get('last') or '—'}"))
    return rows


def _entry(c: dict[str, Any], level, history: dict[str, Any] | None, today: str) -> dict[str, Any]:
    """Contenu d'un texte, indépendant du format : sert au fichier et à l'empreinte."""
    title = (c.get("title") or "").strip() or f"Texte {c['id']}"
    question = (c.get("question") or "").strip()
    asked = [q for q in (history or {}).get("questions", []) if q.strip()][:12]
    return {"id": c["id"], "title": title, "question": question if question and question != title else "",
            "fiche": _fiche(c, level, history, today), "asked": asked, "text": (c.get("text") or "").strip() or "(texte vide dans Qvidian)"}


def _digest(payload: Any) -> str:
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def _write_entry(doc, e: dict[str, Any], heading: int) -> None:
    doc.add_heading(f"C{e['id']} — {e['title']}", level=heading)
    if e["question"]:
        doc.add_paragraph(f"Question type : {e['question']}")
    for label, value in e["fiche"]:
        doc.add_paragraph(f"{label} : {value}")
    if e["asked"]:
        doc.add_heading("Questions de RFI déjà posées", level=heading + 1)
        for q in e["asked"]:
            doc.add_paragraph(q, style="List Bullet")
    doc.add_heading("Réponse", level=heading + 1)
    for block in re.split(r"\n\s*\n|\r\n\s*\r\n", e["text"]):
        if block.strip():
            doc.add_paragraph(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", block.strip()))


def _save(doc, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"~{target.stem[:40]}.tmp")
    doc.save(str(tmp))
    os.replace(tmp, target)  # écriture atomique : l'agent ne lit jamais un fichier à moitié écrit


def _plan_texts(entries: list[tuple[dict, dict]]) -> dict[str, dict[str, Any]]:
    """{chemin relatif: {"entries", "title"}} : un fichier par texte, rangé par dossier Qvidian de premier niveau."""
    plan = {}
    for c, e in entries:
        top = _safe((c.get("folder_path") or "").split(" / ")[0] or "Sans dossier", 40)
        plan[f"{top}/C{c['id']} - {_safe(e['title'], 60)}.docx"] = {"entries": [e], "title": None}
    return plan


def _plan_bundles(entries: list[tuple[dict, dict]], themes: dict[int, str]) -> dict[str, dict[str, Any]]:
    """20 fichiers au plus : un par thème ; les plus petits thèmes sont regroupés dans « Autres thèmes »."""
    groups: dict[str, list[dict]] = {}
    for c, e in entries:
        groups.setdefault(themes.get(c["id"]) or "Divers", []).append(e)
    names = sorted(groups, key=lambda n: -len(groups[n]))
    if len(names) > MAX_BUNDLES:
        rest = [e for n in names[MAX_BUNDLES - 1:] for e in groups.pop(n)]
        groups["Autres thèmes"] = groups.get("Autres thèmes", []) + rest
    return {f"Qvidian - {_safe(name, 60)}.docx": {"entries": sorted(items, key=lambda e: e["id"]), "title": f"Réponses types Qvidian — {name}"}
            for name, items in groups.items()}


def _load_manifest(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def export(contents: list[dict[str, Any]], folder: Path, source: str, mode: str = "texts", include_expired: bool = True,
           history: dict[int, dict[str, Any]] | None = None, today: str | None = None) -> dict[str, Any]:
    """Écrit (ou met à jour) le dossier de l'agent. Renvoie le bilan : écrits, inchangés, retirés."""
    from docx import Document

    if mode not in MODES:
        raise ValueError(f"mode inconnu : {mode}")
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")
    today = today or date.today().isoformat()
    history = history or {}
    kept = [c for c in contents if c.get("enabled", True) and (include_expired or not _is_expired(c, today))]
    funds = FundNames(fund_folders([c.get("folder_path") or "" for c in contents]))
    entries, themes = [], {}
    for c in kept:
        level = classify(c.get("title") or "", c.get("text") or "", c.get("folder_path") or "", funds, c.get("question") or "")
        labels = level.public()["theme_labels"]
        themes[c["id"]] = labels[0] if labels else ""
        entries.append((c, _entry(c, level, history.get(c["id"]), today)))
    plan = _plan_texts(entries) if mode == "texts" else _plan_bundles(entries, themes)

    manifest = _load_manifest(folder)
    same_series = manifest.get("source") == source and manifest.get("mode") == mode and manifest.get("format") == FORMAT
    known: dict[str, str] = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    written, unchanged, files = 0, 0, {}
    for rel, item in plan.items():
        digest = _digest(item)
        files[rel] = digest
        target = folder / rel
        if same_series and known.get(rel) == digest and target.exists():
            unchanged += 1
            continue
        doc = Document()
        if item["title"]:
            doc.add_heading(item["title"], level=0)
            doc.add_paragraph(f"{len(item['entries'])} texte(s) · mis à jour le {today}")
        for e in item["entries"]:
            _write_entry(doc, e, 1)
        _save(doc, target)
        written += 1
    removed = 0
    for rel in known:  # seulement des fichiers écrits par un export précédent
        if rel not in files and re.fullmatch(r"[^/\\]+(/[^/\\]+)?\.docx", rel):
            try:
                (folder / rel).unlink()
                removed += 1
            except OSError:
                pass
    for sub in {Path(rel).parent for rel in known if "/" in rel}:
        try:
            (folder / sub).rmdir()  # dossier vidé par l'export : retiré ; non vide : laissé
        except OSError:
            pass
    now = datetime.now().isoformat(timespec="seconds")
    result = {"at": now, "mode": mode, "source": source, "texts": len(kept), "files": len(files), "written": written,
              "unchanged": unchanged, "removed": removed, "expired": sum(_is_expired(c, today) for c in kept)}
    tmp = folder / f"~{MANIFEST}.tmp"
    tmp.write_text(json.dumps({"source": source, "mode": mode, "format": FORMAT, "last": result, "files": files}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, folder / MANIFEST)
    return result


class AgentExportConfig:
    """Réglages mémorisés sur le poste (data/qvidian/agent_export.json, jamais committé)."""

    DEFAULT = {"path": "", "mode": "texts", "include_expired": True, "auto": True, "last": None, "error": None}

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            return {**self.DEFAULT, **json.loads(self.path.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            return dict(self.DEFAULT)

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        data = {**self.load(), **{k: v for k, v in values.items() if k in self.DEFAULT}}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        return data
