"""Agrégation des réponses candidates : la plus choisie, pondérée par la récence, texte à jour.

Chaque source qui propose une réponse est un « vote » : Fabric, DIC / prospectus, bibliothèque validée, anciens RFI,
contenus Qvidian (avec leur nombre d'utilisations), Copilot. Les textes proches (même réponse mise à jour, reformulée,
corrigée) forment une seule « famille » : ce sont les versions d'une même réponse.

Score d'une famille = Σ votes  poids(source) × poids(vote) × récence(date) × (1 + log2(utilisations)) × contrôle
  - récence(d) = 0,5 ^ (âge en jours / demi-vie) ; demi-vie 365 jours par défaut ; date inconnue → 0,35 ;
    les sources « actuelles » (Fabric, documents officiels, bibliothèque) ne vieillissent pas (récence 1) ;
  - contrôle : réponse vérifiée dans Fabric × 1,5, contredite × 0,3, réutilisation bloquée × 0,3.
Le texte retenu pour une famille est sa version la plus récente : on garde le choix des équipes, dans sa dernière
rédaction. La part (score / total) dit à quel point le choix est net.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

HALF_LIFE_DAYS = 365
UNKNOWN_DATE = 0.35
SOURCE_WEIGHT = {"fabric": 3.0, "kid": 2.5, "prospectus": 2.5, "document": 2.5, "library": 2.5, "mine": 3.0, "app": 1.5,
                 "copilot": 1.5, "qvidian": 1.0, "precedent": 1.0, "alternative": 0.3}
TIMELESS = {"fabric", "kid", "prospectus", "document", "library", "app", "mine", "alternative"}
CHECK_FACTOR = {"match": 1.5, "mismatch": 0.3}
SHORT = 60  # en dessous : deux réponses sont les mêmes seulement si elles sont identiques (chiffres, oui / non…)


@dataclass
class Vote:
    text: str
    kind: str
    label: str = ""
    weight: float = 1.0  # similarité de la question, confiance…
    when: date | None = None
    uses: int = 1
    url: str = ""
    check: str | None = None
    blocked: bool = False
    ref: str = ""

    def public(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label, "url": self.url, "check": self.check, "blocked": self.blocked,
                "date": self.when.isoformat() if self.when else None, "uses": self.uses, "ref": self.ref}


@dataclass
class Choice:
    value: str
    score: float
    share: float = 0.0
    votes: list[Vote] = field(default_factory=list)
    versions: int = 1

    @property
    def latest(self) -> date | None:
        dates = [v.when for v in self.votes if v.when]
        return max(dates) if dates else None

    @property
    def uses(self) -> int:
        return sum(max(v.uses, 1) for v in self.votes)

    def why(self) -> str:
        kinds: dict[str, int] = {}
        for v in self.votes:
            kinds[v.kind] = kinds.get(v.kind, 0) + 1
        parts = [f"{n} {KIND_LABEL.get(k, k)}" for k, n in sorted(kinds.items(), key=lambda kv: -SOURCE_WEIGHT.get(kv[0], 1))]
        q_uses = sum(v.uses for v in self.votes if v.kind == "qvidian")
        if q_uses:
            parts.append(f"utilisée {q_uses} fois dans Qvidian")
        if self.latest:
            parts.append(f"la plus récente le {self.latest.strftime('%d/%m/%Y')}")
        if self.versions > 1:
            parts.append(f"{self.versions} versions du texte, la dernière est proposée")
        return " · ".join(parts)

    def public(self) -> dict[str, Any]:
        return {"value": self.value, "score": round(self.score, 3), "share": round(self.share, 3), "versions": self.versions,
                "latest": self.latest.isoformat() if self.latest else None, "uses": self.uses, "why": self.why(),
                "sources": [v.public() for v in sorted(self.votes, key=lambda v: -SOURCE_WEIGHT.get(v.kind, 1))]}


KIND_LABEL = {"fabric": "Fabric", "kid": "DIC", "prospectus": "prospectus", "document": "document officiel", "library": "réponse validée",
              "mine": "saisie", "app": "proposition de l'app", "copilot": "Copilot", "qvidian": "Qvidian", "precedent": "ancien(s) RFI",
              "alternative": "autre donnée"}


_ACCENTS = re.compile(r"[\u0300-\u036f]")


@lru_cache(maxsize=50_000)
def norm(text: str) -> str:
    """Texte comparable (sans accents, minuscules, ponctuation réduite) ; mémorisé : les mêmes textes reviennent sans cesse."""
    text = _ACCENTS.sub("", unicodedata.normalize("NFKD", text or "")).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w%€$.,/-]+", " ", text)).strip(" .;:")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(text))


@lru_cache(maxsize=20_000)
def _shingles(text: str, n: int) -> frozenset[str]:
    words = _words(text)
    if len(words) < n:
        return frozenset({" ".join(words)} if words else set())
    return frozenset(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))


def shingles(text: str, n: int = 3) -> set[str]:
    return set(_shingles(text or "", n))


def similarity(a: str, b: str) -> float:
    """0..1 : identiques après normalisation = 1 ; textes longs = recouvrement de suites de mots (versions d'un texte)."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return 1.0
    if min(len(na), len(nb)) <= SHORT:
        return 0.0
    sa, sb = _shingles(a, 3), _shingles(b, 3)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return max(inter / len(sa | sb), inter / min(len(sa), len(sb)) * 0.9)


def same_family(a: str, b: str) -> bool:
    return similarity(a, b) >= 0.5


def recency(when: date | None, today: date, half_life: int = HALF_LIFE_DAYS) -> float:
    if when is None:
        return UNKNOWN_DATE
    if isinstance(when, datetime):
        when = when.date()
    age = max((today - when).days, 0)
    return max(0.5 ** (age / max(half_life, 1)), 0.02)


def vote_score(v: Vote, today: date, half_life: int = HALF_LIFE_DAYS) -> float:
    r = 1.0 if v.kind in TIMELESS else recency(v.when, today, half_life)
    s = SOURCE_WEIGHT.get(v.kind, 1.0) * max(v.weight, 0.0) * r * (1 + math.log2(max(v.uses, 1)))
    s *= CHECK_FACTOR.get(v.check or "", 1.0)
    return s * (0.3 if v.blocked else 1.0)


def aggregate(votes: Iterable[Vote], today: date | None = None, half_life: int = HALF_LIFE_DAYS) -> list[Choice]:
    today = today or date.today()
    families: list[list[Vote]] = []
    for v in votes:
        if not (v.text or "").strip() or v.text.strip() == "—":
            continue
        for fam in families:
            if any(same_family(v.text, other.text) for other in fam[:5]):
                fam.append(v)
                break
        else:
            families.append([v])
    choices = []
    for fam in families:
        score = sum(vote_score(v, today, half_life) for v in fam)
        # Texte à jour : la version la plus récente ; à date égale (ou inconnue), celle de la source la plus fiable
        best = max(fam, key=lambda v: ((v.when or date.min), vote_score(v, today, half_life)))
        versions = len({norm(v.text) for v in fam})
        choices.append(Choice(best.text.strip(), score, votes=fam, versions=versions))
    total = sum(c.score for c in choices) or 1.0
    for c in choices:
        c.share = c.score / total
    return sorted(choices, key=lambda c: -c.score)


def to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


__all__ = ["Vote", "Choice", "aggregate", "similarity", "same_family", "recency", "vote_score", "norm", "to_date", "HALF_LIFE_DAYS"]
