"""Aller-retour avec Copilot (Microsoft 365), sans API : Copilot tourne sur le poste.

Voie simple (recommandée) : l'app écrit le prompt (questions numérotées Q1…Qn, règles, format de retour imposé : un
tableau « ID | Réponse | Source | Confiance »), l'utilisateur le colle dans Copilot avec le DIC et le prospectus joints,
puis colle la réponse dans l'app, qui la lit, la contrôle et montre ce qu'elle a compris avant de l'appliquer.
Les gros questionnaires sont découpés en lots (taille d'un message Copilot).
Voie classeur : un pack Excel + PDF à ouvrir dans Copilot, puis réimport du classeur.

Garde-fous à l'import : une réponse sans source citée est ignorée ; une réponse hors liste déroulante est refusée ;
« NON TROUVÉ » n'est jamais écrit ; une réponse qui contredit Fabric est signalée comme incohérence.
"""
from __future__ import annotations

import io
import re
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


# ------------------------------------------------------------------ voie simple : prompt à copier, réponse à coller
BATCH_CHARS = 9000  # questions par lot : sous la limite d'un message Copilot, prompt compris

PROMPT_HEAD = """Tu remplis un questionnaire de due diligence (RFI) pour {who}.
Sources autorisées : UNIQUEMENT les documents joints à ce message ({docs}). N'utilise ni internet ni tes connaissances générales.

Règles
1. Cherche la réponse de chaque question dans les documents joints.
2. Si une « Réponse de l'app » est indiquée, vérifie-la : si le document la confirme, recopie-la ; s'il dit autre chose, donne la valeur du document.
3. Si des « Choix » sont listés, réponds par UN de ces choix, recopié mot pour mot.
4. Cite toujours la source : document + page (ex. « DIC p.2 », « Prospectus p.47 »).
5. Si la réponse n'est pas dans les documents, écris NON TROUVÉ. N'invente jamais un chiffre, une date ou un nom.
6. Garde les unités du document (%, devise) ; dates au format JJ/MM/AAAA.

Format de réponse OBLIGATOIRE — uniquement ce tableau, sans phrase avant ni après, une ligne par question, dans l'ordre :
| ID | Réponse | Source | Confiance |
|---|---|---|---|
| Q1 | 1,50 % | DIC p.2 | haute |
| Q2 | NON TROUVÉ | | |
Confiance : haute (citation exacte), moyenne (déduite d'un passage), basse (incertain).
{part}
Questions"""


def _question_block(label: str, q: dict[str, Any]) -> str:
    section = q.get("context") or ""
    section = "" if re.fullmatch(r"[\d.\s]*", section) else section + " › "
    head = f"{label} — {section}{q['question']}"
    lines = [head.strip()]
    details = []
    if q.get("answer"):
        details.append(f"Réponse de l'app : {q['answer']}")
    if q.get("options"):
        details.append("Choix : " + " / ".join(q["options"][:25]))
    if q.get("hint"):
        details.append(f"Consigne du client : {q['hint']}")
    if details:
        lines.append("   " + " · ".join(details))
    return "\n".join(lines)


def build_prompts(analysis: dict[str, Any], fund: str, share: str, isin: str, documents: list[dict[str, Any]],
                  include_auto: bool = False, batch_chars: int = BATCH_CHARS) -> dict[str, Any]:
    """Un prompt par lot ; `labels` relie Q1…Qn aux cases du questionnaire (renvoyé tel quel au moment de coller)."""
    rows = rows_to_check(analysis, include_auto)
    who = f"le fonds « {fund} »" if fund else "le fonds"
    if share or isin:
        who += f", part {share or ''}{' ' if share and isin else ''}{f'(ISIN {isin})' if isin else ''}"
    names = {"kid": "DIC PRIIPs", "prospectus": "Prospectus"}
    docs = ", ".join(sorted({names.get(d.get("kind"), "document") for d in documents})) or "DIC PRIIPs et prospectus de la part"
    labels = {f"Q{n}": q["id"] for n, q in enumerate(rows, start=1)}
    blocks = [_question_block(label, q) for label, q in zip(labels, rows)]
    batches: list[list[int]] = [[]]
    size = 0
    for i, block in enumerate(blocks):
        if batches[-1] and size + len(block) > batch_chars:
            batches.append([])
            size = 0
        batches[-1].append(i)
        size += len(block) + 1
    out = []
    for n, idx in enumerate(batches, start=1):
        if not idx:
            continue
        part = f"\nLot {n}/{len(batches)} du questionnaire.\n" if len(batches) > 1 else ""
        prompt = PROMPT_HEAD.format(who=who, docs=docs, part=part) + "\n" + "\n".join(blocks[i] for i in idx)
        out.append({"prompt": prompt, "labels": [list(labels)[i] for i in idx], "chars": len(prompt)})
    return {"batches": out, "labels": labels, "count": len(rows)}


ROW = re.compile(r"^\s*\|?\s*\**\s*(Q\s*\d+)\s*\**\s*\|(.*)$", re.I)


def parse_table(text: str) -> list[tuple[str, str, str, str]]:
    """Lignes « | Q12 | réponse | source | confiance | » (tableau Markdown, ou simples barres verticales)."""
    rows = []
    for line in (text or "").splitlines():
        m = ROW.match(line.replace("\u00a0", " "))
        if not m:
            continue
        cells = [c.strip().strip("*`").strip() for c in m.group(2).rstrip().rstrip("|").split("|")]
        cells += [""] * (3 - len(cells))
        answer, source, confidence = cells[0], cells[1], cells[2] if len(cells) > 2 else ""
        rows.append((re.sub(r"\s+", "", m.group(1)).upper(), answer, source, confidence.lower()))
    return rows


def validate(records: list[tuple[str, str, str, str]], analysis: dict[str, Any], ontology) -> dict[str, Any]:
    """(id, réponse, source, confiance) → surcharges « à vérifier » + compte rendu ligne à ligne."""
    by_id = {q["id"]: q for q in analysis["questions"]}
    overrides, lines = {}, []
    for qid, answer, source, confidence in records:
        q = by_id.get(qid)
        if q is None:
            continue
        line = {"id": qid, "question": q["question"], "answer": answer, "citation": source, "confidence": confidence,
                "previous": q.get("answer"), "verdict": "ok", "reason": ""}
        if norm(answer) in NOT_FOUND or norm(answer).startswith("non trouv"):
            line.update(verdict="not_found", reason="pas dans les documents")
        elif not source:
            line.update(verdict="rejected", reason="aucune source citée")
        else:
            if q.get("options"):
                option, _ = choose_option(q["options"], texts=[answer], ontology=ontology, vocab_name="yes_no",
                                          vocab=ontology.vocab_value("yes_no", answer))
                if option is None:
                    line.update(verdict="rejected", reason=f"« {answer} » n'est pas un choix du client")
                else:
                    answer = line["answer"] = option
            if line["verdict"] == "ok":
                line["differs"] = bool(q.get("answer")) and norm(q["answer"]) != norm(answer)
                overrides[qid] = {"text": answer, "source": "copilot", "citation": source, "confidence": confidence,
                                  "previous": q.get("answer")}
        lines.append(line)
    rejected = [{"id": x["id"], "question": x["question"], "reason": x["reason"]} for x in lines if x["verdict"] == "rejected"]
    return {"overrides": overrides, "rejected": rejected, "lines": lines}


def parse_reply(text: str, labels: dict[str, str], analysis: dict[str, Any], ontology) -> dict[str, Any]:
    rows = parse_table(text)
    records = [(labels[label], answer, source, conf) for label, answer, source, conf in rows if label in labels]
    result = validate(records, analysis, ontology)
    result["read"] = len(records)
    result["unknown"] = sorted({label for label, *_ in rows if label not in labels})
    return result


# ------------------------------------------------------------------ voie classeur : réimport du pack Excel
def read_answers(raw: bytes, analysis: dict[str, Any], ontology) -> dict[str, Any]:
    """Classeur Copilot rempli → mêmes contrôles que la voie simple."""
    if raw[:2] == b"PK" and b"Questions_Copilot.xlsx" in raw[:4000]:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            raw = zf.read("Questions_Copilot.xlsx")
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb["Questions"] if "Questions" in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [norm(h) for h in next(rows, [])]
    col = {name: header.index(norm(name)) for name in HEADERS if norm(name) in header}

    def cell(row, name):
        return str(row[col[name]] or "").strip() if name in col else ""

    records = [(row[col["ID"]], cell(row, "Réponse Copilot"), cell(row, "Source citée (document, page)"), cell(row, "Confiance").lower())
               for row in rows if "ID" in col and row[col["ID"]]]
    return validate(records, analysis, ontology)
