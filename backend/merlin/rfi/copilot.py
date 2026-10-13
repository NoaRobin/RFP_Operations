"""Aller-retour avec Copilot (Microsoft 365) : l'app prépare un classeur + les DIC / prospectus de la part ; Copilot
confirme ou complète en citant le document et la page ; l'app réimporte en « à vérifier », jamais en automatique.

Garde-fous à l'import : une réponse sans source citée est ignorée ; une réponse hors liste déroulante est refusée ;
« NON TROUVÉ » n'est jamais écrit ; une réponse qui contredit Fabric est signalée comme incohérence.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .ontology import norm
from .render import choose_option

HEADERS = ["ID", "Section", "Question", "Cellule", "Options autorisées", "Réponse proposée par l'app", "Source de l'app", "Statut",
           "Réponse Copilot", "Source citée (document, page)", "Confiance", "Commentaire"]
NOT_FOUND = {"non trouve", "non trouvee", "not found", "introuvable", "n/a", "na", ""}
PROMPT = """Tu es l'assistant de l'équipe RFP. Pour chaque ligne de l'onglet « Questions » :
1. Lis la question et la « Réponse proposée par l'app ».
2. Cherche la réponse UNIQUEMENT dans les documents fournis avec ce classeur (DIC PRIIPs, prospectus{docs}).
3. Si la réponse proposée est confirmée par un document : recopie-la dans « Réponse Copilot ».
   Si un document dit autre chose ou si l'app n'a rien proposé : écris la réponse trouvée.
   Si « Options autorisées » est renseigné : réponds avec UNE de ces options, mot pour mot.
4. Indique toujours dans « Source citée » le document et la page (ex. « DIC p. 2 »). Sans source, la réponse sera ignorée.
5. Si tu ne trouves pas : écris « NON TROUVÉ ». N'invente jamais un chiffre, une date ou un nom.
6. Confiance : haute (citation exacte), moyenne (déduite d'un passage), basse (incertain).
Fonds : {fund} — part {isin}. Ne modifie pas les colonnes A à H."""


def rows_to_check(analysis: dict[str, Any], include_auto: bool = False) -> list[dict[str, Any]]:
    keep = {"review", "no_value", "unmatched"} | ({"auto"} if include_auto else set())
    return [q for q in analysis["questions"] if q["status"] in keep]


def build_pack(analysis: dict[str, Any], fund: str, isin: str, documents: list[dict[str, Any]], include_auto: bool = False) -> bytes:
    """Classeur (+ PDF) dans un zip : à déposer dans OneDrive et ouvrir avec Copilot."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Consignes Copilot"
    docs = ", ".join(Path(d["path"]).name for d in documents if d.get("path")) or "aucun document trouvé : à joindre"
    ws["A1"] = "Consignes pour Copilot"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"] = PROMPT.format(docs=f" : {docs}", fund=fund or "—", isin=isin or "—")
    ws["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 120
    ws.row_dimensions[3].height = 260

    q = wb.create_sheet("Questions")
    q.append(HEADERS)
    for cell in q[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="FFD23F")
    status_label = {"review": "à vérifier", "no_value": "sans donnée", "unmatched": "sans réponse", "auto": "automatique"}
    for row in rows_to_check(analysis, include_auto):
        issues = [i for i in row.get("issues", []) if i.startswith("incohérence")]
        q.append([row["id"], row.get("context") or "", row["question"], row["location"], " | ".join(row.get("options") or []),
                  row.get("answer") or "", row.get("evidence") or row.get("source") or "",
                  ("incohérence" if issues else status_label.get(row["status"], row["status"])), "", "", "", ""])
    widths = [8, 22, 60, 16, 30, 30, 34, 14, 40, 26, 12, 30]
    for i, w in enumerate(widths, start=1):
        q.column_dimensions[chr(64 + i)].width = w
    if q.max_row > 1:
        dv = DataValidation(type="list", formula1='"haute,moyenne,basse"', allow_blank=True)
        q.add_data_validation(dv)
        dv.add(f"K2:K{q.max_row}")
    for row in q.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    q.freeze_panes = "C2"

    d = wb.create_sheet("Documents")
    d.append(["Type", "Fichier", "Adresse d'origine", "Date"])
    for doc in documents:
        d.append([{"kid": "DIC PRIIPs", "prospectus": "Prospectus"}.get(doc.get("kind"), doc.get("kind")), Path(doc.get("path") or "").name,
                  doc.get("url") or "", doc.get("doc_date") or ""])

    buf = io.BytesIO()
    wb.save(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Questions_Copilot.xlsx", buf.getvalue())
        for doc in documents:
            path = Path(doc.get("path") or "")
            if path.exists():
                zf.write(path, path.name)
        zf.writestr("LISEZ-MOI.txt", "1. Déposez ce dossier dans OneDrive.\n2. Ouvrez Questions_Copilot.xlsx et demandez à Copilot : "
                                       "« Suis les consignes de l'onglet Consignes Copilot en utilisant les PDF du dossier ».\n"
                                       "3. Enregistrez puis réimportez le classeur dans l'app (bouton « Importer les réponses Copilot »).\n")
    return out.getvalue()


def read_answers(raw: bytes, analysis: dict[str, Any], ontology) -> dict[str, Any]:
    """Réponses Copilot → surcharges « à vérifier » (avec citation), et la liste de ce qui a été écarté et pourquoi."""
    if raw[:2] == b"PK" and b"Questions_Copilot.xlsx" in raw[:4000]:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            raw = zf.read("Questions_Copilot.xlsx")
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb["Questions"] if "Questions" in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [norm(h) for h in next(rows, [])]
    col = {name: header.index(norm(name)) for name in HEADERS if norm(name) in header}
    by_id = {q["id"]: q for q in analysis["questions"]}
    overrides, rejected = {}, []
    for row in rows:
        qid = row[col["ID"]] if "ID" in col else None
        if qid not in by_id:
            continue
        q = by_id[qid]
        answer = str(row[col["Réponse Copilot"]] or "").strip() if "Réponse Copilot" in col else ""
        source = str(row[col["Source citée (document, page)"]] or "").strip() if "Source citée (document, page)" in col else ""
        confidence = str(row[col["Confiance"]] or "").strip() if "Confiance" in col else ""
        if norm(answer) in NOT_FOUND or norm(answer).startswith("non trouv"):
            continue
        if not source:
            rejected.append({"id": qid, "question": q["question"], "reason": "aucune source citée"})
            continue
        if q.get("options"):
            option, _ = choose_option(q["options"], texts=[answer], ontology=ontology, vocab_name="yes_no",
                                      vocab=ontology.vocab_value("yes_no", answer))
            if option is None:
                rejected.append({"id": qid, "question": q["question"], "reason": f"« {answer} » n'est pas dans la liste du client"})
                continue
            answer = option
        overrides[qid] = {"text": answer, "source": "copilot", "citation": source, "confidence": confidence,
                          "previous": q.get("answer")}
    return {"overrides": overrides, "rejected": rejected}
