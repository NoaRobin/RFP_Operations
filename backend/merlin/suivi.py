"""Suivi d'activité RFP & Due Diligence (application tryv2, reprise telle quelle dans backend/vendor/suivi).

Montée sous /suivi ; ses données (classeur du pôle, grilles tarifaires) vivent dans data/suivi, jamais dans le dépôt.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("merlin.suivi")
VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "suivi"


def build_suivi_app(data_dir: Path):
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    try:
        import core  # noqa: PLC0415 — module de tryv2

        target = data_dir / "suivi"
        target.mkdir(parents=True, exist_ok=True)
        core.DOSSIER_DONNEES = target
        core.FICHIER_BRANCHEMENT = target / "branchement.json"
        import server  # noqa: PLC0415 — importe tarification, qui lit core.DOSSIER_DONNEES

        return server.app
    except Exception:  # noqa: BLE001 — le reste de l'app doit démarrer même si le suivi échoue
        log.exception("Le module Suivi d'activité n'a pas pu démarrer")
        return None
