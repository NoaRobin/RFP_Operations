"""Documents officiels des fonds (DIC PRIIPs, prospectus) : recherche, lecture déterministe, recoupement avec Fabric.

Aucune IA : le DIC suit un gabarit réglementé (PRIIPs), chaque champ est lu par expression régulière, avec sa page
et son extrait comme preuve. Un fait de document ne remplace jamais Fabric en silence : il le confirme (preuve double),
le contredit (incohérence affichée) ou comble un vide (« à vérifier », source citée).
"""
from .model import DocumentRef, Fact

__all__ = ["DocumentRef", "Fact"]
