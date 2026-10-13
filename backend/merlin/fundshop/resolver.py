"""Trouver un document sans navigateur : adresse mémorisée → adresse construite (identifiants Product Info) → liens de la
page du fonds → lien collé une fois par l'utilisateur. Chaque PDF est vérifié (c'est bien un PDF, et celui de la part) ;
ce qui marche est mémorisé. Si rien ne marche, la raison la plus utile est rendue en clair (problems.py)."""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urljoin, urlparse

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
# Suffixe PAYS_LANGUE : la version française pour la France d'abord, puis les autres pays d'enregistrement
LANGS = {"FR": ("FR_FR", "BE_FR", "LU_FR", "CH_FR"), "EN": ("FR_EN", "LU_EN", "BE_EN", "CH_EN", "ES_EN", "IT_EN")}
SHARE_ID_COLUMNS = ("pi_shareid", "Id")
PRODUCT_ID_COLUMNS = ("pi_productid", "Id", "Product_Global_ID")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DOC_LINK = re.compile(r"(?:https?://[^\"'\s<>]*?)?/?(?:docs/)?([A-Z0-9]+)_([0-9a-fA-F-]{36})_([A-Z]{2}_[A-Z]{2})(?:_(\d{8}))?\.pdf", re.I)
ANY_PDF = re.compile(r"href=[\"']([^\"']+?\.pdf)[\"']", re.I)
TAG = re.compile(r"<[^>]+>")
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


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


def pdf_text(content: bytes, pages: int = 6) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:pages])
    except Exception:  # noqa: BLE001
        return ""


def pdf_isins(content: bytes) -> set[str]:
    """ISIN présents dans le texte du PDF (pypdf) ; repli : chaînes brutes."""
    text = pdf_text(content)
    if text:
        return set(re.findall(r"[A-Z]{2}[A-Z0-9]{9}\d", text))
    return {m.decode() for m in ISIN.findall(content[:400_000])}


def mentions_month(content: bytes, period: Period) -> bool | None:
    """Le reporting porte-t-il sur le mois demandé ? (« au 30/09/2026 », « September 2026 »…) ; None si illisible."""
    text = pdf_text(content, pages=2).lower()
    if not text or not period.month:
        return None
    mm, yyyy = f"{period.month:02d}", str(period.year)
    if re.search(rf"\b\d{{1,2}}[/.-]{mm}[/.-]{yyyy}\b", text):
        return True
    return MONTHS_FR[period.month - 1] + " " + yyyy in text or MONTHS_EN[period.month - 1] + " " + yyyy in text


@dataclass
class Link:
    url: str
    prefix: str
    guid: str
    lang: str
    date: str
    context: str  # texte autour du lien sur la page (libellé de la ligne de téléchargement)


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
        self._found: dict[str, list[str]] = {}

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

    # ------------------------------------------------------------------ pages du site
    def _root(self) -> str:
        u = urlparse(self.site_base)
        return f"{u.scheme}://{u.netloc}"

    def share_slug(self, ident: Identity) -> str:
        """« R-co Valor C EUR » (ou « C EUR ») → « c-eur », comme dans l'adresse de la page de la part."""
        share = ident.share or ""
        if ident.fund and norm(share).startswith(norm(ident.fund)):
            share = share[len(ident.fund):]
        return slug(share)

    def discover(self, ident: Identity, seen: "Attempts") -> list[str]:
        """Comme la recherche du site : l'API « data-fund » donne, pour un ISIN, le fonds (fund_rewrite) et le DIC de la part ;
        la page du fonds liste ses parts (menu « Part … ») : on en déduit la page exacte de la part."""
        if ident.isin in self._found:
            return self._found[ident.isin]
        out: list[str] = []
        lang = "fr"
        api = (f"{self._root()}/api/data-fund/?query={ident.isin}&type=&region=&range=&expertise=&period=&esg="
               f"&country={lang}&language={lang}&user_type=individual")
        try:
            r = self.net.get(api)
            data = json.loads(r.content.decode("utf-8", "replace")) if r.status == 200 else {}
        except NetError as error:
            seen.add(error.code, host=error.host, detail=error.detail, link=api)
            data = {}
        except ValueError:
            data = {}
        record = None
        for funds in (data.get("tree") or {}).values() if isinstance(data, dict) else []:
            for experts in (funds or {}).values():
                for shares in (experts or {}).values():
                    for rec in shares or []:
                        if isinstance(rec, dict) and ident.isin in {str(v).upper() for v in rec.values() if isinstance(v, str)}:
                            record = rec
        if record:
            if record.get("DIPR"):
                self.memory.learn(ident.isin, urljoin(self.docs_base + "/", str(record["DIPR"])), kind="dic")
            ident.fund = ident.fund or str(record.get("fund_title") or "")
            ident.share = ident.share or str(record.get("share_title") or "")
            if record.get("fund_rewrite"):
                fund_page = f"{self._root()}/{lang}/nos-fonds/{record['fund_rewrite']}/"
                share_page = self._share_from_menu(fund_page, str(record.get("share_title") or ident.share), seen)
                out = [share_page or fund_page] + ([fund_page] if share_page and share_page != fund_page else [])
        self._found[ident.isin] = out
        return out

    def _share_from_menu(self, fund_page: str, share_title: str, seen: "Attempts") -> str | None:
        """Le menu « Part C EUR / Part C USD… » de la page du fonds → adresse de la page de la part demandée."""
        self.links(fund_page, seen)  # charge la page (cache)
        html = self._pages.get(fund_page) or ""
        wanted = norm(re.sub(r"^part\s+", "", share_title, flags=re.I))
        for m in re.finditer(r'<option[^>]*value="([^"]+)"[^>]*>\s*([^<]+?)\s*</option>', html):
            label = norm(re.sub(r"^part\s+", "", m.group(2).replace("*", "").strip(), flags=re.I))
            if label and (label == wanted or wanted.endswith(" " + label) or wanted == label):
                return urljoin(self._root() + "/", m.group(1))
        return None

    def pages(self, ident: Identity, lang: str = "FR", seen: "Attempts | None" = None) -> list[str]:
        """Pages où sont listés les téléchargements : celle de la part d'abord, puis celle du fonds (FR puis EN)."""
        out = [self.memory.page(ident.isin)] if self.memory.page(ident.isin) else []
        if seen is not None:
            out += self.discover(ident, seen)
        if ident.fund:
            fund, share = slug(ident.fund), self.share_slug(ident)
            sections = ["fr/nos-fonds", "en/our-funds"] if lang == "FR" else ["en/our-funds", "fr/nos-fonds"]
            for section in sections:
                if share:
                    out.append(f"{self._root()}/{section}/{fund}/{share}/")
                out.append(f"{self._root()}/{section}/{fund}/")
        return list(dict.fromkeys(out))

    def fund_page(self, ident: Identity) -> str:
        """Page à ouvrir pour vérifier à la main."""
        candidates = self.pages(ident)
        return candidates[0] if candidates else self.site_base

    def links(self, page: str, seen: "Attempts") -> list[Link]:
        """Tous les PDF listés sur une page (adresses absolues ou /docs/…), avec le texte qui les entoure."""
        if page not in self._pages:
            try:
                r = self.net.get(page)
                self._pages[page] = r.content.decode("utf-8", "replace") if r.status == 200 else None
            except NetError as error:
                seen.add(error.code, host=error.host, detail=error.detail, link=page)
                self._pages[page] = None
        html = (self._pages[page] or "").replace("\\/", "/").replace("&amp;", "&")
        out: dict[str, Link] = {}
        for m in DOC_LINK.finditer(html):
            prefix, guid, lang, date = m.group(1).upper(), m.group(2).lower(), m.group(3).upper(), m.group(4) or ""
            url = f"{self.docs_base}/{prefix}_{guid}_{lang}{'_' + date if date else ''}.pdf"
            context = norm(TAG.sub(" ", html[max(0, m.start() - 600):m.start()]))[-200:]
            out.setdefault(url, Link(url, prefix, guid, lang, date, context))
        for m in ANY_PDF.finditer(html):  # PDF sans motif connu (rapport semestriel…) : adresse telle quelle
            url = urljoin(self._root() + "/", m.group(1)) if not m.group(1).startswith("/") and "<base" in html else urljoin(page, m.group(1))
            if not DOC_LINK.search(url):
                context = norm(TAG.sub(" ", html[max(0, m.start() - 600):m.start()]))[-200:]
                out.setdefault(url, Link(url, "", "", "", "", context))
        return list(out.values())

    # ------------------------------------------------------------------ un essai
    def _try(self, url: str, ident: Identity, doc: DocType, strategy: str, seen: Attempts, period: Period | None = None) -> Found | None:
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
        info = parse_url(url)
        if doc.needs_month and period and info and not info["date"] and mentions_month(r.content, period) is False:
            seen.add("absent", link=url)  # dernier reporting publié, mais d'un autre mois
            return None
        return Found(url, r.content, strategy, note)

    def hosts(self) -> list[str]:
        """Les deux adresses du site qui servent les PDF (la configurée d'abord)."""
        alt = {"https://docs.am.eu.rothschildandco.com": "https://am.eu.rothschildandco.com/docs",
               "https://am.eu.rothschildandco.com/docs": "https://docs.am.eu.rothschildandco.com"}
        return [self.docs_base] + ([alt[self.docs_base]] if self.docs_base in alt else [])

    def _built(self, doc: DocType, period: Period, guid: str, host: str | None = None, lang: str | None = None) -> list[str]:
        learned = self.memory.data["langs"].get(doc.key)
        langs = [lang] if lang else list(dict.fromkeys(([learned] if learned else []) + list(LANGS[doc.lang])))
        dates = month_end_candidates(period) if doc.needs_month else [""]
        base = (host or self.docs_base).rstrip("/")
        return [f"{base}/{doc.prefix}_{guid}_{lg}{'_' + d if d else ''}.pdf" for lg in langs for d in dates]

    # ------------------------------------------------------------------ recherche
    def find(self, ident: Identity, doc: DocType, period: Period) -> Found:
        label = period.label if doc.needs_month else ""
        if doc.needs_month and not (period.month and period.year):
            raise DocumentProblem(problem("mois", doc=doc.label))
        seen = Attempts()
        tried: set[str] = set()
        trusted_404 = False

        def attempt(urls: list[str], strategy: str) -> Found | None:
            for url in urls:
                if url in tried:
                    continue
                tried.add(url)
                if (f := self._try(url, ident, doc, strategy, seen, period)):
                    if doc.prefix:
                        self.memory.learn(ident.isin, f.url, kind=doc.key)
                    return f
            return None

        # 0. lien collé pour ce document précis (types sans motif d'adresse)
        pasted = self.memory.url(ident.isin, doc.key)
        if pasted and not doc.prefix and (f := attempt([pasted], "lien collé")):
            return f
        if doc.prefix:
            # 1. adresse mémorisée (déjà vérifiée : un 404 veut dire « pas sur le site »)
            guid = self.memory.guid(ident.isin, doc.level)
            if guid:
                if (f := attempt(self._built(doc, period, guid), "mémorisée")):
                    return f
                trusted_404 = set(seen.codes) == {"absent"}
        # 2. la page de la part sur le site (comme à la main : « Téléchargements »), puis celle du fonds
        self.discover(ident, seen)
        share_slug = self.share_slug(ident)
        for page in self.pages(ident, doc.lang, seen):
            on_share_page = (bool(share_slug) and page.rstrip("/").endswith("/" + share_slug)) or page in self._found.get(ident.isin, [])[:1]
            links = self.links(page, seen)
            if not links:
                continue
            if doc.prefix:
                if on_share_page:  # la page de la part : ses adresses sont mémorisées pour toutes les prochaines fois
                    for ln in links:
                        if ln.prefix:
                            self.memory.learn(ident.isin, ln.url)
                found_links = [ln for ln in links if ln.prefix == doc.prefix]
                wanted = [ln for ln in found_links if ln.lang.endswith("_" + doc.lang)] or found_links
                for ln in wanted:
                    same_lang = ln.lang.endswith("_" + doc.lang)
                    urls = ([ln.url] if same_lang and not doc.needs_month else []) + (self._built(doc, period, ln.guid, lang=ln.lang) if same_lang else []) \
                        + self._built(doc, period, ln.guid)
                    if doc.needs_month and not ln.date and same_lang:
                        urls.append(ln.url)  # dernier reporting publié (sans date) : accepté s'il porte sur le mois demandé
                    before = set(seen.codes)
                    if (f := attempt(urls, "page de la part" if on_share_page else "page du fonds")):
                        return f
                    if on_share_page and set(seen.codes) - before == {"absent"}:
                        trusted_404 = True
            else:
                labels = [norm(x) for x in doc.site_labels]
                matching = [ln.url for ln in links if any(lb in ln.context[-80:] for lb in labels)]
                if (f := attempt(matching, "page de la part")):
                    self.memory.data["urls"][f"{ident.isin}|{doc.key}"] = {"url": f.url}
                    return f
        if doc.prefix:
            # 3. identifiants Product Info (la colonne qui a déjà marché d'abord)
            ids = ident.share_ids if doc.level == "share" else ident.product_ids
            learned_col = self.memory.data["id_column"].get(doc.level, "").split(".")[-1]
            for column in sorted(ids, key=lambda c: c != learned_col):
                if (f := attempt(self._built(doc, period, ids[column]), "construite")):
                    table = "PI_OUT_Share" if doc.level == "share" else "pi_out_product_active"
                    self.memory.learn(ident.isin, f.url, f"{table}.{column}", doc.key)
                    return f
            # 4. l'autre adresse du site si la première ne répond pas (même fichier, autre chemin)
            if any(code in seen.codes for code in ("proxy", "hors-ligne", "delai", "reseau", "refuse")):
                guid = self.memory.guid(ident.isin, doc.level)
                for host in self.hosts()[1:]:
                    if guid and (f := attempt(self._built(doc, period, guid, host=host), "mémorisée")):
                        return f
        raise DocumentProblem(self._explain(seen, ident, doc, label, trusted_404))

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


# ------------------------------------------------------------------ ce que le site propose pour une part
def kind_of(prefix: str, lang: str) -> str | None:
    """Préfixe + langue d'un lien du site → type de document de l'app (None : type non géré)."""
    from .catalog import DOC_TYPES

    language = lang.split("_")[-1] if lang else "FR"
    for d in DOC_TYPES.values():
        if d.prefix == prefix and d.lang == language:
            return d.key
    return None


def available(resolver: "Resolver", isin: str, fund: str = "", part: str = "") -> dict:
    """Comme « Téléchargements » sur le site : la liste réelle des documents de la part (mois disponibles pour les reportings).
    Tout ce qui est lu est mémorisé : le téléchargement ira ensuite droit au fichier."""
    from .catalog import DOC_TYPES
    from .period import MONTHS_FR

    ident = resolver.identity(isin, fund, part)
    seen = Attempts()
    pages = resolver.pages(ident, "FR", seen)
    found: dict[str, dict] = {}
    page_used = ""
    for page in pages:
        links = resolver.links(page, seen)
        if not any(ln.prefix for ln in links):
            continue
        page_used = page
        for ln in links:
            key = kind_of(ln.prefix, ln.lang) if ln.prefix else None
            if not key:
                continue
            if DOC_TYPES[key].level == "share" or page == pages[0]:
                resolver.memory.learn(ident.isin, ln.url)
            entry = found.setdefault(key, {"kind": key, "label": DOC_TYPES[key].label, "needs_month": DOC_TYPES[key].needs_month,
                                           "url": ln.url, "months": []})
            if ln.date:
                y, m = int(ln.date[:4]), int(ln.date[4:6])
                entry["months"].append({"value": f"{y}-{m:02d}", "label": f"{MONTHS_FR[m - 1]} {y}", "url": ln.url})
        break
    resolver.memory.save()
    for entry in found.values():
        entry["months"] = sorted({m["value"]: m for m in entry["months"]}.values(), key=lambda m: m["value"], reverse=True)
    problem_out = None
    if not found:
        worst = seen.worst()
        from .problems import problem
        problem_out = (problem(worst[0], host=worst[1].get("host", ""), detail=worst[1].get("detail", ""), status=worst[1].get("status", 0))
                       if worst and worst[0] in {"proxy", "certificat", "hors-ligne", "delai", "reseau", "refuse"}
                       else problem("adresse-inconnue", link=resolver.fund_page(ident))).to_dict()
    order = list(DOC_TYPES)
    return {"isin": ident.isin, "fund": ident.fund, "part": ident.share, "page": page_used,
            "documents": sorted(found.values(), key=lambda e: order.index(e["kind"])), "problem": problem_out}
