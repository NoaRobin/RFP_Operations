"""Accès au site depuis le poste, sans navigateur.

1. Python (httpx) avec les certificats et le proxy déclarés dans Windows (truststore + registre) : rapide, en parallèle.
2. Sinon, la connexion de Windows elle-même (WinINet, via COM) : exactement celle d'Edge — proxy d'entreprise, script PAC,
   authentification automatique, certificats de l'entreprise.

Le premier transport qui répond est gardé pour la suite. Chaque échec devient un code simple (proxy, certificat…), que
`problems.py` traduit en phrase compréhensible.
"""
from __future__ import annotations

import ssl
import sys
import threading
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RFP-pas-envie-de-travailler/2.0 (documents reglementaires publics)"
TIMEOUT = 30


@dataclass
class Reply:
    status: int
    content: bytes
    content_type: str
    url: str

    @property
    def is_pdf(self) -> bool:
        return self.content[:5] == b"%PDF-"


class NetError(Exception):
    """code : proxy | certificat | hors-ligne | delai | reseau."""

    def __init__(self, code: str, detail: str = "", host: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.host = code, detail, host


def _classify(error: Exception, host: str) -> NetError:
    text = f"{type(error).__name__} {error}".lower()
    if isinstance(error, httpx.ProxyError) or "407" in text or "proxy" in text:
        return NetError("proxy", str(error), host)
    if "certificate" in text or "ssl" in text or "tls" in text:
        return NetError("certificat", str(error), host)
    if isinstance(error, httpx.TimeoutException) or "timed out" in text or "timeout" in text:
        return NetError("delai", str(error), host)
    if "getaddrinfo" in text or "name or service" in text or "nodename" in text or "resolve" in text or "dns" in text:
        return NetError("hors-ligne", str(error), host)
    return NetError("reseau", str(error), host)


class PythonTransport:
    name = "python"
    label = "Python (certificats et proxy de Windows)"

    def __init__(self, timeout: float = TIMEOUT):
        verify: ssl.SSLContext | bool = True
        try:  # magasin de certificats du système : indispensable derrière une inspection TLS d'entreprise
            import truststore

            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:  # noqa: BLE001
            pass
        proxies = urllib.request.getproxies()  # sous Windows : lit aussi le proxy déclaré dans les paramètres Internet
        proxy = proxies.get("https") or proxies.get("http")
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, verify=verify, proxy=proxy or None, trust_env=not proxy,
                                    headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"})

    def get(self, url: str) -> Reply:
        host = urlparse(url).netloc
        try:
            r = self._client.get(url)
        except httpx.HTTPError as error:
            raise _classify(error, host) from error
        except ssl.SSLError as error:
            raise NetError("certificat", str(error), host) from error
        if r.status_code == 407:
            raise NetError("proxy", "authentification proxy demandée (407)", host)
        return Reply(r.status_code, r.content, r.headers.get("content-type", ""), str(r.url))


class WindowsTransport:
    """WinINet (MSXML2.XMLHTTP) : la pile réseau d'Edge et d'Outlook. Windows seulement (pywin32)."""
    name = "windows"
    label = "Connexion de Windows (comme Edge)"

    def __init__(self):
        self._local = threading.local()

    @staticmethod
    def available() -> bool:
        if sys.platform != "win32":
            return False
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError:
            return False
        return True

    def _request(self):
        if getattr(self._local, "xhr", None) is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()  # un appartement COM par fil de téléchargement
            self._local.xhr = win32com.client.Dispatch("MSXML2.XMLHTTP.6.0")
        return self._local.xhr

    def get(self, url: str) -> Reply:
        host = urlparse(url).netloc
        try:
            xhr = self._request()
            xhr.open("GET", url, False)
            xhr.setRequestHeader("User-Agent", USER_AGENT)
            xhr.send()
            status = int(xhr.status)
            body = bytes(xhr.responseBody or b"") if status == 200 else b""
            content_type = str(xhr.getResponseHeader("Content-Type") or "")
        except Exception as error:  # noqa: BLE001 - erreurs COM : codes WinINet
            raise _classify(error, host) from error
        if status == 407:
            raise NetError("proxy", "authentification proxy demandée (407)", host)
        return Reply(status, body, content_type, url)


class Network:
    """Essaie les transports dans l'ordre ; garde celui qui a répondu pour les demandes suivantes."""

    def __init__(self, transports: list):
        self.transports = transports
        self._preferred = None
        self._lock = threading.Lock()

    @property
    def active(self) -> str:
        return (self._preferred or self.transports[0]).label if self.transports else "aucun"

    def get(self, url: str) -> Reply:
        order = ([self._preferred] if self._preferred else []) + [t for t in self.transports if t is not self._preferred]
        last: NetError | None = None
        for transport in order:
            try:
                reply = transport.get(url)
            except NetError as error:
                last = error
                continue
            with self._lock:
                self._preferred = transport
            return reply
        raise last or NetError("reseau", "aucun transport disponible", urlparse(url).netloc)

    def check(self, url: str) -> tuple[bool, NetError | None, int]:
        """Le site répond-il ? (n'importe quel code HTTP vaut « joignable »)."""
        try:
            return True, None, self.get(url).status
        except NetError as error:
            return False, error, 0


def default_network() -> Network:
    transports: list = [PythonTransport()]
    if WindowsTransport.available():
        transports.append(WindowsTransport())
    return Network(transports)
