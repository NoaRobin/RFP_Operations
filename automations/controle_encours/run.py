"""Exemple d'automatisation Python : contrôle des encours avant envoi.

Contrat : exposer `run(ctx, **params)`. Tout passe par `ctx` :
- ctx.data.query(sql, params)  → accès Fabric (jamais de connexion directe)
- ctx.step("…")                → étapes affichées dans la timeline
- ctx.log.info / warning / …   → journal en temps réel
- ctx.show_table / save_excel  → résultats
"""
from __future__ import annotations

import pandas as pd

QUERY = """
WITH ranked AS (
    SELECT
        a.CODE_ISIN_PART, a.NOM_PART, a.DATE_VL, a.VL_UNITAIRE, a.ACTIF_NET_PART_EURO,
        ROW_NUMBER() OVER (PARTITION BY a.CODE_ISIN_PART ORDER BY a.DATE_VL DESC) AS rang
    FROM dbo.JUMP_portfolio_aum a
    WHERE a.DATE_VL <= :as_of
)
SELECT CODE_ISIN_PART, NOM_PART, DATE_VL, VL_UNITAIRE, ACTIF_NET_PART_EURO, rang
FROM ranked
WHERE rang <= 2
"""


def run(ctx, as_of: str, seuil: float = 10.0) -> None:
    with ctx.step("Chargement des VL"):
        frame = ctx.data.query(QUERY, {"as_of": as_of})
        ctx.log.info("%d lignes chargées pour %d parts", len(frame), frame["CODE_ISIN_PART"].nunique())

    with ctx.step("Analyse des variations"):
        last = frame[frame["rang"] == 1].set_index("CODE_ISIN_PART")
        prev = frame[frame["rang"] == 2].set_index("CODE_ISIN_PART")
        latest_date = last["DATE_VL"].max()
        anomalies = []
        for isin, row in last.iterrows():
            if row["VL_UNITAIRE"] is None or pd.isna(row["VL_UNITAIRE"]):
                anomalies.append({"ISIN": isin, "Part": row["NOM_PART"], "Type": "VL manquante", "Détail": str(row["DATE_VL"])})
            if str(row["DATE_VL"]) < str(latest_date):
                anomalies.append({"ISIN": isin, "Part": row["NOM_PART"], "Type": "VL en retard",
                                  "Détail": f"Dernière VL au {row['DATE_VL']} (référence : {latest_date})"})
            if isin in prev.index:
                before, after = prev.at[isin, "ACTIF_NET_PART_EURO"], row["ACTIF_NET_PART_EURO"]
                if before and after and not pd.isna(before) and not pd.isna(after):
                    variation = (after - before) / before * 100
                    if abs(variation) >= seuil:
                        anomalies.append({"ISIN": isin, "Part": row["NOM_PART"], "Type": "Variation d'encours",
                                          "Détail": f"{variation:+.1f} % entre {prev.at[isin, 'DATE_VL']} et {row['DATE_VL']}"})
        report = pd.DataFrame(anomalies, columns=["ISIN", "Part", "Type", "Détail"])
        if report.empty:
            ctx.log.success("Aucune anomalie au-dessus de %.1f %% : les chiffres sont présentables.", seuil)
        else:
            ctx.log.warning("%d anomalie(s) détectée(s)", len(report))

    with ctx.step("Rédaction du rapport"):
        summary = pd.DataFrame([
            {"Indicateur": "Parts contrôlées", "Valeur": len(last)},
            {"Indicateur": "Date de référence", "Valeur": str(latest_date)},
            {"Indicateur": "Seuil (%)", "Valeur": seuil},
            {"Indicateur": "Anomalies", "Valeur": len(report)},
        ])
        ctx.show_table(report if not report.empty else summary, "Anomalies" if not report.empty else "Synthèse")
        ctx.save_excel({"Synthèse": summary, "Anomalies": report}, f"Controle_encours_{as_of}.xlsx")
    ctx.set_summary(f"{len(report)} anomalie(s) sur {len(last)} part(s).", anomalies=len(report), parts=len(last))
