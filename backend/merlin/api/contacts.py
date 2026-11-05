"""Qui contacter : inventaire des questions posées aux autres équipes (mails avec l'équipe RFP en copie)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..contacts.service import get_service
from ..state import AppState
from .deps import bad_request, state

router = APIRouter(prefix="/api/contacts")


def service(s: AppState):
    return get_service(s.settings.data_dir)


@router.get("")
def status(s: AppState = Depends(state)) -> dict[str, Any]:
    return service(s).status()


class ScanRequest(BaseModel):
    months: int = Field(36, ge=1, le=120)


@router.post("/scan")
def scan(body: ScanRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Lecture d'Outlook en arrière-plan (suivre avec GET /api/contacts)."""
    return service(s).scan(body.months)


@router.post("/stop")
def stop(s: AppState = Depends(state)) -> dict[str, Any]:
    service(s).stop()
    return service(s).status()


@router.get("/questions")
def questions(q: str = "", team: str = "", dd: str = "", s: AppState = Depends(state)) -> list[dict[str, Any]]:
    from ..search.text import fold

    out = []
    for g in service(s).inventory.data.get("groups", []):
        if q and fold(q) not in fold(g["question"] + " " + " ".join(g["variants"])):
            continue
        if team and g["team"] != team:
            continue
        if dd and dd not in g["dd_types"]:
            continue
        out.append(g)
    return out[:500]


@router.get("/export.xlsx")
def export(s: AppState = Depends(state)) -> Response:
    return Response(service(s).inventory.to_excel(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Qui_contacter_RFI.xlsx"'})


@router.post("/import")
async def import_corrections(file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    content = await file.read()
    try:
        n = service(s).inventory.import_corrections(content)
    except (KeyError, ValueError) as error:
        raise bad_request("Fichier non reconnu : reprenez le fichier exporté (feuille « Questions »).", str(error)) from error
    return {"corrections": n, **service(s).status()}


class AskRequest(BaseModel):
    questions: list[str] = Field(default_factory=list, max_length=500)
    client: str = ""
    fund: str = ""
    deadline: str = ""


@router.post("/ask")
def ask(body: AskRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Questions sans réponse du compléteur → une demande par équipe, mail type prêt à copier."""
    return service(s).inventory.ask_plan(body.questions, body.client, body.fund, body.deadline)
