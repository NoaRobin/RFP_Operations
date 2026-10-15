"""Service Qvidian partagé par l'API et le compléteur RFI : connexion, instantané, contrôles, écritures protégées.

Démonstration et réel ne se mélangent jamais : deux instantanés distincts (demo.sqlite / library.sqlite), et le
compléteur RFI n'utilise la bibliothèque de démonstration qu'en mode démonstration (données fictives).
Le jeton Qvidian reste en mémoire (jamais écrit sur disque).
"""
from __future__ import annotations

import base64
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from ..config import QvidianSettings
from .ai import FindingStore
from .audit import audit
from .bulk import Journal, Plan, WriteGuard, apply, make_plan, undo_plan
from .client import QvidianClient, QvidianError
from .demo import DemoQvidian
from .snapshot import Snapshot, sync


class QvidianService:
    def __init__(self, settings: QvidianSettings, data_dir: Path):
        self.settings = settings
        self.root = data_dir / "qvidian"
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = WriteGuard(settings.write_password)
        self.journal = Journal(self.root / "journal.jsonl")
        self.ai = FindingStore(self.root / "ai_findings.json")
        self.demo = DemoQvidian()
        self.real: QvidianClient | None = None
        self.plans: dict[str, Plan] = {}
        self.sync_state: dict[str, Any] = {"running": False, "message": "", "done": 0, "error": None, "result": None}
        self._lock = threading.Lock()
        self._snapshots: dict[str, Snapshot] = {}
        self._keepalive: threading.Thread | None = None

    def _start_keepalive(self) -> None:
        """La session Qvidian expire après 20 minutes sans appel (réglage par défaut du serveur) : tant que l'app tourne,
        un petit appel de lecture toutes les N minutes évite de refaire le SSO. QVIDIAN_KEEPALIVE_MINUTES=0 le coupe."""
        minutes = self.settings.keepalive_minutes
        if minutes <= 0 or (self._keepalive is not None and self._keepalive.is_alive()):
            return

        def loop() -> None:
            while True:
                time.sleep(60)
                client = self.real
                if client is None or not client.connected:
                    continue
                if time.time() - client.last_call >= minutes * 60:
                    client.keepalive()

        self._keepalive = threading.Thread(target=loop, name="qvidian-keepalive", daemon=True)
        self._keepalive.start()

    # ------------------------------------------------------------------ mode et connexion
    @property
    def mode(self) -> str:
        if self.settings.mode == "off":
            return "off"
        if self.settings.mode == "demo":
            return "demo"
        return "qvidian" if (self.real is not None or self.settings.credentials) else "demo"

    def client(self):
        if self.mode == "demo":
            return self.demo
        if self.mode == "off":
            raise QvidianError("config", "Qvidian est désactivé (QVIDIAN_MODE=off).")
        if self.real is None or not self.real.connected:
            self._connect_from_settings()
        return self.real

    def _connect_from_settings(self) -> None:
        s = self.settings
        client = self.real or QvidianClient(s.auth_url)
        if s.api_key:
            client.connect_api_key(s.user, s.api_key)
        elif s.password:
            client.connect(s.user, s.password)
        else:
            raise QvidianError("config", "Pas de connexion Qvidian (ou session expirée)",
                               "Connectez-vous depuis la fenêtre Qvidian (bouton SSO).")
        self.real = client
        self._start_keepalive()

    def connect(self, user: str, password: str = "", api_key: str = "") -> dict[str, Any]:
        client = QvidianClient(self.settings.auth_url)
        binding = client.connect_api_key(user, api_key) if api_key else client.connect(user, password)
        self.real = client
        self._start_keepalive()
        return {"user": binding.user}

    def sso_url(self, callback: str) -> str:
        if not self.settings.subscriber_suffix:
            raise QvidianError("config", "SSO non configuré", "Renseignez QVIDIAN_SUBSCRIBER_SUFFIX (identifiant de l'abonnement QPA) dans .env.")
        portal = self.settings.auth_url.rsplit("/", 1)[0]
        target = base64.b64encode(callback.encode("utf-8")).decode("ascii")
        return f"{portal}?SubscriberSuffix={self.settings.subscriber_suffix}&SSOWebService={target}"

    def sso_callback(self, token_b64: str, login_b64: str) -> dict[str, Any]:
        token = base64.b64decode(token_b64).decode("utf-8")
        login = base64.b64decode(login_b64).decode("utf-8")
        client = QvidianClient(self.settings.auth_url)
        binding = client.connect_token(login, token)
        self.real = client
        self._start_keepalive()
        return {"user": binding.user}

    def disconnect(self) -> None:
        if self.real is not None:
            self.real.terminate()
        self.real = None

    # ------------------------------------------------------------------ instantané
    def snapshot(self, mode: str | None = None) -> Snapshot:
        mode = mode or self.mode
        name = "demo.sqlite" if mode != "qvidian" else "library.sqlite"
        snap = self._snapshots.get(name)
        if snap is None:
            snap = self._snapshots[name] = Snapshot(self.root / name)
        if name == "demo.sqlite" and snap.empty:
            sync(self.demo, snap, "demo")  # la démo se construit en un instant, avec le même code que le vrai
        return snap

    def rfi_snapshot(self, data_mode: str) -> Snapshot | None:
        """Bibliothèque utilisée par le compléteur RFI : la vraie si synchronisée ; la démo seulement avec des données fictives."""
        if self.settings.mode == "off":
            return None
        real = self.root / "library.sqlite"
        if real.exists():
            snap = self.snapshot("qvidian")
            if not snap.empty:
                return snap
        return self.snapshot("demo") if data_mode == "mock" else None

    def start_sync(self) -> dict[str, Any]:
        with self._lock:
            if self.sync_state["running"]:
                return self.sync_state
            client, mode = self.client(), self.mode
            self.sync_state = {"running": True, "message": "Démarrage…", "done": 0, "error": None, "result": None, "mode": mode}

        def progress(message: str, done: int, _total: int) -> None:
            self.sync_state.update(message=message, done=done)

        def run() -> None:
            try:
                result = sync(client, self.snapshot(mode), mode, progress)
                self.sync_state.update(running=False, result=result, message="Synchronisation terminée")
            except QvidianError as error:
                self.sync_state.update(running=False, error={"code": error.code, "message": error.message, "hint": error.hint})
            except Exception as error:  # noqa: BLE001 - la synchronisation ne doit jamais faire tomber l'app
                self.sync_state.update(running=False, error={"code": "autre", "message": type(error).__name__, "hint": str(error)[:200]})

        threading.Thread(target=run, name="qvidian-sync", daemon=True).start()
        return self.sync_state

    # ------------------------------------------------------------------ contrôles
    def audit(self, today: date | None = None, depth: int = 2) -> dict[str, Any]:
        snap = self.snapshot()
        return audit(snap.all(), today=today, ai=self.ai.load(), depth=depth)

    def status(self) -> dict[str, Any]:
        mode = self.mode
        meta = self.snapshot(mode).meta() if mode != "off" else {}
        return {"mode": mode, "connected": mode == "demo" or (self.real is not None and self.real.connected),
                "user": (self.real.binding.user if self.real and self.real.binding else ("démo" if mode == "demo" else "")),
                "auth_url": self.settings.auth_url, "sso": bool(self.settings.subscriber_suffix), "credentials": self.settings.credentials,
                "write_enabled": self.guard.configured, "locked": self.guard.locked, "snapshot": meta, "sync": self.sync_state,
                "half_life_days": self.settings.half_life_days, "extended_fields": getattr(self.real, "extended_fields", True)}

    # ------------------------------------------------------------------ écritures (mot de passe)
    def plan(self, ids: list[int], action: str, params: dict[str, Any]) -> Plan:
        contents = self.snapshot().many(ids)
        plan = make_plan(contents, action, params)
        self.plans = {k: v for k, v in self.plans.items() if v.created > plan.created - 3600}
        self.plans[plan.id] = plan
        return plan

    def apply(self, plan_id: str, password: str, force: bool, user: str) -> dict[str, Any]:
        plan = self.plans.get(plan_id)
        if plan is None:
            raise QvidianError("qvidian", "Prévisualisation expirée : relancez « Prévisualiser ».")
        self.guard.verify(password)
        client = self.client()
        result = apply(client, plan, force, user, self.journal, self.mode)
        self._refresh([r["id"] for r in result["results"] if r["ok"]], client)
        self.plans.pop(plan_id, None)
        return result

    def undo(self, batch: str, password: str, user: str) -> dict[str, Any]:
        entry = self.journal.get(batch)
        if entry is None:
            raise QvidianError("qvidian", "Lot introuvable dans le journal.")
        if entry.get("source") != self.mode:
            raise QvidianError("qvidian", "Ce lot a été écrit dans une autre bibliothèque (démo / Qvidian).")
        self.guard.verify(password)
        client = self.client()
        result = apply(client, undo_plan(entry), True, user, self.journal, self.mode, undo_of=batch)
        self._refresh([r["id"] for r in result["results"] if r["ok"]], client)
        return result

    def _refresh(self, ids: list[int], client) -> None:
        fresh = []
        for cid in ids:
            try:
                fresh.append(client.content(cid))
            except QvidianError:
                continue
        old = {c["id"]: c for c in self.snapshot().many(ids)}
        for c in fresh:
            c["folder_path"] = c.get("folder_path") or old.get(c["id"], {}).get("folder_path", "")
        if fresh:
            self.snapshot().upsert(fresh)

    # ------------------------------------------------------------------ projets → anciens RFI
    def import_projects(self, store, limit: int = 20) -> dict[str, Any]:
        from ..rfi.precedents.importers import import_document

        client = self.client()
        total, projects = client.projects("AllProjects", 1, limit)
        results = []
        for p in projects:
            try:
                docs = client.project_documents(p["id"])
            except QvidianError as error:
                results.append({"project": p["name"], "error": error.message})
                continue
            for d in docs:
                if d["ext"] not in {"xlsx", "xlsm", "docx"}:
                    continue
                try:
                    name, content = client.project_document(p["id"], d["id"])
                    folder = self.root / ("projets_demo" if self.mode == "demo" else "projets") / str(p["id"])
                    folder.mkdir(parents=True, exist_ok=True)
                    path = folder / Path(name).name
                    path.write_bytes(content)
                    origin = "qvidian-demo" if self.mode == "demo" else "qvidian"
                    res = import_document(store, path, origin, display_name=f"{p['name']} — {Path(name).name}",
                                          modified=d.get("created") or p.get("created") or "")
                    results.append({"project": p["name"], **res})
                except Exception as error:  # noqa: BLE001 - un document illisible n'arrête pas les autres
                    results.append({"project": p["name"], "file": d.get("name"), "error": getattr(error, "message", type(error).__name__)})
        return {"projects": len(projects), "total": total, "documents": results, "imported": sum(r.get("imported", 0) for r in results)}


_SERVICE: dict[str, QvidianService] = {}


def get_service(settings, data_dir: Path) -> QvidianService:
    key = str(data_dir)
    if key not in _SERVICE:
        _SERVICE[key] = QvidianService(settings, data_dir)
    return _SERVICE[key]


__all__ = ["QvidianService", "get_service"]
