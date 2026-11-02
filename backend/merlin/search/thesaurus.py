"""Expansion de la question par le thésaurus métier (thesaurus.yaml) : une expression trouvée appelle ses équivalents."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .text import terms

THESAURUS = Path(__file__).with_name("thesaurus.yaml")


@lru_cache
def _groups() -> list[list[tuple[str, ...]]]:
    raw = yaml.safe_load(THESAURUS.read_text(encoding="utf-8"))["groups"]
    out = []
    for group in raw:
        phrases = [tuple(terms(str(p))) for p in group]
        out.append([p for p in phrases if p])
        for p, label in zip(phrases, group):
            if p:
                _LABELS.setdefault(p, str(label))
    return out


_LABELS: dict[tuple[str, ...], str] = {}  # expression analysée → libellé lisible (pour l'explication)


def _contains(seq: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return any(tuple(seq[i:i + n]) == phrase for i in range(len(seq) - n + 1))


def expand(query_terms: list[str], weight: float = 0.45, cap: int = 24) -> tuple[dict[str, float], list[str], list[tuple[tuple[str, ...], list[tuple[str, ...]]]]]:
    """Termes ajoutés {racine: poids}, expressions reconnues (pour l'explication) et équivalences
    [(expression de la question, autres expressions du groupe)] pour mesurer la couverture.

    Le poids d'un équivalent est réduit (0,45) : il aide à retrouver un texte, sans jamais dépasser les mots écrits."""
    added: dict[str, float] = {}
    matched: list[str] = []
    equivalents: list[tuple[tuple[str, ...], list[tuple[str, ...]]]] = []
    present = set(query_terms)
    for group in _groups():
        hits = [p for p in group if _contains(query_terms, p)]
        if not hits:
            continue
        hit = max(hits, key=len)
        others = [p for p in group if p not in hits][:2]
        matched.append(f"{_LABELS.get(hit, ' '.join(hit))} → {', '.join(_LABELS.get(o, ' '.join(o)) for o in others)}")
        equivalents.append((hit, [p for p in group if p not in hits]))
        for phrase in group:
            if phrase in hits:
                continue
            for t in phrase:
                if t not in present:
                    added[t] = max(added.get(t, 0.0), weight / max(1, len(phrase) - 1) ** 0.5)
            if len(phrase) >= 2:
                for a, b in zip(phrase, phrase[1:]):
                    added[f"{a}_{b}"] = max(added.get(f"{a}_{b}", 0.0), weight)
    top = dict(sorted(added.items(), key=lambda kv: -kv[1])[:cap])
    return top, matched, equivalents


__all__ = ["expand"]
