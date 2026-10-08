"""SharePoint via Microsoft Graph : connexion Microsoft interactive (MSAL, client public, droits délégués de l'utilisateur).

Aucun secret : l'application Entra ID est un « client public » ; le jeton est mis en cache sur le poste
(data/rfi/graph_token_cache.bin, jamais committé). Lecture seule : rien n'est jamais écrit dans SharePoint.
"""
from __future__ import annotations

import threading
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

    def _get(self, url: str, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()}"}
        try:
            response = httpx.get(url, headers=headers, timeout=60, follow_redirects=True, **kwargs)
        except httpx.HTTPError as error:
            raise SourceError("SharePoint injoignable.", f"Réseau ou proxy : {type(error).__name__}") from error
        if response.status_code == 404:
            raise SourceError("Élément introuvable dans SharePoint.")
        if response.status_code in (401, 403):
            raise SourceError("Accès refusé par SharePoint.", "Vérifiez vos droits sur le site et l'autorisation Sites.Read.All.")
        response.raise_for_status()
        return response

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
        response = self._get(f"{GRAPH}/drives/{self._drive_id()}/items/{item.id}/content")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target
