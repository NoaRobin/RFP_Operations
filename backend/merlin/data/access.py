"""Couche d'accès aux données — le SEUL endroit qui parle à Fabric.

Les automatisations, l'Atelier Excel et l'API passent tous par `DataAccess`.
Deux sources interchangeables :
- `FabricSource` : SQL endpoint du Lakehouse via pyodbc (Entra ID),
- `MockSource`   : Lakehouse de démonstration en SQLite ; le SQL T-SQL est traduit à la volée.

Les requêtes utilisent des paramètres nommés `:nom` quel que soit le moteur.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
import sqlglot

from ..config import FabricSettings, Settings, get_settings
from .catalog import Catalog, load_catalog
from .mock import build_mock_lakehouse

log = logging.getLogger("merlin.data")

_PARAM = re.compile(r"'(?:[^']|'')*'|(?<![:\w]):([A-Za-z_]\w*)")


class DataError(RuntimeError):
    """Erreur d'accès aux données, avec un message lisible par un humain."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


class CatalogViolation(DataError):
    pass


def named_to_qmark(sql: str, params: dict[str, Any]) -> tuple[str, list[Any]]:
    """Convertit `:nom` en `?` (pyodbc) en conservant l'ordre d'apparition."""
    ordered: list[Any] = []

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name is None:
            return match.group(0)  # littéral chaîne : intact
        if name not in params:
            raise DataError(f"Paramètre manquant : {name}", "Vérifiez les paramètres de l'automatisation.")
        ordered.append(params[name])
        return "?"

    return _PARAM.sub(replace, sql), ordered


def used_params(sql: str) -> set[str]:
    return {m.group(1) for m in _PARAM.finditer(sql) if m.group(1)}


class Source(Protocol):
    mode: str

    def query(self, sql: str, params: dict[str, Any]) -> pd.DataFrame: ...

    def ping(self) -> bool: ...


# --------------------------------------------------------------------------- Fabric
class FabricSource:
    """SQL analytics endpoint du Lakehouse.

    Connecteur par défaut : **mssql-python** (pilote officiel Microsoft, `pip install`, aucun pilote ODBC à installer).
    Authentification par défaut : ActiveDirectoryInteractive — une fenêtre Microsoft s'ouvre, on saisit son
    identifiant, c'est tout (comme le connecteur MSSQL de VS Code). Une seule connexion par serveur, partagée.
    """

    mode = "fabric"

    def __init__(self, settings: FabricSettings):
        self.settings = settings
        self._conn = None
        self._lock = threading.Lock()

    def connection_string(self, client: str | None = None) -> str:
        s = self.settings
        client = client or s.client
        server = s.server if "," in s.server or ":" in s.server else f"{s.server},1433"
        parts = [f"Server={server}", f"Database={s.database}", "Encrypt=yes", "TrustServerCertificate=no",
                 "ApplicationIntent=ReadOnly", f"Authentication={s.auth}"]
        if s.auth == "ActiveDirectoryServicePrincipal":
            parts += [f"UID={s.client_id}", f"PWD={s.client_secret}"]
        elif s.user:
            parts.append(f"UID={s.user}")  # pré-remplit l'identifiant dans la fenêtre Microsoft
        if client == "pyodbc":
            parts.insert(0, f"Driver={{{s.odbc_driver}}}")
            parts.append(f"Connection Timeout={s.timeout}")
        return ";".join(parts)

    def _connect(self):
        if self._conn is not None:
            return self._conn
        client = self.settings.client
        try:
            if client == "pyodbc":
                import pyodbc  # facultatif

                self._conn = pyodbc.connect(self.connection_string("pyodbc"), timeout=self.settings.timeout)
            else:
                import mssql_python  # pilote Python officiel de Microsoft

                self._conn = mssql_python.connect(self.connection_string("mssql-python"))
        except ImportError as error:
            raise DataError(
                f"Le connecteur {client} n'est pas installé.",
                "Relancez run.bat : il installe mssql-python automatiquement (aucun droit administrateur requis).",
            ) from error
        except Exception as error:  # noqa: BLE001 — erreurs de pilote hétérogènes
            message = str(error)
            hint = "Vérifiez l'adresse du serveur (SQL analytics endpoint), votre identifiant et le VPN."
            if "cancel" in message.lower() or "annul" in message.lower():
                hint = "La fenêtre Microsoft a été fermée avant la fin de la connexion. Réessayez."
            raise DataError("Connexion au Lakehouse impossible.", hint + f" (détail : {message[:200]})") from error
        return self._conn

    def query(self, sql: str, params: dict[str, Any]) -> pd.DataFrame:
        statement, values = named_to_qmark(sql, params)
        with self._lock:
            conn = self._connect()
            cursor = conn.cursor()
            try:
                cursor.execute(statement, values) if values else cursor.execute(statement)
                columns = [c[0] for c in cursor.description or []]
                rows = cursor.fetchall()
            except Exception as error:  # noqa: BLE001
                self._conn = None
                raise DataError("La requête Fabric a échoué.", str(error)[:400]) from error
            finally:
                try:
                    cursor.close()
                except Exception:  # noqa: BLE001
                    pass
        return pd.DataFrame.from_records([tuple(r) for r in rows], columns=columns)

    def ping(self) -> bool:
        try:
            self.query("SELECT 1 AS ok", {})
            return True
        except DataError as error:
            log.warning("Fabric injoignable : %s", error)
            return False


# --------------------------------------------------------------------------- Mock
class MockSource:
    mode = "mock"

    def __init__(self, catalog: Catalog, settings: Settings):
        self.path = build_mock_lakehouse(catalog, settings.mock_db_path)
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect("file::memory:", uri=True, check_same_thread=False)
            # lecture seule : le mock se comporte comme un SQL endpoint (pas d'écriture possible)
            conn.execute("ATTACH DATABASE ? AS dbo", (f"file:{self.path.as_posix()}?mode=ro",))
            self._local.conn = conn
        return conn

    @staticmethod
    def translate(sql: str) -> str:
        try:
            return sqlglot.transpile(sql, read="tsql", write="sqlite")[0]
        except sqlglot.errors.SqlglotError as error:
            raise DataError("Requête non traduisible pour le mode démo.", str(error)) from error

    def query(self, sql: str, params: dict[str, Any]) -> pd.DataFrame:
        statement = self.translate(sql)
        clean = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in params.items()}
        missing = used_params(statement) - set(clean)
        if missing:
            raise DataError(f"Paramètre manquant : {', '.join(sorted(missing))}", "Vérifiez les paramètres de l'automatisation.")
        try:
            cursor = self._conn().execute(statement, clean)
        except sqlite3.Error as error:
            raise DataError("La requête de démonstration a échoué.", f"{error} — SQL : {statement}") from error
        columns = [c[0] for c in cursor.description or []]
        return pd.DataFrame.from_records(cursor.fetchall(), columns=columns)

    def ping(self) -> bool:
        return True


# --------------------------------------------------------------------------- façade
@dataclass
class QueryStats:
    rows: int
    seconds: float


class DataAccess:
    """Point d'entrée unique vers les données. Valide chaque requête contre le catalogue."""

    def __init__(self, source: Source, catalog: Catalog):
        self.source = source
        self.catalog = catalog
        self.last_stats: QueryStats | None = None

    @property
    def mode(self) -> str:
        return self.source.mode

    def query(self, sql: str, params: dict[str, Any] | None = None, *, validate: bool = True) -> pd.DataFrame:
        if validate:
            problems = self.catalog.validate_sql(sql)
            if problems:
                raise CatalogViolation(
                    "La requête cite des éléments absents du catalogue Fabric.",
                    " ; ".join(problems),
                )
        started = time.perf_counter()
        frame = self.source.query(sql, params or {})
        self.last_stats = QueryStats(len(frame), time.perf_counter() - started)
        return frame

    def ping(self) -> bool:
        return self.source.ping()


_resolved_mode: str | None = None


def resolve_mode(settings: Settings | None = None) -> str:
    """auto → fabric si configuré ET joignable, sinon mock. Résultat mis en cache."""
    global _resolved_mode
    if _resolved_mode:
        return _resolved_mode
    settings = settings or get_settings()
    mode = settings.data_mode
    if mode == "auto":
        if settings.fabric.configured and FabricSource(settings.fabric).ping():
            mode = "fabric"
        else:
            mode = "mock"
            log.info("Fabric non configuré ou injoignable : mode démonstration activé.")
    _resolved_mode = mode
    return mode


_shared: DataAccess | None = None


def set_shared(access: DataAccess) -> None:
    """Accès partagé du processus : une seule connexion Fabric (une seule fenêtre Microsoft) pour tout Merlin."""
    global _shared, _resolved_mode
    _shared = access
    _resolved_mode = access.mode


def shared() -> DataAccess | None:
    return _shared


def build_data_access(mode: str | None = None, settings: Settings | None = None) -> DataAccess:
    if _shared is not None and (mode is None or mode == _shared.mode):
        return _shared
    settings = settings or get_settings()
    catalog = load_catalog(str(settings.catalog_csv))
    mode = mode or resolve_mode(settings)
    source: Source = FabricSource(settings.fabric) if mode == "fabric" else MockSource(catalog, settings)
    return DataAccess(source, catalog)
