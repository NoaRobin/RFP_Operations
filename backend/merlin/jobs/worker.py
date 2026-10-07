"""Point d'entrée exécuté DANS le processus enfant d'un job.

Le processus parent ne partage rien avec l'enfant hormis une file de messages :
un plantage, une fuite mémoire ou une boucle infinie dans une automatisation
n'emporte jamais le serveur Merlin.
"""
from __future__ import annotations

import importlib.util
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from ..data.access import CatalogViolation, DataError, build_data_access
from ..plugins.context import BrowserNotAvailable, RunContext, _now
from ..plugins.fabric_type import DEFAULT_STEPS, EmptyResult, run_fabric
from ..plugins.manifest import Manifest


def _load_python_plugin(folder: Path, job_id: str):
    module_name = f"merlin_plugin_{folder.name}_{job_id}"
    spec = importlib.util.spec_from_file_location(module_name, folder / "run.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"run.py introuvable dans {folder}")
    sys.path.insert(0, str(folder))  # permet les modules utilitaires dans le dossier du plugin
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def explain(error: BaseException) -> tuple[str, str]:
    """Message utile + piste d'action. (La blague est ajoutée côté interface.)"""
    if isinstance(error, CatalogViolation):
        return str(error), f"{error.hint}. Corrigez la requête en vous référant à catalog/fabric_catalog.md."
    if isinstance(error, DataError):
        return str(error), error.hint or "Réessayez dans quelques minutes ; si cela persiste, vérifiez la connexion Fabric."
    if isinstance(error, BrowserNotAvailable):
        return str(error), "Ce sort nécessite le navigateur automatisé, qui n'est pas encore activé."
    if isinstance(error, EmptyResult):
        return str(error), "Vérifiez la date et les filtres choisis : il n'existe peut-être pas encore de données pour cette période."
    if isinstance(error, FileNotFoundError):
        return f"Fichier introuvable : {error.filename or error}", "Le fichier a peut-être été déplacé ou renommé."
    if isinstance(error, PermissionError):
        return "Accès refusé à un fichier.", "Fermez le fichier s'il est ouvert dans Excel, puis relancez."
    return f"{type(error).__name__} : {error}", "Consultez le journal ci-dessous ; transmettez-le à l'équipe si besoin."


def child_main(spec: dict[str, Any], queue) -> None:
    job_id = spec["job_id"]
    started = time.perf_counter()

    seq = 0

    def emit(event: dict[str, Any]) -> None:
        nonlocal seq
        seq += 1
        queue.put({**event, "seq": seq})

    emit({"type": "status", "status": "running", "ts": _now()})
    try:
        data = build_data_access(spec["data_mode"])
        steps = spec.get("steps") or []
        ctx = RunContext(
            job_id=job_id,
            user=spec["user"],
            params=spec["params"],
            output_dir=Path(spec["output_dir"]),
            data=data,
            emit=emit,
            steps=steps,
        )
        emit({"type": "plan", "steps": steps, "ts": _now()})
        if spec["target_type"] == "automation":
            folder = Path(spec["plugin_path"])
            manifest = Manifest.model_validate(spec["manifest"])
            if manifest.type == "fabric":
                run_fabric(ctx, manifest, spec["query"], spec["params"])
            else:
                module = _load_python_plugin(folder, job_id)
                module.run(ctx, **spec["params"])
        elif spec["target_type"] == "recipe":
            from ..atelier.engine import run_recipe

            run_recipe(ctx, spec["recipe"], Path(spec["workbook_dir"]))
        else:
            raise ValueError(f"Type de cible inconnu : {spec['target_type']}")
        emit({
            "type": "result", "status": "success", "summary": ctx.summary,
            "duration_ms": int((time.perf_counter() - started) * 1000), "ts": _now(),
        })
    except BaseException as error:  # noqa: BLE001 — on veut tout remonter proprement
        message, hint = explain(error)
        emit({"type": "log", "level": "error", "message": message, "ts": _now()})
        emit({"type": "log", "level": "debug", "message": traceback.format_exc(limit=6), "ts": _now()})
        emit({
            "type": "result", "status": "error", "error": message, "hint": hint,
            "duration_ms": int((time.perf_counter() - started) * 1000), "ts": _now(),
        })


__all__ = ["child_main", "DEFAULT_STEPS"]
