"""Documents des fonds sur le site public : DIC PRIIPs, prospectus, reportings, documents SFDR — à la carte, ou en boucle.

Méthode (challenge du script historique telecharger_documents_fonds.py, qui pilotait Edge clic par clic) :
  1. **Adresse directe** : le site sert ses PDF à des adresses prévisibles
     https://docs.am.eu.rothschildandco.com/{PREFIXE}_{GUID}_{LANGUE}_{PAYS}[_{AAAAMMJJ}].pdf
     (DIPR = DIC, PROS = prospectus, REPM = reporting mensuel, SFDR = annexe, SFDR10 = article 10), le GUID étant celui
     de la part ou du fonds. L'app essaie les identifiants Product Info (Dynamics) et apprend lequel est le bon.
  2. **Adresses apprises** : chaque téléchargement réussi mémorise le GUID de la part / du fonds (et les résultats du
     script historique peuvent être importés) : la fois suivante, un simple appel HTTP suffit.
  3. **Navigateur** (dernier recours, Playwright) : même parcours que le script historique, mais seulement pour
     découvrir l'adresse, puis téléchargement HTTP vérifié.
Chaque PDF est vérifié (signature, taille, ISIN de la part dans le texte pour les documents de part) avant d'être gardé.
"""
