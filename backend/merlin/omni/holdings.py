"""Holdings du mois depuis Fabric, au format du fichier du mois précédent, et contrôles par rapport à lui."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from ..data.access import DataAccess
from ..rfi.ontology import norm

TABLE = "JUMP_portfolio_holdings"
# Libellés courants d'un export JUMP → colonne Fabric (complétés par l'égalité des noms normalisés)
SYNONYMS = {
    "isin": "CODE_ISIN_INSTRUMENT", "code isin": "CODE_ISIN_INSTRUMENT", "isin instrument": "CODE_ISIN_INSTRUMENT",
    "fonds": "NOM_FONDS", "nom fonds": "NOM_FONDS", "portefeuille": "NOM_FONDS", "fund": "NOM_FONDS",
    "instrument": "NOM_INSTRUMENT", "libelle": "NOM_INSTRUMENT", "libelle instrument": "NOM_INSTRUMENT", "security": "NOM_INSTRUMENT",
    "date": "DATE_INVENTAIRE", "date inventaire": "DATE_INVENTAIRE", "date de l'inventaire": "DATE_INVENTAIRE",
    "devise": "DEVISE_INSTRUMENT", "devise instrument": "DEVISE_INSTRUMENT", "devise fonds": "DEVISE_FONDS",
    "quantite": "QUANTITE", "poids": "POIDS_LIGNE_EXPO", "poids expo": "POIDS_LIGNE_EXPO", "poids taux": "POIDS_LIGNE_TAUX",
    "cours": "COURS_UNITAIRE", "classe d'actif": "CLASSE_ACTIF", "classe actif": "CLASSE_ACTIF", "type": "TYPE_HOLDING",
    "ticker": "CODE_BLOOMBERG", "bloomberg": "CODE_BLOOMBERG", "code bloomberg": "CODE_BLOOMBERG",
    "montant": "MONTANT_DEVISE_FONDS", "valorisation": "MONTANT_DEVISE_FONDS", "exposition": "EXPOSITION_DEVISE_FONDS",
}


@dataclass
class HoldingsResult:
    frame: pd.DataFrame
    layout: str  # « gabarit du mois précédent » | « colonnes Fabric »
    unmapped: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)


def _columns(data: DataAccess) -> list[str]:
    table = data.catalog.table(TABLE)
    return [c.name for c in table.columns] if table else []


def template_headers(path: Path) -> tuple[list[str], int]:
    """En-têtes du fichier du mois précédent (première ligne d'au moins 3 cellules texte) et nombre de lignes de données."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    headers: list[str] = []
    rows = 0
    for row in ws.iter_rows(values_only=True):
        values = [v for v in row if v not in (None, "")]
        if not headers:
            if sum(isinstance(v, str) for v in values) >= 3:
                headers = [str(v).strip() if v is not None else "" for v in row]
                while headers and not headers[-1]:
                    headers.pop()
            continue
        if values:
            rows += 1
    wb.close()
    return headers, rows


def map_headers(headers: list[str], columns: list[str]) -> tuple[dict[str, str], list[str]]:
    by_norm = {norm(c.replace("_", " ")): c for c in columns}
    mapping, unmapped = {}, []
    for h in headers:
        if not h:
            continue
        n = norm(h.replace("_", " "))
        col = by_norm.get(n) or SYNONYMS.get(n)
        if col and col in columns:
            mapping[h] = col
        else:
            unmapped.append(h)
    return mapping, unmapped


def build(data: DataAccess, closing: str, template: Path | None) -> HoldingsResult:
    columns = _columns(data)
    frame = data.query(f"SELECT {', '.join('h.' + c for c in columns)} FROM dbo.{TABLE} h WHERE h.DATE_INVENTAIRE = :d "
                       "ORDER BY h.NOM_FONDS, h.POIDS_LIGNE_EXPO DESC", {"d": closing})
    result = HoldingsResult(frame, "colonnes Fabric")
    previous_rows = None
    if template is not None:
        headers, previous_rows = template_headers(template)
        mapping, unmapped = map_headers(headers, columns)
        if headers and not unmapped:
            result.frame = pd.DataFrame({h: frame[mapping[h]] for h in headers if h})
            result.layout = "gabarit du mois précédent"
        elif headers:
            result.unmapped = unmapped
            result.alerts.append(f"{len(unmapped)} colonne(s) du mois précédent sans équivalent Fabric ({', '.join(unmapped[:6])}) : "
                                 "fichier produit avec les colonnes Fabric — utilisez le mode « JUMP Excel » si le gabarit doit être identique.")
    result.checks = controls(frame, previous_rows, template)
    result.alerts += [c["message"] for c in result.checks if c["level"] == "alerte"]
    return result


def controls(frame: pd.DataFrame, previous_rows: int | None, template: Path | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str, level: str = "alerte") -> None:
        out.append({"contrôle": name, "level": "ok" if ok else level, "message": message})

    n = len(frame)
    add("Inventaire non vide", n > 0, f"{n} ligne(s) dans JUMP à la date d'arrêté")
    funds = frame["NOM_FONDS"].nunique() if n else 0
    add("Fonds présents", funds > 0, f"{funds} fonds")
    if previous_rows:
        change = (n - previous_rows) / previous_rows
        add("Volume vs mois précédent", abs(change) <= 0.25, f"{n} lignes contre {previous_rows} le mois précédent ({change:+.0%})")
    if template is not None and n:
        try:
            prev = pd.read_excel(template, sheet_name=0)
            fund_col = next((c for c in prev.columns if norm(str(c)) in {"nom fonds", "fonds", "nom_fonds", "portefeuille", "fund"}), None)
            if fund_col is not None:
                missing = sorted(set(prev[fund_col].dropna().astype(str)) - set(frame["NOM_FONDS"].dropna().astype(str)))
                add("Fonds disparus", not missing, f"{len(missing)} fonds du mois précédent absents : {', '.join(missing[:8])}" if missing
                    else "tous les fonds du mois précédent sont présents")
        except Exception:  # noqa: BLE001
            pass
    if n and "POIDS_LIGNE_EXPO" in frame:
        weights = pd.to_numeric(frame["POIDS_LIGNE_EXPO"], errors="coerce").groupby(frame["NOM_FONDS"]).sum()
        scale = 1.0 if weights.median() <= 1.5 else 100.0  # fraction ou points (unité À CONFIRMER)
        off = weights[(weights / scale - 1).abs() > 0.05]
        add("Somme des poids par fonds ≈ 100 %", off.empty, f"{len(off)} fonds hors 95–105 % : {', '.join(map(str, off.index[:6]))}"
            if len(off) else "tous les fonds entre 95 et 105 %", "attention")
    return out


def write(frame: pd.DataFrame, path: Path, sheet: str = "Holdings") -> Path:
    from ..atelier.writer import write_frames_to_excel

    path.parent.mkdir(parents=True, exist_ok=True)
    write_frames_to_excel({sheet: frame}, path, {})
    return path
