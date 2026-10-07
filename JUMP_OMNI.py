from __future__ import annotations

import argparse
import getpass
import logging
import sys
import time
import unicodedata
from pathlib import Path
from typing import Optional

import keyring
import pythoncom
import win32api
import win32con
import win32com.client
import win32gui
import win32process
from pywinauto import Desktop


# ============================================================================
# CONFIGURATION
# ============================================================================

LOGIN_JUMP = "noa.robin"
SERVICE_COFFRE = "JUMP_Excel_AddIn"
SERVEUR_JUMP = "https://prod-rothschild.jump-saas.com"
XLL_JUMP = Path(r"C:\ProgramData\JUMP\Jump.ExcelAddIn64-packed.xll")

# Liste explicite des fichiers à mettre à jour.
FICHIERS_EXCEL = [
    Path(
        r"C:\Users\RP119879\Rothschild & Co\AM-RFP-CONF - Documents"
        r"\3 - Consultants\Automatisation - Python\03 - Sources"
        r"\Holdings 7_2026 Copy.xlsx"
    ),
]

# Pour traiter tous les fichiers d'un dossier :
# 1. mettre FICHIERS_EXCEL = []
# 2. renseigner DOSSIER_EXCEL
DOSSIER_EXCEL: Optional[Path] = None
INCLURE_SOUS_DOSSIERS = False

FICHIER_LOG = Path(__file__).with_name("automatisation_jump_excel.log")

TIMEOUT_EXCEL = 45
TIMEOUT_UI = 90
TIMEOUT_CONNEXION = 45
TIMEOUT_CALCUL = 600
DELAI_STABILISATION_JUMP = 10

# La fenêtre reste techniquement visible pour que le ruban soit construit,
# mais elle est déplacée très loin hors écran.
POSITION_HORS_ECRAN = -30000
FERMER_EXCEL_A_LA_FIN = True

XL_DONE = 0
XL_NORMAL = -4143
BM_CLICK = 0x00F5


# ============================================================================
# JOURNALISATION ET COFFRE WINDOWS
# ============================================================================

def configurer_logs() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(FICHIER_LOG, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def enregistrer_mot_de_passe() -> None:
    """Enregistre ou remplace le mot de passe dans le coffre Windows."""
    print(f"Identifiant JUMP configuré : {LOGIN_JUMP}")
    mdp1 = getpass.getpass("Nouveau mot de passe JUMP : ")
    mdp2 = getpass.getpass("Confirmer le mot de passe JUMP : ")

    if not mdp1:
        raise RuntimeError("Le mot de passe est vide.")
    if mdp1 != mdp2:
        raise RuntimeError("Les deux mots de passe ne correspondent pas.")

    keyring.set_password(SERVICE_COFFRE, LOGIN_JUMP, mdp1)
    print("Mot de passe enregistré dans le coffre Windows.")


def lire_mot_de_passe() -> str:
    """Lit le mot de passe sans demander de saisie en exécution normale."""
    mot_de_passe = keyring.get_password(SERVICE_COFFRE, LOGIN_JUMP)
    if not mot_de_passe:
        raise RuntimeError(
            "Aucun mot de passe JUMP n'est enregistré. Exécute une seule fois :\n"
            f'python3 "{Path(__file__).name}" --set-credentials'
        )
    return mot_de_passe


# ============================================================================
# OUTILS GÉNÉRAUX
# ============================================================================

def normaliser_texte(texte: object) -> str:
    valeur = "" if texte is None else str(texte)
    valeur = unicodedata.normalize("NFKD", valeur)
    valeur = "".join(c for c in valeur if not unicodedata.combining(c))
    return " ".join(valeur.casefold().split())


def nom_controle(controle) -> str:
    try:
        nom = controle.window_text()
    except Exception:
        nom = ""

    if not nom:
        try:
            nom = controle.element_info.name or ""
        except Exception:
            nom = ""

    return normaliser_texte(nom)


def classe_controle(controle) -> str:
    try:
        return str(controle.element_info.class_name or "")
    except Exception:
        try:
            return str(controle.class_name() or "")
        except Exception:
            return ""


def lister_fichiers() -> list[Path]:
    fichiers: list[Path] = [Path(fichier) for fichier in FICHIERS_EXCEL]

    if DOSSIER_EXCEL is not None:
        dossier = Path(DOSSIER_EXCEL)
        if not dossier.exists():
            raise FileNotFoundError(f"Dossier introuvable : {dossier}")

        recherche = dossier.rglob if INCLURE_SOUS_DOSSIERS else dossier.glob
        for motif in ("*.xlsx", "*.xlsm", "*.xlsb", "*.xls"):
            fichiers.extend(recherche(motif))

    resultat: list[Path] = []
    vus: set[str] = set()

    for fichier in fichiers:
        if fichier.name.startswith("~$"):
            continue

        cle = str(fichier.resolve()).lower()
        if cle not in vus:
            vus.add(cle)
            resultat.append(fichier)

    return resultat


# ============================================================================
# EXCEL HORS ÉCRAN
# ============================================================================

def placer_excel_hors_ecran(excel) -> None:
    """Conserve Excel affiché pour le ruban, mais hors de la zone visible."""
    excel.Visible = True

    try:
        excel.WindowState = XL_NORMAL
    except Exception:
        pass

    try:
        excel.Left = POSITION_HORS_ECRAN
        excel.Top = POSITION_HORS_ECRAN
    except Exception:
        pass


def creer_excel():
    pythoncom.CoInitialize()

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.DisplayAlerts = False
    excel.ScreenUpdating = False
    excel.EnableEvents = False
    excel.AskToUpdateLinks = False

    classeur_temporaire = excel.Workbooks.Add()
    classeur_temporaire.Activate()

    placer_excel_hors_ecran(excel)

    pid = win32process.GetWindowThreadProcessId(int(excel.Hwnd))[1]
    logging.info("Excel démarré hors écran. PID : %s", pid)

    return excel, pid, classeur_temporaire


def fenetre_excel(pid: int):
    limite = time.time() + TIMEOUT_EXCEL
    desktop = Desktop(backend="uia")

    while time.time() < limite:
        for fenetre in desktop.windows(process=pid, visible_only=True):
            try:
                if fenetre.element_info.class_name == "XLMAIN":
                    return fenetre
            except Exception:
                pass

        pythoncom.PumpWaitingMessages()
        time.sleep(0.25)

    raise RuntimeError(f"Fenêtre Excel introuvable pour le PID {pid}.")


def charger_xll(excel, pid: int) -> None:
    if not XLL_JUMP.exists():
        raise FileNotFoundError(f"Add-in JUMP introuvable : {XLL_JUMP}")

    logging.info("Chargement explicite de l'add-in JUMP : %s", XLL_JUMP)

    if not bool(excel.RegisterXLL(str(XLL_JUMP))):
        raise RuntimeError("Excel a refusé de charger le XLL JUMP.")

    limite = time.time() + TIMEOUT_UI
    tentative = 0

    while time.time() < limite:
        tentative += 1
        try:
            fenetre = fenetre_excel(pid)
            for onglet in fenetre.descendants(control_type="TabItem"):
                if nom_controle(onglet) == "jump":
                    logging.info("Onglet JUMP détecté après %s tentative(s).", tentative)
                    logging.info("Add-in JUMP chargé et onglet JUMP détecté.")
                    return
        except Exception:
            pass

        pythoncom.PumpWaitingMessages()
        time.sleep(0.5)

    raise RuntimeError("Le XLL est chargé mais l'onglet JUMP n'a pas été détecté.")


# ============================================================================
# RUBAN JUMP SANS SOURIS
# ============================================================================

def activer_onglet_jump(fenetre) -> None:
    """Active JUMP avec Select ou Invoke, sans clic physique."""
    limite = time.time() + TIMEOUT_UI

    while time.time() < limite:
        for onglet in fenetre.descendants(control_type="TabItem"):
            if nom_controle(onglet) != "jump":
                continue

            try:
                onglet.select()
                time.sleep(1)
                return
            except Exception:
                pass

            try:
                onglet.invoke()
                time.sleep(1)
                return
            except Exception:
                pass

        pythoncom.PumpWaitingMessages()
        time.sleep(0.25)

    raise RuntimeError("Onglet JUMP non invocable en arrière-plan.")


def ouvrir_panneau_statut_serveur(fenetre) -> None:
    """Ouvre le MenuItem NetUIAnchor Statut du serveur sans la souris."""
    candidats = []

    for controle in fenetre.descendants():
        try:
            if nom_controle(controle) != "statut du serveur":
                continue

            type_controle = str(controle.element_info.control_type or "")
            classe = classe_controle(controle)

            if type_controle == "MenuItem" and classe == "NetUIAnchor":
                candidats.append(controle)
        except Exception:
            pass

    if not candidats:
        raise RuntimeError(
            "Commande MenuItem 'Statut du serveur' de classe NetUIAnchor introuvable."
        )

    commande = candidats[0]
    logging.info("Ouverture du panneau 'Statut du serveur' sans souris.")

    erreurs = []

    # MenuItemWrapper n'expose pas forcément click(). On utilise directement
    # les patterns UI Automation disponibles, sans souris et sans focus global.
    try:
        commande.iface_invoke.Invoke()
        logging.info("Commande 'Statut du serveur' activée via UIA Invoke.")
        time.sleep(1)
        return
    except Exception as erreur:
        erreurs.append(f"UIA Invoke: {erreur!r}")

    try:
        commande.iface_selection_item.Select()
        logging.info("Commande 'Statut du serveur' activée via SelectionItem.Select.")
        time.sleep(1)
        return
    except Exception as erreur:
        erreurs.append(f"SelectionItem: {erreur!r}")

    try:
        commande.select()
        logging.info("Commande 'Statut du serveur' activée via select().")
        time.sleep(1)
        return
    except Exception as erreur:
        erreurs.append(f"select(): {erreur!r}")

    try:
        commande.iface_legacy_iaccessible.DoDefaultAction()
        logging.info("Commande 'Statut du serveur' activée via DoDefaultAction.")
        time.sleep(1)
        return
    except Exception as erreur:
        erreurs.append(f"Legacy: {erreur!r}")

    # Ce contrôle Office n'expose aucun pattern d'action. Dernier recours fiable :
    # ramener brièvement Excel à l'écran, effectuer un clic physique sur le contrôle,
    # puis restaurer immédiatement la position du pointeur. La fenêtre sera replacée
    # hors écran après la connexion.
    try:
        hwnd_excel = int(fenetre.handle)
        rectangle = fenetre.rectangle()
        largeur = max(1200, rectangle.width())
        hauteur = max(700, rectangle.height())
        position_curseur = win32api.GetCursorPos()

        win32gui.ShowWindow(hwnd_excel, win32con.SW_RESTORE)
        win32gui.SetWindowPos(
            hwnd_excel,
            win32con.HWND_TOP,
            20,
            20,
            largeur,
            hauteur,
            win32con.SWP_SHOWWINDOW,
        )
        time.sleep(0.5)
        commande.click_input()
        win32api.SetCursorPos(position_curseur)
        logging.info(
            "Commande 'Statut du serveur' activée par clic de secours ; "
            "le pointeur a été restauré."
        )
        time.sleep(1)
        return
    except Exception as erreur:
        erreurs.append(f"clic de secours: {erreur!r}")
        try:
            win32api.SetCursorPos(position_curseur)
        except Exception:
            pass

    raise RuntimeError(
        "Le contrôle 'Statut du serveur' refuse tous les patterns "
        "d'activation et le clic de secours. " + " | ".join(erreurs)
    )


def attendre_toolbar_statut(fenetre):
    """Trouve le ToolBar NetUIToolWindow identifié dans l'inventaire."""
    limite = time.time() + TIMEOUT_UI

    while time.time() < limite:
        for controle in fenetre.descendants(control_type="ToolBar"):
            try:
                if (
                    nom_controle(controle) == "statut du serveur"
                    and classe_controle(controle) == "NetUIToolWindow"
                    and controle.is_visible()
                ):
                    return controle
            except Exception:
                pass

        pythoncom.PumpWaitingMessages()
        time.sleep(0.25)

    raise RuntimeError("ToolBar 'Statut du serveur' NetUIToolWindow introuvable.")


def champs_toolbar_statut(toolbar) -> list:
    champs = []

    for controle in toolbar.descendants(control_type="Edit"):
        try:
            if (
                classe_controle(controle) == "NetUITextbox"
                and controle.is_visible()
                and controle.is_enabled()
            ):
                champs.append(controle)
        except Exception:
            pass

    champs.sort(key=lambda c: (c.rectangle().top, c.rectangle().left))
    return champs


def definir_texte_sans_souris(controle, valeur: str) -> None:
    """Ne bascule jamais vers type_keys, send_keys ou click_input."""
    try:
        controle.set_edit_text(valeur)
        return
    except Exception:
        pass

    try:
        controle.set_text(valeur)
        return
    except Exception:
        pass

    try:
        controle.set_window_text(valeur)
        return
    except Exception as erreur:
        raise RuntimeError(
            "Le champ ne supporte pas la saisie directe en arrière-plan."
        ) from erreur


def bouton_connexion_toolbar(toolbar):
    """Trouve le bouton par classe, texte normalisé et géométrie."""
    candidats = []

    for controle in toolbar.descendants():
        try:
            if str(controle.element_info.control_type or "") != "Button":
                continue
            if classe_controle(controle) != "NetUIRibbonButton":
                continue
            if not controle.is_visible() or not controle.is_enabled():
                continue
            if nom_controle(controle) == "se connecter":
                candidats.append(controle)
        except Exception:
            pass

    if not candidats:
        champs = champs_toolbar_statut(toolbar)
        if champs:
            bas_champs = max(champ.rectangle().bottom for champ in champs)

            for controle in toolbar.descendants():
                try:
                    if str(controle.element_info.control_type or "") != "Button":
                        continue
                    if classe_controle(controle) != "NetUIRibbonButton":
                        continue
                    if not controle.is_visible() or not controle.is_enabled():
                        continue

                    if controle.rectangle().top >= bas_champs:
                        candidats.append(controle)
                except Exception:
                    pass

    if not candidats:
        raise RuntimeError(
            "Bouton NetUIRibbonButton 'Se connecter' introuvable dans le panneau."
        )

    candidats.sort(key=lambda c: (c.rectangle().top, c.rectangle().left))
    return candidats[0]


def invoquer_controle_sans_souris(controle) -> None:
    """Invocation logique uniquement, sans click_input."""
    try:
        controle.invoke()
        return
    except Exception:
        pass

    try:
        controle.click()
        return
    except Exception as erreur:
        raise RuntimeError(
            "Le contrôle JUMP ne supporte pas l'invocation en arrière-plan."
        ) from erreur


def remplir_panneau_et_ouvrir_dialogue(pid: int, identifiant: str) -> None:
    fenetre = fenetre_excel(pid)
    activer_onglet_jump(fenetre)
    ouvrir_panneau_statut_serveur(fenetre)

    toolbar = attendre_toolbar_statut(fenetre)
    champs = champs_toolbar_statut(toolbar)

    logging.info("Panneau 'Statut du serveur' détecté avec %s champs.", len(champs))

    if len(champs) < 2:
        raise RuntimeError(
            f"Deux champs NetUITextbox attendus, trouvés : {len(champs)}."
        )

    definir_texte_sans_souris(champs[0], SERVEUR_JUMP)
    definir_texte_sans_souris(champs[1], identifiant)

    bouton = bouton_connexion_toolbar(toolbar)
    logging.info("Activation silencieuse du bouton 'Se connecter' du panneau.")
    invoquer_controle_sans_souris(bouton)
    time.sleep(1)


# ============================================================================
# MODALE JUMP SANS SOURIS
# ============================================================================

def attendre_fenetre_connexion_jump():
    titre_attendu = "jump - connexion au serveur"
    limite = time.time() + TIMEOUT_CONNEXION

    while time.time() < limite:
        for fenetre in Desktop(backend="win32").windows(visible_only=True):
            try:
                if normaliser_texte(fenetre.window_text()) == titre_attendu:
                    logging.info(
                        "Fenêtre 'JUMP - Connexion au serveur' détectée en Win32. PID : %s",
                        fenetre.process_id(),
                    )
                    return fenetre
            except Exception:
                pass

        pythoncom.PumpWaitingMessages()
        time.sleep(0.25)

    raise RuntimeError("Fenêtre 'JUMP - Connexion au serveur' introuvable.")


def controles_modale_win32(fenetre):
    champs = []
    boutons = []

    for controle in fenetre.descendants():
        try:
            if not controle.is_visible() or not controle.is_enabled():
                continue

            classe_amicale = normaliser_texte(controle.friendly_class_name())
            classe_win32 = normaliser_texte(controle.class_name())

            if classe_amicale in {"edit", "textbox"} or classe_win32 == "edit":
                champs.append(controle)
            elif classe_amicale == "button" or classe_win32 == "button":
                boutons.append(controle)
        except Exception:
            pass

    champs.sort(key=lambda c: (c.rectangle().top, c.rectangle().left))
    boutons.sort(key=lambda c: (c.rectangle().top, c.rectangle().left))

    return champs, boutons


def bouton_modal_exact(boutons, texte: str):
    cible = normaliser_texte(texte)

    for bouton in boutons:
        try:
            if normaliser_texte(bouton.window_text()) == cible:
                return bouton
        except Exception:
            pass

    return None


def cliquer_bouton_win32_sans_souris(bouton) -> None:
    """Envoie BM_CLICK directement au contrôle Windows."""
    try:
        bouton.send_message(BM_CLICK)
        return
    except Exception:
        pass

    try:
        bouton.click()
        return
    except Exception as erreur:
        raise RuntimeError(
            "Le bouton modal JUMP refuse BM_CLICK en arrière-plan."
        ) from erreur


def attendre_disparition_modale(fenetre) -> None:
    limite = time.time() + TIMEOUT_CONNEXION

    while time.time() < limite:
        try:
            if not fenetre.exists() or not fenetre.is_visible():
                logging.info("Fenêtre de connexion JUMP fermée.")
                return
        except Exception:
            logging.info("Fenêtre de connexion JUMP fermée.")
            return

        pythoncom.PumpWaitingMessages()
        time.sleep(0.3)

    raise RuntimeError(
        "La fenêtre de connexion est toujours ouverte. "
        "Le mot de passe peut être incorrect ou un message est affiché."
    )


def verifier_connexion(pid: int) -> None:
    fenetre = fenetre_excel(pid)
    activer_onglet_jump(fenetre)
    ouvrir_panneau_statut_serveur(fenetre)
    toolbar = attendre_toolbar_statut(fenetre)

    for controle in toolbar.descendants():
        try:
            if (
                str(controle.element_info.control_type or "") == "Button"
                and classe_controle(controle) == "NetUIRibbonButton"
                and nom_controle(controle) == "se deconnecter"
                and controle.is_visible()
            ):
                logging.info("Connexion JUMP confirmée par 'Se déconnecter'.")
                return
        except Exception:
            pass

    raise RuntimeError(
        "La modale s'est fermée, mais le bouton 'Se déconnecter' n'est pas apparu."
    )


def replacer_excel_hors_ecran(pid: int) -> None:
    """Replace Excel hors écran après les interactions de connexion."""
    try:
        fenetre = fenetre_excel(pid)
        r = fenetre.rectangle()
        win32gui.SetWindowPos(
            int(fenetre.handle),
            win32con.HWND_BOTTOM,
            POSITION_HORS_ECRAN,
            POSITION_HORS_ECRAN,
            max(1200, r.width()),
            max(700, r.height()),
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )
        logging.info("Excel replacé hors écran après authentification.")
    except Exception as erreur:
        logging.warning("Impossible de replacer Excel hors écran : %s", erreur)


def connecter_jump(pid: int, identifiant: str, mot_de_passe: str) -> None:
    remplir_panneau_et_ouvrir_dialogue(pid, identifiant)

    modale = attendre_fenetre_connexion_jump()
    champs, boutons = controles_modale_win32(modale)

    logging.info(
        "Fenêtre modale JUMP : %s champ(s), %s bouton(s) détecté(s).",
        len(champs),
        len(boutons),
    )

    if not champs:
        raise RuntimeError("Champ de mot de passe introuvable dans la fenêtre modale.")

    # Le backend Win32 expose uniquement le champ Mot de passe.
    champ_mot_de_passe = champs[-1]
    definir_texte_sans_souris(champ_mot_de_passe, mot_de_passe)
    logging.info("Mot de passe renseigné sans clavier physique.")

    bouton = bouton_modal_exact(boutons, "Se connecter")
    if bouton is None:
        raise RuntimeError("Bouton modal 'Se connecter' introuvable.")

    logging.info("Activation silencieuse du bouton modal 'Se connecter'.")
    cliquer_bouton_win32_sans_souris(bouton)
    attendre_disparition_modale(modale)
    time.sleep(1)

    verifier_connexion(pid)
    replacer_excel_hors_ecran(pid)


# ============================================================================
# RECALCUL DES FICHIERS
# ============================================================================

def attendre_calcul(excel) -> None:
    limite = time.time() + TIMEOUT_CALCUL

    try:
        excel.CalculateUntilAsyncQueriesDone()
    except Exception:
        pass

    while time.time() < limite:
        pythoncom.PumpWaitingMessages()

        try:
            if int(excel.CalculationState) == XL_DONE and bool(excel.Ready):
                return
        except Exception:
            pass

        time.sleep(0.5)

    raise TimeoutError("Délai de calcul Excel/JUMP dépassé.")


def traiter_fichier(excel, fichier: Path) -> bool:
    classeur = None

    try:
        if not fichier.exists():
            raise FileNotFoundError(f"Fichier introuvable : {fichier}")

        logging.info("Ouverture : %s", fichier)

        classeur = excel.Workbooks.Open(
            str(fichier),
            UpdateLinks=0,
            ReadOnly=False,
            IgnoreReadOnlyRecommended=True,
        )
        classeur.Activate()

        try:
            classeur.RefreshAll()
        except Exception:
            logging.warning("RefreshAll non exécuté pour %s", fichier.name)

        excel.CalculateFullRebuild()
        attendre_calcul(excel)

        logging.info("Stabilisation JUMP : %s seconde(s).", DELAI_STABILISATION_JUMP)
        limite = time.time() + DELAI_STABILISATION_JUMP

        while time.time() < limite:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.25)

        attendre_calcul(excel)
        classeur.Save()

        logging.info("Fichier enregistré : %s", fichier)
        return True

    except Exception:
        logging.exception("Échec du fichier : %s", fichier)
        return False

    finally:
        if classeur is not None:
            try:
                classeur.Close(SaveChanges=False)
            except Exception:
                logging.exception("Fermeture impossible : %s", fichier)


# ============================================================================
# DÉCONNEXION ET FERMETURE
# ============================================================================

def deconnecter_jump(pid: int) -> None:
    """Déconnexion silencieuse par le bouton du ToolBar."""
    try:
        fenetre = fenetre_excel(pid)
        activer_onglet_jump(fenetre)
        ouvrir_panneau_statut_serveur(fenetre)
        toolbar = attendre_toolbar_statut(fenetre)

        for controle in toolbar.descendants():
            try:
                if (
                    str(controle.element_info.control_type or "") == "Button"
                    and classe_controle(controle) == "NetUIRibbonButton"
                    and nom_controle(controle) == "se deconnecter"
                    and controle.is_visible()
                    and controle.is_enabled()
                ):
                    logging.info("Activation silencieuse de 'Se déconnecter'.")
                    invoquer_controle_sans_souris(controle)
                    time.sleep(1)
                    return
            except Exception:
                pass

        logging.warning(
            "Bouton 'Se déconnecter' introuvable. "
            "La fermeture de l'instance terminera la session."
        )

    except Exception:
        logging.warning(
            "Déconnexion explicite impossible. "
            "La fermeture de l'instance terminera la session."
        )


def fermer_excel(
    excel,
    pid: Optional[int],
) -> None:
    """
    Déconnecte JUMP puis ferme Excel.

    Excel peut rester temporairement occupé après la déconnexion JUMP.
    La fermeture est donc retentée plusieurs fois.
    """

    if excel is None:
        return

    if not FERMER_EXCEL_A_LA_FIN:
        logging.info(
            "Excel reste ouvert selon la configuration."
        )
        return

    if pid is not None:
        deconnecter_jump(
            pid
        )

        logging.info(
            "Attente de la fin de la déconnexion JUMP."
        )

        limite = time.time() + 5

        while time.time() < limite:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.25)

    derniere_erreur = None

    for tentative in range(
        1,
        6,
    ):
        try:
            logging.info(
                "Tentative de fermeture d'Excel %s/5.",
                tentative,
            )

            try:
                excel.DisplayAlerts = False
            except Exception:
                pass

            try:
                excel.EnableEvents = True
            except Exception:
                pass

            excel.Quit()

            logging.info(
                "Excel fermé."
            )

            return

        except Exception as error:
            derniere_erreur = error

            logging.warning(
                "Excel est encore occupé lors de la tentative "
                "%s/5 : %s",
                tentative,
                error,
            )

            limite = time.time() + 2

            while time.time() < limite:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.25)

    logging.warning(
        "Excel n'a pas pu être fermé proprement après "
        "5 tentatives. Le traitement principal reste terminé. "
        "Dernière erreur : %s",
        derniere_erreur,
    )


# ============================================================================
# PROGRAMME PRINCIPAL
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--set-credentials",
        action="store_true",
        help="Enregistre ou remplace le mot de passe dans le coffre Windows.",
    )
    args = parser.parse_args()

    if args.set_credentials:
        enregistrer_mot_de_passe()
        return 0

    configurer_logs()

    excel = None
    pid: Optional[int] = None
    classeur_temporaire = None

    try:
        mot_de_passe = lire_mot_de_passe()
        fichiers = lister_fichiers()

        if not fichiers:
            raise RuntimeError("Aucun fichier Excel à traiter.")

        logging.info("%s fichier(s) à traiter.", len(fichiers))

        excel, pid, classeur_temporaire = creer_excel()
        charger_xll(excel, pid)
        connecter_jump(pid, LOGIN_JUMP, mot_de_passe)

        if classeur_temporaire is not None:
            classeur_temporaire.Close(SaveChanges=False)
            classeur_temporaire = None

        echecs = [
            fichier
            for fichier in fichiers
            if not traiter_fichier(excel, fichier)
        ]

        logging.info(
            "Succès : %s | Échecs : %s",
            len(fichiers) - len(echecs),
            len(echecs),
        )

        return 1 if echecs else 0

    except Exception:
        logging.exception("Arrêt du script sur erreur.")
        return 1

    finally:
        if classeur_temporaire is not None:
            try:
                classeur_temporaire.Close(SaveChanges=False)
            except Exception:
                pass

        fermer_excel(excel, pid)

        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
