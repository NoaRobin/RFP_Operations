"""Téléchargement de la liste de documents (liste éditée dans l'app, page « Documents des fonds »)."""
from __future__ import annotations

import pandas as pd

from merlin.config import get_settings
from merlin.fundshop.runner import run_list
from merlin.fundshop.service import destination, resolver, shopping_list


def run(ctx, mode: str = "missing", types: list[str] | None = None, navigateur: bool = True) -> None:
    settings = get_settings()
    with ctx.step("Préparation de la liste"):
        items = [i for i in shopping_list(settings).load() if i.active and (not types or i.kind in types)]
        dest = destination(settings)
        ctx.log.info("%d document(s) à traiter · destination : %s", len(items), dest)
        if not items:
            ctx.set_summary("Liste vide : ajoutez des documents dans « Documents des fonds ».", total=0)
            return
    with ctx.step("Téléchargements"):
        res, browser = resolver(settings, ctx.data, with_browser=navigateur)
        if navigateur and browser is None:
            ctx.log.warning("Navigateur indisponible (Playwright non installé) : adresses directes seulement.")
        try:
            results = run_list(items, res, dest, only_missing=(mode != "all"),
                               log=lambda level, msg: getattr(ctx.log, level, ctx.log.info)(msg), progress=lambda v: ctx.progress(v * 0.9))
        finally:
            if browser is not None:
                browser.close()
    with ctx.step("Rapport"):
        frame = pd.DataFrame([r.to_dict() for r in results])
        ctx.show_table(frame[["fund", "isin", "kind", "period", "status", "detail", "file"]] if len(frame) else frame, "Résultats")
        ctx.save_excel(frame, "Rapport_telechargement_documents", label="Rapport de téléchargement")
        ok = sum(r.status == "OK" for r in results)
        present = sum(r.status == "DÉJÀ PRÉSENT" for r in results)
        failed = sum(r.status == "ÉCHEC" for r in results)
        ctx.set_summary(f"{ok} téléchargé(s), {present} déjà présent(s), {failed} échec(s).", ok=ok, deja=present, echecs=failed,
                        destination=str(dest))
        if failed:
            ctx.log.warning("%d échec(s) : voir le rapport (raison par ligne).", failed)
