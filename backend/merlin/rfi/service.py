"""Service « Remplir un RFI » : dépôt, repérage du fonds, propositions de réponses, génération de la copie remplie."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..data.access import DataAccess, DataError
from .layout import Layout, Slot, all_text, detect
from .library import Library
from .match import Candidate, match
from .ontology import Concept, load_ontology, norm
from .precedents import PrecedentIndex
from .precedents.advisor import Decision, Entity, FundResolver, PrecedentAdvisor
from .render import Rendered, render
from .understand import Understanding, understand
from .documents.service import DocumentService
from .precedents.compare import same
from .precedents.bindings import BindingIndex, pseudo_concept
from .values import EXTRA_COLUMNS, PRODUCT, SHARE, Raw, Values, to_date
from .writer import write
from .aggregate import HALF_LIFE_DAYS, Vote, aggregate, to_date as vote_date

ALLOWED = {".xlsx", ".xlsm", ".docx"}
ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
AUTO = 0.70  # au-dessus (et sans aucun drapeau) : écrit sans intervention
MIN_SCORE = 0.45  # en dessous : pas de proposition (la meilleure piste reste visible)
MARGIN = 0.08  # deux lectures plus proches que cela et de valeurs différentes : ambiguïté


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
def _library(store: RfiStore) -> Library:
    return Library(store.root / "library.json")


def _share_fund(data: DataAccess, isin: str) -> str | None:
    for item in fund_directory(data):
        if any(s["isin"] == isin for s in item["shares"]):
            return item["pid"]
    return None


def analyze(data: DataAccess, store: RfiStore, path: Path, layout: Layout, pid: str | None, isin: str | None,
            as_of: str | None, lang: str | None = None, overrides: dict[str, Any] | None = None,
            precedents: PrecedentIndex | None = None, precedent_isin: str | None = None,
            documents: "DocumentService | None" = None, bindings: "BindingIndex | None" = None,
            qvidian=None, cache: dict[str, dict[str, Any]] | None = None, half_life: int = HALF_LIFE_DAYS) -> dict[str, Any]:
    """Propose une réponse par case. overrides[id] = id de concept | None (ne pas remplir) | {"text": …}.

    Avec des précédents, chaque case reçoit aussi une décision justifiée (repris de l'ancien, modèle d'ontologie,
    incohérence…), après contrôle des réponses historiques dans Fabric. Avec Qvidian (instantané local), les réponses
    types déjà choisies par l'équipe sont proposées pour les questions qualitatives.
    Chaque case reçoit `choices` : toutes les réponses possibles, toutes sources confondues, classées par
    `merlin.rfi.aggregate` (fréquence × récence × fiabilité de la source).
    `cache` (facultatif) garde le calcul de chaque case : quand on choisit une réponse, seule cette case est recalculée."""
    ontology = load_ontology(data.catalog)
    lang = lang or layout.language
    as_of_d = date.fromisoformat(as_of) if as_of else date.today()
    overrides = overrides or {}
    library = _library(store)
    values_by_entity: dict[tuple[str | None, str | None], Values] = {}
    errors: list[str] = []

    def values_for(slot: Slot) -> Values:
        e_isin = slot.entity.get("isin") or isin
        e_pid = pid if (not slot.entity.get("isin") or slot.entity.get("isin") == isin) else (_share_fund(data, e_isin) or pid)
        key = (e_pid, e_isin)
        if key not in values_by_entity:
            vals = Values(data, ontology, e_pid, e_isin, as_of_d)
            vals.doc_facts = _document_facts(data, documents, vals, e_pid, e_isin, errors)  # type: ignore[attr-defined]
            values_by_entity[key] = vals
        return values_by_entity[key]

    lazy: dict[str, Any] = {}

    def advisor() -> PrecedentAdvisor | None:  # créé à la première case qui en a besoin (rien à créer si tout vient du cache)
        if "advisor" not in lazy:
            lazy["advisor"] = _advisor(data, ontology, precedents, pid, precedent_isin or isin, as_of_d, lang)
        return lazy["advisor"]
    if bindings is not None:
        for table, columns in bindings.columns().items():  # colonnes apprises : lues avec le reste de la fiche
            EXTRA_COLUMNS.setdefault(table, set()).update(c for c in columns if (t := data.catalog.table(table)) and t.column(c))
    similar = (lambda q: [h.precedent.question for h in precedents.search(q, k=5, min_similarity=0.9)]) if precedents else None
    decisions: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    stats = {"auto": 0, "review": 0, "no_value": 0, "unmatched": 0, "skipped": 0, "existing": 0}
    def compute(slot: Slot, override: Any) -> dict[str, Any]:
        u = understand(ontology, slot.question, hint=slot.hint, context=slot.context, options=slot.options,
                       number_format=slot.number_format, as_of=as_of_d, entity_scope="share" if slot.entity.get("isin") else None,
                       parent=slot.parent)
        typed = override is None or (isinstance(override, dict) and override.get("text") is not None)
        vals = None if typed else values_for(slot)  # réponse saisie ou choisie : ni Fabric ni documents à relire
        binding = None
        if bindings and not typed:
            binding = bindings.lookup(f"{slot.parent} {slot.question}" if slot.parent else slot.question, similar)
        row = _analyze_slot(ontology, library, slot, u, vals, lang, as_of_d, override, binding)
        if row["status"] not in {"skipped", "existing"} and row["source"] in {"ontologie", "bibliothèque"} and advisor() is not None:
            row = _apply_decision(row, advisor().advise(slot, u, row))
        if qvidian is not None and override == "__none__":
            row = _apply_qvidian(row, slot, qvidian, as_of_d, half_life)
        return row

    for slot in layout.slots:
        override = overrides.get(slot.id, "__none__")
        key = json.dumps(override, sort_keys=True, ensure_ascii=False, default=str)
        slot_cache = cache.setdefault(slot.id, {}) if cache is not None else {}
        if key in slot_cache:
            row = copy.deepcopy(slot_cache[key])
        else:
            row = compute(slot, override)
            if isinstance(override, dict) and override.get("text") is not None:
                # Réponse choisie ou saisie : on garde sous les yeux toutes les autres sources de la case (carrousel)
                none_key = json.dumps("__none__")
                if none_key not in slot_cache:
                    slot_cache[none_key] = _with_choices(compute(slot, "__none__"), as_of_d, half_life)
                row = _merge_sources(row, slot_cache[none_key])
            row = _with_choices(row, as_of_d, half_life)
            slot_cache[key] = copy.deepcopy(row)
        if row.get("precedent") and row["source"] not in {"réponse saisie", "Copilot"} and row.get("status") not in {"skipped", "existing"}:
            decisions[row["precedent"]["kind"]] = decisions.get(row["precedent"]["kind"], 0) + 1
        stats[row["status"]] += 1
        rows.append(row)
    for v in values_by_entity.values():
        errors.extend(e for e in v.errors if e not in errors)
    if cache is not None:  # les cases reprises du cache ne relisent pas Fabric : on garde les alertes du premier calcul
        kept = cache.setdefault("__errors__", {"list": []})["list"]
        kept.extend(e for e in errors if e not in kept)
        errors = list(kept)
    total = len(rows)
    answerable = sum(1 for r in rows if r["status"] in {"auto", "review"})
    return {"questions": rows, "stats": stats, "language": lang, "as_of": as_of_d.isoformat(), "errors": errors,
            "coverage": {"total": total, "auto": stats["auto"], "review": stats["review"],
                         "rate": round(answerable / total, 3) if total else 0.0},
            "notes": layout.notes, "library": library.stats(), "decisions": decisions,
            "precedents": precedents.store.count() if precedents is not None else 0}


QVIDIAN_SOURCES = 6  # contenus Qvidian montrés comme sources d'une case (les plus pertinents)


def _apply_qvidian(row: dict[str, Any], slot: Slot, snapshot, as_of: date, half_life: int) -> dict[str, Any]:
    """Réponses types Qvidian déjà choisies pour cette question : sources de la case, et proposition « à vérifier »
    quand rien d'autre ne répond (question qualitative). Jamais automatique."""
    from ..qvidian.suggest import votes as qvidian_votes

    if row["status"] in {"skipped", "existing"} or slot.target.get("unresolved_list"):
        return row
    try:
        found = qvidian_votes(snapshot, f"{slot.parent} {slot.question}" if slot.parent else slot.question)
    except Exception:  # noqa: BLE001 - un instantané illisible n'arrête jamais l'analyse
        return row
    if not found:
        return row
    from .aggregate import vote_score

    found.sort(key=lambda v: -vote_score(v, as_of, half_life))
    row = {**row, "sources": list(row.get("sources") or []) + [
        {"kind": "qvidian", "label": v.label, "value": v.text, "date": v.when.isoformat() if v.when else None, "uses": v.uses,
         "weight": round(v.weight, 3), "check": v.check, "ref": v.ref} for v in found[:QVIDIAN_SOURCES]]}
    if row.get("answer") is None and row["status"] in {"unmatched", "no_value"}:
        best = aggregate(found, today=as_of, half_life=half_life)[0]
        value = best.value
        if slot.options:
            value = next((o for o in slot.options if norm(o) == norm(best.value)), None)
            if value is None:
                return row  # liste déroulante du client : un texte libre Qvidian n'y entre pas
        row.update({"answer": value, "value": value, "_value": value, "status": "review", "source": "Qvidian",
                    "confidence": round(min(0.6, 0.3 + 0.3 * best.share), 2), "evidence": f"Qvidian · {best.why()}",
                    "reasons": [f"réponse type Qvidian la plus choisie récemment ({best.why()})"],
                    "issues": [i for i in row["issues"] if i != "question qualitative"] + ["réponse type Qvidian : à relire et adapter au fonds"]})
        row.pop("suggestion", None)
    return row


def _merge_sources(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    seen = {(x.get("kind"), x.get("label"), x.get("value")) for x in row.get("sources") or []}
    extra = [x for x in base.get("sources") or [] if (x.get("kind"), x.get("label"), x.get("value")) not in seen]
    row = {**row, "sources": list(row.get("sources") or []) + extra}
    for k in ("precedent", "alternatives"):
        if base.get(k) and not row.get(k):
            row[k] = base[k]
    if base.get("answer") and norm(base["answer"]) != norm(row.get("answer") or ""):
        row["sources"].append({"kind": "app", "label": f"proposition de l'app ({base.get('source')})", "value": base["answer"]})
    return row


KIND_OF_SOURCE = {"bibliothèque": "library", "réponse saisie": "mine", "Copilot": "copilot", "Qvidian": "qvidian", "document": "document",
                  "précédent": "precedent", "utilisateur": "app", "ontologie": "app", "liaison apprise": "app"}


def _with_choices(row: dict[str, Any], as_of: date, half_life: int) -> dict[str, Any]:
    """Toutes les réponses possibles de la case, regroupées par texte et classées (voir merlin.rfi.aggregate)."""
    votes: list[Vote] = []
    for x in row.get("sources") or []:
        if x.get("kind") == "precedent" or not x.get("value"):
            continue
        votes.append(Vote(str(x["value"]), x.get("kind") or "document", x.get("label") or "", weight=float(x.get("weight") or 1.0),
                          when=vote_date(x.get("date")), uses=int(x.get("uses") or 1), url=x.get("url") or "",
                          check=x.get("check") if x.get("check") in {"match", "mismatch"} else None, ref=str(x.get("ref") or "")))
    for p in (row.get("precedent") or {}).get("precedents") or []:
        if p.get("answer"):
            votes.append(Vote(str(p["answer"]), "precedent", p.get("provenance") or "", weight=float(p.get("similarity") or 1.0),
                              when=vote_date(p.get("date")), url=p.get("url") or "", check=p.get("check"), blocked=bool(p.get("blocked"))))
    for a in row.get("alternatives") or []:
        if a.get("answer"):
            votes.append(Vote(str(a["answer"]), "alternative", a.get("label") or ""))
    answer = row.get("answer")
    if answer and not any(norm(v.text) == norm(str(answer)) for v in votes):
        votes.append(Vote(str(answer), KIND_OF_SOURCE.get(row.get("source") or "", "app"), row.get("evidence") or row.get("source") or ""))
    elif answer and row.get("source") in {"réponse saisie", "Copilot"}:
        kind = KIND_OF_SOURCE[row["source"]]
        if not any(v.kind == kind and norm(v.text) == norm(str(answer)) for v in votes):
            votes.append(Vote(str(answer), kind, row.get("evidence") or row["source"]))
    row["choices"] = [c.public() for c in aggregate(votes, today=as_of, half_life=half_life)[:8]]
    return row


def _document_facts(data: DataAccess, documents, vals: Values, pid: str | None, isin: str | None, errors: list[str]) -> dict:
    """Faits du DIC / prospectus de la part (cache local, puis recherche) ; une panne de document n'arrête jamais l'analyse."""
    if documents is None or not isin:
        return {}
    try:
        directory = fund_directory(data)
    except DataError:
        directory = []
    fund = next((i for i in directory if i["pid"] == pid), None)
    share = next((s for i in directory for s in i["shares"] if s["isin"] == isin), None)
    vals.load()
    last_kid = to_date((vals._share or {}).get("Last_DIC_Modification_Date"))
    try:
        facts, problems, _ = documents.facts(isin, fund["name"] if fund else "", share["name"] if share else "", last_kid)
    except Exception as error:  # noqa: BLE001
        errors.append(f"Documents officiels : {type(error).__name__}")
        return {}
    for p in [x for x in problems if "aucun DIC ni prospectus" not in x][:3]:  # l'absence est visible dans le panneau Documents
        message = f"Documents officiels ({isin}) : {p}"
        if message not in errors:
            errors.append(message)
    return facts


def _advisor(data: DataAccess, ontology, precedents: PrecedentIndex | None, pid: str | None, isin: str | None, as_of: date,
             lang: str) -> PrecedentAdvisor | None:
    if precedents is None or precedents.store.count() == 0:
        return None
    try:
        directory = fund_directory(data)
    except DataError:
        directory = []
    name = next((i["name"] for i in directory if i["pid"] == pid), pid or "")
    current = Entity(pid, isin, name) if (pid or isin) else None
    return PrecedentAdvisor(ontology, precedents, FundResolver(directory), lambda p, i, d: Values(data, ontology, p, i, d),
                            as_of, lang, current)


def _apply_decision(row: dict[str, Any], decision: Decision) -> dict[str, Any]:
    """Fusion : la décision complète la case (justification) et peut en changer le statut, jamais en silence."""
    row = {**row, "precedent": decision.to_public()}
    row["sources"] = list(row.get("sources") or []) + [
        {"kind": "precedent", "label": p.get("provenance", ""), "value": p.get("answer", ""), "check": p.get("check"),
         "url": p.get("url", ""), "blocked": p.get("blocked", False), "detail": p.get("fabric")}
        for p in decision.precedents[:4]]
    if decision.kind == "incoherence":
        row["issues"] = row["issues"] + ["incohérence avec un ancien RFI (voir la justification)"]
        if row["status"] == "auto":
            row["status"] = "review"
    elif decision.status == "auto" and row["status"] == "review":
        row["reasons"] = row["reasons"] + [f"réserves levées par les précédents vérifiés : {'; '.join(row['issues'])}"]
        row["issues"], row["status"] = [], "auto"
    elif decision.answer is not None and row.get("answer") is None:
        row.update({"answer": decision.answer, "value": _jsonable(decision.value), "_value": decision.value, "option": decision.option,
                    "status": "review", "source": "précédent", "concept": decision.concept or row.get("concept"),
                    "reasons": [decision.justification], "confidence": max(row.get("confidence") or 0.0, 0.6)})
        row.pop("suggestion", None)
    return row


def _candidate_answer(ontology, cand: Candidate, u: Understanding, vals: Values, lang: str, slot: Slot, as_of: date) -> tuple[Rendered, Any]:
    raw = vals.get(cand.concept, u, lang)
    rendered = render(ontology, cand.concept, raw, u, lang, number_format=slot.number_format, assert_value=cand.assert_value, as_of=as_of)
    return rendered, raw


def _analyze_slot(ontology, library: Library, slot: Slot, u: Understanding, vals: Values, lang: str, as_of: date,
                  override: Any, binding=None) -> dict[str, Any]:
    base = {**slot.to_dict(), "understanding": u.describe(), "concept": None, "concept_label": None, "confidence": 0.0,
            "answer": None, "value": None, "evidence": None, "issues": [], "reasons": [], "alternatives": [],
            "source": "ontologie", "option": None}
    if slot.target.get("unresolved_list"):
        base["issues"].append("liste déroulante dépendante (INDIRECT…) : options non lisibles, rien n'est écrit")

    # 1. Choix explicite de l'utilisateur
    if override != "__none__":
        if override is None:
            return {**base, "status": "skipped", "source": "utilisateur"}
        if isinstance(override, dict) and override.get("source") == "copilot" and override.get("text"):
            # Copilot : jamais automatique ; la citation et l'écart éventuel avec l'app sont affichés
            text = str(override["text"]).strip()
            previous = override.get("previous")
            issues = list(base["issues"])
            if previous and norm(previous) != norm(text):
                issues.append(f"incohérence : l'app proposait « {previous} », Copilot répond « {text} » ({override.get('citation')})")
            return {**base, "status": "review", "answer": text, "value": text, "_value": text, "confidence": 0.6, "source": "Copilot",
                    "evidence": f"Copilot · {override.get('citation')}", "issues": issues,
                    "reasons": [f"réponse Copilot (confiance {override.get('confidence') or '—'}), source citée : {override.get('citation')}"],
                    "sources": [{"kind": "copilot", "label": str(override.get("citation") or ""), "value": text}]}
        if isinstance(override, dict) and override.get("text") is not None:
            text = str(override["text"]).strip()
            return {**base, "status": "review" if not text else "auto", "answer": text, "value": text, "confidence": 1.0,
                    "source": "réponse saisie", "reasons": ["réponse saisie par l'utilisateur"]}
        concept = ontology.concepts.get(str(override))
        if concept is None:
            return {**base, "status": "unmatched", "issues": ["concept inconnu"]}
        cands = [Candidate(concept, 1.0, "choix de l'utilisateur", ["choisi par l'utilisateur"])]
        return _finish(ontology, base, slot, u, vals, lang, as_of, cands, source="utilisateur")

    # 2. Bibliothèque des réponses validées
    entry, sim = library.lookup(slot.question, [s for s in (vals.pid, vals.isin) if s])
    if entry is not None:
        if entry.action == "ignore":
            return {**base, "status": "skipped", "source": "bibliothèque", "reasons": [f"ignorée lors d'un RFI précédent ({entry.by or '—'}, {entry.at[:10]})"]}
        if entry.action == "text" and entry.text:
            status = "auto" if sim == 1.0 and not base["issues"] else "review"
            return {**base, "status": status, "answer": entry.text, "value": entry.text, "confidence": round(0.97 * sim, 2),
                    "source": "bibliothèque", "reasons": [f"réponse validée précédemment ({entry.by or '—'}, {entry.at[:10]})"]}
        concept = ontology.concepts.get(entry.concept or "")
        if concept is not None and not concept.problems:
            cand = Candidate(concept, 0.97 * sim, "bibliothèque", [f"correspondance validée précédemment ({entry.by or '—'}, {entry.at[:10]})"])
            return _finish(ontology, base, slot, u, vals, lang, as_of, [cand], source="bibliothèque")

    # 3. Ontologie, recoupée avec la liaison apprise sur les anciens RFI (quelle colonne avait été répondue)
    cands = match(ontology, u)
    source = "ontologie"
    concept = _binding_concept(ontology, binding) if binding is not None else None
    if concept is not None:
        proof = f"liaison apprise : pour cette question, {binding.support} fonds sur {binding.compared} avaient reçu la valeur de {binding.target}"
        if cands and (cands[0].concept.id == concept.id or cands[0].concept.source == concept.source):
            cands[0].reasons.append(proof)  # l'ontologie et les anciens RFI désignent la même donnée
        elif cands and cands[0].score >= AUTO:
            cands[0].flags.append(f"les anciens RFI désignaient une autre donnée : {concept.label(lang)} ({binding.support} fonds)")
        else:
            flags = [] if binding.strong else ["liaison apprise sur les anciens RFI : à vérifier"]
            cands = [Candidate(concept, 0.8 if binding.strong else 0.6, "liaison apprise", [proof], flags)] + cands
            source = "liaison apprise"
    if not cands:
        return {**base, "status": "unmatched", "issues": base["issues"] + (["question qualitative"] if u.qualitative else [])}
    return _finish(ontology, base, slot, u, vals, lang, as_of, cands, source=source)


def _binding_concept(ontology, binding) -> Concept | None:
    if binding.target.startswith("doc:"):
        name = binding.target[4:]
        return next((c for c in ontology.usable() if name in c.doc), None)  # champ de document → concept qui le recoupe
    concept = pseudo_concept(binding.target, binding.type, ontology)
    return None if concept.problems else concept


def _finish(ontology, base: dict, slot: Slot, u: Understanding, vals: Values, lang: str, as_of: date,
            cands: list[Candidate], source: str) -> dict[str, Any]:
    best = cands[0]
    evaluated: list[tuple[Candidate, Rendered, Any]] = []
    for cand in cands[:4]:
        rendered, raw = _candidate_answer(ontology, cand, u, vals, lang, slot, as_of)
        evaluated.append((cand, rendered, raw))
    best_c, best_r, best_raw = evaluated[0]
    flags = list(best_c.flags)
    # Lecture par défaut discutable : sans objet si toutes les lectures voisines donnent la même réponse
    if any("non précisé" in f for f in flags) and best_r.display is not None:
        siblings = [(c, r) for c, r, _ in evaluated[1:] if {t.raw for t in c.concept.terms} & {t.raw for t in best_c.concept.terms}
                    and c.concept.type == best_c.concept.type]
        if siblings and all(r.display == best_r.display for _, r in siblings):
            flags = [f for f in flags if "non précisé" not in f]
            best_c.reasons.append("même valeur quelle que soit la lecture")
    issues = list(base["issues"]) + flags + list(best_r.issues)
    alternatives = [{"concept": c.concept.id, "label": c.concept.label(lang), "score": round(c.score, 2),
                     "answer": r.display} for c, r, _ in evaluated[1:]]
    # Ambiguïté : une autre lecture presque aussi probable, avec une valeur différente
    for cand, rendered, _ in evaluated[1:]:
        if cand.score >= best_c.score - MARGIN and rendered.display is not None and rendered.display != best_r.display \
                and not any("autre lecture" in i for i in issues):
            issues.append(f"autre lecture possible : {cand.concept.label(lang)} = {rendered.display}")
            break
    row = {**base, "concept": best_c.concept.id, "concept_label": best_c.concept.label(lang), "confidence": round(best_c.score, 2),
           "reasons": best_c.reasons, "alternatives": alternatives, "evidence": best_raw.evidence if best_raw else None,
           "data_date": best_raw.data_date.isoformat() if best_raw and best_raw.data_date else None, "source": source}
    sources = []
    if best_raw is not None and best_raw.value is not None:
        sources.append({"kind": "fabric", "label": best_raw.evidence, "value": best_r.display,
                        "date": best_raw.data_date.isoformat() if best_raw.data_date else None})
    row["sources"] = sources
    fact = _document_fact(best_c.concept, getattr(vals, "doc_facts", {}))
    if best_r.display is None:
        if fact is not None and best_c.score >= MIN_SCORE:
            return _from_document(ontology, row, best_c, fact, u, lang, slot, as_of, issues)
        return {**row, "status": "no_value" if best_c.score >= MIN_SCORE else "unmatched", "issues": issues}
    row.update({"answer": best_r.display, "value": _jsonable(best_r.value), "option": best_r.option})
    if best_c.score < MIN_SCORE:
        return {**row, "status": "unmatched", "issues": issues + ["confiance trop faible"], "answer": None, "value": None,
                "suggestion": best_r.display}
    confirmed = False
    if fact is not None:
        check = _check_document(ontology, best_c.concept, best_raw.value if best_raw else None, fact)
        sources.append(_fact_source(fact, check, ontology, best_c.concept, u, lang, as_of))
        if check == "match":
            confirmed = True
            row["reasons"] = row["reasons"] + [f"confirmé par le {fact.citation}"]
        elif check == "mismatch":
            issues.append(f"incohérence : Fabric = {best_r.display}, {fact.citation} = {_fact_display(ontology, best_c.concept, fact, u, lang, as_of)}")
    if confirmed and issues and all(any(f in i for f in SOFT_ISSUES) for i in issues):
        row["reasons"] = row["reasons"] + [f"réserves levées par le document officiel : {'; '.join(issues)}"]
        issues = []  # Fabric et le document officiel disent la même chose : la lecture est sûre
    status = "auto" if best_c.score >= AUTO and not issues else "review"
    if slot.state == "answered":
        status = "existing"
    return {**row, "status": status, "issues": issues, "_value": best_r.value}


# --------------------------------------------------------------------------- documents officiels (DIC, prospectus)
SOFT_ISSUES = ("non précisé", "autre lecture", "lecture indirecte")


def _document_fact(concept: Concept, facts: dict) -> Any:
    for name in concept.doc:
        if name in facts:
            return facts[name]
    return None


def _fact_value(concept: Concept, fact) -> Any:
    value = fact.value
    if concept.type == "bool" and isinstance(value, (int, float)):
        return "yes" if value > 0 else "no"  # « commission de performance : 0 % » → non
    return value


def _check_document(ontology, concept: Concept, fabric: Any, fact) -> str:
    if concept.type == "long":
        return "unknown"  # un paragraphe ne se compare pas mot à mot
    value = _fact_value(concept, fact)
    if fact.field.startswith("prospectus.") and value == "yes" and concept.type == "bool":
        # le prospectus ne lit que la présence (« swing pricing ») : un silence n'est pas un « non »
        v = ontology.vocab_value("yes_no", fabric)
        return "match" if v is not None and v.id == "yes" else "mismatch" if v is not None else "unknown"
    return same(ontology, concept, fabric, value)


def _fact_display(ontology, concept: Concept, fact, u: Understanding, lang: str, as_of: date) -> str:
    rendered = render(ontology, concept, Raw(_fact_value(concept, fact), fact.citation), u, lang, as_of=as_of)
    return rendered.display or str(fact.value)


def _fact_source(fact, check: str, ontology, concept: Concept, u: Understanding, lang: str, as_of: date) -> dict[str, Any]:
    return {"kind": fact.doc.kind if fact.doc else "document", "label": fact.citation, "value": _fact_display(ontology, concept, fact, u, lang, as_of),
            "snippet": fact.snippet, "url": fact.doc.url if fact.doc else "", "check": check}


def _from_document(ontology, row: dict, cand: Candidate, fact, u: Understanding, lang: str, slot: Slot, as_of: date,
                   issues: list[str]) -> dict[str, Any]:
    """Fabric vide : la donnée du document officiel est proposée, citée, jamais écrite sans validation."""
    raw = Raw(_fact_value(cand.concept, fact), fact.citation, data_date=to_date(fact.doc.doc_date) if fact.doc else None)
    rendered = render(ontology, cand.concept, raw, u, lang, number_format=slot.number_format, assert_value=cand.assert_value, as_of=as_of)
    source = _fact_source(fact, "fill", ontology, cand.concept, u, lang, as_of)
    if rendered.display is None:
        return {**row, "status": "no_value", "issues": issues + rendered.issues, "sources": row["sources"] + [source]}
    return {**row, "status": "review" if slot.state != "answered" else "existing", "answer": rendered.display,
            "value": _jsonable(rendered.value), "_value": rendered.value, "option": rendered.option, "source": "document",
            "evidence": fact.citation, "reasons": row["reasons"] + [f"Fabric vide : repris du {fact.citation}"],
            "issues": issues + ["donnée lue dans le document officiel, absente de Fabric : à vérifier"],
            "sources": row["sources"] + [source]}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def generate(data: DataAccess, store: RfiStore, doc_id: str, pid: str | None, isin: str | None, as_of: str | None,
             lang: str | None, overrides: dict[str, Any], overwrite: bool, accept: list[str] | None, user: str,
             remember: bool = True, reusable: list[str] | None = None, precedents: PrecedentIndex | None = None,
             documents: "DocumentService | None" = None, bindings: "BindingIndex | None" = None, qvidian=None,
             half_life: int = HALF_LIFE_DAYS, cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Écrit les réponses « auto » + celles acceptées par l'utilisateur dans une nouvelle version du fichier."""
    path = store.original(doc_id)
    layout = detect(path)
    result = analyze(data, store, path, layout, pid, isin, as_of, lang, overrides, precedents, documents=documents, bindings=bindings,
                     qvidian=qvidian, half_life=half_life, cache=cache)
    accepted = set(accept or [])
    slots = {s.id: s for s in layout.slots}
    answers = []
    written_rows = []
    for row in result["questions"]:
        status = row["status"]
        ok = status == "auto" or (status == "review" and row["id"] in accepted) or (status == "existing" and overwrite and row["id"] in accepted | {r["id"] for r in result["questions"] if r["status"] == "existing" and overwrite and not r["issues"]})
        if not ok or row.get("answer") is None:
            continue
        if slots[row["id"]].target.get("unresolved_list"):
            continue
        value = row.pop("_value", None)
        answers.append((slots[row["id"]].target, value if value is not None else row["answer"], slots[row["id"]].options))
        written_rows.append(row)
    for row in result["questions"]:
        row.pop("_value", None)
    meta = store.meta(doc_id)
    folder = store.folder(doc_id)
    number = len(meta["versions"]) + 1
    stem = re.sub(r"[^\w\-]+", "_", Path(meta["filename"]).stem).strip("_") or "rfi"
    target = folder / "versions" / f"{stem}_rempli_v{number}{meta['suffix']}"
    written = write(path, target, answers)

    # Apprentissage : ce qu'un humain a validé devient une connaissance réutilisable
    if remember:
        library = _library(store)
        scope_default = pid or "all"
        reusable_ids = set(reusable or [])
        by_id = {r["id"]: r for r in result["questions"]}
        for row in written_rows:
            if row["source"] == "Copilot":
                continue  # une réponse Copilot validée n'entre pas dans la bibliothèque sans relecture humaine dédiée
            if row["source"] == "réponse saisie":
                library.remember(row["question"], "text", text=row["answer"], scope="all" if row["id"] in reusable_ids else scope_default, by=user)
            elif row["source"] == "précédent" and not row["concept"]:
                library.remember(row["question"], "text", text=row["answer"], scope=scope_default, by=user)
            elif row["concept"] and (row["status"] == "review" or row["source"] in {"utilisateur", "précédent"}):
                library.remember(row["question"], "concept", concept=row["concept"], by=user)
        for qid, ov in (overrides or {}).items():
            if ov is None and qid in by_id:
                library.remember(by_id[qid]["question"], "ignore", scope=scope_default, by=user)
        library.save()
        # Jeu d'or : chaque version validée sert de référence pour mesurer la précision du moteur
        gold = [{"question": r["question"], "location": r["location"], "concept": r["concept"], "answer": r["answer"]} for r in written_rows]
        target.with_suffix(".gold.json").write_text(json.dumps({"as_of": result["as_of"], "pid": pid, "isin": isin, "answers": gold},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")
    info = {"version": number, "written": written, "pid": pid, "isin": isin, "as_of": result["as_of"], "by": user,
            "created_at": datetime.now().isoformat(timespec="seconds"), "stats": result["stats"], "coverage": result["coverage"]}
    target.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**info, "file": target.name, "questions": result["questions"]}


def load_layout(store: RfiStore, doc_id: str) -> tuple[Path, Layout]:
    path = store.original(doc_id)
    return path, detect(path)


def document_text(path: Path) -> str:
    try:
        return all_text(path)
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["RfiStore", "analyze", "generate", "search_funds", "suggest_funds", "fund_directory", "load_layout", "DataError"]
