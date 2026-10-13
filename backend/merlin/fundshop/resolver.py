"""Trouver et télécharger un document : adresse apprise → adresse construite (identifiants Product Info) → page du fonds
→ navigateur. Chaque PDF est vérifié avant d'être accepté ; ce qui marche est mémorisé."""
from __future__ import annotations

import calendar
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import httpx

from ..data.access import DataAccess, DataError
from ..rfi.ontology import norm
from .catalog import DocType
from .memory import Memory, parse_url
from .period import Period

DOCS_BASE = "https://docs.am.eu.rothschildandco.com"
SITE_BASE = "https://am.eu.rothschildandco.com/fr/nos-fonds/"
MIN_SIZE = 1000
ISIN = re.compile(rb"[A-Z]{2}[A-Z0-9]{9}\d")
EN_LANGS = ("EN_FR", "EN_GB", "EN_EN", "EN_LU", "EN_INT")
SHARE_ID_COLUMNS = ("pi_shareid", "Id")
PRODUCT_ID_COLUMNS = ("pi_productid", "Id", "Product_Global_ID")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass
class Identity:
    isin: str
    fund: str = ""
    share: str = ""
    share_ids: dict[str, str] = field(default_factory=dict)  # colonne → GUID
    product_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class Found:
    url: str
    content: bytes
    strategy: str  # apprise | construite | page | navigateur
    note: str = ""


class DocumentNotFound(Exception):
    pass


def month_end_candidates(period: Period) -> list[str]:
    end = period.month_end
    if end is None:
        return []
    out = [end]
    d = end
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    if d != end:
        out.append(d)
    return [x.strftime("%Y%m%d") for x in out]


def pdf_isins(content: bytes) -> set[str]:
    """ISIN présents dans le texte du PDF (pypdf) ; repli : chaînes brutes."""
    found: set[str] = set()
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        for page in reader.pages[:6]:
            found |= set(re.findall(r"[A-Z]{2}[A-Z0-9]{9}\d", page.extract_text() or ""))
    except Exception:  # noqa: BLE001
        found |= {m.decode() for m in ISIN.findall(content[:400_000])}
    return found


class Resolver:
    def __init__(self, data: DataAccess | None, memory: Memory, get: Callable[[str], httpx.Response] | None = None,
                 browser: Callable[[Identity, DocType, Period], str] | None = None, docs_base: str = DOCS_BASE, site_base: str = SITE_BASE):
        self.data, self.memory, self.browser = data, memory, browser
        self.docs_base, self.site_base = docs_base.rstrip("/"), site_base
        self._client = None
        self._get = get or self._http_get
        self._ids: dict[str, Identity] = {}

    def _http_get(self, url: str) -> httpx.Response:
        if self._client is None:
            self._client = httpx.Client(timeout=30, follow_redirects=True,
                                        headers={"User-Agent": "RFP-pas-envie-de-travailler/1.0 (documents réglementaires publics)"})
        return self._client.get(url)

    # ------------------------------------------------------------------ identité Product Info
    def identity(self, isin: str, fund: str = "", share: str = "") -> Identity:
        isin = isin.strip().upper()
        if isin in self._ids:
            return self._ids[isin]
        ident = Identity(isin, fund, share)
        if self.data is not None:
            try:
                s = self.data.query("SELECT s.pi_shareid, s.Id, s.ProductID, s.Share_Name FROM dbo.PI_OUT_Share s WHERE s.ISIN_Code = :isin",
                                    {"isin": isin})
                if len(s):
                    row = s.iloc[0].to_dict()
                    ident.share_ids = {c: str(row[c]).lower() for c in SHARE_ID_COLUMNS if row.get(c) and GUID.match(str(row[c]))}
                    ident.share = ident.share or str(row.get("Share_Name") or "")
                    pid = row.get("ProductID")
                    if pid:
                        p = self.data.query("SELECT p.pi_productid, p.Id, p.Product_Global_ID, p.Product_Name FROM dbo.pi_out_product_active p "
                                            "WHERE p.pi_productid = :pid", {"pid": str(pid)})
                        if len(p):
                            prow = p.iloc[0].to_dict()
                            ident.product_ids = {c: str(prow[c]).lower() for c in PRODUCT_ID_COLUMNS if prow.get(c) and GUID.match(str(prow[c]))}
                            ident.fund = ident.fund or str(prow.get("Product_Name") or "")
            except DataError:
                pass
        self._ids[isin] = ident
        return ident

    # ------------------------------------------------------------------ vérification
    def verify(self, content: bytes, ident: Identity, doc: DocType) -> str:
        """« » si accepté, sinon la raison du refus. Une réserve non bloquante est préfixée de « ~ »."""
        if len(content) < MIN_SIZE or not content.startswith(b"%PDF"):
            return "le fichier reçu n'est pas un PDF"
        if doc.checks_isin:
            isins = pdf_isins(content)
            if isins and ident.isin not in isins:
                return f"PDF d'une autre part ({', '.join(sorted(isins)[:3])})"
            if not isins:
                return "~ISIN non vérifiable dans le PDF"
        return ""

    def _try(self, url: str, ident: Identity, doc: DocType, strategy: str) -> Found | None:
        try:
            r = self._get(url)
        except httpx.HTTPError:
            return None
        if r.status_code != 200 or "html" in r.headers.get("content-type", ""):
            return None
        verdict = self.verify(r.content, ident, doc)
        if verdict and not verdict.startswith("~"):
            return None
        return Found(url, r.content, strategy, verdict.lstrip("~"))

    # ------------------------------------------------------------------ stratégies
    def _built(self, ident: Identity, doc: DocType, period: Period, guid: str) -> list[str]:
        langs = [f"{doc.lang}_FR"] if doc.lang == "FR" else ([self.memory.data["langs"][doc.key]] if doc.key in self.memory.data["langs"] else list(EN_LANGS))
        dates = month_end_candidates(period) if doc.needs_month else [""]
        return [f"{self.docs_base}/{doc.prefix}_{guid}_{lang}{'_' + d if d else ''}.pdf" for lang in langs for d in dates]

    def find(self, ident: Identity, doc: DocType, period: Period, allow_browser: bool = True) -> Found:
        if doc.needs_month and not (period.month and period.year):
            raise DocumentNotFound("ce document demande un mois et une année")
        tried: list[str] = []
        if doc.prefix:
            # 1. GUID appris
            guid = self.memory.guid(ident.isin, doc.level)
            if guid:
                for url in self._built(ident, doc, period, guid):
                    tried.append(url)
                    if (f := self._try(url, ident, doc, "apprise")):
                        return f
            # 2. GUID des identifiants Product Info (colonne apprise d'abord)
            ids = ident.share_ids if doc.level == "share" else ident.product_ids
            learned_col = self.memory.data["id_column"].get(doc.level, "").split(".")[-1]
            for column in sorted(ids, key=lambda c: c != learned_col):
                for url in self._built(ident, doc, period, ids[column]):
                    if url in tried:
                        continue
                    tried.append(url)
                    if (f := self._try(url, ident, doc, "construite")):
                        table = "PI_OUT_Share" if doc.level == "share" else "pi_out_product_active"
                        self.memory.learn(ident.isin, url, f"{table}.{column}", doc.key)
                        return f
            # 3. page du fonds (sans navigateur) : liens du type demandé, vérifiés par l'ISIN
            found = self._from_page(ident, doc, period)
            if found:
                return found
        # 4. navigateur (parcours du script historique), seulement pour découvrir l'adresse
        if allow_browser and self.browser is not None:
            url = self.browser(ident, doc, period)
            if url and (f := self._try(url, ident, doc, "navigateur")):
                self.memory.learn(ident.isin, url, kind=doc.key)
                return f
        raise DocumentNotFound("introuvable (adresse apprise, adresse construite depuis Product Info, page du fonds"
                               + (", navigateur" if allow_browser and self.browser else "") + ")")

    def _from_page(self, ident: Identity, doc: DocType, period: Period) -> Found | None:
        if not ident.fund:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", norm(ident.fund)).strip("-")
        try:
            r = self._get(self.site_base + slug + "/")
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        for m in re.finditer(r"https?://docs\.am\.eu\.rothschildandco\.com/[^\"'\s<>]+\.pdf", r.text):
            info = parse_url(m.group(0))
            if not info or info["prefix"] != doc.prefix:
                continue
            for url in self._built(ident, doc, period, info["guid"]):
                if (f := self._try(url, ident, doc, "page")):
                    self.memory.learn(ident.isin, url, kind=doc.key)
                    return f
        return None
