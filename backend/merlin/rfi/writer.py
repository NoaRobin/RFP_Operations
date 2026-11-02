"""Écriture des réponses dans une COPIE du RFI, sans rien changer d'autre.

Excel : modification directe du XML des feuilles (styles, images, graphiques, validations… intacts :
toutes les autres parties du fichier sont recopiées octet pour octet).
Word : python-docx, en reprenant la mise en forme du texte voisin.
"""
from __future__ import annotations

import copy
import re
import shutil
import zipfile
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NSR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NSP = "http://schemas.openxmlformats.org/package/2006/relationships"


# --------------------------------------------------------------------------- Excel
def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _row_index(ref: str) -> int:
    return int(re.search(r"\d+", ref).group(0))


def _sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    wb = etree.fromstring(zf.read("xl/workbook.xml"))
    rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels.findall(f"{{{NSP}}}Relationship")}
    paths = {}
    for sheet in wb.find(f"{{{NS}}}sheets"):
        target = targets[sheet.get(f"{{{NSR}}}id")]
        path = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        paths[sheet.get("name")] = path
    return paths


def _excel_serial(d: date) -> float:
    return (d - date(1899, 12, 30)).days


def _set_cell(sheet_root, ref: str, value: Any, date_cell: bool = False) -> None:
    sheet_data = sheet_root.find(f"{{{NS}}}sheetData")
    r_idx = _row_index(ref)
    row = next((r for r in sheet_data.findall(f"{{{NS}}}row") if int(r.get("r", 0)) == r_idx), None)
    if row is None:
        row = etree.Element(f"{{{NS}}}row", r=str(r_idx))
        later = [r for r in sheet_data.findall(f"{{{NS}}}row") if int(r.get("r", 0)) > r_idx]
        if later:
            later[0].addprevious(row)
        else:
            sheet_data.append(row)
    cell = next((c for c in row.findall(f"{{{NS}}}c") if c.get("r") == ref), None)
    if cell is None:
        cell = etree.Element(f"{{{NS}}}c", r=ref)
        later = [c for c in row.findall(f"{{{NS}}}c") if _col_index(c.get("r")) > _col_index(ref)]
        if later:
            later[0].addprevious(cell)
        else:
            row.append(cell)
    style = cell.get("s")
    for child in list(cell):
        cell.remove(child)
    for attr in ("t", "cm", "vm"):
        cell.attrib.pop(attr, None)
    if style is not None:
        cell.set("s", style)
    if isinstance(value, bool) or value is None:
        value = "" if value is None else ("Oui" if value else "Non")
    if isinstance(value, (int, float)):
        v = etree.SubElement(cell, f"{{{NS}}}v")
        v.text = repr(float(value)) if isinstance(value, float) else str(value)
        return
    if isinstance(value, (date, datetime)):
        if date_cell:
            v = etree.SubElement(cell, f"{{{NS}}}v")  # cellule déjà au format date : numéro de série Excel
            v.text = str(_excel_serial(value if isinstance(value, date) and not isinstance(value, datetime) else value.date()))
            return
        value = value.strftime("%d/%m/%Y")  # texte : aucun style de date à créer
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS}}}is")
    t = etree.SubElement(is_el, f"{{{NS}}}t")
    t.text = str(value)
    if t.text != t.text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _is_date_format(fmt: str | None) -> bool:
    from .understand import expected_from_format

    return expected_from_format(fmt) == "date"


YELLOW = "FFFFFF00"


def _cell(sheet_root, ref: str):
    """Cellule existante, ou créée vide à sa place (ligne et colonne dans l'ordre)."""
    sheet_data = sheet_root.find(f"{{{NS}}}sheetData")
    r_idx = _row_index(ref)
    row = next((r for r in sheet_data.findall(f"{{{NS}}}row") if int(r.get("r", 0)) == r_idx), None)
    if row is None:
        row = etree.Element(f"{{{NS}}}row", r=str(r_idx))
        later = [r for r in sheet_data.findall(f"{{{NS}}}row") if int(r.get("r", 0)) > r_idx]
        if later:
            later[0].addprevious(row)
        else:
            sheet_data.append(row)
    cell = next((c for c in row.findall(f"{{{NS}}}c") if c.get("r") == ref), None)
    if cell is None:
        cell = etree.Element(f"{{{NS}}}c", r=ref)
        later = [c for c in row.findall(f"{{{NS}}}c") if _col_index(c.get("r")) > _col_index(ref)]
        if later:
            later[0].addprevious(cell)
        else:
            row.append(cell)
    return cell


def _yellow_styles(styles: bytes, used: set[int]) -> tuple[bytes, dict[int, int]]:
    """Ajoute un remplissage jaune et, pour chaque style de cellule utilisé, sa copie jaune (le reste du style intact)."""
    root = etree.fromstring(styles)
    fills = root.find(f"{{{NS}}}fills")
    xfs = root.find(f"{{{NS}}}cellXfs")
    if fills is None or xfs is None:
        return styles, {}
    fill = etree.SubElement(fills, f"{{{NS}}}fill")
    pattern = etree.SubElement(fill, f"{{{NS}}}patternFill", patternType="solid")
    etree.SubElement(pattern, f"{{{NS}}}fgColor", rgb=YELLOW)
    etree.SubElement(pattern, f"{{{NS}}}bgColor", indexed="64")
    fills.set("count", str(len(fills)))
    fill_id = len(fills) - 1
    existing = xfs.findall(f"{{{NS}}}xf")
    mapping: dict[int, int] = {}
    for old in sorted(used):
        base = existing[old] if old < len(existing) else existing[0]
        clone = copy.deepcopy(base)
        clone.set("fillId", str(fill_id))
        clone.set("applyFill", "1")
        xfs.append(clone)
        mapping[old] = len(xfs.findall(f"{{{NS}}}xf")) - 1
    xfs.set("count", str(len(xfs.findall(f"{{{NS}}}xf"))))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), mapping


def write_xlsx(source: Path, target: Path, answers: list[tuple], highlight: list[dict[str, Any]] | None = None) -> int:
    by_sheet: dict[str, list[tuple[str, Any, bool]]] = {}
    for tgt, value, *_ in answers:
        by_sheet.setdefault(tgt["sheet"], []).append((tgt["cell"], value, _is_date_format(tgt.get("number_format"))))
    marks: dict[str, list[str]] = {}
    for tgt in highlight or []:
        if tgt.get("sheet") and tgt.get("cell"):
            marks.setdefault(tgt["sheet"], []).append(tgt["cell"])
    with zipfile.ZipFile(source) as zin:
        paths = _sheet_paths(zin)
        patched: dict[str, bytes] = {}
        roots: dict[str, Any] = {}
        for sheet in set(by_sheet) | set(marks):
            if sheet not in paths:
                continue
            roots[sheet] = etree.fromstring(zin.read(paths[sheet]))
        for sheet, cells in by_sheet.items():
            root = roots.get(sheet)
            if root is None:
                continue
            for ref, value, date_cell in cells:
                _set_cell(root, ref, value, date_cell)
        # Réponses à demander : case surlignée en jaune (seulement les cases réponse ; styles d'origine copiés)
        if marks and "xl/styles.xml" in zin.namelist():
            targets = [(roots[sheet], _cell(roots[sheet], ref)) for sheet, refs in marks.items() if sheet in roots for ref in refs]
            used = {int(c.get("s") or 0) for _, c in targets}
            styles, mapping = _yellow_styles(zin.read("xl/styles.xml"), used)
            if mapping:
                patched["xl/styles.xml"] = styles
                for _, c in targets:
                    c.set("s", str(mapping[int(c.get("s") or 0)]))
        for sheet, root in roots.items():
            patched[paths[sheet]] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        drop_calc = "xl/calcChain.xml" in zin.namelist() and patched
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if drop_calc and item.filename == "xl/calcChain.xml":
                    continue  # Excel la reconstruit à l'ouverture
                data = patched.get(item.filename, zin.read(item.filename))
                if drop_calc and item.filename == "[Content_Types].xml":
                    data = data.replace(b'<Override PartName="/xl/calcChain.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml"/>', b"")
                if drop_calc and item.filename == "xl/_rels/workbook.xml.rels":
                    data = re.sub(rb'<Relationship [^>]*Target="calcChain\.xml"[^>]*/>', b"", data)
                zout.writestr(item, data)
    return sum(len(c) for c in by_sheet.values())


# --------------------------------------------------------------------------- Word
def _copy_format(src_run, dst_run) -> None:
    if src_run is None or src_run._r.rPr is None:
        return
    dst_run._r.insert(0, copy.deepcopy(src_run._r.rPr))


def _last_run(paragraph):
    runs = [r for r in paragraph.runs if r.text.strip()]
    return runs[-1] if runs else (paragraph.runs[-1] if paragraph.runs else None)


def _fill_paragraph(paragraph, text: str, model_run=None) -> None:
    for run in paragraph.runs[1:]:
        run._r.getparent().remove(run._r)
    if paragraph.runs:
        paragraph.runs[0].text = text
    else:
        run = paragraph.add_run(text)
        _copy_format(model_run, run)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
BOXES = "☐□▢⬜"


def _container(document, tgt):
    if "table" in tgt:
        return document.tables[tgt["table"]].rows[tgt["row"]].cells[tgt["col"]]._tc
    return document.paragraphs[tgt["paragraph"]]._p


def _write_sdt(sdt, text: str) -> None:
    """Contrôle de contenu : on remplace le texte affiché (liste déroulante, date, texte) en gardant la mise en forme."""
    content = sdt.find(f"{{{W}}}sdtContent")
    texts = list(content.iter(f"{{{W}}}t")) if content is not None else []
    if texts:
        texts[0].text = text
        for t in texts[1:]:
            t.text = ""
    elif content is not None:
        run = etree.SubElement(content, f"{{{W}}}r")
        etree.SubElement(run, f"{{{W}}}t").text = text
    pr = sdt.find(f"{{{W}}}sdtPr")
    if pr is not None:
        sh = pr.find(f"{{{W}}}showingPlcHdr")
        if sh is not None:
            pr.remove(sh)
            # le texte n'est plus un espace réservé : on retire son style gris
            for rpr in (content.iter(f"{{{W}}}rPr") if content is not None else []):
                for tag in ("color", "rStyle"):
                    el = rpr.find(f"{{{W}}}{tag}")
                    if el is not None and (tag == "color" or "Placeholder" in (el.get(f"{{{W}}}val") or "")):
                        rpr.remove(el)


def _tick(container, label: str, options: list[str]) -> bool:
    """Coche la case dont le libellé correspond (contrôle w14:checkbox ou glyphe ☐ → ☒)."""
    from .ontology import norm

    wanted = norm(label)
    sdts = [s for s in container.iter(f"{{{W}}}sdt") if s.find(f"{{{W}}}sdtPr/{{{W14}}}checkbox") is not None]
    if len(sdts) >= 2 and len(sdts) == len(options):
        for k, opt in enumerate(options):
            if norm(opt) == wanted:
                box = sdts[k].find(f"{{{W}}}sdtPr/{{{W14}}}checkbox/{{{W14}}}checked")
                if box is not None:
                    box.set(f"{{{W14}}}val", "1")
                for t in sdts[k].iter(f"{{{W}}}t"):
                    t.text = "☒"
                return True
        return False
    # Glyphes : la k-ième case du texte
    try:
        k = [norm(o) for o in options].index(wanted)
    except ValueError:
        return False
    seen = 0
    for t in container.iter(f"{{{W}}}t"):
        chars = list(t.text or "")
        for i, ch in enumerate(chars):
            if ch in BOXES:
                if seen == k:
                    chars[i] = "☒"
                    t.text = "".join(chars)
                    return True
                seen += 1
    return False


def _highlight_docx(document, tgt: dict[str, Any]) -> None:
    """Case réponse sans réponse : cellule ombrée en jaune, ou paragraphe surligné (« [à compléter] » s'il est vide)."""
    from docx.enum.text import WD_COLOR_INDEX
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    if tgt.get("table") is not None:
        cell = document.tables[tgt["table"]].rows[tgt["row"]].cells[tgt["col"]]
        pr = cell._tc.get_or_add_tcPr()
        for old in pr.findall(qn("w:shd")):
            pr.remove(old)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "FFFF00")
        pr.append(shd)
        return
    index = tgt.get("paragraph")
    if index is None or index >= len(document.paragraphs):
        return
    paragraph = document.paragraphs[index]
    if tgt.get("type") in {"next", "inline"} and not paragraph.text.strip() or tgt.get("type") == "inline":
        run = paragraph.add_run(" [à compléter]")
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        return
    for run in paragraph.runs:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def write_docx(source: Path, target: Path, answers: list[tuple], highlight: list[dict[str, Any]] | None = None) -> int:
    import docx

    document = docx.Document(str(source))
    paragraphs = document.paragraphs
    written = 0
    for tgt, value, *rest in answers:
        options = rest[0] if rest else []
        text = value.strftime("%d/%m/%Y") if isinstance(value, (date, datetime)) else str(value)
        kind = tgt["type"]
        if kind == "checkbox":
            if not _tick(_container(document, tgt), text, options or []):
                continue
        elif kind == "sdt":
            sdts = list(_container(document, tgt).iter(f"{{{W}}}sdt"))
            sdts = [s for s in sdts if s.find(f"{{{W}}}sdtPr/{{{W14}}}checkbox") is None]
            if not sdts:
                continue
            _write_sdt(sdts[tgt.get("sdt", 0)], text)
        elif kind == "cell":
            row = document.tables[tgt["table"]].rows[tgt["row"]]
            cell = row.cells[tgt["col"]]
            model = None
            for other in row.cells:
                if other._tc is not cell._tc and other.paragraphs and _last_run(other.paragraphs[0]):
                    model = _last_run(other.paragraphs[0])
                    break
            first = cell.paragraphs[0]
            for extra in cell.paragraphs[1:]:
                extra._p.getparent().remove(extra._p)
            _fill_paragraph(first, text, model)
        elif kind == "next":
            paragraph = paragraphs[tgt["paragraph"]]
            model = _last_run(paragraphs[tgt["paragraph"] - 1]) if tgt["paragraph"] else None
            _fill_paragraph(paragraph, text, model)
        elif kind == "inline":
            paragraph = paragraphs[tgt["paragraph"]]
            model = _last_run(paragraph)
            run = paragraph.add_run(" " + text)
            _copy_format(model, run)
            if run.font is not None:
                run.bold = False
        elif kind == "placeholder":
            paragraph = paragraphs[tgt["paragraph"]]
            pattern = re.compile(re.escape(tgt["placeholder"])) if tgt.get("placeholder") else re.compile(r"_{3,}|\.{4,}|…{2,}")
            done = False
            for run in paragraph.runs:
                if pattern.search(run.text):
                    run.text = pattern.sub(text, run.text, count=1)
                    done = True
                    break
            if not done:  # espace réservé coupé entre plusieurs runs
                full = paragraph.text
                new = pattern.sub(text, full, count=1)
                _fill_paragraph(paragraph, new, _last_run(paragraph))
        else:
            continue
        written += 1
    for tgt in highlight or []:
        try:
            _highlight_docx(document, tgt)
        except (IndexError, KeyError):
            continue
    document.save(str(target))
    return written


def write(source: Path, target: Path, answers: list[tuple], highlight: list[dict[str, Any]] | None = None) -> int:
    """highlight : cases réponse restées sans réponse, surlignées en jaune (option « réponses à demander »)."""
    if not answers and not highlight:
        shutil.copy2(source, target)
        return 0
    if source.suffix.lower() in {".xlsx", ".xlsm"}:
        return write_xlsx(source, target, answers, highlight)
    return write_docx(source, target, answers, highlight)
