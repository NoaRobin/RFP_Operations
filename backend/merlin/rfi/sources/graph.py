"""SharePoint via Microsoft Graph : connexion Microsoft interactive (MSAL, client public, droits délégués de l'utilisateur).

Aucun secret : l'application Entra ID est un « client public » ; le jeton est mis en cache sur le poste
(data/rfi/graph_token_cache.bin, jamais committé). Lecture seule : rien n'est jamais écrit dans SharePoint.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from ...config import SharePointSettings
from .base import RemoteItem, SourceError

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["https://graph.microsoft.com/Sites.Read.All"]
SELECT = "id,name,folder,file,webUrl,lastModifiedDateTime,size"


class GraphSharePointSource:
    name = "SharePoint (Microsoft Graph)"

    def __init__(self, settings: SharePointSettings, cache_path: Path):
        self.settings = settings
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._app = None
        self._cache = None
        self._drive: str | None = None
        self._http: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        """Un seul client (connexions gardées ouvertes) : chaque dossier listé ne rouvre plus une connexion TLS."""
        if self._http is None:
            verify: object = True
            try:  # certificats de l'entreprise (inspection TLS du proxy)
                import ssl

                import truststore

                verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            except Exception:  # noqa: BLE001
                pass
            self._http = httpx.Client(timeout=httpx.Timeout(60, connect=20), follow_redirects=True, verify=verify,
                                      limits=httpx.Limits(max_connections=8, max_keepalive_connections=8))
        return self._http

    # ------------------------------------------------------------------ authentification
    def _msal(self):
        if self._app is not None:
            return self._app
        try:
            import msal  # type: ignore[import-not-found]
        except ImportError as error:
            raise SourceError("Le module msal n'est pas installé.", "pip install msal (déjà listé dans requirements.txt)") from error
        self._cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            self._cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        self._app = msal.PublicClientApplication(self.settings.client_id, token_cache=self._cache,
                                                 authority=f"https://login.microsoftonline.com/{self.settings.tenant_id}")
        return self._app

    def _save_cache(self) -> None:
        if self._cache is not None and self._cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def _token(self, interactive: bool = True) -> str:
        if not self.settings.graph_configured:
            raise SourceError("Connexion SharePoint non configurée.", "Renseignez SHAREPOINT_CLIENT_ID (application Entra ID fournie par l'IT) "
                                                                    "ou utilisez le dossier synchronisé OneDrive.")
        with self._lock:
            app = self._msal()
            accounts = app.get_accounts()
            result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
            if not result and interactive:
                result = app.acquire_token_interactive(SCOPES, prompt="select_account")
            self._save_cache()
        if not result or "access_token" not in result:
            detail = (result or {}).get("error_description", "connexion annulée")
            raise SourceError("Connexion Microsoft impossible.", str(detail)[:300])
        return result["access_token"]

    def _get(self, url: str, stream_to: Path | None = None, interactive: bool = True) -> httpx.Response:
        """GET avec relances : limitation SharePoint (429 / 503, en-tête Retry-After), coupure réseau, jeton expiré (401 :
        un nouveau jeton silencieux). Les erreurs restantes deviennent des SourceError (plus jamais d'erreur 500 brute)."""
        last: Exception | None = None
        for attempt in range(5):
            headers = {"Authorization": f"Bearer {self._token(interactive)}"}
            try:
                if stream_to is None:
                    response = self._client().get(url, headers=headers)
                else:
                    with self._client().stream("GET", url, headers=headers) as response:
                        if response.status_code == 200:
                            part = stream_to.with_name(stream_to.name + ".part")
                            stream_to.parent.mkdir(parents=True, exist_ok=True)
                            with part.open("wb") as f:
                                for chunk in response.iter_bytes(1 << 20):
                                    f.write(chunk)
                            os.replace(part, stream_to)
                        else:
                            response.read()
            except httpx.HTTPError as error:
                last = error
                time.sleep(min(30, 2 ** attempt))
                continue
            code = response.status_code
            if code in (429, 503, 502, 504):
                wait = float(response.headers.get("Retry-After") or 2 ** attempt)
                last = SourceError("SharePoint demande de ralentir.", f"HTTP {code}", transient=True, retry_after=wait)
                time.sleep(min(60.0, wait))
                continue
            if code == 401 and attempt == 0:
                self._forget_token()
                continue
            if code == 404:
                raise SourceError("Élément introuvable dans SharePoint (déplacé ou renommé ?).")
            if code in (401, 403):
                raise SourceError("Accès refusé par SharePoint.", "Vérifiez vos droits sur le site et l'autorisation Sites.Read.All.")
            if code >= 400:
                raise SourceError(f"SharePoint a répondu HTTP {code}.", response.text[:200] if stream_to is None else "", transient=code >= 500)
            return response
        if isinstance(last, SourceError):
            raise last
        raise SourceError("SharePoint injoignable.", f"Réseau ou proxy : {type(last).__name__ if last else 'inconnu'}", transient=True)

    def _forget_token(self) -> None:
        """Jeton refusé : le prochain appel en redemande un en silence (le compte reste en cache)."""
        with self._lock:
            app = self._msal()
            for account in app.get_accounts():
                try:
                    app.acquire_token_silent(SCOPES, account=account, force_refresh=True)
                except Exception:  # noqa: BLE001
                    pass
            self._save_cache()

    # ------------------------------------------------------------------ site / bibliothèque
    def _drive_id(self) -> str:
        if self._drive:
            return self._drive
        u = urlparse(self.settings.site_url)
        site = self._get(f"{GRAPH}/sites/{u.hostname}:{u.path}").json()
        drives = self._get(f"{GRAPH}/sites/{site['id']}/drives").json().get("value", [])
        wanted = {self.settings.library.lower(), "documents", "documents partagés", "shared documents"}
        lib_url = quote(self.settings.library)
        for d in drives:
            if d.get("name", "").lower() in wanted or d.get("webUrl", "").rstrip("/").endswith("/" + lib_url):
                self._drive = d["id"]
                return self._drive
        raise SourceError(f"Bibliothèque « {self.settings.library} » introuvable sur le site.")

    def status(self) -> dict:
        if not self.settings.graph_configured:
            return {"source": self.name, "ready": False, "signed_in": False,
                    "hint": "SHAREPOINT_CLIENT_ID non renseigné : utilisez le dossier synchronisé, ou demandez à l'IT une application Entra ID."}
        try:
            app = self._msal()
            signed = bool(app.get_accounts())
        except SourceError as error:
            return {"source": self.name, "ready": False, "signed_in": False, "hint": error.hint}
        return {"source": self.name, "ready": True, "signed_in": signed, "site": self.settings.site_url,
                "hint": "" if signed else "Une fenêtre Microsoft s'ouvrira à la première navigation."}

    def children(self, path: str) -> list[RemoteItem]:
        full = "/".join(p for p in (self.settings.root.strip("/"), path.strip("/")) if p)
        url = f"{GRAPH}/drives/{self._drive_id()}/root:/{quote(full)}:/children?$select={SELECT}&$top=200"
        items: list[RemoteItem] = []
        while url:
            data = self._get(url).json()
            for v in data.get("value", []):
                rel = f"{path}/{v['name']}".strip("/")
                items.append(RemoteItem(id=v["id"], name=v["name"], path=rel, is_folder="folder" in v, url=v.get("webUrl", ""),
                                        modified=v.get("lastModifiedDateTime", ""), size=int(v.get("size") or 0)))
            url = data.get("@odata.nextLink")
        return sorted(items, key=lambda i: i.name.lower())

    def download(self, item: RemoteItem, target: Path) -> Path:
        """Écrit au fil de l'eau dans un .part puis renomme : un gros RFI ne passe plus par la mémoire, et une coupure
        ne laisse jamais un fichier tronqué."""
        self._get(f"{GRAPH}/drives/{self._drive_id()}/items/{item.id}/content", stream_to=target)
        return target
