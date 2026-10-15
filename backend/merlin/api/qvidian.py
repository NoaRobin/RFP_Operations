"""API « Qvidian » : connexion, synchronisation, carte des erreurs, analyse IA (Copilot), suggestions agrégées,
modifications en masse protégées par mot de passe, import des projets comme anciens RFI."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..qvidian.ai import build_prompts, parse_reply
from ..qvidian.client import QvidianError
from ..qvidian.service import QvidianService, get_service
from ..qvidian.suggest import explain, suggest
from ..state import AppState
from .deps import bad_request, current_user, not_found, state

router = APIRouter(prefix="/api/qvidian")


def service(s: AppState) -> QvidianService:
    return get_service(s.settings.qvidian, s.settings.data_dir)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except QvidianError as error:
        raise bad_request(error.message, error.hint) from error


@router.get("/status")
def status(s: AppState = Depends(state)) -> dict[str, Any]:
    return service(s).status()


class ConnectRequest(BaseModel):
    user: str = Field(min_length=1, max_length=200)
    password: str = ""
    api_key: str = ""


@router.post("/connect")
def connect(body: ConnectRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Identifiant + mot de passe (ou clé d'API) : gardés en mémoire le temps de la session, jamais écrits sur disque."""
    if not body.password and not body.api_key:
        raise bad_request("Mot de passe ou clé d'API manquant.")
    _guard(service(s).connect, body.user, body.password, body.api_key)
    return service(s).status()


@router.post("/disconnect")
def disconnect(s: AppState = Depends(state)) -> dict[str, Any]:
    service(s).disconnect()
    return service(s).status()


@router.get("/sso/start")
def sso_start(request: Request, s: AppState = Depends(state)) -> dict[str, str]:
    callback = str(request.url_for("qvidian_sso_callback"))
    return {"url": _guard(service(s).sso_url, callback)}


@router.get("/sso/callback", name="qvidian_sso_callback")
def sso_callback(SSOToken: str = "", SSOLogin: str = "", s: AppState = Depends(state)):  # noqa: N803 - noms imposés par QPA
    """Retour du portail QPA après l'authentification SSO (paramètres en Base64, voir « SSO For Web Service Applications »)."""
    if not SSOToken or not SSOLogin:
        return RedirectResponse("/qvidian?sso=absent")
    try:
        service(s).sso_callback(SSOToken, SSOLogin)
    except (QvidianError, ValueError):
        return RedirectResponse("/qvidian?sso=refuse")
    return RedirectResponse("/qvidian?sso=ok")


@router.post("/sync")
def start_sync(s: AppState = Depends(state)) -> dict[str, Any]:
    return _guard(service(s).start_sync)


@router.get("/audit")
def audit(depth: int = 2, s: AppState = Depends(state)) -> dict[str, Any]:
    return _guard(service(s).audit, None, max(1, min(depth, 4)))


@router.get("/contents/{content_id}")
def content(content_id: int, s: AppState = Depends(state)) -> dict[str, Any]:
    snap = service(s).snapshot()
    c = snap.get(content_id)
    if c is None:
        raise not_found("Contenu absent de l'instantané : relancez la synchronisation.")
    return {**c, "versions": snap.versions(content_id)}


@router.get("/suggest")
def suggest_answer(q: str, s: AppState = Depends(state)) -> dict[str, Any]:
    """Réponses de la bibliothèque pour une question, agrégées (utilisations × récence, versions regroupées)."""
    svc = service(s)
    choices = suggest(svc.snapshot(), q, half_life=svc.settings.half_life_days)
    return {"question": q, "half_life_days": svc.settings.half_life_days, "choices": [explain(c) for c in choices]}


class IdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=2000)


@router.post("/ai/prompt")
def ai_prompt(body: IdsRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    contents = service(s).snapshot().many(body.ids)
    if not contents:
        raise bad_request("Aucun contenu sélectionné.", "Cochez des contenus dans la carte ou la liste.")
    return build_prompts(contents)


class AiReplyRequest(BaseModel):
    text: str = Field(max_length=500_000)
    ids: list[int]


@router.post("/ai/reply")
def ai_reply(body: AiReplyRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    svc = service(s)
    out = parse_reply(body.text, body.ids)
    if out["read"] == 0 and "| C" not in body.text and "|C" not in body.text:
        raise bad_request("Aucune ligne « | C123 | catégorie | gravité | problème | correction | » trouvée.",
                          "Collez toute la réponse de Copilot. Si Copilot n'a rien trouvé, il n'y a pas de tableau : c'est normal.")
    revisions = {c["id"]: c["revision"] for c in svc.snapshot().many(body.ids)}
    out["saved"] = svc.ai.save(out["findings"], revisions)
    out["findings"] = {str(k): v for k, v in out["findings"].items()}
    return out


class PlanRequest(BaseModel):
    ids: list[int] = Field(max_length=500)
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/bulk/plan")
def bulk_plan(body: PlanRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Prévisualisation (aucune écriture, pas de mot de passe)."""
    try:
        return service(s).plan(body.ids, body.action, body.params).public()
    except ValueError as error:
        raise bad_request("Valeur invalide.", str(error)) from error
    except QvidianError as error:
        raise bad_request(error.message, error.hint) from error


class ApplyRequest(BaseModel):
    plan_id: str
    password: str = Field(max_length=200)
    force: bool = False


@router.post("/bulk/apply")
def bulk_apply(body: ApplyRequest, s: AppState = Depends(state), user: str = Depends(current_user)) -> dict[str, Any]:
    return _guard(service(s).apply, body.plan_id, body.password, body.force, user)


@router.get("/journal")
def journal(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return list(reversed(service(s).journal.all()))[:50]


class UndoRequest(BaseModel):
    password: str = Field(max_length=200)


@router.post("/journal/{batch}/undo")
def undo(batch: str, body: UndoRequest, s: AppState = Depends(state), user: str = Depends(current_user)) -> dict[str, Any]:
    return _guard(service(s).undo, batch, body.password, user)


class ImportRequest(BaseModel):
    limit: int = Field(20, ge=1, le=200)


@router.post("/projects/import")
def import_projects(body: ImportRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Documents des projets Qvidian (questionnaires déjà répondus) → anciens RFI du compléteur."""
    from ..rfi.precedents import get_index

    svc = service(s)
    if svc.mode == "demo" and s.data.mode != "mock":
        raise bad_request("Projets de démonstration : jamais mélangés aux vrais anciens RFI.",
                          "Connectez-vous à Qvidian pour importer les vrais projets.")
    return _guard(svc.import_projects, get_index(s.settings.data_dir / "rfi").store, body.limit)


__all__ = ["router", "service"]
