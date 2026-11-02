"""Portée (société / stratégie / fonds / part), thème et fonds cité, pour un contenu Qvidian ou une question.

Déterministe et explicable : chaque décision garde ses indices (« dossier Fonds / Fonds Imaginaire Horizon », « ISIN
QZ… dans le texte »). Les noms de fonds viennent des dossiers de fonds de la bibliothèque et du répertoire Product Info ;
un fonds n'est jamais deviné à partir d'un mot isolé commun à plusieurs fonds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..search.text import fold

LEVELS = Path(__file__).with_name("levels.yaml")
ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
SCOPES = ("societe", "strategie", "fonds", "part")
SCOPE_LABELS = {"societe": "Société", "strategie": "Stratégie", "fonds": "Fonds", "part": "Part", "generique": "Générique"}
THEME_LABELS = {"presentation": "Présentation", "gouvernance": "Gouvernance", "equipe": "Équipe", "gestion": "Gestion",
                "risques": "Risques", "esg": "ESG", "operations": "Opérations", "conformite": "Conformité",
                "continuite": "Continuité & sécurité", "performance": "Performance", "frais": "Frais", "juridique": "Juridique",
                "reporting": "Reporting"}
GENERIC_FUND_WORDS = {"fonds", "fund", "funds", "sicav", "fcp", "opcvm", "ucits", "actions", "equity", "obligations", "bonds",
                      "europe", "euro", "monde", "world", "global", "international", "credit", "part", "classe", "the", "de", "des",
                      "du", "la", "le", "les", "et", "and", "isr", "esg", "sri", "flexible", "patrimoine", "croissance", "income"}


def _n(text: Any) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9']+", fold(str(text or "")).replace("’", "'"))) + " "


@lru_cache
def _config() -> dict[str, Any]:
    return yaml.safe_load(LEVELS.read_text(encoding="utf-8"))


def _hits(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if f" {p} " in text]


@dataclass
class Level:
    scope: str = "generique"
    confidence: float = 0.0
    funds: list[str] = field(default_factory=list)
    isins: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    clues: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {"scope": self.scope, "scope_label": SCOPE_LABELS[self.scope], "confidence": round(self.confidence, 2),
                "funds": self.funds, "isins": self.isins, "themes": self.themes,
                "theme_labels": [THEME_LABELS.get(t, t) for t in self.themes], "clues": self.clues[:6]}


class FundNames:
    """Noms de fonds connus et leurs alias distinctifs (mot propre à un seul fonds : « Horizon », « Aurore »)."""

    def __init__(self, names: list[str]):
        clean = sorted({re.sub(r"\s+", " ", n).strip() for n in names if n and len(n.strip()) >= 4})
        self.names = clean
        token_owners: dict[str, set[str]] = {}
        for n in clean:
            for t in set(_n(n).split()):
                token_owners.setdefault(t, set()).add(n)
        self.aliases: dict[str, list[str]] = {}
        for n in clean:
            alias = [_n(n).strip()]
            for t in _n(n).split():
                if len(t) >= 4 and t not in GENERIC_FUND_WORDS and len(token_owners.get(t, ())) == 1:
                    alias.append(t)
            self.aliases[n] = alias

    def find(self, text: str) -> list[str]:
        t = _n(text)
        out = []
        for name, aliases in self.aliases.items():
            if any(f" {a} " in t for a in aliases):
                out.append(name)
        return out


def fund_folders(folder_paths: list[str]) -> list[str]:
    """Dossiers de fonds : sous-dossiers directs d'un dossier « Fonds / Funds / OPC / Produits »."""
    roots = set(_config()["folders"]["fonds"])
    out = set()
    for path in folder_paths:
        parts = [p.strip() for p in (path or "").split(" / ") if p.strip()]
        for i, p in enumerate(parts[:-1]):
            if _n(p).strip() in roots:
                out.add(parts[i + 1])
    return sorted(out)


def classify(title: str, text: str, folder_path: str = "", funds: FundNames | None = None, question: str = "") -> Level:
    cfg = _config()
    head = _n(f"{title} {question}")
    body = _n((text or "")[:3000])
    folder = _n(folder_path.replace("/", " "))
    level = Level()
    score = {s: 0.0 for s in SCOPES}

    # Fonds cités (dossier d'abord, puis titre, puis texte) — jamais deviné
    if funds is not None:
        in_folder, in_head, in_body = funds.find(folder_path), funds.find(f"{title} {question}"), funds.find((text or "")[:3000])
        named = list(dict.fromkeys(in_folder + in_head + in_body))
        if named:
            level.funds = named[:3]
            score["fonds"] += 4.0 * bool(in_folder) + 3.0 * bool(in_head) + 1.5 * bool(in_body)
            level.clues.append(f"fonds cité : {', '.join(named[:3])}" + (" (dossier)" if in_folder else ""))
    level.isins = list(dict.fromkeys(ISIN.findall(f"{title} {question} {text or ''}")))[:5]
    if level.isins:
        score["part"] += 2.5
        level.clues.append(f"ISIN {level.isins[0]}")

    for scope, phrases in cfg["scopes"].items():
        h = _hits(head, phrases)
        b = _hits(body, phrases)
        if h or b:
            score[scope] += 2.0 * len(h) + 0.6 * min(len(b), 4)
            level.clues.extend(f"« {p} »" for p in (h or b)[:2])
    for scope, words in cfg["folders"].items():
        segs = [_n(p).strip() for p in folder_path.split(" / ")]
        if any(seg in words or any(f" {w} " in f" {seg} " for w in words) for seg in segs if seg):
            score[scope] += 3.0
            level.clues.append(f"dossier « {folder_path} »")
    if level.funds and _hits(head, cfg["scopes"]["part"]):
        score["part"] += 4.0  # la question vise une part précise d'un fonds nommé (« part I du fonds X »)
    elif level.funds and level.isins:
        score["part"] += 1.0  # ISIN cité dans le texte d'une réponse sur le fonds : la portée reste en général le fonds
    if level.funds:
        score["societe"] *= 0.5  # « la société de gestion du fonds X » reste une réponse sur le fonds
        score["strategie"] *= 0.6
    best = max(score, key=lambda s: score[s])
    if score[best] > 0:
        ordered = sorted(score.values(), reverse=True)
        level.scope = best
        level.confidence = (ordered[0] - ordered[1]) / (ordered[0] + 1.0)
    if level.scope == "fonds" and not level.funds:
        level.scope = "strategie" if score["strategie"] else "generique"

    theme_score: dict[str, float] = {}
    for theme, phrases in cfg["themes"].items():
        s = 3.0 * len(_hits(folder, phrases)) + 2.0 * len(_hits(head, phrases)) + 0.5 * min(len(_hits(body, phrases)), 6)
        if s:
            theme_score[theme] = s
    level.themes = [t for t, _ in sorted(theme_score.items(), key=lambda kv: -kv[1])[:2]]
    return level


def query_level(question: str, funds: FundNames | None = None) -> Level:
    """Même lecture pour une question : sert à préférer les réponses de même portée et du même fonds."""
    return classify(question, "", "", funds)


__all__ = ["Level", "FundNames", "classify", "query_level", "fund_folders", "SCOPES", "SCOPE_LABELS", "THEME_LABELS"]
