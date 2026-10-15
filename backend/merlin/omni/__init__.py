"""OMNI mensuel : Holdings du mois, performances NET et GROSS, rangés dans l'arborescence trimestrielle des consultants.

Reprise et challenge de OMNI_MENSUEL.py + JUMP_OMNI.py (scripts historiques conservés tels quels à la racine) :
  - Holdings : lus directement dans Fabric (JUMP_portfolio_holdings, chargé depuis JUMP) à la vraie date d'inventaire
    du mois, au lieu de piloter le complément Excel JUMP à la souris (fenêtre hors écran, mot de passe, ruban). Le
    gabarit du mois précédent fixe l'ordre et les libellés des colonnes ; le mode « JUMP Excel » reste disponible.
  - Date d'arrêté : la dernière date d'inventaire réelle du mois dans JUMP (jours fériés compris), pas « le dernier
    jour ouvré » calculé.
  - Performances NET / GROSS : dossier de dépôt, puis Outlook (filtre côté serveur sur l'expéditeur et la période).
  - Contrôles : comparés au mois précédent (lignes, fonds disparus, poids par fonds) et aux données JUMP (performance
    NET recalculée depuis les VL) au lieu de seuils fixes.
  - Rien n'est écrasé sans demande ; écriture atomique ; rapport de contrôle ; statut OK / PARTIEL / ÉCHEC.
"""
