"""Synchronisation de toutes les due diligences SharePoint (toutes les années) vers le corpus des précédents.

En arrière-plan, jamais dans une requête HTTP (une grosse année prenait plusieurs minutes et la page « plantait ») :
- incrémentale : un document déjà lu et inchangé (date + taille) n'est ni retéléchargé ni relu ;
- robuste : chaque document est indépendant, relances espacées des erreurs passagères (limitation SharePoint, fichier
  OneDrive pas encore descendu, fichier ouvert dans Excel), et chaque échec restant est expliqué en clair ;
- parallèle pour les téléchargements, lecture des documents une par une (base SQLite) ;
- reprise : interrompue (app fermée, bouton « Arrêter »), elle repart où elle en était grâce au manifeste ;
- jamais d'écriture dans SharePoint, copies locales sous data/rfi/sharepoint/ (jamais committé).

Clé d'un document : son chemin complet. Deux « DDQ.xlsx » de deux clients ne s'écrasent plus l'un l'autre.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .base import DocumentSource, RemoteItem, SourceError
from .navigator import DueDiligenceNavigator

RETRIES = 3
MAX_BYTES = 60 * 1024 * 1024


class CachedSource:
    """Mémoire des listes de dossiers le temps d'une synchronisation : le navigateur relit souvent les mêmes dossiers."""

    def __init__(self, source: DocumentSource):
        self.source, self.name = source, getattr(source, "name", "source")
        self._cache: dict[str, list[RemoteItem]] = {}
        self._lock = threading.Lock()

    def status(self) -> dict:
        return self.source.status()

    def children(self, path: str) -> list[RemoteItem]:
        with self._lock:
            if path in self._cache:
                return self._cache[path]
        items = retry(lambda: self.source.children(path))
        with self._lock:
            self._cache[path] = items
        return items

    def download(self, item: RemoteItem, target: Path) -> Path:
        return self.source.download(item, target)


def retry(fn: Callable[[], Any], attempts: int = RETRIES, sleep: Callable[[float], None] = time.sleep) -> Any:
    for k in range(attempts):
        try:
            return fn()
        except SourceError as error:
            if not error.transient or k == attempts - 1:
                raise
            sleep(min(30.0, error.retry_after or 1.5 * 2 ** k))
        except OSError as error:
            if k == attempts - 1:
                raise SourceError("Lecture impossible.", str(error)[:200], transient=True) from error
            sleep(1.5 * 2 ** k)
    raise AssertionError("inaccessible")


def cache_name(path: str) -> str:
    """Nom court de la copie locale (les chemins SharePoint dépassent vite 260 caractères sous Windows)."""
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:20] + Path(path).suffix.lower()


class SharePointSync:
    def __init__(self, root: Path, importer: Callable[[Path, RemoteItem, str], dict[str, Any]],
                 on_done: Callable[[], None] | None = None, workers: int = 4):
        self.root = root  # data/rfi/sharepoint
        self.importer, self.on_done, self.workers = importer, on_done, workers
        self.manifest_path = root / "manifest.json"
        self.state: dict[str, Any] = {"running": False}
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ manifeste (reprise, incrémental)
    def manifest(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, manifest: dict[str, dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def summary(self) -> dict[str, Any]:
        m = self.manifest()
        done = [v for v in m.values() if v.get("ok")]
        return {"documents": len(done), "questions": sum(v.get("imported", 0) for v in done),
                "failed": sum(1 for v in m.values() if not v.get("ok")),
                "last": max((v.get("at", "") for v in m.values()), default="")}

    # ------------------------------------------------------------------ pilotage
    def start(self, source: DocumentSource, years: list[int] | None = None, full: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.state.get("running"):
                return self.state
            self._stop.clear()
            self.state = {"running": True, "phase": "Lecture des dossiers…", "folders": 0, "found": 0, "done": 0, "imported": 0,
                          "skipped": 0, "failed": 0, "errors": [], "started": datetime.now().isoformat(timespec="seconds"),
                          "finished": None, "stopped": False}
        threading.Thread(target=self._run, args=(CachedSource(source), years, full), name="sharepoint-sync", daemon=True).start()
        return self.state

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        return self.state

    def status(self) -> dict[str, Any]:
        return {**self.state, "errors": self.state.get("errors", [])[-50:], "corpus": self.summary()}

    def _error(self, where: str, error: Exception) -> None:
        hint = getattr(error, "hint", "") or ""
        self.state["errors"].append({"file": where, "message": str(error)[:200], "hint": hint[:300]})
        self.state["failed"] += 1

    # ------------------------------------------------------------------ parcours
    def _documents(self, nav: DueDiligenceNavigator, years: list[int] | None):
        """Toutes les due diligences de toutes les années (≤ année en cours), puis les documents de leurs « final »."""
        for year, item in nav.years():
            if years and year not in years:
                continue
            if self._stop.is_set():
                return
            try:
                rfi = nav.rfi_folder(item)
                folders = [f for f in nav.source.children(rfi.path) if f.is_folder] if rfi else []
            except SourceError as error:
                self._error(f"{year}", error)
                continue
            for folder in folders:
                if self._stop.is_set():
                    return
                self.state.update(folders=self.state["folders"] + 1, phase=f"{year} · {folder.name}")
                try:
                    listing = nav.final_documents(folder.path)
                except SourceError as error:
                    self._error(folder.path, error)
                    continue
                for doc in listing["documents"]:
                    yield RemoteItem(**{k: v for k, v in doc.items() if k != "fund"})

    def _one(self, source: CachedSource, item: RemoteItem) -> tuple[RemoteItem, Path | None, Exception | None]:
        if item.size and item.size > MAX_BYTES:
            return item, None, SourceError(f"{item.name} : trop volumineux ({item.size // 1_000_000} Mo).", "Ignoré (limite 60 Mo).")
        target = self.root / "files" / cache_name(item.path)
        try:
            retry(lambda: source.download(item, target), sleep=lambda s: self._stop.wait(s))
            return item, target, None
        except Exception as error:  # noqa: BLE001
            return item, None, error

    def _run(self, source: CachedSource, years: list[int] | None, full: bool) -> None:
        manifest = {} if full else self.manifest()
        nav = DueDiligenceNavigator(source)
        try:
            todo = []
            for item in self._documents(nav, years):
                self.state["found"] += 1
                known = manifest.get(item.path)
                if known and known.get("ok") and known.get("modified") == item.modified and known.get("size") == item.size:
                    self.state["skipped"] += 1
                    continue
                todo.append(item)
            self.state["phase"] = f"Lecture de {len(todo)} documents nouveaux ou modifiés…"
            self.state["todo"] = len(todo)
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [pool.submit(self._one, source, it) for it in todo]
                for k, future in enumerate(as_completed(futures), start=1):
                    item, path, error = future.result()
                    entry = {"modified": item.modified, "size": item.size, "at": datetime.now().isoformat(timespec="seconds"), "name": item.name}
                    if error is None and path is not None and not self._stop.is_set():
                        try:
                            result = self.importer(path, item, item.path)  # lecture une par une : la base SQLite n'aime pas le parallèle
                            entry.update(ok=True, imported=result.get("imported", 0), identity=result.get("identity_problem", ""))
                            self.state["imported"] += result.get("imported", 0)
                        except Exception as e:  # noqa: BLE001 - un document illisible n'arrête pas les autres
                            error = e
                    if error is not None:
                        entry.update(ok=False, error=str(error)[:200])
                        self._error(item.path, error)
                    manifest[item.path] = entry
                    self.state["done"] = k
                    if k % 10 == 0:
                        self._save(manifest)
                    if self._stop.is_set():
                        for f in futures:
                            f.cancel()
                        break
            self._save(manifest)
            stopped = self._stop.is_set()
            self.state.update(phase="Arrêtée : elle reprendra où elle en était." if stopped else "Terminée.", stopped=stopped)
            if self.on_done and not stopped:
                try:
                    self.on_done()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as error:  # noqa: BLE001 - jamais de fil mort silencieux
            self._save(manifest)
            self._error("synchronisation", error)
            self.state["phase"] = "Interrompue par une erreur (détail ci-dessous) : relancez, elle reprendra où elle en était."
        finally:
            self.state.update(running=False, finished=datetime.now().isoformat(timespec="seconds"))


__all__ = ["SharePointSync", "CachedSource", "retry", "cache_name"]
