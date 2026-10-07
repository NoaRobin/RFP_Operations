"""Schéma du fichier `manifest.yaml` d'une automatisation."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ParamType = Literal["string", "text", "number", "integer", "date", "boolean", "select", "multiselect", "isin"]


class Option(BaseModel):
    value: Any
    label: str


class ParamSpec(BaseModel):
    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    label: str
    type: ParamType = "string"
    required: bool = False
    default: Any = None
    help: str | None = None
    placeholder: str | None = None
    options: list[Option] | None = None
    # Requête qui alimente la liste de choix (colonnes `value` et `label`).
    options_query: str | None = None
    min: float | None = None
    max: float | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options(cls, value):
        if value is None:
            return value
        return [o if isinstance(o, dict) else {"value": o, "label": str(o)} for o in value]


class OutputSpec(BaseModel):
    type: Literal["excel", "csv", "table", "file"] = "excel"
    label: str = "Résultat"


class FabricSpec(BaseModel):
    """Automatisation déclarative : une requête paramétrée + un format de sortie. Zéro Python."""

    query: str | None = None
    query_file: str | None = "query.sql"
    output: Literal["excel", "table", "both"] = "both"
    filename: str = "{id}_{date}.xlsx"
    sheet_name: str = "Résultat"
    column_labels: dict[str, str] = Field(default_factory=dict)
    number_formats: dict[str, str] = Field(default_factory=dict)
    empty_is_error: bool = False


class Manifest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str
    description: str = ""
    icon: str = "sparkles"
    category: str = "Divers"
    type: Literal["python", "fabric"]
    version: str = "1.0"
    author: str = "Équipe RFP"
    tags: list[str] = Field(default_factory=list)
    estimated_minutes_saved: int = 10
    params: list[ParamSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    requires: list[Literal["fabric", "browser"]] = Field(default_factory=lambda: ["fabric"])
    fabric: FabricSpec | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "fabric" and self.fabric is None:
            self.fabric = FabricSpec()
        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            raise ValueError("Deux paramètres portent le même nom.")
        return self
