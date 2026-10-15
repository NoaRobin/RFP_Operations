"""Accès au document Word ouvert (Windows, via COM) et lecture .docx hors ligne."""

import bisect

from .analyse import Cellule

WD_FIND_STOP = 0


def _nettoyer(texte_range):
    # Fin de paragraphe (\r) et fin de cellule de tableau (\x07)
    return texte_range.rstrip("\r\x07")


class DocumentWord:
    """Document actif de Word, piloté en local via COM (pas d'API externe)."""

    def __init__(self):
        try:
            import pythoncom  # noqa: F401
            import win32com.client
        except ImportError as e:  # pragma: no cover - Windows uniquement
            raise RuntimeError(
                "pywin32 n'est pas installé : lancer « pip install pywin32 »"
            ) from e
        try:
            self.app = win32com.client.GetActiveObject("Word.Application")
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Word n'est pas ouvert.") from e
        if self.app.Documents.Count == 0:
            raise RuntimeError("Aucun document ouvert dans Word.")
        self.doc = self.app.ActiveDocument
        self.nom = self.doc.FullName
        self._starts = []

    def paragraphes(self):
        textes, self._starts = [], []
        for p in self.doc.Paragraphs:
            r = p.Range
            self._starts.append(r.Start)
            textes.append(_nettoyer(r.Text))
        self._textes = textes
        return textes

    def tableaux(self):
        """Tableaux du document (y compris imbriqués) : liste de listes de Cellule."""
        res = []

        def paras_entre(debut, fin):
            g = bisect.bisect_left(self._starts, debut)
            d = bisect.bisect_left(self._starts, fin)
            return list(range(g, d))

        def visiter(tab):
            cellules = []
            for c in tab.Range.Cells:
                r = c.Range
                cellules.append(Cellule(c.RowIndex, c.ColumnIndex, paras_entre(r.Start, r.End)))
            res.append(cellules)
            for k in range(1, tab.Tables.Count + 1):
                visiter(tab.Tables(k))

        for k in range(1, self.doc.Tables.Count + 1):
            visiter(self.doc.Tables(k))
        return res

    def verifier_inchange(self):
        """Le document doit être le même et ne pas avoir été modifié depuis l'analyse."""
        if self.app.ActiveDocument.FullName != self.nom:
            return "Le document actif dans Word a changé depuis l'analyse."
        if self.doc.Paragraphs.Count != len(self._textes):
            return "Le nombre de paragraphes a changé depuis l'analyse."
        return None

    def debut_edition(self):
        self.suivi_initial = self.doc.TrackRevisions
        self.doc.TrackRevisions = False
        try:
            self.app.UndoRecord.StartCustomRecord("Merge codes Qvidian")
        except Exception:
            pass
        self.app.ScreenUpdating = False

    def fin_edition(self):
        self.app.ScreenUpdating = True
        try:
            self.app.UndoRecord.EndCustomRecord()
        except Exception:
            pass
        self.doc.TrackRevisions = self.suivi_initial

    def remplacer(self, idx, debut, fin, attendu, nouveau, contexte, decalage):
        """Remplace `attendu` par `nouveau` dans le paragraphe `idx`.

        Retourne (ok, message). Rien n'est modifié si la vérification échoue.
        """
        para = self.doc.Paragraphs(idx + 1).Range
        if _nettoyer(para.Text) != self._textes[idx]:
            return False, "Paragraphe modifié depuis l'analyse"
        pos = None
        # 1) position directe
        r = self.doc.Range(para.Start + debut, para.Start + fin)
        if r.Text == attendu and self._contexte_ok(para.Start + debut, contexte, decalage):
            pos = para.Start + debut
        elif len(contexte) >= 12:
            # 2) recherche du contexte exact dans le paragraphe : il doit y être
            #    présent une seule fois, sinon on ne touche à rien.
            trouve = self._chercher(para.Start, para.End, contexte)
            if trouve and not self._chercher(trouve[0] + 1, para.End, contexte):
                pos = trouve[0] + decalage
        if pos is None:
            return False, "Passage introuvable dans Word à l'endroit attendu"
        cible = self.doc.Range(pos, pos + len(attendu))
        if cible.Text != attendu:
            return False, f"Vérification avant insertion échouée (trouvé « {cible.Text} »)"
        cible.Text = nouveau
        controle = self.doc.Range(pos, pos + len(nouveau)).Text
        if controle != nouveau:
            return False, f"Vérification après insertion échouée (lu « {controle} »)"
        # texte de référence mis à jour pour les autres insertions de ce paragraphe
        self._textes[idx] = _nettoyer(self.doc.Paragraphs(idx + 1).Range.Text)
        return True, "OK"

    def _chercher(self, debut, fin, texte):
        r = self.doc.Range(debut, fin)
        f = r.Find
        f.ClearFormatting()
        ok = f.Execute(
            FindText=texte[:250].replace("^", "^^").replace("\t", "^t").replace("\x0b", "^l"),
            MatchCase=True,
            MatchWholeWord=False,
            MatchWildcards=False,
            MatchSoundsLike=False,
            MatchAllWordForms=False,
            Forward=True,
            Wrap=WD_FIND_STOP,
            Format=False,
        )
        if ok and r.Start >= debut and r.End <= fin and r.Text == texte:
            return r.Start, r.End
        return None

    def _contexte_ok(self, pos, contexte, decalage):
        d = pos - decalage
        return self.doc.Range(d, d + len(contexte)).Text == contexte


def lire_docx(chemin):
    """Lecture d'un .docx sans Word (mode analyse / tests) : (paragraphes, tableaux).

    Les paragraphes sont dans l'ordre du document, comme dans Word, y compris
    ceux des cellules de tableaux.
    """
    import docx
    from docx.oxml.ns import qn

    d = docx.Document(chemin)
    body = d.element.body
    elements = list(body.iter(qn("w:p")))
    index = {el: i for i, el in enumerate(elements)}
    paras = []
    for p in elements:
        morceaux = []
        for el in p.iter():
            if el.tag == qn("w:t"):
                morceaux.append(el.text or "")
            elif el.tag == qn("w:tab"):
                morceaux.append("\t")
            elif el.tag in (qn("w:br"), qn("w:cr")):
                morceaux.append("\x0b")
        paras.append("".join(morceaux))
    tableaux = []
    for tbl in body.iter(qn("w:tbl")):
        cellules = []
        for r, tr in enumerate(tbl.findall(qn("w:tr")), start=1):
            for c, tc in enumerate(tr.findall(qn("w:tc")), start=1):
                cellules.append(Cellule(r, c, sorted(index[p] for p in tc.iter(qn("w:p")))))
        tableaux.append(cellules)
    return paras, tableaux


def paragraphes_docx(chemin):
    return lire_docx(chemin)[0]
