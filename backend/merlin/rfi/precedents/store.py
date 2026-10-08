"""Stockage local des précédents : SQLite + index plein texte FTS5 (BM25). Vit dans data/rfi/, jamais committé."""
from __future__ import annotations

import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Iterable

from ..ontology import norm
from .model import Precedent

COLUMNS = ["id", "origin", "source_file", "question", "answer_raw", "kind", "source_ref", "source_url", "sheet", "question_cell",
           "answer_cell", "number_format", "comments", "shape", "extraction", "mapping_status", "fund_name", "isin",
           "share_name", "ref_date", "blocked", "block_reason", "review_required", "auto_copy_allowed"]
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS precedents ({", ".join(c + (" TEXT PRIMARY KEY" if c == "id" else "") for c in COLUMNS)}, question_norm TEXT);
CREATE INDEX IF NOT EXISTS ix_prec_isin ON precedents(isin);
CREATE INDEX IF NOT EXISTS ix_prec_file ON precedents(source_file);
CREATE VIRTUAL TABLE IF NOT EXISTS precedents_fts USING fts5(id UNINDEXED, question_norm, tokenize = "unicode61 remove_diacritics 2");
CREATE TABLE IF NOT EXISTS sources (source_file TEXT PRIMARY KEY, origin TEXT, url TEXT, imported_at TEXT, entries INTEGER,
    identity_problem TEXT);
"""


class PrecedentStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self.version = 0  # incrémentée à chaque écriture (invalide les index de similarité en mémoire)

    # ------------------------------------------------------------------ écriture
    def replace_source(self, source_file: str, origin: str, items: Iterable[Precedent], url: str = "", identity_problem: str = "",
                       imported_at: str = "") -> int:
        """Remplace tous les précédents d'un fichier source (réimport idempotent)."""
        items = list(items)
        with self._lock, self._conn:
            ids = [r[0] for r in self._conn.execute("SELECT id FROM precedents WHERE source_file = ?", (source_file,))]
            self._conn.executemany("DELETE FROM precedents_fts WHERE id = ?", [(i,) for i in ids])
            self._conn.execute("DELETE FROM precedents WHERE source_file = ?", (source_file,))
            placeholders = ", ".join("?" for _ in range(len(COLUMNS) + 1))
            rows = []
            for p in items:
                row = p.to_row()
                rows.append(tuple(row[c] for c in COLUMNS) + (norm(p.question),))
            self._conn.executemany(f"INSERT OR REPLACE INTO precedents ({', '.join(COLUMNS)}, question_norm) VALUES ({placeholders})", rows)
            self._conn.executemany("INSERT INTO precedents_fts (id, question_norm) VALUES (?, ?)", [(p.id, norm(p.question)) for p in items])
            self._conn.execute("INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                               (source_file, origin, url, imported_at, len(items), identity_problem))
        self.version += 1
        return len(items)

    def clear_origin(self, origin: str) -> None:
        with self._lock, self._conn:
            ids = [r[0] for r in self._conn.execute("SELECT id FROM precedents WHERE origin = ?", (origin,))]
            self._conn.executemany("DELETE FROM precedents_fts WHERE id = ?", [(i,) for i in ids])
            self._conn.execute("DELETE FROM precedents WHERE origin = ?", (origin,))
            self._conn.execute("DELETE FROM sources WHERE origin = ?", (origin,))
        self.version += 1

    # ------------------------------------------------------------------ lecture
    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM precedents").fetchone()[0])

    def get(self, ids: list[str]) -> list[Precedent]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = {r["id"]: dict(r) for r in self._conn.execute(f"SELECT * FROM precedents WHERE id IN ({marks})", ids)}
        return [Precedent.from_row(rows[i]) for i in ids if i in rows]

    def all(self) -> list[Precedent]:
        return [Precedent.from_row(dict(r)) for r in self._conn.execute("SELECT * FROM precedents")]

    def questions(self) -> list[tuple[str, str]]:
        """(id, question normalisée) pour l'index de similarité."""
        return [(r[0], r[1]) for r in self._conn.execute("SELECT id, question_norm FROM precedents")]

    def bm25(self, text: str, limit: int = 80) -> list[tuple[str, float]]:
        """Candidats plein texte (BM25). Les mots sont mis entre guillemets : aucune syntaxe FTS injectable."""
        words = [w for w in dict.fromkeys(norm(text).replace("'", " ").split()) if len(w) > 2 and w.isalnum()]
        if not words:
            return []
        query = " OR ".join(f'"{w}"' for w in words[:40])
        try:
            rows = self._conn.execute("SELECT id, bm25(precedents_fts) AS s FROM precedents_fts WHERE precedents_fts MATCH ? "
                                      "ORDER BY s LIMIT ?", (query, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(r[0], -float(r[1])) for r in rows]

    def sources(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM sources ORDER BY imported_at DESC")]

    def stats(self) -> dict:
        rows = [dict(r) for r in self._conn.execute("SELECT origin, kind, shape, blocked, answer_raw FROM precedents")]
        return {"total": len(rows), "by_origin": dict(Counter(r["origin"] for r in rows)), "by_kind": dict(Counter(r["kind"] for r in rows)),
                "by_shape": dict(Counter(r["shape"] or "?" for r in rows)), "blocked": sum(1 for r in rows if r["blocked"]),
                "sources": len(self.sources())}
