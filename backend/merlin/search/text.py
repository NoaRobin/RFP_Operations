"""Analyse du texte pour la recherche : normalisation, mots vides FR / EN / ES / IT, racinisation légère, bigrammes,
n-grammes de caractères, extraits surlignés.

Une seule chaîne d'analyse pour les documents et les questions (sinon les racines ne se rencontrent pas). La racinisation
est volontairement légère (pluriels, féminins, quelques suffixes) : elle rapproche « politiques » de « politique » ou
« investissements » de « investissement » sans confondre « gestion » et « gestionnaire ». Les n-grammes de caractères
rattrapent le reste (fautes de frappe, dérivations).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

STOP = set("""
a au aux avec ce ces cet cette dans de des du elle elles en et est etre il ils je la le les leur leurs lui ma mais me meme mes
moi mon ne nos notre nous on ou par pas pour qu que quel quelle quelles quels qui sa sans se ses si son sont sur ta te tes ton
tu un une vos votre vous y d l s c j n m t qu' etc ainsi aussi tres plus moins tout tous toute toutes chaque dont donc car
the of and or to in on for is are be by with as at an your you our we do does did what which how who whom from this that these
those it its their there here has have had was were will would can could should may might any all each per via into than then
el los las un una unos unas del al y o que en por para con su sus es son como cual cuales se lo le les
il lo gli i una uno della dello degli delle dei di da in con per su e o che come quale quali sono si ne
""".split())

# Mots de consigne des questionnaires : ils ne portent aucun sujet (« Veuillez décrire… », « Please provide… »)
FILLER = set("""
veuillez merci pouvez pourriez indiquer indiquez preciser precisez decrire decrivez detailler detaillez presenter presentez
expliquer expliquez fournir fournissez donner donnez communiquer communiquez lister listez mentionner mentionnez confirmer confirmez
please provide describe detail explain give list state indicate specify outline confirm kindly could would
describa explique indique proporcione detalle indicare descrivere fornire spiegare
avez avons ont etes sommes avoir disposez disposons dispose existe existent retracez racontez resumez dites pourriez
have has does do are is any comment combien many much where when quand pourquoi why
""".split())

_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "’": "'", "‘": "'", "`": "'", "ß": "ss"})


@lru_cache(maxsize=200_000)
def fold(text: str) -> str:
    """Minuscules, sans accents, ligatures dépliées."""
    value = unicodedata.normalize("NFKD", (text or "").translate(_LIGATURES))
    return "".join(c for c in value if not unicodedata.combining(c)).lower()


WORD = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def words(text: str) -> list[str]:
    """Mots normalisés, élisions retirées (« l'encours » → « encours »)."""
    out = []
    for w in WORD.findall(fold(text).replace("'", " ")):
        out.extend(p for p in w.split("-") if p) if "-" in w and not re.search(r"\d", w) else out.append(w)
    return out


_DERIVATIONAL = (
    "issements", "issement", "ionnements", "ionnement", "ionnez", "ionner", "ionnes", "ionne", "ations", "ation", "ateurs", "ateur",
    "atrices", "atrice", "ements", "ement", "ements", "ments", "ment", "ities", "ity", "ites", "ite", "euses", "euse",
    "ings", "ing", "ness", "ions", "ion",
)
_REPLACE = {"ionnez": "ion", "ionner": "ion", "ionnes": "ion", "ionne": "ion", "ionnements": "ion", "ionnement": "ion",
            "ions": "ion", "ion": "ion", "ives": "if", "ive": "if", "ifs": "if", "aux": "al", "ies": "y"}
_VERB = ("ez", "er", "ir", "ee", "es", "e", "ed")


@lru_cache(maxsize=200_000)
def stem(word: str) -> str:
    """Racine légère, commune aux langues du corpus (FR / EN surtout) : pluriel, dérivation (-ation, -ement, -ité…),
    terminaison verbale. « rémunérés » / « rémunération » → « remuner » ; « sélectionnez » / « sélection » → « selection »."""
    w = word
    if len(w) <= 3 or w.isdigit():
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif len(w) > 4 and w[-1] in "sx" and not w.endswith(("ss", "us", "is")):
        w = w[:-1] if not w.endswith("aux") else w[:-3] + "al"
    for suffix in ("ives", "ive", "ifs"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)] + "if"
    for suffix in _DERIVATIONAL:
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[: -len(suffix)] + _REPLACE.get(suffix, "")
            break
    else:
        for suffix in _VERB:
            if w.endswith(suffix) and len(w) - len(suffix) >= 4 and not w.endswith(("eur", "ier")):
                w = w[: -len(suffix)]
                break
    return w


def terms(text: str, keep_filler: bool = False) -> list[str]:
    """Racines des mots porteurs, dans l'ordre (les positions servent aux bigrammes et à la proximité)."""
    return [stem(w) for w in words(text) if w not in STOP and (keep_filler or w not in FILLER) and (len(w) > 1 or w.isdigit())]


def bigrams(seq: list[str]) -> list[str]:
    return [f"{a}_{b}" for a, b in zip(seq, seq[1:])]


def char_ngrams(text: str, n: int = 4) -> list[str]:
    """N-grammes de caractères par mot (« #gest », « esti »…) : tolèrent fautes et dérivations."""
    out = []
    for w in words(text):
        if w in STOP:
            continue
        padded = f"#{w}#"
        if len(padded) <= n:
            out.append(padded)
        else:
            out.extend(padded[i:i + n] for i in range(len(padded) - n + 1))
    return out


def snippet(text: str, query_terms: set[str], width: int = 240) -> tuple[str, list[tuple[int, int]]]:
    """Extrait le plus dense en mots de la question, et positions (début, fin) des mots retrouvés dans l'extrait."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return "", []
    spans = [(m.start(), m.end()) for m in re.finditer(r"[\wÀ-ÿ'’-]+", text)
             if stem(fold(m.group(0)).strip("'’-")) in query_terms]
    if len(text) <= width:
        return text, spans
    best, best_count = 0, -1
    for start, _ in spans or [(0, 0)]:
        lo = max(0, start - width // 4)
        count = sum(1 for s, _ in spans if lo <= s < lo + width)
        if count > best_count:
            best, best_count = lo, count
    lo = text.rfind(" ", 0, best) + 1 if best else 0
    hi = min(len(text), lo + width)
    hi = text.find(" ", hi) if text.find(" ", hi) != -1 and hi < len(text) else hi
    piece = text[lo:hi]
    prefix = "…" if lo else ""
    shift = len(prefix) - lo
    out_spans = [(s + shift, e + shift) for s, e in spans if lo <= s and e <= hi]
    return prefix + piece + ("…" if hi < len(text) else ""), out_spans


__all__ = ["fold", "words", "stem", "terms", "bigrams", "char_ngrams", "snippet", "STOP", "FILLER"]
