"""Envoi des requêtes SOAP depuis le poste : Python (certificats et proxy de Windows), puis la connexion de Windows.

Même principe que `merlin/fundshop/net.py` (repris ici sans le modifier) : derrière un proxy d'entreprise ou une
inspection TLS, la pile réseau de Windows (WinINet, celle d'Edge) passe souvent quand Python seul échoue.
"""
from __future__ import annotations

import ssl
import sys
import threading
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..fundshop.net import NetError, _classify

TIMEOUT = 60


@dataclass
class SoapReply:
    status: int
    content: bytes


class PythonSoap:
    name = "python"

    def __init__(self, timeout: float = TIMEOUT):
        verify: ssl.SSLContext | bool = True
        try:
            import truststore

            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:  # noqa: BLE001
            pass
        proxies = urllib.request.getproxies()
        proxy = proxies.get("https") or proxies.get("http")
        common = dict(timeout=timeout, follow_redirects=False, verify=verify)
        self._client = httpx.Client(proxy=proxy or None, trust_env=not proxy, **common)
        self._direct = httpx.Client(trust_env=False, **common) if proxy else self._client

    def post(self, url: str, body: bytes, action: str) -> SoapReply:
        host = urlparse(url).netloc
        try:
            client = self._direct if urllib.request.proxy_bypass(host.split(":")[0]) else self._client
            r = client.post(url, content=body, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{action}"'})
        except httpx.HTTPError as error:
            raise _classify(error, host) from error
        except ssl.SSLError as error:
            raise NetError("certificat", str(error), host) from error
        if r.status_code == 407:
            raise NetError("proxy", "authentification proxy demandée (407)", host)
        return SoapReply(r.status_code, r.content)


class WindowsSoap:
    """MSXML2.XMLHTTP (WinINet) : proxy d'entreprise, script PAC et certificats de Windows. Windows seulement."""
    name = "windows"

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

    def post(self, url: str, body: bytes, action: str) -> SoapReply:
        host = urlparse(url).netloc
        try:
            if getattr(self._local, "xhr", None) is None:
                import pythoncom
                import win32com.client

                pythoncom.CoInitialize()
                self._local.xhr = win32com.client.Dispatch("MSXML2.XMLHTTP.6.0")
            xhr = self._local.xhr
            xhr.open("POST", url, False)
            xhr.setRequestHeader("Content-Type", "text/xml; charset=utf-8")
            xhr.setRequestHeader("SOAPAction", f'"{action}"')
            xhr.send(body.decode("utf-8"))
            return SoapReply(int(xhr.status), bytes(xhr.responseBody or b""))
        except Exception as error:  # noqa: BLE001 - erreurs COM : traduites en code simple
            raise _classify(error, host) from error


class SoapTransport:
    """Python d'abord ; si le réseau bloque (proxy, certificat), la connexion de Windows ; le transport qui marche est gardé."""

    def __init__(self, transports: list | None = None):
        if transports is None:
            transports = [PythonSoap()] + ([WindowsSoap()] if WindowsSoap.available() else [])
        self.transports = transports
        self.active = transports[0] if transports else None

    def post(self, url: str, body: bytes, action: str) -> SoapReply:
        errors: list[NetError] = []
        order = [self.active] + [t for t in self.transports if t is not self.active]
        for t in order:
            try:
                reply = t.post(url, body, action)
                self.active = t
                return reply
            except NetError as error:
                errors.append(error)
                if error.code not in {"proxy", "certificat", "reseau"}:
                    break
        raise errors[-1] if errors else NetError("reseau", "aucun transport", urlparse(url).netloc)


__all__ = ["SoapTransport", "SoapReply", "PythonSoap", "WindowsSoap", "NetError"]
