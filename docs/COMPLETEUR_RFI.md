# Compléteur RFI — méthode

Objectif : **le taux de complétion le plus élevé possible, sans erreur.** Ce document décrit le moteur, pourquoi il a été
refondu, et comment le faire progresser.

## 1. Ce qui n'allait pas (challenge de la v1)

| Problème v1 | Conséquence | Réponse v2 |
|---|---|---|
| Dictionnaire de ~70 « faits » à mots-clés plats | formulations clients non reconnues, confusions (frais max / réels, fonds / part, ex ante / ex post) | **ontologie** de 198 concepts avec facettes, portée, type, unités, vocabulaires |
| Une case contenant « Indiquer XXX », « [à compléter] », « Oui/Non », « jj/mm/aaaa » était considérée comme **déjà répondue** | la question était sautée | classification **vide / consigne / vraie réponse** ; la consigne devient un indice |
| Listes déroulantes ignorées | valeur écrite hors liste (fichier invalide pour le client) | lecture des validations Excel (y compris **x14**, listes vers un onglet caché, noms définis) et contrôles de contenu Word ; **jamais** de valeur hors liste |
| Pas de grilles « une ligne / une colonne par part » | onglets de frais par ISIN non remplis | détection des grilles : chaque case reçoit la donnée de **son** ISIN |
| Un seul seuil, aucune preuve | erreurs silencieuses, pas de revue possible | bandes **automatique / à vérifier / sans réponse**, preuve (table.colonne, date) et raisons pour chaque réponse |
| Unité des pourcentages devinée (≤ 0,05 = fraction) | risque d'erreur ×100 | convention Product Info d'App4everyone : **points de pourcentage** (1,35 = 1,35 %), écrits en fraction seulement dans une cellule au format % |
| Pas d'apprentissage | même travail à chaque RFI | **bibliothèque** des réponses validées (question → concept, ou réponse saisie) |
| Pas de mesure | « ça a l'air de marcher » | **banc d'essai** de 169 formulations dont 34 pièges : précision 100 % exigée par les tests |

## 2. Ce que font les meilleurs (recherche)

- Les plateformes de réponse aux RFP/DDQ du marché (Loopio, Responsive, Dasseti, AutoRFP, CENTRL…) reposent sur une
  **bibliothèque de réponses validées** et un **routage par niveau de confiance** : haute confiance → automatique,
  basse confiance → revue humaine, avec score et sources affichés. Les chiffres d'exactitude publiés sont des
  affirmations commerciales non vérifiables.
- Aucune source publique ne décrit l'outillage RFP de BlackRock ; ses publications insistent sur les garde-fous
  (détection d'erreurs, revue humaine) face aux contenus générés « plausibles mais faux ».
- Les standards de données fonds (**openfunds**, gabarits **FinDatEx EMT/EET**) organisent les champs par niveau
  (compagnie / fonds / part), type et valeurs autorisées : c'est la structure reprise par l'ontologie
  (les codes EET sont d'ailleurs dans les noms de colonnes Product Info, ex. `…_EET_20420`).
- La littérature sur la **prédiction sélective** (abstention calibrée) montre le compromis couverture / risque :
  le seuil se règle sur des données étiquetées pour viser une précision cible — d'où le banc d'essai et les fichiers
  « gold » produits à chaque RFI validé.

Sources : [AutoRFP — comparatif asset managers](https://autorfp.ai/blog/best-rfp-software-for-asset-managers) ·
[CENTRL — Response360](https://www.centrl.ai/products/response360/) ·
[CENTRL — avenir des DDQ](https://centrl.ai/resources/the-future-of-ddq/rfp-responses-in-asset-management-why-change-is-inevitable/) ·
[Tribble — routage par confiance](https://tribble.ai/blog/rfp-response-automation-ai/) ·
[Arphie — logiciels DDQ](https://www.arphie.ai/glossary/ai-ddq-software) ·
[BlackRock — consultation CE sur l'IA](https://www.blackrock.com/corporate/literature/publication/ec-targeted-consultation-on-artificial-intelligence-in-the-financial-sector-101724.pdf) ·
[openfunds (présentation)](https://www.fintechfutures.com/data-privacy-security/openfunds-launches-global-standard-for-fund-data-interchange) ·
[FinDatEx EET 1.1.2](https://fefundinfo.com/insights/european-esg-template-eet-version-112-what-you-need-to-know-about-the-changes) ·
[Prédiction sélective (arXiv 2203.00211)](https://arxiv.org/pdf/2203.00211)

## 3. Architecture

```
document ──► layout.py      cases réponses : vide / consigne / réponse, listes, format, grille, entité (ISIN)
         ──► understand.py  facettes (ex ante, max, souscription…), portée, période, unités, type attendu, pays
         ──► library.py     réponse déjà validée ? (exacte ou quasi identique)
         ──► match.py       score de chaque concept de l'ontologie (terme, exclusions, facettes, portée, type, couverture)
         ──► values.py      valeur Product Info / JUMP / calcul (performances App4everyone), avec preuve et date
         ──► render.py      langue, unité, format de cellule, option de liste ; contrôles (bornes, ISIN, LEI, dates)
         ──► service.py     bande : automatique (score ≥ 0,70 et aucune réserve) | à vérifier | sans réponse
         ──► writer.py      copie fidèle du fichier (XML Excel patché, Word mise en forme conservée)
```

Garde-fous (une seule réserve suffit pour passer « à vérifier », jamais d'écriture silencieuse) : lecture par défaut
discutable (frais de gestion max/réels, cut-off souscription/rachat… sauf valeurs identiques), autre lecture proche
de valeur différente, date citée dans la question, donnée ancienne, période non précisée, correspondance de liste
partielle, valeur hors vocabulaire, question qualitative.

Abstention stricte (rien n'est écrit) : pas de donnée, valeur hors bornes, ISIN/LEI à clé invalide, devise non ISO,
valeur absente de la liste déroulante, fourchette ambiguë (« 5 ans » face à « 3-5 ans » et « 5-8 ans »), liste
déroulante dépendante non lisible (INDIRECT), doublons Product Info contradictoires.

## 4. Précédents : « c'est ce qui a déjà été fait »

`backend/merlin/rfi/precedents/` compare chaque question aux RFI déjà envoyés, **au-delà de l'ontologie**, en séparant
les trois couches du guide lot 02 : la **donnée** (Fabric, bon fonds / bonne part / bonne date), le **concept**
(ontologie ou liaison déduite) et la **rédaction** (ton, longueur, langue d'une réponse historique — jamais ses valeurs).

```
anciens RFI ──► importers.py   bibliothèque de wording (json/zip) · RFI déjà répondus (SharePoint « final », dépôt)
                               provenance complète ; réponse / commentaire / option / case à cocher / bloc distingués
            ──► store.py       SQLite + FTS5 (BM25) dans data/rfi/precedents.sqlite — jamais committé
            ──► retrieval.py   rappel BM25 puis reclassement : TF-IDF trigrammes de caractères + Jaccard des mots
                               porteurs de sens (+ embeddings multilingues si MERLIN_RFI_EMBEDDER est défini)
            ──► advisor.py     contrôle Fabric de chaque réponse historique pour le fonds qui l'a reçue, puis décision
            ──► templates.py   modèle de rédaction paramétré seulement si tous les faits du texte sont expliqués
```

| Décision | Quand | Effet |
|---|---|---|
| Repris de l'ancien | l'ontologie répond et l'ancienne réponse = donnée Fabric du fonds d'alors | justification affichée ; « à vérifier » → automatique seulement si confirmé sur ≥ 2 fonds, réserves légères uniquement et aucune autre lecture n'explique aussi l'ancien |
| Liaison déduite | l'ontologie ne sait pas lire la question, mais une donnée Fabric explique l'ancienne réponse (et une seule) | même donnée pour ce fonds, « à vérifier » |
| Réponse société / habituelle | même réponse courte pour ≥ 2 fonds, sans chiffre, date, nom de fonds ni « non applicable » | proposée « à vérifier », dans la liste déroulante sinon rien |
| Modèle de rédaction | paragraphe dont tous les faits (nom, SFDR, société de gestion…) sont retrouvés dans Fabric | faits remplacés par ceux du fonds courant ; sinon « référence de style uniquement » |
| Incohérence | l'ancienne réponse ≠ donnée Fabric du fonds d'alors | les deux sont montrées, jamais d'écriture automatique |
| Modèle d'ontologie | aucun précédent comparable ou vérifiable | inchangé |

Garde-fous : `auto_copy_allowed` toujours faux ; un commentaire vide n'est jamais un « NON » ; une consigne restée dans
l'ancien document (« réponse binaire ») n'est pas une réponse ; anomalie d'identité (ISIN du nom de fichier ≠ ISIN de la
cellule, clé invalide) → **réutilisation bloquée** (cas AXA du lot 02 : 63 entrées) ; aucune valeur source corrigée.
L'inventaire (`GET /api/rfi/precedents/inventory`) ne contient que des agrégats et rappelle les limites du corpus.

**SharePoint** (`merlin/rfi/sources/`) : site `SHAREPOINT_SITE_URL`, racine « 1 - Appels d'offres - Due diligence » →
année (2026, sinon les années précédentes) → `RFI` → dossier de la due diligence → `final` → documents. Deux sources
interchangeables derrière le même contrat : **dossier synchronisé OneDrive** (détecté dans le profil, ou
`SHAREPOINT_LOCAL_DIR`) et **Microsoft Graph** (MSAL interactif, client public `SHAREPOINT_CLIENT_ID` fourni par l'IT,
droits délégués `Sites.Read.All`, aucun secret). Lecture seule.

## 5. Mesurer et faire progresser

- `cd backend && python -m merlin.rfi.evaluate` : précision et couverture sur `tests/rfi_gold.yaml`.
- Après chaque RFI validé, un fichier `…_rempli_vN.gold.json` est écrit : `python -m merlin.rfi.evaluate <fichier>`
  rejoue le moteur dessus (non-régression sur de vrais questionnaires).
- Ajouter une formulation : un terme dans `backend/merlin/rfi/ontology/concepts.yaml` (et un cas dans
  `tests/rfi_gold.yaml`). Ajouter une donnée : un concept dont la source existe dans `catalog/fabric_schema.csv`.
- La bibliothèque (`data/rfi/library.json`) apprend de chaque validation ; elle reste sur le poste.

Résultats actuels : banc d'essai 201 formulations (dont les tests Copilot T01–T20 et les pièges des RFI 2026) —
**précision automatique 100 %**, couverture automatique 93,5 %, 100 % avec les propositions « à vérifier ».
Vrais RFI 2026 (lecture + ontologie, sans précédents) : formulaire Abeille 15 → 34 cases reconnues automatiquement
sur 107, AXA 16 → 57 sur 131. Avec le corpus lot 02 en mode démo, le formulaire Abeille passe à 85 propositions sur 107
(automatiques + à vérifier) ; les contrôles Fabric des précédents n'ont pas pu être exécutés hors du poste. RFI de démonstration réalistes : 96 % (Excel, 47
cases dont 10 listes et 11 consignes) et 89 % (Word) — le reste étant qualitatif ou déjà renseigné.
Ce banc a été construit en même temps que le moteur : la vraie mesure viendra des RFI réels de l'équipe.

À CONFIRMER avec l'équipe Data : unité des pourcentages Product Info (points), sémantique de `DIVIDEND_AMOUNT`
(par part) et `COEFFICIENT_OST` (multiplicatif), unité de `POIDS_LIGNE_EXPO`.
