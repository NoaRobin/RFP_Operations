"""Merge codes Qvidian dans Grimoire : le bot `mergebot` (inchangé, backend/vendor) piloté depuis l'interface.

Différences avec l'usage en terminal :
- le Word est déposé dans l'application (pas besoin de Word ni de pywin32) : insertion via python-docx ;
- les décisions (valider, choisir une autre proposition, ignorer, saisir un code) se prennent à l'écran ;
- le référentiel « Années d'expérience » est déposé une fois et conservé localement (jamais versionné).
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

VENDOR = Path(__file__).resolve().parents[2] / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

import bot_merge_codes as bot  # noqa: E402  (code du bot, non modifié)
from mergebot import rapport as R  # noqa: E402
from mergebot.analyse import Analyseur  # noqa: E402
from mergebot.referentiel import LIBELLE_TYPE, MOYENNE, Referentiel, code_incomplet  # noqa: E402
from mergebot.word import lire_docx  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocxSource:
    """Même interface que `mergebot.word.DocumentWord`, sur un fichier .docx (python-docx / lxml)."""

    def __init__(self, path: Path):
        import docx

        self.path = path
        self.document = docx.Document(str(path))
        self.elements = list(self.document.element.body.iter(f"{W}p"))

    def _chars(self, p):
        """Liste (élément w:t ou None, index) par caractère, alignée sur le texte de `lire_docx`."""
        chars = []
        for el in p.iter():
            if el.tag == f"{W}t":
                chars.extend((el, i) for i in range(len(el.text or "")))
            elif el.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
                chars.append((None, 0))
        return chars

    def _text(self, p) -> str:
        out = []
        for el in p.iter():
            if el.tag == f"{W}t":
                out.append(el.text or "")
            elif el.tag == f"{W}tab":
                out.append("\t")
            elif el.tag in (f"{W}br", f"{W}cr"):
                out.append("\x0b")
        return "".join(out)

    def verifier_inchange(self):
        return None

    def debut_edition(self):
        return None

    def fin_edition(self):
        return None

    def remplacer(self, idx, debut, fin, attendu, nouveau, contexte, decalage):
        p = self.elements[idx]
        texte = self._text(p)
        if texte[debut:fin] != attendu:
            return False, f"texte inattendu à cet endroit ({texte[debut:fin]!r} au lieu de {attendu!r})"
        if texte[max(0, debut - decalage): max(0, debut - decalage) + len(contexte)] != contexte:
            return False, "contexte différent de celui analysé"
        chars = self._chars(p)[debut:fin]
        if not chars or any(el is None for el, _ in chars):
            return False, "le nombre est coupé par une tabulation ou un saut de ligne"
        first_el, first_i = chars[0]
        by_el: dict[Any, list[int]] = {}
        for el, i in chars:
            by_el.setdefault(el, []).append(i)
        for el, positions in by_el.items():
            t = el.text or ""
            start, end = min(positions), max(positions) + 1
            el.text = t[:start] + (nouveau if el is first_el else "") + t[end:]
            el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        if nouveau not in self._text(p):
            return False, "relecture après insertion : code absent"
        return True, ""

    def save(self, target: Path) -> None:
        self.document.save(str(target))


# --------------------------------------------------------------------------- stockage
class MergeStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    @property
    def referentiel_path(self) -> Path:
        return self.root / "referentiel.xlsx"

    def save_referentiel(self, content: bytes, filename: str) -> dict[str, Any]:
        tmp = self.root / "referentiel.tmp.xlsx"
        tmp.write_bytes(content)
        ref = Referentiel.charger(str(tmp))  # valide le fichier avant de remplacer l'actuel
        tmp.replace(self.referentiel_path)
        (self.root / "referentiel.json").write_text(json.dumps(
            {"filename": filename, "uploaded_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
        return describe_referentiel(ref)

    def referentiel(self) -> Referentiel | None:
        return Referentiel.charger(str(self.referentiel_path)) if self.referentiel_path.exists() else None

    def referentiel_meta(self) -> dict[str, Any] | None:
        path = self.root / "referentiel.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def folder(self, doc_id: str) -> Path:
        if not re.fullmatch(r"mc_[a-f0-9]{12}", doc_id):
            raise FileNotFoundError(doc_id)
        path = self.root / "documents" / doc_id
        if not path.exists():
            raise FileNotFoundError(doc_id)
        return path

    def save_document(self, filename: str, content: bytes, user: str) -> dict[str, Any]:
        if Path(filename).suffix.lower() != ".docx":
            raise ValueError(Path(filename).suffix)
        doc_id = f"mc_{uuid.uuid4().hex[:12]}"
        folder = self.root / "documents" / doc_id
        folder.mkdir(parents=True)
        (folder / "original.docx").write_bytes(content)
        meta = {"id": doc_id, "filename": Path(filename).name, "user": user, "uploaded_at": datetime.now().isoformat(timespec="seconds")}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return meta

    def meta(self, doc_id: str) -> dict[str, Any]:
        return json.loads((self.folder(doc_id) / "meta.json").read_text(encoding="utf-8"))


def describe_referentiel(ref: Referentiel) -> dict[str, Any]:
    return {"personnes": len(ref.personnes), "codes_equipe": len(ref.codes_equipe), "annee": ref.annee_ref,
            "anomalies": ref.anomalies[:50], "nb_anomalies": len(ref.anomalies)}


# --------------------------------------------------------------------------- analyse & application
def _proposition(p) -> dict[str, Any]:
    return {"code": p.code, "merge_code": bot.merge_code(p.code), "libelle": p.libelle, "type": LIBELLE_TYPE[p.type],
            "valeur_excel": p.valeur_excel, "incomplet": code_incomplet(p.code),
            "statut": bot.statut_proposition(p) or "À insérer"}


def analyse(store: MergeStore, doc_id: str) -> dict[str, Any]:
    ref = store.referentiel()
    if ref is None:
        raise LookupError("referentiel")
    paragraphes, tableaux = lire_docx(str(store.folder(doc_id) / "original.docx"))
    textes = Analyseur(ref).analyser(paragraphes, tableaux)
    candidats = []
    for t in textes:
        for c in t.candidats:
            d, f = c.phrase
            p = c.paragraphe
            candidats.append({
                "index": len(candidats), "texte_id": c.texte_id, "titre": t.titre, "type": LIBELLE_TYPE[c.type_detecte],
                "sur": c.sur, "valeur_texte": c.valeur_texte, "cadre": c.cadre, "remarques": list(c.remarques),
                "avant": p[d:c.debut].lstrip(), "nombre": p[c.debut:c.fin], "apres": p[c.fin:f].rstrip(),
                "propositions": [_proposition(x) for x in c.propositions],
            })
    signalements = [{"texte_id": t.id, "motif": s.motif, "extrait": s.extrait} for t in textes for s in t.signalements]
    return {**store.meta(doc_id), "textes": len(textes), "ids": [t.id for t in textes], "candidats": candidats,
            "signalements": signalements, "referentiel": describe_referentiel(ref)}


def appliquer(store: MergeStore, doc_id: str, decisions: list[dict[str, Any]], user: str) -> dict[str, Any]:
    """decisions[i] = {"choix": "proposition"|"ignorer"|"code", "proposition": n (1..), "code": "XPSDG_…"}."""
    ref = store.referentiel()
    if ref is None:
        raise LookupError("referentiel")
    folder = store.folder(doc_id)
    meta = store.meta(doc_id)
    source = DocxSource(folder / "original.docx")
    paragraphes, tableaux = lire_docx(str(folder / "original.docx"))
    reponses: list[str] = []
    for d in decisions:
        choix = d.get("choix")
        if choix == "ignorer":
            reponses.append("n")
        elif choix == "code":
            reponses.append(str(d.get("code", "")).strip().strip("<>"))
        else:
            reponses.append(str(int(d.get("proposition") or 1)))
    reponses.append("")  # confirmation finale « Insérer N merge code(s) ? »
    flux = iter(reponses)

    def entree(_prompt: str = "") -> str:
        try:
            return next(flux)
        except StopIteration:
            return "n"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = re.sub(r"[^\w\-]+", "_", Path(meta["filename"]).stem).strip("_") or "export"
    rapport_path = folder / f"compte_rendu_{stem}_{stamp}.xlsx"
    rapport = R.Rapport(str(rapport_path))
    journal = io.StringIO()
    with contextlib.redirect_stdout(journal):
        decisions_bot = bot.traiter_paragraphes(paragraphes, source, meta["filename"], Analyseur(ref), ref,
                                                "validation", rapport, entree, tableaux)
    rapport.enregistrer()
    sortie = folder / f"{stem}_merge_codes_{stamp}.docx"
    source.save(sortie)
    statuts: dict[str, int] = {}
    for _, _, statut in decisions_bot or []:
        statuts[statut] = statuts.get(statut, 0) + 1
    return {"document": sortie.name, "rapport": rapport_path.name, "statuts": statuts,
            "inseres": statuts.get(R.REMPLACE, 0), "journal": journal.getvalue()[-6000:]}


def fichier(store: MergeStore, doc_id: str, name: str) -> Path:
    folder = store.folder(doc_id)
    path = (folder / name).resolve()
    if path.parent != folder.resolve() or not path.exists() or path.name.startswith(("original", "meta")):
        raise FileNotFoundError(name)
    return path


# --------------------------------------------------------------------------- démo (fictive)
def demo_referentiel() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Nom", "Merge code (Exp Industrie)", "Merge code (Exp Société)", "Equipe", "Fonction", "Fonction détaillée",
               "Titre", "Date d'entrée dans l'industrie", "Nombre d'années d'expérience", "Date d'entrée dans la société",
               "Nombre d'années dans la société"])
    people = [("Viviane Lac", "XPINDUS_VLac", "XPSDG_VLac", "Obligataire", "Gérant", 2001, 2012),
              ("Arthur Pendragon", "XPINDUS_APendragon", "XPSDG_APendragon", "Obligataire", "Analyste", 2015, 2019),
              ("Morgane Fay", "XPINDUS_MFay", "XPSDG_MFay", "Actions Européennes", "Gérant", 1998, 2008),
              ("Perceval Galles", "XPINDUS_PGalles", "XPSDG_", "Actions Européennes", "Analyste", 2024, 2026)]
    for i, (nom, ci, cs, eq, fn, ai, asoc) in enumerate(people, start=2):
        ws.append([nom, ci, cs, eq, fn, fn, fn, ai, f"=YEAR(TODAY())-H{i}", asoc, f"=YEAR(TODAY())-J{i}"])
    ws.append([])
    ws.append([None, "Expérience moyenne par équipe", None])
    ws.append([None, "Equipe obligataire (total)", "XPMOYAllTeamTaux"])
    ws.append([None, "Analystes crédit", "XPMOYAnalystesTaux"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def demo_export() -> bytes:
    import docx

    year = datetime.now().year
    d = docx.Document()
    d.add_paragraph("Content ID: 1968")
    d.add_paragraph("Title: Équipe de gestion obligataire (démonstration, données fictives)")
    d.add_paragraph(f"Viviane Lac, gérante, dispose de {year - 2001} ans d'expérience dans l'industrie, "
                    f"dont {year - 2012} au sein de R&Co AM.")
    d.add_paragraph(f"L'équipe obligataire compte en moyenne 18 ans d'expérience.")
    d.add_paragraph("Content ID: 2045")
    d.add_paragraph("Title: Portfolio management team (demo)")
    d.add_paragraph(f"Morgane Fay has {year - 1998} years of experience in the asset management industry.")
    t = d.add_table(rows=2, cols=3)
    t.rows[0].cells[0].text = "Nom"
    t.rows[0].cells[1].text = "Expérience dans l'industrie financière"
    t.rows[0].cells[2].text = "Expérience dans la société"
    t.rows[1].cells[0].text = "Arthur Pendragon"
    t.rows[1].cells[1].text = f"{year - 2015} ans"
    t.rows[1].cells[2].text = f"{year - 2019} ans"
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()


__all__ = ["MergeStore", "analyse", "appliquer", "fichier", "demo_referentiel", "demo_export", "MOYENNE", "shutil"]
