"""Orchestration des jobs : un processus par exécution, statut et logs diffusés en temps réel."""
from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import queue as queue_mod
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import Database, now_iso
from ..plugins.fabric_type import DEFAULT_STEPS
from ..plugins.registry import Plugin
from .worker import child_main

log = logging.getLogger("merlin.jobs")
_CTX = mp.get_context("spawn")  # identique sous Windows, macOS et Linux


class _ThreadJob(threading.Thread):
    """Exécution dans un fil du serveur : partage la connexion Fabric (une seule fenêtre Microsoft).

    `terminate` ne peut pas tuer un fil : l'annulation est signalée et les événements suivants sont ignorés.
    """

    def terminate(self) -> None:  # interface identique à multiprocessing.Process
        pass


class EventBus:
    """Diffusion thread-safe des événements vers les abonnés SSE (asyncio)."""

    def __init__(self) -> None:
        self._subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.setdefault(channel, set()).add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subs.get(channel, set())
            for item in list(subs):
                if item[1] is q:
                    subs.discard(item)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._subs.get(channel, set()))
        for loop, q in targets:
            def _put(q=q):
                if not q.full():
                    q.put_nowait(event)
            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                pass  # boucle fermée


@dataclass
class ActiveJob:
    run_id: str
    spec: dict[str, Any]
    process: Any = None
    queue: Any = None
    started: float = field(default_factory=time.monotonic)
    cancelled: bool = False


class JobManager:
    def __init__(self, settings: Settings, db: Database, data_mode: str):
        self.settings = settings
        self.db = db
        self.data_mode = data_mode
        self.bus = EventBus()
        self._active: dict[str, ActiveJob] = {}
        self._pending: deque[ActiveJob] = deque()
        self._lock = threading.Lock()
        # Un redémarrage interrompt les jobs en cours : on le dit honnêtement.
        for run in db.list_runs(limit=500, status="running") + db.list_runs(limit=500, status="queued"):
            db.update_run(run["id"], status="error", error="Le serveur a redémarré pendant l'exécution.",
                          error_hint="Relancez l'automatisation.", finished_at=now_iso())

    # ------------------------------------------------------------- soumission
    def submit_automation(self, plugin: Plugin, params: dict[str, Any], user: str, trigger: str = "manual") -> dict[str, Any]:
        m = plugin.manifest
        steps = m.steps or (DEFAULT_STEPS if m.type == "fabric" else [])
        spec = {
            "target_type": "automation", "plugin_path": str(plugin.path), "manifest": m.model_dump(),
            "query": plugin.query, "steps": steps,
        }
        return self._submit("automation", m.id, m.name, params, user, trigger, m.estimated_minutes_saved, spec)

    def submit_recipe(self, recipe: dict[str, Any], workbook_dir: Path, user: str, trigger: str = "manual") -> dict[str, Any]:
        from ..atelier.engine import RECIPE_STEPS

        spec = {"target_type": "recipe", "recipe": recipe, "workbook_dir": str(workbook_dir), "steps": RECIPE_STEPS}
        minutes = max(5, 2 * len(recipe.get("mappings", [])))
        params = {"as_of": recipe.get("as_of"), "workbook": recipe.get("workbook_id")}
        return self._submit("recipe", recipe.get("id") or "atelier", recipe.get("name") or "Recette de l'Atelier",
                            params, user, trigger, minutes, spec)

    def _submit(self, target_type: str, target_id: str, name: str, params: dict[str, Any], user: str,
                trigger: str, minutes: int, spec: dict[str, Any]) -> dict[str, Any]:
        run = self.db.create_run(
            target_type=target_type, target_id=target_id, target_name=name, user=user, trigger=trigger,
            params=params, minutes_saved=minutes, data_mode=self.data_mode,
        )
        spec.update({
            "job_id": run["id"], "params": params, "user": user, "data_mode": self.data_mode,
            "output_dir": str(self.settings.runs_dir / run["id"]),
        })
        job = ActiveJob(run["id"], spec)
        with self._lock:
            self._pending.append(job)
        self.bus.publish("*", {"type": "run", "run": run})
        self._drain()
        return run

    def _drain(self) -> None:
        with self._lock:
            while self._pending and len(self._active) < self.settings.max_parallel_jobs:
                job = self._pending.popleft()
                self._active[job.run_id] = job
                self._start(job)

    def _start(self, job: ActiveJob) -> None:
        if self.settings.job_executor == "process":
            job.queue = _CTX.Queue()
            job.process = _CTX.Process(target=child_main, args=(job.spec, job.queue), daemon=True, name=f"merlin-{job.run_id}")
        else:
            job.queue = queue_mod.Queue()
            job.process = _ThreadJob(target=child_main, args=(job.spec, job.queue), daemon=True, name=f"merlin-{job.run_id}")
        job.process.start()
        job.started = time.monotonic()
        self.db.update_run(job.run_id, status="running", started_at=now_iso())
        threading.Thread(target=self._pump, args=(job,), daemon=True, name=f"pump-{job.run_id}").start()

    # ------------------------------------------------------------- suivi
    def _handle(self, job: ActiveJob, event: dict[str, Any]) -> bool:
        """Retourne True si l'événement est terminal."""
        run_id = job.run_id
        etype = event.get("type")
        if etype != "progress" or event.get("message"):
            self.db.add_event(run_id, event)
        if etype == "output":
            run = self.db.get_run(run_id) or {}
            outputs = (run.get("outputs") or []) + [{k: event[k] for k in ("name", "kind", "label", "size")}]
            self.db.update_run(run_id, outputs=outputs)
        elif etype == "summary":
            self.db.update_run(run_id, summary=event.get("text"))
        elif etype == "result":
            self.db.update_run(
                run_id, status=event["status"], finished_at=now_iso(), duration_ms=event.get("duration_ms"),
                error=event.get("error"), error_hint=event.get("hint"),
                **({"summary": event["summary"]} if event.get("summary") else {}),
            )
        self.bus.publish(run_id, event)
        if etype in {"result", "status"}:
            self.bus.publish("*", {"type": "run", "run": self.db.get_run(run_id)})
        return etype == "result"

    def _pump(self, job: ActiveJob) -> None:
        finished = False
        try:
            while True:
                try:
                    event = job.queue.get(timeout=0.4)
                    if self._handle(job, event):
                        finished = True
                        break
                except queue_mod.Empty:
                    if job.cancelled:
                        break
                    if not job.process.is_alive():
                        # vider ce qu'il reste puis conclure
                        try:
                            while True:
                                if self._handle(job, job.queue.get_nowait()):
                                    finished = True
                                    break
                        except queue_mod.Empty:
                            pass
                        break
                    if time.monotonic() - job.started > self.settings.job_timeout:
                        job.process.terminate()
                        self._handle(job, {
                            "type": "result", "status": "error",
                            "error": f"Délai dépassé ({self.settings.job_timeout // 60} min).",
                            "hint": "L'exécution a été interrompue. Réduisez le périmètre ou augmentez MERLIN_JOB_TIMEOUT.",
                            "ts": now_iso(),
                        })
                        finished = True
                        break
            if not finished and not job.cancelled:
                self._handle(job, {
                    "type": "result", "status": "error", "error": "Le processus d'exécution s'est arrêté brutalement.",
                    "hint": "Relancez ; si cela se reproduit, consultez le journal du serveur.", "ts": now_iso(),
                })
        except Exception:  # pragma: no cover — filet de sécurité
            log.exception("Erreur de suivi du job %s", job.run_id)
        finally:
            job.process.join(timeout=2)
            with self._lock:
                self._active.pop(job.run_id, None)
            self._drain()

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            pending = next((j for j in self._pending if j.run_id == run_id), None)
            if pending:
                self._pending.remove(pending)
            job = self._active.get(run_id)
        if pending:
            self._finish_cancel(run_id)
            return True
        if not job:
            return False
        job.cancelled = True
        job.process.terminate()
        self._finish_cancel(run_id)
        return True

    def _finish_cancel(self, run_id: str) -> None:
        event = {"type": "result", "status": "cancelled", "error": "Exécution annulée à la demande.", "ts": now_iso()}
        self.db.add_event(run_id, event)
        self.db.update_run(run_id, status="cancelled", finished_at=now_iso(), error=event["error"])
        self.bus.publish(run_id, event)
        self.bus.publish("*", {"type": "run", "run": self.db.get_run(run_id)})

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._active) + [j.run_id for j in self._pending]

    def shutdown(self) -> None:
        with self._lock:
            jobs = list(self._active.values())
        for job in jobs:
            if job.process and job.process.is_alive():
                job.process.terminate()
