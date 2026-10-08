"""Repérage des questions et de leur case réponse dans un RFI Excel (.xlsx/.xlsm) ou Word (.docx).

Excel : une question est une cellule de texte ; sa réponse est la colonne « Réponse / Answer » si l'en-tête
existe, sinon la première cellule vide à sa droite (cellules fusionnées gérées).
Word : tableaux (question dans une cellule, réponse dans une cellule vide de la même ligne), paragraphes
« Question : ____ » (réponse en ligne) et paragraphes question suivis d'un paragraphe vide.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .facts import norm

PLACEHOLDER = re.compile(r"^\s*(?:_{2,}|\.{3,}|…+|x{3,}|\?{1,3}|-|tbd|tbc|n/?a\s*\?|\[[^\]]{0,40}\]|<[^>]{0,40}>|a completer|a remplir|to be completed|reponse|answer|response)\s*$", re.I)
ANSWER_HEADER = re.compile(r"^(?:reponses?|answers?|responses?|valeurs?|values?|reponse du gerant|votre reponse|your answer|donnees|data|information)$")
INLINE_PLACEHOLDER = re.compile(r"_{3,}|\.{4,}|…{2,}|\[\s*(?:a completer|a remplir|reponse|answer|to be completed|x+)\s*\]", re.I)
MAX_ROWS, MAX_COLS = 3000, 40


@dataclass
class Question:
    id: str
    text: str
    location: str  # libellé lisible : « Feuille!B12 », « Tableau 2, ligne 3 », « Paragraphe 14 »
    target: dict[str, Any]  # où écrire
    existing: str = ""
    context: str = ""  # titre de section / feuille, aide au rapprochement

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Detection:
    kind: str  # xlsx | docx
    questions: list[Question] = field(default_factory=list)
    language: str = "fr"
    text_sample: str = ""


def is_question_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 3 or len(text) > 600 or not re.search(r"[A-Za-zÀ-ÿ]{3}", text):
        return False
    if PLACEHOLDER.match(text):
        return False
    return True


def is_empty_answer(value: Any) -> bool:
    return value is None or (isinstance(value, str) and (not value.strip() or bool(PLACEHOLDER.match(value))))


def detect_language(text: str) -> str:
    words = norm(text).split()
    fr = sum(w in {"le", "la", "les", "des", "du", "de", "et", "est", "votre", "vos", "quel", "quelle", "fonds", "part"} for w in words)
    en = sum(w in {"the", "of", "and", "is", "your", "what", "which", "fund", "share", "please", "provide"} for w in words)
    return "en" if en > fr else "fr"


# --------------------------------------------------------------------------- Excel
def detect_xlsx(path: Path) -> Detection:
    wb = load_workbook(path, data_only=True)
    detection = Detection("xlsx")
    sample: list[str] = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        max_row, max_col = min(ws.max_row or 1, MAX_ROWS), min(ws.max_column or 1, MAX_COLS)
        merged_tl: dict[str, str] = {}  # cellule couverte -> coin supérieur gauche
        merged_span: dict[str, int] = {}  # coin -> dernière colonne de la fusion
        for rng in ws.merged_cells.ranges:
            tl = f"{get_column_letter(rng.min_col)}{rng.min_row}"
            merged_span[tl] = rng.max_col
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    if (r, c) != (rng.min_row, rng.min_col):
                        merged_tl[f"{get_column_letter(c)}{r}"] = tl

        # Colonne « Réponse » éventuelle (en-tête dans les 15 premières lignes)
        answer_col, header_row = None, 0
        for r in range(1, min(max_row, 15) + 1):
            for c in range(1, max_col + 1):
                if ANSWER_HEADER.match(norm(ws.cell(r, c).value)):
                    answer_col, header_row = c, r
                    break
            if answer_col:
                break

        section = ws.title
        for r in range(header_row + 1, max_row + 1):
            row_values = [ws.cell(r, c).value for c in range(1, max_col + 1)]
            texts = [(c + 1, v) for c, v in enumerate(row_values) if is_question_text(v) and f"{get_column_letter(c + 1)}{r}" not in merged_tl]
            if not texts:
                continue
            q_col, q_text = texts[0]
            sample.append(q_text)
            if len(texts) == 1 and all(is_empty_answer(v) for v in row_values[q_col:]) and _looks_like_title(q_text):
                section = q_text.strip()
                continue
            target_col = None
            if answer_col and answer_col > q_col:
                target_col = answer_col
            else:
                start = merged_span.get(f"{get_column_letter(q_col)}{r}", q_col) + 1
                for c in range(start, min(start + 4, max_col + 2)):
                    ref = f"{get_column_letter(c)}{r}"
                    if ref in merged_tl:
                        continue
                    value = ws.cell(r, c).value
                    if is_empty_answer(value):
                        target_col = c
                        break
                    if is_question_text(value) and len(str(value)) > 40:
                        break  # une autre question sur la même ligne : pas de case réponse
                    target_col = c  # déjà renseignée : on la garde comme réponse existante
                    break
            if target_col is None:
                continue
            ref = f"{get_column_letter(target_col)}{r}"
            ref = merged_tl.get(ref, ref)
            existing = ws[ref].value
            detection.questions.append(Question(
                id=f"x{len(detection.questions) + 1}", text=str(q_text).strip(), location=f"{ws.title}!{ref}",
                target={"sheet": ws.title, "cell": ref}, existing="" if is_empty_answer(existing) else str(existing),
                context=section,
            ))
    detection.text_sample = " ".join(sample)[:20000]
    detection.language = detect_language(detection.text_sample)
    return detection


def _looks_like_title(text: str) -> bool:
    t = text.strip()
    return len(t) < 60 and not t.endswith(("?", ":")) and (t.isupper() or bool(re.match(r"^(?:[IVX]+|\d+(?:\.\d+)*)[.)]?\s", t)))


# --------------------------------------------------------------------------- Word
def _cell_text(cell) -> str:
    return "\n".join(p.text for p in cell.paragraphs).strip()


def detect_docx(path: Path) -> Detection:
    import docx

    document = docx.Document(str(path))
    detection = Detection("docx")
    sample: list[str] = []

    # Tableaux (niveau 1)
    for t_index, table in enumerate(document.tables):
        rows = table.rows
        answer_idx = None
        if rows:
            header = [norm(_cell_text(c)) for c in rows[0].cells]
            answer_idx = next((i for i, h in enumerate(header) if ANSWER_HEADER.match(h)), None)
        for r_index, row in enumerate(rows):
            if answer_idx is not None and r_index == 0:
                continue
            cells = row.cells
            seen: list[int] = []
            unique = []
            for i, cell in enumerate(cells):  # cellules fusionnées : python-docx répète la même cellule
                if any(cell._tc is cells[j]._tc for j in seen):
                    continue
                seen.append(i)
                unique.append((i, cell))
            if len(unique) < 2:
                continue
            q_pos, q_text = next(((i, _cell_text(c)) for i, c in unique if is_question_text(_cell_text(c))), (None, ""))
            if q_pos is None:
                continue
            sample.append(q_text)
            candidates = [(i, c) for i, c in unique if i > q_pos]
            if answer_idx is not None:
                candidates = [(i, c) for i, c in candidates if i == answer_idx] or candidates
            target = next(((i, c) for i, c in candidates if is_empty_answer(_cell_text(c))), None)
            existing = ""
            if target is None:
                if not candidates:
                    continue
                target = candidates[-1]
                existing = _cell_text(target[1])
                if is_question_text(existing) and len(existing) > 60:
                    continue
            detection.questions.append(Question(
                id=f"t{len(detection.questions) + 1}", text=q_text, location=f"Tableau {t_index + 1}, ligne {r_index + 1}",
                target={"type": "cell", "table": t_index, "row": r_index, "col": target[0]}, existing=existing,
            ))

    # Paragraphes (hors tableaux)
    paragraphs = document.paragraphs
    section = ""
    for p_index, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if style.startswith(("heading", "titre")):
            section = text
            continue
        if not is_question_text(text):
            continue
        sample.append(text)
        if INLINE_PLACEHOLDER.search(text):
            detection.questions.append(Question(
                id=f"p{len(detection.questions) + 1}", text=INLINE_PLACEHOLDER.sub("", text).strip(" :"),
                location=f"Paragraphe {p_index + 1}", target={"type": "placeholder", "paragraph": p_index}, context=section,
            ))
            continue
        if text.endswith(":") and len(text) < 160:
            detection.questions.append(Question(
                id=f"p{len(detection.questions) + 1}", text=text.rstrip(" :"), location=f"Paragraphe {p_index + 1}",
                target={"type": "inline", "paragraph": p_index}, context=section,
            ))
            continue
        if text.endswith("?") and p_index + 1 < len(paragraphs) and is_empty_answer(paragraphs[p_index + 1].text):
            detection.questions.append(Question(
                id=f"p{len(detection.questions) + 1}", text=text, location=f"Paragraphe {p_index + 1}",
                target={"type": "next", "paragraph": p_index + 1}, context=section,
            ))
    detection.text_sample = " ".join(sample)[:20000]
    detection.language = detect_language(detection.text_sample)
    return detection


def detect(path: Path) -> Detection:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return detect_xlsx(path)
    if suffix == ".docx":
        return detect_docx(path)
    raise ValueError(suffix)


def all_text(path: Path) -> str:
    """Texte brut du document (repérage des ISIN et du nom du fonds)."""
    suffix = path.suffix.lower()
    chunks: list[str] = []
    if suffix in {".xlsx", ".xlsm"}:
        wb = load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLS, values_only=True):
                chunks.extend(str(v) for v in row if isinstance(v, str))
    else:
        import docx

        d = docx.Document(str(path))
        chunks.extend(p.text for p in d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                chunks.extend(c.text for c in row.cells)
    return "\n".join(chunks)
