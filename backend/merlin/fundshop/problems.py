"""Quand un document n'arrive pas : pourquoi, en une phrase, et quoi faire. Une seule source pour l'app, le rapport Excel
et le journal."""
from __future__ import annotations

from dataclasses import asdict, dataclass

NETWORK = {"proxy", "certificat", "hors-ligne", "delai", "reseau", "refuse"}


@dataclass
class Problem:
    code: str
    title: str
    why: str
    fix: str
    link: str = ""  # page à ouvrir pour vérifier (page du fonds, lien essayé)

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.title}. {self.why} → {self.fix}"


class DocumentProblem(Exception):
    def __init__(self, problem: Problem):
        super().__init__(str(problem))
        self.problem = problem


def problem(code: str, *, host: str = "", doc: str = "", period: str = "", status: int = 0, isins: str = "", path: str = "",
            detail: str = "", link: str = "") -> Problem:
    pour = f" pour {period}" if period else ""
    texts = {
        "proxy": ("Le réseau de l'entreprise bloque l'app",
                  f"Le proxy n'a pas laissé passer la demande vers {host}, ni par Python ni par la connexion de Windows.",
                  "Ouvrez le lien dans Edge. S'il s'ouvre, signalez à l'informatique que l'app (Python) doit pouvoir joindre ce site."),
        "certificat": ("Connexion sécurisée refusée",
                       f"Le certificat de {host} n'a pas pu être vérifié (le réseau de l'entreprise inspecte les connexions).",
                       "Relancez l'app avec run.bat : il installe ce qu'il faut pour utiliser les certificats de Windows."),
        "hors-ligne": ("Site injoignable",
                       f"Le poste n'arrive pas à joindre {host} : pas de réseau, VPN coupé ou adresse du site erronée.",
                       "Vérifiez la connexion (VPN), puis relancez."),
        "delai": ("Le site ne répond pas", f"{host} n'a pas répondu à temps.", "Réessayez dans quelques minutes."),
        "reseau": ("Problème de réseau", f"La demande vers {host} a échoué ({detail[:120]}).", "Réessayez ; si ça persiste, ouvrez le lien dans Edge."),
        "refuse": ("Accès refusé par le site", f"Le site a répondu « erreur {status} ».", "Ouvrez le lien dans Edge pour voir le message affiché."),
        "adresse-inconnue": ("Adresse du document encore inconnue",
                             "L'app ne sait pas encore où le site range les documents de cette part.",
                             "Sur la page du fonds, faites clic droit → « Copier le lien » sur un PDF de cette part, puis « J'ai le lien ». "
                             "Une seule fois : ensuite l'app retrouve tous ses documents, chaque mois."),
        "absent": (f"Pas sur le site{pour}",
                   f"Le site ne propose pas « {doc} » pour cette part{pour}.",
                   "Les reportings arrivent en général dans les premiers jours du mois suivant : réessayez plus tard ou choisissez "
                   "un mois plus ancien." if period else "Vérifiez sur la page du fonds que ce document existe pour cette part."),
        "autre-part": ("Document d'une autre part",
                       f"Le PDF trouvé concerne une autre part ({isins}) : il n'a pas été gardé.",
                       "Collez le lien du bon document avec « J'ai le lien »."),
        "pas-pdf": ("Le site a renvoyé une page au lieu du PDF",
                    "C'est souvent une page d'erreur, de connexion ou de blocage du proxy.",
                    "Ouvrez le lien dans Edge pour voir ce qui s'affiche."),
        "deja": ("Déjà dans le dossier", "Un fichier du même nom existe : il n'a pas été remplacé.",
                 "Cochez « Remplacer » sur la ligne pour le mettre à jour."),
        "mois": ("Mois manquant", f"« {doc} » change chaque mois : il faut dire lequel.",
                 "Choisissez « Mois précédent » (idéal en boucle) ou un mois précis."),
        "dossier": ("Impossible d'enregistrer le fichier", f"Le dossier « {path} » est inaccessible ({detail[:120]}).",
                    "Vérifiez que le dossier existe et qu'il est synchronisé (OneDrive/SharePoint), ou changez FUNDSHOP_DIR dans .env."),
    }
    title, why, fix = texts[code]
    return Problem(code, title, why, fix, link)


# Ordre de gravité quand plusieurs essais ont échoué pour des raisons différentes : la plus utile à l'utilisateur d'abord
PRIORITY = ["proxy", "certificat", "hors-ligne", "delai", "reseau", "refuse", "autre-part", "pas-pdf", "absent", "adresse-inconnue"]
