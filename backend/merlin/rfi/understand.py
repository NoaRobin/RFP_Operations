"""Compréhension d'une question de RFI : facettes, portée, période, unités, type de réponse attendu.

Tout est déterministe et explicable : chaque élément détecté est restitué à l'utilisateur comme « indice ».
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .lexicon import question_language, to_pivot
from .ontology import Ontology, Term, norm, tokens

QUALITATIVE = re.compile(
    r"^(?:\S+\s+){0,3}(?:decrivez|decrire|expliquez|expliquer|presentez|presenter|detaillez|detailler|commentez|"
    r"justifiez|resumez|describe|explain|outline|discuss|elaborate|summarise|summarize|comment on|justify)\b"
    r"|\b(?:comment (?:le|la|les|votre|vos|est|sont|gerez|integrez|selectionnez)|pourquoi|how do|how does|how is|how are|why|"
    r"quelle est votre approche|what is your approach|votre philosophie|your philosophy|processus de|process for|"
    r"methodologie|methodology)\b")
BOOL_QUESTION = re.compile(
    r"(?:\b(?:oui|yes)\s*/\s*(?:non|no)\b|\by\s*/\s*n\b|\bo\s*/\s*n\b|-t-(?:il|elle|ils|elles)\b|\best-ce que\b|^est-ce\s|\s>\s*\d+\s*(?:ans?|years?)\s*\??$|"
    r"^(?:is|are|does|do|has|have|can|will|was|were)\s|^(?:le|la|les|ce|cette)\s+\S+(?:\s+\S+)?\s+"
    r"(?:est-il|est-elle|a-t-il|peut-il|utilise-t-il|investit-il|exclut-il|prend-il|integre-t-il|dispose-t-il|applique-t-il))")
PERCENT_ASK = re.compile(r"%|\bpourcentage\b|\bpercentage\b|\bpercent\b|\ben pourcent\b")
BP_ASK = re.compile(r"\b(?:bp|bps|pb|points de base|basis points?)\b")
SCALES = [
    (re.compile(r"(?<![a-z0-9])(?:md|mds|mrd|mrds|bn|bln|billions?|milliards?|md€|bn€|mds€)(?![a-z0-9])"), 1e9),
    (re.compile(r"(?<![a-z0-9])(?:m€|meur|musd|m\$|mio|mios|mn|mln|millions?|€m|eurm|usdm)(?![a-z0-9])|(?<![a-z0-9])(?:€|eur|usd)\s?m(?![a-z0-9])|"
                r"(?<![a-z0-9])m\s?(?:€|eur|usd)(?![a-z0-9])|(?<![a-z0-9])(?:en|in)\s+m(?![a-z0-9])"), 1e6),
    (re.compile(r"(?<![a-z0-9])(?:k€|keur|kusd|milliers|thousands?|€k|eurk)(?![a-z0-9])"), 1e3),
]
DATE_IN_TEXT = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b")
MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
          "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
          "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
WORD_NUMBERS = {"un": 1, "une": 1, "one": 1, "deux": 2, "two": 2, "trois": 3, "three": 3, "cinq": 5, "five": 5, "dix": 10, "ten": 10,
                "six": 6, "douze": 12, "twelve": 12}
EXISTENCE = re.compile(r"(?:^|\b)(?:y a-t-il|y-a-t-il|existe-t-il|exist-il|existe t il|is there|are there|does the (?:fund|share class) have|"
                       r"le fonds a-t-il|la part a-t-elle|a-t-il|a-t-elle|presence d'un|presence de)\b")
EXCLUSION = re.compile(r"\(?(?<![a-z0-9])(?:hors|excluding|excluant|excl\.?|sans compter|non compris|not including)\s[^()]*\)?")
ORDINALS = {"premiere": 1, "premier": 1, "1ere": 1, "1er": 1, "first": 1, "deuxieme": 2, "second": 2, "seconde": 2,
            "troisieme": 3, "third": 3, "quatrieme": 4, "fourth": 4, "cinquieme": 5, "fifth": 5, "sixieme": 6, "sixth": 6,
            "septieme": 7, "seventh": 7, "huitieme": 8, "eighth": 8, "neuvieme": 9, "ninth": 9, "dixieme": 10, "tenth": 10}
RANK = re.compile(r"(?<![a-z0-9])(?:(\d{1,2})\s*(?:e|eme|er|ere|st|nd|rd|th)|(?:n°|no\.?|rang|rank|#)\s*(\d{1,2})|(" +
                  "|".join(ORDINALS) + r"))(?![a-z0-9])")
SHARE_QUALIFIER = re.compile(r"\b(?:part|share class|classe|share)\s+(retail|clean(?:share)?|institutionnelle|institutional|i|r|c|d|p|f|z|n)\b")
HINT_DATE = re.compile(r"\b(?:jj/mm/aaaa|jj/mm/aa|dd/mm/yyyy|mm/dd/yyyy|yyyy-mm-dd|aaaa-mm-jj|dd/mm/yy|date)\b")
HINT_BOOL = re.compile(r"\b(?:oui\s*/\s*non|yes\s*/\s*no|y\s*/\s*n|o\s*/\s*n|oui ou non|yes or no|reponse binaire|binary answer)\b")


@dataclass
class Period:
    kind: str  # ytd | months | years | inception | calendar
    n: int = 0
    year: int | None = None
    annualized: bool | None = None  # None : non précisé

    def label(self, lang: str = "fr") -> str:
        if self.kind == "ytd":
            return "YTD"
        words = PERIOD_WORDS.get(lang, PERIOD_WORDS["en"])
        if self.kind == "inception":
            return words["inception"]
        if self.kind == "calendar":
            return str(self.year)
        unit = words["months"] if self.kind == "months" else (words["year"] if self.n == 1 else words["years"])
        ann = f" {words['annualized']}" if self.annualized else ""
        return f"{self.n} {unit}{ann}"


PERIOD_WORDS = {
    "fr": {"inception": "depuis la création", "months": "mois", "year": "an", "years": "ans", "annualized": "annualisé"},
    "en": {"inception": "since inception", "months": "months", "year": "year", "years": "years", "annualized": "annualised"},
    "es": {"inception": "desde el lanzamiento", "months": "meses", "year": "año", "years": "años", "annualized": "anualizada"},
    "it": {"inception": "dal lancio", "months": "mesi", "year": "anno", "years": "anni", "annualized": "annualizzata"},
}


@dataclass
class Understanding:
    text: str  # question telle que lue
    q: str  # question normalisée
    q_tokens: list[str]
    hint: str = ""  # consigne trouvée dans la case réponse (« Indiquer la devise… »)
    context: str = ""  # section, en-tête de colonne
    facets: dict[str, set[str]] = field(default_factory=dict)
    context_facets: dict[str, set[str]] = field(default_factory=dict)
    scopes: set[str] = field(default_factory=set)
    context_scopes: set[str] = field(default_factory=set)  # portée déduite de la section ou d'une grille par part
    entity_scope: str | None = None
    asks_date: bool = False
    existence: bool = False  # « Y a-t-il… », « Existe-t-il… », « Is there… »
    parent: str = ""
    rank: int | None = None  # « 3ème position », « first holding »
    share_qualifier: str | None = None  # « part Clean », « part I »… : la question vise peut-être une autre part
    qualitative: bool = False
    yes_no: bool = False
    period: Period | None = None
    explicit_date: date | None = None
    calendar_years: list[int] = field(default_factory=list)
    wants_percent: bool = False
    wants_bp: bool = False
    scale: float = 1.0
    currency: str | None = None
    countries: list[str] = field(default_factory=list)
    expected: str | None = None  # bool | date | percent | number | enum | text
    expected_from: str = ""  # liste déroulante | format de cellule | consigne | question
    options: list[str] = field(default_factory=list)
    language: str = "fr"  # langue de la question (es / it : lue via le lexique pivot)

    @property
    def all_tokens(self) -> list[str]:
        return self.q_tokens + tokens(to_pivot(norm(self.hint), self.language))

    def describe(self) -> list[str]:
        """Indices lisibles pour l'interface."""
        out = []
        for facet, values in {**self.context_facets, **self.facets}.items():
            out.append(f"{facet} : {', '.join(sorted(values))}")
        if self.period:
            out.append(f"période : {self.period.label()}")
        if self.explicit_date:
            out.append(f"date citée : {self.explicit_date.strftime('%d/%m/%Y')}")
        if self.scale != 1.0:
            out.append({1e3: "unité : milliers", 1e6: "unité : millions", 1e9: "unité : milliards"}[self.scale])
        if self.wants_bp:
            out.append("unité : points de base")
        if self.expected:
            out.append(f"réponse attendue : {self.expected} ({self.expected_from})")
        if self.countries:
            out.append(f"pays cité : {', '.join(self.countries)}")
        return out


# --------------------------------------------------------------------------- recherche de termes
def find_phrase(words: list[str], seq: list[str], prefix: bool = False) -> bool:
    n = len(words)
    if not n or n > len(seq):
        return False
    for i in range(len(seq) - n + 1):
        ok = True
        for j, w in enumerate(words):
            t = seq[i + j]
            if t == w or (prefix and len(w) >= 5 and t.startswith(w) and len(t) - len(w) <= 7):
                continue
            ok = False
            break
        if ok:
            return True
    return False


def has_term(term: Term, seq: list[str], prefix: bool = False) -> bool:
    if len(term.parts) == 1 and term.parts[0] == ["%"]:
        return "%" in seq
    return all(find_phrase(part, seq, prefix) for part in term.parts)


def detect_facets(ontology: Ontology, seq: list[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for facet, values in ontology.facets.items():
        for value, terms in values.items():
            if any(has_term(t, seq) for t in terms):
                found.setdefault(facet, set()).add(value)
    # « non acquis » contient « acquis » : la négation l'emporte
    retention = found.get("retention")
    if retention and {"retained", "not_retained"} <= retention:
        found["retention"] = {"not_retained"}
    return found


# --------------------------------------------------------------------------- périodes & dates
def _int_word(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    return WORD_NUMBERS.get(text)


def parse_explicit_date(q: str) -> date | None:
    m = DATE_IN_TEXT.search(q)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d)
        except ValueError:
            try:
                return date(y, d, mo)  # format US
            except ValueError:
                return None
    m = re.search(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", q)
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b", q)
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    return None


def parse_period(q: str, as_of: date) -> tuple[Period | None, list[int]]:
    """Période de performance demandée. Retourne aussi les années civiles citées hors dates complètes."""
    stripped = DATE_IN_TEXT.sub(" ", q)
    stripped = re.sub(r"\b\d{1,2}(?:er)?\s+(?:" + "|".join(MONTHS) + r")\s+\d{4}\b", " ", stripped)
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", stripped)]
    annualized: bool | None = None
    if re.search(r"\b(?:annualise|annualisee|annualises|annualisees|annualised|annualized|p\.?a|per annum|par an|moyenne annuelle|average annual)\b", q):
        annualized = True
    elif re.search(r"\b(?:cumule|cumulee|cumules|cumulees|cumulative|cumulated|non annualise|not annualised|not annualized)\b", q):
        annualized = False
    if re.search(r"\b(?:ytd|year to date|year-to-date|depuis le debut de l'annee|depuis le 1er janvier|depuis le debut d'annee|"
                 r"since the beginning of the year|debut d'annee|annee en cours|current year|since 1st january|since january 1st)\b", q):
        return Period("ytd"), years
    if re.search(r"\b(?:depuis (?:la )?(?:creation|lancement|l'origine|origine)|since inception|since launch|from inception|"
                 r"depuis le lancement|depuis la premiere vl)\b", q):
        return Period("inception", annualized=annualized), years
    m = re.search(r"\b(\d{1,2}|un|une|one|trois|three|six|douze|twelve)\s*(?:-\s*)?(mois|months?|m)\b", q)
    if m and _int_word(m.group(1)):
        n = _int_word(m.group(1)) or 0
        return (Period("years", 1, annualized=annualized) if n == 12 else Period("months", n)), years
    m = re.search(r"\b(\d{1,2}|un|une|one|deux|two|trois|three|cinq|five|dix|ten)\s*(?:-\s*)?(ans?|annees?|years?|yrs?|y)\b", q)
    if m and _int_word(m.group(1)):
        n = _int_word(m.group(1)) or 0
        return Period("years", n, annualized=annualized), years
    if re.search(r"\b(?:sur l'annee|over the year|one-year|1-year|annuelle|annual)\b", q) and not years:
        return Period("years", 1, annualized=annualized), years
    calendar = [y for y in years if 1990 <= y <= as_of.year]
    if len(calendar) == 1:
        y = calendar[0]
        return (Period("ytd") if y == as_of.year else Period("calendar", year=y)), years
    return None, years


# --------------------------------------------------------------------------- type attendu
def expected_from_options(ontology: Ontology, options: list[str]) -> str:
    if not options:
        return ""
    if all(ontology.vocab_value("yes_no", o) for o in options) and len(options) <= 4:
        return "bool"
    numeric = [o for o in options if re.fullmatch(r"\s*[<>≤≥]?\s*[-+]?\d+(?:[.,]\d+)?\s*%?\s*(?:[-–à]\s*\d+(?:[.,]\d+)?\s*%?)?\s*", str(o))]
    if len(numeric) == len(options):
        return "number"
    return "enum"


def expected_from_format(number_format: str | None) -> str:
    fmt = (number_format or "").lower()
    if not fmt or fmt == "general" or fmt == "@":
        return ""
    if "%" in fmt:
        return "percent"
    if re.search(r"(?<![\"\\])[dmy]{1,4}", re.sub(r"\[[^\]]*\]|\"[^\"]*\"", "", fmt)) and not re.search(r"[#0]", fmt):
        return "date"
    if re.search(r"[#0]", fmt):
        return "number"
    return ""


def detect_countries(ontology: Ontology, q: str) -> list[str]:
    found = []
    for v in ontology.vocabularies.get("country", []):
        for s in v.synonyms:
            if len(s) < 4:
                continue  # « de », « it », « no »… trop ambigus
            if re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", q):
                found.append(v.id)
                break
    return found


def understand(ontology: Ontology, text: str, *, hint: str = "", context: str = "", options: list[str] | None = None,
               number_format: str | None = None, as_of: date | None = None, entity_scope: str | None = None,
               parent: str = "", lang: str | None = None) -> Understanding:
    as_of = as_of or date.today()
    # Question espagnole / italienne : réécrite en français de l'ontologie (lexique pivot), puis lue comme les autres
    qlang = question_language(f"{text} {hint}", lang)
    own = EXCLUSION.sub(" ", to_pivot(norm(text), qlang))  # « (hors frais de transactions) » : ce qui est exclu n'est pas le sujet
    # Sous-question conditionnelle (« Si oui, de quel montant ? ») : le sujet vient de la question parente
    q = (to_pivot(norm(parent), qlang) + " " + own).strip() if parent else own
    seq = tokens(q)
    u = Understanding(text=text, q=q, q_tokens=seq, hint=hint, context=context, options=list(options or []), language=qlang)
    hint_n = to_pivot(norm(hint), qlang)
    context_n = to_pivot(norm(context), qlang)
    full = seq + tokens(hint_n)
    u.facets = detect_facets(ontology, full)
    u.context_facets = {k: v for k, v in detect_facets(ontology, tokens(context_n)).items() if k not in u.facets}
    for scope, terms in ontology.scope_terms.items():
        if any(has_term(t, seq) for t in terms):
            u.scopes.add(scope)
    ctx_seq = tokens(context_n)
    for scope, terms in ontology.scope_terms.items():
        if any(has_term(t, ctx_seq) for t in terms):
            u.context_scopes.add(scope)
    if entity_scope:
        u.context_scopes = {entity_scope}
        u.entity_scope = entity_scope
    u.qualitative = bool(QUALITATIVE.search(q))
    u.yes_no = bool(BOOL_QUESTION.search(own)) or bool(HINT_BOOL.search(hint_n)) or \
        bool(re.search(r"(?:>|≥)\s*\d+\s*(?:ans?|years?)\s*\??\s*$", str(text).strip().lower()))  # « Ancienneté > 3 ans »
    u.existence = bool(EXISTENCE.search(own))
    u.parent = parent
    u.explicit_date = parse_explicit_date(q)
    u.asks_date = bool(re.search(r"(?<![a-z0-9])(?:date|dates|depuis quand|depuis le|since when|since|depuis|when|quand|obtenu le|obtained on|obtained)(?![a-z0-9])", q)) \
        and not re.search(r"(?<![a-z0-9])(?:depuis (?:la )?(?:creation|lancement|l'origine|le debut)|since (?:inception|launch|the beginning))(?![a-z0-9])", q)
    u.period, u.calendar_years = parse_period(q + " " + hint_n, as_of)
    u.wants_percent = bool(PERCENT_ASK.search(q + " " + hint_n))
    u.wants_bp = bool(BP_ASK.search(q + " " + hint_n))
    for pattern, scale in SCALES:
        if pattern.search(q + " " + hint_n):
            u.scale = scale
            break
    m = re.search(r"(?<![a-z0-9])(eur|euro|euros|€|usd|\$|gbp|chf|jpy)(?![a-z0-9])", q + " " + hint_n) or \
        re.search(r"(?<![a-z0-9])[mk](€|\$)(?![a-z0-9])|(?<![a-z0-9])(eur|usd)[mk](?![a-z0-9])", q + " " + hint_n)
    if m:
        raw_ccy = next(g for g in m.groups() if g)
        u.currency = {"euro": "EUR", "euros": "EUR", "€": "EUR", "$": "USD"}.get(raw_ccy, raw_ccy.upper())
    u.countries = detect_countries(ontology, q)
    m = RANK.search(own)
    if m:
        u.rank = int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else ORDINALS[m.group(3)]
    m = SHARE_QUALIFIER.search(own)
    if m:
        u.share_qualifier = m.group(1)

    # Type attendu : liste déroulante > format de cellule > consigne > forme de la question
    kind = expected_from_options(ontology, u.options)
    if kind:
        u.expected, u.expected_from = kind, "liste déroulante"
    elif expected_from_format(number_format):
        u.expected, u.expected_from = expected_from_format(number_format), "format de la cellule"
    elif HINT_DATE.search(hint_n):
        u.expected, u.expected_from = "date", "consigne"
    elif HINT_BOOL.search(hint_n):
        u.expected, u.expected_from = "bool", "consigne"
    elif u.yes_no:
        u.expected, u.expected_from = "bool", "question"
    return u


__all__ = ["Understanding", "Period", "understand", "has_term", "find_phrase", "detect_facets", "parse_period"]
