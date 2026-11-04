"""Installation des modèles de recherche, même derrière un proxy d'entreprise.

Pourquoi « HTTP 403 » : les petits fichiers viennent de huggingface.co, mais les gros (model.onnx) sont redirigés vers
un serveur de diffusion (us.aws.cdn.hf.co, cas-bridge.xethub.hf.co…) que beaucoup de proxys bloquent. D'où :

1. Python avec le proxy et les certificats déclarés dans Windows, **reprise** là où le téléchargement s'est arrêté
   (Range), au fil de l'eau sur le disque ;
2. sinon, sous Windows, **BITS** (le service de téléchargement de Windows Update) : il passe par le proxy de
   l'entreprise avec l'authentification de la session Windows, reprend seul après une coupure ;
3. sinon, **dépôt manuel** : liens à ouvrir dans Edge, puis glisser les fichiers dans l'app (ou « Chercher dans
   Téléchargements »). Chaque fichier est reconnu par sa taille et son empreinte SHA-256, quel que soit son nom.

Chaque fichier est vérifié (SHA-256 publiée par Hugging Face) avant d'être installé : un fichier tronqué, modifié ou
venu d'un miroir douteux est refusé. Jamais de téléchargement sans clic explicite.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

HF = "https://huggingface.co"
CHUNK = 1 << 20


class DownloadError(Exception):
    def __init__(self, message: str, hint: str = "", host: str = "", status: int = 0):
        super().__init__(message)
        self.hint, self.host, self.status = hint, host, status


def bases() -> list[str]:
    """Sources essayées dans l'ordre : MERLIN_MODELS_URL (miroir interne, plusieurs séparés par des virgules), puis Hugging Face."""
    extra = [b.strip().rstrip("/") for b in os.environ.get("MERLIN_MODELS_URL", "").split(",") if b.strip()]
    return list(dict.fromkeys(extra + [HF]))


def url_of(base: str, repo: str, remote: str) -> str:
    return f"{base}/{repo}/resolve/main/{remote}"


def sha256(path: Path, progress: Callable[[int], None] | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK * 4):
            h.update(chunk)
            if progress:
                progress(len(chunk))
    return h.hexdigest()


def _verify() -> Any:
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001
        return True


def blocked_hint(host: str) -> str:
    return (f"Le proxy de l'entreprise refuse {host}. Les gros fichiers des modèles viennent de ce serveur de diffusion de "
            "Hugging Face. Solutions : 1) « Installer depuis le navigateur » : ouvrez les liens dans Edge, puis déposez les "
            "fichiers ici ; 2) demandez à l'IT d'autoriser huggingface.co et *.hf.co ; 3) un miroir interne "
            "(MERLIN_MODELS_URL dans .env).")


# ---------------------------------------------------------------------------------------------- transports
class PythonFetch:
    name = "python"
    label = "Python (proxy et certificats de Windows)"

    def __call__(self, url: str, part: Path, size: int, progress: Callable[[int], None], stop: threading.Event) -> None:
        import httpx

        proxies = urllib.request.getproxies()  # sous Windows : le proxy des paramètres Internet (registre)
        proxy = proxies.get("https") or proxies.get("http")
        headers = {"User-Agent": "RFP-pas-envie-de-travailler/2.0 (installation de modeles)"}
        start = part.stat().st_size if part.exists() else 0
        if start >= size:
            return
        if start:
            headers["Range"] = f"bytes={start}-"  # reprise : on ne refait jamais ce qui est déjà descendu
        try:
            with httpx.Client(proxy=proxy or None, trust_env=not proxy, follow_redirects=True, verify=_verify(),
                              timeout=httpx.Timeout(60, connect=20)) as client, client.stream("GET", url, headers=headers) as r:
                host = r.url.host or urlparse(url).netloc
                if r.status_code in (401, 403, 407, 451):
                    raise DownloadError(f"HTTP {r.status_code} sur {host}", blocked_hint(host), host, r.status_code)
                if r.status_code >= 400:
                    raise DownloadError(f"HTTP {r.status_code} sur {host}", "", host, r.status_code)
                mode = "ab" if start and r.status_code == 206 else "wb"
                if mode == "wb" and start:
                    progress(-start)
                with part.open(mode) as f:
                    for chunk in r.iter_bytes(CHUNK):
                        if stop.is_set():
                            raise DownloadError("Arrêté.", "Le téléchargement reprendra où il en était.")
                        f.write(chunk)
                        progress(len(chunk))
        except httpx.HTTPError as error:
            text = f"{type(error).__name__} {error}".lower()
            host = urlparse(url).netloc
            if "certificate" in text or "ssl" in text:
                raise DownloadError(f"Certificat refusé ({host})", "Inspection TLS de l'entreprise : essai par Windows.", host) from error
            if "proxy" in text or "407" in text:
                raise DownloadError(f"Proxy : {error}"[:200], blocked_hint(host), host, 407) from error
            raise DownloadError(f"Réseau : {type(error).__name__}", "Connexion coupée : relancez, le téléchargement reprendra.", host) from error


class BitsFetch:
    """BITS (Background Intelligent Transfer Service) : la pile de Windows Update, proxy et identifiants de la session."""
    name = "windows"
    label = "Windows (BITS, comme Windows Update)"

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32" and shutil.which("powershell") is not None

    def __call__(self, url: str, part: Path, size: int, progress: Callable[[int], None], stop: threading.Event) -> None:
        def q(text: str) -> str:
            return "'" + text.replace("'", "''") + "'"

        part.unlink(missing_ok=True)
        cmd = (f"$ErrorActionPreference='Stop'; Import-Module BitsTransfer; "
               f"Start-BitsTransfer -Source {q(url)} -Destination {q(str(part))} -ProxyUsage SystemDefault -Priority Foreground "
               f"-DisplayName 'Merlin modele' -Description 'Installation d un modele de recherche'")
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        seen = 0
        while proc.poll() is None:
            if stop.wait(1.0):
                proc.kill()
                raise DownloadError("Arrêté.")
            tmp = [p for p in part.parent.glob("BIT*.tmp")]  # fichier temporaire de BITS : sa taille donne l'avancement
            now = max((p.stat().st_size for p in tmp), default=0) if tmp else 0
            if now > seen:
                progress(now - seen)
                seen = now
        _, err = proc.communicate()
        if proc.returncode != 0 or not part.exists():
            text = (err or "").strip().splitlines()
            host = urlparse(url).netloc
            detail = next((t for t in text if t.strip()), "échec")[:200]
            denied = "403" in detail or "denied" in detail.lower() or "refus" in detail.lower()
            raise DownloadError(f"Windows (BITS) : {detail}", blocked_hint(host) if denied else "", host, 403 if denied else 0)
        progress(max(0, part.stat().st_size - seen))


def transports() -> list[Any]:
    out: list[Any] = [PythonFetch()]
    if BitsFetch.available():
        out.append(BitsFetch())
    return out


# ---------------------------------------------------------------------------------------------- installation
class Downloads:
    """Un téléchargement à la fois par modèle, état lisible par l'écran « API & moteur »."""

    def __init__(self, root: Path, fetchers: list[Any] | None = None):
        self.root = root
        self.fetchers = fetchers
        self.state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def _specs(self):
        from .neural import MODELS

        return MODELS

    def links(self, model_id: str) -> list[dict[str, Any]]:
        spec = self._specs()[model_id]
        return [{"name": name, "url": url_of(HF, spec.repo, f.remote), "size": f.size, "sha256": f.sha256}
                for name, f in spec.files.items()]

    def start(self, model_id: str) -> dict[str, Any]:
        return self.start_many([model_id])[model_id]

    def start_many(self, model_ids: list[str]) -> dict[str, dict[str, Any]]:
        specs = self._specs()
        todo = []
        with self._lock:
            self._stop.clear()
            for mid in model_ids:
                spec = specs[mid]
                current = self.state.get(mid)
                if current and current.get("running"):
                    continue
                self.state[mid] = {"running": True, "queued": True, "done": 0, "total": sum(f.size for f in spec.files.values()),
                                   "error": None, "hint": "", "host": "", "file": "", "via": "", "attempts": [], "links": self.links(mid)}
                todo.append(spec)
        if todo:  # un modèle après l'autre : la bande passante va au premier, qui devient utilisable plus tôt
            threading.Thread(target=lambda: [self._run(s) for s in todo], name="models-download", daemon=True).start()
        return {mid: self.state[mid] for mid in model_ids}

    def stop(self) -> None:
        self._stop.set()

    def _run(self, spec) -> None:
        state = self.state[spec.id]
        state["queued"] = False
        folder = self.root / spec.id
        folder.mkdir(parents=True, exist_ok=True)
        try:
            for name, f in spec.files.items():
                target = folder / name
                if target.exists() and target.stat().st_size == f.size:
                    state["done"] += f.size
                    continue
                state["file"] = name
                self._fetch(spec, name, f, target, state)
            state.update(running=False, finished=time.time(), error=None, hint="")
        except DownloadError as error:
            state.update(running=False, error=str(error), hint=error.hint, host=error.host)
        except Exception as error:  # noqa: BLE001 - un échec n'arrête jamais l'app
            state.update(running=False, error=str(error)[:300])

    def _fetch(self, spec, name: str, f, target: Path, state: dict[str, Any]) -> None:
        part = target.with_name(target.name + ".part")
        base_done = state["done"]

        def progress(n: int) -> None:
            state["done"] = max(base_done, state["done"] + n)

        last: DownloadError | None = None
        for base in bases():
            url = url_of(base, spec.repo, f.remote)
            for fetch in (self.fetchers or transports()):
                state["via"] = fetch.label
                try:
                    fetch(url, part, f.size, progress, self._stop)
                except DownloadError as error:
                    state["attempts"].append({"via": fetch.label, "host": error.host, "error": str(error)[:160]})
                    last = error
                    if self._stop.is_set():
                        raise
                    continue
                if part.stat().st_size != f.size or sha256(part) != f.sha256:
                    part.unlink(missing_ok=True)  # tronqué ou modifié : jamais installé
                    last = DownloadError(f"{name} : empreinte incorrecte", "Fichier altéré en route (proxy ?) : il a été supprimé.")
                    state["attempts"].append({"via": fetch.label, "host": "", "error": str(last)})
                    state["done"] = base_done
                    continue
                os.replace(part, target)
                state["done"] = base_done + f.size
                return
        raise last or DownloadError(f"{name} : aucun chemin de téléchargement")

    # ------------------------------------------------------------------ dépôt manuel
    def install_files(self, paths: list[Path], move: bool = False) -> dict[str, Any]:
        """Reconnaît chaque fichier par sa taille puis son empreinte (le nom ne compte pas : Edge renomme les doublons
        « model_quantized (1).onnx »), et l'installe à sa place. Un fichier inconnu est ignoré, jamais installé."""
        wanted: dict[int, list[tuple[str, str, Any]]] = {}
        for mid, spec in self._specs().items():
            for name, f in spec.files.items():
                wanted.setdefault(f.size, []).append((mid, name, f))
        installed, ignored = [], []
        for path in paths:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            candidates = wanted.get(size)
            if not candidates:
                ignored.append(path.name)
                continue
            digest = sha256(path)
            hits = [(mid, name) for mid, name, f in candidates if f.sha256 == digest]
            if not hits:
                ignored.append(path.name)
                continue
            for mid, name in hits:  # un même tokenizer sert à plusieurs modèles
                folder = self.root / mid
                folder.mkdir(parents=True, exist_ok=True)
                tmp = folder / (name + ".part")
                shutil.copyfile(path, tmp)
                os.replace(tmp, folder / name)
                installed.append({"model": mid, "file": name})
            if move:
                path.unlink(missing_ok=True)
        from .neural import installed as is_installed

        ready = sorted({i["model"] for i in installed if is_installed(self.root, i["model"])})
        return {"installed": installed, "ignored": ignored, "ready": ready}

    def scan(self, folder: Path | None = None) -> dict[str, Any]:
        """« Chercher dans Téléchargements » : seuls les fichiers de la bonne taille sont lus (rapide même si le dossier est plein)."""
        folder = folder or Path(os.environ.get("USERPROFILE") or Path.home()) / "Downloads"
        sizes = {f.size for spec in self._specs().values() for f in spec.files.values()}
        found = []
        try:
            for entry in os.scandir(folder):
                try:
                    if entry.is_file() and entry.stat().st_size in sizes:
                        found.append(Path(entry.path))
                except OSError:
                    continue
        except OSError as error:
            raise DownloadError(f"Dossier illisible : {folder}", str(error)[:200]) from error
        return {**self.install_files(found), "folder": str(folder), "looked_at": len(found)}


__all__ = ["Downloads", "DownloadError", "PythonFetch", "BitsFetch", "bases", "sha256", "blocked_hint"]
