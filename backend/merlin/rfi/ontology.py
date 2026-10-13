"""Chargement et validation de l'ontologie RFI (concepts, facettes, vocabulaires).

L'ontologie est la « source de vérité » du remplissage : un concept n'est utilisable que si sa source existe
dans le catalogue Fabric (catalog/fabric_schema.csv). Les problèmes sont signalés, jamais contournés.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..data.catalog import Catalog

ONTOLOGY_DIR = Path(__file__).with_name("ontology")
TYPES = {"text", "long", "enum", "bool", "percent", "number", "int", "amount", "date", "time", "code", "list"}
COMPUTED = {"jump", "perf", "registration", "meta", "precedent", "fund", "share"}
PSEUDO_TERMS = {"period_mention", "country_mention"}


# --------------------------------------------------------------------------- normalisation
def norm(text: Any) -> str:
    """Minuscules, sans accents, apostrophes unifiées, ponctuation réduite à des espaces (sauf % ' / + - & . €)."""
    value = unicodedata.normalize("NFKD", str(text if text is not None else ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("’", "'").replace("`", "'").replace("‘", "'").replace("œ", "oe").replace("æ", "ae")
    value = re.sub(r"[^a-z0-9%'/+\-&.€$£]+", " ", value)
    value = re.sub(r"(?<![a-z0-9])[.\-]+|[.\-]+(?![a-z0-9])", " ", value)  # ponctuation isolée
    return " ".join(value.split())


def stem(token: str) -> str:
    """Racine très légère (pluriels FR/EN) : « frais »→« frais », « charges »→« charge », « lignes »→« ligne »."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token[-1] in "sx" and not token.endswith(("ss", "us", "is", "ais")):
        return token[:-1]
    return token


def tokens(text: str) -> list[str]:
    # « / » entre deux mots sépare deux mots (« zone géographique/secteur ») ; « 6/8/9 » reste un seul jeton
    text = re.sub(r"(?<=[a-z])/(?=[a-z])", " ", text)
    return [stem(t) for t in re.split(r"[\s']+", text) if t]


# --------------------------------------------------------------------------- modèle
@dataclass
class Term:
    """Expression d'un concept : une phrase contiguë, ou un ensemble de mots (« a & b ») dans n'importe quel ordre."""
    raw: str
    parts: list[list[str]]  # une seule partie = phrase contiguë ; plusieurs = co-occurrence

    @property
    def specificity(self) -> int:
        return sum(len(p) for p in self.parts)

    @property
    def words(self) -> set[str]:
        return {w for p in self.parts for w in p}


def parse_term(raw: str) -> Term:
    parts = [tokens(norm(p)) for p in str(raw).split("&")]
    return Term(raw=str(raw), parts=[p for p in parts if p])


@dataclass
class Concept:
    id: str
    label_fr: str
    label_en: str
    scope: str
    type: str
    source: Any
    terms: list[Term]
    require: list[Term] = field(default_factory=list)
    exclude: list[Term] = field(default_factory=list)
    facets: dict[str, str] = field(default_factory=dict)
    default: list[str] = field(default_factory=list)
    ambiguous: bool = False
    vocab: str | None = None
    range: tuple[float, float] | None = None
    validate: str | None = None
    transform: Any = None
    qualitative_ok: bool = False
    doc: list[str] = field(default_factory=list)  # faits de document (DIC, prospectus) qui recoupent ce concept
    ambiguous_always: bool = False  # lecture indirecte de la colonne : toujours « à vérifier »
    ask_bool: bool = False  # concept oui / non utilisable seulement si la question attend oui / non
    asof: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def computed(self) -> bool:
        return isinstance(self.source, str) and self.source.split(":", 1)[0] in COMPUTED

    def source_for(self, lang: str) -> str:
        if isinstance(self.source, dict):
            return self.source.get(lang) or self.source.get("fr") or next(iter(self.source.values()))
        return self.source

    @property
    def columns(self) -> list[tuple[str, str]]:
        """(table, colonne) Product Info lues par ce concept."""
        if self.computed:
            return []
        sources = self.source.values() if isinstance(self.source, dict) else [self.source]
        return [tuple(s.split(".", 1)) for s in sources]  # type: ignore[misc]

    def label(self, lang: str = "fr") -> str:
        return self.label_en if lang == "en" else self.label_fr

    def to_dict(self) -> dict[str, Any]:
        src = self.source if isinstance(self.source, str) else " / ".join(self.source.values())
        return {"id": self.id, "label": self.label_fr, "label_en": self.label_en, "scope": self.scope, "type": self.type,
                "source": src, "vocab": self.vocab, "ambiguous": self.ambiguous, "healthy": not self.problems,
                "problems": self.problems}


@dataclass
class VocabValue:
    id: str
    fr: str
    en: str
    synonyms: set[str]

    def label(self, lang: str) -> str:
        return self.en if lang == "en" else self.fr


@dataclass
class Ontology:
    concepts: dict[str, Concept]
    facets: dict[str, dict[str, list[Term]]]
    scope_terms: dict[str, list[Term]]
    generic: set[str]
    vocabularies: dict[str, list[VocabValue]]

    def usable(self) -> list[Concept]:
        return [c for c in self.concepts.values() if not c.problems]

    def vocab_value(self, vocab: str | None, raw: Any) -> VocabValue | None:
        """Valeur canonique d'un vocabulaire à partir d'un texte (valeur Product Info, option de liste…)."""
        if not vocab or vocab not in self.vocabularies:
            return None
        key = norm(raw)
        if not key:
            return None
        values = self.vocabularies[vocab]
        for v in values:
            if key in v.synonyms or key == norm(v.id) or key in (norm(v.fr), norm(v.en)):
                return v
        # Correspondance par inclusion, seulement si elle est unique (ex. « Article 8 SFDR (light green) »)
        hits = [v for v in values if any(len(s) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", key) for s in v.synonyms)]
        return hits[0] if len(hits) == 1 else None


def _range(value: Any) -> tuple[float, float] | None:
    if not value:
        return None
    lo, hi = value
    return float(lo), float(hi)


@lru_cache
def load_ontology(catalog: Catalog) -> Ontology:
    concepts_raw = yaml.safe_load((ONTOLOGY_DIR / "concepts.yaml").read_text(encoding="utf-8"))["concepts"]
    facets_raw = yaml.safe_load((ONTOLOGY_DIR / "facets.yaml").read_text(encoding="utf-8"))
    vocab_raw = yaml.safe_load((ONTOLOGY_DIR / "vocabularies.yaml").read_text(encoding="utf-8"))["vocabularies"]

    vocabularies = {
        name: [VocabValue(id=str(v["id"]), fr=str(v["fr"]), en=str(v["en"]),
                          synonyms={norm(s) for s in v.get("synonyms", [])} | {norm(v["fr"]), norm(v["en"])})
               for v in values]
        for name, values in vocab_raw.items()
    }
    facets = {name: {value: [parse_term(t) for t in terms] for value, terms in values.items()}
              for name, values in facets_raw["facets"].items()}
    scope_terms = {k: [parse_term(t) for t in v] for k, v in facets_raw["scope_terms"].items()}
    generic = {stem(t) for g in facets_raw["generic_terms"] for t in tokens(norm(g))}

    concepts: dict[str, Concept] = {}
    for spec in concepts_raw:
        fr, _, en = str(spec["label"]).partition("|")
        concept = Concept(
            id=spec["id"], label_fr=fr.strip(), label_en=(en or fr).strip(), scope=spec["scope"], type=spec["type"],
            source=spec["source"], terms=[parse_term(t) for t in spec.get("terms", [])],
            require=[parse_term(t) for t in spec.get("require", []) if t not in PSEUDO_TERMS],
            exclude=[parse_term(t) for t in spec.get("exclude", [])], facets=dict(spec.get("facets") or {}),
            default=list(spec.get("default") or []), ambiguous=bool(spec.get("ambiguous")), vocab=spec.get("vocab"),
            range=_range(spec.get("range")), validate=spec.get("validate"), transform=spec.get("transform"),
            qualitative_ok=bool(spec.get("qualitative_ok")), asof=spec.get("asof"), ask_bool=bool(spec.get("ask_bool")),
            ambiguous_always=bool(spec.get("ambiguous_always")),
            doc=[spec["doc"]] if isinstance(spec.get("doc"), str) else list(spec.get("doc") or []),
        )
        concept.pseudo_require = [t for t in spec.get("require", []) if t in PSEUDO_TERMS]  # type: ignore[attr-defined]
        if concept.id in concepts:
            concept.problems.append("Identifiant en double")
        if concept.type not in TYPES:
            concept.problems.append(f"Type inconnu : {concept.type}")
        if concept.scope not in {"fund", "share"}:
            concept.problems.append(f"Portée inconnue : {concept.scope}")
        if concept.vocab and concept.vocab not in vocabularies:
            concept.problems.append(f"Vocabulaire inconnu : {concept.vocab}")
        for facet, value in concept.facets.items():
            if facet not in facets or value not in facets[facet]:
                concept.problems.append(f"Facette inconnue : {facet}={value}")
        for facet in concept.default:
            if facet not in concept.facets:
                concept.problems.append(f"Facette par défaut non déclarée : {facet}")
        if not concept.terms:
            concept.problems.append("Aucun terme")
        # Les colonnes doivent exister dans le catalogue : jamais de nom deviné.
        for table, column in concept.columns + ([tuple(concept.asof.split(".", 1))] if concept.asof else []):
            t = catalog.table(table)
            if t is None or t.column(column) is None:
                concept.problems.append(f"Colonne absente du catalogue : {table}.{column}")
        concepts[concept.id] = concept
    # Variante de l'autre portée (fonds / part) partageant un terme : la portée de la question devient décisive
    for c in concepts.values():
        raws = {t.raw for t in c.terms}
        c.scope_sibling = any(o.scope != c.scope and raws & {t.raw for t in o.terms} for o in concepts.values())  # type: ignore[attr-defined]
    return Ontology(concepts=concepts, facets=facets, scope_terms=scope_terms, generic=generic, vocabularies=vocabularies)


__all__ = ["Concept", "Ontology", "Term", "VocabValue", "load_ontology", "norm", "stem", "tokens", "parse_term"]
