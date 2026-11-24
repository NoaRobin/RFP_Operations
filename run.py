"""Lanceur RFP pas envie de travailler — double-cliquer sur run.bat (Windows) ou `python run.py`.

Ce qu'il fait, sans rien demander :
1. crée (une fois) un environnement Python hors du projet : %LOCALAPPDATA%\\RFPpasenvie (ou ~/.cache/rfppasenvie) ;
2. installe les dépendances manquantes (quelques minutes la première fois) ;
3. démarre le serveur et ouvre le navigateur.

La connexion à Fabric est automatique dès que l'adresse du serveur est connue (fichier d'équipe `equipe.json`, écrit
au premier branchement réussi) : au plus, une fenêtre Microsoft à valider. Le premier poste se branche une fois par le
bouton « Fabric » de l'application.

Donner l'app à une collègue : double-clic sur partager.bat (ou `python run.py --partager`). Un zip propre est posé sur
le Bureau (sans vos données, sans secret) ; elle le décompresse et double-clique sur run.bat. Rien d'autre.

Options : --port 8080 · --no-browser · --demo (force les données fictives) · --doctor (diagnostic) · --partager · --rebuild (front, Node requis)
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


def venv_candidates() -> list[Path]:
    """Emplacements possibles de l'environnement, hors du projet. Le Python du Microsoft Store redirige en cachette ce
    qu'il écrit dans AppData : l'environnement créé là est alors introuvable (« failed to locate pyvenv.cfg »). Le
    dossier personnel, lui, n'est jamais redirigé : il sert de repli."""
    custom = os.environ.get("RFP_VENV") or os.environ.get("GRIMOIRE_VENV")
    if custom:
        return [Path(custom)]
    name = f"venv-py{sys.version_info.major}{sys.version_info.minor}"
    if not WIN:
        return [Path.home() / ".cache" / "rfppasenvie" / name]
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "RFPpasenvie" / name
    home = Path.home() / ".rfppasenvie" / name
    return [home, local] if "WindowsApps" in sys.executable else [local, home]


def venv_python(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if WIN else "bin/python")


def healthy(folder: Path) -> bool:
    """L'environnement existe ET son Python démarre (pyvenv.cfg présent, pip disponible)."""
    py = venv_python(folder)
    if not py.exists() or not (folder / "pyvenv.cfg").exists():
        return False
    try:
        return subprocess.run([str(py), "-c", "import pip"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def venv_dir() -> Path:
    """L'environnement en état de marche s'il y en a un, sinon le premier emplacement à essayer."""
    candidates = venv_candidates()
    return next((c for c in candidates if healthy(c)), candidates[0])


def has_modules(py: Path, modules: list[str]) -> bool:
    code = "import importlib.util,sys;sys.exit(0 if all(importlib.util.find_spec(m) for m in %r) else 1)" % modules
    return subprocess.run([str(py), "-c", code], capture_output=True).returncode == 0


def create_environment() -> Path:
    """Crée l'environnement au premier emplacement où il fonctionne vraiment ; un environnement cassé est refait."""
    problems = []
    for folder in venv_candidates():
        if healthy(folder):
            return folder
        if folder.exists():
            say("Environnement Python incomplet : il est refait…")
            shutil.rmtree(folder, ignore_errors=True)
        say(f"Création de l'environnement Python ({folder})…")
        try:
            folder.parent.mkdir(parents=True, exist_ok=True)
            venv.create(folder, with_pip=True)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{folder} : {error}")
            continue
        if healthy(folder):
            return folder
        problems.append(f"{folder} : créé mais inutilisable")
        shutil.rmtree(folder, ignore_errors=True)
    fail("Création de l'environnement Python impossible. " + " | ".join(problems),
         "Installez Python depuis python.org (pas depuis le Microsoft Store), en cochant « Add Python to PATH », puis relancez run.bat.")
    return venv_candidates()[0]


def ensure_environment() -> Path:
    if sys.version_info < (3, 10):
        fail("Python 3.10 ou plus récent est requis.", "Installez Python depuis python.org (cocher « Add Python to PATH »).")
    py = venv_python(create_environment())
    modules = REQUIRED + (["mssql_python"] if WIN else [])
    if not has_modules(py, modules):
        say("Installation des dépendances (quelques minutes la première fois)…")
        cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(BACKEND / "requirements.txt")]
        if subprocess.run(cmd).returncode != 0:
            fail("L'installation des dépendances a échoué.",
                 "Vérifiez la connexion internet (ou le VPN), puis relancez run.bat. Proxy d'entreprise : "
                 "`set HTTPS_PROXY=http://proxy:port` avant. Diagnostic : run.bat --doctor")
    return py


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_port(wanted: int) -> int:
    for port in range(wanted, wanted + 20):
        if port_free(port):
            return port
    fail(f"Aucun port libre entre {wanted} et {wanted + 19}.", "Fermez les autres instances de RFP pas envie de travailler.")
    return wanted


def open_when_ready(url: str, browser: bool, proc: subprocess.Popen) -> None:
    def wait() -> None:
        for _ in range(240):
            if proc.poll() is not None:
                return
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=1):
                    say(f"RFP pas envie de travailler est prêt : {url}")
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


SHARE_DIRS = ["backend", "automations", "catalog", "docs", "outils", "frontend/dist"]
SHARE_FILES = ["run.bat", "run.py", "run.sh", "README.md", "equipe.json", ".env.example", "JUMP_OMNI.py", "OMNI_MENSUEL.py"]
SHARE_SKIP_DIRS = {"__pycache__", ".pytest_cache", "tests", "node_modules", ".git"}


def desktop() -> Path:
    for folder in (Path.home() / "Desktop", Path.home() / "Bureau", Path.home() / "OneDrive" / "Desktop", Path.home() / "OneDrive" / "Bureau"):
        if folder.is_dir():
            return folder
    return ROOT.parent


def share() -> None:
    """Zip à donner à une collègue : le programme et les réglages d'équipe, jamais data/ ni .env (clés, mots de passe)."""
    import zipfile

    if not DIST.exists():
        fail("L'interface compilée est absente (frontend/dist).", "Faites un `git pull` avant de partager.")
    if not (ROOT / "equipe.json").exists():
        print("  ⚠ Pas encore de réglages d'équipe : lancez l'app et connectez-vous une fois à Fabric (bouton « Fabric »),\n"
              "    puis relancez partager.bat. Sans cela, votre collègue devra saisir l'adresse du serveur elle-même.\n")
    target = desktop() / "RFP pas envie de travailler.zip"
    tmp = target.with_suffix(".tmp")
    count = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SHARE_FILES:
            if (ROOT / name).is_file():
                z.write(ROOT / name, f"RFPpasenvie/{name}")
                count += 1
        for folder in SHARE_DIRS:
            for path in sorted((ROOT / folder).rglob("*")):
                rel = path.relative_to(ROOT)
                if not path.is_file() or SHARE_SKIP_DIRS & set(rel.parts) or path.suffix in {".pyc", ".log"} or path.name == ".env":
                    continue
                z.write(path, f"RFPpasenvie/{rel.as_posix()}")
                count += 1
    os.replace(tmp, target)
    say(f"Paquet prêt ({count} fichiers, {target.stat().st_size // 1_000_000} Mo) : {target}")
    print("\n    À dire à votre collègue :\n"
          "      1. Clic droit sur le zip › « Extraire tout », dans un dossier simple (ex. Documents).\n"
          "      2. Double-clic sur run.bat. La première fois, l'installation prend quelques minutes.\n"
          "      3. Si une fenêtre Microsoft s'ouvre, choisir son compte. C'est tout.\n")


def shortcut() -> None:
    """Premier lancement sous Windows : raccourci sur le Bureau (une seule fois ; l'échec est sans conséquence)."""
    marker = venv_dir().parent / "raccourci.txt"
    if not WIN or marker.exists():
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(ROOT), encoding="utf-8")
        link = desktop() / "RFP pas envie de travailler.lnk"
        script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:RFP_LNK);"
                  "$s.TargetPath=$env:RFP_BAT;$s.WorkingDirectory=$env:RFP_DIR;$s.Save()")
        env = dict(os.environ, RFP_LNK=str(link), RFP_BAT=str(ROOT / "run.bat"), RFP_DIR=str(ROOT))
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, capture_output=True, timeout=20)
        if link.exists():
            say("Raccourci créé sur le Bureau : « RFP pas envie de travailler ».")
    except Exception:  # noqa: BLE001
        pass


def doctor() -> None:
    print(f"\n  Python        : {sys.version.split()[0]} ({sys.executable})")
    print(f"  Système       : {platform.platform()}")
    print(f"  Projet        : {ROOT}")
    if len(str(ROOT)) > 180 or "onedrive" in str(ROOT).lower():
        print("  ⚠ Projet dans OneDrive ou chemin très long : préférez un dossier court et local (ex. C:\\dev\\RFPpasenvie).")
    folder = venv_dir()
    print(f"  Environnement : {folder} ({'en état de marche' if healthy(folder) else 'absent ou cassé : il sera refait au prochain lancement'})")
    if "WindowsApps" in sys.executable:
        print("  ⚠ Python du Microsoft Store : l'environnement est placé dans le dossier personnel (.rfppasenvie).")
    print(f"  Interface     : {'compilée' if DIST.exists() else 'ABSENTE — git pull, ou python run.py --rebuild'}")
    print(f"  Proxy         : {os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or 'aucun'}")
    print(f"  Fabric        : {'adresse connue (connexion automatique)' if (ROOT / 'equipe.json').exists() or (ROOT / 'data' / 'fabric.json').exists() else 'adresse inconnue : bouton « Fabric » dans l app, une fois'}")
    print(f"  Port 8000     : {'libre' if port_free(8000) else 'occupé (un autre port sera choisi)'}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lance RFP pas envie de travailler.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="données fictives uniquement")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--partager", action="store_true", help="prépare le zip à donner à une collègue")
    args = ap.parse_args()

    print("\n  ✦ RFP PAS ENVIE DE TRAVAILLER — #RFPasenviedetravailler\n  « My RFP will go on… »\n")
    if args.doctor:
        doctor()
        return
    if args.partager:
        share()
        return
    if args.rebuild:
        rebuild_front()
    if not DIST.exists():
        fail("L'interface compilée est absente (frontend/dist).", "Faites un `git pull` ou lancez `python run.py --rebuild` (Node.js requis).")
    py = ensure_environment()
    shortcut()
    port = pick_port(args.port)
    env = dict(os.environ)
    env.setdefault("MERLIN_DATA_MODE", "mock" if args.demo else "auto")
    env.setdefault("MERLIN_CORS_ORIGINS", f"http://127.0.0.1:{port},http://localhost:{port}")
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([str(py), "-m", "uvicorn", "merlin.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=BACKEND, env=env)
    open_when_ready(url, not args.no_browser, proc)
    say("Fermez cette fenêtre (ou Ctrl+C) pour arrêter RFP pas envie de travailler.")
    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        say("À bientôt.")


if __name__ == "__main__":
    main()
