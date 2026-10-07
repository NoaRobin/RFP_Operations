"""Conteneur des services partagés par l'API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .atelier.store import AtelierStore
from .config import Settings
from .data.access import DataAccess
from .data.catalog import Catalog
from .db import Database
from .jobs.manager import JobManager
from .plugins.registry import PluginRegistry
from .scheduler import MerlinScheduler


@dataclass
class AppState:
    settings: Settings
    catalog: Catalog
    data: DataAccess
    registry: PluginRegistry
    db: Database
    jobs: JobManager
    scheduler: MerlinScheduler
    store: AtelierStore
    started_at: str

    def launch_schedule(self, schedule: dict[str, Any]) -> None:
        """Appelé par le planificateur."""
        user = f"Planificateur ({schedule['created_by']})"
        if schedule["target_type"] == "automation":
            plugin = self.registry.get(schedule["target_id"])
            if plugin and plugin.healthy:
                from .plugins.registry import coerce_params

                self.jobs.submit_automation(plugin, coerce_params(plugin.manifest.params, schedule["params"] or {}), user, "schedule")
        elif schedule["target_type"] == "recipe":
            recipe = self.store.get_recipe(schedule["target_id"])
            recipe = {**recipe, "as_of": None}  # une recette planifiée prend toujours la date du jour
            self.jobs.submit_recipe(recipe, self.store.workbook_dir(recipe["workbook_id"]), user, "schedule")


_state: AppState | None = None


def set_state(state: AppState) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("Merlin n'est pas initialisé.")
    return _state
