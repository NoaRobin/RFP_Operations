"""Catalogue Fabric chargé depuis catalog/fabric_schema.csv — la source de vérité.

Sert à :
- valider les requêtes des automatisations (aucun nom de table/colonne inventé),
- générer le schéma des données de démonstration,
- exposer le catalogue à l'interface.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class Column:
    name: str
    position: int
    data_type: str
    max_length: int | None
    precision: int | None
    scale: int | None
    nullable: bool

    @property
    def type_label(self) -> str:
        if self.data_type == "decimal" and self.precision is not None:
            return f"decimal({self.precision},{self.scale or 0})"
        if self.data_type == "varchar" and self.max_length:
            return f"varchar({self.max_length})"
        return self.data_type

    @property
    def kind(self) -> str:
        """Famille simplifiée : text | number | date | datetime."""
        if self.data_type in {"decimal", "numeric", "int", "bigint", "float", "real", "smallint", "bit"}:
            return "number"
        if self.data_type == "date":
            return "date"
        if self.data_type.startswith("datetime"):
            return "datetime"
        return "text"


@dataclass
class Table:
    database: str
    schema: str
    name: str
    columns: list[Column] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


def _int(value: str) -> int | None:
    value = (value or "").strip()
    return int(value) if value and value.upper() != "NULL" else None


class Catalog:
    def __init__(self, tables: dict[str, Table]):
        self.tables = tables

    @classmethod
    def from_csv(cls, path: Path) -> "Catalog":
        tables: dict[str, Table] = {}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = row["nom_table"].strip()
                table = tables.setdefault(
                    name, Table(row["nom_base"].strip(), row["schema_table"].strip(), name)
                )
                table.columns.append(
                    Column(
                        name=row["nom_colonne"].strip(),
                        position=int(row["position_colonne"]),
                        data_type=row["type_donnee"].strip().lower(),
                        max_length=_int(row["longueur_max"]),
                        precision=_int(row["precision_numerique"]),
                        scale=_int(row["decimales"]),
                        nullable=row["accepte_null"].strip().upper() == "YES",
                    )
                )
        for table in tables.values():
            table.columns.sort(key=lambda c: c.position)
        return cls(tables)

    # ------------------------------------------------------------------ lookup
    def table(self, name: str) -> Table | None:
        return self.tables.get(name)

    def _case_hint(self, name: str, candidates: list[str]) -> str:
        match = next((c for c in candidates if c.lower() == name.lower()), None)
        return f" (vouliez-vous dire « {match} » ? Le SQL endpoint est sensible à la casse)" if match else ""

    # -------------------------------------------------------------- validation
    def validate_sql(self, sql: str) -> list[str]:
        """Retourne la liste des problèmes (vide = requête conforme au catalogue)."""
        try:
            tree = sqlglot.parse_one(sql, read="tsql")
        except sqlglot.errors.ParseError as error:
            return [f"Requête illisible : {error}"]

        errors: list[str] = []
        cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
        aliases = {a.alias for a in tree.find_all(exp.Alias) if a.alias}
        aliases |= {
            col.name
            for cte in tree.find_all(exp.CTE)
            for col in (cte.args.get("alias").columns if cte.args.get("alias") else [])
        }

        referenced: dict[str, Table] = {}  # alias ou nom -> table
        for node in tree.find_all(exp.Table):
            name = node.name
            if name in cte_names:
                continue
            table = self.table(name)
            if table is None:
                errors.append(
                    f"Table inconnue du catalogue : {name}"
                    + self._case_hint(name, list(self.tables))
                )
                continue
            if node.db and node.db != table.schema:
                errors.append(f"Schéma inattendu pour {name} : {node.db} (attendu : {table.schema})")
            referenced[node.alias_or_name] = table
            referenced[name] = table

        all_columns = {c.name for t in referenced.values() for c in t.columns}
        for column in tree.find_all(exp.Column):
            name = column.name
            if not name or name == "*" or name in aliases:
                continue
            qualifier = column.table
            if qualifier and qualifier in referenced:
                table = referenced[qualifier]
                if table.column(name) is None:
                    errors.append(
                        f"Colonne inconnue : {qualifier}.{name} (table {table.name})"
                        + self._case_hint(name, [c.name for c in table.columns])
                    )
            elif qualifier and qualifier in cte_names:
                continue
            elif name not in all_columns and referenced:
                errors.append(
                    f"Colonne inconnue : {name}" + self._case_hint(name, sorted(all_columns))
                )
        return sorted(set(errors))

    def to_dict(self) -> list[dict]:
        return [
            {
                "database": t.database,
                "schema": t.schema,
                "name": t.name,
                "columns": [
                    {
                        "name": c.name,
                        "type": c.type_label,
                        "kind": c.kind,
                        "nullable": c.nullable,
                        "position": c.position,
                    }
                    for c in t.columns
                ],
            }
            for t in self.tables.values()
        ]


@lru_cache
def load_catalog(path: str) -> Catalog:
    return Catalog.from_csv(Path(path))
