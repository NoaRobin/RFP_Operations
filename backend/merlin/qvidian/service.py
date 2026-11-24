"""Service Qvidian partagé par l'API et le compléteur RFI : connexion, instantané, contrôles, écritures protégées.

Démonstration et réel ne se mélangent jamais : deux instantanés distincts (demo.sqlite / library.sqlite), et le
compléteur RFI n'utilise la bibliothèque de démonstration qu'en mode démonstration (données fictives).
Le jeton Qvidian reste en mémoire (jamais écrit sur disque).
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from ..config import QvidianSettings
from .ai import FindingStore
from .agent_export import AgentExportConfig, export as agent_export
from .audit import audit
from .bulk import Journal, Plan, WriteGuard, apply, make_plan, undo_plan
from .client import QvidianClient, QvidianError
from .credentials import CredentialStore
from .demo import DemoQvidian
from .history import History, build_links, demo_precedents
from .library_search import SearchManager
from .snapshot import Snapshot, sync


class QvidianService:
    def __init__(self, settings: QvidianSettings, data_dir: Path):
        self.settings = settings
        self.root = data_dir / "qvidian"
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = WriteGuard(settings.write_password)
        self.credentials = CredentialStore(self.root / "credentials.json")
        from ..match.service import MatchBuilder

        self.matcher = MatchBuilder()
        self._stored = self.credentials.load()  # clé d'API saisie une fois dans l'app, chiffrée sur le poste (DPAPI)
        self.journal = Journal(self.root / "journal.jsonl")
        self.ai = FindingStore(self.root / "ai_findings.json")
        self.agent_export = AgentExportConfig(self.root / "agent_export.json")
        self.demo = DemoQvidian()
        self.search = SearchManager(data_dir / "models", settings.search_encoder, settings.search_reranker, settings.half_life_days)
        self.search.downloads.on_done = lambda _mid: (self.rebuild_index(), self.build_matcher())
        self.data_dir = data_dir
        self._history_cache: dict[str, tuple[float, dict]] = {}
        self.history_state: dict[str, Any] = {"running": False, "error": None}
        self.search.history_for = self.history_for
        self.search.history_signature = self._history_mtime
        self.search.report_for = lambda snap: self.audit() if snap.path == self.snapshot().path else None
        self.real: QvidianClient | None = None
        self.plans: dict[str, Plan] = {}
        self.sync_state: dict[str, Any] = {"running": False, "message": "", "done": 0, "error": None, "result": None}
        self._lock = threading.Lock()
        self._snapshots: dict[str, Snapshot] = {}
        self._keepalive: threading.Thread | None = None
        self.last_sso_error = ""
        self.connect_error = ""
        self.connected_by = ""
        self._audit_cache: dict[tuple, dict[str, Any]] = {}

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
        return "qvidian" if (self.real is not None or self._creds()) else "demo"

    def _creds(self) -> dict[str, str] | None:
        """Identifiants de connexion automatique : .env d'abord, sinon ceux mémorisés depuis l'app."""
        s = self.settings
        if s.credentials:
            return {"user": s.user, "api_key": s.api_key, "password": s.password, "auth_url": s.auth_url, "from": "env"}
        if self._stored and self._stored.get("user") and (self._stored.get("api_key") or self._stored.get("password")):
            return {**self._stored, "auth_url": self._stored.get("auth_url") or s.auth_url, "from": "app"}
        return None

    def client(self):
        if self.mode == "demo":
            return self.demo
        if self.mode == "off":
            raise QvidianError("config", "Qvidian est désactivé (QVIDIAN_MODE=off).")
        if self.real is None or not self.real.connected:
            self._connect_from_settings()
        return self.real

    def _connect_from_settings(self) -> None:
        """Clé d'API (ou mot de passe) du .env : prioritaire sur le SSO, et reconnexion automatique quand la session
        expire — on ne se reconnecte jamais à la main tant que l'app tourne."""
        s = self._creds() or {}
        client = self.real or self._new_client(s.get("auth_url"))
        if s.get("api_key"):
            login = lambda: client.connect_api_key(s["user"], s["api_key"])  # noqa: E731
        elif s.get("password"):
            login = lambda: client.connect(s["user"], s["password"])  # noqa: E731
        else:
            raise QvidianError("config", "Pas de connexion Qvidian (ou session expirée)",
                               "Connectez-vous depuis la fenêtre Qvidian (bouton SSO), ou mettez QVIDIAN_USER et QVIDIAN_API_KEY dans .env.")
        login()
        client.reauth = login
        self.real = client
        self.connect_error = ""
        self.connected_by = "api_key" if s.get("api_key") else "password"
        self._start_keepalive()

    def warmup(self) -> None:
        """Au démarrage de l'app : connexion par la clé d'API du .env, instantané, liens anciens RFI et index de recherche."""
        def run() -> None:
            try:
                if self.mode == "qvidian" and self._creds() and (self.real is None or not self.real.connected):
                    self._connect_from_settings()
            except QvidianError as error:
                self.connect_error = error.message
            try:
                snap = self.snapshot()
                self.history_for(snap)
                self.search.get(snap, wait=False)
                self.audit()
                if self.matcher.get(snap.path) is None:
                    self.build_matcher(snap, background=False)
            except Exception:  # noqa: BLE001 - préparation facultative
                pass

        threading.Thread(target=run, name="qvidian-warmup", daemon=True).start()

    def _new_client(self, auth_url: str | None = None) -> QvidianClient:
        client = QvidianClient(auth_url or self.settings.auth_url)
        if hasattr(client, "configure"):
            client.configure(self.settings.cache_seconds, self.settings.max_calls_per_second)
        return client

    def connect(self, user: str, password: str = "", api_key: str = "", remember: bool = True, auth_url: str = "") -> dict[str, Any]:
        """Connexion depuis l'app. Espaces et retours à la ligne d'un copier-coller retirés (cause n° 1 d'un refus).
        remember : la clé est mémorisée sur ce poste (chiffrée DPAPI) et l'app se reconnecte seule ensuite."""
        user, password, api_key, auth_url = user.strip(), password.strip(), "".join(api_key.split()), auth_url.strip()
        client = self._new_client(auth_url or None)
        try:
            binding = client.connect_api_key(user, api_key) if api_key else client.connect(user, password)
        except QvidianError as error:
            if error.code == "auth" and api_key:
                raise QvidianError("auth", f"Clé d'API refusée par Qvidian : {error.message}",
                                   "Vérifiez : 1) l'identifiant est celui du compte Qvidian auquel la clé a été attribuée (souvent "
                                   "l'adresse e-mail professionnelle) ; 2) la clé est copiée en entier ; 3) l'adresse du service "
                                   f"({client.auth_url}) est bien celle de votre abonnement.") from error
            raise
        client.reauth = (lambda: client.connect_api_key(user, api_key)) if api_key else (lambda: client.connect(user, password))
        self.real = client
        self.connected_by = "api_key" if api_key else "password"
        self.connect_error = ""
        if remember:
            self.credentials.save(user, api_key=api_key, password=password, auth_url=auth_url)
            self._stored = self.credentials.load()
        self._start_keepalive()
        try:  # bibliothèque vide : première synchronisation lancée tout de suite (incrémentale ensuite)
            self.start_sync("auto")
        except QvidianError:
            pass
        return {"user": binding.user}

    def forget(self) -> None:
        """Oublie la clé mémorisée sur ce poste (et se déconnecte si la session venait d'elle)."""
        self.credentials.forget()
        self._stored = None
        if not self.settings.credentials:
            self.disconnect()

    def sso_url(self, callback: str) -> str:
        """Le SubscriberSuffix est facultatif : l'exemple SSOQvidianWebServices (Default.aspx.cs) redirige avec le seul
        SSOWebService quand il est vide ; le portail QPA demande alors l'adresse e-mail et oriente vers le SSO de l'entreprise."""
        portal = self.settings.auth_url.rsplit("/", 1)[0]
        target = base64.b64encode(callback.encode("utf-8")).decode("ascii")
        if self.settings.subscriber_suffix:
            return f"{portal}?SubscriberSuffix={self.settings.subscriber_suffix}&SSOWebService={target}"
        return f"{portal}?SSOWebService={target}"

    def sso_callback(self, token_b64: str, login_b64: str) -> dict[str, Any]:
        """Paramètres renvoyés par le portail QPA (Base64). Tolérant : « + » devenu espace dans l'adresse, Base64 « URL »,
        remplissage manquant, ou valeur déjà en clair. Chaque échec est noté (sans le jeton) dans data/qvidian/sso.log."""
        token, login = _from_b64(token_b64), _from_b64(login_b64)
        client = self._new_client()
        try:
            binding = client.connect_token(login, token.strip("{} "))
        except QvidianError as error:
            self.last_sso_error = f"{error.message} (identifiant reçu : {login or 'vide'} ; jeton de {len(token)} caractères)"
            self._log_sso(self.last_sso_error)
            raise
        self.real = client
        self.last_sso_error = ""
        self.connected_by = "sso"
        self._start_keepalive()
        return {"user": binding.user}

    def _log_sso(self, message: str) -> None:
        try:
            with (self.root / "sso.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except OSError:
            pass

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
        if name == "demo.sqlite" and (snap.empty or snap.meta().get("count") != str(len(self.demo.contents))):
            sync(self.demo, snap, "demo")  # la démo se construit en un instant, avec le même code que le vrai (et suit ses évolutions)
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

    def start_sync(self, kind: str = "auto") -> dict[str, Any]:
        """kind : full | delta | auto (incrémentale si une synchronisation complète existe déjà)."""
        with self._lock:
            if self.sync_state["running"]:
                return self.sync_state
            client, mode = self.client(), self.mode
            self.sync_state = {"running": True, "message": "Démarrage…", "done": 0, "error": None, "result": None, "mode": mode,
                               "kind": kind, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

        def progress(message: str, done: int, _total: int) -> None:
            self.sync_state.update(message=message, done=done)

        def run() -> None:
            try:
                snap = self.snapshot(mode)
                wanted = "delta" if kind == "auto" and snap.meta().get("synced_at") and not snap.empty else ("full" if kind == "auto" else kind)
                result = sync(client, snap, mode, progress, workers=self.settings.concurrency, mode=wanted)
                self.rebuild_history(snap, background=True)  # liens anciens RFI ↔ textes, puis index de recherche
                if self.agent_export.load().get("auto") and self.agent_export.load().get("path"):
                    self.sync_state.update(message="Mise à jour du dossier de l'agent")
                    result["agent_export"] = self.export_for_agent(snap=snap, mode_name=mode)
                self.sync_state.update(running=False, result=result, message="Synchronisation terminée")
            except QvidianError as error:
                self.sync_state.update(running=False, error={"code": error.code, "message": error.message, "hint": error.hint})
            except Exception as error:  # noqa: BLE001 - la synchronisation ne doit jamais faire tomber l'app
                self.sync_state.update(running=False, error={"code": "autre", "message": type(error).__name__, "hint": str(error)[:200]})

        threading.Thread(target=run, name="qvidian-sync", daemon=True).start()
        return self.sync_state

    # ------------------------------------------------------------------ dossier lu par l'agent (Copilot)
    def export_for_agent(self, snap: Snapshot | None = None, mode_name: str | None = None) -> dict[str, Any]:
        """Met à jour le dossier de l'agent depuis l'instantané courant ; l'erreur éventuelle est gardée, jamais levée."""
        cfg = self.agent_export.load()
        mode_name = mode_name or self.mode
        snap = snap or self.snapshot(mode_name)
        try:
            if not cfg["path"]:
                raise ValueError("Aucun dossier choisi.")
            history = History(self._history_path(snap)).by_content() if self._history_path(snap).exists() else {}
            last = agent_export(snap.all(), Path(cfg["path"]), "demo" if mode_name != "qvidian" else "qvidian", cfg["mode"],
                                bool(cfg["include_expired"]), history)
            self.agent_export.save({"last": last, "error": None})
            return last
        except Exception as error:  # noqa: BLE001 - dossier absent, fichier ouvert… : dit à l'écran, ne bloque pas la synchro
            message = str(error)[:300] or type(error).__name__
            self.agent_export.save({"error": message})
            return {"error": message}

    # ------------------------------------------------------------------ historique : anciens RFI ↔ textes Qvidian
    def _history_path(self, snap: Snapshot) -> Path:
        return snap.path.with_name(f"{snap.path.stem}.history.json")

    def _history_mtime(self, snap: Snapshot) -> float | None:
        path = self._history_path(snap)
        return path.stat().st_mtime if path.exists() else None

    def _precedents(self, snap: Snapshot) -> list[Any]:
        try:
            from ..rfi.precedents import get_index

            stored = get_index(self.data_dir / "rfi").store.all()
        except Exception:  # noqa: BLE001 - pas d'anciens RFI : seulement la démo
            stored = []
        if snap.path.name == "demo.sqlite":
            return demo_precedents({c["id"]: c for c in snap.all()}) + stored
        return [p for p in stored if "demo" not in (p.origin or "")]  # vraie bibliothèque : jamais de précédents de démonstration

    def _history_key(self, snap: Snapshot, precedents: int) -> str:
        meta = snap.meta()
        return f"{meta.get('synced_at')}|{meta.get('count')}|{precedents}"

    def history_for(self, snap: Snapshot) -> dict[int, dict[str, Any]]:
        """Liens enregistrés ; reconstruits en arrière-plan quand l'instantané ou les anciens RFI ont changé."""
        path = self._history_path(snap)
        mtime = path.stat().st_mtime if path.exists() else 0.0
        cached = self._history_cache.get(str(path))
        if cached is None or cached[0] != mtime:
            cached = (mtime, History(path).by_content() if mtime else {})
            self._history_cache[str(path)] = cached
        if not mtime and not self.history_state.get("running"):
            self.rebuild_history(snap, background=True)
        return cached[1]

    def rebuild_history(self, snap: Snapshot | None = None, background: bool = False) -> dict[str, Any]:
        snap = snap or self.snapshot()

        def run() -> None:
            self.history_state.update(running=True, error=None)
            try:
                precedents = self._precedents(snap)
                links = build_links(snap.all(), precedents)
                History(self._history_path(snap)).save(links, len(precedents), self._history_key(snap, len(precedents)))
                self.history_state.update(running=False, finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
                self.search.get(snap, wait=False)  # l'index de recherche intègre les questions passées
                self.build_matcher(snap, background=False)  # rapprochement calibré des questions (même moteur partout)
            except Exception as error:  # noqa: BLE001 - l'historique ne doit jamais bloquer la recherche
                self.history_state.update(running=False, error=str(error)[:300])

        if background:
            threading.Thread(target=run, name="qvidian-history", daemon=True).start()
        else:
            run()
        return self.history_summary(snap)

    # ------------------------------------------------------------------ questions déjà tombées
    def build_matcher(self, snap: Snapshot | None = None, background: bool = True) -> dict[str, Any]:
        snap = snap or self.snapshot()
        precedents = self._precedents(snap)
        links = History(self._history_path(snap)).links
        enc2, rr2 = self.search.precise_models()
        models = {"encoder": self.search._encoder(), "reranker": self.search._reranker(), "precise_encoder": enc2, "precise_reranker": rr2}
        return self.matcher.build(snap, precedents, links, models, self._history_key(snap, len(precedents)), background)

    def match(self, question: str, k: int = 8) -> dict[str, Any]:
        snap = self.snapshot()
        m = self.matcher.get(snap.path)
        if m is None:
            if not self.matcher.state["running"]:
                self.build_matcher(snap)
            return {"ready": False, "state": self.matcher.state, "matches": [], "answers": []}
        t0 = time.time()
        matches = m.match(question, k=k)
        votes = m.content_votes(question)
        titles = {c["id"]: c for c in snap.many([cid for cid, *_ in votes])}
        answers = [{"id": cid, "p": round(p, 3), "files": files, "asked": asked, "title": titles.get(cid, {}).get("title", ""),
                    "text": (titles.get(cid, {}).get("text") or "")[:400]} for cid, p, files, asked in votes if cid in titles]
        threshold = (m.fast_model.report.get("threshold") if m.fast_model else None)
        return {"ready": True, "matches": [x.public() for x in matches], "answers": answers, "threshold": threshold,
                "calibrated": m.fast_model is not None, "ms": round((time.time() - t0) * 1000, 1)}

    def memory(self) -> dict[str, Any]:
        from .memory import memory

        snap = self.snapshot()
        engine = self.search.get(snap, wait=False)
        levels = {}
        if engine is not None and getattr(engine, "rows", None):
            levels = {c["id"]: engine.levels[i].scope for i, c in enumerate(engine.rows)}
        return memory(snap.all(), History(self._history_path(snap)).links, self.matcher.get(snap.path), levels=levels)

    def _levels(self, snap: Snapshot) -> dict[int, str]:
        engine = self.search.get(snap, wait=False)
        if engine is not None and getattr(engine, "rows", None):
            return {c["id"]: engine.levels[i].scope for i, c in enumerate(engine.rows)}
        return {}

    def freshness(self) -> dict[str, Any]:
        from .workshop import freshness

        return freshness(self.snapshot().all())

    def families(self) -> list[dict[str, Any]]:
        from .workshop import families

        return families(self.snapshot().all())

    def question_bank(self, q: str = "", only: str = "") -> dict[str, Any]:
        from .workshop import question_bank

        snap = self.snapshot()
        m = self.matcher.get(snap.path)
        if m is None and not self.matcher.state["running"]:
            self.build_matcher(snap)
        return {**question_bank(m, {c["id"]: c for c in snap.all()}, q, only), "state": self.matcher.state}

    def export(self, ids: list[int]) -> bytes:
        from .workshop import export_xlsx

        snap = self.snapshot()
        rows = {c["id"]: c for c in snap.many(ids)}
        return export_xlsx([rows[i] for i in ids if i in rows], self._levels(snap))

    def match_status(self) -> dict[str, Any]:
        snap = self.snapshot()
        m = self.matcher.get(snap.path)
        return {"state": self.matcher.state, "stats": m.stats() if m else None}

    def history_summary(self, snap: Snapshot | None = None) -> dict[str, Any]:
        snap = snap or self.snapshot()
        h = History(self._history_path(snap))
        by_content = h.by_content()
        titles = {c["id"]: c["title"] for c in snap.many(list(by_content))}
        top = sorted(by_content.items(), key=lambda kv: -kv[1]["files"])[:20]
        return {**h.summary(), "state": self.history_state,
                "top": [{"id": cid, "title": titles.get(cid, ""), "files": e["files"], "last": e["last"], "questions": e["questions"][:5]}
                        for cid, e in top]}

    # ------------------------------------------------------------------ recherche sémantique
    def library_search(self, query: str, filters: dict[str, Any] | None = None, sort: str = "pertinence", k: int = 20,
                       rerank: bool = True) -> dict[str, Any]:
        snap = self.snapshot()
        engine = self.search.get(snap, wait=False)
        out = engine.search(query, filters, sort, k, rerank)
        out["index"] = self.search.status(snap)["building"]
        return out

    def insight(self, content_id: int) -> dict[str, Any] | None:
        return self.search.get(self.snapshot(), wait=False).describe(content_id)

    def overview(self) -> dict[str, Any]:
        return self.search.get(self.snapshot(), wait=False).overview()

    def engine_status(self) -> dict[str, Any]:
        snap = self.snapshot()
        self.search.get(snap, wait=False)
        return self.search.status(snap)

    def download_model(self, model_id: str) -> dict[str, Any]:
        from ..search.neural import MODELS

        if model_id not in MODELS:
            raise QvidianError("config", f"Modèle inconnu : {model_id}")
        state = self.search.downloads.start(model_id)
        return {**state, "id": model_id}

    def rebuild_index(self) -> dict[str, Any]:
        self.search.reset_models()
        snap = self.snapshot()
        self.search._engines.pop(str(snap.path), None)
        self.search.get(snap, wait=False)
        return self.search.status(snap)

    def api_stats(self) -> dict[str, Any]:
        client = self.demo if self.mode == "demo" else self.real
        tel = client.telemetry.summary() if client is not None and hasattr(client, "telemetry") else None
        s = self.settings
        return {"mode": self.mode, "telemetry": tel, "cache_entries": len(client.cache) if client is not None and hasattr(client, "cache") else 0,
                "limiter_wait_s": round(getattr(getattr(client, "limiter", None), "waited", 0.0), 2),
                "delta_supported": getattr(client, "delta_supported", None),
                "settings": {"concurrency": s.concurrency, "max_calls_per_second": s.max_calls_per_second, "cache_seconds": s.cache_seconds,
                             "keepalive_minutes": s.keepalive_minutes, "search_encoder": s.search_encoder, "search_reranker": s.search_reranker},
                "snapshot": self.snapshot().meta() if self.mode != "off" else {}, "last_sync": self.sync_state.get("result")}

    def reset_stats(self) -> None:
        client = self.demo if self.mode == "demo" else self.real
        if client is not None and hasattr(client, "telemetry"):
            client.telemetry.reset()

    # ------------------------------------------------------------------ contrôles
    def audit(self, today: date | None = None, depth: int = 2) -> dict[str, Any]:
        """Carte des erreurs, gardée en mémoire tant que l'instantané et l'analyse IA n'ont pas changé (retour instantané)."""
        snap = self.snapshot()
        meta = snap.meta()
        ai_mtime = self.ai.path.stat().st_mtime if self.ai.path.exists() else 0.0
        key = (str(snap.path), meta.get("synced_at"), meta.get("count"), meta.get("updated_at"), ai_mtime, depth,
               (today or date.today()).isoformat())
        cached = self._audit_cache.get(key)
        if cached is None:
            disk = snap.path.with_name(f"{snap.path.stem}.audit-{depth}.json")
            try:  # au redémarrage de l'app : la carte enregistrée sert si rien n'a changé
                stored = json.loads(disk.read_text(encoding="utf-8")) if disk.exists() else None
                cached = stored["audit"] if stored and stored.get("key") == list(key) else None
            except (OSError, ValueError, KeyError):
                cached = None
            if cached is None:
                cached = audit(snap.all(), today=today, ai=self.ai.load(), depth=depth)
                try:
                    tmp = disk.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"key": list(key), "audit": cached}, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(disk)
                except OSError:
                    pass
            self._audit_cache = {k: v for k, v in self._audit_cache.items() if k[0] != key[0] or k[5] != depth}
            self._audit_cache[key] = cached
        return cached

    def status(self) -> dict[str, Any]:
        mode = self.mode
        meta = self.snapshot(mode).meta() if mode != "off" else {}
        return {"mode": mode, "connected": mode == "demo" or (self.real is not None and self.real.connected),
                "user": (self.real.binding.user if self.real and self.real.binding else ("démo" if mode == "demo" else "")),
                "auth_url": self.settings.auth_url, "sso": True, "connected_by": self.connected_by,
                "api_key_configured": bool((self._creds() or {}).get("api_key")),
                "credentials_from": (self._creds() or {}).get("from", ""), "remembered": self.credentials.public(), "connect_error": self.connect_error, "last_sso_error": self.last_sso_error, "sso_suffix": bool(self.settings.subscriber_suffix), "credentials": bool(self._creds()),
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
        if not projects:  # guide : AllProjects exige ManageAllProjects ; sinon, les projets de l'utilisateur
            total, projects = client.projects("MyProjects", 1, limit)
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


def _from_b64(value: str) -> str:
    raw = (value or "").strip().replace(" ", "+")
    for decode in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            text = decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
            if text and text.isprintable():
                return text
        except (ValueError, UnicodeDecodeError):
            continue
    return value or ""  # pas du Base64 : valeur en clair


_SERVICE: dict[str, QvidianService] = {}


def get_service(settings, data_dir: Path) -> QvidianService:
    key = str(data_dir)
    if key not in _SERVICE:
        _SERVICE[key] = QvidianService(settings, data_dir)
    return _SERVICE[key]


__all__ = ["QvidianService", "get_service"]
