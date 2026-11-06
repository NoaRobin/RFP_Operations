"""Client des services web Qvidian (QPA) — uniquement les opérations confirmées par le WSDL et les exemples fournis.

Connexion (QvidianAuthentication.asmx) : Connect(userName, password), ConnectByAPIKey(userName, apiKey) ou
ConnectByAuthToken(userName, authToken) (jeton SSO, ou reconnexion) → ConnectionBinding {AuthToken, QvidianURL…}.
Ensuite chaque appel à Qvidian.asmx porte l'en-tête SOAP QvidianCredentialHeader/AuthenticationToken.

Lecture : dossiers et contenus de la bibliothèque, recherche, détail d'un contenu, fichier, aperçu HTML, projets et
leurs documents, journal d'audit, permissions. Écriture : libraryContentDetailsUpdate (métadonnées en masse), appelée
uniquement par `bulk.py` après contrôle du mot de passe d'écriture.
"""
from __future__ import annotations

import base64
import html
import re
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from . import soap
from .soap import Items, RawXml, SoapFault, as_list
from .telemetry import READ_CACHE_TTL, RETRY_CODES, WRITE_OPS, RateLimiter, Telemetry, TtlCache, backoff
from .transport import NetError, SoapTransport

DEFAULT_AUTH_URL = "https://qpalogin.qvidian.eu/QvidianAuthentication.asmx"  # adresse de l'exemple WSManual (à confirmer)
# Champs de recherche utilisés dans les exemples (confirmés) ; les autres colonnes sont tentées puis abandonnées si refusées
SEARCH_FIELDS = ["ContentID", "Revision", "ContentTypeName", "Title", "ContentFileExt", "LCIDLanguage", "Enabled", "ContentText"]
SEARCH_FIELDS_EXTRA = ["DateLastModified", "DateLastUsed", "TimesUsedCount", "Expired", "DateToExpire", "LibraryFolderPath", "LibraryFolderID",
                       "DateCreated", "CheckedOut", "CheckedOutByUserName", "LCID", "AlertText", "InlineEdit"]


class QvidianError(Exception):
    """code : config | auth | permission | proxy | certificat | hors-ligne | delai | reseau | qvidian."""

    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


HINTS = {
    "config": "Renseignez QVIDIAN_AUTH_URL et l'identifiant Qvidian dans .env, ou connectez-vous depuis la fenêtre Qvidian.",
    "auth": "Identifiant, mot de passe ou clé d'API refusés. En SSO, utilisez le bouton « Se connecter avec le SSO ».",
    "permission": "Votre compte Qvidian n'a pas ce droit : demandez-le à l'administrateur Qvidian.",
    "proxy": "Le proxy de l'entreprise bloque Qvidian. L'app a aussi essayé la connexion de Windows.",
    "certificat": "Certificat refusé (inspection TLS de l'entreprise ?).",
    "hors-ligne": "Adresse Qvidian introuvable : vérifiez QVIDIAN_AUTH_URL et le réseau.",
    "delai": "Qvidian ne répond pas assez vite : réessayez plus tard.",
    "reseau": "Problème réseau vers Qvidian.",
    "qvidian": "Qvidian a refusé la demande (message ci-dessus).",
}


@dataclass
class Binding:
    token: str
    user: str
    qvidian_url: str
    urls: dict[str, str]


def _bool(v: Any) -> bool:
    return str(v).strip().lower() == "true"


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _date(v: Any) -> str | None:
    """« 2024-03-05T10:20:00 » → « 2024-03-05 » ; la date minimale .NET (0001-01-01) veut dire « jamais »."""
    if not v or not isinstance(v, str) or v.startswith("0001-01-01"):
        return None
    return v[:10] if re.match(r"\d{4}-\d{2}-\d{2}", v) else None


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    if not markup:
        return ""
    if "<" not in markup:
        return html.unescape(markup).strip()
    p = _Text()
    p.feed(markup)
    text = "".join(p.parts)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t ]+", " ", text)).strip()


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"</(p|div|span|li|td|b|i|strong|em)>|<br\s*/?>", text or "", re.I))


EXCERPT_CHARS = 1000  # ContentText des listes et de la recherche : extrait limité à ~1000 caractères par Qvidian


def is_excerpt(c: dict[str, Any]) -> bool:
    """Texte probablement coupé par Qvidian (extrait des listes) : le texte entier se lit par l'aperçu ou les détails."""
    raw = c.get("raw_text") or c.get("text") or ""
    return len(raw) >= EXCERPT_CHARS - 10 and len(c.get("text") or "") <= EXCERPT_CHARS


def normalize_content(c: dict[str, Any]) -> dict[str, Any]:
    """Objet Content du WSDL → dictionnaire simple (types Python, dates ISO)."""
    raw_text = c.get("ContentText") or ""
    meta = c.get("SubmittedContentMetadata") or {}
    return {
        "id": _int(c.get("ContentID")), "revision": _int(c.get("Revision")), "guid": c.get("GUID") or "",
        "folder_id": _int(c.get("LibraryFolderID")), "folder": c.get("LibraryFolderTitle") or "", "folder_path": c.get("LibraryFolderPath") or "",
        "title": (c.get("Title") or "").strip(), "text": html_to_text(raw_text) if looks_like_html(raw_text) else raw_text.strip(),
        "raw_text": raw_text, "type": c.get("ContentTypeName") or c.get("ContentType") or "", "language": c.get("LCIDLanguage") or "",
        "lcid": _int(c.get("LCID")), "enabled": _bool(c.get("Enabled", "true")), "expired": _bool(c.get("Expired")),
        "created": _date(c.get("DateCreated")), "modified": _date(c.get("DateLastModified")), "last_used": _date(c.get("DateLastUsed")),
        "expires": _date(c.get("DateToExpire")), "content_updated": _date(c.get("DateContentUpdated")),
        "times_used": _int(c.get("TimesUsedCount")), "owners": c.get("CurrentOwnersName") or c.get("Owners") or "",
        "modified_by": c.get("LastModifiedByUserName") or "", "alert_text": c.get("AlertText") or "",
        "alert_active": _bool(c.get("AlertActive")), "inline_edit": _bool(c.get("InlineEdit")),
        "checked_out": _bool(c.get("CheckedOut")), "checked_out_by": c.get("CheckedOutByUserName") or "",
        "question": (meta.get("QuestionText") or "").strip() if isinstance(meta, dict) else "",
        "learned_terms": c.get("LearnedTerms") or "", "assigned_terms": c.get("AssignedTerms") or "",
        "file_ext": c.get("ContentFileExt") or "", "edit_perm": _bool(c.get("EditPerm")), "comments": c.get("Comments") or "",
    }


def normalize_folder(f: dict[str, Any]) -> dict[str, Any]:
    return {"id": _int(f.get("LibraryFolderID")), "parent_id": _int(f.get("LibraryParentFolderID")), "title": (f.get("Title") or "").strip(),
            "children": _int(f.get("ChildFolderCount")), "contents": _int(f.get("ContentCount")), "enabled": _bool(f.get("Enabled", "true"))}


def _checked(obj: Any, what: str) -> Any:
    """Guide « Error Handling » : une méthode qui renvoie un objet signale ses erreurs par HasErrors / errors (codes
    ErrorCodes) plutôt que par une exception ; les autres champs ne sont alors pas remplis."""
    if isinstance(obj, dict) and (_bool(obj.get("HasErrors")) or _bool(obj.get("hasErrors"))):
        codes = [str(c) for c in as_list(obj.get("errors") or obj.get("errorCodes"), "int")]
        raise QvidianError("qvidian", f"Qvidian a refusé « {what} » (code{'s' if len(codes) > 1 else ''} {', '.join(codes) or '?'})", HINTS["qvidian"])
    return obj


class QvidianClient:
    mode = "qvidian"

    def __init__(self, auth_url: str = DEFAULT_AUTH_URL, transport: SoapTransport | None = None):
        self.auth_url = auth_url or DEFAULT_AUTH_URL
        self.transport = transport or SoapTransport()
        self.binding: Binding | None = None
        self.extended_fields = True
        self.last_call = 0.0
        self._lock = threading.Lock()
        self.telemetry = Telemetry()
        self.cache = TtlCache(300)
        self.limiter = RateLimiter(8.0, 16)
        self.delta_supported: bool | None = None  # filtre DateLastModified accepté par le serveur ? (découvert au premier essai)
        self.reauth = None  # reconnexion complète (clé d'API ou mot de passe du .env) quand la session a expiré

    def configure(self, cache_seconds: int = 300, calls_per_second: float = 8.0) -> "QvidianClient":
        self.cache.ttl = max(0, cache_seconds)
        self.limiter = RateLimiter(calls_per_second, max(2, int(calls_per_second * 2)))
        return self

    # ------------------------------------------------------------------ appels
    def _send(self, url: str, operation: str, body: bytes) -> bytes:
        """Envoi mesuré, limité en débit ; lectures relancées (2 fois au plus) sur délai dépassé ou coupure réseau."""
        attempts = 0 if operation in WRITE_OPS else 2
        retries = 0
        while True:
            self.limiter.acquire()
            started = time.perf_counter()
            try:
                reply = self.transport.post(url, body, f"{soap.NS}{operation}")
            except NetError as error:
                ms = (time.perf_counter() - started) * 1000
                if error.code in RETRY_CODES and retries < attempts:
                    retries += 1
                    time.sleep(backoff(retries))
                    continue
                self.telemetry.record(operation, ms, ok=False, code=error.code, retries=retries)
                raise QvidianError(error.code, f"Qvidian injoignable ({error.code})", HINTS.get(error.code, "")) from error
            ms = (time.perf_counter() - started) * 1000
            if reply.status >= 500 and b"Fault" not in reply.content and retries < attempts:
                retries += 1
                time.sleep(backoff(retries))
                continue
            ok = reply.status < 400 and b"Fault" not in reply.content[:4000]
            self.telemetry.record(operation, ms, ok=ok, code=None if ok else str(reply.status), bytes_in=len(reply.content), retries=retries)
            if reply.status >= 400 and b"Fault" not in reply.content:
                raise QvidianError("reseau" if reply.status >= 500 else "qvidian", f"Qvidian a répondu {reply.status}", HINTS["reseau"])
            return reply.content

    def _post(self, url: str, operation: str, params: dict[str, Any], header: dict[str, Any] | None) -> Any:
        content = self._send(url, operation, soap.envelope(operation, params, header))
        try:
            return soap.result(content, operation)
        except SoapFault as fault:
            raise self._fault(fault) from fault

    @staticmethod
    def _fault(fault: SoapFault) -> QvidianError:
        text = fault.message.lower()
        if any(w in text for w in ("permission", "not authorized", "access denied", "unauthorized")):
            return QvidianError("permission", fault.message, HINTS["permission"])
        # Codes du guide : AuthenticationCredentialsMismatch, AuthenticationValueMismatch, AuthenticationTokenMismatch,
        # AuthenticationTokensEmpty, AuthenticationPasswordEmpty, AuthenticationFailure…
        if any(w in text for w in ("password", "invalid user", "login", "token", "authentic", "locked", "credential", "mismatch", "user name", "username")):
            return QvidianError("auth", fault.message, HINTS["auth"])
        return QvidianError("qvidian", fault.message + (f" (n° {fault.number})" if fault.number else ""), HINTS["qvidian"])

    def _auth(self, operation: str, **params: Any) -> Binding:
        res = self._post(self.auth_url, operation, params, {"IgnoreLockedOut": False})
        if not isinstance(res, dict) or not res.get("AuthToken"):
            raise QvidianError("auth", "Connexion Qvidian refusée", HINTS["auth"])
        urls = {k: v for k, v in res.items() if k.endswith("URL") and isinstance(v, str)}
        self.binding = Binding(res["AuthToken"], res.get("AuthUserName") or params.get("userName", ""), res.get("QvidianURL") or "", urls)
        if not self.binding.qvidian_url:
            raise QvidianError("config", "Qvidian n'a pas renvoyé l'adresse du service (QvidianURL)", HINTS["config"])
        return self.binding

    def connect(self, user: str, password: str) -> Binding:
        return self._auth("Connect", userName=user, password=password)

    def connect_api_key(self, user: str, api_key: str) -> Binding:
        return self._auth("ConnectByAPIKey", userName=user, apiKey=api_key)

    def connect_token(self, user: str, token: str) -> Binding:
        """Jeton SSO (renvoyé par le portail QPA) ou reconnexion avec le jeton courant."""
        return self._auth("ConnectByAuthToken", userName=user, authToken=token)

    def terminate(self) -> None:
        if self.binding is not None:
            try:
                self._post(self.auth_url, "ConnectionTerminate", {"authenticationToken": self.binding.token}, {"IgnoreLockedOut": False})
            except QvidianError:
                pass
            self.binding = None

    @property
    def connected(self) -> bool:
        return self.binding is not None

    def call(self, operation: str, **params: Any) -> Any:
        """Appel authentifié. Le jeton vit tant que la session est active : 1200 s sans appel par défaut
        (guide « Authentication Tokens », réglage ConnectionTimeout du serveur)."""
        if self.binding is None and self.reauth is not None:
            self.reauth()
        if self.binding is None:
            raise QvidianError("config", "Pas de connexion Qvidian", HINTS["config"])
        cache_key = None
        if operation in READ_CACHE_TTL and self.cache.ttl > 0 and not any(isinstance(v, RawXml) for v in params.values()):
            cache_key = (operation, tuple(sorted((k, str(v)) for k, v in params.items())))
            hit, value = self.cache.get(cache_key)
            if hit:
                self.telemetry.record(operation, 0.0, cached=True)
                return value
        try:
            res = self._post(self.binding.qvidian_url, operation, params, {"AuthenticationToken": self.binding.token})
        except QvidianError as error:
            if error.code != "auth":
                raise
            # Jeton refusé : une reconnexion avec le jeton courant (« Reconnect » du test UI), puis un seul nouvel essai
            with self._lock:
                try:
                    self.connect_token(self.binding.user, self.binding.token)
                except QvidianError as again:
                    if self.reauth is None:
                        self.binding = None  # session expirée côté Qvidian : il faut se reconnecter (SSO ou identifiant)
                        raise QvidianError("session", "Session Qvidian expirée (20 minutes sans activité par défaut).",
                                           "Reconnectez-vous depuis la fenêtre Qvidian (bouton SSO).") from again
                    self.reauth()  # clé d'API du .env : nouvelle session, sans rien demander
            res = self._post(self.binding.qvidian_url, operation, params, {"AuthenticationToken": self.binding.token})
        self.last_call = time.time()
        if cache_key is not None:
            self.cache.put(cache_key, res, READ_CACHE_TTL[operation])
        return res

    def keepalive(self) -> bool:
        """Petit appel de lecture pour garder la session ouverte pendant que l'app tourne."""
        try:
            self.has_permission("ViewSearchEnabledContent")
            return True
        except QvidianError:
            return False

    # ------------------------------------------------------------------ lecture
    def has_permission(self, permission: str) -> bool:
        return _bool(self.call("HasPermissions", Permission=permission))

    def top_folder(self) -> dict[str, Any]:
        return normalize_folder(_checked(self.call("libraryFolderGetTop") or {}, "libraryFolderGetTop"))

    def folders(self, parent_id: int) -> list[dict[str, Any]]:
        return [normalize_folder(f) for f in as_list(self.call("libraryFoldersGetList", parentFolderID=parent_id), "LibraryFolder")]

    def folder_contents(self, folder_id: int) -> list[dict[str, Any]]:
        items = as_list(self.call("libraryFolderContentGetList", folderID=folder_id), "Content")
        return [normalize_content(c) for c in items if not _bool(c.get("HasErrors"))]  # objet en erreur : ses champs ne sont pas remplis

    def content(self, content_id: int) -> dict[str, Any]:
        return normalize_content(_checked(self.call("libraryContentDetailsGet", contentID=content_id) or {}, f"contenu {content_id}"))

    def content_file(self, content_id: int) -> tuple[str, bytes]:
        res = self.call("libraryContentGet", contentID=content_id) or {}
        return res.get("fileName") or f"contenu_{content_id}", base64.b64decode(res.get("fileContent") or "")

    def preview_html(self, content_id: int, revision: int) -> str:
        res = _checked(self.call("libraryContentPreviewHTMLGet", contentID=content_id, revision=revision) or {}, "aperçu HTML")
        return res.get("htmlContent") or ""

    def search(self, terms: str = "", page: int = 0, size: int = 50, behavior: str = "AnyOfTheseWords",
               found_in: tuple[str, ...] = ("Title", "Content"), filters: list[dict[str, Any]] | None = None) -> tuple[int, list[dict[str, Any]]]:
        """librarySearchRequestInit puis librarySearch (comme les exemples) ; renvoie (total, contenus)."""
        for extended in ([True, False] if self.extended_fields else [False]):
            try:
                return self._search(terms, page, size, behavior, found_in, extended, filters)
            except QvidianError as error:
                if not extended or error.code != "qvidian":
                    raise
                self.extended_fields = False  # colonnes supplémentaires refusées : on s'en tient à celles des exemples
        return 0, []

    def folder_contents_paged(self, folder_id: int, size: int = 200, limit: int = 20000) -> list[dict[str, Any]]:
        """Tous les contenus d'un dossier, page par page (librarySearch filtré par dossier) : au-delà de 500 éléments,
        libraryFolderContentGetList est tronquée (guide « Guidelines for using Qvidian Web Services »)."""
        out: list[dict[str, Any]] = []
        page = 0
        while len(out) < limit:
            total, items = self.search(page=page, size=size, filters=[soap.folder_filter(folder_id)])
            out.extend(items)
            if not items or len(out) >= total:
                break
            page += 1
        return out

    def changed_since(self, day: str, size: int = 200, limit: int = 50000) -> list[dict[str, Any]]:
        """Contenus modifiés depuis une date (AAAA-MM-JJ) : synchronisation incrémentale. Filtre DateLastModified
        (colonne de recherche, opérateur GreaterThanOrEqual et type DateType de l'énumération du WSDL ; format de date
        de l'exemple EventDateUTC). Si le serveur le refuse, delta_supported passe à False et l'app refait une synchronisation complète."""
        out: list[dict[str, Any]] = []
        page = 0
        try:
            while len(out) < limit:
                total, items = self.search(page=page, size=size, filters=[soap.property_filter("DateLastModified", "DateType", "GreaterThanOrEqual", [day])])
                out.extend(items)
                if not items or len(out) >= total:
                    break
                page += 1
        except QvidianError:
            self.delta_supported = False
            raise
        self.delta_supported = True
        return out

    def existing_ids(self, ids: list[int], batch: int = 200) -> set[int]:
        """Identifiants encore présents (et visibles) dans Qvidian : filtre ContentID MatchesAny, comme l'exemple du test UI."""
        found: set[int] = set()
        for start in range(0, len(ids), batch):
            part = [str(i) for i in ids[start:start + batch]]
            page = 0
            while True:
                total, items = self.search(page=page, size=batch, filters=[soap.property_filter("ContentID", "IntegerType", "MatchesAny", part)])
                found.update(c["id"] for c in items)
                if not items or (page + 1) * batch >= total:
                    break
                page += 1
        return found

    def _search(self, terms: str, page: int, size: int, behavior: str, found_in: tuple[str, ...], extended: bool,
                filters: list[dict[str, Any]] | None = None) -> tuple[int, list]:
        if self.binding is None:
            raise QvidianError("config", "Pas de connexion Qvidian", HINTS["config"])
        body = soap.envelope("librarySearchRequestInit", {}, {"AuthenticationToken": self.binding.token})
        try:
            resp = soap.parse(self._send(self.binding.qvidian_url, "librarySearchRequestInit", body), "librarySearchRequestInit")
        except SoapFault as fault:
            raise self._fault(fault) from fault
        req = next(iter(resp), None)
        if req is None:
            raise QvidianError("qvidian", "librarySearchRequestInit n'a rien renvoyé", HINTS["qvidian"])
        o = soap.ORDER
        soap.set_value(req, "resetResultsCache", True, o["LibrarySearchRequest"])
        crit = soap.set_child(req, "searchCriteria", o["LibrarySearchRequest"])
        soap.set_value(crit, "pageSize", size, o["SearchCriteria"])
        soap.set_value(crit, "pageIndex", page, o["SearchCriteria"])
        soap.set_value(crit, "searchFields", Items("string", SEARCH_FIELDS + (SEARCH_FIELDS_EXTRA if extended else [])), o["SearchCriteria"])
        soap.set_value(crit, "sortField", "ContentID", o["SearchCriteria"])
        soap.set_value(crit, "sortDesc", False, o["SearchCriteria"])
        if filters:
            soap.set_records(crit, "filtersAND", "FilterCriteria", filters, o["SearchCriteria"])
        if terms.strip():
            tc = soap.set_child(req, "searchTermsCriteria", o["LibrarySearchRequest"])
            soap.set_value(tc, "terms", terms.strip(), o["searchTermsCriteria"])
            soap.set_value(tc, "useInflectional", False, o["searchTermsCriteria"])
            soap.set_value(tc, "defaultBehavior", behavior, o["searchTermsCriteria"])
            soap.set_value(tc, "foundInFields", Items("eSearchFoundIns", list(found_in)), o["searchTermsCriteria"])
            soap.set_value(tc, "languageIDs", Items("string", ["-1"]), o["searchTermsCriteria"])
        res = self.call("librarySearch", librarySearchRequest=RawXml(soap.element_xml(req, "librarySearchRequest"))) or {}
        if _bool(res.get("contentDataCompressed")) and not res.get("contentDataList"):
            raise QvidianError("qvidian", "résultats compressés non pris en charge", "Cas non documenté : à signaler.")
        return _int(res.get("totalCount")), [normalize_content(c) for c in as_list(res.get("contentDataList"), "Content")]

    def projects(self, mode: str = "AllProjects", page: int = 1, size: int = 50) -> tuple[int, list[dict[str, Any]]]:
        res = self.call("projectList", projectListType=mode, pageSize=size, currentPage=page, totalCount=0) or {}
        items = as_list(res.get("projectListResult"), "ProjectInfo") if isinstance(res, dict) else []
        return _int(res.get("totalCount") if isinstance(res, dict) else 0), [{
            "id": _int(p.get("ProjectID")), "name": p.get("ProjectName") or "", "type": p.get("DocTypeName") or "",
            "created": _date(p.get("DateCreated")), "last_used": _date(p.get("DateLastUsed")), "proposal_date": _date(p.get("ProposalDate")),
            "status": p.get("StatusString") or "", "archived": _bool(p.get("Archived")), "owners": p.get("OwnerList") or ""} for p in items]

    def project_documents(self, project_id: int) -> list[dict[str, Any]]:
        items = as_list(self.call("projectDocumentsGetList", projectID=project_id), "ProjectDocument")
        return [{"id": _int(d.get("ProjectDocumentID")), "project_id": project_id, "name": d.get("MiscFileDesc") or "",
                 "ext": (d.get("MiscFileExt") or "").lower().lstrip("."), "created": _date(d.get("DateCreated")),
                 "by": d.get("BuiltByUserName") or ""} for d in items]

    def project_document(self, project_id: int, document_id: int) -> tuple[str, bytes]:
        res = self.call("projectDocumentGet", projectID=project_id, projectDocID=document_id) or {}
        return res.get("fileName") or f"projet_{project_id}_{document_id}", base64.b64decode(res.get("fileContent") or "")

    def audit_events(self, event_ids: list[str] | None = None, page: int = 0, size: int = 100) -> tuple[int, list[dict[str, Any]]]:
        filters = Items("SimpleFilterCriteria", [{"fieldName": "EventID", "dataType": "IntegerType", "op": "MatchesAny",
                                                  "values": Items("string", event_ids)}]) if event_ids else None
        params: dict[str, Any] = {"pageSize": size, "pageIndex": page}
        if filters is not None:
            params["filtersAND"] = filters
        params.update({"sortField": "AuditID", "sortDesc": True})
        res = self.call("eventAuditSearch", searchParams=params) or {}
        rows = as_list(res.get("data"), "EventAuditing")
        return _int(res.get("totalCount")), [{"id": _int(r.get("AuditID")), "event": _int(r.get("EventID")), "title": r.get("EventTitle") or "",
                                              "object": _int(r.get("EventObjectID")), "user": r.get("UserFullName") or "",
                                              "date": _date(r.get("EventDateUTC")), "summary": r.get("EventSummary") or ""} for r in rows]

    # ------------------------------------------------------------------ écriture (bulk.py seulement)
    def update_details(self, content_ids: list[int], changes: dict[str, Any]) -> list[dict[str, Any]]:
        """libraryContentDetailsUpdate : même changement pour tous les contenus. Liste vide = succès (exemple du test UI)."""
        res = self.call("libraryContentDetailsUpdate", contentIDs=Items("int", content_ids), contentChanges=soap.content_updates(changes))
        wanted = {str(i) for i in content_ids}  # les lectures en cache de ces contenus ne sont plus à jour
        self.cache.invalidate(lambda k: k[0] == "libraryContentDetailsGet" and any(p[0] == "contentID" and p[1] in wanted for p in k[1]))
        problems = []
        for c in as_list(res, "Content"):
            if _bool(c.get("HasErrors")):
                problems.append({"id": _int(c.get("ContentID")), "errors": [str(e) for e in as_list(c.get("errors"), "int")]})
        return problems



__all__ = ["QvidianClient", "QvidianError", "Binding", "normalize_content", "normalize_folder", "html_to_text", "DEFAULT_AUTH_URL", "HINTS"]
