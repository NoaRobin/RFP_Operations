"""API « OMNI » : configuration (dossiers) et derniers rapports de contrôle."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ..omni.period import build
from ..state import AppState
from .deps import state

router = APIRouter(prefix="/api/omni")


@router.get("")
def overview(s: AppState = Depends(state)) -> dict[str, Any]:
    o = s.settings.omni
    root = Path(o.root) if o.root else s.settings.data_dir / "omni"
    inbox = Path(o.inbox) if o.inbox else s.settings.data_dir / "omni" / "depot"
    p = build(s.data, None, None)
    reports = []
    folder = root / "_controles"
    if folder.exists():
        for f in sorted(folder.glob("Controle_OMNI_*.json"), reverse=True)[:12]:
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
                reports.append({"file": f.name, "periode": r.get("periode"), "statut": r.get("statut"), "date_arrete": r.get("date_arrete"),
                                "alertes": r.get("alertes", [])[:5], "holdings": (r.get("holdings") or {}).get("lignes"),
                                "controle_net": (r.get("controle_net") or {}).get("status")})
            except ValueError:
                continue
    return {"root": str(root), "inbox": str(inbox), "outlook": bool(o.sender), "sender": o.sender, "jump_excel": bool(o.jump_script),
            "next": {"periode": p.label, "mois": p.month, "annee": p.year, "date_arrete": p.closing.isoformat(), "source": p.closing_source},
            "reports": reports}
