"""Texte des PDF, page par page, et version « à plat » (minuscules, sans accents) de MÊME longueur pour que les
positions trouvées dans le texte normalisé désignent le bon extrait du texte d'origine."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "’": "'", "‘": "'", " ": " ", " ": " ", "–": "-", "—": "-"}


def pages_text(path: Path) -> list[str]:
    from pypdf import PdfReader  # import local : la dépendance n'est nécessaire que pour les documents

    reader = PdfReader(str(path))
    out = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - une page illisible n'empêche pas les autres
            text = ""
        for a, b in LIGATURES.items():
            text = text.replace(a, b)
        out.append(re.sub(r"[ \t]+", " ", text))
    return out


def flat(text: str) -> str:
    """Minuscules sans accents, caractère pour caractère (même longueur que l'original)."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c)) or ch
        out.append(base[0].lower() if len(base) >= 1 else ch)
    return "".join(out)


def snippet(text: str, start: int, end: int, margin: int = 60) -> str:
    a, b = max(0, start - margin), min(len(text), end + margin)
    return ("…" if a else "") + re.sub(r"\s+", " ", text[a:b]).strip() + ("…" if b < len(text) else "")


def percent(raw: str) -> float | None:
    raw = raw.replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
