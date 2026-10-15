"""Une réponse historique correspond-elle à la donnée Fabric d'un concept ? (match | mismatch | unknown)

Sert à deux choses : vérifier qu'un ancien RFI disait bien la même chose que la donnée (preuve), et déduire quelle
donnée Fabric se cache derrière une question que l'ontologie ne sait pas lire (liaison). Prudence : formats, unités
(fraction / points de %, millions) et arrondis sont tolérés ; un doute donne « unknown », jamais « match ».
"""
from __future__ import annotations

import re
from typing import Any

from ..ontology import Concept, Ontology, norm
from ..values import is_empty, to_date
from .retrieval import content_words

NUM = re.compile(r"[-+]?\d[\d\s  ]*(?:[.,]\d+)?")
NOT_ANSWERS = {"n/a", "na", "nc", "n.c", "nd", "n.d", "-", "--", "?", "tbc", "a confirmer", "non communique", "non disponible", "#n/a"}


def parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    m = NUM.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s  ]", "", m.group(0))
    if raw.count(",") == 1 and raw.count(".") == 0:
        raw = raw.replace(",", ".")
    raw = raw.replace(",", "")
    try:
        number = float(raw)
    except ValueError:
        return None
    return number


def _close(a: float, b: float, rel: float, abs_tol: float) -> bool:
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))


def same(ontology: Ontology, concept: Concept, fabric: Any, historical: Any) -> str:
    """Compare la valeur Fabric (brute, avant mise en forme) à une réponse historique."""
    if isinstance(historical, str) and norm(historical) in NOT_ANSWERS:
        return "unknown"
    if is_empty(fabric) or historical is None or str(historical).strip() == "":
        return "unknown"
    if isinstance(fabric, tuple):  # (montant, devise)
        fabric = fabric[0]
    t = concept.type
    if t in {"percent", "number", "int", "amount"}:
        a, b = parse_number(fabric), parse_number(historical)
        if a is None or b is None:
            return "unknown"
        if t == "percent":
            text = str(historical)
            candidates = [b, b * 100] if ("%" not in text and abs(b) <= 1) else [b]
            return "match" if any(_close(a, c, 0.01, 0.011) for c in candidates) else "mismatch"
        if t == "amount":
            # « en millions », « en milliards » : l'échelle n'est pas toujours écrite
            return "match" if any(_close(a, b * s, 0.01, 0.5) for s in (1, 1e3, 1e6, 1e9)) else "mismatch"
        return "match" if _close(a, b, 0.0, 1e-6) else "mismatch"
    if t == "date":
        da, db = to_date(fabric), to_date(historical)
        if da is None or db is None:
            return "unknown"
        return "match" if da == db else "mismatch"
    if t == "bool":
        va, vb = ontology.vocab_value("yes_no", fabric), ontology.vocab_value("yes_no", historical)
        if va is None or vb is None:
            return "unknown"
        return "match" if va.id == vb.id else "mismatch"
    if t == "enum" and concept.vocab:
        va, vb = ontology.vocab_value(concept.vocab, fabric), ontology.vocab_value(concept.vocab, historical)
        if va is not None and vb is not None:
            return "match" if va.id == vb.id else "mismatch"
        if va is not None and vb is None:
            return _text_same(fabric, historical)
        return "unknown"
    if t == "list" and isinstance(fabric, (list, tuple)):
        return "unknown"
    return _text_same(fabric, historical)


def _text_same(a: Any, b: Any) -> str:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return "unknown"
    if na == nb:
        return "match"
    if len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na) and min(len(na), len(nb)) / max(len(na), len(nb)) >= 0.5:
        return "match"
    wa, wb = content_words(na), content_words(nb)
    if wa and wb:
        jac = len(wa & wb) / len(wa | wb)
        if jac >= 0.75:
            return "match"
        short = len(na.split()) <= 8 and len(nb.split()) <= 8  # noms, codes, libellés courts
        if jac < (0.5 if short else 0.2):
            return "mismatch"
    return "unknown"
