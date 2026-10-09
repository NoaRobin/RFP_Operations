"""Lecture d'un RFI : où sont les questions, où écrire chaque réponse, et sous quelles contraintes.

Excel (.xlsx / .xlsm)
  - trois dispositions : liste de questions (question → case réponse), grille « une ligne par part » (en-têtes de
    colonnes = questions, une colonne ISIN), grille « une colonne par part » (ISIN en en-tête de colonnes) ;
  - listes déroulantes (validations de données) : classiques ET « x14 » (listes pointant vers une autre feuille,
    ignorées par openpyxl) ; plages, noms définis et listes en dur sont résolus ;
  - cases déjà « remplies » par le client avec une consigne (« Indiquer la devise », « Oui/Non », « [à compléter] »,
    « jj/mm/aaaa », « Select… ») : reconnues comme vides, la consigne sert d'indice ;
  - format de la cellule (pourcentage, date, nombre) relevé pour écrire la valeur au bon format.
Word (.docx)
  - tableaux question / réponse (et grilles par ISIN), paragraphes « Question : ____ », paragraphe vide après « ? » ;
  - contrôles de contenu (listes déroulantes, cases à cocher) et cases « ☐ Oui ☐ Non » écrites en texte.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

from .ontology import norm

MAX_ROWS, MAX_COLS = 3000, 60
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NSR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NSP = "http://schemas.openxmlformats.org/package/2006/relationships"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM = "http://schemas.microsoft.com/office/excel/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
BOXES = "☐□☑☒■▢⬜"
CHECKED = "☒☑■"

# ------------------------------------------------------------------ consignes / cases « vides »
_PH_EXACT = re.compile(
    r"^(?:x+|_+|\.+|…+|-+|–|—|\?+|n/?a|na|tbd|tbc|tba|nc|n\.c|nd|n\.d|ras|%|€|x+(?:[\s,.]+x+)*\s*%?|"
    r"(?:jj|dd)/mm/(?:aaaa|yyyy|aa|yy)|mm/dd/(?:yyyy|yy)|yyyy-mm-dd|aaaa-mm-jj|hh:mm|hh h mm|hhhmm|"
    r"(?:oui|yes|y|o)\s*/\s*(?:non|no|n)(?:\s*/\s*(?:n/?a|na))?|"
    r"a completer|a renseigner|a remplir|a preciser|a indiquer|a fournir|a confirmer|completer|renseigner|remplir|"
    r"reponse|reponses|answer|response|your answer|votre reponse|to be completed|to be filled|to be provided|to complete|"
    r"fill in|select|selectionner|choisir|choose|please select|veuillez selectionner|liste deroulante|dropdown|"
    r"choisir dans la liste|choisir parmi la liste deroulante|choisir parmi la liste|reponse binaire|reponse libre|reponse numerique|"
    r"select from list|select from the list|select one|choisir une valeur|insert|enter|texte|text|information non disponible|"
    r"montant|amount|date|valeur|value|commentaire|comment|comments|commentaires)$")
_PH_BRACKET = re.compile(r"^[\[<({«].{0,120}[\]>)}»]$")
_PH_INSTRUCTION = re.compile(
    r"^(?:merci d[e']\s*|veuillez\s+|priere de\s+|svp\s+|please\s+|kindly\s+)?"
    r"(?:indiquer|indiquez|preciser|precisez|renseigner|renseignez|inserer|inserez|saisir|saisissez|mentionner|mentionnez|"
    r"donner|donnez|fournir|fournissez|completer|completez|selectionner|selectionnez|choisir|choisissez|cocher|cochez|"
    r"indicate|insert|specify|provide|state|enter|fill in|fill|complete|select|choose|tick|confirm|list|give|input|type|inscrire|inscrivez)\b")
_PH_MASK = re.compile(r"\b(?:xxx+|xx[,.]xx|\[\s*\.\.\.\s*\]|\.{3,}|_{3,}|<\s*\w+\s*>)")


def classify_cell(value: Any, *, italic: bool = False, grey: bool = False) -> tuple[str, str]:
    """('empty' | 'placeholder' | 'answered', consigne). Une consigne n'est jamais une réponse."""
    if value is None:
        return "empty", ""
    if not isinstance(value, str):
        return "answered", ""
    text = value.strip()
    if not text:
        return "empty", ""
    n = norm(text)
    if not n or _PH_EXACT.match(n) or _PH_BRACKET.match(text) and len(text) <= 120:
        return "placeholder", text
    if len(n) <= 160 and _PH_INSTRUCTION.match(n):
        return "placeholder", text
    if len(n) <= 60 and _PH_MASK.search(n):
        return "placeholder", text
    if (italic or grey) and len(n) <= 120 and not re.search(r"\d{3,}", n):
        return "placeholder", text
    return "answered", ""


def is_question_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 3 or len(text) > 700 or not re.search(r"[A-Za-zÀ-ÿ]{3}", text):
        return False
    n = norm(text)
    # Une consigne (« Indiquer l'encours du fonds ») est une question quand elle est en position de question ;
    # seuls les espaces réservés purs (« xxx », « [à compléter] », « Oui/Non ») ne le sont jamais.
    if _PH_EXACT.match(n) or (_PH_BRACKET.match(text) and len(text) <= 60) or (len(n) <= 30 and _PH_MASK.search(n)):
        return False
    return True


def detect_language(text: str) -> str:
    words = norm(text).split()
    fr = sum(w in {"le", "la", "les", "des", "du", "de", "et", "est", "votre", "vos", "quel", "quelle", "fonds", "part", "indiquer", "veuillez"} for w in words)
    en = sum(w in {"the", "of", "and", "is", "your", "what", "which", "fund", "share", "please", "provide", "indicate"} for w in words)
    return "en" if en > fr else "fr"


@dataclass
class Slot:
    """Une case où écrire une réponse."""
    id: str
    question: str
    location: str
    target: dict[str, Any]
    state: str = "empty"  # empty | placeholder | answered
    existing: str = ""  # contenu actuel si c'est une vraie réponse
    hint: str = ""  # consigne trouvée dans la case
    context: str = ""  # section, en-tête de colonne
    options: list[str] = field(default_factory=list)  # liste déroulante / cases à cocher
    options_source: str = ""  # « liste déroulante Excel », « contrôle de contenu Word », « cases à cocher »
    number_format: str | None = None
    entity: dict[str, str] = field(default_factory=dict)  # {"isin": …} dans une grille par part
    layout: str = "list"  # list | row-grid | column-grid | paragraph
    comment: str = ""  # commentaire existant (colonne « Commentaires »), jamais écrit par l'app
    comment_cell: str = ""
    parent: str = ""  # question dont dépend une sous-question conditionnelle (« Si oui… »)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Layout:
    kind: str
    slots: list[Slot] = field(default_factory=list)
    language: str = "fr"
    text_sample: str = ""
    isins: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ====================================================================== EXCEL
def _sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    wb = etree.fromstring(zf.read("xl/workbook.xml"))
    rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels.findall(f"{{{NSP}}}Relationship")}
    paths = {}
    for sheet in wb.find(f"{{{NS}}}sheets"):
        target = targets[sheet.get(f"{{{NSR}}}id")]
        paths[sheet.get("name")] = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
    return paths


def _split_list(formula: str) -> list[str]:
    inner = formula.strip()
    if inner.startswith('"') and inner.endswith('"'):
        inner = inner[1:-1].replace('""', '"')
    return [p.strip() for p in inner.split(",") if p.strip()]


def _resolve_range(wb, ref: str, default_sheet: str) -> list[str] | None:
    ref = ref.strip().lstrip("=")
    if "!" in ref:
        sheet, rng = ref.rsplit("!", 1)
        sheet = sheet.strip("'").replace("''", "'")
    else:
        sheet, rng = default_sheet, ref
    if sheet not in wb.sheetnames:
        return None
    try:
        min_col, min_row, max_col, max_row = range_boundaries(rng.replace("$", ""))
    except ValueError:
        return None
    ws = wb[sheet]
    values = []
    for row in ws.iter_rows(min_row=min_row, max_row=min(max_row, min_row + 500), min_col=min_col, max_col=max_col, values_only=True):
        for v in row:
            if v is not None and str(v).strip():
                values.append(str(v).strip())
    return values


def _resolve_formula(wb, formula: str, sheet: str) -> list[str] | None:
    f = (formula or "").strip()
    if not f:
        return None
    if f.startswith('"'):
        return _split_list(f)
    if re.match(r"^(?:INDIRECT|OFFSET|CHOOSE|IF)\s*\(", f, re.I):
        return None  # listes dépendantes : non résolues, jamais devinées
    if re.match(r"^'?[^!]+'?!\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?$", f) or re.match(r"^\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?$", f):
        return _resolve_range(wb, f, sheet)
    name = f.lstrip("=")
    try:
        dn = wb.defined_names.get(name)
    except Exception:  # noqa: BLE001
        dn = None
    if dn is None and hasattr(wb[sheet], "defined_names"):
        dn = wb[sheet].defined_names.get(name)
    if dn is not None:
        out: list[str] = []
        for title, coord in dn.destinations:
            vals = _resolve_range(wb, f"'{title}'!{coord}", sheet)
            if vals is None:
                return None
            out.extend(vals)
        return out
    return None


def _validations(zf: zipfile.ZipFile, path: str, wb, sheet: str) -> dict[str, list[str] | None]:
    """Cellule → options de la liste déroulante (None si la liste existe mais n'est pas résoluble)."""
    root = etree.fromstring(zf.read(path))
    found: list[tuple[str, str]] = []
    for dv in root.iter(f"{{{NS}}}dataValidation"):
        if dv.get("type") == "list":
            f1 = dv.find(f"{{{NS}}}formula1")
            found.append((dv.get("sqref") or "", f1.text if f1 is not None else ""))
    for dv in root.iter(f"{{{X14}}}dataValidation"):
        if dv.get("type") == "list":
            f = dv.find(f"{{{X14}}}formula1/{{{XM}}}f")
            sq = dv.find(f"{{{XM}}}sqref")
            found.append((sq.text if sq is not None else "", f.text if f is not None else ""))
    out: dict[str, list[str] | None] = {}
    for sqref, formula in found:
        options = _resolve_formula(wb, formula, sheet)
        for part in sqref.split():
            try:
                min_col, min_row, max_col, max_row = range_boundaries(part)
            except ValueError:
                continue
            if (max_row - min_row) * (max_col - min_col) > 20000:
                max_row = min(max_row, min_row + 3000)
            for r in range(min_row, max_row + 1):
                for c in range(min_col, min(max_col, MAX_COLS) + 1):
                    out[f"{get_column_letter(c)}{r}"] = options
    return out


def _font_flags(cell) -> tuple[bool, bool]:
    font = cell.font
    italic = bool(font and font.i)
    grey = False
    color = getattr(font, "color", None) if font else None
    rgb = getattr(color, "rgb", None) if color is not None else None
    if isinstance(rgb, str) and len(rgb) >= 6:
        r, g, b = int(rgb[-6:-4], 16), int(rgb[-4:-2], 16), int(rgb[-2:], 16)
        grey = abs(r - g) < 20 and abs(g - b) < 20 and 90 <= r <= 200
    return italic, grey


ANSWER_HEADER = re.compile(r"^(?:reponses?|answers?|responses?|valeurs?|values?|votre reponse|your answer|reponse du gerant|"
                           r"reponse de la societe de gestion|manager response|manager's response|asset manager response|"
                           r"donnees|data|information|informations|input|saisie|a completer|to be completed|fund response|"
                           r"reponse fonds|reponse gestionnaire|your response|response from the manager)$")
COMMENT_HEADER = re.compile(r"commentaire|comments?|precisions?|remarques?|observations?|notes?")
INSTRUCTION_ROW = re.compile(r"^(?:-\s*)?(?:tous les champs|le fichier ne doit|si besoin|merci de|veuillez|please (?:complete|fill|note|answer)|"
                             r"all (?:fields|questions)|instructions?|important|nb|n\.b|note)\b")
CONDITIONAL = re.compile(r"^(?:si oui|si non|sinon|dans l'affirmative|dans ce cas|le cas echeant|if yes|if no|if so|if not|otherwise|"
                         r"in that case|ce minimum|cette|lequel|laquelle|lesquels|lesquelles|which one|preciser|precisez|please specify|"
                         r"details?|detaillez|si applicable|if applicable)\b")
QUESTION_HEADER = re.compile(r"^(?:questions?|items?|criteres?|criteria|champs?|fields?|libelles?|labels?|intitules?|"
                             r"rubriques?|sujets?|topics?|description|designation|information requested|information demandee|data point|datapoint)$")


def _isin_cells(values: list[Any]) -> list[int]:
    return [i for i, v in enumerate(values) if isinstance(v, str) and ISIN_RE.fullmatch(v.strip())]


def detect_xlsx(path: Path) -> Layout:
    wb = load_workbook(path, data_only=True)
    layout = Layout("xlsx")
    sample: list[str] = []
    with zipfile.ZipFile(path) as zf:
        sheet_paths = _sheet_paths(zf)
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            try:
                dvs = _validations(zf, sheet_paths[ws.title], wb, ws.title)
            except (KeyError, etree.XMLSyntaxError):
                dvs = {}
            _detect_sheet(ws, dvs, layout, sample)
    layout.text_sample = " ".join(sample)[:20000]
    layout.language = detect_language(layout.text_sample)
    layout.isins = sorted(set(ISIN_RE.findall(" ".join(sample))))
    return layout


def _make_slot(layout: Layout, ws, ref: str, question: str, context: str, dvs: dict, kind: str, entity: dict | None = None) -> Slot:
    cell = ws[ref]
    italic, grey = _font_flags(cell)
    state, hint = classify_cell(cell.value, italic=italic, grey=grey)
    options = dvs.get(ref, [])
    slot = Slot(
        id=f"x{len(layout.slots) + 1}", question=question.strip(), location=f"{ws.title}!{ref}",
        target={"sheet": ws.title, "cell": ref, "number_format": cell.number_format}, state=state,
        existing=("" if state != "answered" else str(cell.value)), hint=hint, context=context,
        options=list(options or []), options_source="liste déroulante Excel" if ref in dvs else "",
        number_format=cell.number_format, entity=entity or {}, layout=kind,
    )
    if ref in dvs and options is None:
        slot.options_source = "liste déroulante Excel (non résolue)"
        slot.target["unresolved_list"] = True
    if state == "answered" and options and norm(cell.value) not in {norm(o) for o in options}:
        pass
    return slot


def _detect_sheet(ws, dvs: dict, layout: Layout, sample: list[str]) -> None:
    max_row = min(ws.max_row or 1, MAX_ROWS)
    max_col = min((ws.max_column or 1) + 3, MAX_COLS)  # la case réponse vide peut être hors de la zone utilisée
    merged_tl: dict[str, str] = {}
    merged_span: dict[str, int] = {}
    for rng in ws.merged_cells.ranges:
        tl = f"{get_column_letter(rng.min_col)}{rng.min_row}"
        merged_span[tl] = rng.max_col
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    merged_tl[f"{get_column_letter(c)}{r}"] = tl
    grid = [[ws.cell(r, c).value for c in range(1, max_col + 1)] for r in range(1, max_row + 1)]
    for row in grid:
        sample.extend(str(v) for v in row if isinstance(v, str))

    # ---------------------------------------------------- grille « une colonne par part » : ISIN en ligne d'en-tête
    for r_idx in range(min(len(grid), 40)):
        isin_cols = _isin_cells(grid[r_idx])
        if len(isin_cols) >= 2:
            first = min(isin_cols)
            label_col = next((c for c in range(first - 1, -1, -1) if any(is_question_text(grid[r][c]) for r in range(r_idx + 1, len(grid)))), None)
            if label_col is None:
                break
            section = ws.title
            for r in range(r_idx + 1, len(grid)):
                label = grid[r][label_col]
                if not is_question_text(label):
                    continue
                if all(grid[r][c] is None for c in isin_cols) and _looks_like_title(str(label)):
                    section = str(label).strip()
                    continue
                for c in isin_cols:
                    ref = f"{get_column_letter(c + 1)}{r + 1}"
                    if ref in merged_tl:
                        continue
                    isin = str(grid[r_idx][c]).strip()
                    layout.slots.append(_make_slot(layout, ws, ref, str(label), f"{section}", dvs, "column-grid", {"isin": isin}))
            layout.notes.append(f"{ws.title} : grille par part ({len(isin_cols)} ISIN en colonnes)")
            return

    # ---------------------------------------------------- grille « une ligne par part » : colonne d'ISIN sous un en-tête
    for r_idx in range(min(len(grid), 40)):
        headers = [(c, v) for c, v in enumerate(grid[r_idx]) if isinstance(v, str) and v.strip() and not ISIN_RE.fullmatch(v.strip())]
        if len(headers) < 3:
            continue
        below = grid[r_idx + 1: r_idx + 400]
        isin_col = next((c for c, _ in headers if sum(1 for row in below if isinstance(row[c], str) and ISIN_RE.fullmatch(row[c].strip())) >= 2), None)
        if isin_col is None:
            isin_col = next((c for c in range(max_col) if sum(1 for row in below if isinstance(row[c], str) and ISIN_RE.fullmatch(str(row[c]).strip())) >= 2), None)
            if isin_col is None:
                continue
        for r in range(r_idx + 1, len(grid)):
            cell = grid[r][isin_col]
            if not (isinstance(cell, str) and ISIN_RE.fullmatch(cell.strip())):
                continue
            for c, header in headers:
                if c == isin_col:
                    continue
                ref = f"{get_column_letter(c + 1)}{r + 1}"
                if ref in merged_tl:
                    continue
                layout.slots.append(_make_slot(layout, ws, ref, str(header), ws.title, dvs, "row-grid", {"isin": cell.strip()}))
        layout.notes.append(f"{ws.title} : grille par part (une ligne par ISIN)")
        return

    # ---------------------------------------------------- liste de questions
    answer_col, comment_col, question_col, header_row = None, None, None, 0
    for r in range(min(len(grid), 30)):
        found = False
        for c, v in enumerate(grid[r]):
            n = norm(v)
            if not n or len(n) > 70:
                continue
            above = sum(1 for rr in range(r) if is_question_text(grid[rr][c]))
            if above >= 2:
                continue  # une ligne précédée de questions dans la même colonne n'est pas un en-tête (« Label », « Valeur »…)
            if ANSWER_HEADER.match(n) or (re.search(r"(?<![a-z])(?:reponses?|answers?|responses?)(?![a-z])", n) and not n.endswith("?")
                                          and not re.search(r"commentaire|comment|precision", n)):
                answer_col, header_row, found = c, r + 1, True
            elif COMMENT_HEADER.search(n) and answer_col is not None:
                comment_col = c
            elif QUESTION_HEADER.match(n):
                question_col, header_row, found = c, r + 1, True
        if found:
            if answer_col is not None:
                comment_col = next((c for c, v in enumerate(grid[r]) if c > answer_col and COMMENT_HEADER.search(norm(v))), comment_col)
            if answer_col is None and question_col is not None:
                # « Question | <nom du fonds> » : la colonne voisine reçoit les réponses
                answer_col = next((c for c in range(question_col + 1, max_col) if grid[r][c] is not None), None)
            break
    body = grid[header_row:]
    if question_col is None:
        # Colonne des questions : celle qui porte le plus de libellés (avant la colonne réponse)
        counts: dict[int, int] = {}
        for row in body:
            for c, v in enumerate(row):
                if (answer_col is None or c < answer_col) and is_question_text(v):
                    counts[c] = counts.get(c, 0) + 1
        if counts:
            question_col = max(counts, key=lambda c: (counts[c], -c))
            if answer_col is not None:
                # la question est la colonne de texte la plus proche à gauche de la réponse
                near = [c for c in counts if c < answer_col and counts[c] >= max(2, counts[question_col] // 3)]
                question_col = max(near) if near else question_col
    section = ws.title
    previous_question = ""
    for r in range(header_row, len(grid)):
        row = grid[r]
        cells = {c: v for c, v in enumerate(row) if f"{get_column_letter(c + 1)}{r + 1}" not in merged_tl}
        # Libellé de section dans une colonne à gauche des questions (« Demande », « Contacts SdG »…)
        if question_col is not None:
            left = [str(cells[c]).strip() for c in range(question_col) if isinstance(cells.get(c), str) and cells[c].strip()]
            if left:
                section = left[-1]
        q_candidates = [(c, v) for c, v in cells.items() if is_question_text(v) and (answer_col is None or c < answer_col)
                        and (question_col is None or c >= question_col)]
        if not q_candidates:
            continue
        q_col, q_text = q_candidates[0]
        rest = row[q_col + 1:]
        if len(q_candidates) == 1 and all(classify_cell(v)[0] != "answered" for v in rest) and _looks_like_title(str(q_text)) and \
                not any(f"{get_column_letter(c + 1)}{r + 1}" in dvs for c in range(q_col + 1, max_col)):
            section = str(q_text).strip()
            continue
        if INSTRUCTION_ROW.match(norm(q_text)) and answer_col is None:
            continue  # consigne générale du questionnaire, pas une question
        target_col = None
        if answer_col is not None and answer_col > q_col:
            target_col = answer_col
        else:
            start = merged_span.get(f"{get_column_letter(q_col + 1)}{r + 1}", q_col + 1)
            for c in range(start, min(start + 5, max_col)):
                ref = f"{get_column_letter(c + 1)}{r + 1}"
                if ref in merged_tl:
                    continue
                state, _ = classify_cell(row[c])
                if state != "answered" or ref in dvs:
                    target_col = c
                    break
                if is_question_text(row[c]) and len(str(row[c])) > 40:
                    break
                target_col = c  # déjà renseignée par une vraie réponse
                break
        if target_col is None:
            continue
        ref = f"{get_column_letter(target_col + 1)}{r + 1}"
        ref = merged_tl.get(ref, ref)
        slot = _make_slot(layout, ws, ref, str(q_text), section, dvs, "list")
        if comment_col is not None and comment_col != target_col and comment_col < len(row) and row[comment_col] is not None:
            slot.comment = str(row[comment_col]).strip()
            slot.comment_cell = f"{get_column_letter(comment_col + 1)}{r + 1}"
        if CONDITIONAL.match(norm(q_text)) and previous_question:
            slot.parent = previous_question  # « Si oui, de quel montant ? » dépend de la question précédente
        else:
            previous_question = str(q_text).strip()
        layout.slots.append(slot)


def _looks_like_title(text: str) -> bool:
    t = text.strip()
    # Titre de section : MAJUSCULES, ou numérotation romaine / lettre (« II. Frais », « B) Gestion »).
    # Un libellé court (« Forme juridique ») suivi d'une case vide est une question, pas un titre.
    if re.fullmatch(r"[A-Z0-9/&.\-]{2,8}", t):
        return False  # sigle seul (ISIN, SRI, SFDR, LEI, NAV, TER…) : c'est une donnée demandée, pas un titre
    return len(t) < 70 and not t.endswith(("?", ":")) and (t.isupper() or bool(re.match(r"^(?:[IVX]{1,4}|[A-H])[.)]\s", t)))


# ====================================================================== WORD
def _wq(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _el_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(_wq("t")))


def _sdt_info(sdt) -> tuple[str, list[str]]:
    """('dropdown' | 'checkbox' | 'date' | 'text', options)."""
    pr = sdt.find(_wq("sdtPr"))
    if pr is None:
        return "text", []
    for kind in ("dropDownList", "comboBox"):
        lst = pr.find(_wq(kind))
        if lst is not None:
            opts = [li.get(_wq("displayText")) or li.get(_wq("value")) or "" for li in lst.findall(_wq("listItem"))]
            return "dropdown", [o for o in opts if o.strip() and not re.match(r"^(?:choisissez|choose|select|selectionnez)", norm(o))]
    if pr.find(f"{{{W14}}}checkbox") is not None:
        return "checkbox", []
    if pr.find(_wq("date")) is not None:
        return "date", []
    return "text", []


def _checkbox_options(container) -> list[tuple[int, str]]:
    """Cases à cocher d'un paragraphe / d'une cellule : contrôles w14:checkbox ou glyphes « ☐ Libellé »."""
    sdts = [s for s in container.iter(_wq("sdt")) if _sdt_info(s)[0] == "checkbox"]
    if len(sdts) >= 2:
        text = etree.tostring(container, method="text", encoding="unicode")
        out = []
        for k, s in enumerate(sdts):
            label = ""
            nxt = s.getnext()
            while nxt is not None and nxt.tag != _wq("sdt"):
                label += _el_text(nxt)
                nxt = nxt.getnext()
            out.append((k, label.strip(" :;,") or f"option {k + 1}"))
        if any(o[1] for o in out) and text:
            return out
    text = _el_text(container)
    parts = re.findall(rf"[{BOXES}]\s*([^{BOXES}\n]+)", text)
    return [(k, p.strip(" :;,/")) for k, p in enumerate(parts)] if len(parts) >= 2 else []


def detect_docx(path: Path) -> Layout:
    import docx

    document = docx.Document(str(path))
    layout = Layout("docx")
    sample: list[str] = []

    for t_index, table in enumerate(document.tables):
        rows = table.rows
        answer_idx = None
        isin_cols: list[int] = []
        if rows:
            header = [norm(c.text) for c in rows[0].cells]
            answer_idx = next((i for i, h in enumerate(header) if ANSWER_HEADER.match(h)), None)
            isin_cols = [i for i, c in enumerate(rows[0].cells) if ISIN_RE.fullmatch(c.text.strip())]
        for r_index, row in enumerate(rows):
            if (answer_idx is not None or isin_cols) and r_index == 0:
                continue
            cells = row.cells
            unique: list[tuple[int, Any]] = []
            for i, cell in enumerate(cells):
                if any(cell._tc is u[1]._tc for u in unique):
                    continue
                unique.append((i, cell))
            if len(unique) < 2:
                continue
            q_pos, q_text = next(((i, c.text.strip()) for i, c in unique if is_question_text(c.text)), (None, ""))
            if q_pos is None:
                continue
            sample.append(q_text)
            if isin_cols:
                for i, cell in unique:
                    if i in isin_cols:
                        isin = rows[0].cells[i].text.strip()
                        layout.slots.append(_docx_cell_slot(layout, cell, q_text, t_index, r_index, i, f"Tableau {t_index + 1}, ligne {r_index + 1}", {"isin": isin}, "column-grid"))
                continue
            candidates = [(i, c) for i, c in unique if i > q_pos]
            if answer_idx is not None:
                candidates = [(i, c) for i, c in candidates if i == answer_idx] or candidates
            if not candidates:
                continue
            target = next(((i, c) for i, c in candidates if classify_cell(c.text)[0] != "answered" or _checkbox_options(c._tc)
                           or any(_sdt_info(s)[0] != "text" for s in c._tc.iter(_wq("sdt")))), None)
            if target is None:
                target = candidates[-1]
                if is_question_text(target[1].text) and len(target[1].text) > 60:
                    continue
            layout.slots.append(_docx_cell_slot(layout, target[1], q_text, t_index, r_index, target[0], f"Tableau {t_index + 1}, ligne {r_index + 1}", {}, "list"))

    paragraphs = document.paragraphs
    section = ""
    for p_index, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        el = paragraph._p
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if style.startswith(("heading", "titre")):
            section = text
            continue
        boxes = _checkbox_options(el)
        sdts = [s for s in el.iter(_wq("sdt")) if _sdt_info(s)[0] in {"dropdown", "date"}]
        if boxes:
            first_box = re.search(rf"[{BOXES}]", text)
            question = text[: first_box.start()].strip(" :") if first_box and first_box.start() > 2 else (paragraphs[p_index - 1].text.strip() if p_index else "")
            if is_question_text(question):
                sample.append(question)
                layout.slots.append(Slot(id=f"p{len(layout.slots) + 1}", question=question, location=f"Paragraphe {p_index + 1}",
                                         target={"type": "checkbox", "paragraph": p_index}, state="empty", options=[o for _, o in boxes],
                                         options_source="cases à cocher", context=section, layout="paragraph"))
            continue
        if sdts:
            kind, options = _sdt_info(sdts[0])
            before = ""
            for node in el:
                if node is sdts[0] or sdts[0] in node.iterdescendants():
                    break
                before += _el_text(node)
            question = before.strip(" :") or (paragraphs[p_index - 1].text.strip() if p_index else "")
            if is_question_text(question):
                state, hint = classify_cell(_el_text(sdts[0]))
                sample.append(question)
                layout.slots.append(Slot(id=f"p{len(layout.slots) + 1}", question=question, location=f"Paragraphe {p_index + 1}",
                                         target={"type": "sdt", "paragraph": p_index, "sdt": 0}, state=state, hint=hint,
                                         existing=_el_text(sdts[0]) if state == "answered" else "", options=options,
                                         options_source="contrôle de contenu Word" if options else "", context=section, layout="paragraph",
                                         number_format="date" if kind == "date" else None))
            continue
        if not is_question_text(text):
            continue
        sample.append(text)
        m = re.search(r"_{3,}|\.{4,}|…{2,}|\[[^\]]{0,60}\]|<[^>]{0,40}>", text)
        if m:
            hint = m.group(0) if m.group(0).startswith(("[", "<")) else ""
            question = (text[: m.start()] + text[m.end():]).strip(" :")
            layout.slots.append(Slot(id=f"p{len(layout.slots) + 1}", question=question, location=f"Paragraphe {p_index + 1}",
                                     target={"type": "placeholder", "paragraph": p_index, "placeholder": m.group(0)},
                                     state="placeholder", hint=hint, context=section, layout="paragraph"))
            continue
        if text.endswith(":") and len(text) < 200:
            layout.slots.append(Slot(id=f"p{len(layout.slots) + 1}", question=text.rstrip(" :"), location=f"Paragraphe {p_index + 1}",
                                     target={"type": "inline", "paragraph": p_index}, state="empty", context=section, layout="paragraph"))
            continue
        if text.endswith("?") and p_index + 1 < len(paragraphs):
            nxt = paragraphs[p_index + 1].text
            state, hint = classify_cell(nxt)
            if state != "answered":
                layout.slots.append(Slot(id=f"p{len(layout.slots) + 1}", question=text, location=f"Paragraphe {p_index + 1}",
                                         target={"type": "next", "paragraph": p_index + 1}, state=state, hint=hint, context=section, layout="paragraph"))
    layout.text_sample = " ".join(sample)[:20000]
    layout.language = detect_language(layout.text_sample)
    full = "\n".join(p.text for p in paragraphs) + "\n" + "\n".join(c.text for t in document.tables for r in t.rows for c in r.cells)
    layout.isins = sorted(set(ISIN_RE.findall(full)))
    return layout


def _docx_cell_slot(layout: Layout, cell, question: str, t: int, r: int, c: int, location: str, entity: dict, kind: str) -> Slot:
    tc = cell._tc
    boxes = _checkbox_options(tc)
    sdts = [s for s in tc.iter(_wq("sdt")) if _sdt_info(s)[0] in {"dropdown", "date"}]
    target = {"type": "cell", "table": t, "row": r, "col": c}
    options, source, number_format = [], "", None
    state, hint = classify_cell(cell.text)
    existing = cell.text.strip() if state == "answered" else ""
    if boxes:
        target = {"type": "checkbox", "table": t, "row": r, "col": c}
        options, source = [o for _, o in boxes], "cases à cocher"
        state, existing = ("answered", cell.text.strip()) if any(ch in cell.text for ch in CHECKED) else ("empty", "")
    elif sdts:
        kind_sdt, options = _sdt_info(sdts[0])
        target = {"type": "sdt", "table": t, "row": r, "col": c, "sdt": 0}
        source = "contrôle de contenu Word" if options else ""
        number_format = "date" if kind_sdt == "date" else None
        state, hint = classify_cell(_el_text(sdts[0]))
        existing = _el_text(sdts[0]) if state == "answered" else ""
    return Slot(id=f"t{len(layout.slots) + 1}", question=question, location=location, target=target, state=state, existing=existing,
                hint=hint, options=options, options_source=source, number_format=number_format, entity=entity, layout=kind)


def detect(path: Path) -> Layout:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return detect_xlsx(path)
    if suffix == ".docx":
        return detect_docx(path)
    raise ValueError(suffix)


def all_text(path: Path) -> str:
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


__all__ = ["Slot", "Layout", "detect", "all_text", "classify_cell", "is_question_text", "column_index_from_string"]
