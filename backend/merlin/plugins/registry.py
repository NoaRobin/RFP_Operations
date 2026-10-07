"""Découverte des automatisations : chaque dossier de `automations/` contenant un manifest."""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..data.catalog import Catalog
from .manifest import Manifest, ParamSpec

log = logging.getLogger("merlin.plugins")


@dataclass
class Plugin:
    manifest: Manifest
    path: Path
    query: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def healthy(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        data = self.manifest.model_dump()
        data["healthy"] = self.healthy
        data["problems"] = self.problems
        data["query"] = self.query
        return data


@dataclass
class BrokenPlugin:
    folder: str
    problems: list[str]


class PluginRegistry:
    def __init__(self, root: Path, catalog: Catalog):
        self.root = root
        self.catalog = catalog
        self.plugins: dict[str, Plugin] = {}
        self.broken: list[BrokenPlugin] = []

    def discover(self) -> "PluginRegistry":
        self.plugins.clear()
        self.broken.clear()
        if not self.root.exists():
            log.warning("Dossier d'automatisations introuvable : %s", self.root)
            return self
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            manifest_path = folder / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                manifest = Manifest.model_validate(raw)
            except (yaml.YAMLError, ValidationError) as error:
                self.broken.append(BrokenPlugin(folder.name, [f"manifest.yaml invalide : {error}"]))
                continue
            plugin = Plugin(manifest, folder)
            self._inspect(plugin)
            if manifest.id in self.plugins:
                self.broken.append(BrokenPlugin(folder.name, [f"Identifiant en double : {manifest.id}"]))
                continue
            self.plugins[manifest.id] = plugin
            log.info("Sort découvert : %s (%s)%s", manifest.id, manifest.type, "" if plugin.healthy else " — ABÎMÉ")
        return self

    def _inspect(self, plugin: Plugin) -> None:
        m = plugin.manifest
        if m.type == "fabric":
            spec = m.fabric
            query = spec.query
            if not query and spec.query_file:
                query_path = plugin.path / spec.query_file
                if query_path.exists():
                    query = query_path.read_text(encoding="utf-8")
            if not query:
                plugin.problems.append("Aucune requête : renseignez fabric.query ou un fichier query.sql.")
                return
            plugin.query = query
            plugin.problems += self.catalog.validate_sql(query)
            from ..data.access import used_params  # import local pour éviter un cycle

            declared = {p.name for p in m.params}
            for missing in sorted(used_params(query) - declared):
                plugin.problems.append(f"La requête utilise :{missing} qui n'est pas déclaré dans params.")
        for param in m.params:
            if param.options_query:
                plugin.problems += [f"[{param.name}] {e}" for e in self.catalog.validate_sql(param.options_query)]
        if m.type == "python":
            run_file = plugin.path / "run.py"
            if not run_file.exists():
                plugin.problems.append("run.py manquant.")
                return
            try:
                tree = ast.parse(run_file.read_text(encoding="utf-8"))
            except SyntaxError as error:
                plugin.problems.append(f"run.py ne compile pas : {error}")
                return
            if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
                plugin.problems.append("run.py doit exposer une fonction run(ctx, **params).")

    def get(self, plugin_id: str) -> Plugin | None:
        return self.plugins.get(plugin_id)

    def all(self) -> list[Plugin]:
        return list(self.plugins.values())


# --------------------------------------------------------------------- paramètres
class ParamError(ValueError):
    pass


def coerce_params(specs: list[ParamSpec], raw: dict[str, Any]) -> dict[str, Any]:
    """Valide et convertit les paramètres reçus de l'UI selon le manifest."""
    result: dict[str, Any] = {}
    errors: list[str] = []
    for spec in specs:
        value = raw.get(spec.name, spec.default)
        if value in ("", None, []):
            if spec.default == "today" and spec.type == "date":
                value = date.today().isoformat()
            elif spec.required:
                errors.append(f"« {spec.label} » est obligatoire.")
                continue
            else:
                result[spec.name] = None
                continue
        try:
            if spec.type == "date":
                value = date.today().isoformat() if value == "today" else date.fromisoformat(str(value)[:10]).isoformat()
            elif spec.type == "integer":
                value = int(value)
            elif spec.type == "number":
                value = float(value)
            elif spec.type == "boolean":
                value = value if isinstance(value, bool) else str(value).lower() in {"1", "true", "oui", "yes"}
            elif spec.type == "isin":
                value = str(value).strip().upper()
                if len(value) != 12 or not value[:2].isalpha() or not value.isalnum():
                    raise ValueError("un ISIN fait 12 caractères (2 lettres + 10 caractères)")
            elif spec.type == "multiselect":
                value = list(value) if isinstance(value, (list, tuple)) else [v.strip() for v in str(value).split(",") if v.strip()]
            else:
                value = str(value)
        except (TypeError, ValueError) as error:
            errors.append(f"« {spec.label} » : valeur invalide ({error}).")
            continue
        if spec.type in {"integer", "number"}:
            if spec.min is not None and value < spec.min:
                errors.append(f"« {spec.label} » doit être ≥ {spec.min:g}.")
            if spec.max is not None and value > spec.max:
                errors.append(f"« {spec.label} » doit être ≤ {spec.max:g}.")
        if spec.type == "select" and spec.options and value not in {o.value for o in spec.options}:
            errors.append(f"« {spec.label} » : choix inconnu.")
        result[spec.name] = value
    if errors:
        raise ParamError(" ".join(errors))
    return result
