# RFP & Due Diligence

Application interne de pilotage des appels d’offres et de la due diligence.

Elle répond en un écran à la question de la semaine — *quels appels d’offres
sont ouverts, pour quel encours, et qu’avons-nous gagné ou perdu ?* — puis
laisse descendre, page après page, jusqu’au dossier individuel. Un bouton
produit le rapport HTML du périmètre affiché : un fichier unique, ouvrable
d’un double-clic, sans Python ni connexion.

---

## Démarrer

```bash
pip install -r requirements.txt
python server.py
```

L’application s’ouvre sur **http://localhost:8000**. Port occupé ?
`uvicorn server:app --port 8080`.

Sous Windows, **`demarrer.bat`** fait les deux d’un double-clic : il installe
les dépendances au premier lancement, démarre le serveur et ouvre le navigateur.

Elle démarre sur un jeu de **données de démonstration** au format du classeur
du pôle (environ 1 700 questionnaires, 2014 → aujourd’hui). Rien à configurer
pour la découvrir.

```bash
python core.py                # contrôle la chaîne de bout en bout
python tarification.py        # contrôle le moteur tarifaire et sa parité JavaScript
python export.py              # écrit le rapport HTML sur tout l’historique
```

---

## Brancher vos données

Trois façons, de la plus simple à la plus précise.

Rothschild Blue
PMS:   540 U  •  534C

CMYK:   100  •  71  •  0  •  51

RGB:   28  •  53  •  94

HEX:   1C355E

White
PMS:   —

CMYK:   0  •  0  •  0  •  0

RGB:   255  •  255  •  255

HEX:   FFFFFF

Black
PMS:   Process Black U

CMYK:   0  •  0  •  0  •  100

RGB:   0  •  0  •  0

HEX:   000000

Highlight colours
Gold
PMS:   7556 U

CMYK:   8  •  29  •  71  •  9

RGB:   204  •  159  •  83

HEX:   CC9F53

Red
PMS:   208 U

CMYK:   0  •  100  •  29  •  44

RGB:   138  •  30  •  65

HEX:   8A1E41

Background colours
Rose
PMS:   7611 U 

CMYK:   1  •  18  •  16  •  0

RGB:   232  •  201  •  186

HEX:   E8C9BA

Stone
PMS:   Warm Gray 2 U 

CMYK:   10  •  10  •  11  •  0

RGB:   214  •  209  •  202

HEX:   D6D1CA

Graphite
PMS:   419 U

CMYK:   61  •  55  •  66  •  46

RGB:   77  •  74  •  71

HEX:   4C4A47

Tints of primary colours
Percentage tints of the primary colours can be used, as background shading, overlays for images, and in diagrams.  A defined selection will be available in Microsoft Office but outside of these applications, tints can be adjusted to specific requirements.

Blue

80%   #4A5D7E

60%   #77869E

40%   #A4AEBF

20%   #D2D7DF

Gold

80%   #D7B275

60%   #E1C698

40%   #EBD9BA

20%   #F5ECDD

Red

80%   #A24B67

60%   #B9788D

40%   #D0A5B3

20%   #E8D2D9

Rose

80%   #EDD4C8

60%   #F1DFD5

40%   #F6E9E3

20%   #FAF4F1

Stone

80%   #DEDAD5

60%   #E6E3DF

40%   #EFECEA

20%   #F7F6F4

Graphite

80%   #706E6C

60%   #949291

40%   #B8B7B5

20%   #DBDBDA

Chart colours
The chart palette is composed of three colours with four hues each. 

#1
CMYK:   96  •  82  •  17  •  4

RGB:   46  •  62  •  128

HEX:   2E3E80

#10
CMYK:   85  •  50  •  17  •  3

RGB:   38  •  109  •  160

HEX:   1F6699

#2
CMYK:   64  •  20  •  29  •  3

RGB:   95  •  161  •  173

HEX:   50A1A1

#3
CMYK:   37  •  16  •  29  •  1

RGB:   172  •  191  •  183

HEX:   ACBFB7

#9
CMYK:   53  •  89  •  31  •  26

RGB:   117  •  47  •  90

HEX:   752F5A

#6
CMYK:   36  •  91  •  27  •  16

RGB:  153  •  46  •  99

HEX:   992E63

#12
CMYK:   23  •  72  •  42  •  12

RGB:   181  •  91  •  106

HEX:   B55B6A

#7
CMYK:   20  •  36  •  27  •  4

RGB:   204  •  167  •  167

HEX:   CCA7A7

#4
CMYK:   76  •  37  •  72  •  30

RGB:  61  •  102  •  74

HEX:  3D664A

#8
CMYK:   62  •  22  •  69  •  5

RGB:   110  •  153  •  102

HEX:   6E9966

#5
CMYK:   37  •  16  •  60  •  2

RGB:   162  •  174  •  102

HEX:   B0BA7D

#11
CMYK:   28  •  17  •  43  •  2

RGB:   195  •  194  •  157

HEX:   C3C29D

1. **Déposer un fichier dans `data/`.** S’il est seul, il est lu au démarrage :
   premier onglet, colonnes reconnues automatiquement.
2. **Depuis l’application, écran « Données ».** Glisser le classeur, choisir
   l’onglet, vérifier la correspondance des colonnes, corriger celles qui n’ont
   pas été reconnues, activer. Le fichier n’est activé qu’après avoir été lu
   sans erreur.
3. **Écrire `data/branchement.json`** à la main :

```json
{
  "fichier": "Extraction RFP 2026.xlsx",
  "onglet": "Suivi",
  "colonnes": { "montant_potentiel": "Ticket (M€)" },
  "actif": true
}
```

**Formats acceptés** : `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.tsv`, `.txt`.

**Le classeur du pôle est lu tel quel.** Les en-têtes attendus sont ceux du
fichier de suivi, et voici comment chacun est lu :

| Colonne | Lecture |
|---|---|
| `Numero` | identifiant du dossier |
| `Année`, `Month` | servent à reconstruire une date de réception si elle manque |
| `Date de réception`, `Date de fin` | bornes du dossier ; le délai de traitement est leur écart en jours calendaires |
| `Client`, `Segment`, `Type de client`, `Country` | qui demande — Instit. / Distr. / Intern. deviennent Institutionnel / Distributeur / International |
| `Consultant` | cabinet intermédiaire ; « None » = en direct |
| `Writer`, `Reviewer` | rédacteur et relecteur |
| `Type` | RFP ou Due Diligence : la famille du dossier. Il n’existe pas de type plus fin ; un intitulé ancien (« questionnaire », « DDQ », « RFI ») est compris à la lecture et rattaché à la due diligence |
| `Volume` | **l’encours en jeu, en M€**. C’est la grandeur centrale : elle est sommée par état (ouvert, gagné, perdu), par segment, par étape |
| `Number` | vaut 1 ; ignoré, on compte les lignes |
| `Step_1`, `Step_2`, `ORAL_RFP` | trois étapes binaires : dossier remis, présélection, soutenance orale. Elles forment le chemin des appels d’offres |
| `Status` | Done / In progress / Cancelled → envoyé / en cours / abandonné |
| `Result` | Won / Lost / NA → gagné / perdu / en attente. Prime sur `Status` pour un appel d’offres |
| `Qvidian Update` | la base de réponses a-t-elle été mise à jour |
| `Expertise` | High Conviction / Open Architecture / Corporate |
| `Legal form`, `Asset class`, `Sub-asset class`, `Reference fund` | ce qui est proposé |
| `SRI` | fonds ISR, Yes / No |
| `% ESG` | tranche : « < 25 % ESG », « 25-50 % », « 50-75 % », « 75 % » |
| `Sales` | commercial en charge |
| `Language` | FR / EN |
| `4Change` | conservée, jamais interprétée |

**La correspondance est tolérante** : casse, accents, espaces, tirets,
underscores et unités entre parenthèses sont ignorés. « Date de réception »,
`DATE_RECEPTION` et « date réception » désignent la même colonne, et les
intitulés d’anciennes extractions (« Sub asset class », « Ticket (M€) »,
« Analyste », « Montant »…) restent reconnus ; pour en ajouter, compléter
`COLUMN_ALIASES` en tête de `core.py`.

**Trois colonnes sont indispensables** : `Date de réception`, `Type`, `Status`.
Toutes les autres sont facultatives — si `Step_1` manque, le chemin des appels
d’offres disparaît et le reste demeure. L’écran « Données » dit précisément ce
qui manque et ce qui a été écarté.

> Les données réelles ne rejoignent jamais le dépôt : `data/` est ignoré par
> git, à l’exception de son `.gitignore`.

**Vocabulaire métier**, paramétrable dans le bloc `[BRANCHEMENT PRINCIPAL]` de
`core.py` : familles (RFP / due diligence), normalisation des statuts, délais
cibles par type, seuil ESG, horizons de croissance.

### Le classeur des grilles tarifaires

Le simulateur de l’écran **Tarification** lit un second classeur, indépendant du
premier : **une ligne par tranche** d’une offre de frais passée. Il se dépose
depuis l’écran « Données », section « Les grilles tarifaires » (lu, contrôlé,
puis activé : jamais activé sans avoir été lu), et vit dans `data/tarification/`
— à l’écart de `data/`, pour que la détection automatique du classeur d’activité
ne le prenne jamais pour lui.

| Colonne | Lecture |
|---|---|
| **`Client`** | clé catégorielle (« Client 7 ») : rien n’en est déduit |
| **`Quantite_Minimum`**, **`Quantite_Maximum`** | bornes de la tranche, en M€ ; la dernière tranche est ouverte |
| **`Frais_par_seuil`** | taux de la tranche, en % (0,12) ou en fraction (0,0012, format pourcentage d’Excel) — l’unité est décidée par colonne |
| `Volume1` | l’encours de l’offre, en M€ |
| `Annee`, `Sub_asset_class`, `Client_Prospect`, `Public_Privé`, `TVA`, `Commissions de surperformance` | millésime, expertise, issue (gagné / perdu / en cours), nature, fiscalité |

Les en-têtes renommés ou tronqués sont reconnus (`tarification.COLONNES`), une
ligne de titre au-dessus du tableau est sautée, le meilleur onglet est choisi.
Sans classeur, le simulateur tourne sur les 48 lignes de la page 5 de la
présentation d’origine, et le dit.

**Les vrais libellés clients** remplacent « Client 7 » sans toucher au code :
`data/tarification/correspondance_clients.csv` (`client;libelle`, UTF-8 ou
cp1252, `;` ou `,`), à télécharger pré-rempli depuis l’écran, à compléter dans
Excel et à redéposer — ou au crayon, ligne par ligne, dans la liste des offres.
Un libellé identique à un client du classeur d’activité rattache l’offre à son
dossier d’appel d’offres ; un rattachement manuel (`rattachements.json`) prime
et se défait d’un clic. `correspondance_expertises.csv` (`expertise;dimension;valeur`, par
exemple `Credit IG;sous_classe_actifs;Crédit investment grade`) redéfinit,
expertise par expertise, le rapprochement avec les classes d’actifs de
l’activité.

---

## Architecture

| Fichier | Rôle | Dépendances |
|---|---|---|
| `core.py` | Configuration, lecture, normalisation, **couche métrique**, statistiques, thème, figures Plotly, moteur de constats | pandas, numpy, plotly |
| `server.py` | API et service de l’interface : périmètre, analyse, dossiers, rapport, branchement | FastAPI, uvicorn |
| `static/` | L’interface : HTML, CSS, modules JavaScript — aucune étape de construction | — |
| `export.py` | Le rapport HTML autonome | plotly |
| `tarification.py` | Le moteur tarifaire : lecture du classeur des grilles, contrôle des anomalies, calcul progressif, corridors par tranche, croisement avec l’activité | pandas |
| `static/js/tarif.js` | Le même calcul en JavaScript, pour simuler sans aller-retour serveur ; sa parité avec Python est testée | — |
| `static/js/simulateurs.js` | Les simulateurs du gérant : valeur du mandat sur sa durée, leviers de négociation, chance de gain selon le prix ; testés sous node par `python tarification.py` | — |
| `static/js/escalier.js` | L’escalier des frais : la grille dessinée telle que le client la paie, manipulable et animée (SVG) | — |
| `assets/` | Inter et EB Garamond (SIL OFL) ; emplacement du logo officiel | — |

`core.py` n’importe pas FastAPI : il se teste et se réutilise seul (notebook,
script, tâche planifiée). Il produit un objet `Analysis` — indicateurs, blocs
d’analyse, constats — que le serveur et le rapport consomment **à l’identique**,
et il calcule lui-même la charge utile de la vue d’ensemble (`carnet_detaille`,
`resume_situation`) que l’un sert par HTTP et que l’autre imprime. Un chiffre
affiché à l’écran est le même que dans le rapport, par construction ; les
constantes que l’écran doit connaître (ordre des indicateurs, seuil d’attente
longue, longueur des listes) lui sont transmises par `/api/meta`, jamais recopiées.

**Couche métrique.** Chaque indicateur est défini une fois, dans une fonction
documentée (`carnet`, `taux_succes_rfp`, `aum_gagne`, `cadence_mensuelle`,
`croissance`, `identites_carnet`…). Deux graphiques ne peuvent pas compter la
même chose différemment.

**Ajouter une analyse** : écrire `_bloc_xxx(df, mensuel, stats)` qui renvoie un
`Block`, puis l’inscrire dans `_CONSTRUCTEURS`. Elle apparaît automatiquement
dans l’écran de sa section **et** dans le rapport. Un `Block` dont la figure est
`None` **est** un tableau : il s’affiche déplié. Un bloc qui échoue est signalé
sans interrompre l’écran.

**L’état vit dans l’URL** : `?ecran=rfp&periode=2025&pays=Suisse&q=leman`. Un
lien copié rouvre le même écran, le même périmètre, la même fiche ; le bouton
« précédent » fonctionne.

---

## Les écrans

**Situation** — la lecture hebdomadaire de la direction, sans rien ouvrir
d’autre. Une phrase calculée : combien d’appels d’offres sont ouverts, pour quel
encours, combien en rédaction et combien en attente de décision ; puis, sur la
période, les mandats remportés et perdus avec leurs encours. Dessous, dans
l’ordre : **la liste des appels d’offres ouverts** (client, classe d’actifs,
état, étape atteinte, jours d’attente, suivi commercial, encours — le plus gros
encours d’abord), le carnet des cinq états avec ses identités arithmétiques,
les indicateurs (succès, encours remporté, perdu, en jeu, présélection, oral,
délais), le chemin des appels d’offres (reçus → Step 1 → Step 2 → Oral →
remportés, effectifs et encours à chaque marche),
ce qui a changé, les listes nommées des gagnés et perdus, **l’année par année**
(une ligne par exercice du périmètre : reçus, tranchés, taux de succès, encours,
délai — triable d’un clic sur l’en-tête), **les classes d’actifs** (ce que
chacune reçoit, remporte et porte d’encours, triable de même), la décomposition
de l’activité et les huit derniers trimestres.

La barre de périmètre propose les douze, vingt-quatre et trente-six derniers
mois, **chaque exercice présent dans les données**, et tout l’historique. Le
rapport est produit sur le périmètre affiché.

**Analyses** — six questions, une à la fois : Activité, Appels d’offres, Due
diligence, Encours & gains, ESG, Diagnostic. La page Appels d’offres ouvre sur
la liste des dossiers ouverts et le chemin des étapes, puis le taux de succès
par classe d’actifs, par segment de client, par consultant et par commercial.
Chaque analyse porte sa phrase, sa figure, sa note de méthode et son tableau
jumeau. Un clic sur une catégorie recalcule tout le périmètre.

**Tarification** — le simulateur de prix d’appels d’offres, reconstruit depuis
le rapport Power BI d’origine puis repensé du point de vue du gérant
(inventaire, arbitrages et décisions :
[`docs/simulateur-tarification.md`](docs/simulateur-tarification.md)). Les
réglages : l’expertise, la taille du mandat, sa durée et la croissance supposée
de l’encours ; les offres comparées se résument en une ligne qui s’ouvre sur ses
filtres. Puis, dans l’ordre où l’on se pose les questions :

s civiles, indice de référence.
backend/rco/domain/holdings.py : montants, taux de change, sommes, poids.
backend/rco/service.py : contrôle des totaux, rebasage de l'indice de référence, somme par pays calculée dans un ordre fixe.
backend/rco/api.py : un Decimal est converti en nombre fini ou en null avant l'envoi JSON.

Tests

backend/tests/sqlsource.py, backend/tests/test_numeric.py, backend/tests/test_invalid_data.py (nouveaux).

Frontend (uniquement pour afficher « indisponible ») et documentation

frontend/src/components/viz.tsx, lib/types.ts, pages/Fund.tsx, pages/Share.tsx, pages/Holdings.tsx, et frontend/dist reconstruit.
README.md : nouvelle section « Données invalides ».
2. Les trois causes racines
mssql-python renvoie les colonnes DECIMAL en decimal.Decimal. Mélangées à des float, elles font échouer les calculs : Decimal / float dans /api/controls, float * Decimal dans /api/holdings.
Les vraies données contiennent des VL ou des valeurs d'indice de référence nulles. Dans calendar_years, v1 / v0 - 1 avec v0 = 0 produisait le ZeroDivisionError de /api/funds.
Une VL précédente nulle donne un rendement infini. Le produit cumulé déborde (« overflow encountered in accumulate »), puis inf − inf dans les variations, la volatilité et le drawdown donne « invalid value encountered in subtract ».
3. Comportement choisi pour les valeurs invalides
Règle générale : une valeur absente, non numérique, infinie ou booléenne devient None (valeur isolée) ou NaN (série), jamais 0. Elle est envoyée en null.
Performances : une base absente, nulle ou non finie donne une performance null, pour le fonds comme pour l'indice de référence. Un dénominateur nul n'est jamais remplacé par 1.
Indice de performance : il s'arrête au premier rendement invalide ou ≤ −100 %, et vaut NaN à partir de ce point. Les périodes concernées sont indisponibles et une note s'affiche sur la page du fonds. Les performances valides ne sont ni plafonnées ni modifiées.
Taux de change : un taux incalculable donne un montant en euros NaN, pas 0. Aucun taux n'est inventé : un taux égal à 1 n'est utilisé que si la devise du fonds est EUR.
Sommes : faites avec min_count=1, donc un groupe entièrement invalide reste indisponible. Aucune ligne n'est supprimée : les lignes sans montant restent dans la recherche, avec un compte affiché sous la mosaïque.
Contrôle des totaux : il affiche « indisponible » quand un total manque.
Journaux : uniquement des nombres de valeurs écartées et des positions, jamais de valeurs. Aucun warning n'est masqué globalement et numpy.seterr n'est pas utilisé.
4. Tests ajoutés
test_numeric.py (40 tests) :
conversion de Decimal, float, None, NaN, ±inf, pandas NA, booléens, chaînes et très grandes valeurs ;
Decimal / float et float * Decimal ;
division par zéro ;
formatage « indisponible » ;
le journal contient le nombre de valeurs écartées, jamais les valeurs.
test_invalid_data.py (30 tests) :
années civiles avec v0 = 0, None, NaN, Decimal("0"), une série valide, et un fonds valide dont l'indice de référence est nul ;
indice de performance avec VL nulle, rendement de −100 % et valeurs non numériques, sans RuntimeWarning ;
portefeuilles mêlant float, Decimal, None, NaN et chaînes numériques ;
change incalculable ;
contrôle des totaux ;
toutes les routes appelées sur la source simulée, sans 500 ni RuntimeWarning ;
mêmes résultats sur des données valides qu'elles soient en Decimal ou en float.
5. Résultats des tests
python run.py --test : 169 tests backend et 26 tests frontend passent. Les 3 warnings restants sont des avertissements de dépréciation de FastAPI.
Données valides inchangées : j'ai comparé 102 routes avant et après les corrections. Structure et valeurs sont identiques, à l'exception de la somme d'encours par pays, qui variait au dernier chiffre (écart relatif ≤ 6·10⁻¹⁶). Cette variation existait déjà : le code d'origine donnait des résultats légèrement différents d'un lancement à l'autre. La somme est maintenant calculée dans un ordre fixe, donc le résultat est identique à chaque lancement.
Source simulée avec anomalies : /api/funds, /api/controls, /api/holdings et /api/meta répondent 200, avec zéro RuntimeWarning.
6. Commandes PowerShell pour relancer
cd <dossier du projet>
git pull
python run.py --test
python run.py --fabric --port 8080 --no-browser

Dans une seconde fenêtre PowerShell :

foreach ($r in "funds","controls","holdings","meta") {
  try { Invoke-RestMethod "http://127.0.0.1:8080/api/$r" | Out-Null; "$r : OK" }
  catch { "$r : ERREUR"; $_.ErrorDetails.Message }
}
7. Routes encore en erreur

Aucune sur la source simulée : les 54 routes testées répondent sans erreur. Sur vos vraies tables, s'il reste une anomalie que la simulation n'a pas prévue, la route renvoie une erreur JSON structurée, sans données. Envoyez-moi ce message d'erreur et je corrigerai le cas précis.











Corrige la page Passif et l’intégration des tables Fabric Compte, Position et Transaction sans modifier le design général ni les autres pages.

Le chargement Fabric fonctionne, mais les données affichées sur la page Passif sont largement incorrectes ou absentes parce que les CSV ont été chargés avec des colonnes génériques _c0, _c1, etc. L’auto-détection actuelle attribue plusieurs rôles aux mauvaises colonnes.

Symptômes constatés dans l’application :

- Transactions : « non publié »
- aucune journée de transactions publiée
- dates de positions et de transactions affichées « — »
- période de transactions vide
- tenaire de compte « nan »
- après cut-off indisponible
- comptes sans parent et comptes ouverts incohérents
- plus de 1 000 comptes annoncés comme dissous, ce qui semble provenir d’une mauvaise lecture des dates
- la transparence indique que le montant Position serait _c3, alors que _c3 est Compte Centaure
- la transparence indique que le montant Transaction serait _c21, alors que _c21 est Montant Devise et que Montant EUR est _c22
- plusieurs colonnes numériques sont classées « à confirmer » alors que leur rôle est connu
- des valeurs manquantes deviennent le texte « nan » au lieu d’être traitées comme nulles

Utilise les correspondances exactes suivantes.

TABLE COMPTE

_c0 = TeneurCompte
_c1 = Id Compte
_c2 = Nom Compte
_c3 = Id CompteParent
_c4 = Nom CompteParent
_c5 = Id Client
_c6 = Nom Client
_c7 = Classification
_c8 = Devise
_c9 = DateCreation
_c10 = DateDissolution

TABLE POSITION

_c0 = Nom client
_c1 = Pays
_c2 = Teneur de compte
_c3 = Compte Centaure
_c4 = Compte
_c5 = Classification compte
_c6 = Commercial
_c7 = SdG
_c8 = Type fonds
_c9 = Fonds
_c10 = ISIN
_c11 = Classe d'Actif
_c12 = Desk
_c13 = Date
_c14 = Quantite
_c15 = Cours
_c16 = Montant Devise
_c17 = Devise
_c18 = Montant EUR
_c19 = Dernier trade
_c20 = Premier trade

TABLE TRANSACTION

_c0 = Nom client
_c1 = Pays
_c2 = Teneur de compte
_c3 = Compte Centaure
_c4 = Compte
_c5 = Classification compte
_c6 = Commercial
_c7 = SdG
_c8 = Type fonds
_c9 = Fonds
_c10 = ISIN
_c11 = Classe d'Actif
_c12 = Desk
_c13 = Date centralisation
_c14 = Date VL
_c15 = Date Valeur
_c16 = Sens
_c17 = Statut
_c18 = Devise
_c19 = Quantite
_c20 = Cours
_c21 = Montant Devise
_c22 = Montant EUR
_c23 = Commentaire
_c24 = Centralisateur
_c25 = Reference
_c26 = Date de création
_c27 = Compte indirect

Priorité 1 : supprimer l’auto-détection lorsque les tables correspondent à ces schémas.

Si les colonnes portent leurs vrais noms, utilise les vrais noms.
Si elles portent des noms _c0…_cN, applique exactement la correspondance ci-dessus.
Ne cherche pas à deviner le montant à partir de « la plus grande colonne numérique ».

Corrige les mappings par défaut :

APP_PASSIF_MAP_POSITION="compte=_c3,isin=_c10,classe_actif=_c11,desk=_c12,date=_c13,quantite=_c14,cours=_c15,montant_devise=_c16,devise=_c17,montant_eur=_c18,dernier_trade=_c19,premier_trade=_c20"

APP_PASSIF_MAP_TRANSACTION="compte=_c3,isin=_c10,classe_actif=_c11,desk=_c12,date_centralisation=_c13,date_vl=_c14,date_valeur=_c15,sens=_c16,statut=_c17,devise=_c18,quantite=_c19,cours=_c20,montant_devise=_c21,montant_eur=_c22,centralisateur=_c24,reference=_c25,date_creation=_c26,compte_indirect=_c27"

APP_PASSIF_MAP_COMPTE="teneur=_c0,id_compte=_c1,nom_compte=_c2,id_parent=_c3,nom_parent=_c4,id_client=_c5,nom_client=_c6,classification=_c7,devise=_c8,date_creation=_c9,date_dissolution=_c10"

Priorité 2 : traiter correctement les valeurs manquantes.

Considère comme nulles :
- NULL
- chaîne vide
- espaces
- nan
- NaN
- none
- null
- N/A

Ne jamais afficher la chaîne « nan » dans l’interface.
Pour les teneurs de compte manquants, afficher « Non renseigné » ou les intégrer à la part résiduelle selon la règle de confidentialité.
Ne pas compter une date vide ou invalide comme une date de dissolution.

Priorité 3 : corriger les dates.

Position :
- date du snapshot = _c13
- premier trade = _c20
- dernier trade = _c19

Transaction :
- date de centralisation = _c13
- date VL = _c14
- date de valeur = _c15
- date de création = _c26

Les dates des fichiers sont au format américain, par exemple :
9/30/2026 12:00:00 AM

Parse-les explicitement et teste les formats réels avant agrégation.
La « Photo de l’encours » doit afficher la date maximale valide de Position.
La période de transactions doit utiliser les dates de centralisation valides retenues par le filtre des 60 derniers jours ouvrés.
Si aucune date n’est valide, afficher une erreur de diagnostic expliquant le format rejeté, au lieu de simplement afficher « — ».

Priorité 4 : corriger les transactions.

- utiliser Montant EUR = _c22 pour les pondérations en euros
- ne pas utiliser _c21 comme Montant EUR
- respecter Sens = _c16
- respecter Statut = _c17
- analyser les statuts réellement présents
- inclure uniquement les statuts explicitement autorisés
- ne pas déduire qu’une transaction est valide uniquement parce que le montant existe
- utiliser Reference = _c25 pour détecter les doublons
- ne pas supprimer automatiquement plusieurs lignes de même référence sans vérifier compte, ISIN, sens, statut, date et montant
- calculer « après cut-off » uniquement si une règle métier et les données nécessaires existent ; sinon afficher « non calculable », pas une valeur vide trompeuse

Priorité 5 : corriger la structure des comptes.

- Id Compte = _c1
- Id CompteParent = _c3
- Id Client = _c5
- Classification = _c7
- DateCreation = _c9
- DateDissolution = _c10

Un compte est dissous uniquement si DateDissolution contient une date valide.
Un compte sans DateDissolution valide doit être considéré comme non dissous, sans inventer son statut.
« Avec compte parent » doit reposer sur un Id CompteParent non vide.
« Sans compte parent » doit reposer sur un Id CompteParent réellement vide.
Ne pas confondre le premier enregistrement vide du CSV avec une ligne métier.

Priorité 6 : corriger les positions.

- le montant utilisé pour calculer les parts d’encours est Montant EUR = _c18
- Montant Devise = _c16 ne doit être agrégé qu’à devise identique
- Quantite = _c14
- Cours = _c15
- Compte Centaure = _c3
- ISIN = _c10
- Fonds = _c9

Ne jamais utiliser le nom du fonds comme clé principale.
Rattacher l’ISIN à PI_OUT_Share.ISIN_Code après normalisation.
Rattacher Compte Centaure à Compte.Id Compte après normalisation.
Ne jamais mélanger Position, qui représente le passif détenu par compte, avec JUMP_portfolio_holdings, qui représente les instruments détenus dans les portefeuilles.

Priorité 7 : améliorer la transparence.

Dans la section « Lecture des tables sources », afficher :
- le mapping effectivement appliqué
- le type détecté de chaque colonne
- le nombre de valeurs valides et invalides pour les dates
- le nombre de valeurs nulles
- le nombre de comptes rattachés
- le nombre d’ISIN rattachés
- les colonnes explicitement configurées
- les colonnes encore réellement à confirmer

Une colonne définie dans le mapping exact ne doit plus être marquée « À confirmer ».

Priorité 8 : ajouter des contrôles automatiques.

Ajoute des tests vérifiant notamment :

1. Position._c3 n’est jamais interprété comme montant.
2. Position._c18 est utilisé comme Montant EUR.
3. Transaction._c21 est Montant Devise.
4. Transaction._c22 est Montant EUR.
5. Les dates américaines sont correctement parsées.
6. Une chaîne vide ou « nan » ne devient jamais une catégorie affichée.
7. Une DateDissolution vide ne classe pas le compte comme dissous.
8. Une transaction avec une date valide apparaît dans la période.
9. Les données confidentielles restent agrégées.
10. Aucun nom de client, compte individuel ou opération individuelle ne quitte Fabric.
11. Les groupes de moins de cinq restent masqués.
12. Les parts d’encours sont calculées sur Montant EUR.
13. Les montants absolus ne sont jamais envoyés au frontend.
14. Le mode avec vrais noms de colonnes et le mode _c0…_cN produisent les mêmes agrégats.

Ajoute aussi à --fabric-check :
- validation des 11 colonnes de Compte
- validation des 21 colonnes de Position
- validation des 28 colonnes de Transaction
- contrôle des mappings
- contrôle du parsing des dates
- contrôle de présence de lignes exploitables

À la fin :
- explique pourquoi les transactions n’étaient pas publiées
- explique pourquoi les dates étaient vides
- explique pourquoi « nan » apparaissait comme teneur de compte
- explique pourquoi les comptes étaient faussement classés comme dissous
- donne les compteurs de dates valides et invalides
- donne les taux de rattachement compte et ISIN
- liste les fichiers modifiés
- exécute les tests
- reconstruis frontend/dist
- livre une version lançable avec python run.py --fabric sans Node.js sur le poste utilisateur
- ne modifie aucune autre page ni aucun calcul existant hors du Passif.












Mail à l'IT : point d'étape depuis la réunion Microsoft
Aucune modification du code : le livrable est un mail rédigé dans le chat.

Objet : Point d'étape application de référentiel fonds : choix techniques et sécurité des données

Bonjour à tous,

Comme convenu lors de la réunion avec Microsoft, voici où j'en suis et les choix techniques que je retiens.

L'application Il s'agit d'une application web interne de consultation du référentiel des fonds (encours, performances, distribution, passif). Elle tourne en local sur le poste de l'utilisateur : un serveur Python léger et une interface web, lancés en une seule commande. Elle ne fait appel à aucun service externe, aucun service cloud supplémentaire et aucune API tierce. Aucune installation de Node.js n'est nécessaire sur le poste.

Accès aux données

La source est le Lakehouse Fabric (LKH_RFPTeam_Bronze), interrogé via son point de terminaison SQL avec le connecteur Microsoft officiel (mssql-python).
L'authentification passe par le compte Microsoft (Entra ID) de l'utilisateur. Chacun n'accède donc qu'à ce que ses droits Fabric lui permettent, et aucun compte technique n'est partagé.
Aucun identifiant ni secret n'est écrit dans le code : le serveur et la base sont lus dans la configuration du poste.
Data API Builder / GraphQL (suggestion du consultant) Je ne le retiens pas pour l'instant. Mes raisons :

Il faudrait héberger et maintenir un service de plus, exposé sur le réseau, avec sa propre configuration de sécurité. C'est une surface d'attaque supplémentaire pour un besoin qui reste limité.
GraphQL laisse le client composer ses requêtes. Mon besoin est l'inverse : un petit nombre de lectures fixes et agrégées, dont je maîtrise exactement le contenu. Les règles de confidentialité ci-dessous sont plus simples à garantir et à auditer ainsi.
L'accès direct en lecture, avec l'identité de l'utilisateur, conserve tel quel le modèle de droits de Fabric.
Je le reconsidérerai si l'application doit être hébergée de façon centrale, ou si plusieurs outils doivent partager les mêmes données. Dans ce cas, la bonne cible serait l'API GraphQL native de Fabric ou Data API Builder, en lecture seule, sur des vues dédiées et avec l'authentification Entra ID.

Sécurisation des données C'est le point sur lequel j'ai été le plus strict :

Lecture seule : un garde-fou dans l'application n'autorise que des requêtes SELECT et bloque toute écriture ou modification.
Agrégation à la source pour les données sensibles (comptes, positions, transactions) : les calculs sont faits dans Fabric. Aucune ligne de client, de compte ou d'opération n'en sort, et les colonnes de noms (client, compte, commercial, commentaire) ne sont jamais lues.
Anonymisation :
aucun montant absolu, seulement des parts en pourcentage ;
des effectifs par tranches ;
tout groupe de moins de 5 éléments est masqué.
Aucune donnée métier dans les journaux, ni versionnée : les fichiers de configuration et tout export de données sont exclus du dépôt de code.
Développement et tests sur des données fictives, au format exact des tables, jamais sur des données réelles.
Un outil de diagnostic vérifie la configuration, la connexion et la structure des tables. Il n'affiche que des noms de colonnes et des comptages, jamais de valeurs.
Prochaines étapes J'aimerais valider avec vous :

les droits d'accès appropriés sur l'espace de travail Fabric (idéalement un rôle en lecture seule, voire des vues dédiées pour les tables sensibles) ;
une revue de sécurité de l'application avant toute diffusion plus large.
Je reste disponible pour une démonstration ou pour vous détailler n'importe quel point.

Bonne journée, Noa

Tâches












Reprends la branche claude/magical-galileo-bxubss et travaille dans video/ (lis video/README.md et video/VOIX_OFF.md).

Objectif : remplacer la voix off provisoire du teaser « Dix minutes » par la voix neuronale Azure masculine, grave et calme, puis livrer la vidéo finale.

1. Vérifie que AZURE_SPEECH_KEY et AZURE_SPEECH_REGION sont définies (sans jamais afficher la clé) et que le domaine <région>.tts.speech.microsoft.com répond. Si ce n'est pas le cas, arrête-toi et dis-moi ce qui manque.
2. Lance npm i, puis python3 music/voiceover.py --compare. Envoie-moi out/voix-comparatif.wav (Rémy, puis Henri), mais n'attends pas ma réponse : continue avec fr-FR-RemyMultilingualNeural.
3. Génère la voix off avec python3 music/voiceover.py. Si une phrase déborde de son plan, ajuste SEGMENTS ou les durées (src/teaser/timeline.ts et music/montage.py, toujours ensemble), puis régénère. Ensuite, relance python3 music/teaser.py pour que la musique s'efface sous la nouvelle voix.
4. Contrôle quelques images fixes des plans dont le minutage a bougé (npx remotion still DixMinutes … --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell).
5. Rends la vidéo en arrière-plan : npx remotion render DixMinutes out/dix-minutes.mp4 --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell --codec=h264 --crf=17 --audio-codec=aac --audio-bitrate=320k. Ne touche pas à public/vo pendant le rendu. Une fois terminé, vérifie que chaque phrase de src/teaser/vo.json est audible au-dessus de la musique dans le fichier final.
6. Remplace video/rendus/dix-minutes.mp4 (pleine qualité) et video/rendus/dix-minutes-leger.mp4 (moins de 30 Mo : réencode avec le ffmpeg de node_modules/@remotion/compositor-linux-x64-gnu, crf 26, audio 160k). Envoie-moi la version légère dans le chat.
7. Mets à jour video/README.md et video/VOIX_OFF.md (voix utilisée, plus de mention « provisoire »). Commite et pousse sur claude/magical-galileo-bxubss : les vidéos dans un commit séparé, et chaque push vérifié.

Règles : n'envoie à Azure que le texte de la voix off ; aucune donnée réelle hors des deux chiffres communiqués ; aucune clé dans le code, les journaux ou les commits.
