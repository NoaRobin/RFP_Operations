"""Arborescence trimestrielle « <année>/Q<n> <année>/{Holdings, Performances, AUM, Characteristics} » et copies sûres."""
from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .period import OmniPeriod

DEFAULT_FOLDERS = ("AUM", "Characteristics", "Holdings", "Performances")


@dataclass(frozen=True)
class Targets:
    quarter_dir: Path
    holdings: Path
    net: Path
    gross: Path

    def to_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}


def quarter_dir(root: Path, year: int, quarter: int) -> Path:
    return root / str(year) / f"Q{quarter} {year}"


def targets(root: Path, p: OmniPeriod) -> Targets:
    q = quarter_dir(root, p.year, p.quarter)
    return Targets(q, q / "Holdings" / f"Holdings {p.month}_{p.year}.xlsx",
                   q / "Performances" / f"Monthly perf NET of fees_{p.yyyymmdd}.xlsx",
                   q / "Performances" / f"Monthly perf GROSS of fees_{p.yyyymmdd}.xlsx")


def previous_holdings(root: Path, p: OmniPeriod) -> Path | None:
    """Holdings du mois précédent (gabarit de colonnes et point de comparaison)."""
    month, year = p.previous()
    q = (month - 1) // 3 + 1
    candidate = quarter_dir(root, year, q) / "Holdings" / f"Holdings {month}_{year}.xlsx"
    if candidate.exists():
        return candidate
    folder = quarter_dir(root, year, q) / "Holdings"
    files = sorted(folder.glob("Holdings*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True) if folder.exists() else []
    return files[0] if files else None


def ensure_tree(root: Path, p: OmniPeriod) -> list[str]:
    """Crée le trimestre en reproduisant les dossiers (jamais les fichiers) du trimestre précédent."""
    notes = []
    dest = quarter_dir(root, p.year, p.quarter)
    if not dest.exists():
        py, pq = (p.year - 1, 4) if p.quarter == 1 else (p.year, p.quarter - 1)
        prev = quarter_dir(root, py, pq)
        dest.mkdir(parents=True)
        if prev.exists():
            n = 0
            for d in prev.rglob("*"):
                if d.is_dir():
                    (dest / d.relative_to(prev)).mkdir(parents=True, exist_ok=True)
                    n += 1
            notes.append(f"trimestre créé : {n} dossier(s) reproduit(s) depuis {prev.name}")
        else:
            notes.append("trimestre créé (dossiers par défaut)")
    for name in DEFAULT_FOLDERS:
        (dest / name).mkdir(parents=True, exist_ok=True)
    return notes


def valid_xlsx(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0 and zipfile.is_zipfile(path)


def safe_place(source: Path, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"déjà présent (non écrasé) : {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, tmp)
    if not valid_xlsx(tmp):
        tmp.unlink(missing_ok=True)
        raise ValueError(f"copie invalide : {destination.name}")
    os.replace(tmp, destination)
