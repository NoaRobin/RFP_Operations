"""Mise en forme d'une valeur pour la case réponse : langue, unité, format de cellule, option de liste déroulante.

Garde-fous « zéro erreur » : une valeur hors bornes, un ISIN / LEI invalide, une valeur absente de la liste
déroulante, une date invraisemblable… ne sont JAMAIS écrits : la question passe « à vérifier » avec la raison.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .ontology import Concept, Ontology, VocabValue, norm
from .understand import Understanding
from .values import Raw, _num, is_empty, to_date

ISO_CURRENCIES = {"EUR", "USD", "GBP", "CHF", "JPY", "SEK", "NOK", "DKK", "CAD", "AUD", "SGD", "HKD", "CNY", "NZD", "PLN", "CZK", "HUF", "ZAR", "BRL", "MXN", "INR", "KRW", "TRY", "ILS", "AED", "SAR", "CLP"}


@dataclass
class Rendered:
    display: str | None  # texte montré dans l'interface
    value: Any = None  # ce qui est écrit (str, nombre, date) ; None → rien
    issues: list[str] = field(default_factory=list)  # empêchent l'écriture automatique
    blocking: bool = False  # aucune écriture possible
    option: str | None = None  # option de liste choisie


# --------------------------------------------------------------------------- validations
def isin_valid(code: str) -> bool:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", code):
        return False
    digits = "".join(str(int(c, 36)) for c in code[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(code[-1])


def lei_valid(code: str) -> bool:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{18}\d{2}", code):
        return False
    return int("".join(str(int(c, 36)) for c in code)) % 97 == 1


# --------------------------------------------------------------------------- formats
def fmt_number(value: float, decimals: int, lang: str) -> str:
    text = f"{value:,.{decimals}f}"
    if lang == "fr":
        text = text.replace(",", " ").replace(".", ",")
    elif lang in {"es", "it"}:
        text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")  # 1.234,56
    return text


def _decimals(value: float, max_dec: int = 2) -> int:
    for d in range(0, max_dec + 1):
        if abs(round(value, d) - value) < 1e-9:
            return d
    return max_dec


def _settlement(text: str, lang: str) -> str:
    if lang != "fr":  # es / it : notation D+N, comme en anglais
        text = re.sub(r"\bJ\s*([+-])\s*(\d+)", r"D\1\2", text)
        text = re.sub(r"\bjours? ouvres?\b", "business days", text, flags=re.I)
    else:
        text = re.sub(r"\bD\s*([+-])\s*(\d+)", r"J\1\2", text)
    return text


def _time(text: str, lang: str) -> str:
    m = re.match(r"^\s*(\d{1,2})\s*[:hH]\s*(\d{2})(?::\d{2})?\s*(.*)$", text)
    if not m:
        return text.strip()
    rest = m.group(3).strip()
    return f"{int(m.group(1)):02d}:{m.group(2)}" + (f" {rest}" if rest else "")


# --------------------------------------------------------------------------- listes déroulantes
_RANGE = re.compile(r"^\s*(?:(?P<op>inferieur ou egal a|au moins|moins de|plus de|less than|more than|over|under|up to|jusqu'a|au-dela de|superieur a|inferieur a|at least|"
                    r"menos de|mas de|hasta|al menos|meno di|piu di|oltre|fino a|almeno|inferiore a|superiore a)\s*)?"
                    r"(?:entre|between|de|from|tra|fra|da|desde)?\s*(?P<a>-?\d+(?:[.,]\d+)?)\s*%?\s*(?:(?:-|–|à|a|to|and|et|y|e)\s*(?P<b>-?\d+(?:[.,]\d+)?)\s*%?)?")


def _opnorm(text: str) -> str:
    """Normalisation qui CONSERVE les comparateurs (« > 5 ans » ≠ « 5 ans »)."""
    t = str(text)
    for a, b in (("≤", " inferieur ou egal a "), ("<=", " inferieur ou egal a "), ("≥", " au moins "), (">=", " au moins "),
                 ("<", " moins de "), (">", " plus de ")):
        t = t.replace(a, b)
    return norm(t)


def _bounds(option: str) -> tuple[float, float, bool, bool] | None:
    """(bas, haut, bas inclus, haut inclus) d'une option « 1-3 ans », « < 1 % », « > 5 years », « 4 »."""
    o = re.sub(r"\b(?:ans?|annees?|years?|mois|months?|jours?|days?|anos?|anni|anno|mese?s|mesi|mese|dias?|giorni|giorno)\b", "", _opnorm(option)).strip()
    m = _RANGE.match(o)
    if not m or not m.group("a"):
        return None
    if len(re.sub(r"[\d\s.,%<>=≤≥\-–]", "", o)) > 14:
        return None  # trop de texte autour : pas une simple fourchette
    a = float(m.group("a").replace(",", "."))
    b = m.group("b")
    op = (m.group("op") or "").strip()
    if b:
        return a, float(b.replace(",", ".")), True, True
    if op in {"moins de", "less than", "under", "inferieur a", "menos de", "meno di", "inferiore a"}:
        return float("-inf"), a, False, False
    if op in {"inferieur ou egal a", "up to", "jusqu'a", "hasta", "fino a"}:
        return float("-inf"), a, False, True
    if op in {"plus de", "more than", "over", "au-dela de", "superieur a", "mas de", "piu di", "oltre", "superiore a"}:
        return a, float("inf"), False, False
    if op in {"au moins", "at least", "al menos", "almeno"}:
        return a, float("inf"), True, False
    return a, a, True, True


def choose_option(options: list[str], *, number: float | None = None, vocab: VocabValue | None = None,
                  texts: list[str] | None = None, ontology: Ontology | None = None, vocab_name: str | None = None) -> tuple[str | None, str]:
    """Option de la liste correspondant à la valeur. (option, raison) ; option None si aucune ou plusieurs."""
    norm_opts = [(o, _opnorm(o)) for o in options if str(o).strip()]
    wanted = {_opnorm(t) for t in (texts or []) if t}
    if vocab is not None:
        wanted |= vocab.synonyms | {norm(vocab.fr), norm(vocab.en), norm(vocab.id)}
    exact = [o for o, n in norm_opts if n in wanted]
    if len(set(exact)) == 1:
        return exact[0], "correspondance exacte"
    # Choix combinés (« ISR/Finansol », « ISR + Greenfin ») : même ensemble d'éléments, dans n'importe quel ordre
    def parts(text: str) -> frozenset[str]:
        return frozenset(_opnorm(p) for p in re.split(r"\s*(?:/|,|;|\+|&|\bet\b|\band\b)\s*", str(text)) if _opnorm(p))
    for t in texts or []:
        want = parts(t)
        if len(want) > 1:
            combo = [o for o, _ in norm_opts if parts(o) == want]
            if len(set(combo)) == 1:
                return combo[0], "même combinaison d'éléments"
    if vocab is not None and ontology is not None and vocab_name:
        same = [o for o, _ in norm_opts if (v := ontology.vocab_value(vocab_name, o)) is not None and v.id == vocab.id]
        if len(set(same)) == 1:
            return same[0], "même valeur du vocabulaire"
    if number is not None:
        hits = []
        for o, _ in norm_opts:
            b = _bounds(o)
            if b is None:
                continue
            lo, hi, lo_in, hi_in = b
            if (lo < number or (lo_in and number == lo)) and (number < hi or (hi_in and number == hi)):
                hits.append(o)
        if len(hits) == 1:
            return hits[0], "valeur dans la fourchette"
        if len(hits) > 1:
            return None, f"la valeur {number:g} tombe dans plusieurs options ({', '.join(hits)})"
    if number is not None and any(_bounds(o) for o, _ in norm_opts):
        return None, "aucune fourchette de la liste ne contient la valeur"
    partial = [o for o, n in norm_opts if any(w and len(w) >= 4 and (w in n or n in w) for w in wanted)
               and not re.search(r"\d", n)]
    if len(set(partial)) == 1:
        return partial[0], "correspondance partielle (à vérifier)"
    return None, "aucune option de la liste ne correspond"


# --------------------------------------------------------------------------- rendu principal
def render(ontology: Ontology, concept: Concept, raw: Raw, u: Understanding, lang: str, *,
           number_format: str | None = None, assert_value: str | None = None, as_of: date | None = None) -> Rendered:
    as_of = as_of or date.today()
    value = raw.value
    if value is None or (not isinstance(value, (list, tuple)) and is_empty(value)):
        return Rendered(None, issues=[raw.note or "pas de donnée"], blocking=True)
    issues: list[str] = []
    if raw.stale:
        issues.append(f"donnée ancienne ({raw.data_date.strftime('%d/%m/%Y') if raw.data_date else '?'})")
    if raw.ambiguous_period:
        issues.append("période ou caractère annualisé non précisé : lecture par défaut")
    fmt = (number_format or "").lower()
    percent_cell = "%" in fmt
    t = concept.type

    # ---------------------------------------------------------------- question fermée sur une valeur
    if assert_value == "__present__":
        if value is None or str(value).strip() == "" or (isinstance(value, (list, tuple)) and not value):
            return Rendered(None, issues=["donnée vide : « non » ne peut pas en être déduit"], blocking=True)
        return _bool_out(ontology.vocab_value("yes_no", "yes"), u, lang, issues, ontology)
    if assert_value == "__positive__":
        number = _num(value[0] if isinstance(value, tuple) else value)
        if number is None:
            return Rendered(None, issues=[f"valeur non numérique : {value}"], blocking=True)
        return _bool_out(ontology.vocab_value("yes_no", "yes" if number > 0 else "no"), u, lang, issues, ontology)
    if assert_value is not None:
        actual = ontology.vocab_value(concept.vocab, value)
        if actual is None:
            return Rendered(None, issues=[f"valeur « {value} » non reconnue dans le vocabulaire {concept.vocab}"], blocking=True)
        yes = ontology.vocab_value("yes_no", "yes" if actual.id == assert_value else "no")
        return _bool_out(yes, u, lang, issues, ontology)

    if t == "bool":
        v = ontology.vocab_value("yes_no", value)
        if v is None:
            return Rendered(None, issues=[f"valeur « {value} » non interprétable en oui / non"], blocking=True)
        return _bool_out(v, u, lang, issues, ontology)

    if t == "enum":
        v = ontology.vocab_value(concept.vocab, value)
        if concept.range and v is not None:
            n = _num(v.id)
            if n is None or not concept.range[0] <= n <= concept.range[1]:
                return Rendered(None, issues=[f"valeur hors bornes : {value}"], blocking=True)
        if concept.validate == "currency":
            code = (v.id if v else str(value)).strip().upper()
            if code not in ISO_CURRENCIES:
                return Rendered(None, issues=[f"devise non ISO : {value}"], blocking=True)
        if u.options:
            option, why = choose_option(u.options, vocab=v, texts=[str(value)], number=_num(v.id) if v and concept.vocab == "sri" else None,
                                        ontology=ontology, vocab_name=concept.vocab)
            if option is None:
                return Rendered(None, issues=[f"« {v.label(lang) if v else value} » : {why}"], blocking=True)
            if "partielle" in why:
                issues.append(why)
            return Rendered(option, option, issues, option=option)
        if v is None:
            issues.append(f"valeur hors vocabulaire, reprise telle quelle : {value}")
            text = str(value).strip()
        else:
            text = v.label(lang)
        return Rendered(text, int(text) if concept.vocab == "sri" and text.isdigit() else text, issues)

    if t in {"percent", "number", "int", "amount"}:
        ccy = None
        if isinstance(value, tuple):
            value, ccy = value
        number = _num(value)
        if number is None:
            return Rendered(None, issues=[f"valeur non numérique : {value}"], blocking=True)
        if concept.range and not concept.range[0] <= number <= concept.range[1]:
            return Rendered(None, issues=[f"valeur hors bornes de vraisemblance : {number:g}"], blocking=True)
        if t == "int" and abs(number - round(number)) > 1e-9:
            return Rendered(None, issues=[f"entier attendu : {number:g}"], blocking=True)
        if u.options:
            option, why = choose_option(u.options, number=number, texts=[fmt_number(number, _decimals(number), lang), f"{number:g}"])
            if option is None:
                return Rendered(None, issues=[f"{number:g} : {why}"], blocking=True)
            return Rendered(option, option, issues + ([why] if "partielle" in why else []), option=option)
        if t == "percent":
            if percent_cell:
                return Rendered(fmt_number(number, 2 if concept.computed else max(2, _decimals(number, 3)), lang) + " %",
                                round(number / 100, 6 if concept.computed else 8), issues)
            if u.wants_bp:
                bp = round(number * 100, 2)
                return Rendered(f"{fmt_number(bp, _decimals(bp, 1), lang)} bp", bp, issues)
            d = 2 if concept.computed else (max(2, _decimals(number, 3)) if abs(number) < 100 else 2)
            if u.wants_percent:
                return Rendered(fmt_number(number, d, lang), round(number, 4), issues)
            text = fmt_number(number, d, lang) + " %"
            return Rendered(text, text, issues)
        if t == "amount":
            scale = u.scale
            if scale == 1.0 and number >= 1e6 and concept.id.startswith("jump.encours"):
                scale = 1e6  # un encours brut à l'euro près n'est jamais attendu : millions par défaut, unité affichée
                shown = fmt_number(number / scale, 1, lang) + (" m" if lang == "en" else " M") + (f" {ccy}" if ccy else "")
                return Rendered(shown, shown, issues)
            scaled = number / scale
            decimals = 0 if scale == 1 else (1 if scaled >= 10 else 2)
            text = fmt_number(scaled, decimals, lang)
            if ccy and u.currency and ccy != u.currency:
                return Rendered(None, issues=[f"montant en {ccy}, la question le demande en {u.currency}"], blocking=True)
            if ccy and u.currency is None and not u.options:
                text_ccy = f"{text} {ccy}"
                return Rendered(text_ccy, text_ccy if not fmt else round(scaled, decimals), issues)
            return Rendered(text, round(scaled, decimals), issues)
        decimals = 0 if t == "int" else _decimals(number, 4)
        text = fmt_number(number, decimals, lang)
        if ccy and t == "number":
            return Rendered(f"{text} {ccy}", round(number, 4) if fmt else f"{text} {ccy}", issues)
        return Rendered(text, int(round(number)) if t == "int" else round(number, 4), issues)

    if t == "date":
        d = to_date(value)
        if d is None:
            return Rendered(None, issues=[f"date illisible : {value}"], blocking=True)
        upper = date(as_of.year + 60, 12, 31) if concept.id.endswith("echeance") else as_of
        if not date(1900, 1, 1) <= d <= upper:
            return Rendered(None, issues=[f"date invraisemblable : {d.isoformat()}"], blocking=True)
        us = "mm/dd/yyyy" in norm(u.hint)
        text = d.strftime("%m/%d/%Y" if us else "%d/%m/%Y")
        if u.options:
            option, why = choose_option(u.options, texts=[text, d.isoformat(), str(d.year)])
            if option is None:
                return Rendered(None, issues=[f"{text} : {why}"], blocking=True)
            return Rendered(option, option, issues, option=option)
        return Rendered(text, d if "date" in (u.expected or "") or _is_date_format(fmt) else text, issues)

    if t == "list":
        if not value:
            return Rendered(None, issues=["liste vide"], blocking=True)
        if isinstance(value[0], tuple):
            text = "; ".join(f"{_translate_item(ontology, n, lang)} ({fmt_number(w, 2, lang)} %)" for n, w in value)
        else:
            labels = []
            for item in value:
                v = ontology.vocab_value(concept.vocab, item) if concept.vocab else None
                labels.append(v.label(lang) if v else str(item))
            text = ", ".join(labels)
        return Rendered(text, text, issues)

    text = str(value).strip()
    if t == "code":
        if concept.validate == "isin" and not isin_valid(text):
            return Rendered(None, issues=[f"ISIN invalide (clé de contrôle) : {text}"], blocking=True)
        if concept.validate == "lei" and not lei_valid(text):
            return Rendered(None, issues=[f"LEI invalide (clé de contrôle) : {text}"], blocking=True)
    if t == "time":
        text = _time(text, lang)
    if concept.id.startswith("part.reglement"):
        text = _settlement(text, lang)
    if u.options:
        nums = re.findall(r"\d+(?:[.,]\d+)?", text)
        number = float(nums[0].replace(",", ".")) if len(nums) == 1 else None
        option, why = choose_option(u.options, texts=[text], number=number)
        if option is None:
            return Rendered(None, issues=[f"« {text} » : {why}"], blocking=True)
        return Rendered(option, option, issues + ([why] if "partielle" in why else []), option=option)
    if t == "long" and len(text) > 32000:
        return Rendered(None, issues=["texte trop long pour une cellule"], blocking=True)
    return Rendered(text, text, issues)


def _is_date_format(fmt: str) -> bool:
    from .understand import expected_from_format

    return expected_from_format(fmt) == "date"


def _translate_item(ontology: Ontology, name: str, lang: str) -> str:
    for vocab in ("asset_class", "currency"):
        v = ontology.vocab_value(vocab, name)
        if v:
            return v.label(lang)
    return name


def _bool_out(v: VocabValue | None, u: Understanding, lang: str, issues: list[str], ontology: Ontology) -> Rendered:
    if v is None:
        return Rendered(None, issues=["oui / non indéterminé"], blocking=True)
    if u.options:
        option, why = choose_option(u.options, vocab=v, ontology=ontology, vocab_name="yes_no")
        if option is None:
            return Rendered(None, issues=[f"« {v.label(lang)} » : {why}"], blocking=True)
        return Rendered(option, option, issues, option=option)
    hint = norm(u.hint)
    if re.search(r"\by\s*/\s*n\b", hint) or re.search(r"\by\s*/\s*n\b", u.q):
        text = "Y" if v.id == "yes" else "N"
    elif re.search(r"\bo\s*/\s*n\b", hint) or re.search(r"\bo\s*/\s*n\b", u.q):
        text = "O" if v.id == "yes" else "N"
    elif "yes" in hint or "yes" in u.q.split():
        text = v.en
    elif "oui" in hint or "oui" in u.q.split():
        text = v.fr
    else:
        text = v.label(lang)
    return Rendered(text, text, issues)


__all__ = ["Rendered", "render", "choose_option", "isin_valid", "lei_valid", "fmt_number"]
