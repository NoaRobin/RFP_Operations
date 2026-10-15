"""Connexion à Fabric depuis l'interface : adresse du serveur + identifiant, puis fenêtre Microsoft.

Rien de secret n'est stocké : seulement l'adresse du SQL endpoint, la base et l'identifiant (data/fabric.json),
pour proposer « Se reconnecter » au prochain lancement. Le jeton reste dans le pilote Microsoft.
"""
from __future__ import annotations

import dataclasses
import json
import re
import threading
from datetime import datetime
from typing import Any

from .access import DataError, FabricSource, MockSource, set_shared

_lock = threading.Lock()
_status: dict[str, Any] = {"state": "disconnected"}


def _config_file(state):
    return state.settings.data_dir / "fabric.json"


def clean_server(raw: str) -> str:
    """Accepte une adresse nue, « tcp:…,1433 » ou une chaîne de connexion copiée depuis VS Code / Fabric."""
    value = (raw or "").strip()
    match = re.search(r"(?:server|data source)\s*=\s*([^;]+)", value, re.I)
    if match:
        value = match.group(1)
    value = re.sub(r"^tcp:", "", value.strip(), flags=re.I)
    value = re.sub(r"^https?://", "", value).strip().strip("/")
    return value


def saved(state) -> dict[str, Any] | None:
    path = _config_file(state)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status(state) -> dict[str, Any]:
    cfg = saved(state) or {}
    env = state.settings.fabric
    return {
        **_status,
        "mode": state.data.mode,
        "server": _status.get("server") or cfg.get("server") or env.server,
        "database": _status.get("database") or cfg.get("database") or env.database,
        "user": _status.get("user") or cfg.get("user") or env.user,
        "client": env.client,
        "saved": bool(cfg),
    }


def connect(state, server: str, database: str, user: str) -> dict[str, Any]:
    server = clean_server(server)
    if not server or "." not in server:
        raise DataError(
            "Adresse du serveur manquante ou incomplète.",
            "Dans Fabric : Lakehouse › SQL analytics endpoint › copier la chaîne de connexion "
            "(…datawarehouse.fabric.microsoft.com). C'est la même que dans VS Code.",
        )
    settings = dataclasses.replace(
        state.settings.fabric, server=server, database=(database or "LKH_RFPTeam_Bronze").strip(),
        user=(user or "").strip(), auth="ActiveDirectoryInteractive",
    )
    with _lock:
        _status.update({"state": "connecting", "server": server, "database": settings.database, "user": settings.user})
        source = FabricSource(settings)
        try:
            source.query("SELECT 1 AS ok", {})  # ← ici s'ouvre la fenêtre Microsoft
        except DataError as error:
            _status.update({"state": "error", "error": str(error), "hint": error.hint})
            raise
        state.data.source = source
        set_shared(state.data)
        state.jobs.data_mode = "fabric"
        _status.update({"state": "connected", "since": datetime.now().isoformat(timespec="seconds"), "error": None})
        _config_file(state).write_text(
            json.dumps({"server": server, "database": settings.database, "user": settings.user}, indent=2),
            encoding="utf-8",
        )
    return status(state)


def disconnect(state) -> dict[str, Any]:
    with _lock:
        state.data.source = MockSource(state.catalog, state.settings)
        set_shared(state.data)
        state.jobs.data_mode = "mock"
        _status.clear()
        _status["state"] = "disconnected"
    return status(state)
