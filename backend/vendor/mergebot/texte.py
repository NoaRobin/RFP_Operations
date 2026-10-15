"""Outils texte : normalisation qui conserve les positions des caractères."""

import re
import unicodedata

_APOSTROPHES = {"’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"}
_ESPACES = {" ", " ", " ", " ", "\t", "\x0b"}


def _normaliser_car(c):
    if c in _APOSTROPHES:
        return "'"
    if c in _ESPACES:
        return " "
    if c in "–—‑":
        return "-"
    base = unicodedata.normalize("NFD", c)[0]
    bas = base.lower()
    return bas[0] if bas else c


def normaliser(texte):
    """Minuscules, sans accents, apostrophes et espaces unifiés.

    Le résultat a exactement la même longueur que l'entrée, ce qui permet de
    chercher dans le texte normalisé et de reporter les positions sur le texte
    d'origine.
    """
    return "".join(_normaliser_car(c) for c in texte)


_FIN_PHRASE = re.compile(r"(?<=[.!?;])\s+(?=\S)")


def phrases(texte):
    """Découpe un paragraphe en phrases : liste de (debut, fin)."""
    res = []
    debut = 0
    for m in _FIN_PHRASE.finditer(texte):
        res.append((debut, m.start()))
        debut = m.end()
    if debut < len(texte):
        res.append((debut, len(texte)))
    return res or [(0, len(texte))]
