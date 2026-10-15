"""Performances NET et GROSS du mois : dossier de dépôt, puis Outlook. Contrôle de la NET contre les VL JUMP."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..rfi import perf as P
from ..rfi.ontology import norm
from ..rfi.understand import Period as UPeriod
from .period import MONTHS_FR, OmniPeriod
from .tree import valid_xlsx

GROSS = ("gross", "brut", "brute", "before fees", "avant frais")
NET = (" net ", "net of fees", "nette", "after fees", "apres frais")
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def kind_of(name: str) -> str | None:
    n = norm(name)
    if not n.endswith(".xlsx"):
        return None
    if any(m in n for m in GROSS):
        return "gross"
    if any(m in f" {n.replace('_', ' ')} " for m in NET):
        return "net"
    return None


def mentions_period(text: str, p: OmniPeriod) -> bool:
    t = norm(text)
    markers = {p.yyyymmdd, p.closing.strftime("%d/%m/%Y"), p.closing.strftime("%d-%m-%Y"), f"{norm(MONTHS_FR[p.month - 1])} {p.year}",
               f"{p.year}{p.month:02d}", f"{p.month:02d}_{p.year}", f"{p.month:02d}-{p.year}"}
    return any(m in t for m in markers)


@dataclass
class PerfFiles:
    net: Path | None = None
    gross: Path | None = None
    origin: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.net is not None and self.gross is not None


def from_folder(folder: Path, p: OmniPeriod, work: Path) -> PerfFiles:
    out = PerfFiles()
    if not folder.exists():
        return out
    for f in sorted(folder.glob("*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True):
        kind = kind_of(f.name)
        if kind and getattr(out, kind) is None and mentions_period(f.name, p) and valid_xlsx(f):
            target = work / f"performance_{kind}.xlsx"
            shutil.copy2(f, target)
            setattr(out, kind, target)
            out.origin[kind] = f"dossier de dépôt : {f.name}"
    return out


def from_outlook(p: OmniPeriod, work: Path, sender: str, subject_words: tuple[str, ...], end_day: int = 20) -> PerfFiles:
    """Outlook du poste (Windows). Filtre côté serveur (Restrict) sur la fenêtre de réception, puis expéditeur et objet."""
    out = PerfFiles()
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        out.notes.append("Outlook indisponible sur ce poste (pywin32 absent)")
        return out
    pythoncom.CoInitialize()
    try:
        ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        nm, ny = (1, p.year + 1) if p.month == 12 else (p.month + 1, p.year)
        start, end = datetime(ny, nm, 1), datetime(ny, nm, end_day, 23, 59)
        restriction = f"[ReceivedTime] >= '{start:%d/%m/%Y %H:%M}' AND [ReceivedTime] <= '{end:%d/%m/%Y %H:%M}'"
        found: dict[str, tuple[datetime, Any]] = {}

        def folders(root):
            yield root
            try:
                for child in root.Folders:
                    yield from folders(child)
            except Exception:  # noqa: BLE001
                return

        for folder in folders(ns.GetDefaultFolder(6).Parent):
            try:
                items = folder.Items.Restrict(restriction)
            except Exception:  # noqa: BLE001
                continue
            for msg in items:
                try:
                    address = str(msg.SenderEmailAddress or "").lower()
                    if address.startswith("/o=") and msg.Sender and msg.Sender.GetExchangeUser():
                        address = str(msg.Sender.GetExchangeUser().PrimarySmtpAddress or "").lower()
                    if address != sender.lower() or not all(w in norm(msg.Subject) for w in subject_words):
                        continue
                    received = datetime(msg.ReceivedTime.year, msg.ReceivedTime.month, msg.ReceivedTime.day, msg.ReceivedTime.hour,
                                        msg.ReceivedTime.minute)
                    for i in range(1, msg.Attachments.Count + 1):
                        att = msg.Attachments.Item(i)
                        kind = kind_of(str(att.FileName))
                        if kind and (kind not in found or received > found[kind][0]):
                            found[kind] = (received, att)
                except Exception:  # noqa: BLE001
                    continue
        for kind, (received, att) in found.items():
            target = work / f"performance_{kind}.xlsx"
            att.SaveAsFile(str(target))
            if valid_xlsx(target):
                setattr(out, kind, target)
                out.origin[kind] = f"Outlook : {att.FileName} reçu le {received:%d/%m/%Y %H:%M}"
    finally:
        pythoncom.CoUninitialize()
    return out


def check_net(data, net: Path, p: OmniPeriod, tolerance_bp: float = 1.0, limit: int = 400) -> dict[str, Any]:
    """Compare les performances NET du fichier aux performances recalculées depuis les VL JUMP (même ISIN, même mois)."""
    try:
        sheet = pd.read_excel(net, sheet_name=0, header=None)
    except Exception as error:  # noqa: BLE001
        return {"status": "illisible", "detail": str(error)}
    rows = []
    for _, row in sheet.iterrows():
        values = list(row.values)
        isin = next((str(v).strip() for v in values if isinstance(v, str) and ISIN.match(str(v).strip())), None)
        if isin:
            rows.append((isin, [float(v) for v in values if isinstance(v, (int, float)) and not pd.isna(v)]))
    if not rows:
        return {"status": "non comparable", "detail": "aucun ISIN repéré dans le fichier NET"}
    ok = ko = unknown = 0
    gaps = []
    for isin, numbers in rows[:limit]:
        try:
            nav = P.nav_frame(data.query("SELECT a.DATE_VL, a.VL_UNITAIRE, a.DIVIDEND_AMOUNT, a.COEFFICIENT_OST, a.VL_BENCH, a.NOM_BENCH "
                                         "FROM dbo.JUMP_portfolio_aum a WHERE a.CODE_ISIN_PART = :isin AND a.DATE_VL <= :d ORDER BY a.DATE_VL",
                                         {"isin": isin, "d": p.closing.isoformat()}))
            res = P.period_return(P.adjusted_index(nav), UPeriod("months", 1), p.closing, annualize=False)
            fabric = res.value
        except Exception:  # noqa: BLE001
            fabric = None
        if fabric is None or not numbers:
            unknown += 1
            continue
        best = min(numbers, key=lambda v: min(abs(v * 100 - fabric), abs(v - fabric)))
        gap = min(abs(best * 100 - fabric), abs(best - fabric))
        if gap * 100 <= tolerance_bp:
            ok += 1
        else:
            ko += 1
            gaps.append({"ISIN": isin, "Fabric (%)": round(fabric, 4), "Fichier (le plus proche)": best, "Écart (pb)": round(gap * 100, 1)})
    status = "concorde" if ko == 0 and ok else ("écarts" if ko else "non comparable")
    return {"status": status, "ok": ok, "ecarts": ko, "non_comparables": unknown, "gaps": gaps[:50]}
