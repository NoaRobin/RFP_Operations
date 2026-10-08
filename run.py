"""Lanceur Grimoire — double-cliquer sur run.bat (Windows) ou `python run.py`.

Ce qu'il fait, sans rien demander :
1. crée (une fois) un environnement Python hors du projet : %LOCALAPPDATA%\\Grimoire (ou ~/.cache/grimoire) ;
2. installe les dépendances manquantes (quelques minutes la première fois) ;
3. démarre le serveur et ouvre le navigateur.

La connexion à Fabric se fait ensuite dans l'application : bouton « Se connecter à Fabric », adresse du serveur,
votre identifiant, une fenêtre Microsoft s'ouvre. C'est tout.

Options : --port 8080 · --no-browser · --demo (force les données fictives) · --doctor (diagnostic) · --rebuild (front, Node requis)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONT = ROOT / "frontend"
DIST = FRONT / "dist" / "index.html"
WIN = os.name == "nt"
REQUIRED = ["fastapi", "uvicorn", "pandas", "openpyxl", "docx", "sqlglot", "apscheduler", "yaml", "plotly", "multipart", "sse_starlette"]


def say(msg: str) -> None:
    print(f"  ✦ {msg}", flush=True)


def fail(msg: str, hint: str = "") -> None:
    print(f"\n  ✗ {msg}")
    if hint:
        print(f"    → {hint}")
    print()
    sys.exit(1)


def venv_dir() -> Path:
    custom = os.environ.get("GRIMOIRE_VENV")
    if custom:
        return Path(custom)
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") if WIN else Path.home() / ".cache"
    return base / ("Grimoire" if WIN else "grimoire") / f"venv-py{sys.version_info.major}{sys.version_info.minor}"


def venv_python(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if WIN else "bin/python")


def has_modules(py: Path, modules: list[str]) -> bool:
    code = "import importlib.util,sys;sys.exit(0 if all(importlib.util.find_spec(m) for m in %r) else 1)" % modules
    return subprocess.run([str(py), "-c", code], capture_output=True).returncode == 0


def ensure_environment() -> Path:
    if sys.version_info < (3, 10):
        fail("Python 3.10 ou plus récent est requis.", "Installez Python depuis python.org (cocher « Add Python to PATH »).")
    folder = venv_dir()
    py = venv_python(folder)
    if not py.exists():
        say(f"Premier lancement : création de l'environnement Python ({folder})…")
        folder.parent.mkdir(parents=True, exist_ok=True)
        try:
            venv.create(folder, with_pip=True)
        except Exception as error:  # noqa: BLE001
            fail(f"Création de l'environnement impossible : {error}",
                 "Sous Windows, réinstallez Python depuis python.org ; ou définissez GRIMOIRE_VENV vers un dossier accessible.")
    modules = REQUIRED + (["mssql_python"] if WIN else [])
    if not has_modules(py, modules):
        say("Installation des dépendances (quelques minutes la première fois)…")
        cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(BACKEND / "requirements.txt")]
        if subprocess.run(cmd).returncode != 0:
            fail("L'installation des dépendances a échoué.",
                 "Proxy d'entreprise ? `set HTTPS_PROXY=http://proxy:port` puis relancez. Sinon : python run.py --doctor")
    return py


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_port(wanted: int) -> int:
    for port in range(wanted, wanted + 20):
        if port_free(port):
            return port
    fail(f"Aucun port libre entre {wanted} et {wanted + 19}.", "Fermez les autres instances de Grimoire.")
    return wanted


def open_when_ready(url: str, browser: bool, proc: subprocess.Popen) -> None:
    def wait() -> None:
        for _ in range(240):
            if proc.poll() is not None:
                return
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=1):
                    say(f"Grimoire est prêt : {url}")
                    if browser:
                        webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.5)

    threading.Thread(target=wait, daemon=True).start()


def rebuild_front() -> None:
    npm = shutil.which("npm")
    if not npm:
        fail("Node.js est requis pour reconstruire l'interface.", "Inutile en temps normal : l'interface est livrée compilée.")
    say("Reconstruction de l'interface…")
    subprocess.run([npm, "install"], cwd=FRONT, check=True, shell=WIN)
    subprocess.run([npm, "run", "build"], cwd=FRONT, check=True, shell=WIN)


def doctor() -> None:
    print(f"\n  Python        : {sys.version.split()[0]} ({sys.executable})")
    print(f"  Système       : {platform.platform()}")
    print(f"  Projet        : {ROOT}")
    if len(str(ROOT)) > 180 or "onedrive" in str(ROOT).lower():
        print("  ⚠ Projet dans OneDrive ou chemin très long : préférez un dossier court et local (ex. C:\\dev\\Grimoire).")
    folder = venv_dir()
    print(f"  Environnement : {folder} ({'présent' if venv_python(folder).exists() else 'absent'})")
    print(f"  Interface     : {'compilée' if DIST.exists() else 'ABSENTE — git pull, ou python run.py --rebuild'}")
    print(f"  Proxy         : {os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or 'aucun'}")
    print(f"  Port 8000     : {'libre' if port_free(8000) else 'occupé (un autre port sera choisi)'}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lance Grimoire.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="données fictives uniquement")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    print("\n  ✦ GRIMOIRE — #RFPasenviedetravailler\n")
    if args.doctor:
        doctor()
        return
    if args.rebuild:
        rebuild_front()
    if not DIST.exists():
        fail("L'interface compilée est absente (frontend/dist).", "Faites un `git pull` ou lancez `python run.py --rebuild` (Node.js requis).")
    py = ensure_environment()
    port = pick_port(args.port)
    env = dict(os.environ)
    env.setdefault("MERLIN_DATA_MODE", "mock" if args.demo else "auto")
    env.setdefault("MERLIN_CORS_ORIGINS", f"http://127.0.0.1:{port},http://localhost:{port}")
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([str(py), "-m", "uvicorn", "merlin.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=BACKEND, env=env)
    open_when_ready(url, not args.no_browser, proc)
    say("Fermez cette fenêtre (ou Ctrl+C) pour arrêter Grimoire.")
    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        say("À bientôt.")


if __name__ == "__main__":
    main()
