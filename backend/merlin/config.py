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
    user: str = ""
    client: str = "mssql-python"
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    timeout: int = 30

    @property
    def configured(self) -> bool:
        return bool(self.server and self.database)


@dataclass(frozen=True)
class SharePointSettings:
    """Bibliothèque SharePoint des RFI déjà répondus (AM RFP CONF DOC)."""
    site_url: str = "https://reachbcp1.sharepoint.com/sites/S001314"
    library: str = "Shared Documents"
    root: str = "1 - Appels d'offres - Due diligence"
    local_dir: str = ""  # dossier synchronisé OneDrive (alternative sans inscription d'application)
    client_id: str = ""  # application Entra ID (client public, droits délégués Sites.Read.All)
    tenant_id: str = "organizations"

    @property
    def graph_configured(self) -> bool:
        return bool(self.client_id and self.site_url)


@dataclass(frozen=True)
class OmniSettings:
    """OMNI mensuel (Holdings + performances NET / GROSS rangés par trimestre)."""
    root: str = ""  # …\3 - Consultants (dossier synchronisé) ; vide = data/omni
    inbox: str = ""  # dossier de dépôt des performances ; vide = data/omni/depot
    sender: str = ""  # expéditeur Outlook des performances
    subject_words: str = "perf,omni"
    jump_script: str = ""  # JUMP_OMNI.py (mode « JUMP Excel », Windows)


@dataclass(frozen=True)
class FundShopSettings:
    """Téléchargement des documents des fonds (liste à la carte, en boucle)."""
    dest_dir: str = ""  # ex. …\7 - Ressources\Stagiaire\FundShop ; vide = data/fundshop/documents
    docs_base: str = "https://docs.am.eu.rothschildandco.com"
    site_base: str = "https://am.eu.rothschildandco.com/fr/nos-fonds/"


@dataclass(frozen=True)
class FundDocumentSettings:
    """DIC PRIIPs et prospectus : site public des fonds, dossier local, dépôts manuels."""
    mode: str = "auto"  # auto : site utilisé seulement avec Fabric (fonds réels) | on | off
    site_url: str = "https://am.eu.rothschildandco.com"
    fund_path: str = "/en/our-funds/{slug}/"
    search_path: str = "/en/search/?q={isin}"
    local_dir: str = ""  # dossier synchronisé « Documentation » (PDF nommés avec l'ISIN)


@dataclass(frozen=True)
class QvidianSettings:
    """Qvidian (QPA) : services web SOAP. Identifiants et mot de passe d'écriture : uniquement dans .env, jamais dans le code."""
    mode: str = "auto"  # auto : Qvidian si connecté, sinon bibliothèque de démonstration | demo | off
    auth_url: str = "https://qpalogin.qvidian.eu/QvidianAuthentication.asmx"
    user: str = ""
    password: str = ""
    api_key: str = ""
    subscriber_suffix: str = ""  # SSO : identifiant de l'abonnement sur le portail QPA
    write_password: str = ""  # mot de passe des modifications en masse (QVIDIAN_WRITE_PASSWORD)
    keepalive_minutes: int = 10  # la session Qvidian expire après 20 min sans appel : petit appel de maintien (0 = jamais)
    half_life_days: int = 365  # agrégation : une réponse choisie il y a un an pèse moitié moins qu'aujourd'hui
    concurrency: int = 4  # synchronisation : dossiers lus en parallèle (1 = un à la fois)
    max_calls_per_second: float = 8.0  # limiteur de débit : ne jamais saturer le serveur Qvidian
    cache_seconds: int = 300  # lectures de détail mises en cache (0 = aucun cache)
    search_encoder: str = "e5-small"  # moteur sémantique : encodeur installé dans data/models/
    search_reranker: bool = True  # reranker cross-encoder s'il est installé

    @property
    def credentials(self) -> bool:
        return bool(self.user and (self.password or self.api_key))


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
    job_executor: str
    seed_demo_history: bool
    cors_origins: list[str] = field(default_factory=list)
    fabric: FabricSettings = field(default_factory=FabricSettings)
    sharepoint: SharePointSettings = field(default_factory=SharePointSettings)
    fund_documents: FundDocumentSettings = field(default_factory=FundDocumentSettings)
    fundshop: FundShopSettings = field(default_factory=FundShopSettings)
    omni: OmniSettings = field(default_factory=OmniSettings)
    qvidian: QvidianSettings = field(default_factory=QvidianSettings)

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
        # thread (défaut) : connexion Fabric partagée ; process : isolation totale (une connexion par job)
        job_executor=_env("MERLIN_JOB_EXECUTOR", "thread").lower(),
        seed_demo_history=_bool("MERLIN_SEED_DEMO_HISTORY", True),
        cors_origins=[o for o in _env("MERLIN_CORS_ORIGINS", "http://localhost:5173").split(",") if o],
        fabric=FabricSettings(
            server=_env("FABRIC_SQL_ENDPOINT"),
            database=_env("FABRIC_DATABASE", "LKH_RFPTeam_Bronze"),
            auth=_env("FABRIC_AUTH", "ActiveDirectoryInteractive"),
            user=_env("FABRIC_USER"),
            client=_env("FABRIC_CLIENT", "mssql-python").lower(),
            client_id=_env("FABRIC_CLIENT_ID"),
            client_secret=_env("FABRIC_CLIENT_SECRET"),
            tenant_id=_env("FABRIC_TENANT_ID"),
            odbc_driver=_env("FABRIC_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            timeout=int(_env("FABRIC_TIMEOUT", "30")),
        ),
        qvidian=QvidianSettings(
            mode=_env("QVIDIAN_MODE", "auto").lower(),
            auth_url=_env("QVIDIAN_AUTH_URL", QvidianSettings.auth_url),
            user=_env("QVIDIAN_USER"),
            password=_env("QVIDIAN_PASSWORD"),
            api_key=_env("QVIDIAN_API_KEY"),
            subscriber_suffix=_env("QVIDIAN_SUBSCRIBER_SUFFIX"),
            write_password=os.environ.get("QVIDIAN_WRITE_PASSWORD", ""),
            half_life_days=int(_env("QVIDIAN_HALF_LIFE_DAYS", "365") or 365),
            keepalive_minutes=int(_env("QVIDIAN_KEEPALIVE_MINUTES", "10") or "10"),
            concurrency=max(1, min(16, int(_env("QVIDIAN_CONCURRENCY", "4") or "4"))),
            max_calls_per_second=float(_env("QVIDIAN_MAX_CALLS_PER_SECOND", "8") or "8"),
            cache_seconds=int(_env("QVIDIAN_CACHE_SECONDS", "300") or "300"),
            search_encoder=_env("MERLIN_SEARCH_ENCODER", "e5-small") or "e5-small",
            search_reranker=(_env("MERLIN_SEARCH_RERANKER", "on") or "on").lower() not in {"off", "0", "false", "non"},
        ),
        omni=OmniSettings(
            root=_env("OMNI_ROOT"),
            inbox=_env("OMNI_INBOX"),
            sender=_env("OMNI_SENDER"),
            subject_words=_env("OMNI_SUBJECT_WORDS", "perf,omni"),
            jump_script=_env("OMNI_JUMP_SCRIPT"),
        ),
        fundshop=FundShopSettings(
            dest_dir=_env("FUNDSHOP_DIR"),
            docs_base=_env("FUNDSHOP_DOCS_BASE", FundShopSettings.docs_base),
            site_base=_env("FUNDSHOP_SITE_BASE", FundShopSettings.site_base),
        ),
        fund_documents=FundDocumentSettings(
            mode=_env("FUND_DOCS", "auto").lower(),
            site_url=_env("FUND_SITE_URL", FundDocumentSettings.site_url),
            fund_path=_env("FUND_SITE_FUND_PATH", FundDocumentSettings.fund_path),
            search_path=_env("FUND_SITE_SEARCH_PATH", FundDocumentSettings.search_path),
            local_dir=_env("FUND_DOCS_DIR"),
        ),
        sharepoint=SharePointSettings(
            site_url=_env("SHAREPOINT_SITE_URL", SharePointSettings.site_url),
            library=_env("SHAREPOINT_LIBRARY", SharePointSettings.library),
            root=_env("SHAREPOINT_ROOT", SharePointSettings.root),
            local_dir=_env("SHAREPOINT_LOCAL_DIR"),
            client_id=_env("SHAREPOINT_CLIENT_ID"),
            tenant_id=_env("SHAREPOINT_TENANT_ID") or _env("FABRIC_TENANT_ID") or "organizations",
        ),
    )
    settings.ensure_dirs()
    return settings
