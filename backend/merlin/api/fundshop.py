"""API « Documents des fonds » : la liste, l'Excel vierge (et l'export), l'import, le lien collé, le test de connexion."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ..data.access import DataError
from ..fundshop.catalog import DOC_TYPES, doc_type
from ..fundshop.problems import DocumentProblem, problem
from ..fundshop.runner import load_last_run
from ..fundshop.service import destination, memory, resolver, root, shopping_list
from ..fundshop.shopping import DEFAULT_NAME, Item, from_excel
from ..fundshop.template import build as build_template
from ..rfi.service import fund_directory
from ..state import AppState
from .deps import bad_request, not_found, state

router = APIRouter(prefix="/api/fundshop")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ItemIn(BaseModel):
    isin: str
    kind: str
    fund: str = ""
    part: str = ""
    month: str = ""
    filename: str = ""
    active: bool = True
    overwrite: bool = False
    id: str | None = None


def _item(body: ItemIn) -> Item:
    try:
        doc = doc_type(body.kind)
    except ValueError as error:
        raise bad_request(str(error)) from error
    data = body.model_dump(exclude_none=True)
    data["kind"], data["isin"] = doc.key, body.isin.strip().upper()
    if not doc.needs_month:
        data["month"] = ""
    item = Item(**data)
    try:
        item.target_name()
    except ValueError as error:
        raise bad_request(str(error), "Mois : « Mois précédent » ou un mois précis (2026-07).") from error
    return item


def _directory(s: AppState) -> list[dict[str, Any]]:
    try:
        return fund_directory(s.data)
    except DataError:
        return []


@router.get("")
def overview(s: AppState = Depends(state)) -> dict[str, Any]:
    dest = destination(s.settings)
    items = shopping_list(s.settings).load()
    last = load_last_run(root(s.settings))
    by_id = {r["id"]: r for r in (last or {}).get("results", [])}
    rows = []
    for i in items:
        d = i.to_dict()
        d["present"] = bool(d.get("target")) and (dest / d["target"]).exists()
        d["result"] = by_id.get(i.id)
        rows.append(d)
    return {"items": rows, "destination": str(dest), "default_name": DEFAULT_NAME, "memory": memory(s.settings).stats(),
            "types": [{"key": d.key, "label": d.label, "needs_month": d.needs_month} for d in DOC_TYPES.values()],
            "last_run": {k: v for k, v in last.items() if k != "results"} if last else None}


@router.put("")
def replace(items: list[ItemIn], s: AppState = Depends(state)) -> dict[str, Any]:
    shopping_list(s.settings).save([_item(i) for i in items])
    return overview(s)


@router.get("/template.xlsx")
def template(with_list: bool = False, s: AppState = Depends(state)) -> Response:
    """Liste vierge (référentiel des parts en liste déroulante) ; with_list=true : pré-remplie avec la liste actuelle."""
    items = shopping_list(s.settings).load() if with_list else None
    name = "Ma liste de documents.xlsx" if with_list else "Liste de courses vierge.xlsx"
    return Response(build_template(_directory(s), items), media_type=XLSX,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name.replace(' ', '%20')}"})


@router.post("/import")
async def import_excel(file: UploadFile = File(...), replace_all: bool = False, s: AppState = Depends(state)) -> dict[str, Any]:
    raw = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "liste.xlsx"
        path.write_bytes(raw)
        try:
            items, errors = from_excel(path)
        except Exception as error:  # noqa: BLE001
            raise bad_request("Ce fichier Excel n'a pas pu être lu.", "Enregistrez-le en .xlsx dans Excel puis réessayez.") from error
    store = shopping_list(s.settings)
    current = [] if replace_all else store.load()
    keys = {(i.isin, i.kind, i.month) for i in current}
    added = [i for i in items if (i.isin, i.kind, i.month) not in keys]
    store.save(current + added)
    return {**overview(s), "imported": len(added), "duplicates": len(items) - len(added), "errors": errors}


@router.post("/learn-csv")
async def learn_csv(file: UploadFile = File(...), s: AppState = Depends(state)) -> dict[str, Any]:
    """Amorce la mémoire des adresses avec resultats_telechargement.csv de l'ancien script."""
    raw = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "resultats.csv"
        path.write_bytes(raw)
        mem = memory(s.settings)
        try:
            count = mem.seed_from_csv(path)
        except (UnicodeDecodeError, KeyError) as error:
            raise bad_request("Ce CSV n'est pas celui de l'ancien script (colonnes isin, statut, url_source).") from error
    return {"learned": count, "memory": mem.stats()}


class LinkIn(BaseModel):
    isin: str
    url: str
    kind: str | None = None


@router.post("/link")
def learn_link(body: LinkIn, s: AppState = Depends(state)) -> dict[str, Any]:
    """« J'ai le lien » : un PDF du site (ou la page du fonds) suffit pour retrouver ensuite tous les documents de la part."""
    try:
        message = resolver(s.settings, s.data).learn_link(body.isin, body.url, body.kind)
    except ValueError as error:
        raise bad_request(str(error), "Sur le site, clic droit sur le lien du PDF → « Copier le lien ».") from error
    return {"message": message, "memory": memory(s.settings).stats()}


class TryIn(BaseModel):
    isin: str
    kind: str
    month: str = ""
    fund: str = ""


@router.post("/try")
def try_one(body: TryIn, s: AppState = Depends(state)) -> dict[str, Any]:
    """Cherche un document sans l'enregistrer : dit tout de suite si ça marchera, et sinon pourquoi."""
    item = _item(ItemIn(isin=body.isin, kind=body.kind, month=body.month, fund=body.fund))
    res = resolver(s.settings, s.data)
    try:
        found = res.find(res.identity(item.isin, item.fund), doc_type(item.kind), item.period())
    except DocumentProblem as error:
        res.memory.save()
        return {"found": False, "problem": error.problem.to_dict()}
    res.memory.save()
    return {"found": True, "url": found.url, "size": len(found.content), "note": found.note}


@router.get("/available/{isin}")
def available_documents(isin: str, fund: str = "", part: str = "", s: AppState = Depends(state)) -> dict[str, Any]:
    """Ce que le site propose vraiment pour cette part (comme la rubrique « Téléchargements »), mois disponibles compris."""
    from ..fundshop.resolver import available

    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin.strip().upper()):
        raise bad_request("ISIN invalide.")
    return available(resolver(s.settings, s.data), isin, fund, part)


class CheckIn(BaseModel):
    lines: list[str]


@router.post("/check")
def check(body: CheckIn, s: AppState = Depends(state)) -> dict[str, Any]:
    """« Tester sur le site » : pour chaque fonds / part, le parcours de la page « Nos fonds » étape par étape (sans téléchargement)."""
    from ..fundshop.resolver import check_line

    res = resolver(s.settings, s.data)
    lines = [x for x in (l.strip() for l in body.lines) if x][:40]
    results = [check_line(res, line) for line in lines]
    return {"results": results, "ok": sum(r["ok"] for r in results), "total": len(results)}


@router.get("/diagnostic")
def diagnostic(s: AppState = Depends(state)) -> dict[str, Any]:
    """Test de connexion en clair : dossier, site des documents, site des fonds, Product Info."""
    res = resolver(s.settings, s.data)
    dest = destination(s.settings)
    checks = []
    try:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".rfp-test").write_bytes(b"ok")
        (dest / ".rfp-test").unlink()
        checks.append({"label": "Dossier de destination", "ok": True, "message": str(dest)})
    except OSError as error:
        p = problem("dossier", path=str(dest), detail=str(error))
        checks.append({"label": "Dossier de destination", "ok": False, "message": p.why, "fix": p.fix})
    for label, url in (("Site des documents (PDF)", res.docs_base + "/"), ("Site des fonds", res.site_base)):
        ok, error, status = res.net.check(url)
        if ok:
            checks.append({"label": label, "ok": True, "message": f"joignable ({res.net.active})"})
        else:
            p = problem(error.code, host=error.host or urlparse(url).netloc, detail=error.detail)
            checks.append({"label": label, "ok": False, "message": f"{p.title} : {p.why}", "fix": p.fix})
    # Écran d'accueil (profil investisseur) : sans lui, le site ne montre ni les fonds ni les téléchargements
    try:
        opened = res.open_session()
        page = res.fetch(res.site_base)
        ok = opened and page.status == 200 and not res.gated(page)
        checks.append({"label": "Écran d'accueil du site (profil)", "ok": ok,
                       "message": f"profil « {res.profile} » accepté" if ok else "le site affiche toujours son écran « Particuliers / Professionnels »",
                       **({} if ok else {"fix": "Ouvrez le site dans Edge et choisissez le profil ; si ça persiste, essayez FUNDSHOP_PROFILE=individual dans .env."})})
    except Exception as error:  # noqa: BLE001
        checks.append({"label": "Écran d'accueil du site (profil)", "ok": False, "message": str(error)[:160]})
    stats = res.memory.stats()
    checks.append({"label": "Adresses connues", "ok": True,
                   "message": f"{stats['shares']} part(s) et {stats['funds']} fonds mémorisés"
                              + (f" · Product Info vérifié ({', '.join(stats['id_column'].values())})" if stats["id_column"] else "")})
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "network": res.net.active}


@router.get("/bundle.zip")
def bundle(s: AppState = Depends(state)) -> Response:
    """Les documents du dernier lancement, en un zip, téléchargé par le navigateur (dossier Téléchargements du poste)."""
    import io
    import zipfile
    from datetime import date

    last = load_last_run(root(s.settings)) or {}
    dest = destination(s.settings)
    files = [dest / Path(r["file"]).name for r in last.get("results", []) if r.get("status") in ("OK", "DÉJÀ PRÉSENT") and r.get("file")]
    files = [f for f in dict.fromkeys(files) if f.exists()]
    if not files:
        raise not_found("Aucun document prêt : lancez d'abord « Télécharger ».")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    name = f"Documents des fonds {date.today().isoformat()}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name.replace(' ', '%20')}"})


@router.get("/file/{name}")
def download(name: str, s: AppState = Depends(state)):
    path = destination(s.settings) / Path(name).name
    if not path.exists():
        raise not_found("Fichier introuvable dans le dossier.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
