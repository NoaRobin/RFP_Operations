"""Identité d'un précédent : ISIN (clé de contrôle), cohérence nom de fichier / cellule. Aucune correction silencieuse."""
from __future__ import annotations

import re

from ..render import isin_valid  # même contrôle de clé que le rendu (une seule implémentation)

ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")


def isins_in(text: str) -> list[str]:
    return list(dict.fromkeys(ISIN_RE.findall((text or "").upper())))


def identity_problem(filename: str, cell_isins: list[str]) -> str:
    """Raison de bloquer la réutilisation automatique, ou chaîne vide.

    - ISIN du nom de fichier différent de l'ISIN lu dans le document ;
    - ISIN du document à clé invalide.
    Les valeurs sources ne sont jamais corrigées : on signale, on bloque, un humain confirme.
    """
    from_name = isins_in(filename)
    cells = [i for i in dict.fromkeys(c.strip().upper() for c in cell_isins if c)]
    for isin in cells:
        if not isin_valid(isin):
            return f"ISIN « {isin} » à clé de contrôle invalide dans le document : identité à confirmer"
    if from_name and cells and not set(from_name) & set(cells):
        return f"ISIN du nom de fichier ({', '.join(from_name)}) différent de l'ISIN du document ({', '.join(cells)}) : identité à confirmer"
    return ""
