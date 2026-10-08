"""Lecture du fichier Excel des années d'expérience (onglet « Data »)."""

import datetime
import re
from dataclasses import dataclass

import openpyxl

from .texte import normaliser

INDUSTRIE = "INDUSTRIE"
SOCIETE = "SOCIETE"
MOYENNE = "MOYENNE"

LIBELLE_TYPE = {
    INDUSTRIE: "Expérience industrie",
    SOCIETE: "Expérience société",
    MOYENNE: "Expérience moyenne équipe",
}

# Équipes et rôles utilisés pour les codes d'expérience moyenne.
TOTAL, GERANTS, ANALYSTES = "total", "gérants", "analystes"


def _annee(valeur):
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, (datetime.date, datetime.datetime)):
        return valeur.year
    if isinstance(valeur, (int, float)):
        return int(valeur)
    m = re.search(r"(19|20)\d\d", str(valeur))
    return int(m.group(0)) if m else None


def _code(valeur):
    if valeur is None:
        return None
    code = str(valeur).strip()
    return code or None


def code_incomplet(code):
    return not code or code.endswith("_")


_RE_FORMULE = re.compile(r"^=[\s()+\-\d.HJ]*$")


def evaluer_annees(formule, annee_ref, annee_h, annee_j, ligne):
    """Évalue la colonne « Nombre d'années » de l'Excel (ex. =(YEAR(TODAY())-H39)-4).

    Retourne None si la formule n'est pas une simple soustraction d'années.
    """
    if isinstance(formule, (int, float)):
        return int(formule)
    if not isinstance(formule, str):
        return None
    f = formule.replace(" ", "").upper().replace("YEAR(TODAY())", str(annee_ref))
    for col, val in (("H", annee_h), ("J", annee_j)):
        if f"{col}{ligne}" in f:
            if val is None:
                return None
            f = f.replace(f"{col}{ligne}", str(val))
    if not _RE_FORMULE.match(f) or re.search(r"[HJ]", f):
        return None
    try:
        return int(eval(f[1:], {"__builtins__": {}}, {}))  # chiffres, + - ( ) uniquement
    except Exception:
        return None


@dataclass
class Personne:
    nom: str
    code_industrie: str
    code_societe: str
    annee_industrie: int
    annee_societe: int
    ligne: int
    equipe: str = None
    fonction: str = None
    formule_industrie: object = None
    formule_societe: object = None

    def code(self, type_):
        return self.code_industrie if type_ == INDUSTRIE else self.code_societe

    def annees(self, type_, annee_ref):
        """Nombre d'années, calculé comme dans l'Excel (formule de la colonne I ou K)."""
        annee = self.annee_industrie if type_ == INDUSTRIE else self.annee_societe
        formule = self.formule_industrie if type_ == INDUSTRIE else self.formule_societe
        if formule is not None:
            v = evaluer_annees(formule, annee_ref, self.annee_industrie, self.annee_societe, self.ligne)
            if v is not None:
                return v
        return None if annee is None else annee_ref - annee


@dataclass
class CodeEquipe:
    libelle: str
    code: str
    equipe: str
    role: str
    ligne: int


def equipe_du_libelle(libelle):
    """Équipe (au sens des codes d'expérience moyenne) d'un libellé de l'Excel."""
    n = normaliser(libelle or "")
    if "oblig" in n:
        equipe = "Obligataire"
    elif "europ" in n:
        equipe = "Actions européennes"
    elif "themat" in n:
        equipe = "Actions thématiques"
    elif "valor" in n:
        equipe = "Valor"
    elif "multi" in n:
        equipe = "Multigestion"
    else:
        equipe = None
    if "total" in n:
        role = TOTAL
    elif "analyst" in n:
        role = ANALYSTES
    elif "gerant" in n:
        role = GERANTS
    else:
        role = TOTAL
    return equipe, role


class Referentiel:
    def __init__(self, personnes, codes_equipe, annee_ref, anomalies):
        self.personnes = personnes
        self.codes_equipe = codes_equipe
        self.annee_ref = annee_ref
        self.anomalies = anomalies
        self.codes = {}
        for p in personnes:
            for t in (INDUSTRIE, SOCIETE):
                c = p.code(t)
                if not code_incomplet(c):
                    self.codes[c] = (t, p)
        for ce in codes_equipe:
            self.codes[ce.code] = (MOYENNE, ce)

    def code_equipe(self, equipe, role):
        for ce in self.codes_equipe:
            if ce.equipe == equipe and ce.role == role:
                return ce
        return None

    def decrire_code(self, code):
        """(type, libellé, valeur) pour un code saisi à la main, ou None."""
        if code not in self.codes:
            return None
        type_, obj = self.codes[code]
        if type_ == MOYENNE:
            return type_, obj.libelle, None, None
        return type_, obj.nom, obj.annees(type_, self.annee_ref), obj

    @classmethod
    def charger(cls, chemin, annee_ref=None, onglet="Data"):
        annee_ref = annee_ref or datetime.date.today().year
        wb = openpyxl.load_workbook(chemin, data_only=False, read_only=True)
        if onglet not in wb.sheetnames:
            raise ValueError(f"Onglet « {onglet} » introuvable dans {chemin}")
        lignes = list(wb[onglet].iter_rows(values_only=True))
        wb.close()

        personnes, codes_equipe, anomalies = [], [], []
        section = None
        for num, row in enumerate(lignes, start=1):
            if num == 1:
                continue
            row = list(row) + [None] * 11
            nom, col_b, col_c = row[0], row[1], row[2]
            lib_b = normaliser(str(col_b)) if col_b else ""
            if nom is None and col_b and col_c is None:
                if "experience moyenne" in lib_b:
                    section = MOYENNE
                else:
                    section = None
                continue
            if nom:
                nom = " ".join(str(nom).split())
                p = Personne(
                    nom=nom,
                    code_industrie=_code(col_b),
                    code_societe=_code(col_c),
                    annee_industrie=_annee(row[7]),
                    annee_societe=_annee(row[9]),
                    ligne=num,
                    equipe=(str(row[3]).strip() if row[3] else None),
                    fonction=(str(row[4]).strip() if row[4] else None),
                    formule_industrie=row[8],
                    formule_societe=row[10],
                )
                personnes.append(p)
                for t in (INDUSTRIE, SOCIETE):
                    if code_incomplet(p.code(t)):
                        anomalies.append(
                            f"Ligne {num} – {nom} : code {LIBELLE_TYPE[t].lower()} incomplet "
                            f"({p.code(t)!r}) – ne sera jamais inséré"
                        )
                if p.annee_industrie is None:
                    anomalies.append(f"Ligne {num} – {nom} : date d'entrée dans l'industrie manquante")
                if p.annee_societe is None:
                    anomalies.append(f"Ligne {num} – {nom} : date d'entrée dans la société manquante")
                for t, f in ((INDUSTRIE, row[8]), (SOCIETE, row[10])):
                    std = f"=YEAR(TODAY())-{'H' if t == INDUSTRIE else 'J'}{num}"
                    if isinstance(f, str) and f.replace(" ", "").upper() != std:
                        v = p.annees(t, annee_ref)
                        anomalies.append(
                            f"Ligne {num} – {nom} : formule particulière {f} "
                            f"({LIBELLE_TYPE[t].lower()} = {v} an(s) en {annee_ref})"
                        )
            elif section == MOYENNE and col_b and col_c:
                code = _code(col_c)
                equipe, role = equipe_du_libelle(str(col_b))
                if equipe is None:
                    anomalies.append(f"Ligne {num} – équipe non reconnue pour « {col_b} »")
                    continue
                codes_equipe.append(CodeEquipe(str(col_b).strip(), code, equipe, role, num))

        vus = {}
        for p in personnes:
            for t in (INDUSTRIE, SOCIETE):
                c = p.code(t)
                if code_incomplet(c):
                    continue
                if c in vus:
                    anomalies.append(f"Code {c} en double (lignes {vus[c]} et {p.ligne})")
                vus[c] = p.ligne
        for ce in codes_equipe:
            if " " in ce.code:
                anomalies.append(
                    f"Ligne {ce.ligne} – le code « {ce.code} » contient un espace : "
                    "vérifier qu'il est identique dans Qvidian"
                )
        if not personnes:
            raise ValueError("Aucun collaborateur trouvé dans l'onglet Data")
        return cls(personnes, codes_equipe, annee_ref, anomalies)
