"""Configuration de Merlin : uniquement des variables d'environnement (voir .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# .env à la racine du dépôt puis dans backend/ (le premier trouvé gagne pour chaque clé)
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _path(name: str, default: Path) -> Path:
    raw = _env(name)
    path = Path(raw) if raw else default
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "oui", "on"}


@dataclass(frozen=True)
class FabricSettings:
    server: str = ""
    database: str = ""
    auth: str = "ActiveDirectoryInteractive"
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    timeout: int = 30

    @property
    def configured(self) -> bool:
        return bool(self.server and self.database)


@dataclass(frozen=True)
class Settings:
    data_mode: str  # auto | mock | fabric
    data_dir: Path
    automations_dir: Path
    catalog_csv: Path
    frontend_dist: Path
    timezone: str
    default_user: str
    job_timeout: int
    max_parallel_jobs: int
    seed_demo_history: bool
    cors_origins: list[str] = field(default_factory=list)
    fabric: FabricSettings = field(default_factory=FabricSettings)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "merlin.db"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def atelier_dir(self) -> Path:
        return self.data_dir / "atelier"

    @property
    def mock_db_path(self) -> Path:
        return self.data_dir / "mock_lakehouse.sqlite"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.runs_dir, self.atelier_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        data_mode=_env("MERLIN_DATA_MODE", "auto").lower(),
        data_dir=_path("MERLIN_DATA_DIR", REPO_ROOT / "data"),
        automations_dir=_path("MERLIN_AUTOMATIONS_DIR", REPO_ROOT / "automations"),
        catalog_csv=_path("MERLIN_CATALOG_CSV", REPO_ROOT / "catalog" / "fabric_schema.csv"),
        frontend_dist=_path("MERLIN_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"),
        timezone=_env("MERLIN_TIMEZONE", "Europe/Paris"),
        default_user=_env("MERLIN_DEFAULT_USER", "Utilisateur anonyme"),
        job_timeout=int(_env("MERLIN_JOB_TIMEOUT", "1800")),
        max_parallel_jobs=int(_env("MERLIN_MAX_PARALLEL_JOBS", "4")),
        seed_demo_history=_bool("MERLIN_SEED_DEMO_HISTORY", True),
        cors_origins=[o for o in _env("MERLIN_CORS_ORIGINS", "http://localhost:5173").split(",") if o],
        fabric=FabricSettings(
            server=_env("FABRIC_SQL_ENDPOINT"),
            database=_env("FABRIC_DATABASE", "LKH_RFPTeam_Bronze"),
            auth=_env("FABRIC_AUTH", "ActiveDirectoryInteractive"),
            client_id=_env("FABRIC_CLIENT_ID"),
            client_secret=_env("FABRIC_CLIENT_SECRET"),
            tenant_id=_env("FABRIC_TENANT_ID"),
            odbc_driver=_env("FABRIC_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            timeout=int(_env("FABRIC_TIMEOUT", "30")),
        ),
    )
    settings.ensure_dirs()
    return settings
