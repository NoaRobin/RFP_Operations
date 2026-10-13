"""Trouver un document sans navigateur : adresse mémorisée → adresse construite (identifiants Product Info) → liens de la
page du fonds → lien collé une fois par l'utilisateur. Chaque PDF est vérifié (c'est bien un PDF, et celui de la part) ;
ce qui marche est mémorisé. Si rien ne marche, la raison la plus utile est rendue en clair (problems.py)."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlparse

from ..data.access import DataAccess, DataError
from ..rfi.ontology import norm
from .catalog import DOC_TYPES, DocType
from .memory import Memory, parse_url
from .net import Network, NetError, default_network
from .period import Period
from .problems import PRIORITY, DocumentProblem, Problem, problem

DOCS_BASE = "https://docs.am.eu.rothschildandco.com"
SITE_BASE = "https://am.eu.rothschildandco.com/fr/nos-fonds/"
MIN_SIZE = 1000
ISIN = re.compile(rb"[A-Z]{2}[A-Z0-9]{9}\d")
EN_LANGS = ("EN_FR", "EN_GB", "EN_EN", "EN_LU", "EN_INT")
SHARE_ID_COLUMNS = ("pi_shareid", "Id")
PRODUCT_ID_COLUMNS = ("pi_productid", "Id", "Product_Global_ID")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PDF_LINK = re.compile(r"https?://[^\"'\s<>]+?\.pdf", re.I)


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
    strategy: str  # mémorisée | construite | page du fonds | lien collé
    note: str = ""


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


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(name)).strip("-")


class Attempts:
    """Ce qui s'est passé pendant la recherche, pour expliquer un échec."""

    def __init__(self):
        self.codes: dict[str, dict] = {}
        self.tried = 0

    def add(self, code: str, **context) -> None:
        self.codes.setdefault(code, context)

    def worst(self) -> tuple[str, dict] | None:
        for code in PRIORITY:
            if code in self.codes:
                return code, self.codes[code]
        return None


class Resolver:
    def __init__(self, data: DataAccess | None, memory: Memory, net: Network | None = None, docs_base: str = DOCS_BASE,
                 site_base: str = SITE_BASE):
        self.data, self.memory = data, memory
        self.docs_base, self.site_base = docs_base.rstrip("/"), site_base if site_base.endswith("/") else site_base + "/"
        self._net = net
        self._ids: dict[str, Identity] = {}
        self._pages: dict[str, str | None] = {}

    @property
    def net(self) -> Network:
        if self._net is None:
            self._net = default_network()
        return self._net

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

    def fund_page(self, ident: Identity) -> str:
        """Page à ouvrir pour vérifier à la main : page mémorisée, sinon celle déduite du nom du fonds."""
        return self.memory.page(ident.isin) or (self.site_base + slug(ident.fund) + "/" if ident.fund else self.site_base)

    # ------------------------------------------------------------------ un essai
    def _try(self, url: str, ident: Identity, doc: DocType, strategy: str, seen: Attempts) -> Found | None:
        seen.tried += 1
        try:
            r = self.net.get(url)
        except NetError as error:
            seen.add(error.code, host=error.host, detail=error.detail, link=url)
            return None
        if r.status in (401, 403):
            seen.add("refuse", status=r.status, link=url)
            return None
        if r.status != 200:
            seen.add("absent", link=url)
            return None
        if not r.is_pdf or len(r.content) < MIN_SIZE:
            seen.add("pas-pdf", link=url)
            return None
        note = ""
        if doc.checks_isin:
            isins = pdf_isins(r.content)
            if isins and ident.isin not in isins:
                if doc.prefix == "DIPR" and len(isins) == 1:  # DIC d'une autre part : on retient son adresse pour plus tard
                    self.memory.learn(next(iter(isins)), url, kind="dic")
                seen.add("autre-part", isins=", ".join(sorted(isins)[:3]), link=url)
                return None
            if not isins:
                note = "ISIN non vérifiable dans le PDF"
        return Found(url, r.content, strategy, note)

    def _built(self, doc: DocType, period: Period, guid: str) -> list[str]:
        if doc.lang == "FR":
            langs = ["FR_FR"]
        else:
            langs = [self.memory.data["langs"][doc.key]] if doc.key in self.memory.data["langs"] else list(EN_LANGS)
        dates = month_end_candidates(period) if doc.needs_month else [""]
        return [f"{self.docs_base}/{doc.prefix}_{guid}_{lang}{'_' + d if d else ''}.pdf" for lang in langs for d in dates]

    # ------------------------------------------------------------------ recherche
    def find(self, ident: Identity, doc: DocType, period: Period) -> Found:
        label = period.label if doc.needs_month else ""
        if doc.needs_month and not (period.month and period.year):
            raise DocumentProblem(problem("mois", doc=doc.label))
        seen = Attempts()
        trusted_404 = False
        if not doc.prefix:
            # Type sans adresse connue : seulement le lien collé par l'utilisateur pour cette part
            pasted = self.memory.url(ident.isin, doc.key)
            if pasted and (f := self._try(pasted, ident, doc, "lien collé", seen)):
                return f
        else:
            tried: set[str] = set()

            def attempt(urls: list[str], strategy: str) -> Found | None:
                for url in urls:
                    if url in tried:
                        continue
                    tried.add(url)
                    if (f := self._try(url, ident, doc, strategy, seen)):
                        return f
                return None

            # 1. adresse mémorisée (GUID déjà vérifié : un 404 veut dire « pas sur le site »)
            guid = self.memory.guid(ident.isin, doc.level)
            if guid:
                if (f := attempt(self._built(doc, period, guid), "mémorisée")):
                    return f
                trusted_404 = set(seen.codes) == {"absent"}
            # 2. identifiants Product Info (la colonne qui a déjà marché d'abord)
            ids = ident.share_ids if doc.level == "share" else ident.product_ids
            learned_col = self.memory.data["id_column"].get(doc.level, "").split(".")[-1]
            for column in sorted(ids, key=lambda c: c != learned_col):
                if (f := attempt(self._built(doc, period, ids[column]), "construite")):
                    table = "PI_OUT_Share" if doc.level == "share" else "pi_out_product_active"
                    self.memory.learn(ident.isin, f.url, f"{table}.{column}", doc.key)
                    return f
            # 3. liens de la page du fonds
            for guid_found in self._page_guids(ident, doc, seen):
                if (f := attempt(self._built(doc, period, guid_found), "page du fonds")):
                    self.memory.learn(ident.isin, f.url, kind=doc.key)
                    return f
        raise DocumentProblem(self._explain(seen, ident, doc, label, trusted_404))

    def _page_guids(self, ident: Identity, doc: DocType, seen: Attempts) -> list[str]:
        page = self.memory.page(ident.isin) or (self.site_base + slug(ident.fund) + "/" if ident.fund else "")
        if not page:
            return []
        if page not in self._pages:
            try:
                r = self.net.get(page)
                self._pages[page] = r.content.decode("utf-8", "replace") if r.status == 200 else None
            except NetError as error:
                seen.add(error.code, host=error.host, detail=error.detail, link=page)
                self._pages[page] = None
        html = self._pages[page] or ""
        out: list[str] = []
        for m in PDF_LINK.finditer(html.replace("\\/", "/")):
            info = parse_url(m.group(0))
            if info and info["prefix"] == doc.prefix and info["guid"] not in out:
                out.append(info["guid"])
        return out

    def _explain(self, seen: Attempts, ident: Identity, doc: DocType, label: str, trusted_404: bool) -> Problem:
        worst = seen.worst()
        page = self.fund_page(ident)
        if worst is None:
            return problem("adresse-inconnue", link=page)
        code, ctx = worst
        if code == "absent" and not trusted_404:
            return problem("adresse-inconnue", link=page)  # adresses devinées : on ne sait pas si le document existe
        if code == "absent":
            return problem("absent", doc=doc.label, period=label, link=page)
        return problem(code, host=ctx.get("host", urlparse(self.docs_base).netloc), status=ctx.get("status", 0),
                       isins=ctx.get("isins", ""), detail=ctx.get("detail", ""), link=ctx.get("link") or page)

    # ------------------------------------------------------------------ lien collé par l'utilisateur
    def learn_link(self, isin: str, url: str, kind: str | None = None) -> str:
        """Un lien de PDF du site (l'app en déduit l'adresse de tous les documents de la part) ou la page du fonds."""
        url = url.strip()
        isin = isin.strip().upper()
        info = parse_url(url)
        if info:
            doc = DOC_TYPES.get(kind or "") or next((d for d in DOC_TYPES.values() if d.prefix == info["prefix"]), None)
            if doc and doc.checks_isin:
                try:
                    r = self.net.get(url)
                except NetError as error:
                    self.memory.learn(isin, url, kind=doc.key)
                    self.memory.save()
                    return f"Lien enregistré, mais pas vérifié : {problem(error.code, host=error.host, detail=error.detail).title.lower()}."
                if r.status == 200 and r.is_pdf:
                    isins = pdf_isins(r.content)
                    if isins and isin not in isins:
                        raise ValueError(f"Ce PDF concerne une autre part ({', '.join(sorted(isins)[:3])}), pas {isin}.")
            self.memory.learn(isin, url, kind=doc.key if doc else None)
            self.memory.save()
            level = "de cette part" if info["level"] == "share" else "de ce fonds"
            return f"C'est noté : l'app connaît maintenant l'adresse des documents {level}."
        if url.startswith("http") and urlparse(url).netloc == urlparse(self.site_base).netloc:
            self.memory.remember_page(isin, url)
            self.memory.save()
            return "Page du fonds enregistrée : l'app y cherchera les liens des PDF."
        if kind and not (DOC_TYPES.get(kind) and DOC_TYPES[kind].prefix) and url.lower().endswith(".pdf"):
            self.memory.data["urls"][f"{isin}|{kind}"] = {"url": url}
            self.memory.save()
            return "Lien enregistré pour ce document."
        raise ValueError("Ce lien n'est ni un PDF du site des fonds, ni une page de fonds.")
