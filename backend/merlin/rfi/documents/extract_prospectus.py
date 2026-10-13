"""Lecture ciblée d'un prospectus : modalités et frais du compartiment demandé.

Un prospectus de SICAV couvre souvent plusieurs compartiments : on ne lit que la section du fonds demandé (repérée par
son nom ou l'ISIN de la part) ; si elle est introuvable, rien n'est lu. Les faits de prospectus ne sont jamais
écrits seuls en automatique : ils confirment Fabric, ou sont proposés « à vérifier ».
"""
from __future__ import annotations

import re

from ..ontology import norm
from .model import DocumentRef, Fact
from .text import flat, percent, snippet

ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")


def _section(full: str, isin: str | None, fund_name: str, other_names: list[str]) -> tuple[int, int] | None:
    """Bornes de la section du fonds dans le texte « à plat »."""
    f = flat(full)
    distinct = set(ISIN.findall(full))
    if len(distinct) <= 8:  # un seul fonds (et ses parts)
        return 0, len(full)
    name = flat(fund_name or "").strip()
    starts = [m.start() for m in re.finditer(re.escape(name), f)] if len(name) >= 6 else []
    if not starts and isin:
        starts = [m.start() for m in re.finditer(isin.lower(), f)]
    if not starts:
        return None
    start = starts[0]
    end = len(full)
    for other in other_names:
        o = flat(other).strip()
        if len(o) >= 6 and o != name and not name.startswith(o):
            pos = f.find(o, start + 500)
            if 0 < pos < end:
                end = pos
    return start, end


def extract(pages: list[str], doc: DocumentRef, isin: str | None, fund_name: str, other_names: list[str]) -> tuple[dict[str, Fact], list[str]]:
    full = "\n".join(pages)
    bounds = _section(full, isin, fund_name, other_names)
    if bounds is None:
        return {}, [f"section du fonds « {fund_name} » introuvable dans le prospectus : rien n'est lu"]
    a, b = bounds
    offsets = []
    pos = 0
    for p in pages:
        offsets.append(pos)
        pos += len(p) + 1
    text = full[a:b]
    f = flat(text)
    facts: dict[str, Fact] = {}

    def page_of(i: int) -> int:
        return max(n for n, off in enumerate(offsets, start=1) if off <= a + i)

    def add(name: str, value, m: re.Match, extra: int = 0) -> None:
        if name not in facts and value is not None:
            facts[name] = Fact(name, value, page_of(m.start()), snippet(text, m.start(), m.end() + extra), doc)

    m = re.search(r"(?:centralis\w*|cut-?off|heure limite)[^.]{0,160}?(\d{1,2})\s*h\s*(\d{2})?", f)
    if m:
        add("prospectus.cutoff", f"{int(m.group(1)):02d}:{m.group(2) or '00'}", m)
    m = re.search(r"(?:reglement|settlement)[^.]{0,120}?(?:j|d)\s*\+\s*(\d)", f)
    if m:
        add("prospectus.settlement", f"J+{m.group(1)}", m)
    m = re.search(r"valeur liquidative[^.]{0,120}?(quotidienne|chaque jour|hebdomadaire|bimensuelle|mensuelle)|"
                  r"net asset value[^.]{0,120}?(daily|each business day|weekly|monthly)", f)
    if m:
        word = m.group(1) or m.group(2)
        add("prospectus.nav_frequency", {"chaque jour": "quotidienne", "each business day": "daily"}.get(word, word), m)
    for name, label in (("prospectus.max_management_fee", r"frais de gestion financiere|management fees?"),
                        ("prospectus.max_entry_fee", r"commission de souscription non acquise|subscription fee not retained|droits d'entree"),
                        ("prospectus.max_exit_fee", r"commission de rachat non acquise|redemption fee not retained|droits de sortie")):
        for m in re.finditer(label, f):
            v = re.search(r"(\d{1,2}(?:[.,]\d{1,3})?)\s*%\s*(?:ttc|tax)?\s*(?:maximum|max)", f[m.end(): m.end() + 220]) or \
                re.search(r"(?:maximum|max\.?|au plus)\s*:?\s*(\d{1,2}(?:[.,]\d{1,3})?)\s*%", f[m.end(): m.end() + 220])
            if v:
                add(name, percent(v.group(1)), m, v.end())
                break
    m = re.search(r"swing pricing|mecanisme d'ajustement de la valeur liquidative", f)
    if m:
        add("prospectus.swing_pricing", "yes", m)
    m = re.search(r"plafonnement des rachats|redemption gates?|mecanisme de \"?gates?", f)
    if m:
        add("prospectus.gates", "yes", m)
    m = re.search(r"depositaire\s*:\s*([^\n]{4,90})", f)
    if m:
        add("prospectus.depositary", text[m.start(1): m.end(1)].strip(" .;"), m)
    m = re.search(r"commissaire aux comptes\s*:\s*([^\n]{4,90})", f)
    if m:
        add("prospectus.auditor", text[m.start(1): m.end(1)].strip(" .;"), m)
    return facts, ([] if facts else ["aucune modalité lue dans la section du fonds"])
