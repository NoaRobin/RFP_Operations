"""API : santé, automatisations, exécutions (SSE), tableau de bord, planification, suggestions."""
from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..data.access import DataError
from ..db import new_id, now_iso
from ..plugins.registry import ParamError, coerce_params
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api")
TERMINAL = {"success", "error", "cancelled"}


# ------------------------------------------------------------------ santé
@router.get("/health")
def health(s: AppState = Depends(state)) -> dict[str, Any]:
    return {
        "status": "ok", "data_mode": s.data.mode, "started_at": s.started_at,
        "automations": len(s.registry.plugins), "broken": len(s.registry.broken),
        "fabric_configured": s.settings.fabric.configured,
    }


@router.get("/catalog")
def catalog(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return s.catalog.to_dict()


# ------------------------------------------------------------------ automatisations
def _stats_by_target(s: AppState) -> dict[str, dict[str, Any]]:
    rows = s.db.all(
        "SELECT target_id, COUNT(*) AS runs, SUM(status='success') AS ok, MAX(created_at) AS last_at "
        "FROM runs GROUP BY target_id"
    )
    return {r["target_id"]: r for r in rows}


@router.get("/automations")
def list_automations(s: AppState = Depends(state)) -> dict[str, Any]:
    stats = _stats_by_target(s)
    items = []
    for plugin in s.registry.all():
        data = plugin.to_dict()
        data.pop("query", None)
        st = stats.get(plugin.id, {})
        data["stats"] = {"runs": st.get("runs", 0), "success": st.get("ok", 0) or 0, "last_at": st.get("last_at")}
        items.append(data)
    return {"automations": items, "broken": [b.__dict__ for b in s.registry.broken]}


@router.get("/automations/{automation_id}")
def get_automation(automation_id: str, s: AppState = Depends(state)) -> dict[str, Any]:
    plugin = s.registry.get(automation_id)
    if not plugin:
        raise not_found("Ce sort n'existe pas (ou plus).")
    data = plugin.to_dict()
    data["recent_runs"] = s.db.list_runs(limit=8, target_id=automation_id)
    return data


@router.get("/automations/{automation_id}/options/{param}")
def param_options(automation_id: str, param: str, s: AppState = Depends(state)) -> list[dict[str, Any]]:
    plugin = s.registry.get(automation_id)
    spec = next((p for p in plugin.manifest.params if p.name == param), None) if plugin else None
    if not spec:
        raise not_found("Paramètre inconnu.")
    if spec.options:
        return [o.model_dump() for o in spec.options]
    if not spec.options_query:
        return []
    try:
        frame = s.data.query(spec.options_query)
    except DataError as error:
        raise bad_request(str(error), error.hint) from error
    return [{"value": v, "label": str(l)} for v, l in zip(frame["value"], frame["label"])]


class RunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/automations/{automation_id}/run")
def run_automation(automation_id: str, body: RunRequest, s: AppState = Depends(state), user: str = Depends(current_user)):
    plugin = s.registry.get(automation_id)
    if not plugin:
        raise not_found("Ce sort n'existe pas (ou plus).")
    if not plugin.healthy:
        raise bad_request("Ce sort est abîmé et ne peut pas être lancé.", " ; ".join(plugin.problems))
    try:
        params = coerce_params(plugin.manifest.params, body.params)
    except ParamError as error:
        raise bad_request(str(error), "Corrigez les champs signalés puis relancez.") from error
    return s.jobs.submit_automation(plugin, params, user)


# ------------------------------------------------------------------ exécutions
@router.get("/runs")
def list_runs(limit: int = Query(50, le=500), target_id: str | None = None, status: str | None = None,
              s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return s.db.list_runs(limit, target_id, status)


@router.get("/runs/{run_id}")
def get_run(run_id: str, s: AppState = Depends(state)) -> dict[str, Any]:
    run = s.db.get_run(run_id)
    if not run:
        raise not_found("Aucune trace de cette exécution.")
    return {**run, "events": s.db.events(run_id)}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, s: AppState = Depends(state)) -> dict[str, Any]:
    if not s.jobs.cancel(run_id):
        raise bad_request("Ce sort n'est plus en cours.", "Il s'est peut-être déjà terminé.")
    return {"ok": True}


@router.get("/runs/{run_id}/files/{filename}")
def download(run_id: str, filename: str, s: AppState = Depends(state)):
    run = s.db.get_run(run_id)
    if not run or filename not in {o["name"] for o in run.get("outputs") or []}:
        raise not_found("Fichier introuvable.")
    path = (s.settings.runs_dir / run_id / filename).resolve()
    if s.settings.runs_dir.resolve() not in path.parents or not path.exists():
        raise not_found("Fichier introuvable.")
    return FileResponse(path, filename=filename)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, s: AppState = Depends(state)):
    run = s.db.get_run(run_id)
    if not run:
        raise not_found("Aucune trace de cette exécution.")
    queue = s.jobs.bus.subscribe(run_id)

    async def stream():
        try:
            yield {"event": "run", "data": json.dumps(s.db.get_run(run_id), default=str)}
            last_seq = 0
            done = False
            for event in s.db.events(run_id):
                last_seq = max(last_seq, event.get("seq") or 0)
                done = done or event.get("type") == "result"
                yield {"event": "message", "data": json.dumps(event, default=str)}
            current = s.db.get_run(run_id)
            if done or (current and current["status"] in TERMINAL):
                yield {"event": "end", "data": json.dumps(current, default=str)}
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event.get("seq") and event["seq"] <= last_seq:
                    continue
                yield {"event": "message", "data": json.dumps(event, default=str)}
                if event.get("type") == "result":
                    yield {"event": "end", "data": json.dumps(s.db.get_run(run_id), default=str)}
                    return
        finally:
            s.jobs.bus.unsubscribe(run_id, queue)

    return EventSourceResponse(stream())


@router.get("/stream")
async def global_stream(request: Request, s: AppState = Depends(state)):
    queue = s.jobs.bus.subscribe("*")

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "message", "data": json.dumps(event, default=str)}
        finally:
            s.jobs.bus.unsubscribe("*", queue)

    return EventSourceResponse(stream())


# ------------------------------------------------------------------ tableau de bord
@router.get("/dashboard")
def dashboard(s: AppState = Depends(state)) -> dict[str, Any]:
    runs = s.db.all("SELECT * FROM runs WHERE created_at >= ? ORDER BY created_at DESC",
                    ((datetime.now() - timedelta(days=90)).isoformat(),))
    today = date.today()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    month_start = today.replace(day=1).isoformat()
    ok = [r for r in runs if r["status"] == "success"]
    finished = [r for r in runs if r["status"] in TERMINAL]

    activity = []
    by_day: dict[str, Counter] = defaultdict(Counter)
    for r in runs:
        by_day[r["created_at"][:10]][r["status"]] += 1
    for offset in range(13, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        activity.append({"day": day, "success": by_day[day]["success"], "error": by_day[day]["error"] + by_day[day]["cancelled"]})

    team: dict[str, dict[str, Any]] = {}
    for r in runs:
        if r["user"].startswith("Planificateur"):
            continue
        t = team.setdefault(r["user"], {"user": r["user"], "runs": 0, "minutes_saved": 0, "last_at": r["created_at"]})
        t["runs"] += 1
        t["minutes_saved"] += r["minutes_saved"] if r["status"] == "success" else 0

    top = Counter((r["target_id"], r["target_name"]) for r in runs)
    alerts: list[dict[str, Any]] = []
    if s.data.mode == "mock":
        alerts.append({"level": "info", "code": "mock_mode", "title": "Mode démonstration",
                       "detail": "Fabric n'est pas configuré ou injoignable : les données affichées sont fictives."})
    recent_errors = [r for r in runs if r["status"] == "error" and r["created_at"] >= (datetime.now() - timedelta(days=2)).isoformat()]
    if recent_errors:
        alerts.append({"level": "error", "code": "recent_errors", "title": f"{len(recent_errors)} sort(s) en échec ces 48 h",
                       "detail": recent_errors[0]["error"] or "", "run_id": recent_errors[0]["id"]})
    for broken in s.registry.broken:
        alerts.append({"level": "warning", "code": "broken_plugin", "title": f"Manifest illisible : {broken.folder}", "detail": " ; ".join(broken.problems)})
    for plugin in s.registry.all():
        if not plugin.healthy:
            alerts.append({"level": "warning", "code": "unhealthy_plugin", "title": f"Sort abîmé : {plugin.manifest.name}", "detail": " ; ".join(plugin.problems)})

    schedules = [x for x in s.scheduler.list() if x["enabled"] and x["next_run"]]
    schedules.sort(key=lambda x: x["next_run"])
    active = s.jobs.active_ids()
    return {
        "counters": {
            "spells_total": s.db.scalar("SELECT COUNT(*) FROM runs") or 0,
            "spells_week": sum(1 for r in runs if r["created_at"] >= week_ago),
            "success_rate": round(len(ok) / len(finished), 3) if finished else None,
            "minutes_saved_total": s.db.scalar("SELECT COALESCE(SUM(minutes_saved),0) FROM runs WHERE status='success'") or 0,
            "minutes_saved_month": sum(r["minutes_saved"] for r in ok if r["created_at"] >= month_start),
            "running": len(active),
        },
        "running": [s.db.get_run(i) for i in active],
        "scheduled": schedules[:8],
        "activity": activity,
        "team": sorted(team.values(), key=lambda t: t["minutes_saved"], reverse=True)[:8],
        "recent": runs[:12],
        "top": [{"id": k[0], "name": k[1], "count": v} for k, v in top.most_common(5)],
        "alerts": alerts,
        "data_mode": s.data.mode,
        "has_demo_history": any(r.get("demo") for r in runs),
    }


@router.delete("/demo-history")
def delete_demo_history(s: AppState = Depends(state)) -> dict[str, Any]:
    from ..seed import clear_demo_history

    clear_demo_history(s.db)
    return {"ok": True}


# ------------------------------------------------------------------ planification
class ScheduleRequest(BaseModel):
    target_type: str = Field(pattern="^(automation|recipe)$")
    target_id: str
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    frequency: str
    hour: int = Field(8, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    weekday: int | None = Field(None, ge=0, le=6)
    day_of_month: int | None = Field(None, ge=1, le=31)


@router.get("/schedules")
def list_schedules(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return s.scheduler.list()


@router.post("/schedules")
def create_schedule(body: ScheduleRequest, s: AppState = Depends(state), user: str = Depends(current_user)):
    data = body.model_dump()
    if body.target_type == "automation":
        plugin = s.registry.get(body.target_id)
        if not plugin:
            raise not_found("Ce sort n'existe pas.")
        try:
            data["params"] = coerce_params(plugin.manifest.params, body.params)
        except ParamError as error:
            raise bad_request(str(error)) from error
        data["label"] = data["label"] or plugin.manifest.name
    else:
        try:
            recipe = s.store.get_recipe(body.target_id)
        except FileNotFoundError as error:
            raise not_found("Recette introuvable.") from error
        data["label"] = data["label"] or recipe.get("name")
    try:
        return s.scheduler.create(data, user)
    except ValueError as error:
        raise bad_request(str(error)) from error


class ScheduleToggle(BaseModel):
    enabled: bool


@router.patch("/schedules/{schedule_id}")
def toggle_schedule(schedule_id: str, body: ScheduleToggle, s: AppState = Depends(state)):
    result = s.scheduler.set_enabled(schedule_id, body.enabled)
    if not result:
        raise not_found("Planification introuvable.")
    return result


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, s: AppState = Depends(state)):
    s.scheduler.delete(schedule_id)
    return {"ok": True}


# ------------------------------------------------------------------ suggestions
class SuggestionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    description: str = Field("", max_length=4000)
    urgency: str = Field("normal", pattern="^(normal|important|vital)$")


@router.post("/suggestions")
def create_suggestion(body: SuggestionRequest, s: AppState = Depends(state), user: str = Depends(current_user)):
    record = {"id": new_id("sug"), "user": user, "created_at": now_iso(), **body.model_dump()}
    s.db.execute(
        "INSERT INTO suggestions (id, user, title, description, urgency, created_at) "
        "VALUES (:id, :user, :title, :description, :urgency, :created_at)", record,
    )
    return record


@router.get("/suggestions")
def list_suggestions(s: AppState = Depends(state)):
    return s.db.all("SELECT * FROM suggestions ORDER BY created_at DESC LIMIT 200")
