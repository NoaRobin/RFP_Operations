# OMNI mensuel, documents du site et deuxième avis Copilot

Ce document reprend trois scripts historiques et les remet en question avant de les intégrer à Merlin :
- `JUMP_OMNI.py` ;
- `OMNI_MENSUEL.py` ;
- `telecharger_documents_fonds.py`.

Les scripts d'origine sont conservés tels quels à la racine. Merlin ne les modifie pas : il les remplace, ou les appelle en mode de secours.

---

## 1. OMNI mensuel

### Le process actuel, tel que les scripts le font
1. **`OMNI_MENSUEL.py`** calcule la période : le mois précédent, avec pour date de clôture le dernier jour ouvré, sans tenir compte des fériés.
2. Il exige **un seul** `Holdings*.xlsx` dans `03 - Sources`, puis lance `JUMP_OMNI.py`.
3. **`JUMP_OMNI.py`** pilote Excel par l'interface (pywinauto et COM) :
   - Excel est ouvert hors écran ;
   - clic sur le ruban « Statut du serveur » ;
   - connexion au complément JUMP, avec le mot de passe lu dans le trousseau Windows ;
   - `RefreshAll`, puis enregistrement du classeur.
4. **Contrôle de réussite** : la date de modification du fichier a changé.
5. Le fichier est copié vers `3 - Consultants/<année>/Q<n> <année>/Holdings/Holdings M_YYYY.xlsx`. L'arborescence du trimestre est recréée sur le modèle du trimestre précédent.
6. **Outlook** : recherche dans tous les dossiers sur 120 jours, selon ces critères :
   - expéditeur fixe ;
   - objet contenant « perf » et « omni » ;
   - reçu entre le 1er et le 20 du mois suivant.

   Les pièces jointes NET et GROSS sont enregistrées dans `Performances/Monthly perf NET|GROSS of fees_YYYYMMDD.xlsx`.
7. **Contrôles fixes** :
   - le fichier Holdings compte entre 2 000 et 4 000 lignes ;
   - aucune performance ne dépasse 1 en valeur absolue.

   Le statut est PARTIEL s'il manque une performance. Le script écrit aussi un rapport JSON et pose un verrou.

### Ce qui ne va pas
| Point | Risque |
|---|---|
| Automatisation par clics dans Excel (ruban, fenêtre de connexion) | Une mise à jour d'Excel ou de JUMP, une fenêtre qui change de titre ou un écran verrouillé, et tout s'arrête. Impossible à lancer sans session ouverte. |
| Date de clôture = « dernier jour de semaine » | Faux les mois où ce jour est férié : l'inventaire JUMP réel est à une autre date. |
| Contrôle « le fichier a été modifié » | Un rafraîchissement partiel ou en erreur modifie aussi le fichier : le contrôle passe à tort. |
| Seuils fixes 2 000–4 000 lignes | Ils dérivent avec la gamme (fonds lancés ou fermés) et ne détectent ni un fonds manquant ni des poids faux. |
| \|perf\| > 1 | Ne dit pas si la performance est la bonne, seulement si elle est absurde. |
| Recherche Outlook large (tous dossiers, 120 jours) | Lente, et sensible à un transfert ou à un « RE: ». La date de réception ne garantit pas le mois de la donnée. |
| Le fichier existant est écrasé | Une relance tardive efface un fichier déjà envoyé. |

### Ce que fait Merlin (automatisation « OMNI mensuel », page `/omni`)
1. **Période** :
   - l'utilisateur choisit le mois, ou laisse vide pour le mois précédent (adapté au mode programmé) ;
   - la date de clôture est la **vraie date d'inventaire** : `MAX(DATE_INVENTAIRE)` du mois dans `JUMP_portfolio_holdings` ;
   - le dernier jour ouvré ne sert qu'en repli, et le rapport indique alors ce repli.
2. **Holdings** :
   - **Fabric** (par défaut) : lecture directe de `JUMP_portfolio_holdings` à cette date. Le fichier du mois précédent sert de **gabarit** : mêmes colonnes, dans le même ordre. Ni Excel ni clics ne sont nécessaires.
   - **JUMP Excel** : lance le script historique (`OMNI_JUMP_SCRIPT`) quand un gabarit strictement identique est exigé.
   - **Ne pas refaire** : utile pour relancer seulement la partie performances.
3. **Performances** :
   - d'abord un **dossier de dépôt** (`OMNI_INBOX`), dans lequel le nom de fichier doit contenir la période ;
   - sinon **Outlook**, filtré par expéditeur (`OMNI_SENDER`), mots de l'objet (`OMNI_SUBJECT_WORDS`) et fenêtre de réception (`Items.Restrict`, sans parcourir tous les dossiers).
4. **Contrôles relatifs**, au lieu des seuils fixes :
   - nombre de lignes à ±25 % du mois précédent ;
   - fonds disparus ;
   - somme des poids par fonds entre 95 et 105 % ;
   - **recoupement NET avec la VL JUMP** : la performance mensuelle de chaque ISIN est comparée au rendement calculé sur les VL, avec une tolérance d'un point de base. Résultat : « concorde », « écarts » ou « non comparable ».
5. **Rangement** :
   - même arborescence trimestrielle ;
   - écriture atomique ;
   - **jamais d'écrasement** sans la case « Remplacer » ;
   - rapport `_controles/Controle_OMNI_YYYYMMDD.json`, avec un statut OK ou PARTIEL.
6. **En boucle** : bouton « Programmer chaque mois » (planificateur de l'app), avec le mois laissé vide.

**À CONFIRMER**
- **Colonnes du gabarit** : la correspondance entre les en-têtes du fichier Holdings et les colonnes Fabric est faite par synonymes (`merlin/omni/holdings.py`). Une colonne non reconnue est signalée, jamais inventée.
- **Unité de `POIDS_LIGNE_EXPO`** : % ou fraction. Le contrôle 95–105 % est en mode « attention » tant que ce n'est pas confirmé.
- **Fichiers de performance** : la colonne ISIN et la ligne de performance mensuelle doivent être validées sur un vrai fichier reçu.

---

## 2. Documents du site (DIC, prospectus, reportings, SFDR)

### Le script actuel
`telecharger_documents_fonds.py` lit « Liste de courses.xlsx », puis pilote Edge avec Playwright :
1. recherche de l'ISIN ;
2. ouverture de la page du fonds, onglet « Documentation » ;
3. choix de la section et du mois ;
4. clic sur le lien, puis téléchargement.

Le journal du dernier passage compte **303 erreurs**, dont :
- délais d'attente dépassés au téléchargement ;
- un bug `casefold` sur des octets ;
- fonds introuvable ;
- mauvaise page ouverte.

### Le constat qui change tout
Les adresses réussies (`resultats_telechargement.csv`, journal) suivent toutes un même modèle :

```
https://docs.am.eu.rothschildandco.com/{PRÉFIXE}_{GUID}_{LANGUE}_{PAYS}[_{AAAAMMJJ}].pdf
```

| Préfixe | Document | GUID de… |
|---|---|---|
| `DIPR` | DIC PRIIPs | la part |
| `PROS` | prospectus | du produit |
| `REPM` | reporting mensuel (+ date de fin de mois) | de la part |
| `SFDR` | annexe SFDR | du produit |
| `SFDR10` | article 10 SFDR | du produit |

Le navigateur n'est donc **pas nécessaire** dès que l'on connaît le GUID.

### Ce que fait Merlin (page `/documents`, automatisation « Documents des fonds »)
1. **Ordre des stratégies** :
   1. **adresse apprise** : mémoire `data/fundshop/learned.json`, alimentée par chaque succès et par l'import du CSV historique ;
   2. **adresse construite** à partir des GUID de Product Info. L'app essaie les colonnes `PI_OUT_Share.pi_shareid` / `Id` et `pi_out_product_active.pi_productid` / `Id` / `Product_Global_ID`, et **retient celle qui fonctionne** ;
   3. **page du fonds** : liens PDF portant le bon préfixe ;
   4. **navigateur** en dernier recours, seulement pour découvrir l'adresse ; le téléchargement se fait ensuite en HTTP.
2. **Vérification de chaque PDF** :
   - une taille minimale ;
   - un PDF valide ;
   - aucun ISIN d'une autre part dans le document. Le DIC d'une autre part est refusé.
3. **Parallélisme** : 4 téléchargements HTTP à la fois. Les échecs sont ensuite repris un par un avec le navigateur.
4. **Fichiers** : « seulement les absents » par défaut, aucun écrasement sans « Écraser », écriture atomique. Le rapport Excel indique pour chaque ligne le statut (OK, DÉJÀ PRÉSENT, ÉCHEC, IGNORÉ), la stratégie et l'adresse.
5. **Ponctuel ou en boucle** : chaque ligne porte un mois **précis** (« 2026-07 ») ou **relatif** (« M-1 », « M-2 »).
   - « Télécharger maintenant » lance la liste une fois.
   - « Programmer (en boucle) » la relance chaque mois, et M-1 désigne alors toujours le mois écoulé.
   - La liste se construit dans l'app (recherche de fonds) ou s'importe depuis l'Excel historique.
6. **Le complétueur RFI** utilise le même mécanisme pour trouver le DIC et le prospectus d'une part, sans navigateur.

**À CONFIRMER**
- **GUID** : que les GUID des adresses sont bien ceux de Product Info. L'app le vérifie d'elle-même et apprend la bonne colonne.
- **Versions anglaises** : les codes `EN_FR`, `EN_GB`, `EN_LU`… sont essayés tour à tour.
- **Rapport périodique SFDR** : son préfixe est inconnu ; ce document passe donc par la page du fonds ou le navigateur.
- **Date des reportings** : fin de mois calendaire ou dernier jour ouvré ? Les deux sont essayées.

**Pour démarrer sur le poste**
- Importer `resultats_telechargement.csv` (« Apprendre du CSV ») : toutes les adresses déjà trouvées deviennent directes.
- Renseigner `FUNDSHOP_DIR`, le dossier FundShop de destination.

---

## 3. Deuxième avis Copilot (Microsoft 365)

Copilot entreprise tourne sur le poste et n'a pas d'API utilisable par l'app. Le circuit passe donc par un fichier, avec des garde-fous à l'import.

1. **Préparer le pack** : dans l'atelier de revue, « Préparer le pack Copilot » produit un zip qui contient :
   - `Questions_Copilot.xlsx`, avec trois onglets :
     - « Consignes Copilot » : prompt prêt à l'emploi ;
     - « Questions » : questions à vérifier ou sans réponse, réponse de l'app, source, options autorisées ;
     - « Documents » ;
   - les PDF du DIC et du prospectus de la part ;
   - un LISEZ-MOI.
2. **Faire travailler Copilot** : déposer le dossier dans OneDrive, ouvrir le classeur et demander à Copilot de suivre l'onglet « Consignes ». Il remplit trois colonnes :
   - « Réponse Copilot » ;
   - « Source citée (document, page) » ;
   - « Confiance ».
3. **Réimporter** : bouton « Importer les réponses Copilot » (le `.xlsx` ou le zip). Règles appliquées :
   - **une réponse sans source citée est écartée** ;
   - « NON TROUVÉ » n'est jamais écrit ;
   - pour une liste déroulante, la réponse doit correspondre à une option du client, sinon elle est écartée ;
   - une réponse retenue arrive **toujours « à vérifier »**, jamais en automatique, avec la citation ;
   - si Copilot contredit la proposition de l'app, l'**incohérence** est affichée ;
   - une réponse Copilot validée n'entre pas dans la bibliothèque des réponses réutilisables.

L'outil sert à **confirmer** ou à **compléter** des réponses lues dans le DIC ou le prospectus. Il ne remplace pas Fabric : quand Fabric a la donnée, c'est Fabric qui fait foi.
