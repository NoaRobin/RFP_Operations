"""Apprentissage par l'historique : les questions des anciens RFI (SharePoint, projets Qvidian, lot 02) rapprochées
du texte Qvidian qui y avait été répondu.

Beaucoup de RFI sont complétés avec des réponses Qvidian : la réponse d'un ancien questionnaire est donc souvent un
contenu de la bibliothèque, à l'identique ou dans une version voisine. Pour chaque réponse rédigée d'un ancien RFI,
on cherche le contenu Qvidian correspondant (recherche lexicale sur les textes, puis contrôle par suites de mots) :
  - identique   : même texte après normalisation ;
  - version     : même texte dans une autre rédaction (similarité ≥ 0,55) ;
  - repris      : le texte Qvidian figure dans la réponse, complété (≥ 85 % de ses mots, 15 mots au moins).
Chaque lien garde sa provenance (fichier, date, fonds). La recherche Qvidian et le compléteur RFI s'en servent :
« cette question a reçu ce texte dans N anciens RFI ». Fichier local à côté de l'instantané, jamais committé.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..rfi.aggregate import similarity
from ..rfi.ontology import norm
from ..search.lexical import BM25F, Field, query_vector
from ..search.text import terms

MIN_ANSWER_CHARS = 40
VERSION = 0.55
CONTAINED = 0.85


@dataclass
class Link:
    content_id: int
    question: str
    mode: str  # identique | version | repris
    similarity: float
    file: str
    date: str = ""
    fund: str = ""
    origin: str = ""
    precedent_id: str = ""


def _containment(content_text: str, answer: str) -> float:
    c = set(terms(content_text))
    if len(c) < 15:
        return 0.0
    return len(c & set(terms(answer))) / len(c)


def build_links(contents: list[dict[str, Any]], precedents: list[Any]) -> list[Link]:
    """precedents : objets Precedent (ou équivalents : question, answer_text, source_file, ref_date, fund_name, origin, id)."""
    texts = [c for c in contents if len((c.get("text") or "").strip()) >= 20]
    if not texts:
        return []
    index = BM25F([{"text": c["text"]} for c in texts], fields=[Field("text", 1.0, 0.75)], bigram_weight=0.8)
    links: list[Link] = []
    for p in precedents:
        answer = (getattr(p, "answer_text", "") or "").strip()
        if len(answer) < MIN_ANSWER_CHARS or getattr(p, "blocked", False) or not (getattr(p, "question", "") or "").strip():
            continue
        q, _ = query_vector(answer[:1500])
        best: tuple[float, str, dict] | None = None
        for h in index.score(q, 5):
            c = texts[h.index]
            if norm(c["text"]) == norm(answer):
                cand = (1.0, "identique", c)
            else:
                sim = similarity(c["text"], answer)
                cont = _containment(c["text"], answer)
                if sim >= VERSION:
                    cand = (sim, "version", c)
                elif cont >= CONTAINED:
                    cand = (0.5 + 0.4 * cont, "repris", c)
                else:
                    continue
            if best is None or cand[0] > best[0]:
                best = cand
        if best is not None:
            links.append(Link(best[2]["id"], p.question.strip(), best[1], round(best[0], 3), getattr(p, "source_file", ""),
                              (getattr(p, "ref_date", "") or "")[:10], getattr(p, "fund_name", "") or "", getattr(p, "origin", ""),
                              getattr(p, "id", "")))
    return links


@dataclass
class _DemoPrecedent:
    id: str
    question: str
    answer_text: str
    source_file: str
    ref_date: str
    fund_name: str
    origin: str = "demo"
    blocked: bool = False


def demo_precedents(contents_by_id: dict[int, dict[str, Any]]) -> list[_DemoPrecedent]:
    from .demo_library import DEMO_HISTORY

    out = []
    for file, day, fund, rows in DEMO_HISTORY:
        for k, (question, cid) in enumerate(rows):
            if cid in contents_by_id:
                out.append(_DemoPrecedent(f"demo:{file}:{k}", question, contents_by_id[cid]["text"], file, day, fund))
    return out


class History:
    """Liens enregistrés et leur résumé par contenu."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"links": [], "built_at": None, "precedents": 0}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

    @property
    def links(self) -> list[Link]:
        return [Link(**x) for x in self.data.get("links", [])]

    def save(self, links: list[Link], precedents: int, signature: str) -> None:
        self.data = {"links": [asdict(x) for x in links], "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "precedents": precedents,
                     "signature": signature}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def by_content(self) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for link in self.links:
            e = out.setdefault(link.content_id, {"questions": [], "files": set(), "last": "", "examples": []})
            if norm(link.question) not in {norm(q) for q in e["questions"]}:
                e["questions"].append(link.question)
            e["files"].add(link.file)
            e["last"] = max(e["last"], link.date or "")
            e["examples"].append({"file": link.file, "date": link.date, "question": link.question, "mode": link.mode, "fund": link.fund})
        for e in out.values():
            e["files"] = len(e["files"])
            e["examples"].sort(key=lambda x: x["date"] or "", reverse=True)
            e["examples"] = e["examples"][:8]
        return out

    def summary(self) -> dict[str, Any]:
        links = self.links
        return {"built_at": self.data.get("built_at"), "precedents": self.data.get("precedents", 0), "links": len(links),
                "contents": len({x.content_id for x in links}), "files": len({x.file for x in links}),
                "questions": len({norm(x.question) for x in links}),
                "by_mode": {m: sum(1 for x in links if x.mode == m) for m in ("identique", "version", "repris")}}


__all__ = ["History", "Link", "build_links", "demo_precedents"]
