"""Détection des passages « années d'expérience » et proposition de merge codes.

Le principe est volontairement prudent :
- seules des formulations explicites d'années d'expérience sont proposées
  (phrases en français ou en anglais, et cellules de tableaux dont l'en-tête
  parle d'expérience) ;
- chaque proposition indique si elle est « sûre » (personne / équipe et type
  identifiés sans ambiguïté) ou non ;
- tout le reste (formulation non reconnue, nombre écrit en lettres, année
  d'arrivée…) est signalé dans le compte rendu sans être modifié ;
- les merge codes déjà présents sont contrôlés : si le bot aurait proposé un
  autre code, c'est signalé.
"""

import re
from dataclasses import dataclass, field

from .referentiel import (
    ANALYSTES,
    GERANTS,
    INDUSTRIE,
    MOYENNE,
    SOCIETE,
    TOTAL,
    code_incomplet,
    equipe_du_libelle,
)
from .texte import normaliser, phrases

# --------------------------------------------------------------------------
# Identifiants de textes
# --------------------------------------------------------------------------

GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

# Un paragraphe est un début de texte s'il correspond à l'un de ces motifs.
# Le groupe nommé « id » est l'identifiant reporté dans le compte rendu.
# Export Qvidian : « Content ID: 1968 ↵ Title: … »
MOTIFS_ID_DEFAUT = [
    r"^\s*content\s*id\s*[:#=]?\s*(?P<id>\d+)",
    r"^\s*(?:id|identifiant)\s*(?:du\s+texte\s*)?[:#=\-]?\s*(?P<id>[\w\-]{3,})\s*$",
    r"^\s*(?:id|identifiant)\s*[:#=]\s*(?P<id>[\w\-]{3,})\b",
    r"^\s*(?P<id>" + GUID + r")\s*$",
    r"^\s*(?P<id>\d{4,})\s*$",
]
RE_TITRE = re.compile(r"title\s*:\s*([^\x0b\r\n]+)", re.IGNORECASE)

SANS_ID = "(avant le premier ID)"


def compiler_motifs_id(motifs=None):
    return [re.compile(m, re.IGNORECASE) for m in (motifs or MOTIFS_ID_DEFAUT)]


def trouver_id(paragraphe, motifs):
    if "<<" in paragraphe:  # balises Qvidian (<<GALLERY: guid ...>>) : jamais un ID
        return None
    for m in motifs:
        r = m.search(paragraphe)
        if r:
            return r.group("id")
    return None


@dataclass
class Texte:
    id: str
    para_debut: int  # index du paragraphe portant l'ID (ou 0)
    para_fin: int  # exclu
    titre: str = ""
    candidats: list = field(default_factory=list)
    signalements: list = field(default_factory=list)
    codes_existants: list = field(default_factory=list)


def segmenter(paragraphes, motifs):
    textes = []
    courant = Texte(SANS_ID, 0, 0)
    for i, p in enumerate(paragraphes):
        ident = trouver_id(p, motifs)
        if ident is not None:
            courant.para_fin = i
            if courant.id != SANS_ID or any(x.strip() for x in paragraphes[courant.para_debut:i]):
                textes.append(courant)
            m = RE_TITRE.search(p)
            courant = Texte(ident, i, i, titre=m.group(1).strip() if m else "")
    courant.para_fin = len(paragraphes)
    if courant.id != SANS_ID or any(x.strip() for x in paragraphes[courant.para_debut:]):
        textes.append(courant)
    return textes


# --------------------------------------------------------------------------
# Tableaux
# --------------------------------------------------------------------------


@dataclass
class Cellule:
    ligne: int
    colonne: int
    paras: list  # index des paragraphes de la cellule


# --------------------------------------------------------------------------
# Motifs de détection (appliqués au texte normalisé : minuscules, sans accent)
# --------------------------------------------------------------------------

N = r"(?P<n>\d{1,2})(?![\d,.]\d)"
Q = (r"(?:(?:plus|pres)\s+de\s+|environ\s+|over\s+|more\s+than\s+|nearly\s+|almost\s+|around\s+|"
     r"about\s+|some\s+|approximately\s+|close\s+to\s+)?")
ANS = r"\s*(?:ans|annees|an|years|year|yrs)\b"
EXP = r"(?:d'\s*experience|of\s+(?:[a-z\-]+\s+){0,2}experience|(?:[a-z\-]+\s+){0,1}experience)"

# (type, motif, temporel) — « temporel » : « depuis N ans » / « for N years »,
# retenu seulement si un collaborateur ou la société est cité dans la phrase.
MOTIFS = [
    # --- Expérience moyenne d'équipe ---
    (MOYENNE, r"experience\s+moyenne\s+(?:de\s+|d'\s*)?" + Q + N + ANS, False),
    (MOYENNE, N + ANS + r"\s+d'\s*experience\s+(?:en\s+)?moyenne", False),
    (MOYENNE, r"(?:en\s+)?moyenne\s+(?:de\s+|d'\s*)?" + Q + N + ANS + r"\s+d'\s*experience", False),
    (MOYENNE, r"average\s+(?:[a-z\-]+\s+){0,2}experience\s+(?:of\s+)?" + Q + N + ANS, False),
    (MOYENNE, r"average\s+(?:of\s+)?" + Q + N + ANS + r"'?\s+(?:of\s+)?(?:[a-z\-]+\s+){0,2}experience", False),
    (MOYENNE, r"on\s+average\s+" + Q + N + ANS, False),
    (MOYENNE, N + ANS + r"'?\s+(?:of\s+)?(?:[a-z\-]+\s+){0,2}experience\s+on\s+average", False),
    # --- Ancienneté dans la société ---
    (SOCIETE, r"(?:dont|including|of\s+which)\s+" + Q + N + r"(?:" + ANS + r")?\s+(?:au\s+sein|chez|a\s+la\s+soc|"
              r"dans\s+la\s+soc|dans\s+le\s+groupe|at\b|with\b|within\b|in\s+the\s+(?:firm|group|company))", False),
    # --- Expérience individuelle (type décidé par le contexte) ---
    (INDUSTRIE, N + ANS + r"'?\s+" + EXP, False),
    (INDUSTRIE, r"experience\s+(?:professionnelle\s+)?(?:de\s+|of\s+)" + Q + N + ANS, False),
    (INDUSTRIE, r"depuis\s+" + Q + N + ANS, True),
    (INDUSTRIE, r"(?:for|over)\s+(?:the\s+(?:last|past)\s+)?" + Q + N + ANS, True),
]
MOTIFS = [(t, re.compile(m), temporel) for t, m, temporel in MOTIFS]

PRIORITE = {MOYENNE: 0, SOCIETE: 1, INDUSTRIE: 2}

MARQUEURS_MOYENNE = re.compile(r"\bmoyenne\b|\baverage\b|\ben moyenne\b|\bon average\b")
MARQUEURS_SOCIETE = re.compile(
    r"au sein d|\bchez\b|rothschild|r&co|r & co|\bla societe\b|notre societe|\ble groupe\b|"
    r"la maison|\bthe firm\b|\bthe company\b|\bthe group\b|\bjoined\b|\brejoint\b|\bat r\b|\bwith r\b|"
    r"\bwithin r\b|\bour firm\b|\bour company\b"
)
MARQUEURS_INDUSTRIE = re.compile(
    r"industrie|industry|\bmarches?\b|\bmarkets?\b|carriere|career|gestion d'actifs|asset management|"
    r"\bfinance\b|financial|professionnelle|professional|investment experience|experience en gestion|"
    r"experience d'investissement|investment management"
)
COUPURE_CONTEXTE = re.compile(r",|;|\bdont\b|\bincluding\b|\bof which\b|\bet\b|\band\b|\(")

# Énumération avant un nombre détecté : « 35, 24 et [8] ans », « 30 and [25] years »
RE_ENUM_AVANT = re.compile(r"(?P<n>\d{1,2})(?:\s*(?:ans|annees|years))?\s*(?:,|\bet\b|\band\b|&)\s*$")

# Formulations à signaler sans les modifier.
NOMBRE_EN_LETTRES = (
    r"un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|"
    r"dix-\w+|vingt(?:-\w+)?|trente(?:-\w+)?|quarante(?:-\w+)?|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty(?:-\w+)?|thirty(?:-\w+)?|forty(?:-\w+)?"
)
RE_NOMBRE_ANS = re.compile(r"\b(\d{1,2})" + ANS)
RE_LETTRES_ANS = re.compile(r"\b(?:" + NOMBRE_EN_LETTRES + r")\s+(?:ans|annees|years)\b")
RE_ANNEE_ARRIVEE = re.compile(
    r"\b(?:rejoint|rejoint\s+\S+(?:\s+\S+){0,4}\s+en|depuis|entre\s+\S+(?:\s+\S+){0,4}\s+en|"
    r"joined(?:\s+\S+){0,5}\s+in|since|debut\w*\s+(?:sa|de sa)\s+carriere\s+en|"
    r"began\s+(?:his|her|their)\s+career\s+in|started\s+(?:his|her|their)\s+career\s+in)\s+((?:19|20)\d\d)\b"
)
RE_EXPERIENCE = re.compile(r"experien|carriere|career|anciennete|rejoint|joined")
RE_CODE_EXISTANT = re.compile(r"<<\s*([^<>]+?)\s*>>")
RE_CODE_XP = re.compile(r"^(?:XPINDUS|XPSDG|XPMOY)", re.IGNORECASE)

# Cellule de tableau contenant seulement une durée : « 25 ans », « 25 years », « 25 »
RE_VALEUR_CELLULE = re.compile(
    r"^\s*(?:plus de\s+|>\s*|over\s+|more than\s+)?(?P<n>\d{1,2})\s*(?:ans|annees|an|years|year|yrs)?\s*\.?\s*$"
)
RE_ENTETE_EXPERIENCE = re.compile(r"experien|anciennete|\bannees\b|\bans\b|\byears\b|seniority|tenure")
RE_ENTETE_SOCIETE = re.compile(
    r"societe|company|\bfirm\b|r&co|r & co|rothschild|maison|groupe|\bgroup\b|\bchez\b|au sein|within|"
    r"\bat the\b|\bwith the\b|\bat r\b|\bwith r\b|tenure|anciennete"
)
RE_ENTETE_INDUSTRIE = re.compile(
    r"industr|marche|market|\btotal\b|carriere|career|profession|secteur|sector|gestion d'actifs|"
    r"asset management|investissement|investment|financ"
)

# --------------------------------------------------------------------------
# Équipes (expérience moyenne)
# --------------------------------------------------------------------------

MOTS_EQUIPES = {
    "Obligataire": r"obligat|\bcredit\b|fixed income|\bbonds?\b|\btaux\b|high yield|investment grade|\bdebt\b",
    "Actions européennes": r"actions europ|actions (?:de la )?zone euro|europe(?:an)? equit|euro ?zone equit|"
    r"euro area equit|capitalisations (?:de la )?zone euro|capitalisations europ|"
    r"analyse financiere actions|analystes? actions|equity analys|equity research|european (?:large|small|mid)",
    "Actions thématiques": r"themati|small ?caps?|petites (?:et moyennes )?capitalisations|mid ?caps?",
    "Valor": r"\bvalor\b",
    "Multigestion": r"multi-?gestion|multi-?manag|architecture ouverte|open architecture|fund selection|"
    r"selection de fonds|fonds de fonds|fund of funds",
}
MOTS_EQUIPES = {k: re.compile(v) for k, v in MOTS_EQUIPES.items()}

RE_ROLE = re.compile(
    r"(?P<pm>\bgerants?\b|\bgerantes?\b|\bgestionnaires?\b|\bmanagers?\b|\bgerant-analystes?\b)|"
    r"(?P<an>\banalystes?\b|\banalysts?\b)|"
    r"(?P<eq>\bequipes?\b|\bteams?\b)"
)


@dataclass
class Proposition:
    code: str
    libelle: str
    type: str
    valeur_excel: object = None  # int ou None
    personne: object = None  # Personne ou None


@dataclass
class Candidat:
    texte_id: str
    para: int  # index du paragraphe dans le document
    debut: int  # position du nombre dans le paragraphe
    fin: int
    valeur_texte: str
    type_detecte: str
    paragraphe: str
    phrase: tuple  # (debut, fin) dans le paragraphe
    propositions: list = field(default_factory=list)
    sur: bool = False
    remarques: list = field(default_factory=list)
    cadre: str = ""  # description du contexte (cellule de tableau)

    @property
    def texte_phrase(self):
        p = self.paragraphe[self.phrase[0]:self.phrase[1]].strip()
        return f"{self.cadre} : {p}" if self.cadre else p

    def contexte(self, marge=30, borne_gauche=0, borne_droite=None):
        """Extrait autour du nombre pour retrouver et vérifier sa position dans Word.

        Les bornes excluent les autres nombres remplacés dans le même paragraphe.
        """
        borne_droite = len(self.paragraphe) if borne_droite is None else borne_droite
        d = max(self.phrase[0], self.debut - marge, borne_gauche)
        f = min(self.phrase[1], self.fin + marge, borne_droite)
        return self.paragraphe[d:f], self.debut - d


@dataclass
class Signalement:
    texte_id: str
    para: int
    motif: str
    extrait: str


# --------------------------------------------------------------------------
# Recherche des personnes
# --------------------------------------------------------------------------

PARTICULES = {"de", "du", "des", "la", "le", "d", "van", "von", "di", "da", "del", "der"}


class Annuaire:
    """Reconnaît les collaborateurs de l'Excel dans un texte normalisé.

    Le nom complet est toujours reconnu ; pour les noms d'au moins 3 mots, un
    début de nom sans ambiguïté l'est aussi (« Grégoire du Mesnil » pour
    « Grégoire du Mesnil du Buisson »).
    """

    def __init__(self, referentiel):
        def motif(jetons):
            return re.compile(r"(?<![\w])" + r"[\s\-]+".join(re.escape(j) for j in jetons) + r"(?![\w])")

        complets, partiels = {}, {}
        for p in referentiel.personnes:
            jetons = [j for j in re.split(r"[\s\-]+", normaliser(p.nom)) if j]
            complets[tuple(jetons)] = p
            for k in range(2, len(jetons)):
                if jetons[k - 1] not in PARTICULES:
                    partiels.setdefault(tuple(jetons[:k]), []).append(p)
        self.entrees = [(p, motif(j)) for j, p in complets.items()]
        for j, ps in partiels.items():
            if len(ps) == 1 and j not in complets:
                self.entrees.append((ps[0], motif(j)))

    def chercher(self, texte_norm):
        """Liste de (debut, fin, Personne), triée par position."""
        res = []
        for p, rx in self.entrees:
            for m in rx.finditer(texte_norm):
                res.append((m.start(), m.end(), p))
        res.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        # supprime les noms inclus dans un nom plus long au même endroit
        filtre = []
        for r in res:
            if any(o[0] <= r[0] and r[1] <= o[1] and (o[1] - o[0]) > (r[1] - r[0]) for o in res):
                continue
            if filtre and filtre[-1][:2] == r[:2]:
                continue
            filtre.append(r)
        return filtre

    def personnes(self, texte_norm):
        res = []
        for _, _, p in self.chercher(texte_norm):
            if p not in res:
                res.append(p)
        return res


# --------------------------------------------------------------------------
# Fonctions d'analyse
# --------------------------------------------------------------------------


def _detections(norm):
    """Nombres d'années trouvés : {(debut, fin): (type, debut_motif, fin_motif, temporel)}."""
    trouves = {}
    for type_, rx, temporel in MOTIFS:
        for m in rx.finditer(norm):
            cle = (m.start("n"), m.end("n"))
            if cle not in trouves or PRIORITE[type_] < PRIORITE[trouves[cle][0]] or (
                    PRIORITE[type_] == PRIORITE[trouves[cle][0]] and trouves[cle][3] and not temporel):
                trouves[cle] = (type_, m.start(), m.end(), temporel)
    return trouves


def _dans_code(debut, fin, norm):
    for m in RE_CODE_EXISTANT.finditer(norm):
        if m.start() <= debut and fin <= m.end():
            return True
    return False


def _clause_avant(norm, ph, debut):
    avant = norm[ph[0]:debut]
    coupures = [m.end() for m in re.finditer(r"[,;(]|\bet\b|\band\b", avant)]
    return avant[coupures[-1]:] if coupures else avant


def _type_individuel(norm, ph, debut, type_motif, fin_motif, temporel):
    """Retourne (type, certain)."""
    if type_motif == SOCIETE:
        return SOCIETE, True
    apres = norm[fin_motif:ph[1]]
    coupure = COUPURE_CONTEXTE.search(apres)
    if coupure:
        apres = apres[:coupure.start()]
    avant = norm[max(ph[0], debut - 40):debut]
    if MARQUEURS_SOCIETE.search(apres):
        return SOCIETE, True
    if temporel:
        # « chez Rothschild & Co AM depuis 9 ans », « with R&Co AM for 9 years »
        if MARQUEURS_SOCIETE.search(_clause_avant(norm, ph, debut)):
            return SOCIETE, True
        if MARQUEURS_INDUSTRIE.search(apres):
            return INDUSTRIE, True
        return INDUSTRIE, False
    if MARQUEURS_INDUSTRIE.search(apres) or MARQUEURS_INDUSTRIE.search(avant):
        return INDUSTRIE, True
    if re.search(r"experience", norm[debut:fin_motif]):
        return INDUSTRIE, True  # « N ans d'expérience » = expérience dans l'industrie
    return INDUSTRIE, False


def _type_entete(entete_norm):
    """Type d'un en-tête de tableau : INDUSTRIE, SOCIETE, MOYENNE, 'AMBIGU' ou None (pas d'expérience)."""
    if not entete_norm or not RE_ENTETE_EXPERIENCE.search(entete_norm):
        return None
    if MARQUEURS_MOYENNE.search(entete_norm):
        return MOYENNE
    soc = bool(RE_ENTETE_SOCIETE.search(entete_norm))
    ind = bool(RE_ENTETE_INDUSTRIE.search(entete_norm))
    if soc and not ind:
        return SOCIETE
    if ind and not soc:
        return INDUSTRIE
    return "AMBIGU"


def _equipes_mots(norm_zone):
    return [e for e, rx in MOTS_EQUIPES.items() if rx.search(norm_zone)]


def _role(norm, ph, debut):
    """Rôle désigné avant le nombre (dernier mot-clé de la phrase)."""
    role = None
    for m in RE_ROLE.finditer(norm[ph[0]:debut]):
        if m.group("pm"):
            role = GERANTS
        elif m.group("an"):
            role = ANALYSTES
        else:
            role = TOTAL if role is None else role
    return role


class Analyseur:
    def __init__(self, referentiel, motifs_id=None):
        self.ref = referentiel
        self.annuaire = Annuaire(referentiel)
        self.motifs_id = compiler_motifs_id(motifs_id)
        self._positions = {}  # (paragraphe, position) -> merge code déjà présent

    # ------------------------------------------------------------------
    def analyser(self, paragraphes, tableaux=None):
        """Analyse le document.

        Les merge codes d'expérience déjà présents sont remplacés par « 99 » le
        temps de l'analyse : ils servent ainsi de repère (énumérations) et sont
        contrôlés (le code présent est comparé au code que le bot proposerait).
        """
        tableaux = tableaux or []
        virtuels, self._positions, decalages = self._virtualiser(paragraphes)
        try:
            textes = self._analyser(virtuels, tableaux, paragraphes)
        finally:
            positions, self._positions = self._positions, {}

        def v2o(i, pos):
            return pos + sum(lo - 2 for vs, lo in decalages.get(i, ()) if vs + 2 <= pos)

        for t in textes:
            gardes = []
            for c in t.candidats:
                code = positions.get((c.para, c.debut))
                if code is not None:
                    self._controler(c, code, t, paragraphes)
                    continue
                if c.para in decalages:
                    c.debut = v2o(c.para, c.debut)
                    c.fin = c.debut + len(c.valeur_texte)
                    c.phrase = (v2o(c.para, c.phrase[0]), v2o(c.para, c.phrase[1]))
                    c.paragraphe = paragraphes[c.para]
                gardes.append(c)
            t.candidats = gardes
        return textes

    def _virtualiser(self, paragraphes):
        virtuels, positions, decalages = [], {}, {}
        for i, p in enumerate(paragraphes):
            morceaux, pos, dernier = [], 0, 0
            for m in RE_CODE_EXISTANT.finditer(p):
                code = m.group(1)
                if not RE_CODE_XP.match(code) and code not in self.ref.codes:
                    continue
                morceaux.append(p[dernier:m.start()])
                pos += m.start() - dernier
                positions[(i, pos)] = code
                decalages.setdefault(i, []).append((pos, m.end() - m.start()))
                morceaux.append("99")
                pos += 2
                dernier = m.end()
            morceaux.append(p[dernier:])
            virtuels.append("".join(morceaux))
        return virtuels, positions, decalages

    def _controler(self, c, code, t, paragraphes):
        original = paragraphes[c.para].strip()
        extrait = f"{c.cadre} : {original}" if c.cadre else original
        proposes = [p.code for p in c.propositions]
        if code not in self.ref.codes:
            t.signalements.append(Signalement(t.id, c.para, f"Merge code présent <<{code}>> inconnu dans l'Excel", extrait))
        elif proposes and code != proposes[0] and (c.sur or code not in proposes):
            t.signalements.append(Signalement(
                t.id, c.para, f"Merge code présent <<{code}>> probablement faux : le bot proposerait <<{proposes[0]}>>",
                extrait))

    def _analyser(self, paragraphes, tableaux, originaux):
        textes = segmenter(paragraphes, self.motifs_id)
        normes = [normaliser(p) for p in paragraphes]
        par_para = {}
        for t in textes:
            for i in range(t.para_debut, t.para_fin):
                par_para[i] = t
        couverts = {}  # para -> positions déjà traitées (cellules de tableaux)
        for tab in tableaux:
            self._analyser_tableau(tab, paragraphes, normes, par_para, couverts)
        for t in textes:
            norm_texte = " ".join(normes[t.para_debut:t.para_fin])
            for i in range(t.para_debut, t.para_fin):
                for m in RE_CODE_EXISTANT.finditer(originaux[i]):
                    t.codes_existants.append(m.group(1))
                self._analyser_paragraphe(t, i, paragraphes[i], normes[i], normes, norm_texte,
                                          couverts.setdefault(i, set()), originaux[i])
            t.candidats.sort(key=lambda c: (c.para, c.debut))
        return textes

    # -- paragraphes -----------------------------------------------------
    def _analyser_paragraphe(self, t, i, para, norm, normes, norm_texte, couverts, original):
        detections = _detections(norm)
        for (debut, fin), (type_motif, deb_motif, fin_motif, temporel) in sorted(detections.items()):
            if debut in couverts or _dans_code(debut, fin, norm):
                continue
            ph = next((p for p in phrases(para) if p[0] <= debut < p[1]), (0, len(para)))
            zone = norm[ph[0]:ph[1]]
            if temporel and not (self.annuaire.chercher(zone) or MARQUEURS_SOCIETE.search(zone)):
                continue  # « depuis 3 ans avec un prestataire » : hors sujet
            moyenne = type_motif == MOYENNE or (
                type_motif != SOCIETE and MARQUEURS_MOYENNE.search(zone) and not self.annuaire.chercher(zone))
            # énumération éventuelle avant le nombre : « 35, 24 et [8] ans »
            groupe = [(debut, fin)]
            if not moyenne:
                d = debut
                while True:
                    m = RE_ENUM_AVANT.search(norm[ph[0]:d])
                    if not m or ph[0] + m.start("n") in couverts:
                        break
                    groupe.insert(0, (ph[0] + m.start("n"), ph[0] + m.end("n")))
                    d = ph[0] + m.start()
            for rang, (d_n, f_n) in enumerate(groupe):
                if d_n in couverts:
                    continue
                couverts.add(d_n)
                c = Candidat(t.id, i, d_n, f_n, para[d_n:f_n], type_motif, para, ph)
                if moyenne:
                    c.type_detecte = MOYENNE
                    self._proposer_moyenne(c, norm, ph, norm_texte)
                else:
                    self._proposer_individuel(c, norm, ph, normes, t, type_motif, fin_motif, temporel,
                                              debut, groupe, rang)
                t.candidats.append(c)
        self._signaler(t, i, para, norm, couverts, original)

    # -- tableaux --------------------------------------------------------
    def _analyser_tableau(self, cellules, paragraphes, normes, par_para, couverts):
        if not cellules:
            return
        lignes = {}
        for c in cellules:
            lignes.setdefault(c.ligne, []).append(c)
        for r in lignes:
            lignes[r].sort(key=lambda c: c.colonne)

        def texte(c):
            return " ".join(normes[i].strip() for i in c.paras if normes[i].strip())

        def valeur(c):
            for i in c.paras:
                m = RE_VALEUR_CELLULE.match(normes[i])
                if m:
                    return i, m
            return None

        textes_cell = {id(c): texte(c) for c in cellules}
        for c in cellules:
            v = valeur(c)
            if v is None:
                continue
            i, m = v
            if i not in par_para:
                continue
            # en-tête de colonne : première cellule non numérique au-dessus, dans
            # une ligne ayant le même nombre de cellules (colonnes alignées)
            entete_col = None
            for r in sorted((r for r in lignes if r < c.ligne), reverse=True):
                if len(lignes[r]) != len(lignes[c.ligne]):
                    continue
                dessus = next((x for x in lignes[r] if x.colonne == c.colonne), None)
                if dessus and textes_cell[id(dessus)] and not valeur(dessus):
                    entete_col = dessus
                    break
            premiere = lignes[c.ligne][0]
            entete_ligne = premiere if premiere is not c else None
            type_col = _type_entete(textes_cell[id(entete_col)]) if entete_col else None
            type_lig = _type_entete(textes_cell[id(entete_ligne)]) if entete_ligne else None
            if type_col:
                type_, entete = type_col, entete_col
                autres = [x for x in lignes[c.ligne] if x is not c and not valeur(x)]
            elif type_lig:
                type_, entete = type_lig, entete_ligne
                autres = [x for x in cellules if x.colonne == c.colonne and x is not c and not valeur(x)]
            else:
                continue  # pas un tableau d'expérience
            if m.group(0).strip().isdigit() and not RE_ENTETE_EXPERIENCE.search(textes_cell[id(entete)]):
                continue
            debut, fin = m.start("n"), m.end("n")
            couverts.setdefault(i, set()).add(debut)
            t = par_para[i]
            para = paragraphes[i]
            personnes = []
            for x in autres:
                for p in self.annuaire.personnes(textes_cell[id(x)]):
                    if p not in personnes:
                        personnes.append(p)
            entete_txt = " ".join(paragraphes[k].strip() for k in entete.paras if paragraphes[k].strip())
            qui = ", ".join(p.nom for p in personnes) or "personne non identifiée"
            cand = Candidat(t.id, i, debut, fin, para[debut:fin], type_ if type_ in (INDUSTRIE, SOCIETE, MOYENNE)
                            else INDUSTRIE, para, (0, len(para)), cadre=f"Tableau – {qui} – {entete_txt}")
            if type_ == MOYENNE:
                cand.remarques.append("Tableau d'expérience moyenne : choisir le code d'équipe")
                self._proposer_moyenne(cand, normes[i], (0, len(para)), " ".join(textes_cell.values()))
                cand.sur = False
            else:
                types = [INDUSTRIE, SOCIETE] if type_ == "AMBIGU" else [type_]
                if type_ == "AMBIGU":
                    cand.remarques.append(f"En-tête « {entete_txt} » : industrie ou société ?")
                self._attribuer(cand, personnes, types, len(personnes) == 1, type_ != "AMBIGU")
            t.candidats.append(cand)

    # -- expérience individuelle ------------------------------------------
    def _proposer_individuel(self, c, norm, ph, normes, t, type_motif, fin_motif, temporel,
                             debut_motif, groupe, rang):
        type_, type_certain = _type_individuel(norm, ph, debut_motif, type_motif, fin_motif, temporel)
        c.type_detecte = type_
        noms_phrase = self.annuaire.chercher(norm[ph[0]:ph[1]])
        personnes = []
        for _, _, p in noms_phrase:
            if p not in personnes:
                personnes.append(p)
        attribution_certaine = len(personnes) == 1 and len(groupe) == 1
        if len(groupe) > 1:
            # « X et Y disposent de 30 et 25 ans » / « co-géré par X et Y. Elles
            # disposent de 30 et 25 ans » : attribution dans l'ordre des noms
            zones = [norm[ph[0]:groupe[0][0]], norm[:ph[0]]]
            zones += [normes[j] for j in range(c.para - 1, max(t.para_debut, c.para - 3) - 1, -1)]
            ordre = []
            for zone in zones:
                ordre = self.annuaire.personnes(zone)
                if len(ordre) == len(groupe):
                    break
            if len(ordre) == len(groupe):
                personnes = [ordre[rang]] + [p for p in ordre if p is not ordre[rang]]
                c.remarques.append(f"Énumération de {len(groupe)} valeurs : attribuée dans l'ordre des noms "
                                   f"({', '.join(p.nom for p in ordre)}), à confirmer")
            else:
                c.remarques.append(f"Énumération de {len(groupe)} valeurs : personne à choisir")
        elif len(personnes) > 1:
            # le nom le plus proche avant le nombre en premier
            avant = [p for d, _, p in noms_phrase if ph[0] + d < c.debut]
            proche = avant[-1] if avant else personnes[0]
            personnes.remove(proche)
            personnes.insert(0, proche)
            c.remarques.append("Plusieurs collaborateurs cités dans la phrase")
        if not personnes and len(groupe) == 1:
            # recherche du dernier nom cité plus haut dans le même texte
            noms = self.annuaire.chercher(norm[:ph[0]])
            j = c.para - 1
            while not noms and j >= max(t.para_debut, c.para - 3):
                noms = self.annuaire.chercher(normes[j])
                j -= 1
            if noms:
                personnes = [noms[-1][2]]
                c.remarques.append(f"Nom non cité dans la phrase : déduit du contexte ({personnes[0].nom})")
        if not type_certain:
            c.remarques.append("Type (industrie / société) déduit, à confirmer")
        self._attribuer(c, personnes, [type_, SOCIETE if type_ == INDUSTRIE else INDUSTRIE],
                        attribution_certaine, type_certain)

    def _attribuer(self, c, personnes, types, attribution_certaine, type_certain):
        if not personnes:
            c.remarques.append("Aucun collaborateur de l'Excel identifié : saisir le code à la main ou ignorer")
        elif len(personnes) > 1 and "Plusieurs" not in " ".join(c.remarques) and "numération" not in " ".join(c.remarques):
            c.remarques.append("Plusieurs collaborateurs possibles")
        for t in types:
            for p in personnes:
                c.propositions.append(Proposition(
                    code=p.code(t),
                    libelle=f"{p.nom} – {'industrie' if t == INDUSTRIE else 'société'}",
                    type=t,
                    valeur_excel=p.annees(t, self.ref.annee_ref),
                    personne=p,
                ))
        if not c.propositions:
            return
        prop = c.propositions[0]
        if (c.para, c.debut) in self._positions:
            coherent = True  # code déjà présent : la valeur n'est pas connue
        else:
            valeur = int(c.valeur_texte)
            coherent = prop.valeur_excel is not None and 0 <= prop.valeur_excel - valeur <= 5
            if prop.valeur_excel is None:
                c.remarques.append("Date d'entrée absente de l'Excel")
            elif not coherent:
                c.remarques.append(f"Valeur du texte ({valeur}) éloignée de l'Excel ({prop.valeur_excel})")
        c.sur = attribution_certaine and type_certain and not code_incomplet(prop.code) and coherent

    # -- expérience moyenne -----------------------------------------------
    def _equipes_personnes(self, zone):
        res = []
        for p in self.annuaire.personnes(zone):
            e, _ = equipe_du_libelle(p.equipe)
            if e and e not in res:
                res.append(e)
        return res

    def _proposer_moyenne(self, c, norm, ph, norm_texte):
        niveaux = [
            ("phrase", norm[ph[0]:ph[1]]),
            ("paragraphe", norm),
            ("texte", norm_texte),
        ]
        equipes, niveau = [], None
        for nom_niveau, zone in niveaux:
            equipes = _equipes_mots(zone)
            for e in self._equipes_personnes(zone):
                if e not in equipes:
                    equipes.append(e)
            if equipes:
                niveau = nom_niveau
                break
        role = _role(norm, ph, c.debut)
        if role is None:
            c.remarques.append("Rôle (gérants / analystes / équipe) non précisé avant le nombre")
        if not equipes:
            c.remarques.append("Équipe non identifiée : saisir le code à la main ou ignorer")
        elif len(equipes) > 1:
            c.remarques.append("Plusieurs équipes possibles : " + ", ".join(equipes))
        elif niveau == "texte":
            c.remarques.append("Équipe déduite du reste du texte, à confirmer")

        roles = [role] if role else [GERANTS, ANALYSTES, TOTAL]
        vus = set()
        for e in equipes:
            for r in roles + [x for x in (GERANTS, ANALYSTES, TOTAL) if x not in roles]:
                ce = self.ref.code_equipe(e, r)
                if ce and ce.code not in vus:
                    vus.add(ce.code)
                    c.propositions.append(Proposition(ce.code, ce.libelle, MOYENNE))
        if equipes and role and not self.ref.code_equipe(equipes[0], role):
            c.remarques.append(f"Pas de merge code « {equipes[0]} / {role} » dans l'Excel")
        premier = self.ref.code_equipe(equipes[0], role) if len(equipes) == 1 and role else None
        c.sur = bool(premier) and niveau in ("phrase", "paragraphe")

    # -- signalements -------------------------------------------------------
    def _signaler(self, t, i, para, norm, couverts, original):
        codes = {pos for (j, pos) in self._positions if j == i}
        for ph in phrases(para):
            zone = norm[ph[0]:ph[1]]
            extrait = para[ph[0]:ph[1]].strip() if not codes else original.strip()
            if not RE_EXPERIENCE.search(zone):
                continue
            for m in RE_NOMBRE_ANS.finditer(zone):
                d = ph[0] + m.start(1)
                if d not in couverts and d not in codes and not _dans_code(ph[0] + m.start(), ph[0] + m.end(), norm):
                    t.signalements.append(Signalement(t.id, i, "Formulation non reconnue (nombre d'années)", extrait))
                    break
            if RE_LETTRES_ANS.search(zone):
                t.signalements.append(Signalement(t.id, i, "Nombre d'années écrit en lettres", extrait))
            if RE_ANNEE_ARRIVEE.search(zone) and self.annuaire.chercher(zone):
                t.signalements.append(Signalement(t.id, i, "Expérience exprimée par une année (ex. « depuis 2005 »)", extrait))
