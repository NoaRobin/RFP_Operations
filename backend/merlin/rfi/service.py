"""Service « Remplir un RFI » : dépôt, repérage du fonds, propositions de réponses, génération de la copie remplie."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..data.access import DataAccess, DataError
from .detect import Detection, all_text, detect
from .facts import PRODUCT, SHARE, FactValues, format_value, load_facts, norm
from .match import match_question
from .writer import write

ALLOWED = {".xlsx", ".xlsm", ".docx"}
ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
MIN_CONFIDENCE = 0.45


class RfiStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def folder(self, doc_id: str) -> Path:
        if not re.fullmatch(r"rfi_[a-f0-9]{12}", doc_id):
            raise FileNotFoundError(doc_id)
        path = self.root / doc_id
        if not path.exists():
            raise FileNotFoundError(doc_id)
        return path

    def save(self, filename: str, content: bytes, user: str) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED:
            raise ValueError(suffix)
        doc_id = f"rfi_{uuid.uuid4().hex[:12]}"
        folder = self.root / doc_id
        (folder / "versions").mkdir(parents=True)
        original = folder / f"original{suffix}"
        original.write_bytes(content)
        original.chmod(0o444)
        meta = {"id": doc_id, "filename": Path(filename).name, "suffix": suffix, "size": len(content), "user": user,
                "sha256": hashlib.sha256(content).hexdigest(), "uploaded_at": datetime.now().isoformat(timespec="seconds")}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def meta(self, doc_id: str) -> dict[str, Any]:
        folder = self.folder(doc_id)
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        meta["versions"] = sorted((p.name for p in (folder / "versions").glob("*.*") if p.suffix != ".json"), reverse=True)
        return meta

    def original(self, doc_id: str) -> Path:
        return next(self.folder(doc_id).glob("original.*"))

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        items = []
        for folder in self.root.glob("rfi_*"):
            meta_file = folder / "meta.json"
            if meta_file.exists():
                items.append(json.loads(meta_file.read_text(encoding="utf-8")))
        return sorted(items, key=lambda m: m["uploaded_at"], reverse=True)[:limit]


# --------------------------------------------------------------------------- référentiel des fonds
_funds_cache: dict[str, Any] = {"at": 0.0, "mode": None, "items": []}


def fund_directory(data: DataAccess) -> list[dict[str, Any]]:
    """Fonds Product Info et leurs parts (cache 10 minutes)."""
    if time.time() - _funds_cache["at"] < 600 and _funds_cache["mode"] == data.mode:
        return _funds_cache["items"]
    products = data.query(f"SELECT p.pi_productid, p.Product_Name FROM dbo.{PRODUCT} p WHERE p.Product_Name IS NOT NULL")
    shares = data.query(f"SELECT s.ProductID, s.ISIN_Code, s.Share_Name FROM dbo.{SHARE} s WHERE s.ISIN_Code IS NOT NULL")
    by_product: dict[str, list[dict[str, str]]] = {}
    for row in shares.itertuples(index=False):
        by_product.setdefault(str(row.ProductID), []).append({"isin": str(row.ISIN_Code), "name": str(row.Share_Name or row.ISIN_Code)})
    items = [{"pid": str(r.pi_productid), "name": str(r.Product_Name), "shares": sorted(by_product.get(str(r.pi_productid), []), key=lambda s: s["name"])}
             for r in products.itertuples(index=False)]
    items.sort(key=lambda i: norm(i["name"]))
    _funds_cache.update({"at": time.time(), "mode": data.mode, "items": items})
    return items


def search_funds(data: DataAccess, q: str, limit: int = 20) -> list[dict[str, Any]]:
    items = fund_directory(data)
    qn = norm(q)
    if not qn:
        return items[:limit]
    tokens = qn.split()
    out = []
    for item in items:
        hay = norm(item["name"] + " " + " ".join(s["isin"] + " " + s["name"] for s in item["shares"]))
        if all(t in hay for t in tokens):
            out.append(item)
    return out[:limit]


def suggest_funds(data: DataAccess, text: str) -> list[dict[str, Any]]:
    """Fonds probables : ISIN présents dans le document, puis noms de fonds cités."""
    items = fund_directory(data)
    by_isin = {s["isin"]: (item, s) for item in items for s in item["shares"]}
    suggestions: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for isin in dict.fromkeys(ISIN.findall(text or "")):
        if isin in by_isin:
            item, share = by_isin[isin]
            key = (item["pid"], share["isin"])
            if key not in seen:
                seen.add(key)
                suggestions.append({"pid": item["pid"], "name": item["name"], "isin": share["isin"], "share_name": share["name"],
                                    "reason": f"ISIN {isin} trouvé dans le document"})
    text_n = f" {norm(text)} "
    named = sorted((i for i in items if len(norm(i["name"])) > 6 and f" {norm(i['name'])} " in text_n), key=lambda i: -len(i["name"]))
    for item in named[:3]:
        if all(s["pid"] != item["pid"] for s in suggestions):
            share = item["shares"][0] if item["shares"] else {"isin": None, "name": None}
            suggestions.append({"pid": item["pid"], "name": item["name"], "isin": share["isin"], "share_name": share["name"],
                                "reason": "Nom du fonds cité dans le document"})
    return suggestions[:5]


# --------------------------------------------------------------------------- analyse & génération
def analyze(data: DataAccess, path: Path, detection: Detection, pid: str | None, isin: str | None,
            as_of: str | None, lang: str | None = None, overrides: dict[str, str | None] | None = None) -> dict[str, Any]:
    facts = load_facts(data.catalog)
    fact_list = list(facts.values())
    lang = lang or detection.language
    as_of = as_of or date.today().isoformat()
    values = FactValues(data, pid, isin, as_of)
    values.preload(fact_list)
    overrides = overrides or {}
    rows, stats = [], {"fill": 0, "existing": 0, "no_value": 0, "unmatched": 0, "skipped": 0}
    for q in detection.questions:
        matches = match_question(q.text, fact_list)
        chosen = None
        if q.id in overrides:
            chosen_id = overrides[q.id]
            chosen = facts.get(chosen_id) if chosen_id else None
            confidence = 1.0 if chosen else 0.0
        elif matches and matches[0].confidence >= MIN_CONFIDENCE:
            chosen, confidence = matches[0].fact, matches[0].confidence
        else:
            confidence = matches[0].confidence if matches else 0.0
        display, value = (None, None)
        if chosen is not None:
            display, value = format_value(chosen, values.raw(chosen), lang, norm(q.text))
        if q.id in overrides and overrides[q.id] is None:
            status = "skipped"
        elif chosen is None:
            status = "unmatched"
        elif q.existing:
            status = "existing"
        elif display is None:
            status = "no_value"
        else:
            status = "fill"
        stats[status] += 1
        rows.append({
            **q.to_dict(), "fact": chosen.id if chosen else None, "fact_label": chosen.label if chosen else None,
            "confidence": round(confidence, 2), "answer": display, "value": value if isinstance(value, (int, float, str)) or value is None else display,
            "status": status, "alternatives": [{"fact": m.fact.id, "label": m.fact.label, "confidence": m.confidence} for m in matches],
        })
    return {"questions": rows, "stats": stats, "language": lang, "as_of": as_of, "errors": values.errors}


def generate(data: DataAccess, store: RfiStore, doc_id: str, pid: str | None, isin: str | None, as_of: str | None,
             lang: str | None, overrides: dict[str, str | None], overwrite: bool, user: str) -> dict[str, Any]:
    path = store.original(doc_id)
    detection = detect(path)
    result = analyze(data, path, detection, pid, isin, as_of, lang, overrides)
    targets = {q.id: q.target for q in detection.questions}
    answers = []
    for row in result["questions"]:
        if row["answer"] is None or row["status"] in {"skipped", "unmatched", "no_value"}:
            continue
        if row["status"] == "existing" and not overwrite:
            continue
        answers.append((targets[row["id"]], row["value"] if row["value"] is not None else row["answer"]))
    meta = store.meta(doc_id)
    folder = store.folder(doc_id)
    number = len(meta["versions"]) + 1
    stem = re.sub(r"[^\w\-]+", "_", Path(meta["filename"]).stem).strip("_") or "rfi"
    target = folder / "versions" / f"{stem}_rempli_v{number}{meta['suffix']}"
    written = write(path, target, answers)
    info = {"version": number, "written": written, "pid": pid, "isin": isin, "as_of": result["as_of"], "by": user,
            "created_at": datetime.now().isoformat(timespec="seconds"), "stats": result["stats"]}
    target.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**info, "file": target.name, "questions": result["questions"]}


def load_detection(store: RfiStore, doc_id: str) -> tuple[Path, Detection]:
    path = store.original(doc_id)
    return path, detect(path)


def document_text(path: Path) -> str:
    try:
        return all_text(path)
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["RfiStore", "analyze", "generate", "search_funds", "suggest_funds", "fund_directory", "DataError"]
