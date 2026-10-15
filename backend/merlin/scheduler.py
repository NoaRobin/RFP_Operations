"""Planification (APScheduler) : à la demande, quotidien, hebdomadaire, mensuel."""
from __future__ import annotations

import logging
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database, new_id, now_iso

log = logging.getLogger("merlin.scheduler")
FREQUENCIES = {"daily", "weekly", "monthly"}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def build_trigger(schedule: dict[str, Any], timezone: str) -> CronTrigger:
    hour, minute = int(schedule.get("hour", 8)), int(schedule.get("minute", 0))
    frequency = schedule["frequency"]
    if frequency == "daily":
        # « Quotidien » = jours ouvrés : personne ne lit un RFP le dimanche (enfin, on espère).
        return CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=timezone)
    if frequency == "weekly":
        return CronTrigger(day_of_week=WEEKDAYS[int(schedule.get("weekday") or 0)], hour=hour, minute=minute, timezone=timezone)
    if frequency == "monthly":
        day = schedule.get("day_of_month") or 1
        return CronTrigger(day="last" if int(day) >= 29 else int(day), hour=hour, minute=minute, timezone=timezone)
    raise ValueError(f"Fréquence inconnue : {frequency}")


def describe(schedule: dict[str, Any]) -> str:
    at = f"{int(schedule.get('hour', 8)):02d}h{int(schedule.get('minute', 0)):02d}"
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    if schedule["frequency"] == "daily":
        return f"Chaque jour ouvré à {at}"
    if schedule["frequency"] == "weekly":
        return f"Chaque {days[int(schedule.get('weekday') or 0)]} à {at}"
    day = int(schedule.get("day_of_month") or 1)
    return f"Le {'dernier jour' if day >= 29 else ('1er' if day == 1 else str(day))} de chaque mois à {at}"


class MerlinScheduler:
    def __init__(self, db: Database, timezone: str, launcher: Callable[[dict[str, Any]], None]):
        self.db = db
        self.timezone = timezone
        self.launcher = launcher
        self.scheduler = BackgroundScheduler(timezone=timezone)

    def start(self) -> None:
        for schedule in self.db.all("SELECT * FROM schedules WHERE enabled = 1"):
            self._register(schedule)
        self.scheduler.start()
        log.info("Planificateur démarré (%d planification(s))", len(self.scheduler.get_jobs()))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _fire(self, schedule_id: str) -> None:
        schedule = self.db.one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        if schedule and schedule["enabled"]:
            try:
                self.launcher(schedule)
            except Exception:  # noqa: BLE001
                log.exception("Échec du lancement planifié %s", schedule_id)

    def _register(self, schedule: dict[str, Any]) -> None:
        self.scheduler.add_job(
            self._fire, build_trigger(schedule, self.timezone), args=[schedule["id"]], id=schedule["id"],
            replace_existing=True, misfire_grace_time=3600, coalesce=True,
        )

    def next_run(self, schedule_id: str) -> str | None:
        job = self.scheduler.get_job(schedule_id)
        return job.next_run_time.isoformat() if job and job.next_run_time else None

    def list(self) -> list[dict[str, Any]]:
        items = self.db.all("SELECT * FROM schedules ORDER BY created_at DESC")
        for item in items:
            item["next_run"] = self.next_run(item["id"]) if item["enabled"] else None
            item["description"] = describe(item)
        return items

    def create(self, data: dict[str, Any], user: str) -> dict[str, Any]:
        if data.get("frequency") not in FREQUENCIES:
            raise ValueError("Fréquence attendue : daily, weekly ou monthly.")
        build_trigger(data, self.timezone)  # valide les heures/jours
        import json

        record = {
            "id": new_id("sch"), "target_type": data["target_type"], "target_id": data["target_id"],
            "label": data.get("label") or data["target_id"], "params": json.dumps(data.get("params") or {}, ensure_ascii=False),
            "frequency": data["frequency"], "hour": int(data.get("hour", 8)), "minute": int(data.get("minute", 0)),
            "weekday": data.get("weekday"), "day_of_month": data.get("day_of_month"), "enabled": 1,
            "created_by": user, "created_at": now_iso(),
        }
        self.db.execute(
            f"INSERT INTO schedules ({', '.join(record)}) VALUES ({', '.join(':' + k for k in record)})", record
        )
        schedule = self.db.one("SELECT * FROM schedules WHERE id = ?", (record["id"],))
        self._register(schedule)
        return {**schedule, "next_run": self.next_run(schedule["id"]), "description": describe(schedule)}

    def set_enabled(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        self.db.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (int(enabled), schedule_id))
        schedule = self.db.one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        if not schedule:
            return None
        if enabled:
            self._register(schedule)
        elif self.scheduler.get_job(schedule_id):
            self.scheduler.remove_job(schedule_id)
        return {**schedule, "next_run": self.next_run(schedule_id), "description": describe(schedule)}

    def delete(self, schedule_id: str) -> None:
        self.db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        if self.scheduler.get_job(schedule_id):
            self.scheduler.remove_job(schedule_id)
