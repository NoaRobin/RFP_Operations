"""Historique de démonstration (mode mock uniquement) pour que le tableau de bord ne soit pas vide.

Toutes les lignes sont marquées `demo = 1` et les utilisateurs sont fictifs.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .db import Database, new_id

TEAM = ["Viviane L.", "Arthur P.", "Morgane F.", "Perceval G.", "Guenièvre C."]


def seed_demo_history(db: Database, automations: list[tuple[str, str, int]]) -> int:
    if db.scalar("SELECT COUNT(*) FROM runs") or not automations:
        return 0
    rng = random.Random(7)
    now = datetime.now()
    count = 0
    targets = automations + [("rc_demo", "Recette — Questionnaire consultant", 25)]
    for days_ago in range(20, 0, -1):
        for _ in range(rng.randint(1, 5)):
            target_id, name, minutes = rng.choice(targets)
            created = (now - timedelta(days=days_ago)).replace(hour=rng.randint(8, 18), minute=rng.randint(0, 59), second=0)
            duration = rng.randint(1200, 48000)
            ok = rng.random() > 0.12
            db.create_run(
                id=new_id("run"), target_type="recipe" if target_id.startswith("rc_") else "automation",
                target_id=target_id, target_name=name, user=rng.choice(TEAM), trigger=rng.choice(["manual"] * 4 + ["schedule"]),
                params={}, status="success" if ok else "error", created_at=created.isoformat(timespec="seconds"),
                started_at=created.isoformat(timespec="seconds"),
                finished_at=(created + timedelta(milliseconds=duration)).isoformat(timespec="seconds"),
                duration_ms=duration, summary="Exécution de démonstration" if ok else None,
                error=None if ok else "Connexion au Lakehouse impossible.",
                error_hint=None if ok else "Exemple d'erreur de démonstration.",
                outputs=[], minutes_saved=minutes, data_mode="mock", demo=1,
            )
            count += 1
    return count


def clear_demo_history(db: Database) -> None:
    ids = [r["id"] for r in db.all("SELECT id FROM runs WHERE demo = 1")]
    db.execute("DELETE FROM runs WHERE demo = 1")
    if ids:
        db.execute(f"DELETE FROM run_events WHERE run_id IN ({','.join('?' * len(ids))})", tuple(ids))
