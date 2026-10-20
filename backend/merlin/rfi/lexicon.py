"""Questionnaires espagnols et italiens : détection de la langue et traduction pivot vers le français de l'ontologie.

La compréhension reste celle du français / anglais (concepts.yaml, facets.yaml) : une question es / it normalisée est
réécrite mot à mot en français avant l'analyse (ontology/lexicon.yaml). Une seule passe, expressions les plus longues
d'abord : un mot déjà traduit n'est jamais retraduit. Rien n'est deviné : un mot absent du lexique reste tel quel.
"""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from .ontology import ONTOLOGY_DIR, norm

# Mots propres à chaque langue (« la », « de », « gestion »… communs au français et à l'espagnol ne départagent rien)
FR = {"le", "les", "des", "du", "et", "est", "votre", "vos", "quel", "quelle", "quels", "quelles", "fonds", "part", "parts",
      "indiquer", "indiquez", "veuillez", "frais", "nom", "devise", "souscription", "rachat", "societe", "ou", "au", "aux"}
EN = {"the", "of", "and", "is", "your", "what", "which", "fund", "share", "please", "provide", "indicate", "class", "fee", "fees",
      "does", "has", "are", "name", "currency", "date", "subscription", "redemption", "management", "company", "if"}


@lru_cache
def _lexicon() -> dict:
    return yaml.safe_load((ONTOLOGY_DIR / "lexicon.yaml").read_text(encoding="utf-8"))


@lru_cache
def _compiled(lang: str) -> tuple[re.Pattern, dict[str, str]] | None:
    spec = _lexicon().get(lang)
    if not spec:
        return None
    mapping: dict[str, str] = {}
    for key, value in {**(spec.get("words") or {}), **(spec.get("phrases") or {})}.items():
        k = norm(key) + ("'" if str(key).endswith("'") else "")
        mapping[k] = str(value)
    alternatives = [re.escape(k) + ("" if k.endswith("'") else r"(?![a-z0-9])") for k in sorted(mapping, key=len, reverse=True)]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alternatives) + ")"), mapping


def markers(lang: str) -> set[str]:
    return set(map(str, (_lexicon().get(lang) or {}).get("markers") or []))


def language_scores(text: str) -> dict[str, int]:
    words = norm(text).replace("'", " ").split()
    sets = {"fr": FR, "en": EN, "es": markers("es"), "it": markers("it")}
    return {lang: sum(w in s for w in words) for lang, s in sets.items()}


def detect_language(text: str) -> str:
    """fr | en | es | it. En cas d'égalité : français (langue par défaut des questionnaires)."""
    scores = language_scores(text)
    best = max(scores.values())
    if best == 0:
        return "fr"
    for lang in ("fr", "en", "es", "it"):
        if scores[lang] == best:
            return lang
    return "fr"


def _coverage(text: str, lang: str) -> int:
    """Nombre de mots de la question connus du lexique de la langue (départage espagnol / italien)."""
    compiled = _compiled(lang)
    return len(compiled[0].findall(norm(text))) if compiled else 0


def question_language(text: str, document_language: str | None = None) -> str:
    """Langue d'une question : celle du document, sauf question nettement d'une autre langue (document mixte)."""
    scores = language_scores(text)
    local = max(("fr", "en"), key=lambda k: scores[k])
    foreign = max(("es", "it"), key=lambda k: (scores[k], _coverage(text, k)))
    if document_language in {"es", "it"}:
        other = "it" if document_language == "es" else "es"
        if scores[local] >= 2 and scores[local] > scores[document_language]:
            return local  # question française / anglaise dans un document espagnol / italien
        if scores[other] >= 2 and scores[other] > scores[document_language] and scores[other] > scores[local]:
            return other
        return document_language
    if scores[foreign] >= 2 and scores[foreign] > scores[local]:
        return foreign
    return document_language if document_language in {"fr", "en"} else ("en" if scores["en"] > scores["fr"] else "fr")


def to_pivot(text: str, lang: str) -> str:
    """Texte normalisé es / it → français normalisé (inchangé pour fr / en)."""
    if lang not in {"es", "it"}:
        return text
    compiled = _compiled(lang)
    if compiled is None:
        return text
    pattern, mapping = compiled
    return " ".join(pattern.sub(lambda m: mapping.get(m.group(0), m.group(0)), text).split())


__all__ = ["detect_language", "question_language", "to_pivot", "language_scores"]
