"""Instantané local de la bibliothèque Qvidian (SQLite + recherche plein texte FTS5), sous data/qvidian/ (jamais committé).

Synchronisation complète = parcours des dossiers (libraryFolderGetTop → libraryFoldersGetList), puis contenus de chaque
dossier par recherche filtrée (en parallèle, débit plafonné) ; incrémentale = contenus modifiés depuis la dernière fois
(filtre DateLastModified) et contrôle des suppressions par lots d'identifiants (filtre ContentID MatchesAny). Chaque texte déjà vu est gardé dans `versions` : les réponses
évoluent (mises à jour), l'agrégation les regroupe en familles et propose la rédaction la plus récente.
Un instantané de démonstration et un instantané réel ne partagent jamais le même fichier.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .client import html_to_text, is_excerpt

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
            db.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', ?)", (datetime.now().isoformat(timespec="microseconds"),))

    def remove(self, ids: list[int]) -> None:
        """Contenus supprimés de Qvidian (synchronisation incrémentale) : retirés de l'instantané, leurs versions restent."""
        with self._lock, self._conn() as db:
            for cid in ids:
                db.execute("DELETE FROM contents WHERE id = ?", (cid,))
                db.execute("DELETE FROM search WHERE rowid = ?", (cid,))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('count', ?)", (str(db.execute("SELECT COUNT(*) FROM contents").fetchone()[0]),))

    def set_meta(self, values: dict[str, Any]) -> None:
        with self._lock, self._conn() as db:
            for key, value in values.items():
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, str(value)))

    def ids(self) -> list[int]:
        with self._conn() as db:
            return [r[0] for r in db.execute("SELECT id FROM contents")]

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


def _folder_items(client, folder: dict[str, Any], here: str, problems: list[str]) -> list[dict[str, Any]]:
    """Contenus d'un dossier : recherche filtrée sur le dossier (texte, utilisations, dates), sinon liste simple."""
    try:
        # Guide (libraryFolderContentGetList) : 500 éléments au plus et champs réduits (ni texte, ni compteurs
        # d'utilisation) ; la voie recommandée est librarySearch filtré sur la colonne LibraryFolderID.
        items = []
        if hasattr(client, "folder_contents_paged"):
            try:
                items = client.folder_contents_paged(folder["id"])
            except Exception as error:  # noqa: BLE001 - repli sur la liste du dossier, avec l'alerte
                problems.append(f"{here or folder['title']} : recherche par dossier refusée, liste simple utilisée "
                                f"({getattr(error, 'message', type(error).__name__)})")
        if not items:
            items = client.folder_contents(folder["id"])
            if len(items) >= FOLDER_LIST_MAX:
                problems.append(f"{here or folder['title']} : liste limitée à {FOLDER_LIST_MAX} contenus")
    except Exception as error:  # noqa: BLE001 - un dossier refusé n'arrête pas la synchronisation
        problems.append(f"{here or folder['title']} : {getattr(error, 'message', type(error).__name__)}")
        items = []
    for c in items:
        c["folder_path"] = c.get("folder_path") or here
    return items


def full_text(client, c: dict[str, Any]) -> bool:
    """Texte entier d'un contenu dont on n'a que l'extrait : aperçu HTML (libraryContentPreviewHTMLGet), sinon détails
    (libraryContentDetailsGet) ; garde le plus long. Vrai si le texte a été complété."""
    best = c.get("text") or ""
    try:
        best = max(best, html_to_text(client.preview_html(c["id"], c.get("revision", -1)) or ""), key=len)
    except Exception:  # noqa: BLE001 - droit d'aperçu absent : on essaie les détails
        pass
    if is_excerpt({**c, "text": best}):
        try:
            best = max(best, client.content(c["id"]).get("text") or "", key=len)
        except Exception:  # noqa: BLE001
            pass
    if len(best) > len(c.get("text") or ""):
        c["text"] = best
        return True
    return False


def _previews(client, contents: list[dict[str, Any]], limit: int, workers: int) -> int:
    """Texte vide → aperçu HTML ; extrait coupé à ~1000 caractères → texte entier (tous, sans limite). En parallèle."""
    empty = [c for c in contents if not c.get("text") and (c.get("type") or "").lower() not in {"slide", "file"}][:limit]
    todo = empty + [c for c in contents if c.get("text") and is_excerpt(c)]

    def one(c: dict[str, Any]) -> None:
        full_text(client, c)

    if workers > 1 and len(todo) > 1:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qvidian-preview") as pool:
            list(pool.map(one, todo))
    else:
        for c in todo:
            one(c)
    return len(todo)


def sync(client, snapshot: Snapshot, source: str, progress: Callable[[str, int, int], None] | None = None,
         preview_limit: int = 3000, workers: int = 1, mode: str = "full") -> dict[str, Any]:
    """Synchronisation de l'instantané.

    full  : parcours de tous les dossiers ; contenus lus en parallèle (`workers` fils, débit plafonné par le client).
    delta : seulement les contenus modifiés depuis la dernière synchronisation (moins un jour de marge), puis contrôle des
            suppressions par lots d'identifiants. Repli automatique sur « full » si le serveur refuse le filtre de date."""
    say = progress or (lambda *_: None)
    started = time.time()
    meta = snapshot.meta()
    if mode == "delta" and meta.get("synced_at") and not snapshot.empty and getattr(client, "delta_supported", None) is not False \
            and hasattr(client, "changed_since"):
        try:
            return _delta(client, snapshot, source, say, preview_limit, workers, meta, started)
        except Exception as error:  # noqa: BLE001 - filtre de date refusé : synchronisation complète
            note = f"incrémental indisponible ({getattr(error, 'message', type(error).__name__)}) : synchronisation complète"
            result = _full(client, snapshot, source, say, preview_limit, workers, started)
            result["problems"] = [note] + result["problems"]
            return result
    return _full(client, snapshot, source, say, preview_limit, workers, started)


def _full(client, snapshot: Snapshot, source: str, say, preview_limit: int, workers: int, started: float) -> dict[str, Any]:
    top = client.top_folder()
    folders: list[dict[str, Any]] = []
    queue = [(top, "")]
    problems: list[str] = []
    while queue:  # l'arbre des dossiers d'abord (léger), les contenus ensuite en parallèle
        folder, path = queue.pop(0)
        here = f"{path} / {folder['title']}".strip(" /") if folder["id"] != top["id"] else ""
        folders.append({**folder, "path": here})
        say(f"Dossiers : {len(folders)}", 0, 0)
        if folder.get("children", 1):
            try:
                children = client.folders(folder["id"])
            except Exception as error:  # noqa: BLE001
                problems.append(f"{here or folder['title']} (sous-dossiers) : {getattr(error, 'message', type(error).__name__)}")
                children = []
            queue.extend((child, here) for child in children)
    with_contents = [f for f in folders if f.get("contents", 1)]
    contents: list[dict[str, Any]] = []
    done = 0
    if workers > 1 and len(with_contents) > 1:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qvidian-sync") as pool:
            futures = {pool.submit(_folder_items, client, f, f["path"], problems): f for f in with_contents}
            for fut in as_completed(futures):
                contents.extend(fut.result())
                done += 1
                say(f"Dossier « {futures[fut]['path'] or futures[fut]['title']} » ({done}/{len(with_contents)})", len(contents), 0)
    else:
        for f in with_contents:
            contents.extend(_folder_items(client, f, f["path"], problems))
            done += 1
            say(f"Dossier « {f['path'] or f['title']} » ({done}/{len(with_contents)})", len(contents), 0)
    unique = {c["id"]: c for c in contents}  # un contenu vu dans deux dossiers (raccourci) n'est gardé qu'une fois
    contents = list(unique.values())
    say("Aperçus des textes vides", len(contents), 0)
    previews = _previews(client, contents, preview_limit, workers)
    snapshot.replace(folders, contents, source)
    seconds = round(time.time() - started, 1)
    snapshot.set_meta({"sync_mode": "full", "sync_seconds": seconds})
    say("Terminé", len(contents), len(contents))
    return {"mode": "full", "contents": len(contents), "folders": len(folders), "previews": previews, "problems": problems[:20],
            "seconds": seconds, "workers": workers}


def _delta(client, snapshot: Snapshot, source: str, say, preview_limit: int, workers: int, meta: dict[str, str],
           started: float) -> dict[str, Any]:
    since = (datetime.fromisoformat(meta["synced_at"]).date() - timedelta(days=1)).isoformat()
    say(f"Modifications depuis le {since}", 0, 0)
    changed = client.changed_since(since)
    known = {c["id"]: c for c in snapshot.many([c["id"] for c in changed])}
    folder_paths = {f["id"]: f["path"] for f in snapshot.folders()}
    for c in changed:
        c["folder_path"] = c.get("folder_path") or folder_paths.get(c.get("folder_id")) or known.get(c["id"], {}).get("folder_path", "")
    previews = _previews(client, changed, preview_limit, workers)
    if changed:
        snapshot.upsert(changed)
    say("Contrôle des suppressions", len(changed), 0)
    ids = snapshot.ids()
    removed: list[int] = []
    problems: list[str] = []
    if ids and hasattr(client, "existing_ids"):
        alive = client.existing_ids(ids)
        if alive or len(ids) < 5:
            removed = [i for i in ids if i not in alive]
            if removed:
                snapshot.remove(removed)
        else:
            problems.append("contrôle des suppressions ignoré : aucun identifiant reconnu (droits ?)")
    now = datetime.now().isoformat(timespec="seconds")
    seconds = round(time.time() - started, 1)
    snapshot.set_meta({"synced_at": now, "source": source, "sync_mode": "delta", "sync_seconds": seconds,
                       "count": len(snapshot.ids())})
    say("Terminé", len(changed), len(changed))
    return {"mode": "delta", "since": since, "contents": len(snapshot.ids()), "changed": len(changed), "removed": len(removed),
            "previews": previews, "problems": problems, "seconds": seconds, "workers": workers}


__all__ = ["Snapshot", "sync"]
