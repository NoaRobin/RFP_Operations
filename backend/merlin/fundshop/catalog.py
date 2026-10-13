"""Types de documents du site (rubrique, libellés, préfixe d'adresse, niveau part / fonds)."""
from __future__ import annotations

from dataclasses import dataclass

from ..rfi.ontology import norm


@dataclass(frozen=True)
class DocType:
    key: str
    label: str  # libellé affiché dans l'app (et valeur de la colonne « Type de document »)
    section: str  # rubrique du site (navigateur)
    site_labels: tuple[str, ...]  # libellés de la ligne sur le site
    needs_month: bool
    prefix: str | None  # préfixe d'adresse directe ; None = inconnu (navigateur seulement)
    level: str  # share | product
    lang: str = "FR"
    short: str = ""  # pour le nom de fichier

    @property
    def checks_isin(self) -> bool:
        return self.level == "share"


DOC_TYPES: dict[str, DocType] = {d.key: d for d in [
    DocType("dic", "DIC", "Documents juridiques", ("DIC PRIIPS", "DIC"), False, "DIPR", "share", short="DIC PRIIPS"),
    DocType("prospectus", "Prospectus", "Documents juridiques", ("Prospectus",), False, "PROS", "product", short="Prospectus"),
    DocType("reporting mensuel", "Reporting mensuel", "Reporting", ("Reporting Mensuel",), True, "REPM", "share", short="Reporting"),
    DocType("reporting mensuel en", "Reporting mensuel EN", "Reporting", ("Reporting Mensuel [EN]",), True, "REPM", "share", "EN",
            short="Reporting EN"),
    DocType("annexe sfdr", "Annexe SFDR", "Documents ESG", ("Annexe SFDR",), False, "SFDR", "product", short="Annexe SFDR"),
    DocType("annexe sfdr en", "Annexe SFDR EN", "Documents ESG", ("Annexe SFDR [EN]", "Annexe SFDR - EN", "Annexe SFDR EN", "SFDR Annex",
            "SFDR Annex [EN]"), False, "SFDR", "product", "EN", short="Annexe SFDR EN"),
    DocType("article 10 sfdr", "Article 10 SFDR", "Documents ESG", ("Article 10 SFDR",), False, "SFDR10", "product", short="Article 10 SFDR"),
    DocType("rapport annuel", "Rapport annuel", "Documents juridiques", ("Rapport annuel", "Annual report"), False, "RAAN", "product",
            short="Rapport annuel"),
    DocType("rapport semestriel", "Rapport semestriel", "Documents juridiques", ("Rapport semestriel", "Semi-annual report"), False, None,
            "product", short="Rapport semestriel"),
    DocType("rapport periodique sfdr", "Rapport périodique SFDR", "Documents ESG", ("Rapport périodique SFDR", "Rapport periodique SFDR"),
            False, None, "product", short="Rapport périodique SFDR"),
]}

ALIASES = {"dic priips": "dic", "kid": "dic", "dici": "dic", "rapport mensuel": "reporting mensuel", "reporting": "reporting mensuel",
           "reporting en": "reporting mensuel en", "rapport periodique sfdr": "rapport periodique sfdr", "annexe sfdr [en]": "annexe sfdr en",
           "article 10": "article 10 sfdr", "annual report": "rapport annuel", "semi-annual report": "rapport semestriel",
           "priips kid": "dic", "monthly report": "reporting mensuel", "prospectus complet": "prospectus"}


def doc_type(value: object) -> DocType:
    key = norm(value).replace("’", "'")
    key = ALIASES.get(key, key)
    if key not in DOC_TYPES:
        raise ValueError(f"Type de document inconnu : {value}. Types : {', '.join(d.label for d in DOC_TYPES.values())}")
    return DOC_TYPES[key]
