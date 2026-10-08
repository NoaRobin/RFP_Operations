"""Modèles de rédaction paramétrés, construits seulement après décomposition des faits.

Une réponse narrative historique est découpée en : faits reconnus (valeurs Fabric du fonds d'origine retrouvées dans
le texte → paramètres {concept}) et texte fixe. S'il reste un élément propre au fonds d'origine qui n'est pas expliqué
(ISIN, nom, chiffre, date), le modèle est refusé : le texte ne sert que de référence de style.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..ontology import norm

# Faits typiques des paragraphes de présentation d'un fonds
FACT_CONCEPTS = ["fonds.nom", "part.nom", "part.isin", "fonds.societe_gestion", "fonds.devise", "part.devise", "fonds.date_creation",
                 "part.date_creation", "fonds.indice_reference", "fonds.sfdr", "fonds.sri", "fonds.duree_placement", "fonds.gerant",
                 "fonds.depositaire", "fonds.forme_juridique", "fonds.domicile", "fonds.classe_actifs",
                 "part.frais_courants_ex_post", "part.frais_gestion_max", "part.commission_surperformance",
                 "fonds.part_min_investissements_durables", "fonds.echeance"]
RESIDUAL = [
    (re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b"), "ISIN"),
    (re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b(?:19|20)\d{2}\b"), "date ou année"),
    (re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|pct|bp|pb|bps|pbs)"), "chiffre"),
    (re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:m€|md€|meur|mdeur|millions?|milliards?|bn|mn|k€)"), "montant"),
]


@dataclass
class Template:
    text: str  # avec {concept} à la place des faits
    params: list[str] = field(default_factory=list)
    residual: list[str] = field(default_factory=list)  # éléments propres au fonds d'origine non expliqués

    @property
    def safe(self) -> bool:
        return bool(self.params) and not self.residual


def _variants(value: Any, display: str | None) -> list[str]:
    out = []
    for v in (display, value if isinstance(value, str) else None):
        if v and len(str(v).strip()) >= 3:
            out.append(str(v).strip())
    return list(dict.fromkeys(out))


def decompose(text: str, facts: dict[str, tuple[Any, str | None]], origin_names: list[str]) -> Template:
    """facts : concept → (valeur brute, rendu) pour le fonds d'ORIGINE du texte."""
    template = text
    params: list[str] = []
    for cid, (value, display) in sorted(facts.items(), key=lambda kv: -max((len(v) for v in _variants(*kv[1])), default=0)):
        for variant in sorted(_variants(value, display), key=len, reverse=True):
            pattern = re.compile(re.escape(variant), re.IGNORECASE)
            if pattern.search(template):
                template = pattern.sub("{" + cid + "}", template)
                params.append(cid)
                break
    stripped = re.sub(r"\{[a-z_.0-9]+\}", " ", template)
    residual = []
    for name in origin_names:
        if name and len(name) >= 4 and norm(name) in norm(stripped):
            residual.append(f"nom « {name} »")
    for regex, label in RESIDUAL:
        for m in regex.finditer(stripped):
            residual.append(f"{label} « {m.group(0).strip()} »")
    return Template(template, list(dict.fromkeys(params)), list(dict.fromkeys(residual))[:6])


def fill(template: Template, current: Callable[[str], str | None]) -> str | None:
    """Remplit avec les faits du fonds courant ; None si un paramètre manque (jamais de trou silencieux)."""
    out = template.text
    for cid in template.params:
        value = current(cid)
        if value is None or str(value).strip() == "":
            return None
        out = out.replace("{" + cid + "}", str(value))
    return out
