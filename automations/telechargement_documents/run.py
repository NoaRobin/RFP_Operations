"""Téléchargement de la liste de documents (page « Documents des fonds »), sans navigateur."""
from __future__ import annotations

import pandas as pd

from merlin.config import get_settings
from merlin.fundshop.runner import precheck, run_list, save_last_run
from merlin.fundshop.service import destination, resolver, root, shopping_list

COLUMNS = {"fund": "Fonds", "part": "Part", "isin": "ISIN", "kind": "Document", "period": "Mois", "status": "Statut", "title": "Résultat",
           "why": "Pourquoi", "fix": "Que faire", "file": "Fichier", "url": "Adresse"}


def run(ctx, mode: str = "missing", types: list[str] | None = None) -> None:
    settings = get_settings()
    with ctx.step("Préparation de la liste"):
        items = [i for i in shopping_list(settings).load() if i.active and (not types or i.kind in types)]
        dest = destination(settings)
        ctx.log.info("%d document(s) à traiter · dossier : %s", len(items), dest)
        if not items:
            ctx.set_summary("Liste vide : ajoutez des documents dans « Documents des fonds ».", total=0, minutes_saved=0)
            return
    with ctx.step("Vérification du réseau et du dossier"):
        res = resolver(settings, ctx.data)
        blocked = precheck(res, dest)
        if blocked:
            ctx.log.error("%s. %s → %s", blocked.title, blocked.why, blocked.fix)
        else:
            ctx.log.info("Site joignable (%s).", res.net.active)
    with ctx.step("Téléchargements"):
        results = run_list(items, res, dest, only_missing=(mode != "all"), blocked=blocked,
                           log=lambda level, msg: getattr(ctx.log, level, ctx.log.info)(msg), progress=lambda v: ctx.progress(v * 0.95))
        save_last_run(root(settings), results, dest, res.net.active if not blocked else "", blocked)
    with ctx.step("Rapport"):
        frame = pd.DataFrame([r.to_dict() for r in results])[list(COLUMNS)].rename(columns=COLUMNS)
        ctx.show_table(frame.drop(columns=["Adresse"]), "Résultats")
        ctx.save_excel(frame, "Rapport_telechargement_documents", label="Rapport de téléchargement")
        ok = sum(r.status == "OK" for r in results)
        present = sum(r.status == "DÉJÀ PRÉSENT" for r in results)
        failed = sum(r.status == "ÉCHEC" for r in results)
        if blocked:
            ctx.set_summary(f"Rien n'a pu être téléchargé : {blocked.title.lower()}. {blocked.fix}", ok=0, deja=present, echecs=failed, minutes_saved=0)
        else:
            ctx.set_summary(f"{ok} téléchargé(s), {present} déjà présent(s), {failed} à regarder.", ok=ok, deja=present, echecs=failed,
                            destination=str(dest), minutes_saved=ok)  # estimation prudente : 1 min par document réellement téléchargé
