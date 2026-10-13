from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import (
    BrowserContext,
    Download,
    Locator,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

BASE_URL = "https://am.eu.rothschildandco.com/fr/nos-fonds/"
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
EXCEL_FILE = ROOT_DIR / "Liste de courses.xlsx"
DEST_DIR = Path(
    r"C:\Users\RP119879\Rothschild & Co\AM-RFP-CONF - Documents\7 - Ressources\Stagiaire\FundShop"
)
PROFILE_DIR = SCRIPT_DIR / "session_edge"
CSV_LOG = ROOT_DIR / "resultats_telechargement.csv"
TEXT_LOG = ROOT_DIR / "telechargement_documents.log"
STATE_FILE = ROOT_DIR / "telechargement_documents_last_run.json"

TIMEOUT = 60_000
DOWNLOAD_TIMEOUT = 30_000
WAIT = 1_500
MIN_SIZE = 1_000

DOCS = {
    "reporting mensuel": ("Reporting", ["Reporting Mensuel"], True),
    "reporting mensuel en": ("Reporting", ["Reporting Mensuel [EN]"], True),
    "dic": ("Documents juridiques", ["DIC PRIIPS"], False),
    "prospectus": ("Documents juridiques", ["Prospectus"], False),
    "annexe sfdr": ("Documents ESG", ["Annexe SFDR"], False),
    "annexe sfdr en": (
    "Documents ESG",
    [
        "Annexe SFDR [EN]",
        "Annexe SFDR - EN",
        "Annexe SFDR EN",
        "SFDR Annex",
        "SFDR Annex [EN]",
    ],
    False,
),
    "article 10 sfdr": ("Documents ESG", ["Article 10 SFDR"], False),
    "rapport periodique sfdr": (
        "Documents ESG",
        ["Rapport périodique SFDR", "Rapport periodique SFDR"],
        False,
    ),
}

MONTHS = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
}


class ControlledError(RuntimeError):
    pass


@dataclass(frozen=True)
class Period:
    month: Optional[int] = None
    year: Optional[int] = None

    @property
    def label(self) -> str:
        if self.month and self.year:
            return f"{MONTHS[self.month]} {self.year}"
        return str(self.year) if self.year else "non précisée"


@dataclass(frozen=True)
class Request:
    row: int
    fund: str
    isin: str
    part: str
    kind: str
    period: Period
    filename: str
    overwrite: bool = False


@dataclass
class Result:
    ligne: int
    fonds: str
    isin: str
    type_document: str
    statut: str
    detail: str
    part: str = ""
    libelle_site: str = ""
    url_source: str = ""
    chemin_final: str = ""
    taille_octets: int = 0
    sha256: str = ""
    date_traitement: str = ""


def norm(value: object) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or ""))
    text_value = "".join(
        character
        for character in text_value
        if not unicodedata.combining(character)
    )
    return " ".join(text_value.casefold().replace("’", "'").split())


def empty(value: object) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return norm(value) in {"", "nan", "nat", "none", "null"}


def text(value: object) -> str:
    return "" if empty(value) else str(value).strip()


def as_bool(value: object, default: bool = False) -> bool:
    normalized = norm(text(value))
    if normalized in {"oui", "yes", "true", "vrai", "1", "x"}:
        return True
    if normalized in {"non", "no", "false", "faux", "0"}:
        return False
    return default


def safe_name(value: object) -> str:
    name = text(value)
    for character in '<>:"/\\|?*':
        name = name.replace(character, "-")
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    if not name:
        raise ControlledError("Nom final vide.")
    if not Path(name).suffix:
        name += ".pdf"
    return name


def canonical_kind(value: object) -> str:
    kind = norm(text(value))
    aliases = {
        "dic priips": "dic",
        "rapport mensuel": "reporting mensuel",
        "rapport périodique sfdr": "rapport periodique sfdr",
    }
    kind = aliases.get(kind, kind)
    if kind not in DOCS:
        raise ControlledError(
            "Type inconnu: "
            + text(value)
            + ". Valeurs: "
            + ", ".join(DOCS)
        )
    return kind


def parse_period(month_value: object, year_value: object) -> Period:
    year = None if empty(year_value) else int(float(text(year_value)))

    if empty(month_value):
        return Period(None, year)

    if isinstance(month_value, (pd.Timestamp, datetime)):
        return Period(int(month_value.month), int(month_value.year))

    raw = text(month_value)
    for date_format in ("%m/%Y", "%m-%Y", "%Y-%m", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw.split()[0], date_format)
            return Period(parsed.month, parsed.year)
        except ValueError:
            pass

    normalized = norm(raw)
    for month_number, month_label in MONTHS.items():
        if norm(month_label) in normalized or norm(month_label[:4]) in normalized:
            long_year = re.search(r"\b(20\d{2})\b", normalized)
            short_year = re.search(r"(?:-|/|\s)(\d{2})\b", normalized)
            parsed_year = (
                int(long_year.group(1))
                if long_year
                else 2000 + int(short_year.group(1))
                if short_year
                else year
            )
            return Period(month_number, parsed_year)

    raise ControlledError(f"Mois non reconnu: {raw}")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_pdf(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MIN_SIZE:
        path.unlink(missing_ok=True)
        raise ControlledError("Fichier absent ou trop petit.")

    with path.open("rb") as file_handle:
        signature = file_handle.read(5)

    if path.suffix.casefold() == ".pdf" and not signature.startswith(b"%PDF"):
        path.unlink(missing_ok=True)
        raise ControlledError("Le fichier reçu n'est pas un PDF valide.")


def load_requests() -> list[Request]:
    if not EXCEL_FILE.exists():
        raise ControlledError(f"Fichier Excel introuvable: {EXCEL_FILE}")

    try:
        dataframe = pd.read_excel(EXCEL_FILE, engine="openpyxl")
    except PermissionError as error:
        raise ControlledError(
            f"Ferme Excel: {EXCEL_FILE.name} est verrouillé."
        ) from error

    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    required = ["Fonds", "ISIN", "Part", "Type de document", "Nom final"]
    missing = [column for column in required if column not in dataframe.columns]

    if missing:
        raise ControlledError(f"Colonnes manquantes: {missing}")

    requests: list[Request] = []
    errors: list[str] = []

    for index, row in dataframe.dropna(how="all").iterrows():
        line = int(index) + 2

        if "Actif" in dataframe.columns and not as_bool(row.get("Actif"), True):
            continue

        try:
            fund = text(row.get("Fonds"))
            isin = text(row.get("ISIN")).upper()
            part = text(row.get("Part"))

            if not fund or not isin:
                raise ControlledError("Fonds ou ISIN vide.")

            kind = canonical_kind(row.get("Type de document"))
            period = parse_period(row.get("Mois demandé"), row.get("Année"))

            if DOCS[kind][2] and not (period.month and period.year):
                raise ControlledError("Ce type exige un mois et une année.")

            requests.append(
                Request(
                    row=line,
                    fund=fund,
                    isin=isin,
                    part=part,
                    kind=kind,
                    period=period,
                    filename=safe_name(row.get("Nom final")),
                    overwrite=as_bool(row.get("Écraser"), False),
                )
            )
        except Exception as error:
            errors.append(f"Ligne {line}: {error}")

    if errors:
        raise ControlledError("Tableau invalide:\n- " + "\n- ".join(errors))
    if not requests:
        raise ControlledError("Aucune demande à traiter.")

    return requests


def first_visible(locator: Locator) -> Optional[Locator]:
    for index in range(locator.count()):
        item = locator.nth(index)
        try:
            if item.is_visible():
                return item
        except Exception:
            pass
    return None


def open_fund(page: Page, request: Request) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    fields = page.locator(
        'input[type="search"]:visible, '
        'input[placeholder*="Recherch" i]:visible, '
        'input[placeholder*="ISIN" i]:visible'
    )
    if fields.count() == 0:
        raise ControlledError("Champ de recherche introuvable.")

    field = fields.first
    field.fill("")
    field.fill(request.isin)
    try:
        field.press("Enter")
    except Exception:
        pass

    page.wait_for_timeout(3000)

    candidates = page.get_by_text(request.fund, exact=False)
    result = first_visible(candidates)
    if result is None:
        raise ControlledError(
            f"Fonds introuvable: {request.fund} / {request.isin}"
        )

    link = result.locator("xpath=ancestor::a[1]")
    clickable = link.first if link.count() else result
    clickable.click()
    page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    page.wait_for_timeout(WAIT)

    body_text = norm(page.locator("body").inner_text())
    if norm(request.isin) not in body_text:
        part_detail = f" | Part demandée: {request.part}" if request.part else ""
        logging.warning(
            "L'ISIN demandé n'est pas visible sur la page ouverte: %s%s | URL: %s",
            request.isin,
            part_detail,
            page.url,
        )
    else:
        logging.info(
            "Fonds vérifié: %s | %s | Part: %s",
            request.fund,
            request.isin,
            request.part or "non précisée",
        )


def open_downloads(page: Page) -> None:
    page.goto(
        page.url.split("#")[0] + "#documentation",
        wait_until="domcontentloaded",
        timeout=TIMEOUT,
    )
    page.wait_for_timeout(2500)

    title = first_visible(
        page.get_by_text(
            re.compile(r"^\s*Téléchargements\s*$", re.I),
            exact=True,
        )
    )
    if title is not None:
        title.scroll_into_view_if_needed()
    page.wait_for_timeout(WAIT)


def document_is_visible(page: Page, labels: list[str]) -> bool:
    for label in labels:
        candidate = first_visible(
            page.get_by_text(
                re.compile(rf"^\s*{re.escape(label)}\s*$", re.I),
                exact=True,
            )
        )
        if candidate is not None:
            return True
    return False


def click_section(page: Page, title: str, expected_labels: list[str]) -> None:
    """Laisse la rubrique ouverte, quel que soit son état initial."""
    if document_is_visible(page, expected_labels):
        logging.info("Rubrique déjà ouverte: %s", title)
        return

    title_locator = first_visible(
        page.get_by_text(
            re.compile(rf"^\s*{re.escape(title)}\s*$", re.I),
            exact=True,
        )
    )
    if title_locator is None:
        raise ControlledError(f"Rubrique introuvable: {title}")

    title_locator.scroll_into_view_if_needed()
    control = title_locator

    for xpath in (
        "xpath=ancestor::button[1]",
        "xpath=ancestor::*[@role='button'][1]",
        "xpath=ancestor::*[@aria-expanded][1]",
    ):
        candidate = title_locator.locator(xpath)
        if candidate.count():
            control = candidate.first
            break

    try:
        control.click()
    except Exception:
        control.click(force=True)

    page.wait_for_timeout(WAIT)

    if not document_is_visible(page, expected_labels):
        page.wait_for_timeout(1500)

    if not document_is_visible(page, expected_labels):
        raise ControlledError(
            f"La rubrique {title} a été ouverte, mais aucun document attendu "
            "n'est visible."
        )

    logging.info("Rubrique ouverte et vérifiée: %s", title)


def click_custom_month(page: Page, period: Period) -> None:
    target = period.label
    month_pattern = re.compile(
        r"^(janvier|février|mars|avril|mai|juin|juillet|août|septembre|"
        r"octobre|novembre|décembre)\s+20\d{2}$",
        re.I,
    )

    current = first_visible(page.get_by_text(month_pattern, exact=True))
    if current is None:
        raise ControlledError("Contrôle du mois introuvable dans Reporting.")

    if norm(current.inner_text()) == norm(target):
        return

    current.scroll_into_view_if_needed()
    clickable = current

    for xpath in (
        "xpath=ancestor::button[1]",
        "xpath=ancestor::*[@role='combobox'][1]",
        "xpath=ancestor::*[@aria-haspopup][1]",
        "xpath=parent::*",
    ):
        candidate = current.locator(xpath)
        if candidate.count():
            clickable = candidate.first
            break

    try:
        clickable.click()
    except Exception:
        clickable.click(force=True)

    page.wait_for_timeout(500)
    option = first_visible(
        page.get_by_text(
            re.compile(rf"^\s*{re.escape(target)}\s*$", re.I),
            exact=True,
        )
    )
    if option is None:
        raise ControlledError(f"Option de mois introuvable: {target}")

    option.click()
    page.wait_for_timeout(WAIT)
    logging.info("Mois sélectionné: %s", target)


def find_document_control(page: Page, labels: list[str]) -> tuple[Locator, str]:
    """Trouve le contrôle présent dans la même ligne que le document."""
    known_labels = [
        document_label
        for _, document_labels, _ in DOCS.values()
        for document_label in document_labels
    ]

    for label in labels:
        label_locator = first_visible(
            page.get_by_text(
                re.compile(rf"^\s*{re.escape(label)}\s*$", re.I),
                exact=True,
            )
        )
        if label_locator is None:
            continue

        label_locator.scroll_into_view_if_needed()

        for level in range(0, 8):
            row = (
                label_locator
                if level == 0
                else label_locator.locator("xpath=" + "/.." * level)
            )
            if row.count() == 0:
                continue

            controls = row.locator("a[href], button")
            visible_controls: list[Locator] = []
            for index in range(controls.count()):
                control = controls.nth(index)
                try:
                    if control.is_visible():
                        visible_controls.append(control)
                except Exception:
                    pass

            if not visible_controls:
                continue

            row_text = norm(row.inner_text())
            labels_in_row = sum(
                1 for known_label in known_labels if norm(known_label) in row_text
            )
            if labels_in_row > 1:
                continue

            for control in visible_controls:
                href = control.get_attribute("href") or ""
                if href and not href.startswith("#"):
                    logging.info("Document ciblé: %s | href=%s", label, href)
                    return control, label

            logging.info("Document ciblé: %s | bouton de la même ligne", label)
            return visible_controls[-1], label

    raise ControlledError(
        "Document introuvable après ouverture de la rubrique. Libellés: "
        + ", ".join(labels)
    )


def download_pdf(
    page: Page,
    context: BrowserContext,
    control: Locator,
    destination: Path,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    href = control.get_attribute("href") or ""
    if href and not href.casefold().startswith(("#", "javascript:", "blob:")):
        url = urljoin(page.url, href)
        try:
            response = context.request.get(url, timeout=TIMEOUT)
            body = response.body()
            content_type = response.headers.get("content-type", "").casefold()
            is_html = body[:100].lstrip().lower().startswith(b"<!doctype html")
            if (
                response.ok
                and len(body) >= MIN_SIZE
                and "text/html" not in content_type
                and not is_html
            ):
                destination.write_bytes(body)
                return url
        except Exception:
            logging.exception("Téléchargement direct impossible, essai par clic.")

    try:
        with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as event:
            control.click()
        download: Download = event.value
        download.save_as(str(destination))
        return download.url or page.url
    except PWTimeout as error:
        raise ControlledError(
            "Le document a été ciblé, mais aucun téléchargement n'a démarré."
        ) from error


def process(page: Page, context: BrowserContext, request: Request) -> Result:
    destination = DEST_DIR / request.filename
    timestamp = datetime.now().isoformat(timespec="seconds")

    if destination.exists() and not request.overwrite:
        return Result(
            ligne=request.row,
            fonds=request.fund,
            isin=request.isin,
            type_document=request.kind,
            statut="DÉJÀ PRÉSENT",
            detail="Fichier déjà présent.",
            part=request.part,
            chemin_final=str(destination),
            taille_octets=destination.stat().st_size,
            sha256=digest(destination),
            date_traitement=timestamp,
        )

    open_fund(page, request)
    open_downloads(page)

    section, labels, needs_month = DOCS[request.kind]
    click_section(page, section, labels)

    if needs_month:
        click_custom_month(page, request.period)

    control, site_label = find_document_control(page, labels)
    source = download_pdf(page, context, control, destination)
    validate_pdf(destination)

    return Result(
        ligne=request.row,
        fonds=request.fund,
        isin=request.isin,
        type_document=request.kind,
        statut="OK",
        detail="Document téléchargé depuis sa propre ligne.",
        part=request.part,
        libelle_site=site_label,
        url_source=source,
        chemin_final=str(destination),
        taille_octets=destination.stat().st_size,
        sha256=digest(destination),
        date_traitement=timestamp,
    )


def save_results(results: list[Result]) -> None:
    with CSV_LOG.open("w", newline="", encoding="utf-8-sig") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=list(Result.__dataclass_fields__),
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    state = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "ok": sum(result.statut == "OK" for result in results),
        "deja": sum(result.statut == "DÉJÀ PRÉSENT" for result in results),
        "echecs": sum(result.statut == "ÉCHEC" for result in results),
    }
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(TEXT_LOG, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    try:
        if not DEST_DIR.exists():
            raise ControlledError(f"Dossier cible introuvable: {DEST_DIR}")

        requests = load_requests()
        logging.info("%s demande(s) validée(s).", len(requests))

        if args.validate_only:
            print(f"VALIDATION OK : {len(requests)} demande(s).")
            return 0
    except Exception as error:
        logging.error("Validation impossible: %s", error)
        print(f"ERREUR: {error}")
        return 2

    results: list[Result] = []

    with sync_playwright() as playwright:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="msedge",
            headless=args.headless,
            slow_mo=0 if args.headless else 120,
            accept_downloads=True,
            viewport={"width": 1450, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

            if not args.headless:
                print(
                    "Edge est ouvert. Vérifie la liste des fonds puis appuie sur Entrée."
                )
                input()

            for position, request in enumerate(requests, 1):
                print(
                    f"[{position}/{len(requests)}] "
                    f"{request.fund} | {request.kind}"
                )
                final_error: Optional[Exception] = None

                for attempt in range(1, 3):
                    try:
                        result = process(page, context, request)
                        results.append(result)
                        print(f"  {result.statut}: {result.detail}")
                        final_error = None
                        break
                    except Exception as error:
                        final_error = error
                        logging.exception(
                            "Ligne %s tentative %s/2",
                            request.row,
                            attempt,
                        )
                        page.wait_for_timeout(1000)

                if final_error is not None:
                    results.append(
                        Result(
                            ligne=request.row,
                            fonds=request.fund,
                            isin=request.isin,
                            type_document=request.kind,
                            statut="ÉCHEC",
                            detail=str(final_error),
                            part=request.part,
                            date_traitement=datetime.now().isoformat(
                                timespec="seconds"
                            ),
                        )
                    )
                    print(f"  ÉCHEC: {final_error}")

                save_results(results)
        finally:
            save_results(results)
            context.close()

    ok_count = sum(result.statut == "OK" for result in results)
    already_count = sum(
        result.statut == "DÉJÀ PRÉSENT" for result in results
    )
    failure_count = sum(result.statut == "ÉCHEC" for result in results)

    print("=" * 65)
    print(
        f"TERMINÉ | OK: {ok_count} | "
        f"DÉJÀ PRÉSENTS: {already_count} | ÉCHECS: {failure_count}"
    )
    print(f"Journal: {CSV_LOG}")

    return 1 if failure_count else 0


if __name__ == "__main__":
    sys.exit(main())
