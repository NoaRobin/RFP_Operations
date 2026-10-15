"""Bot d'insertion des merge codes Qvidian « années d'expérience » dans Word.

Utilisation (Windows, Word ouvert avec l'export Qvidian) :
    python bot_merge_codes.py                 # validation de chaque passage (recommandé)
    python bot_merge_codes.py --mode auto     # passages « sûrs » insérés sans question
    python bot_merge_codes.py --mode analyse  # aucune modification, compte rendu seul
    python bot_merge_codes.py --docx export.docx   # analyse d'un fichier sans Word

Voir GUIDE_BOT.md.
"""

import argparse
import glob
import os
import sys

from mergebot import rapport as R
from mergebot.analyse import SANS_ID, Analyseur
from mergebot.referentiel import LIBELLE_TYPE, MOYENNE, Referentiel, code_incomplet

ICI = os.path.dirname(os.path.abspath(__file__))
EXCEL_DEFAUT = os.path.join(ICI, "Années d'expérience - FR_EN pour Qvidian.xlsx")
if not os.path.exists(EXCEL_DEFAUT):
    _trouves = sorted(glob.glob(os.path.join(ICI, "Années d*exp*rience*.xlsx")), key=os.path.getmtime)
    EXCEL_DEFAUT = _trouves[-1] if _trouves else EXCEL_DEFAUT
RAPPORT_DEFAUT = os.path.join(ICI, "compte_rendu_merge_codes.xlsx")
LIGNE = "─" * 78


def merge_code(code):
    """Format exact attendu par Qvidian : <<CODE>> (chevrons ASCII doublés)."""
    return f"<<{code}>>"


# --------------------------------------------------------------------------
# Affichage / décisions
# --------------------------------------------------------------------------


def phrase_marquee(c):
    d, f = c.phrase
    p = c.paragraphe
    return (p[d:c.debut] + "[[" + p[c.debut:c.fin] + "]]" + p[c.fin:f]).strip()


def decrire(prop):
    val = "—" if prop.type == MOYENNE else ("date absente" if prop.valeur_excel is None else f"{prop.valeur_excel} an(s)")
    alerte = "  ⚠ code incomplet" if code_incomplet(prop.code) else ""
    return f"{merge_code(prop.code):30} {prop.libelle}  (Excel : {val}){alerte}"


def afficher_candidat(c, k, total):
    print(LIGNE)
    sur = "SÛR" if c.sur else "À CONFIRMER"
    print(f"[{k}/{total}]  ID {c.texte_id}  –  {LIBELLE_TYPE[c.type_detecte]}  –  {sur}")
    if c.cadre:
        print(f"  {c.cadre}")
    print(f"  « {phrase_marquee(c)} »")
    for r in c.remarques:
        print(f"  ! {r}")
    for i, p in enumerate(c.propositions, start=1):
        print(f"  {i}. {decrire(p)}{'   ← proposé' if i == 1 else ''}")


def demander(c, ref, entree):
    """Retourne une Proposition, None (ignorer) ou 'QUITTER'."""
    from mergebot.analyse import Proposition

    defaut = c.propositions[0] if c.propositions else None
    aide = "Entrée = valider 1" if defaut else "Entrée = ignorer"
    while True:
        rep = entree(f"  {aide} | n = ignorer | numéro | code (ex. XPSDG_YI) | q = arrêter ce lot > ").strip()
        if rep == "":
            return defaut
        if rep.lower() == "n":
            return None
        if rep.lower() == "q":
            return "QUITTER"
        if rep.isdigit() and 1 <= int(rep) <= len(c.propositions):
            return c.propositions[int(rep) - 1]
        code = rep.strip().strip("<>").strip()
        info = ref.decrire_code(code)
        if info:
            type_, libelle, valeur, personne = info
            return Proposition(code, libelle, type_, valeur, personne)
        print(f"  Code « {code} » inconnu dans l'Excel. Réessayer.")


def statut_proposition(prop):
    if code_incomplet(prop.code):
        return R.CODE_INCOMPLET
    if prop.type != MOYENNE:
        if prop.valeur_excel is None:
            return R.SANS_VALEUR
        if prop.valeur_excel <= 0:
            return R.ZERO
    return None


# --------------------------------------------------------------------------
# Traitement d'un document
# --------------------------------------------------------------------------


def traiter(source, nom_doc, analyseur, ref, mode, rapport, entree=input):
    paragraphes = source.paragraphes()
    tableaux = source.tableaux()
    return traiter_paragraphes(paragraphes, source, nom_doc, analyseur, ref, mode, rapport, entree, tableaux)


def traiter_paragraphes(paragraphes, source, nom_doc, analyseur, ref, mode, rapport, entree=input, tableaux=None):
    textes = analyseur.analyser(paragraphes, tableaux)
    ids = [t.id for t in textes if t.id != SANS_ID]
    candidats = [c for t in textes for c in t.candidats]
    print(LIGNE)
    print(f"Document : {nom_doc}")
    print(f"{len(paragraphes)} paragraphes, {len(tableaux or [])} tableaux, {len(ids)} textes identifiés par un ID, "
          f"{len(candidats)} passage(s) détecté(s).")
    if ids:
        print(f"Premier ID : {ids[0]}   Dernier ID : {ids[-1]}")
    if not ids:
        print("⚠ Aucun ID de texte reconnu : vérifier le format des ID (option --id-regex).")
    if len(set(ids)) != len(ids):
        print("⚠ Certains ID apparaissent plusieurs fois dans le document.")

    # 1) Décisions (aucune modification du document à ce stade)
    decisions = []  # (candidat, proposition|None, statut)
    for k, c in enumerate(candidats, start=1):
        if mode == "auto" and c.sur:
            prop = c.propositions[0]
            print(f"[{k}/{len(candidats)}] ID {c.texte_id} : {c.valeur_texte} → {merge_code(prop.code)} (sûr, automatique)")
        elif mode == "analyse":
            prop = c.propositions[0] if c.propositions else None
        else:
            afficher_candidat(c, k, len(candidats))
            prop = demander(c, ref, entree)
            if prop == "QUITTER":
                print("Lot interrompu : aucune modification n'a été faite dans Word.")
                return None
        if prop is None:
            statut = R.IGNORE if mode != "analyse" else "Aucune proposition (mode analyse)"
        else:
            statut = statut_proposition(prop) or (R.ANALYSE if mode == "analyse" else "À insérer")
        decisions.append((c, prop, statut))

    a_inserer = [d for d in decisions if d[2] == "À insérer"]

    # 2) Insertion dans Word (du bas vers le haut du document)
    if a_inserer and source is not None:
        print(LIGNE)
        rep = entree(f"Insérer {len(a_inserer)} merge code(s) dans Word ? Entrée = oui, n = non > ").strip().lower()
        if rep == "n":
            print("Aucune modification faite.")
            a_inserer = []
            decisions = [(c, p, R.IGNORE if s == "À insérer" else s) for c, p, s in decisions]
        else:
            probleme = source.verifier_inchange()
            if probleme:
                print(f"⚠ {probleme} Aucune modification faite : relancer l'analyse.")
                return None
            resultats = {}
            ordre = sorted(a_inserer, key=lambda d: (d[0].para, d[0].debut), reverse=True)
            source.debut_edition()
            try:
                for c, prop, _ in ordre:
                    voisins = [d[0] for d in ordre if d[0].para == c.para and d[0] is not c]
                    gauche = max([v.fin for v in voisins if v.fin <= c.debut], default=0)
                    droite = min([v.debut for v in voisins if v.debut >= c.fin], default=None)
                    contexte, decalage = c.contexte(borne_gauche=gauche, borne_droite=droite)
                    ok, msg = source.remplacer(c.para, c.debut, c.fin, c.valeur_texte,
                                               merge_code(prop.code), contexte, decalage)
                    resultats[id(c)] = (ok, msg)
            finally:
                source.fin_edition()
            nouvelles = []
            for c, prop, statut in decisions:
                if statut == "À insérer":
                    ok, msg = resultats.get(id(c), (False, "non traité"))
                    statut = R.REMPLACE if ok else R.ECHEC
                    if not ok:
                        c.remarques.append(msg)
                nouvelles.append((c, prop, statut))
            decisions = nouvelles
    elif source is None:
        decisions = [(c, p, R.ANALYSE if s == "À insérer" else s) for c, p, s in decisions]

    # 3) Compte rendu
    par_texte = {}
    for c, prop, statut in decisions:
        par_texte.setdefault(c.texte_id, []).append((c, prop, statut))
        qui = prop.libelle if prop else ""
        rapport.passage(
            c.texte_id, statut, LIBELLE_TYPE[prop.type if prop else c.type_detecte], qui,
            c.valeur_texte, "" if not prop or prop.valeur_excel is None else prop.valeur_excel,
            prop.code if prop else "", c.texte_phrase, " ; ".join(c.remarques),
        )
        if statut == R.ZERO:
            rapport.zero(c.texte_id, prop.personne.nom if prop.personne else prop.libelle,
                         LIBELLE_TYPE[prop.type], prop.code, c.texte_phrase)
        if statut in (R.ECHEC, R.CODE_INCOMPLET, R.SANS_VALEUR):
            rapport.a_verifier(c.texte_id, statut + " – " + " ; ".join(c.remarques), c.texte_phrase)

    compteur = {}
    for t in textes:
        for s in t.signalements:
            rapport.a_verifier(t.id, s.motif, s.extrait)
        ds = par_texte.get(t.id, [])
        statuts = [s for _, _, s in ds]
        nb = statuts.count(R.REMPLACE)
        bloquants = [s for s in statuts if s in (R.ECHEC, R.CODE_INCOMPLET, R.SANS_VALEUR)]
        if bloquants or t.signalements or "Aucune proposition (mode analyse)" in statuts:
            statut_t = "À vérifier"
        elif nb:
            statut_t = "Merge code(s) inséré(s)"
        elif R.ZERO in statuts:
            statut_t = R.ZERO
        elif R.ANALYSE in statuts:
            statut_t = "Passage(s) à remplacer (mode analyse)"
        elif ds:
            statut_t = "Passage(s) ignoré(s)"
        else:
            statut_t = "Aucun passage à remplacer"
        compteur[statut_t] = compteur.get(statut_t, 0) + 1
        detail = [f"{c.valeur_texte} → {merge_code(p.code) if p else '—'} : {s}" for c, p, s in ds]
        detail += [f"{s.motif}" for s in t.signalements]
        rapport.texte(nom_doc, t.id, statut_t, nb, len(ds), t.codes_existants, "\n".join(detail), t.titre)

    print(LIGNE)
    print(f"Lot {rapport.lot} terminé – {len(textes)} texte(s) :")
    for s, n in sorted(compteur.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {s}")
    zeros = [(c.texte_id, p.libelle) for c, p, s in decisions if s == R.ZERO]
    if zeros:
        print("IDs avec 0 an d'expérience (non insérés, à faire en 2027) :")
        for i, q in zeros:
            print(f"  - {i} : {q}")
    return decisions


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--excel", default=EXCEL_DEFAUT, help="Fichier Excel des années d'expérience")
    ap.add_argument("--rapport", default=RAPPORT_DEFAUT, help="Compte rendu Excel (cumulatif)")
    ap.add_argument("--mode", choices=["validation", "auto", "analyse"], default="validation")
    ap.add_argument("--annee", type=int, help="Année de référence pour le calcul (défaut : année en cours)")
    ap.add_argument("--id-regex", action="append",
                    help="Motif d'ID (expression régulière avec un groupe (?P<id>...)), répétable")
    ap.add_argument("--docx", help="Analyser un fichier .docx sans Word (aucune modification)")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ref = Referentiel.charger(args.excel, args.annee)
    analyseur = Analyseur(ref, args.id_regex)
    print(LIGNE)
    print(f"Référentiel : {len(ref.personnes)} collaborateurs, {len(ref.codes_equipe)} codes d'équipe, "
          f"année de référence {ref.annee_ref}.")
    if ref.anomalies:
        print("Anomalies dans l'Excel :")
        for a in ref.anomalies:
            print(f"  - {a}")

    if args.docx:
        from mergebot.word import lire_docx

        rapport = R.Rapport(args.rapport)
        paragraphes, tableaux = lire_docx(args.docx)
        traiter_paragraphes(paragraphes, None, os.path.basename(args.docx),
                            analyseur, ref, "analyse", rapport, tableaux=tableaux)
        print(f"Compte rendu : {rapport.enregistrer()}")
        return

    from mergebot.word import DocumentWord

    while True:
        print(LIGNE)
        rep = input("Ouvre le Word exporté de Qvidian, puis Entrée pour lancer (q = quitter) > ").strip().lower()
        if rep == "q":
            break
        try:
            doc = DocumentWord()
        except RuntimeError as e:
            print(f"⚠ {e}")
            continue
        rapport = R.Rapport(args.rapport)
        try:
            res = traiter(doc, doc.nom, analyseur, ref, args.mode, rapport)
        except Exception as e:  # on ne perd jamais le compte rendu déjà produit
            print(f"⚠ Erreur inattendue : {e!r}")
            print("  Si des merge codes ont déjà été insérés, Ctrl+Z dans Word annule toute l'opération.")
            res = None
        if res is not None:
            chemin = rapport.enregistrer()
            print(f"Compte rendu enregistré : {chemin}")
            if chemin != args.rapport:
                print("⚠ Le compte rendu principal était ouvert dans Excel : copie enregistrée à part.")
            print("Vérifie puis enregistre le Word, et prépare le lot suivant.")


if __name__ == "__main__":
    main()
