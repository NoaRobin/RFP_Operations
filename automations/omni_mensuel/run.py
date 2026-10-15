"""OMNI mensuel : Holdings + performances NET / GROSS, contrôlés et rangés dans l'arborescence trimestrielle."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from merlin.config import get_settings
from merlin.omni import holdings as H
from merlin.omni import performance as PF
from merlin.omni.period import build
from merlin.omni.tree import ensure_tree, previous_holdings, safe_place, targets, valid_xlsx


def run(ctx, mois: int | None = None, annee: int | None = None, holdings: str = "fabric", outlook: bool = True, ecraser: bool = False) -> None:
    settings = get_settings().omni
    root = Path(settings.root) if settings.root else get_settings().data_dir / "omni"
    inbox = Path(settings.inbox) if settings.inbox else get_settings().data_dir / "omni" / "depot"
    inbox.mkdir(parents=True, exist_ok=True)
    report: dict = {"statut": "ÉCHEC", "alertes": []}
    work = ctx.output_dir / "travail"
    work.mkdir(parents=True, exist_ok=True)

    with ctx.step("Période et dossiers"):
        p = build(ctx.data, mois, annee)
        t = targets(root, p)
        for note in ensure_tree(root, p):
            ctx.log.info(note)
        ctx.log.info("Période : %s · date d'arrêté %s (%s) · %s", p.label, p.closing.strftime("%d/%m/%Y"), p.closing_source, t.quarter_dir)
        report.update({"periode": p.label, "date_arrete": p.closing.isoformat(), "source_date": p.closing_source, "cibles": t.to_dict()})
        if p.closing_source != "JUMP":
            ctx.log.warning("Aucun inventaire JUMP ce mois-ci dans Fabric : date calculée (jours fériés non pris en compte).")

    with ctx.step("Holdings"):
        template = previous_holdings(root, p)
        if holdings == "skip":
            ctx.log.info("Holdings non refaits (option choisie).")
        elif holdings == "jump_excel":
            if not settings.jump_script or not Path(settings.jump_script).exists():
                raise RuntimeError("Mode JUMP Excel : renseignez OMNI_JUMP_SCRIPT (chemin de JUMP_OMNI.py) dans .env.")
            ctx.log.info("Actualisation par le complément JUMP Excel (script historique)…")
            code = subprocess.run([sys.executable, settings.jump_script], cwd=str(Path(settings.jump_script).parent)).returncode
            if code != 0:
                raise RuntimeError(f"JUMP_OMNI.py a échoué (code {code}).")
            ctx.log.success("Holdings actualisé par JUMP Excel : le script historique gère sa copie.")
        else:
            res = H.build(ctx.data, p.closing.isoformat(), template)
            report["holdings"] = {"lignes": len(res.frame), "format": res.layout, "colonnes_sans_equivalent": res.unmapped, "controles": res.checks}
            ctx.log.info("%d lignes · %d fonds · format : %s", len(res.frame), res.frame.iloc[:, 0].nunique() if len(res.frame) else 0, res.layout)
            for alert in res.alerts:
                ctx.log.warning(alert)
            report["alertes"] += res.alerts
            if res.frame.empty:
                raise RuntimeError("Aucune ligne d'inventaire dans Fabric à la date d'arrêté : rien n'est écrit.")
            local = H.write(res.frame, ctx.output_dir / t.holdings.name)
            ctx.register_file(local, "excel", "Holdings du mois")
            try:
                safe_place(local, t.holdings, ecraser)
                ctx.log.success("Holdings rangé : %s", t.holdings)
            except FileExistsError as error:
                ctx.log.warning("%s (cochez « Remplacer » pour l'écraser)", error)
                report["alertes"].append(str(error))

    with ctx.step("Performances"):
        files = PF.from_folder(inbox, p, work)
        if not files.complete and outlook and settings.sender:
            more = PF.from_outlook(p, work, settings.sender, tuple(w.strip() for w in settings.subject_words.split(",") if w.strip()))
            files.net, files.gross = files.net or more.net, files.gross or more.gross
            files.origin.update({k: v for k, v in more.origin.items() if k not in files.origin})
            files.notes += more.notes
        elif not files.complete and outlook:
            files.notes.append("OMNI_SENDER non renseigné : recherche Outlook désactivée")
        for note in files.notes:
            ctx.log.warning(note)
        for kind, target in (("net", t.net), ("gross", t.gross)):
            source = getattr(files, kind)
            if source is None:
                ctx.log.warning("Performance %s introuvable (déposez-la dans %s ou attendez l'e-mail).", kind.upper(), inbox)
                continue
            ctx.log.info("Performance %s : %s", kind.upper(), files.origin.get(kind, ""))
            try:
                safe_place(source, target, ecraser)
                ctx.log.success("Rangée : %s", target)
            except FileExistsError as error:
                ctx.log.warning(str(error))
        report["performances"] = {"origine": files.origin, "complet": files.complete}

    with ctx.step("Contrôles et rangement"):
        if files.net is not None and valid_xlsx(files.net):
            check = PF.check_net(ctx.data, files.net, p)
            report["controle_net"] = {k: v for k, v in check.items() if k != "gaps"}
            ctx.log.info("Performance NET vs VL JUMP : %s", check.get("status"))
            if check.get("gaps"):
                ctx.show_table(pd.DataFrame(check["gaps"]), "Écarts de performance NET")
        statut = "OK" if files.complete and (holdings == "skip" or "holdings" in report) else "PARTIEL"
        report["statut"] = statut
        checks = pd.DataFrame(report.get("holdings", {}).get("controles", []))
        if len(checks):
            ctx.show_table(checks, "Contrôles des Holdings")
        ctx.save_excel({"Synthèse": pd.DataFrame([{"Clé": k, "Valeur": json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v}
                                                    for k, v in report.items()]),
                        "Contrôles Holdings": checks if len(checks) else pd.DataFrame({"contrôle": []})},
                       f"Controle_OMNI_{p.yyyymmdd}", label="Rapport de contrôle")
        (root / "_controles").mkdir(parents=True, exist_ok=True)
        (root / "_controles" / f"Controle_OMNI_{p.yyyymmdd}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                                                             encoding="utf-8")
        missing = [k.upper() for k in ("net", "gross") if getattr(files, k) is None]
        ctx.set_summary(f"OMNI {p.label} : {statut}" + (f" — performances manquantes : {', '.join(missing)} (relancer avec « Ne pas refaire les Holdings »)"
                                                         if missing else ""), statut=statut, periode=p.label, dossier=str(t.quarter_dir))
