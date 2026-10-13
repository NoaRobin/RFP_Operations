# -*- coding: utf-8 -*-
"""
OMNI_MENSUEL.py

Prépare les trois fichiers mensuels OMNI :

1. Holdings
2. Performance NET
3. Performance GROSS

Fonctionnement :

- Le Holdings source reste dans :
  03 - Sources

- JUMP actualise ce fichier.

- Le Holdings actualisé est copié dans :
  année / trimestre / Holdings

- Les performances sont recherchées dans Outlook.

- Si les performances ne sont pas trouvées, le Holdings reste enregistré
  dans le trimestre et le traitement se termine avec un statut PARTIEL.

- Si un nouveau trimestre doit être créé, le script reproduit les dossiers
  du trimestre précédent sans recopier ses fichiers.

Dépendances Windows :

    python -m pip install pywin32 openpyxl

Exemples :

    python "01 - Scripts\\OMNI_MENSUEL.py"

    python "01 - Scripts\\OMNI_MENSUEL.py" --month 7 --year 2026

    python "01 - Scripts\\OMNI_MENSUEL.py" --month 7 --year 2026 --skip-jump

    python "01 - Scripts\\OMNI_MENSUEL.py" --month 7 --year 2026 --force
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None


try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = Path(
    r"C:\Users\RP119879\Rothschild & Co\AM-RFP-CONF - Documents"
    r"\3 - Consultants\Automatisation - Python"
)

SCRIPTS_DIR = BASE_DIR / "01 - Scripts"
LOG_DIR = BASE_DIR / "02 - Journaux"
SOURCES_DIR = BASE_DIR / "03 - Sources"
TEMP_DIR = BASE_DIR / "04 - Temporaire"

CONSULTANTS_ROOT = Path(
    r"C:\Users\RP119879\Rothschild & Co\AM-RFP-CONF - Documents"
    r"\3 - Consultants"
)

JUMP_SCRIPT = SCRIPTS_DIR / "JUMP_OMNI.py"

SOURCE_HOLDINGS_DIR = SOURCES_DIR

OUTLOOK_SENDER = "laurent.tico@rothschildandco.com"

OUTLOOK_SUBJECT_WORDS = (
    "perf",
    "omni",
)

OUTLOOK_LOOKBACK_DAYS = 120

# Les performances du mois M sont généralement reçues
# au début du mois M+1.
OUTLOOK_NEXT_MONTH_END_DAY = 20

# Seuil ajusté après le contrôle réussi de juillet 2026 :
# 2 295 lignes constatées.
MIN_HOLDINGS_ROWS = 2000
MAX_HOLDINGS_ROWS = 4000

# Alerte indicative pour les valeurs numériques des performances.
PERFORMANCE_ABSOLUTE_ALERT = 1.0

DEFAULT_QUARTER_FOLDERS = (
    "AUM",
    "Characteristics",
    "Holdings",
    "Performances",
)


MONTHS_FR = {
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


LOG_FILE = LOG_DIR / "OMNI_MENSUEL.log"

STATE_FILE = LOG_DIR / "OMNI_MENSUEL_last_run.json"

LOCK_FILE = TEMP_DIR / "OMNI_MENSUEL.lock"


# =============================================================================
# STRUCTURES
# =============================================================================

@dataclass(frozen=True)
class Period:
    month: int
    year: int
    quarter: int
    closing_date: date

    @property
    def yyyymmdd(self) -> str:
        return self.closing_date.strftime("%Y%m%d")

    @property
    def label(self) -> str:
        return f"{MONTHS_FR[self.month]} {self.year}"


@dataclass(frozen=True)
class TargetPaths:
    quarter_dir: Path
    holdings_dir: Path
    performance_dir: Path
    holdings: Path
    net: Path
    gross: Path
    report: Path


class ControlledStop(RuntimeError):
    """
    Arrêt propre et expliqué du traitement.
    """

    pass


class PerformanceFilesMissing(RuntimeError):
    """
    Les performances NET ou GROSS n'ont pas été trouvées.
    Le Holdings peut néanmoins avoir été enregistré.
    """

    pass


# =============================================================================
# OUTILS GÉNÉRAUX
# =============================================================================

def normalize(value: object) -> str:
    """
    Normalise un texte pour faciliter les comparaisons.
    """

    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    return " ".join(
        text.casefold().split()
    )


def setup() -> None:
    """
    Crée les dossiers techniques et configure le journal.
    """

    for folder in (
        LOG_DIR,
        SOURCES_DIR,
        TEMP_DIR,
    ):
        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(
                LOG_FILE,
                mode="a",
                encoding="utf-8",
            ),
            logging.StreamHandler(
                sys.stdout
            ),
        ],
        force=True,
    )


def notify(
    title: str,
    message: str,
    error: bool = False,
) -> None:
    """
    Écrit dans le journal et affiche une fenêtre Windows.
    """

    if error:
        logging.error(
            message.replace("\n", " | ")
        )
    else:
        logging.info(
            message.replace("\n", " | ")
        )

    try:
        import ctypes

        flags = 0x10 if error else 0x40

        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            title,
            flags,
        )

    except Exception:
        pass


def write_state(
    status: str,
    period: Optional[Period],
    message: str,
    **extra,
) -> None:
    """
    Enregistre le résultat de la dernière exécution.
    """

    payload = {
        "timestamp": datetime.now().isoformat(
            timespec="seconds"
        ),
        "status": status,
        "period": asdict(period) if period else None,
        "message": message,
        **extra,
    }

    if period:
        payload["period"]["closing_date"] = (
            period.closing_date.isoformat()
        )

    STATE_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# =============================================================================
# VERROU
# =============================================================================

def acquire_lock() -> None:
    """
    Empêche deux exécutions simultanées.
    """

    if LOCK_FILE.exists():
        age_hours = (
            time.time()
            - LOCK_FILE.stat().st_mtime
        ) / 3600

        if age_hours < 6:
            raise ControlledStop(
                "Une exécution semble déjà en cours.\n\n"
                f"Fichier de verrouillage :\n{LOCK_FILE}\n\n"
                "Si aucune exécution n'est réellement ouverte, "
                "supprime ce fichier puis relance le programme."
            )

        logging.warning(
            "Ancien verrou détecté et supprimé : %s",
            LOCK_FILE,
        )

        LOCK_FILE.unlink(
            missing_ok=True
        )

    LOCK_FILE.write_text(
        str(os.getpid()),
        encoding="ascii",
    )


def release_lock() -> None:
    """
    Supprime le verrou à la fin du programme.
    """

    try:
        LOCK_FILE.unlink(
            missing_ok=True
        )

    except Exception as error:
        logging.warning(
            "Impossible de supprimer le verrou %s : %s",
            LOCK_FILE,
            error,
        )


# =============================================================================
# PÉRIODE
# =============================================================================

def previous_month(
    today: date,
) -> tuple[int, int]:
    """
    Retourne le mois précédent.
    """

    first_day = today.replace(
        day=1
    )

    previous = (
        first_day
        - timedelta(days=1)
    )

    return (
        previous.month,
        previous.year,
    )


def last_weekday(
    year: int,
    month: int,
) -> date:
    """
    Retourne le dernier jour du mois hors samedi et dimanche.

    Cette fonction ne connaît pas les jours fériés.
    L'option --closing-date permet de fournir une autre date.
    """

    if month == 12:
        result = (
            date(year + 1, 1, 1)
            - timedelta(days=1)
        )
    else:
        result = (
            date(year, month + 1, 1)
            - timedelta(days=1)
        )

    while result.weekday() >= 5:
        result -= timedelta(days=1)

    return result


def build_period(
    month: Optional[int],
    year: Optional[int],
    forced_date: Optional[str],
) -> Period:
    """
    Construit la période à traiter.
    """

    if (
        (month is None)
        != (year is None)
    ):
        raise ControlledStop(
            "--month et --year doivent être indiqués ensemble."
        )

    if month is None:
        month, year = previous_month(
            date.today()
        )

    month = int(month)
    year = int(year)

    if not 1 <= month <= 12:
        raise ControlledStop(
            "Le mois doit être compris entre 1 et 12."
        )

    if forced_date:
        try:
            closing = datetime.strptime(
                forced_date,
                "%Y-%m-%d",
            ).date()

        except ValueError as error:
            raise ControlledStop(
                "La date --closing-date doit respecter "
                "le format YYYY-MM-DD."
            ) from error

    else:
        closing = last_weekday(
            year,
            month,
        )

    if (
        closing.month != month
        or closing.year != year
    ):
        raise ControlledStop(
            "La date --closing-date doit appartenir "
            "au mois demandé."
        )

    quarter = (
        (month - 1) // 3
    ) + 1

    return Period(
        month=month,
        year=year,
        quarter=quarter,
        closing_date=closing,
    )


def previous_quarter_period(
    period: Period,
) -> tuple[int, int]:
    """
    Retourne l'année et le numéro du trimestre précédent.
    """

    if period.quarter == 1:
        return (
            period.year - 1,
            4,
        )

    return (
        period.year,
        period.quarter - 1,
    )


# =============================================================================
# DOSSIERS SHAREPOINT
# =============================================================================

def targets_for(
    period: Period,
) -> TargetPaths:
    """
    Calcule les chemins de destination du trimestre.
    """

    quarter_dir = (
        CONSULTANTS_ROOT
        / str(period.year)
        / f"Q{period.quarter} {period.year}"
    )

    holdings_dir = (
        quarter_dir
        / "Holdings"
    )

    performance_dir = (
        quarter_dir
        / "Performances"
    )

    return TargetPaths(
        quarter_dir=quarter_dir,
        holdings_dir=holdings_dir,
        performance_dir=performance_dir,
        holdings=(
    holdings_dir
    / f"Holdings {period.month}_{period.year}.xlsx"
),
        net=(
            performance_dir
            / f"Monthly perf NET of fees_{period.yyyymmdd}.xlsx"
        ),
        gross=(
            performance_dir
            / f"Monthly perf GROSS of fees_{period.yyyymmdd}.xlsx"
        ),
        report=(
            LOG_DIR
            / f"Controle_OMNI_{period.yyyymmdd}.json"
        ),
    )


def create_quarter_tree(
    period: Period,
    paths: TargetPaths,
) -> None:
    """
    Crée l'arborescence du trimestre.

    Si le trimestre n'existe pas :
    - le script reproduit les dossiers du trimestre précédent ;
    - aucun fichier du trimestre précédent n'est copié.

    Si le trimestre précédent n'est pas disponible :
    - le script crée les dossiers par défaut.

    Aucun dossier ni fichier existant n'est supprimé.
    """

    quarter_already_exists = (
        paths.quarter_dir.exists()
    )

    paths.quarter_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if quarter_already_exists:
        logging.info(
            "Arborescence trimestrielle déjà présente : %s",
            paths.quarter_dir,
        )

    else:
        previous_year, previous_quarter = (
            previous_quarter_period(period)
        )

        previous_quarter_dir = (
            CONSULTANTS_ROOT
            / str(previous_year)
            / f"Q{previous_quarter} {previous_year}"
        )

        copied_folder_count = 0

        if previous_quarter_dir.exists():
            for element in previous_quarter_dir.rglob("*"):
                if not element.is_dir():
                    continue

                relative_path = element.relative_to(
                    previous_quarter_dir
                )

                destination = (
                    paths.quarter_dir
                    / relative_path
                )

                destination.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                copied_folder_count += 1

            logging.info(
                "Nouvelle arborescence trimestrielle créée "
                "à partir des dossiers de %s : %s dossier(s) reproduit(s).",
                previous_quarter_dir,
                copied_folder_count,
            )

        else:
            logging.warning(
                "Trimestre précédent introuvable : %s. "
                "Création de l'arborescence par défaut.",
                previous_quarter_dir,
            )

    # Ces dossiers doivent toujours exister,
    # même s'ils n'étaient pas présents dans le trimestre précédent.
    for folder_name in DEFAULT_QUARTER_FOLDERS:
        (
            paths.quarter_dir
            / folder_name
        ).mkdir(
            parents=True,
            exist_ok=True,
        )

    paths.holdings_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths.performance_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


# =============================================================================
# CONTRÔLE DES FICHIERS EXCEL
# =============================================================================

def valid_xlsx(
    path: Path,
) -> bool:
    """
    Vérifie qu'un fichier existe, n'est pas vide
    et possède une structure XLSX valide.
    """

    return (
        path.is_file()
        and path.stat().st_size > 0
        and zipfile.is_zipfile(path)
    )


def find_source_holdings() -> Path:
    """
    Recherche le Holdings dans 03 - Sources.
    Un seul fichier Holdings*.xlsx doit être présent.
    """

    files = [
        path
        for path in SOURCE_HOLDINGS_DIR.glob(
            "Holdings*.xlsx"
        )
        if (
            path.is_file()
            and not path.name.startswith("~$")
        )
    ]

    if not files:
        raise ControlledStop(
            "Aucun fichier Holdings*.xlsx trouvé dans :\n"
            f"{SOURCE_HOLDINGS_DIR}"
        )

    files.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if len(files) > 1:
        names = "\n- ".join(
            str(path)
            for path in files
        )

        raise ControlledStop(
            "Plusieurs fichiers Holdings sont présents "
            "dans 03 - Sources.\n\n"
            "Conserve uniquement le fichier à actualiser :\n- "
            + names
        )

    selected = files[0]

    logging.info(
        "Source Holdings retenue : %s",
        selected,
    )

    return selected


# =============================================================================
# JUMP
# =============================================================================

def run_jump(
    source_holdings: Path,
) -> None:
    """
    Lance JUMP et contrôle que le Holdings a été modifié.
    """

    if not JUMP_SCRIPT.exists():
        raise ControlledStop(
            f"Script JUMP introuvable : {JUMP_SCRIPT}"
        )

    if not source_holdings.exists():
        raise ControlledStop(
            f"Holdings source introuvable : {source_holdings}"
        )

    modification_before = (
        source_holdings.stat().st_mtime
    )

    logging.info(
        "Lancement du script JUMP : %s",
        JUMP_SCRIPT,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(JUMP_SCRIPT),
        ],
        cwd=str(SCRIPTS_DIR),
    )

    if result.returncode != 0:
        raise ControlledStop(
            "Le script JUMP a échoué avec le code "
            f"{result.returncode}."
        )

    if not source_holdings.exists():
        raise ControlledStop(
            "Le fichier Holdings a disparu après "
            "l'exécution JUMP."
        )

    if not valid_xlsx(source_holdings):
        raise ControlledStop(
            "Le fichier Holdings enregistré par JUMP "
            "n'est pas un XLSX valide."
        )

    modification_after = (
        source_holdings.stat().st_mtime
    )

    if modification_after <= modification_before:
        raise ControlledStop(
            "JUMP s'est terminé sans modifier la date "
            "du fichier Holdings."
        )

    logging.info(
        "Actualisation JUMP confirmée pour : %s",
        source_holdings,
    )


# =============================================================================
# OUTLOOK
# =============================================================================

def all_folders(
    root,
) -> Iterable:
    """
    Parcourt tous les dossiers de la boîte Outlook principale.
    """

    yield root

    try:
        for child in root.Folders:
            yield from all_folders(
                child
            )

    except Exception:
        return


def smtp_sender(
    message,
) -> str:
    """
    Récupère l'adresse SMTP réelle de l'expéditeur.
    """

    try:
        address = str(
            message.SenderEmailAddress
            or ""
        ).strip().casefold()

        if address.startswith("/o="):
            sender = message.Sender

            if sender:
                exchange_user = (
                    sender.GetExchangeUser()
                )

                if exchange_user:
                    address = str(
                        exchange_user.PrimarySmtpAddress
                        or ""
                    ).strip().casefold()

        return address

    except Exception:
        return ""


def attachment_kind(
    name: str,
) -> Optional[str]:
    """
    Identifie une pièce jointe NET ou GROSS à partir de son nom.
    """

    normalized_name = normalize(
        name
    )

    if not normalized_name.endswith(
        ".xlsx"
    ):
        return None

    gross_markers = (
        "gross",
        "brut",
        "brute",
        "before fees",
        "avant frais",
    )

    net_markers = (
        " net ",
        "net of fees",
        "nette",
        "after fees",
        "apres frais",
    )

    if any(
        marker in normalized_name
        for marker in gross_markers
    ):
        return "gross"

    padded_name = (
        f" {normalized_name} "
    )

    if any(
        marker in padded_name
        for marker in net_markers
    ):
        return "net"

    return None


def outlook_period_window(
    period: Period,
) -> tuple[datetime, datetime]:
    """
    Retourne la fenêtre de réception attendue.

    Exemple :
    les performances de juillet 2026 sont recherchées
    entre le 1er et le 20 août 2026.
    """

    if period.month == 12:
        next_month = 1
        next_year = period.year + 1

    else:
        next_month = period.month + 1
        next_year = period.year

    start = datetime(
        next_year,
        next_month,
        1,
        0,
        0,
        0,
    )

    end = datetime(
        next_year,
        next_month,
        OUTLOOK_NEXT_MONTH_END_DAY,
        23,
        59,
        59,
    )

    return start, end


def message_matches_period(
    message,
    period: Period,
) -> bool:
    """
    Accepte un message si :

    1. la période apparaît explicitement dans l'objet ou le corps ;

    ou

    2. le message a été reçu au début du mois suivant.
    """

    subject = str(
        getattr(
            message,
            "Subject",
            "",
        )
        or ""
    )

    body = str(
        getattr(
            message,
            "Body",
            "",
        )
        or ""
    )

    full_text = normalize(
        f"{subject} {body}"
    )

    explicit_markers = {
        period.yyyymmdd,
        period.closing_date.strftime(
            "%d/%m/%Y"
        ),
        period.closing_date.strftime(
            "%d-%m-%Y"
        ),
        f"{MONTHS_FR[period.month]} {period.year}",
    }

    if any(
        normalize(marker) in full_text
        for marker in explicit_markers
    ):
        return True

    try:
        received = message.ReceivedTime

        received_datetime = datetime(
            received.year,
            received.month,
            received.day,
            received.hour,
            received.minute,
            received.second,
        )

        start, end = outlook_period_window(
            period
        )

        return (
            start
            <= received_datetime
            <= end
        )

    except Exception as error:
        logging.warning(
            "Impossible de contrôler la date du message '%s' : %s",
            subject,
            error,
        )

        return False


def fetch_performance_files(
    period: Period,
    work_dir: Path,
) -> tuple[Path, Path]:
    """
    Recherche les performances NET et GROSS dans Outlook.
    """

    if (
        pythoncom is None
        or win32com is None
    ):
        raise ControlledStop(
            "Module pywin32 absent.\n\n"
            "Lance cette commande :\n"
            "python -m pip install pywin32"
        )

    pythoncom.CoInitialize()

    found: dict[
        str,
        tuple[datetime, object, object],
    ] = {}

    inspected_messages = 0
    inspected_attachments = 0

    try:
        outlook = (
            win32com.client.Dispatch(
                "Outlook.Application"
            )
        )

        namespace = outlook.GetNamespace(
            "MAPI"
        )

        inbox = namespace.GetDefaultFolder(
            6
        )

        root = inbox.Parent

        cutoff = (
            datetime.now()
            - timedelta(
                days=OUTLOOK_LOOKBACK_DAYS
            )
        )

        expected_start, expected_end = outlook_period_window(
            period
        )

        logging.info(
            "Recherche Outlook dans la boîte principale "
            "et tous ses dossiers."
        )

        logging.info(
            "Fenêtre de réception acceptée pour %s : "
            "du %s au %s.",
            period.label,
            expected_start.strftime("%d/%m/%Y"),
            expected_end.strftime("%d/%m/%Y"),
        )

        for folder in all_folders(root):
            try:
                items = folder.Items

                try:
                    items.Sort(
                        "[ReceivedTime]",
                        True,
                    )
                except Exception:
                    pass

                for message in items:
                    try:
                        received = (
                            message.ReceivedTime
                        )

                        received_naive = datetime(
                            received.year,
                            received.month,
                            received.day,
                            received.hour,
                            received.minute,
                            received.second,
                        )

                        if received_naive < cutoff:
                            continue

                        sender = smtp_sender(
                            message
                        )

                        if sender != OUTLOOK_SENDER:
                            continue

                        subject = str(
                            getattr(
                                message,
                                "Subject",
                                "",
                            )
                            or ""
                        )

                        subject_normalized = normalize(
                            subject
                        )

                        if not all(
                            word in subject_normalized
                            for word in OUTLOOK_SUBJECT_WORDS
                        ):
                            continue

                        inspected_messages += 1

                        logging.info(
                            "Message Outlook candidat : "
                            "%s | %s | %s",
                            received_naive.strftime(
                                "%d/%m/%Y %H:%M"
                            ),
                            sender,
                            subject,
                        )

                        if not message_matches_period(
                            message,
                            period,
                        ):
                            logging.info(
                                "Message rejeté car sa période "
                                "ne correspond pas : %s",
                                subject,
                            )

                            continue

                        attachments = (
                            message.Attachments
                        )

                        attachment_count = (
                            attachments.Count
                        )

                        logging.info(
                            "Message accepté avec %s pièce(s) jointe(s) : %s",
                            attachment_count,
                            subject,
                        )

                        for index in range(
                            1,
                            attachment_count + 1,
                        ):
                            attachment = (
                                attachments.Item(index)
                            )

                            attachment_name = str(
                                attachment.FileName
                            )

                            inspected_attachments += 1

                            logging.info(
                                "Pièce jointe Outlook examinée : %s",
                                attachment_name,
                            )

                            kind = attachment_kind(
                                attachment_name
                            )

                            if kind is None:
                                logging.info(
                                    "Pièce jointe non reconnue comme "
                                    "NET ou GROSS : %s",
                                    attachment_name,
                                )

                                continue

                            logging.info(
                                "Pièce jointe reconnue comme %s : %s",
                                kind.upper(),
                                attachment_name,
                            )

                            if (
                                kind not in found
                                or received_naive > found[kind][0]
                            ):
                                found[kind] = (
                                    received_naive,
                                    message,
                                    attachment,
                                )

                    except Exception as error:
                        logging.debug(
                            "Message Outlook ignoré : %s",
                            error,
                        )

                        continue

            except Exception as error:
                logging.debug(
                    "Dossier Outlook ignoré : %s",
                    error,
                )

                continue

        missing = [
            kind.upper()
            for kind in (
                "net",
                "gross",
            )
            if kind not in found
        ]

        if missing:
            raise PerformanceFilesMissing(
                "Pièce(s) jointe(s) Performance "
                "introuvable(s) dans Outlook : "
                + ", ".join(missing)
                + ".\n\n"
                + f"Messages candidats examinés : {inspected_messages}\n"
                + f"Pièces jointes examinées : {inspected_attachments}\n"
                + f"Expéditeur recherché : {OUTLOOK_SENDER}\n"
                + "Objet recherché : contient Perf et Omni\n"
                + f"Période recherchée : {period.label}"
            )

        outputs: dict[str, Path] = {}

        for kind in (
            "net",
            "gross",
        ):
            (
                _,
                _,
                attachment,
            ) = found[kind]

            destination = (
                work_dir
                / f"performance_{kind}.xlsx"
            )

            destination.unlink(
                missing_ok=True
            )

            attachment.SaveAsFile(
                str(destination)
            )

            if not valid_xlsx(
                destination
            ):
                raise PerformanceFilesMissing(
                    "La pièce jointe "
                    f"{kind.upper()} téléchargée "
                    "n'est pas un fichier XLSX valide."
                )

            outputs[kind] = (
                destination
            )

            logging.info(
                "Pièce jointe %s récupérée : %s",
                kind.upper(),
                attachment.FileName,
            )

        return (
            outputs["net"],
            outputs["gross"],
        )

    finally:
        pythoncom.CoUninitialize()


# =============================================================================
# CONTRÔLES EXCEL
# =============================================================================

def workbook_stats(
    path: Path,
    kind: str,
) -> dict:
    """
    Contrôle le contenu général d'un fichier Excel.
    """

    if load_workbook is None:
        raise ControlledStop(
            "Module openpyxl absent.\n\n"
            "Lance cette commande :\n"
            "python -m pip install openpyxl"
        )

    workbook = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    report = {
        "file": str(path),
        "worksheets": [],
        "alerts": [],
    }

    total_nonempty_rows = 0

    try:
        for worksheet in workbook.worksheets:
            nonempty_rows = 0
            blank_inside = 0
            extreme_values = []

            max_column = (
                worksheet.max_column
                or 0
            )

            for row in worksheet.iter_rows():
                values = [
                    cell.value
                    for cell in row
                ]

                if not any(
                    value not in (
                        None,
                        "",
                    )
                    for value in values
                ):
                    continue

                nonempty_rows += 1

                last_nonempty_index = max(
                    (
                        index
                        for index, value
                        in enumerate(values)
                        if value not in (
                            None,
                            "",
                        )
                    ),
                    default=-1,
                )

                if last_nonempty_index >= 0:
                    blank_inside += sum(
                        value in (
                            None,
                            "",
                        )
                        for value in values[
                            : last_nonempty_index + 1
                        ]
                    )

                if kind in (
                    "net",
                    "gross",
                ):
                    for cell in row:
                        value = cell.value

                        if (
                            isinstance(
                                value,
                                (int, float),
                            )
                            and abs(value)
                            > PERFORMANCE_ABSOLUTE_ALERT
                        ):
                            extreme_values.append(
                                {
                                    "cell": cell.coordinate,
                                    "value": value,
                                }
                            )

                            if (
                                len(extreme_values)
                                >= 20
                            ):
                                break

            total_nonempty_rows += (
                nonempty_rows
            )

            report["worksheets"].append(
                {
                    "name": worksheet.title,
                    "rows_nonempty": nonempty_rows,
                    "max_columns": max_column,
                    "blank_cells_inside_used_rows": blank_inside,
                    "extreme_numeric_values_sample": extreme_values,
                }
            )

    finally:
        workbook.close()

    report["total_nonempty_rows"] = (
        total_nonempty_rows
    )

    if (
        kind == "holdings"
        and not (
            MIN_HOLDINGS_ROWS
            <= total_nonempty_rows
            <= MAX_HOLDINGS_ROWS
        )
    ):
        report["alerts"].append(
            "Nombre de lignes Holdings hors fourchette "
            f"{MIN_HOLDINGS_ROWS}-{MAX_HOLDINGS_ROWS} : "
            f"{total_nonempty_rows}"
        )

    return report


# =============================================================================
# COPIE DES FICHIERS
# =============================================================================

def safe_copy(
    source: Path,
    destination: Path,
    force: bool,
) -> None:
    """
    Copie un fichier de manière sécurisée.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if (
        destination.exists()
        and not force
    ):
        raise ControlledStop(
            "Fichier déjà présent :\n"
            f"{destination}\n\n"
            "Utilise --force uniquement si tu veux "
            "réellement le remplacer."
        )

    temporary_destination = (
        destination.with_suffix(
            destination.suffix
            + ".tmp"
        )
    )

    temporary_destination.unlink(
        missing_ok=True
    )

    shutil.copy2(
        source,
        temporary_destination,
    )

    if not valid_xlsx(
        temporary_destination
    ):
        temporary_destination.unlink(
            missing_ok=True
        )

        raise ControlledStop(
            "La copie de contrôle n'est pas "
            "un XLSX valide : "
            f"{destination.name}"
        )

    os.replace(
        temporary_destination,
        destination,
    )

    logging.info(
        "Fichier copié : %s",
        destination,
    )


# =============================================================================
# TRAITEMENT PRINCIPAL
# =============================================================================

def process(
    period: Period,
    paths: TargetPaths,
    skip_jump: bool,
    force: bool,
) -> dict:
    """
    Exécute le traitement mensuel.

    Le Holdings est copié dans le trimestre avant la recherche Outlook.

    Si NET ou GROSS sont introuvables, le Holdings reste enregistré.
    """

    run_dir = (
        TEMP_DIR
        / (
            f"run_{period.yyyymmdd}_"
            f"{datetime.now():%H%M%S}"
        )
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        source_holdings = (
            find_source_holdings()
        )

        if not skip_jump:
            run_jump(
                source_holdings
            )

        else:
            logging.info(
                "Actualisation JUMP ignorée grâce "
                "à l'option --skip-jump."
            )

        source_holdings = (
            find_source_holdings()
        )

        if not valid_xlsx(
            source_holdings
        ):
            raise ControlledStop(
                "Le fichier Holdings n'est pas "
                "un fichier XLSX valide :\n"
                f"{source_holdings}"
            )

        holdings_control = workbook_stats(
            source_holdings,
            "holdings",
        )

        create_quarter_tree(
            period,
            paths,
        )

        safe_copy(
            source=source_holdings,
            destination=paths.holdings,
            force=force,
        )

        partial_controls = {
            "period": asdict(period),
            "generated_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "status": "HOLDINGS_STORED",
            "holdings": holdings_control,
            "outputs": {
                "holdings": str(
                    paths.holdings
                ),
                "net": None,
                "gross": None,
            },
        }

        partial_controls["period"][
            "closing_date"
        ] = period.closing_date.isoformat()

        paths.report.write_text(
            json.dumps(
                partial_controls,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        logging.info(
            "Holdings enregistré dans le trimestre "
            "avant la recherche Outlook : %s",
            paths.holdings,
        )

        try:
            net_source, gross_source = (
                fetch_performance_files(
                    period,
                    run_dir,
                )
            )

        except PerformanceFilesMissing as error:
            message = (
                f"Traitement partiel pour {period.label}.\n\n"
                "Le Holdings a bien été contrôlé et enregistré :\n"
                f"{paths.holdings}\n\n"
                "Les performances n'ont pas été trouvées :\n"
                f"{error}\n\n"
                "Tu peux relancer plus tard avec --skip-jump."
            )

            partial_controls["status"] = (
                "PARTIAL"
            )

            partial_controls["message"] = (
                str(error)
            )

            paths.report.write_text(
                json.dumps(
                    partial_controls,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            return {
                "status": "PARTIAL",
                "message": message,
                "holdings": holdings_control,
                "net": {
                    "alerts": [
                        "Performance NET introuvable."
                    ]
                },
                "gross": {
                    "alerts": [
                        "Performance GROSS introuvable."
                    ]
                },
                "outputs": partial_controls[
                    "outputs"
                ],
            }

        net_control = workbook_stats(
            net_source,
            "net",
        )

        gross_control = workbook_stats(
            gross_source,
            "gross",
        )

        safe_copy(
            source=net_source,
            destination=paths.net,
            force=force,
        )

        safe_copy(
            source=gross_source,
            destination=paths.gross,
            force=force,
        )

        controls = {
            "period": asdict(period),
            "generated_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "status": "COMPLETE",
            "holdings": holdings_control,
            "net": net_control,
            "gross": gross_control,
            "outputs": {
                "holdings": str(
                    paths.holdings
                ),
                "net": str(
                    paths.net
                ),
                "gross": str(
                    paths.gross
                ),
            },
        }

        controls["period"][
            "closing_date"
        ] = period.closing_date.isoformat()

        paths.report.write_text(
            json.dumps(
                controls,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return controls

    finally:
        shutil.rmtree(
            run_dir,
            ignore_errors=True,
        )


# =============================================================================
# PROGRAMME
# =============================================================================

def main() -> int:
    """
    Point d'entrée du programme.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Préparation mensuelle Holdings, "
            "NET et GROSS pour OMNI"
        )
    )

    parser.add_argument(
        "--month",
        type=int,
        help="Mois à traiter, par exemple 7",
    )

    parser.add_argument(
        "--year",
        type=int,
        help="Année à traiter, par exemple 2026",
    )

    parser.add_argument(
        "--closing-date",
        help=(
            "Date exacte au format YYYY-MM-DD "
            "si la date doit être forcée"
        ),
    )

    parser.add_argument(
        "--skip-jump",
        action="store_true",
        help=(
            "Utilise le Holdings déjà actualisé "
            "dans 03 - Sources"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Remplace les fichiers cibles existants",
    )

    args = parser.parse_args()

    setup()

    period: Optional[Period] = None
    lock_acquired = False

    try:
        acquire_lock()

        lock_acquired = True

        period = build_period(
            args.month,
            args.year,
            args.closing_date,
        )

        paths = targets_for(
            period
        )

        logging.info(
            "Période OMNI : %s, clôture %s",
            period.label,
            period.closing_date,
        )

        logging.info(
            "Dossier cible : %s",
            paths.quarter_dir,
        )

        controls = process(
            period=period,
            paths=paths,
            skip_jump=args.skip_jump,
            force=args.force,
        )

        if (
            controls.get("status")
            == "PARTIAL"
        ):
            message = controls["message"]

            write_state(
                status="PARTIAL",
                period=period,
                message=message,
                outputs=controls.get(
                    "outputs",
                    {},
                ),
            )

            notify(
                title="OMNI mensuel partiel",
                message=message,
                error=False,
            )

            return 3

        alerts = (
            controls["holdings"]["alerts"]
            + controls["net"]["alerts"]
            + controls["gross"]["alerts"]
        )

        message = (
            f"Préparation OMNI terminée pour {period.label}.\n\n"
            f"Holdings :\n{paths.holdings}\n\n"
            f"NET :\n{paths.net}\n\n"
            f"GROSS :\n{paths.gross}\n\n"
            f"Rapport :\n{paths.report}"
        )

        if alerts:
            message += (
                "\n\nALERTES À VÉRIFIER :\n- "
                + "\n- ".join(alerts)
            )

        write_state(
            status=(
                "SUCCESS_WITH_ALERTS"
                if alerts
                else "SUCCESS"
            ),
            period=period,
            message=message,
            alerts=alerts,
            outputs=controls.get(
                "outputs",
                {},
            ),
        )

        notify(
            title="OMNI mensuel",
            message=message,
            error=False,
        )

        return 0

    except ControlledStop as error:
        message = str(error)

        write_state(
            status="STOPPED",
            period=period,
            message=message,
        )

        notify(
            title="OMNI - arrêt contrôlé",
            message=message,
            error=True,
        )

        return 2

    except Exception as error:
        logging.exception(
            "Erreur inattendue"
        )

        message = (
            "Erreur inattendue : "
            f"{type(error).__name__}: {error}\n\n"
            f"Consulte le journal :\n{LOG_FILE}"
        )

        write_state(
            status="ERROR",
            period=period,
            message=message,
        )

        notify(
            title="OMNI - erreur",
            message=message,
            error=True,
        )

        return 1

    finally:
        if lock_acquired:
            release_lock()


if __name__ == "__main__":
    sys.exit(
        main()
    )