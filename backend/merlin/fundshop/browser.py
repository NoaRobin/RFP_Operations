"""Dernier recours : le parcours du site historique (recherche par ISIN → page du fonds → Téléchargements → rubrique
→ mois → ligne du document), seulement pour **découvrir l'adresse** du PDF. Corrections par rapport au script :
la page ouverte doit porter l'ISIN demandé (sinon arrêt), le href est lu en texte (bug « bytes.casefold »),
une seule fenêtre, sans pause manuelle. Nécessite Playwright (facultatif)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from ..rfi.ontology import norm
from .catalog import DocType
from .period import Period
from .resolver import Identity

TIMEOUT = 45_000


class SiteBrowser:
    def __init__(self, base_url: str, headless: bool = True, channel: str | None = None):
        self.base_url = base_url
        self.headless = headless
        self.channel = channel
        self._pw = self._browser = self._page = None

    def available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except ImportError:
            return False

    def _open(self):
        if self._page is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            kwargs = {"headless": self.headless}
            if self.channel:
                kwargs["channel"] = self.channel
            self._browser = self._pw.chromium.launch(**kwargs)
            self._page = self._browser.new_page(accept_downloads=True)
        return self._page

    def close(self) -> None:
        for obj in (self._browser, self._pw):
            try:
                obj and (obj.close() if hasattr(obj, "close") else obj.stop())
            except Exception:  # noqa: BLE001
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self._page = None

    def __call__(self, ident: Identity, doc: DocType, period: Period) -> str:
        page = self._open()
        page.goto(self.base_url, wait_until="domcontentloaded", timeout=TIMEOUT)
        field = page.locator('input[type="search"]:visible, input[placeholder*="Recherch" i]:visible, input[placeholder*="ISIN" i]:visible').first
        field.fill(ident.isin)
        field.press("Enter")
        page.wait_for_timeout(2500)
        link = page.locator(f'a:has-text("{ident.fund}")').first if ident.fund else page.locator("a[href*='/nos-fonds/']").first
        link.click()
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        if ident.isin not in page.locator("body").inner_text():
            raise RuntimeError(f"page ouverte sans l'ISIN {ident.isin} ({page.url})")
        page.goto(page.url.split("#")[0] + "#documentation", wait_until="domcontentloaded", timeout=TIMEOUT)
        page.wait_for_timeout(1500)
        section = page.get_by_text(re.compile(rf"^\s*{re.escape(doc.section)}\s*$", re.I)).first
        if section.count():
            section.click()
            page.wait_for_timeout(800)
        if doc.needs_month and period.month:
            current = page.get_by_text(re.compile(r"^(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+20\d{2}$", re.I)).first
            if current.count() and norm(current.inner_text()) != norm(period.label):
                current.click()
                page.get_by_text(re.compile(rf"^\s*{re.escape(period.label)}\s*$", re.I)).first.click()
                page.wait_for_timeout(1000)
        for label in doc.site_labels:
            row = page.get_by_text(re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)).first
            if not row.count():
                continue
            for level in range(0, 6):
                scope = row if level == 0 else row.locator("xpath=" + "/.." * level)
                links = scope.locator("a[href]")
                for n in range(links.count()):
                    href = str(links.nth(n).get_attribute("href") or "")
                    if href.lower().endswith(".pdf") or "docs.am." in href:
                        return urljoin(page.url, href)
        raise RuntimeError("document introuvable sur la page du fonds")
