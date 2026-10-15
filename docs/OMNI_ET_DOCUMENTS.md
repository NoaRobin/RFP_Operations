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

### Comment le site range les documents (relevé sur le site public, octobre 2026)
- **Page de chaque part** : `https://am.eu.rothschildandco.com/fr/nos-fonds/{fonds}/{part}/` (en anglais `/en/our-funds/…`),
  ex. `…/nos-fonds/r-co-valor/c-eur/`. Le nom du fonds et de la part donnent l'adresse (minuscules, tirets, sans accents).
  La rubrique « Téléchargements » liste les PDF de la part : DIC PRIIPs, prospectus, reportings, documents SFDR,
  rapports annuels et semestriels.
- **Adresse des PDF** : `{PRÉFIXE}_{GUID}_{PAYS}_{LANGUE}[_{AAAAMMJJ}].pdf`, servie à deux endroits identiques :
  `https://docs.am.eu.rothschildandco.com/…` et `https://am.eu.rothschildandco.com/docs/…`.
  - préfixes (code source de la page R-co Valor) : `DIPR` (DIC), `REPM` (reporting mensuel), `PERFNAV` (performances) par part ;
    `PROS` (prospectus), `SFDR` (annexe), `SFDR10` (article 10), `RPSFDR` (rapport périodique SFDR), `RAAN` (rapport annuel),
    `RASA` (rapport semestriel) par fonds ;
- **Écran d'accueil** : tant que le visiteur n'a pas choisi son profil (« Particuliers / Professionnels »), le site renvoie
  cet écran (redirection `/disclaimer/`, `let user_type = ''`) au lieu des pages et la recherche ne répond pas. Le choix est
  un formulaire `POST /fr/` (`a=change_user_type`, `country=fr`, `lang=fr`, `user_type=professional|individual`) qui pose
  un cookie de session. L'app le fait au premier accès (profil : `FUNDSHOP_PROFILE`, « professional » par défaut) et le
  refait si le site le redemande.
- **Recherche du site** : `GET /api/data-fund/?query={ISIN}&country=fr&language=fr&user_type=individual` renvoie le fonds
  (`fund_rewrite`, `fund_title`), la part (`share_title`) et le nom du fichier DIC (`DIPR`). La page du fonds contient
  un menu « Part … » (`<option value="/fr/nos-fonds/{fonds}/{part}/">`) ; la part par défaut est la page du fonds elle-même.
  Les liens « Téléchargements » sont écrits en clair dans la page (pas besoin de navigateur).
  - suffixe **PAYS_LANGUE** : `FR_FR` (France, français), `FR_EN` (France, anglais), `BE_FR`, `ES_EN`, `IT_EN`… ;
  - reporting : sans date = dernier mois publié ; avec date = mois précis (dernier jour ouvré, ex. `_20260130`).

### Ce que fait Merlin (page `/documents`, automatisation « Documents des fonds »)
**Plus de navigateur.** Cliquer dans le site (Playwright) était lent et fragile : délais de téléchargement, pages qui
changent, fonds introuvables. L'app va droit à l'adresse du PDF.

1. **Réseau du poste** (`merlin/fundshop/net.py`) :
   1. Python avec les certificats et le proxy de Windows (`truststore`, paramètres Internet) : rapide, 4 téléchargements à la fois ;
   2. sinon la connexion de Windows elle-même (WinINet, celle d'Edge : proxy d'entreprise, script PAC, authentification
      automatique). Le premier qui répond est gardé.
2. **Trouver l'adresse** (`resolver.py`), dans l'ordre :
   1. adresse mémorisée (`data/fundshop/learned.json`) ;
   2. **la recherche du site** (API `data-fund` par ISIN) puis **la page de la part** (menu des parts), lue comme on le ferait à la main (rubrique « Téléchargements ») : tous ses liens sont
      mémorisés d'un coup (DIC, reportings, prospectus, SFDR…), puis la page du fonds ;
   3. adresse déduite des identifiants Product Info (`PI_OUT_Share.pi_shareid`… ; la colonne qui marche est retenue) ;
   4. **« J'ai le lien »** : l'utilisateur colle une fois le lien d'un PDF de la part (ou la page du fonds). L'app en déduit
      l'adresse de tous les documents de cette part, pour tous les mois.

   Chaque DIC lu au passage apprend aussi l'adresse des autres parts qu'il cite.
3. **Vérification de chaque PDF** : vrai PDF, taille minimale, ISIN de la part (le DIC d'une autre part est refusé).
4. **Quand ça ne marche pas** (`problems.py`), chaque ligne dit pourquoi et quoi faire, en une phrase :
   proxy, certificat, site injoignable, pas de réponse, accès refusé, adresse encore inconnue, document pas encore publié
   (reportings), document d'une autre part, page au lieu d'un PDF, fichier déjà présent, dossier inaccessible.
   Avant de lancer, l'app vérifie le dossier et le site : si le réseau bloque, une seule explication plutôt que 50 échecs.
   Le bouton « Tester la connexion » fait le même contrôle à la demande.
5. **La liste** : dans l'app, on choisit une part et l'app affiche **ce que le site publie réellement pour elle** (types, mois en ligne) : on coche, impossible de demander ce qui n'existe pas (enregistrement automatique), ou dans Excel avec la **liste vierge** :
   la part, le document et le mois se choisissent dans des listes déroulantes, l'ISIN se remplit tout seul ; onglet « Aide ».
   L'ancienne « Liste de courses » s'importe aussi. « Ma liste en Excel » exporte la liste actuelle dans le même format.
6. **Une fois ou en boucle** : « Mois précédent » / « Il y a 2 mois » sont gardés relatifs ; « Programmer chaque mois »
   relance la liste. Les fichiers déjà présents ne sont jamais remplacés sans la case « Remplacer » (écriture atomique).
7. **Le complétueur RFI** utilise le même mécanisme pour le DIC et le prospectus d'une part.

**À CONFIRMER**
- **GUID** : que les GUID des adresses sont bien ceux de Product Info. L'app le vérifie d'elle-même et apprend la bonne colonne.
- **Versions anglaises** : `FR_EN` d'abord, puis `LU_EN`, `BE_EN`, `CH_EN`, `ES_EN`, `IT_EN`.
- **Rapport périodique SFDR** : son préfixe est inconnu ; il faut coller une fois son lien (« J'ai le lien »).
- **Date des reportings** : fin de mois calendaire ou dernier jour ouvré ? Les deux sont essayées.

**Pour démarrer sur le poste**
- Cliquer « Tester la connexion » : il dit tout de suite si le réseau, le dossier et le site sont accessibles.
- (Options) reprendre `resultats_telechargement.csv` de l'ancien script : ses adresses deviennent directes.
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
