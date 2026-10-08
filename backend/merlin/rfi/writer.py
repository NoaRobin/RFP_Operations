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


def _set_cell(sheet_root, ref: str, value: Any) -> None:
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
        value = value.strftime("%d/%m/%Y")  # texte : aucun style de date à créer
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS}}}is")
    t = etree.SubElement(is_el, f"{{{NS}}}t")
    t.text = str(value)
    if t.text != t.text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def write_xlsx(source: Path, target: Path, answers: list[tuple[dict, Any]]) -> int:
    by_sheet: dict[str, list[tuple[str, Any]]] = {}
    for tgt, value in answers:
        by_sheet.setdefault(tgt["sheet"], []).append((tgt["cell"], value))
    with zipfile.ZipFile(source) as zin:
        paths = _sheet_paths(zin)
        patched: dict[str, bytes] = {}
        for sheet, cells in by_sheet.items():
            path = paths[sheet]
            root = etree.fromstring(zin.read(path))
            for ref, value in cells:
                _set_cell(root, ref, value)
            patched[path] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
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


def write_docx(source: Path, target: Path, answers: list[tuple[dict, Any]]) -> int:
    import docx

    document = docx.Document(str(source))
    paragraphs = document.paragraphs
    written = 0
    for tgt, value in answers:
        text = value.strftime("%d/%m/%Y") if isinstance(value, (date, datetime)) else str(value)
        kind = tgt["type"]
        if kind == "cell":
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
            pattern = re.compile(r"_{3,}|\.{4,}|…{2,}|\[\s*(?:à compléter|a completer|à remplir|a remplir|réponse|reponse|answer|to be completed|x+)\s*\]", re.I)
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
    document.save(str(target))
    return written


def write(source: Path, target: Path, answers: list[tuple[dict, Any]]) -> int:
    if not answers:
        shutil.copy2(source, target)
        return 0
    if source.suffix.lower() in {".xlsx", ".xlsm"}:
        return write_xlsx(source, target, answers)
    return write_docx(source, target, answers)
