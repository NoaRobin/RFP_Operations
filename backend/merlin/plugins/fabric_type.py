"""Exécuteur des automatisations déclaratives `type: fabric` (requête + sortie, sans Python)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .context import RunContext
from .manifest import Manifest

DEFAULT_STEPS = ["Préparation", "Interrogation du Lakehouse", "Mise en forme", "Écriture du résultat"]


class EmptyResult(RuntimeError):
    pass


def render_filename(template: str, manifest: Manifest, params: dict[str, Any]) -> str:
    values = {"id": manifest.id, "date": date.today().isoformat(), **{k: v for k, v in params.items() if v is not None}}
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return f"{manifest.id}_{values['date']}.xlsx"


def run_fabric(ctx: RunContext, manifest: Manifest, query: str, params: dict[str, Any]) -> None:
    spec = manifest.fabric
    assert spec is not None
    with ctx.step("Préparation"):
        shown = {k: v for k, v in params.items() if v is not None}
        ctx.log.info("Paramètres : %s", ", ".join(f"{k}={v}" for k, v in shown.items()) or "aucun")
        ctx.log.info("Source de données : %s", "Lakehouse Fabric" if ctx.data_mode == "fabric" else "Lakehouse de démonstration")

    with ctx.step("Interrogation du Lakehouse"):
        frame = ctx.data.query(query, params)
        stats = ctx.data.last_stats
        ctx.log.info("%d ligne(s) reçue(s) en %.2f s", len(frame), stats.seconds if stats else 0)

    if frame.empty and spec.empty_is_error:
        raise EmptyResult("La requête n'a renvoyé aucune ligne.")

    with ctx.step("Mise en forme"):
        if spec.column_labels:
            frame = frame.rename(columns=spec.column_labels)
        ctx.show_table(frame, manifest.name)

    with ctx.step("Écriture du résultat"):
        if spec.output in {"excel", "both"}:
            path = ctx.save_excel(
                {spec.sheet_name: frame},
                render_filename(spec.filename, manifest, params),
                number_formats=spec.number_formats,
            )
            ctx.log.success("Fichier prêt : %s", path.name)
        if frame.empty:
            ctx.log.warning("Aucune ligne : vérifiez les filtres (date, fonds…).")
    ctx.set_summary(f"{len(frame)} ligne(s) extraite(s).", rows=len(frame))
