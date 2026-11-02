"""Forme des réponses : consensus des anciens RFI du MÊME questionnaire.

Un client renvoie souvent le même questionnaire d'une année sur l'autre (ou à plusieurs fonds) : ses anciennes
versions répondues disent comment il attend la réponse — « Yes » ou « Oui », « 1.35% » ou « 1,35 % », « 31/12/2025 »
ou « 2025-12-31 », majuscules… et, pour une question rédigée, le texte déjà donné.

1. Questionnaires de même format : anciens RFI (précédents) dont les questions recoupent celles du document
   (au moins 3 questions identiques et 30 % du document).
2. Pour chaque case : les réponses données à la même question dans ces fichiers.
3. Consensus de forme (au moins 2 réponses, 60 % d'accord) appliqué au rendu de la valeur Fabric : le fond vient
   toujours de la donnée, seule la forme est reprise ; la raison est affichée (« forme de 3 anciens RFI sur 4 »).
4. Réponse rédigée identique dans au moins deux anciens RFI de ce questionnaire : proposée « à vérifier » quand
   rien d'autre ne répond (jamais écrite d'office).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .ontology import norm

PERCENT = re.compile(r"^\s*(?P<num>-?\d+(?:[.,]\d+)?)(?P<space>\s*)%\s*$")
DATES = [
    ("dd/mm/yyyy", re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%d/%m/%Y"),
    ("dd.mm.yyyy", re.compile(r"^\d{2}\.\d{2}\.\d{4}$"), "%d.%m.%Y"),
    ("yyyy-mm-dd", re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    ("dd-mm-yyyy", re.compile(r"^\d{2}-\d{2}-\d{4}$"), "%d-%m-%Y"),
]
YES = {"oui", "yes", "y", "o", "si", "ja"}
NO = {"non", "no", "n", "nein"}
MIN_SHARED, MIN_OVERLAP = 3, 0.3
MIN_SUPPORT, MIN_AGREEMENT = 2, 0.6


@dataclass
class Source:
    file: str
    shared: int
    overlap: float
    date: str = ""


@dataclass
class FormSpec:
    kind: str  # bool | percent | date | upper | text
    style: dict[str, Any]
    support: int
    total: int
    examples: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def reason(self) -> str:
        ex = " · ".join(f"« {e} »" for e in self.examples[:2])
        return f"forme reprise de {self.support} ancien{'s' if self.support > 1 else ''} RFI de ce questionnaire sur {self.total} ({ex})"


def _case(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return "upper"
    if letters and all(c.islower() for c in letters):
        return "lower"
    return "title"


def features(text: str) -> tuple[str, dict[str, Any]] | None:
    t = str(text or "").strip()
    if not t:
        return None
    n = norm(t)
    if n in YES or n in NO:
        lang = "fr" if n in {"oui", "non", "o"} else "en"
        return "bool", {"lang": lang, "case": _case(t), "short": len(t) == 1}
    m = PERCENT.match(t)
    if m:
        num = m.group("num")
        sep = "," if "," in num else ("." if "." in num else None)
        decimals = len(num.split(sep)[1]) if sep else 0
        return "percent", {"sep": sep, "decimals": decimals, "space": bool(m.group("space"))}
    for name, regex, _ in DATES:
        if regex.match(t):
            return "date", {"format": name}
    if len(t) <= 40 and any(c.isalpha() for c in t) and _case(t) == "upper" and len(t) > 3:
        return "upper", {}
    if len(t) > 60:
        return "text", {"words": len(t.split())}
    return None


def consensus(answers: list[tuple[str, str]]) -> FormSpec | None:
    """answers : [(texte, fichier)] — même question, anciens RFI de ce questionnaire."""
    feats = [(features(a), a, f) for a, f in answers]
    feats = [(k, a, f) for k, a, f in feats if k is not None]
    if len(feats) < MIN_SUPPORT:
        return None
    kinds = Counter(k[0] for k, _, _ in feats)
    kind, n = kinds.most_common(1)[0]
    if n < MIN_SUPPORT or n / len(feats) < MIN_AGREEMENT:
        return None
    same = [(k, a, f) for k, a, f in feats if k[0] == kind]
    if kind == "text":
        words = sorted(k[1]["words"] for k, _, _ in same)
        return FormSpec("text", {"words": words[len(words) // 2]}, n, len(feats), [a[:60] for _, a, _ in same[:2]], [f for _, _, f in same])
    styles = Counter(tuple(sorted(k[1].items())) for k, _, _ in same)
    style, m = styles.most_common(1)[0]
    if m < MIN_SUPPORT or m / len(feats) < MIN_AGREEMENT:
        return None
    examples = [a for k, a, _ in same if tuple(sorted(k[1].items())) == style]
    return FormSpec(kind, dict(style), m, len(feats), examples[:3], [f for k, _, f in same if tuple(sorted(k[1].items())) == style])


def _bool_label(yes: bool, style: dict[str, Any]) -> str:
    if style.get("short"):
        word = ("O" if yes else "N") if style["lang"] == "fr" else ("Y" if yes else "N")
    else:
        word = ("oui" if yes else "non") if style["lang"] == "fr" else ("yes" if yes else "no")
    return word.upper() if style["case"] == "upper" else word.lower() if style["case"] == "lower" else word.capitalize()


def apply(spec: FormSpec, answer: Any, value: Any) -> tuple[str, Any] | None:
    """(nouvelle réponse, nouvelle valeur écrite) dans la forme du consensus, ou None si elle ne s'applique pas."""
    if not isinstance(answer, str):
        return None
    text = answer.strip()
    if spec.kind == "bool":
        n = norm(text)
        if n not in YES and n not in NO:
            return None
        out = _bool_label(n in YES, spec.style)
        return (out, out) if out != text else None
    if spec.kind == "percent":
        m = re.match(r"^\s*(-?\d+(?:[  .,]\d+)*)\s*%\s*$", text)
        if not m or isinstance(value, (int, float)):
            return None  # cellule au format % : la valeur numérique est écrite, Excel affiche la forme
        number = float(m.group(1).replace(" ", "").replace(" ", "").replace(",", "."))
        out = f"{number:.{spec.style['decimals']}f}"
        if spec.style.get("sep") == ",":
            out = out.replace(".", ",")
        out += (" %" if spec.style.get("space") else "%")
        return (out, out) if out != text else None
    if spec.kind == "date":
        d = value if isinstance(value, (date, datetime)) else None
        if d is None:
            try:
                d = datetime.strptime(text, "%d/%m/%Y")
            except ValueError:
                return None
        if isinstance(value, (date, datetime)):
            return None  # cellule date : Excel affiche selon son format
        fmt = next(f for name, _, f in DATES if name == spec.style["format"])
        out = d.strftime(fmt)
        return (out, out) if out != text else None
    if spec.kind == "upper":
        if len(text) > 40 or text.upper() == text:
            return None
        return text.upper(), text.upper()
    return None


class FormModel:
    """Anciens RFI de même format que le document, et leurs réponses question par question."""

    def __init__(self, precedents: list[Any], questions: list[str]):
        doc = {norm(q) for q in questions if q and q.strip()}
        by_file: dict[str, list[Any]] = {}
        for p in precedents:
            if p.kind in {"answer", "checkbox"} and not p.blocked and (p.answer_text or "").strip():
                by_file.setdefault(p.source_file, []).append(p)
        self.sources: list[Source] = []
        self.answers: dict[str, list[tuple[str, str, str]]] = {}
        for file, items in by_file.items():
            qs = {norm(p.question) for p in items}
            shared = len(doc & qs)
            overlap = shared / max(1, min(len(doc), 60))
            if shared >= MIN_SHARED and overlap >= MIN_OVERLAP:
                self.sources.append(Source(file, shared, round(overlap, 2), max((p.ref_date or "")[:10] for p in items)))
                for p in items:
                    key = norm(p.question)
                    if key in doc:
                        self.answers.setdefault(key, []).append((p.answer_text, file, (p.ref_date or "")[:10]))
        self.sources.sort(key=lambda s: (-s.overlap, s.file))

    def spec(self, question: str) -> FormSpec | None:
        return consensus([(a, f) for a, f, _ in self.answers.get(norm(question), [])])

    def standard_text(self, question: str) -> tuple[str, list[tuple[str, str]]] | None:
        """Réponse rédigée identique dans au moins deux anciens RFI de ce questionnaire (la plus récente rédaction)."""
        rows = [(a, f, d) for a, f, d in self.answers.get(norm(question), []) if len(a) > 60]
        if len(rows) < 2:
            return None
        counts = Counter(norm(a) for a, _, _ in rows)
        key, n = counts.most_common(1)[0]
        if n < 2:
            return None
        same = sorted([r for r in rows if norm(r[0]) == key], key=lambda r: r[2], reverse=True)
        return same[0][0], [(f, d) for _, f, d in same]

    def public(self) -> list[dict[str, Any]]:
        return [{"file": s.file, "shared": s.shared, "overlap": s.overlap, "date": s.date} for s in self.sources[:10]]


__all__ = ["FormModel", "FormSpec", "consensus", "features", "apply"]
