"""Où trouver le DIC et le prospectus d'une part : site public, dossier synchronisé, dépôt manuel.

Même contrat pour toutes les sources (DocumentFinder) : le service ne dépend que de lui. Le site n'est jamais
« deviné » au hasard : on part de la page du fonds (nom Product Info) ou de la recherche du site, et un PDF n'est
retenu que si la page ou le lien porte l'ISIN de la part — puis le contenu du PDF est re-vérifié à la lecture.
"""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import quote, urljoin, urlparse

import httpx

from ..ontology import norm
from .model import DocumentRef

KID = re.compile(r"(?<![a-z])(kid|dic|kiid|dici|priips|key information|informations? cles|document d'informations)(?![a-z])")
PROSPECTUS = re.compile(r"(?<![a-z])(prospectus|prospekt)(?![a-z])")
LANG = re.compile(r"(?<![a-z])(fr|en|de|it|es|nl)(?![a-z])")
USER_AGENT = "RFP-pas-envie-de-travailler/1.0 (lecture des documents réglementaires publics)"


class DocumentFinder(Protocol):
    name: str

    def find(self, isin: str, fund_name: str, share_name: str) -> list[DocumentRef]: ...

    def fetch(self, ref: DocumentRef, target: Path) -> Path: ...


def classify(text: str) -> str:
    t = norm(text)
    if KID.search(t):
        return "kid"
    if PROSPECTUS.search(t):
        return "prospectus"
    return "other"


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("&", " ")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = [dict(attrs).get("title") or "", dict(attrs).get("aria-label") or ""]

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(t.strip() for t in self._text if t and t.strip())))
            self._href = None


def links(html: str) -> list[tuple[str, str]]:
    parser = _Links()
    parser.feed(html)
    return parser.links


class WebsiteDocumentFinder:
    """Site public des fonds (ex. https://am.eu.rothschildandco.com/en/our-funds/<fonds>/<part>/)."""

    name = "site"

    def __init__(self, base_url: str, fund_path: str = "/en/our-funds/{slug}/", search_path: str = "/en/search/?q={isin}",
                 get: Callable[[str], httpx.Response] | None = None, timeout: float = 20.0):
        self.base = base_url.rstrip("/")
        self.fund_path = fund_path
        self.search_path = search_path
        self._get = get or (lambda url: httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}))
        self.errors: list[str] = []

    def _page(self, url: str) -> str | None:
        try:
            r = self._get(url)
        except httpx.HTTPError as error:
            self.errors.append(f"site injoignable ({type(error).__name__}) : {url}")
            return None
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "text/html"):
            return None
        return r.text

    def _same_site(self, url: str) -> bool:
        return urlparse(url).netloc in ("", urlparse(self.base).netloc)

    def _share_pages(self, isin: str, fund_name: str) -> list[tuple[str, str]]:
        """(url, html) des pages qui citent l'ISIN : page du fonds et ses sous-pages de parts, sinon la recherche."""
        found: list[tuple[str, str]] = []
        seeds = []
        if fund_name:
            seeds.append(self.base + self.fund_path.format(slug=slugify(fund_name)))
        seeds.append(self.base + self.search_path.format(isin=quote(isin)))
        seen: set[str] = set()
        for seed in seeds:
            html = self._page(seed)
            if html is None:
                continue
            seen.add(seed)
            if isin in html:
                found.append((seed, html))
            # sous-pages de parts / résultats de recherche
            for href, _ in links(html):
                url = urljoin(seed, href)
                if url in seen or not self._same_site(url) or url.lower().endswith(".pdf"):
                    continue
                if "/our-funds/" in url or "/nos-fonds/" in url:
                    seen.add(url)
                    sub = self._page(url)
                    if sub and isin in sub:
                        found.append((url, sub))
                if len(seen) > 40:
                    break
            if found:
                break
        return found

    def find(self, isin: str, fund_name: str, share_name: str) -> list[DocumentRef]:
        refs: dict[str, DocumentRef] = {}
        for page_url, html in self._share_pages(isin, fund_name):
            for href, label in links(html):
                url = urljoin(page_url, href)
                if not (url.lower().split("?")[0].endswith(".pdf") or "download" in url.lower() or "/file/" in url.lower()):
                    continue
                kind = classify(f"{label} {url}")
                if kind == "other":
                    continue
                m = LANG.search(norm(f"{label} {url.rsplit('/', 1)[-1]}"))
                lang = m.group(1) if m else ""
                refs.setdefault(url, DocumentRef(isin=isin, kind=kind, title=label.strip() or url.rsplit("/", 1)[-1], url=url,
                                                 lang=lang or "", source="site"))
        return list(refs.values())

    def fetch(self, ref: DocumentRef, target: Path) -> Path:
        r = self._get(ref.url)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            raise ValueError(f"document non téléchargeable ({r.status_code})")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        return target


class FolderDocumentFinder:
    """Dossier local (synchronisé OneDrive / SharePoint « Documentation » ou dépôts manuels) : PDF dont le nom porte l'ISIN."""

    def __init__(self, root: Path | None, name: str = "dossier"):
        self.root = root
        self.name = name

    def find(self, isin: str, fund_name: str, share_name: str) -> list[DocumentRef]:
        if self.root is None or not self.root.is_dir():
            return []
        out = []
        for path in sorted(self.root.rglob("*.pdf"))[:5000]:
            if isin.upper() in path.name.upper():
                kind = classify(path.stem)
                if kind != "other":
                    out.append(DocumentRef(isin=isin, kind=kind, title=path.name, url=path.as_uri(), path=str(path), source=self.name))
        return out

    def fetch(self, ref: DocumentRef, target: Path) -> Path:
        source = Path(ref.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())  # copie : l'original n'est jamais ouvert en écriture
        return target


class FundShopFinder:
    """Même moteur que la page « Documents des fonds » : adresse apprise / construite depuis Product Info / page du fonds."""

    name = "site (adresse directe)"

    def __init__(self, resolver):
        self.resolver = resolver
        self.errors: list[str] = []
        self._content: dict[str, bytes] = {}

    def find(self, isin: str, fund_name: str, share_name: str) -> list[DocumentRef]:
        from ...fundshop.catalog import DOC_TYPES
        from ...fundshop.period import Period
        from ...fundshop.problems import DocumentProblem

        ident = self.resolver.identity(isin, fund_name, share_name)
        refs = []
        for key, kind in (("dic", "kid"), ("prospectus", "prospectus")):
            try:
                found = self.resolver.find(ident, DOC_TYPES[key], Period())
            except DocumentProblem as error:
                self.errors.append(f"{DOC_TYPES[key].label} : {error.problem.title.lower()}")
                continue
            self._content[found.url] = found.content
            refs.append(DocumentRef(isin=isin, kind=kind, title=f"{DOC_TYPES[key].label} (adresse {found.strategy})", url=found.url, lang="fr",
                                    source="site"))
        self.resolver.memory.save()
        return refs

    def fetch(self, ref: DocumentRef, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._content.pop(ref.url))
        return target
