"""Connexion à Fabric depuis l'interface : adresse du serveur + identifiant, puis fenêtre Microsoft.

Rien de secret n'est stocké : seulement l'adresse du SQL endpoint, la base et l'identifiant (data/fabric.json).
Le jeton reste dans le pilote Microsoft.

Connexion automatique au lancement (`auto_connect`) : l'adresse vient du dernier branchement du poste, sinon du fichier
d'équipe `equipe.json` (racine du projet : serveur et base seulement, écrit au premier branchement réussi et emporté
par « partager.bat »), sinon du .env. L'identifiant est celui de la session Windows (`whoami /upn`). Une collègue
n'a donc rien à saisir : au plus, valider la fenêtre Microsoft.
"""
from __future__ import annotations

import dataclasses
import getpass
import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime
from typing import Any

from ..config import REPO_ROOT
from .access import DataError, FabricSource, MockSource, set_shared

log = logging.getLogger("merlin.fabric")
TEAM_FILE = REPO_ROOT / "equipe.json"
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


def team() -> dict[str, Any]:
    """Réglages d'équipe (serveur et base, rien de personnel ni de secret)."""
    try:
        data = json.loads(TEAM_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("server") else {}
    except (OSError, ValueError):
        return {}


def _os_user() -> str:
    try:
        return getpass.getuser().lower()
    except Exception:  # noqa: BLE001
        return ""


def windows_user() -> str:
    """Identifiant Microsoft de la session Windows (prenom.nom@…), pour préremplir la fenêtre de connexion."""
    if os.name != "nt":
        return ""
    try:
        out = subprocess.run(["whoami", "/upn"], capture_output=True, text=True, timeout=5).stdout.strip()
        return out if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", out) else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def auto_target(state) -> dict[str, str] | None:
    """Où se connecter sans rien demander : dernier branchement du poste, sinon fichier d'équipe, sinon .env."""
    cfg, env = saved(state) or {}, state.settings.fabric
    shared = team()
    server = cfg.get("server") or shared.get("server") or env.server
    if not server:
        return None
    mine = cfg.get("user") if cfg.get("os_user") in (None, _os_user()) else ""  # dossier copié d'un autre poste : pas son identifiant
    return {"server": server, "database": cfg.get("database") or shared.get("database") or env.database,
            "user": mine or windows_user() or env.user}


def auto_connect(state, background: bool = True) -> bool:
    """Branche Fabric au lancement si l'adresse est connue. Jamais bloquant ; l'échec se lit dans le statut."""
    target = auto_target(state)
    if target is None or state.data.mode == "fabric" or _status.get("state") == "connecting":
        return False

    def run() -> None:
        try:
            connect(state, target["server"], target["database"], target["user"], auto=True)
            log.info("Fabric : connecté automatiquement (%s).", target["user"] or "identifiant choisi dans la fenêtre Microsoft")
        except DataError as error:
            log.warning("Fabric : connexion automatique impossible : %s", error)
        except Exception as error:  # noqa: BLE001 - ne doit jamais faire tomber l'app
            _status.update({"state": "error", "error": str(error)[:300] or type(error).__name__})

    _status.update({"state": "connecting", "auto": True, **target})
    if background:
        threading.Thread(target=run, name="fabric-auto", daemon=True).start()
    else:
        run()
    return True


def status(state) -> dict[str, Any]:
    cfg = saved(state) or {}
    env = state.settings.fabric
    return {
        "known": auto_target(state) is not None,
        **_status,
        "mode": state.data.mode,
        "server": _status.get("server") or cfg.get("server") or env.server,
        "database": _status.get("database") or cfg.get("database") or env.database,
        "user": _status.get("user") or cfg.get("user") or env.user,
        "client": env.client,
        "saved": bool(cfg),
    }


def connect(state, server: str, database: str, user: str, auto: bool = False) -> dict[str, Any]:
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
        _status.update({"state": "connecting", "server": server, "database": settings.database, "user": settings.user, "auto": auto})
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
            json.dumps({"server": server, "database": settings.database, "user": settings.user, "os_user": _os_user()}, indent=2),
            encoding="utf-8",
        )
        if team().get("server") != server or team().get("database") != settings.database:
            try:  # réglages d'équipe : les collègues n'auront rien à saisir
                TEAM_FILE.write_text(json.dumps({"server": server, "database": settings.database}, indent=2), encoding="utf-8")
            except OSError:
                pass
    return status(state)


def disconnect(state) -> dict[str, Any]:
    with _lock:
        state.data.source = MockSource(state.catalog, state.settings)
        set_shared(state.data)
        state.jobs.data_mode = "mock"
        _status.clear()
        _status["state"] = "disconnected"
    return status(state)
