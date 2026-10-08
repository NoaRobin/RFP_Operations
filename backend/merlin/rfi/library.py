"""Bibliothèque de réponses validées (le « answer library » des outils de RFP).

Chaque génération validée par un humain enrichit la bibliothèque :
  - question → concept choisi (la correspondance sera reprise telle quelle, avec confiance maximale) ;
  - question → réponse libre saisie (pour ce fonds, ou pour tous les fonds si cochée « réutilisable ») ;
  - question → « ne pas remplir ».
Stockée dans data/rfi/library.json (poste local, jamais committée). Aucune donnée n'est inventée : une réponse
libre n'est reprise que si un humain l'a écrite.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .ontology import norm, tokens

_lock = threading.Lock()


@dataclass
class Entry:
    q: str  # question normalisée
    action: str  # concept | text | ignore
    concept: str | None = None
    text: str | None = None
    scope: str = "all"  # all | <pi_productid> | <isin>
    by: str = ""
    at: str = ""
    count: int = 1


class Library:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[Entry] = []
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.entries = [Entry(**e) for e in raw.get("entries", [])]
            except (ValueError, TypeError):
                self.entries = []

    def save(self) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"entries": [asdict(e) for e in self.entries]}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    @staticmethod
    def key(question: str) -> str:
        return norm(question)

    def lookup(self, question: str, scopes: list[str]) -> tuple[Entry | None, float]:
        """Meilleure entrée applicable : (entrée, similarité). Exacte = 1,0 ; quasi identique ≥ 0,9."""
        q = self.key(question)
        if not q:
            return None, 0.0
        allowed = set(scopes) | {"all"}
        best: tuple[Entry | None, float] = (None, 0.0)
        q_tokens = set(tokens(q))
        for e in self.entries:
            if e.scope not in allowed:
                continue
            if e.q == q:
                sim = 1.0
            else:
                other = set(tokens(e.q))
                if not other or not q_tokens:
                    continue
                sim = len(q_tokens & other) / len(q_tokens | other)
                if sim < 0.9:
                    continue
            # À similarité égale, l'entrée la plus spécifique (ce fonds / cette part) l'emporte
            rank = sim + (0.001 if e.scope != "all" else 0)
            if rank > best[1]:
                best = (e, sim)
        return best

    def remember(self, question: str, action: str, *, concept: str | None = None, text: str | None = None, scope: str = "all",
                 by: str = "") -> None:
        q = self.key(question)
        if not q:
            return
        now = datetime.now().isoformat(timespec="seconds")
        for e in self.entries:
            if e.q == q and e.scope == scope:
                e.action, e.concept, e.text, e.by, e.at = action, concept, text, by, now
                e.count += 1
                return
        self.entries.append(Entry(q=q, action=action, concept=concept, text=text, scope=scope, by=by, at=now))

    def stats(self) -> dict[str, Any]:
        out: dict[str, int] = {}
        for e in self.entries:
            out[e.action] = out.get(e.action, 0) + 1
        return {"total": len(self.entries), **out}


__all__ = ["Library", "Entry"]
