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

**Questions société** (PRI, sanction AMF, actionnaire, politiques de vote / d'engagement, NZAM) : concepts
`societe.*` sans donnée Fabric (`source: precedent:firm`). Les anciens RFI sont regroupés **par le sens** (le même
moteur d'ontologie lit chaque ancienne question), pas par ressemblance de libellé : « Signataire PRI », « Est-ce que
l'Asset Manager est signataire des PRI ? » et « UNPRI signatory? » comptent ensemble. Oui / Yes / OUI sont unifiés ;
un paragraphe sans oui / non explicite ne compte ni pour ni contre ; un désaccord bloque la proposition.

**JUMP** : la part est retrouvée dans `JUMP_portfolio_aum` par son ISIN (puis `ID_PI_PART`, `ID_PI_FONDS`) ; encours,
inventaire et performances utilisent ensuite `ID_JUMP_FONDS` / `ID_JUMP_PART`, avec repli sur les identifiants PI.
Si rien n'est trouvé, la raison est affichée dans les alertes de l'analyse.

Garde-fous : `auto_copy_allowed` toujours faux ; un commentaire vide n'est jamais un « NON » ; une consigne restée dans
l'ancien document (« réponse binaire ») n'est pas une réponse ; anomalie d'identité (ISIN du nom de fichier ≠ ISIN de la
cellule, clé invalide) → **réutilisation bloquée** (cas AXA du lot 02 : 63 entrées) ; aucune valeur source corrigée.
L'inventaire (`GET /api/rfi/precedents/inventory`) ne contient que des agrégats et rappelle les limites du corpus.

**SharePoint** (`merlin/rfi/sources/`) : site `SHAREPOINT_SITE_URL`, racine « 1 - Appels d'offres - Due diligence » →
année (2026, sinon les années précédentes) → `RFI` → dossier de la due diligence → `final` → documents. Deux sources
interchangeables derrière le même contrat : **dossier synchronisé OneDrive** (détecté dans le profil, ou
`SHAREPOINT_LOCAL_DIR`) et **Microsoft Graph** (MSAL interactif, client public `SHAREPOINT_CLIENT_ID` fourni par l'IT,
droits délégués `Sites.Read.All`, aucun secret). Lecture seule.

## 5. Documents officiels (DIC PRIIPs, prospectus)

`backend/merlin/rfi/documents/` : pour la part choisie, l'app cherche le DIC et le prospectus (dépôt manuel, dossier
`FUND_DOCS_DIR`, puis site public `FUND_SITE_URL` : page du fonds → pages de parts qui portent l'ISIN → liens PDF), les
garde en cache (`data/rfi/documents/<ISIN>/`, rafraîchi après 30 jours ou si `Last_DIC_Modification_Date` est plus
récente) et les lit **sans IA** (gabarit PRIIPs réglementé, expressions régulières FR / EN) :
SRI, durée de détention, coûts d'entrée / sortie / récurrents / de transaction, commission de performance, objectif,
date ; prospectus : cut-off, règlement J+N, fréquence de VL, frais maximum, swing pricing, gates, dépositaire,
commissaire aux comptes — **dans la section du compartiment seulement**. Un DIC dont l'ISIN n'est pas celui de la part
est refusé.

Chaque concept porte ses champs de document (`doc:` dans `concepts.yaml`). Fusion :

| Fabric | Document | Résultat |
|---|---|---|
| valeur | même valeur | automatique, preuve double, réserves légères levées |
| valeur | autre valeur | **incohérence** affichée, jamais automatique |
| vide | valeur | proposée « à vérifier », citée (« DIC du JJ/MM/AAAA, p. N ») |

En mode `FUND_DOCS=auto` le site n'est interrogé qu'avec Fabric (fonds réels). À valider sur le poste : URL des pages
fonds (`FUND_SITE_FUND_PATH`) et repérage des sections de vos prospectus.

## 6. Liaisons apprises

`python -m merlin.rfi.precedents.bindings` (ou bouton « Apprendre à partir des anciens RFI ») : pour chaque question
posée à ≥ 3 fonds, la réponse historique est comparée à **toutes les colonnes Product Info du catalogue** du fonds
concerné et aux champs de ses documents en cache. Liaison retenue si ≥ 90 % de concordance, sans colonne concurrente
(« ambiguë ») ni réponses toutes identiques (« non probante »). À l'analyse : la liaison confirme l'ontologie, la
contredit (réserve) ou répond quand l'ontologie ne lit pas la question — automatique seulement si ≥ 5 fonds à 100 %
ou validée par l'équipe. Les décisions (valider / rejeter) survivent aux reconstructions ; `data/rfi/bindings.json`.

## 7. Atelier de revue

Trois zones : le document tel que le client l'a construit (cases colorées par état, clic = sélection) ou la liste par
section ; la question en grand avec ses actions ; les preuves (incohérences en tête, Fabric, extrait du DIC / prospectus
avec lien, anciens RFI, liaison apprise, raisonnement) et « Utiliser cette valeur » pour trancher. Anneau de complétion
(automatique / validée / à vérifier / à compléter), validations groupées (confirmées par un document, réponses société,
visibles), clavier : J / K, A, E, S, X. `prefers-reduced-motion` respecté.

## 8. Mesurer et faire progresser

- `python -m merlin.rfi.replay <bibliothèque>` : couverture et concordance sur de vrais questionnaires (voir plus haut).

- `cd backend && python -m merlin.rfi.evaluate` : précision et couverture sur `tests/rfi_gold.yaml`.
- Après chaque RFI validé, un fichier `…_rempli_vN.gold.json` est écrit : `python -m merlin.rfi.evaluate <fichier>`
  rejoue le moteur dessus (non-régression sur de vrais questionnaires).
- Ajouter une formulation : un terme dans `backend/merlin/rfi/ontology/concepts.yaml` (et un cas dans
  `tests/rfi_gold.yaml`). Ajouter une donnée : un concept dont la source existe dans `catalog/fabric_schema.csv`.
- La bibliothèque (`data/rfi/library.json`) apprend de chaque validation ; elle reste sur le poste.

Résultats actuels (octobre 2026) :

| Mesure | Résultat |
|---|---|
| Banc d'essai (`tests/rfi_gold.yaml`, 239 formulations dont les tests Copilot T01–T20 et 80+ pièges) | précision automatique **100 %**, couverture automatique 91 % |
| Ontologie sur les 770 questions uniques du lot 02 | 275 reconnues (165 automatiques, 110 à vérifier) contre 188 au départ |
| **Banc de rejeu** lot 02 (3 754 questions réellement répondues, chaque fonds rejoué sans ses propres réponses) | couverture **74 %** (ontologie 47 %, précédents 27 %) ; concordance des propositions issues des précédents avec ce qui avait été répondu : **96,4 %** |
| Par famille (rejeu) | Suivi qualitatif 82 % · AXA 85 % · formulaires de référencement 75 % · fiches DATA 63 % · DDQ / ESG / due diligence société 14–30 % (questions rédigées uniques dans le corpus) |

En mode démo les valeurs Fabric sont fictives : la justesse des réponses de l'ontologie ne se mesure qu'avec Fabric.

### Banc de rejeu (à lancer sur le poste, avec Fabric)

```
cd backend && python -m merlin.rfi.replay chemin/Bibliotheque_Wording_RFI_Lot02.json
```

Chaque (fichier, fonds) est rejoué sans ses propres réponses ; les propositions sont comparées à ce qui avait été
répondu. Avec Fabric, le fonds est retrouvé par son ISIN et la concordance de l'ontologie devient une mesure de
justesse sur données réelles. Rapport agrégé (aucune valeur) : `data/rfi/replay_report.json`.

Règles des précédents calibrées sur ce banc : majorité ≥ 75 % des autres fonds ; un libellé repris d'un seul fonds
n'est jamais proposé (≈ 50 % juste), un oui / non l'est (≈ 93 %) ; deux fonds concordants ≈ 89 %.

À CONFIRMER avec l'équipe Data : unité des pourcentages Product Info (points), sémantique de `DIVIDEND_AMOUNT`
(par part) et `COEFFICIENT_OST` (multiplicatif), unité de `POIDS_LIGNE_EXPO`.
