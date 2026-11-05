"""API « Qvidian » : connexion, synchronisation, carte des erreurs, analyse IA (Copilot), suggestions agrégées,
modifications en masse protégées par mot de passe, import des projets comme anciens RFI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import File, UploadFile, APIRouter, Depends, Request
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
    remember: bool = True
    auth_url: str = Field(default="", max_length=300)


@router.post("/connect")
def connect(body: ConnectRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Identifiant + clé d'API (ou mot de passe). remember : mémorisés sur ce poste, chiffrés par Windows (DPAPI),
    reconnexion automatique ensuite — plus besoin du .env. La clé n'est jamais renvoyée au navigateur."""
    if not body.password.strip() and not body.api_key.strip():
        raise bad_request("Mot de passe ou clé d'API manquant.")
    if body.auth_url and not body.auth_url.startswith("https://"):
        raise bad_request("L'adresse du service Qvidian doit commencer par https://")
    _guard(service(s).connect, body.user, body.password, body.api_key, body.remember, body.auth_url)
    return service(s).status()


@router.post("/credentials/forget")
def forget_credentials(s: AppState = Depends(state)) -> dict[str, Any]:
    service(s).forget()
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
def sso_callback(request: Request, s: AppState = Depends(state)):
    """Retour du portail QPA après l'authentification SSO (SSOToken, SSOLogin, SSOUserID en Base64 — guide
    « SSO For Web Service Applications »). Noms de paramètres lus sans tenir compte des majuscules."""
    from urllib.parse import quote

    q = {k.lower(): v for k, v in request.query_params.items()}
    token, login = q.get("ssotoken", ""), q.get("ssologin", "")
    if not token or not login:
        names = ", ".join(sorted(request.query_params.keys())) or "aucun"
        message = f"Qvidian n'a pas renvoyé SSOToken / SSOLogin (paramètres reçus : {names})"
        service(s).last_sso_error = message
        service(s)._log_sso(message)
        return RedirectResponse(f"/qvidian?sso=absent&raison={quote(message)}")
    try:
        service(s).sso_callback(token, login)
    except QvidianError as error:
        return RedirectResponse(f"/qvidian?sso=refuse&raison={quote(error.message)}")
    return RedirectResponse("/qvidian?sso=ok")


@router.post("/sync")
def start_sync(kind: str = "auto", s: AppState = Depends(state)) -> dict[str, Any]:
    """kind : auto (incrémentale dès qu'une synchronisation complète existe) | full | delta."""
    return _guard(service(s).start_sync, kind if kind in {"auto", "full", "delta"} else "auto")


def _funds(s: AppState) -> None:
    """Noms de fonds Product Info (répertoire Fabric) : aident à reconnaître un texte propre à un fonds. Jamais bloquant."""
    svc = service(s)
    if svc.search.extra_funds:
        return
    try:
        from ..rfi.service import fund_directory

        svc.search.extra_funds = [f["name"] for f in fund_directory(s.data)][:2000]
    except Exception:  # noqa: BLE001 - Fabric indisponible : les dossiers de fonds Qvidian suffisent
        svc.search.extra_funds = []


class SearchRequest(BaseModel):
    q: str = Field("", max_length=2000)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: str = "pertinence"
    k: int = Field(20, ge=1, le=100)
    rerank: bool = True


@router.post("/search")
def search(body: SearchRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Recherche sémantique hybride dans l'instantané (portée, fonds, utilisations, versions regroupées, explications)."""
    _funds(s)
    return _guard(service(s).library_search, body.q, body.filters, body.sort, body.k, body.rerank)


@router.get("/overview")
def overview(s: AppState = Depends(state)) -> dict[str, Any]:
    return _guard(service(s).overview)


@router.get("/engine")
def engine(s: AppState = Depends(state)) -> dict[str, Any]:
    return service(s).engine_status()


@router.post("/engine/models/{model_id}")
def download_model(model_id: str, s: AppState = Depends(state)) -> dict[str, Any]:
    """Téléchargement explicite d'un modèle ONNX (data/models/) ; l'index sémantique se construit ensuite en arrière-plan."""
    return _guard(service(s).download_model, model_id)


class MatchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=4000)
    k: int = 8


@router.post("/match")
def match(body: MatchRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    """Questions déjà tombées identiques à celle-ci (probabilité calibrée) et textes Qvidian choisis pour elles."""
    return service(s).match(body.q, body.k)


@router.get("/memory")
def memory(s: AppState = Depends(state)) -> dict[str, Any]:
    """Mémoire des réponses : couverture, réutilisation, textes piliers, à créer, à rafraîchir, jamais utilisés."""
    return service(s).memory()


@router.get("/freshness")
def freshness(s: AppState = Depends(state)) -> dict[str, Any]:
    """Échéances : expirations Qvidian et dates de révision proposées d'après le contenu du texte."""
    return service(s).freshness()


@router.get("/families")
def families(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    """Doublons et versions d'un même texte, avec le texte à garder proposé."""
    return service(s).families()


@router.get("/questions")
def question_bank(q: str = "", only: str = "", s: AppState = Depends(state)) -> dict[str, Any]:
    """Questions des anciens RFI, les plus posées d'abord ; only = covered | orphan."""
    return service(s).question_bank(q, only)


class ExportRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)


@router.post("/export.xlsx")
def export(body: ExportRequest, s: AppState = Depends(state)):
    from fastapi.responses import Response

    return Response(service(s).export(body.ids), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Selection_Qvidian.xlsx"'})


@router.get("/match/status")
def match_status(s: AppState = Depends(state)) -> dict[str, Any]:
    return service(s).match_status()


@router.post("/match/rebuild")
def match_rebuild(s: AppState = Depends(state)) -> dict[str, Any]:
    svc = service(s)
    snap = svc.snapshot()
    model = snap.path.with_name(f"{snap.path.stem}.matcher.json")
    model.unlink(missing_ok=True)  # réapprentissage complet
    svc.build_matcher(snap)
    return svc.match_status()


@router.post("/engine/packs/{pack}")
def download_pack(pack: str, s: AppState = Depends(state)) -> dict[str, Any]:
    """Pack « rapide » ou « precis » : ses modèles l'un après l'autre (clic explicite)."""
    from ..search.neural import PACKS

    if pack not in PACKS:
        raise bad_request(f"Pack inconnu : {pack}")
    svc = service(s)
    svc.search.downloads.start_many(PACKS[pack]["models"])
    return svc.engine_status()


@router.get("/engine/it-request")
def it_request_text(pack: str = "rapide") -> dict[str, Any]:
    """Demande toute prête pour l'IT (domaines à ouvrir, URL, tailles, SHA-256, licences)."""
    from ..search.install import it_request
    from ..search.neural import MODELS, PACKS

    ids = PACKS[pack]["models"] if pack in PACKS else PACKS["rapide"]["models"]
    return {"text": it_request(MODELS, ids)}


@router.post("/engine/downloads/stop")
def stop_downloads(s: AppState = Depends(state)) -> dict[str, Any]:
    service(s).search.downloads.stop()
    return service(s).engine_status()


@router.post("/engine/models/upload")
async def upload_models(files: list[UploadFile] = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    """Fichiers téléchargés dans le navigateur : reconnus par taille + SHA-256 (le nom ne compte pas), puis installés."""
    import shutil
    import tempfile

    svc = service(s)
    folder = Path(tempfile.mkdtemp(prefix="merlin-models-", dir=svc.search.models_root.parent if svc.search.models_root.parent.exists() else None))
    try:
        paths = []
        for k, f in enumerate(files):
            target = folder / f"{k}.bin"
            with target.open("wb") as out:
                shutil.copyfileobj(f.file, out, 1 << 20)
            paths.append(target)
        result = svc.search.downloads.install_files(paths)
        result["ignored"] = [files[int(Path(n).stem)].filename for n in result["ignored"] if Path(n).stem.isdigit()]
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if result["ready"]:
        svc.rebuild_index()
        svc.build_matcher()
    return {**result, "engine": svc.engine_status()}


class ScanRequest(BaseModel):
    folder: str = ""  # vide : dossier Téléchargements de la session Windows


@router.post("/engine/models/scan")
def scan_models(body: ScanRequest, s: AppState = Depends(state)) -> dict[str, Any]:
    from ..search.install import DownloadError

    svc = service(s)
    try:
        result = svc.search.downloads.scan(Path(body.folder) if body.folder.strip() else None)
    except DownloadError as error:
        raise bad_request(str(error), error.hint) from error
    if result["ready"]:
        svc.rebuild_index()
        svc.build_matcher()
    return {**result, "engine": svc.engine_status()}


@router.post("/engine/rebuild")
def rebuild(s: AppState = Depends(state)) -> dict[str, Any]:
    return service(s).rebuild_index()


@router.get("/api-stats")
def api_stats(s: AppState = Depends(state)) -> dict[str, Any]:
    """Appels Qvidian mesurés : latence p50 / p95, erreurs, cache, relances, débit, dernière synchronisation."""
    return service(s).api_stats()


@router.post("/api-stats/reset")
def api_stats_reset(s: AppState = Depends(state)) -> dict[str, Any]:
    service(s).reset_stats()
    return service(s).api_stats()


@router.get("/history")
def history(s: AppState = Depends(state)) -> dict[str, Any]:
    """Questions des anciens RFI rapprochées des textes Qvidian choisis (résumé + contenus les plus choisis)."""
    return _guard(service(s).history_summary)


@router.post("/history/rebuild")
def history_rebuild(s: AppState = Depends(state)) -> dict[str, Any]:
    return _guard(service(s).rebuild_history)


@router.get("/folders")
def folders(s: AppState = Depends(state)) -> list[dict[str, Any]]:
    return service(s).snapshot().folders()


@router.get("/audit")
def audit(depth: int = 2, s: AppState = Depends(state)) -> dict[str, Any]:
    return _guard(service(s).audit, None, max(1, min(depth, 4)))


@router.get("/contents/{content_id}")
def content(content_id: int, s: AppState = Depends(state)) -> dict[str, Any]:
    snap = service(s).snapshot()
    c = snap.get(content_id)
    if c is None:
        raise not_found("Contenu absent de l'instantané : relancez la synchronisation.")
    try:
        insight = service(s).insight(content_id)
    except Exception:  # noqa: BLE001 - le détail reste lisible même si le moteur ne l'est pas
        insight = None
    return {**c, "versions": snap.versions(content_id), "insight": insight}


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
