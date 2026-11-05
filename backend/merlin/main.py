"""Point d'entrée FastAPI : `uvicorn merlin.main:app`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import atelier, contacts, core, documents, fundshop, mergecodes, omni, precedents, qvidian, rfi
from .atelier.store import AtelierStore
from .config import get_settings
from .data.access import DataError, build_data_access, resolve_mode, set_shared
from .db import Database, now_iso
from .jobs.manager import JobManager
from .plugins.registry import PluginRegistry
from .scheduler import MerlinScheduler
from .seed import seed_demo_history
from .state import AppState, get_state, set_state
from .suivi import build_suivi_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("merlin")


def create_state() -> AppState:
    settings = get_settings()
    mode = resolve_mode(settings)
    data = build_data_access(mode, settings)
    set_shared(data)
    registry = PluginRegistry(settings.automations_dir, data.catalog).discover()
    db = Database(settings.db_path)
    jobs = JobManager(settings, db, mode)
    state_holder: dict[str, AppState] = {}
    scheduler = MerlinScheduler(db, settings.timezone, lambda sch: state_holder["s"].launch_schedule(sch))
    state = AppState(settings, data.catalog, data, registry, db, jobs, scheduler, AtelierStore(settings.atelier_dir), now_iso())
    state_holder["s"] = state
    if mode == "mock" and settings.seed_demo_history:
        seeded = seed_demo_history(db, [(p.id, p.manifest.name, p.manifest.estimated_minutes_saved) for p in registry.all()])
        if seeded:
            log.info("Historique de démonstration : %d exécutions fictives ajoutées.", seeded)
    return state


def _warm_qvidian(state) -> None:
    """Qvidian prêt avant le premier clic : connexion par la clé d'API du .env (sans SSO), instantané, index de recherche
    et liens avec les anciens RFI préparés en arrière-plan. Jamais bloquant, jamais en test (MERLIN_WARMUP=0)."""
    import os

    if os.environ.get("MERLIN_WARMUP", "1") == "0" or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from .qvidian.service import get_service

        get_service(state.settings.qvidian, state.settings.data_dir).warmup()
    except Exception as error:  # noqa: BLE001
        log.warning("Préparation Qvidian ignorée : %s", error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = create_state()
    set_state(state)
    state.scheduler.start()
    _warm_qvidian(state)
    log.info("RFP pas envie de travailler : prêt — mode données : %s — %d automatisation(s)", state.data.mode, len(state.registry.plugins))
    yield
    state.scheduler.shutdown()
    state.jobs.shutdown()


app = FastAPI(title="RFP pas envie de travailler", version="1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # carte des erreurs, recherche : JSON 5 à 10 × plus léger (SSE non compressé)
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(core.router)
app.include_router(atelier.router)
app.include_router(rfi.router)
app.include_router(precedents.router)
app.include_router(documents.router)
app.include_router(fundshop.router)
app.include_router(omni.router)
app.include_router(mergecodes.router)
app.include_router(qvidian.router)
app.include_router(contacts.router)

_suivi = build_suivi_app(get_settings().data_dir)
if _suivi is not None:
    app.mount("/suivi", _suivi, name="suivi")


@app.exception_handler(DataError)
async def data_error_handler(_: Request, error: DataError):
    return JSONResponse(status_code=502, content={"detail": {"message": str(error), "hint": error.hint}})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, error: RequestValidationError):
    fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in error.errors())
    return JSONResponse(status_code=422, content={"detail": {"message": "Requête invalide.", "hint": f"Champs concernés : {fields}"}})


@app.exception_handler(HTTPException)
async def http_handler(_: Request, error: HTTPException):
    detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail), "hint": ""}
    return JSONResponse(status_code=error.status_code, content={"detail": detail})


# ---------------------------------------------------------------- frontend compilé (facultatif)
dist = get_settings().frontend_dist
if (dist / "index.html").exists():
    class _Immutable(StaticFiles):
        """Fichiers de /assets nommés par leur empreinte : le navigateur les garde un an, l'app se rouvre sans les relire."""

        async def get_response(self, path, scope):  # type: ignore[override]
            response = await super().get_response(path, scope)
            if response.status_code == 200:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

    app.mount("/assets", _Immutable(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(("api/", "suivi/")):
            raise HTTPException(404, {"message": "Route API inconnue.", "hint": ""})
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})  # toujours la dernière version du front


__all__ = ["app", "get_state"]
