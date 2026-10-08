"""Compte rendu Excel cumulatif (un lot = un document Word)."""

import datetime
import os

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ONGLETS = {
    "Textes": ["Lot", "Date", "Document Word", "ID texte", "Statut", "Nb merge codes insérés",
               "Nb passages détectés", "Merge codes déjà présents", "Détail", "Titre"],
    "Passages": ["Lot", "Date", "ID texte", "Statut", "Type", "Personne / équipe", "Valeur dans le texte",
                 "Valeur Excel", "Merge code", "Phrase", "Remarques"],
    "0 an - à insérer 2027": ["Lot", "Date", "ID texte", "Personne", "Type", "Merge code à insérer", "Phrase"],
    "À vérifier": ["Lot", "Date", "ID texte", "Motif", "Phrase"],
}
LARGEURS = {"Titre": 50, "Phrase": 90, "Détail": 60, "Remarques": 50, "Document Word": 40, "Motif": 45,
            "Personne / équipe": 32, "Statut": 34, "Merge code": 26, "Merge code à insérer": 26}

COULEURS = {
    "Merge code(s) inséré(s)": "C6EFCE",
    "Remplacé": "C6EFCE",
    "Aucun passage à remplacer": "EDEDED",
    "À vérifier": "FFEB9C",
    "0 an – à insérer en 2027": "BDD7EE",
}

# Statuts
REMPLACE = "Remplacé"
IGNORE = "Ignoré (décision utilisateur)"
ZERO = "0 an – à insérer en 2027"
ECHEC = "Échec insertion – à faire à la main"
CODE_INCOMPLET = "Code incomplet dans l'Excel – non inséré"
ANALYSE = "Proposé (mode analyse, rien modifié)"
SANS_VALEUR = "Date d'entrée absente de l'Excel – non inséré"


class Rapport:
    def __init__(self, chemin):
        self.chemin = chemin
        if os.path.exists(chemin):
            self.wb = openpyxl.load_workbook(chemin)
            for nom, entetes in ONGLETS.items():
                if nom not in self.wb.sheetnames:
                    self._creer(nom, entetes)
                else:  # compte rendu d'une version précédente : colonnes ajoutées à la fin
                    ws = self.wb[nom]
                    for i, e in enumerate(entetes, start=1):
                        if ws.cell(row=1, column=i).value is None:
                            c = ws.cell(row=1, column=i, value=e)
                            c.font = Font(bold=True, color="FFFFFF")
                            c.fill = PatternFill("solid", fgColor="1F3864")
                            ws.column_dimensions[get_column_letter(i)].width = LARGEURS.get(e, 16)
        else:
            self.wb = openpyxl.Workbook()
            self.wb.remove(self.wb.active)
            for nom, entetes in ONGLETS.items():
                self._creer(nom, entetes)
        ws = self.wb["Textes"]
        lots = [r[0] for r in ws.iter_rows(min_row=2, values_only=True) if isinstance(r[0], int)]
        self.lot = (max(lots) if lots else 0) + 1
        self.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    def _creer(self, nom, entetes):
        ws = self.wb.create_sheet(nom)
        ws.append(entetes)
        for i, e in enumerate(entetes, start=1):
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
            c.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[get_column_letter(i)].width = LARGEURS.get(e, 16)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(entetes))}1"

    def _ajouter(self, onglet, valeurs, statut=None):
        ws = self.wb[onglet]
        ws.append([self.lot, self.date] + list(valeurs))
        ligne = ws.max_row
        for c in ws[ligne]:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if statut in COULEURS:
            ws.cell(row=ligne, column=ONGLETS[onglet].index("Statut") + 1).fill = PatternFill(
                "solid", fgColor=COULEURS[statut]
            )
        ws.auto_filter.ref = f"A1:{get_column_letter(len(ONGLETS[onglet]))}{ligne}"

    def texte(self, document, texte_id, statut, nb_inseres, nb_detectes, codes_existants, detail, titre=""):
        self._ajouter("Textes", [document, texte_id, statut, nb_inseres, nb_detectes,
                                 ", ".join(codes_existants), detail, titre], statut)

    def passage(self, texte_id, statut, type_, qui, valeur_texte, valeur_excel, code, phrase, remarques):
        self._ajouter("Passages", [texte_id, statut, type_, qui, valeur_texte, valeur_excel,
                                   f"<<{code}>>" if code else "", phrase, remarques], statut)

    def zero(self, texte_id, personne, type_, code, phrase):
        self._ajouter("0 an - à insérer 2027", [texte_id, personne, type_, f"<<{code}>>", phrase])

    def a_verifier(self, texte_id, motif, phrase):
        self._ajouter("À vérifier", [texte_id, motif, phrase])

    def enregistrer(self):
        """Enregistre ; si le fichier est ouvert dans Excel, enregistre une copie horodatée."""
        try:
            self.wb.save(self.chemin)
            return self.chemin
        except PermissionError:
            base, ext = os.path.splitext(self.chemin)
            alt = f"{base}_{datetime.datetime.now():%Y%m%d_%H%M%S}{ext}"
            self.wb.save(alt)
            return alt
