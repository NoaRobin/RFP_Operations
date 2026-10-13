"""Lecture d'un DIC PRIIPs (FR / EN). Gabarit réglementé : expressions régulières, page et extrait pour chaque fait.

Valeurs en points de pourcentage (1,35 = 1,35 %), convention Product Info. Un champ non trouvé n'est pas un zéro :
« aucun coût de sortie » explicite donne 0, un silence ne donne rien.
"""
from __future__ import annotations

import re
from datetime import date

from ..values import to_date
from .model import DocumentRef, Fact
from .text import flat, percent, snippet

ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
PCT = r"(-?\d{1,2}(?:[.,]\d{1,4})?)\s*%"
MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
          "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
          "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}

# (champ, motifs de libellé, fenêtre de recherche de la valeur, motif « zéro explicite »)
COST_FIELDS = [
    ("kid.entry_costs", r"couts d'entree|entry costs", r"(?:pas de|aucun|ne facturons pas de|no|do not charge an?) (?:couts? d'entree|frais d'entree|entry (?:costs?|fees?))"),
    ("kid.exit_costs", r"couts de sortie|exit costs", r"(?:pas de|aucun|ne facturons pas de|no|do not charge an?) (?:couts? de sortie|frais de sortie|exit (?:costs?|fees?))"),
    ("kid.ongoing_costs", r"frais de gestion et autres (?:frais|couts) administratifs (?:et|ou) d'exploitation|management fees and other administrative or operating costs", None),
    ("kid.transaction_costs", r"couts de transaction|transaction costs", None),
    ("kid.performance_fee", r"commissions? liees? aux resultats|commissions? de (?:sur)?performance|performance fees?", r"(?:aucune|pas de|no) (?:commission|performance fee)"),
]


def _date(text: str) -> date | None:
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})(?:er)? (" + "|".join(MONTHS) + r") (\d{4})", text)
    if m:
        return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"(" + "|".join(MONTHS) + r") (\d{1,2}),? (\d{4})", text)
    if m:
        return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return to_date(text)


def extract(pages: list[str], doc: DocumentRef, expected_isin: str | None) -> tuple[dict[str, Fact], list[str]]:
    facts: dict[str, Fact] = {}
    problems: list[str] = []
    full = "\n".join(pages)
    isins = list(dict.fromkeys(ISIN.findall(full)))
    if expected_isin:
        if expected_isin.upper() not in isins:
            problems.append(f"ISIN {expected_isin} absent du document ({', '.join(isins[:3]) or 'aucun ISIN'}) : DIC non utilisé")
            return {}, problems
    elif len(isins) != 1:
        problems.append("ISIN du DIC non identifiable : document non utilisé")
        return {}, problems

    def add(name: str, value, page_no: int, text: str, start: int, end: int) -> None:
        if name not in facts and value is not None:
            facts[name] = Fact(name, value, page_no, snippet(text, start, end), doc)

    for page_no, text in enumerate(pages, start=1):
        f = flat(text)
        # Date du document
        m = re.search(r"(?:exactes? et a jour au|a jour au|valables? au|est exact au|date de production|accurate (?:as at|as of)|"
                      r"valid as at|date of production|en date du|dated)\s*:?\s*([0-9a-z /.,]{6,24})", f)
        if m and "kid.date" not in facts:
            d = _date(m.group(1))
            if d:
                add("kid.date", d.isoformat(), page_no, text, m.start(), m.end())
        # Indicateur de risque (SRI 1–7)
        for pattern in (r"classe de risque\s*(?:de\s*)?([1-7])\b", r"(?:risk class|category)\s*([1-7])\s*(?:out of|sur|/)\s*7",
                        r"\b([1-7])\s*(?:sur|out of)\s*7\b", r"risk class\s*([1-7])\b"):
            m = re.search(pattern, f)
            if m:
                add("kid.sri", int(m.group(1)), page_no, text, m.start(), m.end())
                break
        # Période de détention recommandée
        m = re.search(r"(?:periode|duree) de detention recommandee\s*:?\s*(?:de\s*)?(\d{1,2})\s*(ans?|annees?|mois)|"
                      r"recommended holding period\s*:?\s*(?:of\s*)?(\d{1,2})\s*(years?|months?)", f)
        if m:
            n = int(m.group(1) or m.group(3))
            unit = (m.group(2) or m.group(4) or "")
            months = unit.startswith(("mois", "month"))
            add("kid.rhp", f"{n} mois" if months else f"{n} an{'s' if n > 1 else ''}", page_no, text, m.start(), m.end())
        # Coûts
        for name, label, zero in COST_FIELDS:
            if name in facts:
                continue
            for m in re.finditer(label, f):
                window = f[m.end(): m.end() + 220]
                if zero and re.search(zero, f[max(0, m.start() - 80): m.end() + 160]):
                    add(name, 0.0, page_no, text, m.start(), m.end() + 60)
                    break
                v = re.search(PCT, window)
                if v and percent(v.group(1)) is not None:
                    add(name, percent(v.group(1)), page_no, text, m.start(), m.end() + v.end())
                    break
        # Objectif (texte : seulement pour un « à vérifier »)
        m = re.search(r"\bobjectifs?\s*:?\s+", f)
        if m and "kid.objective" not in facts and page_no <= 2:
            body = text[m.end(): m.end() + 700]
            cut = re.search(r"\n\s*(?:investisseurs de detail|investisseurs vises|intended retail|retail investor)", flat(body))
            add("kid.objective", re.sub(r"\s+", " ", body[: cut.start() if cut else 500]).strip(), page_no, text, m.start(), m.end())
    if "kid.date" in facts:
        doc.doc_date = facts["kid.date"].value
    if not facts:
        problems.append("aucune donnée lue dans ce DIC (gabarit non reconnu)")
    return facts, problems
