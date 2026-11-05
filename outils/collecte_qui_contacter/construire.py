"""Reconstruit Collecte_Qui_Contacter.bat = _modele.bat.txt + collecte.py (un seul fichier à copier sur SharePoint).
Lancer après toute modification de collecte.py :  python outils/collecte_qui_contacter/construire.py"""
from pathlib import Path

here = Path(__file__).resolve().parent
bat = (here / "_modele.bat.txt").read_text(encoding="utf-8").rstrip() + "\n#__PYTHON__\n" + (here / "collecte.py").read_text(encoding="utf-8")
(here / "Collecte_Qui_Contacter.bat").write_text(bat.replace("\r\n", "\n"), encoding="utf-8", newline="\r\n")
print("Collecte_Qui_Contacter.bat reconstruit")
