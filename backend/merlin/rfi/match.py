"""Rapprochement question → fait, par mots-clés FR/EN (aucune donnée ne quitte le poste, aucune IA externe)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .facts import Fact, norm

QUALITATIVE = re.compile(
    r"^(?:decrivez|decrire|expliquez|expliquer|presentez|presenter|detaillez|commentez|comment|pourquoi|"
    r"describe|explain|outline|discuss|elaborate|how do|how does|why|what is your view|please describe|please explain)\b"
)
SHARE_HINT = re.compile(r"\b(?:part|parts|share|shares|share class|classe|categorie de parts|isin)\b")
FUND_HINT = re.compile(r"\b(?:fonds|fund|opc|opcvm|sicav|fcp|compartiment|sub-fund)\b")


@lru_cache(maxsize=4096)
def _pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")


def _has(text: str, term: str) -> bool:
    if term == "%":
        return "%" in text
    return bool(_pattern(term).search(text))


@dataclass
class Match:
    fact: Fact
    score: float
    confidence: float
    reason: str


def match_question(text: str, facts: list[Fact]) -> list[Match]:
    q = norm(text)
    if not q:
        return []
    qualitative = bool(QUALITATIVE.match(q)) and len(q) > 80
    share_hint, fund_hint = bool(SHARE_HINT.search(q)), bool(FUND_HINT.search(q))
    matches: list[Match] = []
    for fact in facts:
        if fact.problems or any(_has(q, t) for t in fact.exclude):
            continue
        best, reason = 0.0, ""
        for group in fact.keywords:
            if group and all(_has(q, t) for t in group):
                score = sum(len(t) for t in group) + 4 * (len(group) - 1)
                if score > best:
                    best, reason = score, " + ".join(group)
        if not best:
            continue
        if fact.scope == "share" and share_hint:
            best += 3
        if fact.scope == "fund" and fund_hint and not share_hint:
            best += 2
        if qualitative:
            best *= 0.4
        # Les questions longues diluent les mots-clés : la confiance baisse avec la longueur.
        length_factor = 1.0 if len(q) < 60 else 0.85 if len(q) < 120 else 0.7 if len(q) < 250 else 0.5
        confidence = min(1.0, (best + 6) / 16) * length_factor
        matches.append(Match(fact, best, round(confidence, 2), reason))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:4]
