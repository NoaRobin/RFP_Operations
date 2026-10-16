"""Instantané local de la bibliothèque Qvidian (SQLite + recherche plein texte FTS5), sous data/qvidian/ (jamais committé).

Synchronisation = parcours des dossiers (libraryFolderGetTop → libraryFoldersGetList → libraryFolderContentGetList),
les opérations utilisées par l'exemple WSManual. Chaque texte déjà vu est gardé dans `versions` : les réponses
évoluent (mises à jour), l'agrégation les regroupe en familles et propose la rédaction la plus récente.
Un instantané de démonstration et un instantané réel ne partagent jamais le même fichier.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .client import html_to_text

FOLDER_LIST_MAX = 500  # libraryFolderContentGetList : 500 éléments au plus (guide)
COLUMNS = ["id", "revision", "guid", "folder_id", "folder", "folder_path", "title", "text", "raw_text", "type", "language", "lcid",
           "enabled", "expired", "created", "modified", "last_used", "expires", "times_used", "owners", "modified_by", "alert_text",
           "alert_active", "inline_edit", "checked_out", "checked_out_by", "question", "learned_terms", "assigned_terms", "file_ext",
           "edit_perm", "comments"]
BOOLS = {"enabled", "expired", "alert_active", "inline_edit", "checked_out", "edit_perm"}
STOP = set("""a au aux avec ce ces dans de des du elle en et est il ils la le les leur leurs mais ne nos notre nous ou par pas pour qu
que quel quelle quelles quels qui sa se ses son sont sur ta te tes ton tu un une vos votre vous y the of and or to in on for is are be
by with as at an your you our we do does what which how who from this that these those please describe provide""".split())


class Snapshot:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as db:
            db.executescript(f"""
                CREATE TABLE IF NOT EXISTS contents ({', '.join(c + (' INTEGER PRIMARY KEY' if c == 'id' else '') for c in COLUMNS)}, synced_at TEXT);
                CREATE TABLE IF NOT EXISTS folders (id INTEGER PRIMARY KEY, parent_id INTEGER, title TEXT, path TEXT, contents INTEGER);
                CREATE TABLE IF NOT EXISTS versions (content_id INTEGER, revision INTEGER, hash TEXT, title TEXT, text TEXT, modified TEXT,
                                                     seen_at TEXT, PRIMARY KEY (content_id, hash));
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(title, question, text, terms, tokenize='unicode61 remove_diacritics 2');
            """)

    def _conn(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------------ écriture
    def upsert(self, contents: list[dict[str, Any]], now: str | None = None) -> None:
        now = now or datetime.now().isoformat(timespec="seconds")
        with self._lock, self._conn() as db:
            for c in contents:
                row = [int(c[k]) if k in BOOLS else c.get(k) for k in COLUMNS]
                db.execute(f"INSERT OR REPLACE INTO contents ({', '.join(COLUMNS)}, synced_at) VALUES ({', '.join('?' * (len(COLUMNS) + 1))})", row + [now])
                db.execute("DELETE FROM search WHERE rowid = ?", (c["id"],))
                db.execute("INSERT INTO search (rowid, title, question, text, terms) VALUES (?, ?, ?, ?, ?)",
                           (c["id"], c.get("title", ""), c.get("question", ""), c.get("text", ""),
                            f"{c.get('learned_terms', '')} {c.get('assigned_terms', '')}"))
                digest = hashlib.sha1(f"{c.get('title', '')}\n{c.get('text', '')}".encode("utf-8")).hexdigest()[:16]
                db.execute("INSERT OR IGNORE INTO versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (c["id"], c.get("revision", 0), digest, c.get("title", ""), c.get("text", ""), c.get("modified"), now))

    def replace(self, folders: list[dict[str, Any]], contents: list[dict[str, Any]], source: str) -> None:
        """Fin de synchronisation complète : les contenus disparus de Qvidian sont retirés (leurs versions restent)."""
        ids = {c["id"] for c in contents}
        self.upsert(contents)
        with self._lock, self._conn() as db:
            for (cid,) in db.execute("SELECT id FROM contents").fetchall():
                if cid not in ids:
                    db.execute("DELETE FROM contents WHERE id = ?", (cid,))
                    db.execute("DELETE FROM search WHERE rowid = ?", (cid,))
            db.execute("DELETE FROM folders")
            db.executemany("INSERT INTO folders VALUES (?, ?, ?, ?, ?)",
                           [(f["id"], f["parent_id"], f["title"], f["path"], f.get("contents", 0)) for f in folders])
            for key, value in {"source": source, "synced_at": datetime.now().isoformat(timespec="seconds"),
                               "count": str(len(contents))}.items():
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    # ------------------------------------------------------------------ lecture
    def meta(self) -> dict[str, str]:
        with self._conn() as db:
            return {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM meta")}

    def _row(self, r: sqlite3.Row) -> dict[str, Any]:
        d = {k: r[k] for k in COLUMNS}
        for k in BOOLS:
            d[k] = bool(d[k])
        return d

    def all(self) -> list[dict[str, Any]]:
        with self._conn() as db:
            return [self._row(r) for r in db.execute(f"SELECT {', '.join(COLUMNS)} FROM contents ORDER BY id")]

    def get(self, content_id: int) -> dict[str, Any] | None:
        with self._conn() as db:
            r = db.execute(f"SELECT {', '.join(COLUMNS)} FROM contents WHERE id = ?", (content_id,)).fetchone()
            return self._row(r) if r else None

    def many(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        with self._conn() as db:
            rows = db.execute(f"SELECT {', '.join(COLUMNS)} FROM contents WHERE id IN ({', '.join('?' * len(ids))})", ids).fetchall()
            return [self._row(r) for r in rows]

    def folders(self) -> list[dict[str, Any]]:
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT * FROM folders ORDER BY path")]

    def versions(self, content_id: int) -> list[dict[str, Any]]:
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT revision, title, text, modified, seen_at FROM versions WHERE content_id = ? "
                                                "ORDER BY seen_at DESC, revision DESC", (content_id,))]

    def search(self, text: str, k: int = 40) -> list[dict[str, Any]]:
        words = [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 2 and w not in STOP][:24]
        if not words:
            return []
        query = " OR ".join(f'"{w}"' for w in dict.fromkeys(words))
        with self._conn() as db:
            try:
                ids = [r[0] for r in db.execute("SELECT rowid FROM search WHERE search MATCH ? ORDER BY bm25(search, 4.0, 4.0, 1.0, 2.0) LIMIT ?",
                                                (query, k))]
            except sqlite3.OperationalError:
                return []
        by_id = {c["id"]: c for c in self.many(ids)}
        return [by_id[i] for i in ids if i in by_id]

    @property
    def empty(self) -> bool:
        with self._conn() as db:
            return db.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 0


def sync(client, snapshot: Snapshot, source: str, progress: Callable[[str, int, int], None] | None = None,
         preview_limit: int = 3000) -> dict[str, Any]:
    """Parcourt toute la bibliothèque et remplace l'instantané. Texte vide → aperçu HTML (libraryContentPreviewHTMLGet)."""
    say = progress or (lambda *_: None)
    top = client.top_folder()
    folders: list[dict[str, Any]] = []
    queue = [(top, "")]
    contents: list[dict[str, Any]] = []
    previews = 0
    problems: list[str] = []
    while queue:
        folder, path = queue.pop(0)
        here = f"{path} / {folder['title']}".strip(" /") if folder["id"] != top["id"] else ""
        folders.append({**folder, "path": here})
        say(f"Dossier « {here or folder['title']} »", len(contents), 0)
        if folder.get("contents", 1):
            try:
                items = client.folder_contents(folder["id"])
                # Au-delà de 500 éléments la liste du dossier est tronquée (guide) : on repasse par la recherche paginée
                if (len(items) >= FOLDER_LIST_MAX or folder.get("contents", 0) > len(items)) and hasattr(client, "folder_contents_paged"):
                    try:
                        paged = client.folder_contents_paged(folder["id"])
                        if len(paged) > len(items):
                            items = paged
                    except Exception as error:  # noqa: BLE001 - on garde la liste partielle, avec l'alerte
                        problems.append(f"{here or folder['title']} : liste limitée à {len(items)} contenus "
                                        f"({getattr(error, 'message', type(error).__name__)})")
            except Exception as error:  # noqa: BLE001 - un dossier refusé n'arrête pas la synchronisation
                problems.append(f"{here or folder['title']} : {getattr(error, 'message', type(error).__name__)}")
                items = []
            for c in items:
                c["folder_path"] = c.get("folder_path") or here
                if not c.get("text") and previews < preview_limit and c.get("type", "").lower() not in {"slide", "file"}:
                    previews += 1
                    try:
                        c["text"] = html_to_text(client.preview_html(c["id"], c["revision"]))
                    except Exception:  # noqa: BLE001 - droit AllowPreviewHTML absent : le texte reste vide
                        pass
                contents.append(c)
        if folder.get("children", 1):
            try:
                children = client.folders(folder["id"])
            except Exception as error:  # noqa: BLE001
                problems.append(f"{here or folder['title']} (sous-dossiers) : {getattr(error, 'message', type(error).__name__)}")
                children = []
            queue.extend((child, here) for child in children)
    snapshot.replace(folders, contents, source)
    say("Terminé", len(contents), len(contents))
    return {"contents": len(contents), "folders": len(folders), "previews": previews, "problems": problems[:20]}



__all__ = ["Snapshot", "sync"]
