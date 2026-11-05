"""Pilotage : lecture d'Outlook en arrière-plan (jamais dans une requête), avancement, inventaire sur disque."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from .inventory import Inventory, asks_from_mails
from .outlook import OutlookReader, OutlookUnavailable, available, since_months

TEAM = os.environ.get("CONTACTS_TEAM_ADDRESS", "AmeuRFPteam")


class ContactsService:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "contacts"
        self.inventory = Inventory(self.root / "inventory.json")
        self.state: dict[str, Any] = {"running": False, "message": "", "mails": 0, "folders": 0, "error": None}
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        return {"state": self.state, "outlook": available(), "team": TEAM, "summary": self.inventory.summary()}

    def scan(self, months: int = 36) -> dict[str, Any]:
        with self._lock:
            if self.state["running"]:
                return self.status()
            self._stop.clear()
            self.state = {"running": True, "message": "Ouverture d'Outlook…", "mails": 0, "folders": 0, "error": None,
                          "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        threading.Thread(target=self._run, args=(months,), name="contacts-scan", daemon=True).start()
        return self.status()

    def stop(self) -> None:
        self._stop.set()

    def _run(self, months: int) -> None:
        try:
            reader = OutlookReader()
            members = reader.members(TEAM)
            mails = []

            def progress(folder: str, n: int) -> None:
                if n:
                    self.state["mails"] += n
                else:
                    self.state["folders"] += 1
                self.state["message"] = f"{self.state['mails']} mails avec {TEAM} en copie · dossier {folder[-60:]}"

            for m in reader.scan(TEAM, since_months(months), progress, self._stop.is_set):
                mails.append(m)
            self.state["message"] = "Regroupement des questions…"
            asks, stats = asks_from_mails(mails, TEAM, members)
            self.inventory.rebuild(asks, {**stats, "months": months})
            self.state.update(message="Arrêtée (inventaire partiel)." if self._stop.is_set() else "Terminé.")
        except OutlookUnavailable as error:
            self.state.update(error=str(error), message="")
        except Exception as error:  # noqa: BLE001 - jamais de fil mort silencieux
            self.state.update(error=f"{type(error).__name__} : {error}"[:300], message="")
        finally:
            self.state.update(running=False, finished=time.strftime("%Y-%m-%dT%H:%M:%S"))


_SERVICES: dict[str, ContactsService] = {}


def get_service(data_dir: Path) -> ContactsService:
    key = str(data_dir)
    if key not in _SERVICES:
        _SERVICES[key] = ContactsService(data_dir)
    return _SERVICES[key]


__all__ = ["ContactsService", "get_service", "TEAM"]
