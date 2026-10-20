"""L'Atelier Excel branché sur le moteur du compléteur RFI : ontologie, compréhension (FR / EN / ES / IT), valeurs, rendu.

Chaque concept de l'ontologie RFI devient une « extraction » de l'Atelier (identifiant `onto:<concept>`). L'en-tête de la
colonne (ou le libellé de la ligne, classeur transposé) est lu comme une question de RFI : « Performance 3 ans annualisée »
donne la période, « Encours (M€) » l'unité, « Divisa de la clase » la langue. La valeur de chaque ISIN est lue par
`merlin.rfi.values.Values` (fiche Product Info de la part et de SON fonds, JUMP, performances) puis mise en forme par
`merlin.rfi.render` selon le format de la cellule : exactement le même chemin que le compléteur RFI.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..data.access import DataAccess, DataError
from ..rfi.lexicon import detect_language
from ..rfi.match import match
from ..rfi.ontology import Concept, Ontology, load_ontology
from ..rfi.render import render
from ..rfi.understand import understand
from ..rfi.values import Values

PREFIX = "onto:"
AUTO_SCORE = 0.70  # même seuil que le compléteur RFI pour une proposition directe
GROUPS = {"fonds": "Ontologie RFI · Fonds", "part": "Ontologie RFI · Part", "jump": "Ontologie RFI · Encours & portefeuille",
          "perf": "Ontologie RFI · Performances", "societe": "Ontologie RFI · Société de gestion", "meta": "Ontologie RFI · Divers"}
FORMATS = {"percent": "percent", "number": "number", "int": "number", "amount": "amount", "date": "date"}


def is_ontology(extraction_id: str) -> bool:
    return str(extraction_id).startswith(PREFIX)


def concept_id(extraction_id: str) -> str:
    return str(extraction_id)[len(PREFIX):]


def ontology_for(data: DataAccess) -> Ontology:
    return load_ontology(data.catalog)


def palette(ontology: Ontology) -> list[dict[str, Any]]:
    """Concepts de l'ontologie présentés comme des extractions de l'Atelier (clé : ISIN de la part)."""
    out = []
    for c in ontology.concepts.values():
        source = c.source if isinstance(c.source, str) else " / ".join(c.source.values())
        caution = "Lecture par défaut discutable : vérifiez l'aperçu." if (c.ambiguous or c.ambiguous_always) else None
        out.append({"id": PREFIX + c.id, "label": c.label_fr, "group": GROUPS.get(c.id.split(".", 1)[0], GROUPS["meta"]), "key": "isin_part",
                    "format": FORMATS.get(c.type, "text"), "synonyms": [t.raw for t in c.terms[:12]] + [c.label_en],
                    "source": source, "caution": caution, "healthy": not c.problems, "problems": c.problems})
    return out


def sheet_language(texts: list[str]) -> str:
    return detect_language(" ".join(t for t in texts if t))


def suggest(ontology: Ontology, header: str, lang: str | None, limit: int = 3) -> list[dict[str, Any]]:
    """Concepts probables pour un en-tête de colonne (ou un libellé de ligne), lu comme une question de RFI sur une part."""
    if not header or not str(header).strip():
        return []
    u = understand(ontology, str(header), entity_scope="share", lang=lang)
    out = []
    for cand in match(ontology, u, limit=limit):
        if cand.concept.problems:
            continue
        out.append({"extraction": PREFIX + cand.concept.id, "label": cand.concept.label_fr, "score": round(float(cand.score), 3),
                    "auto": cand.score >= AUTO_SCORE and not cand.flags and not cand.concept.ambiguous})
    return out


class OntologyFiller:
    """Valeurs d'un concept pour une liste d'ISIN, une fiche Fabric par part (et par fonds de la part)."""

    def __init__(self, data: DataAccess, ontology: Ontology, as_of: str | date, lang: str = "fr"):
        self.data, self.ontology, self.lang = data, ontology, lang
        self.as_of = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of)[:10])
        self._values: dict[str, Values] = {}
        self._funds: dict[str, str] | None = None
        self.errors: list[str] = []

    def _fund_of(self, isin: str) -> str | None:
        if self._funds is None:
            from ..rfi.service import fund_directory

            try:
                self._funds = {s["isin"].upper(): item["pid"] for item in fund_directory(self.data) for s in item["shares"]}
            except DataError as error:
                self.errors.append(str(error))
                self._funds = {}
        return self._funds.get(isin.upper())

    def values(self, isin: str) -> Values | None:
        isin = isin.strip().upper()
        if isin not in self._values:
            pid = self._fund_of(isin)
            if pid is None:
                return None
            self._values[isin] = Values(self.data, self.ontology, pid, isin, self.as_of)
        return self._values[isin]

    def fill(self, concept: Concept, header: str, isin: str, number_format: str | None = None) -> dict[str, Any]:
        """{"value", "display", "issues", "evidence"} ; value None → rien à écrire (raison dans issues)."""
        vals = self.values(isin)
        if vals is None:
            return {"value": None, "display": "", "issues": [f"ISIN {isin} inconnu de Product Info"], "evidence": ""}
        u = understand(self.ontology, str(header or concept.label_fr), entity_scope="share", lang=self.lang, as_of=self.as_of,
                       number_format=number_format)
        raw = vals.get(concept, u, self.lang)
        rendered = render(self.ontology, concept, raw, u, self.lang, number_format=number_format, as_of=self.as_of)
        for e in vals.errors:
            if e not in self.errors:
                self.errors.append(e)
        value = None if rendered.blocking else rendered.value
        if isinstance(value, datetime):
            value = value.date()
        return {"value": value, "display": rendered.display or "", "issues": list(rendered.issues), "evidence": raw.evidence}


__all__ = ["PREFIX", "OntologyFiller", "is_ontology", "concept_id", "palette", "suggest", "sheet_language", "ontology_for"]
