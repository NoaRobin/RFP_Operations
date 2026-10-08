# ✦ RFP pas envie de travailler — #RFPasenviedetravailler

> *My RFP will go on… mais sans nous.*

**RFP pas envie de travailler** est l'application de l'équipe RFP. Elle fait quatre choses :

| Module | Ce qu'il fait |
|---|---|
| **Remplir un RFI** (`/rfi`) | Vous déposez un questionnaire **Excel ou Word**. L'app repère les questions quantitatives, cherche les réponses dans Fabric (≈ 90 % Product Info, le reste JUMP) et vous rend **exactement le même fichier**, avec les cases remplies. L'original n'est jamais modifié. |
| **Merge codes Qvidian** (`/merge-codes`) | Le bot *mergecode* (repris tel quel depuis la branche `claude/merge-code`) repère les années d'expérience dans l'export Word de Qvidian et propose le bon `<<merge code>>`. Vous validez d'un clic, il insère et produit le compte rendu Excel. |
| **Suivi d'activité** (`/suivi-activite`) | Le module *tryv2* (appels d'offres ouverts, gagnés, perdus, tarification), intégré sans modification sous `/suivi`. |
| **Les épreuves** (`/sorts`) | La bibliothèque d'automatisations (chaque automatisation est une épreuve, façon Koh-Lanta, que vous ne passerez plus à la main) (encours par part, top lignes, contrôles…) + l'Atelier Excel, le tableau de bord, l'historique, la palette **Ctrl+K**. |

Sans connexion Fabric, l'app démarre en **mode démonstration** avec un Lakehouse fictif (ISIN `QZ…`, fonds imaginaires).

> Identité : **cartoon néo-brutal** — papier crème, encre violette, contours épais, ombres décalées ; Fredoka + Nunito ; un livre vivant en 3D (three.js, ombrage toon), une course-poursuite de livres traqués par des RFI/RFP/DDQ, Mathilde qui regarde passer les RFP à sa fenêtre (et cite Céline Dion), des micro-animations GSAP. Easter eggs : tapez `celine` ou `kohlanta`. Le package Python s'appelle toujours `merlin` (nom technique interne).

## Démarrage : un double-clic

Prérequis : **Python 3.11+** (rien d'autre : l'interface est déjà compilée dans `frontend/dist`).

1. Double-cliquez sur **`run.bat`** (Windows) — ou `./run.sh` / `python run.py` ailleurs.
2. La première fois, il crée un environnement Python dans `%LOCALAPPDATA%\RFPpasenvie` et installe les dépendances (quelques minutes).
3. Le navigateur s'ouvre sur l'app.

Options : `run.bat --demo` (force les données fictives) · `run.bat --doctor` (diagnostic) · `--port 8080` · `--no-browser` · `--rebuild` (recompile l'interface, Node requis).

### Se connecter à Fabric (comme dans VS Code)
Dans l'app, cliquez sur le badge **Fabric** en haut à droite, puis :
1. **Serveur** : Fabric › Lakehouse › *SQL analytics endpoint* › copier la chaîne de connexion (la même que dans l'extension VS Code *mssql*) ;
2. **Votre identifiant Microsoft** (prenom.nom@…) ;
3. **Ouvrir la fenêtre Microsoft** : la fenêtre de connexion habituelle apparaît, vous validez. C'est tout.

L'app utilise le pilote `mssql-python` (le même que l'extension VS Code, installé automatiquement sous Windows, aucun pilote ODBC requis) en `ActiveDirectoryInteractive`, lecture seule. Le serveur, la base et l'identifiant sont retenus dans `data/fabric.json` (**aucun mot de passe ni jeton n'est stocké**). Une seule fenêtre Microsoft par session : toutes les épreuves partagent la connexion.

### Développement

```bash
cd backend && pip install -r requirements.txt && uvicorn merlin.main:app --reload   # API sur :8000
cd frontend && npm install && npm run dev                                          # interface sur :5173
cd backend && pytest                                                               # tests
cd frontend && npm run build                                                       # recompile frontend/dist (à committer)
```

---

## Remplir un RFI : comment ça marche
Méthode complète, résultats et sources : [`docs/COMPLETEUR_RFI.md`](docs/COMPLETEUR_RFI.md).
1. **Lecture** : listes de questions, grilles « une ligne / une colonne par part », cases pré-remplies de consignes
   (« Indiquer… », « [à compléter] », « Oui/Non », « jj/mm/aaaa ») traitées comme vides, listes déroulantes Excel
   (y compris vers un onglet caché) et Word, cases à cocher, format des cellules (%, date).
2. **Ontologie** (`backend/merlin/rfi/ontology/`) : 177 concepts fonds / part reliés à Product Info, JUMP et aux
   performances (méthode App4everyone), avec facettes (ex ante / ex post, maximum / réel, souscription / rachat…),
   vocabulaires FR / EN et bornes de vraisemblance. **Pas d'IA externe, rien ne sort du poste.**
3. **Revue** : chaque réponse a sa preuve (table.colonne, date) ; « automatique » seulement sans aucune réserve,
   sinon « à vérifier » (un clic pour valider). Jamais de valeur hors liste, hors bornes ou à clé ISIN/LEI invalide.
4. **Écriture** : même fichier, cases remplies au bon format ; chaque validation enrichit la bibliothèque.

Mesure : `cd backend && python -m merlin.rfi.evaluate` (banc de 169 formulations dont 34 pièges : précision 100 % exigée).

## Merge codes : le référentiel
L'Excel « Années d'expérience – FR_EN pour Qvidian » (onglet *Data*) se dépose **une fois** dans l'écran Merge codes. Il reste dans `data/mergecodes/` sur votre poste et **n'est jamais committé** (données de collaborateurs).

---

## Arborescence

```
run.bat / run.sh / run.py  ← lanceur (venv, dépendances, navigateur)
catalog/                   ← fabric_schema.csv (machine) + fabric_catalog.md (lisible, « À CONFIRMER »)
automations/               ← UN DOSSIER = UN SORT (manifest.yaml + query.sql | run.py)
backend/merlin/
  data/        access.py (accès UNIQUE Fabric | mock), fabric_link.py (connexion façon VS Code), catalog.py, mock.py
  rfi/         ontology/ (concepts, facettes, vocabulaires), layout, understand, match, values, perf, render, library, writer, evaluate
  mergecodes/  service.py (pilote le bot vendorisé, sans Word ni pywin32)
  suivi.py     monte tryv2 sous /suivi
  plugins/ jobs/ atelier/ api/ scheduler.py db.py main.py
backend/vendor/            ← code repris TEL QUEL : mergebot/ (+ bot_merge_codes.py), suivi/ (tryv2)
frontend/src/
  content/texts.ts         ← TOUS les textes de l'interface (et l'humour)
  motion/tokens.ts         ← courbes, durées, distances
  styles/tokens.css        ← couleurs, typographies, ombres cartoon
  components/three/        ← livre vivant 3D (toon + contours) + repli 2D SVG automatique
  components/fx/Chase.tsx, Mathilde.tsx ← course-poursuite et Mathilde à sa fenêtre (SVG + GSAP)
  pages/                   ← Home, Rfi, MergeCodes, Suivi, Library (sorts), Atelier, Dashboard, History, About…
frontend/dist/             ← interface compilée (committée : run.bat n'a pas besoin de Node)
data/                      ← (généré, ignoré par git) historique, RFI, merge codes, suivi, mock
```

---

## Palette de commandes (⌘K / Ctrl+K)
Disponible partout, y compris dans un champ de saisie. Elle indexe les automatisations, les recettes de l'Atelier, les exécutions récentes, les pages et quelques actions.
- **↵** : ouvrir l'automatisation, rejouer la recette, ouvrir l'exécution ou la page.
- **⇧↵** : lancer immédiatement une automatisation avec ses valeurs par défaut (« aujourd'hui » pour les dates), si aucun paramètre obligatoire ne manque.
- Les choix récents remontent en tête quand la recherche est vide.

## Ajouter une automatisation

### Option A — sans Python : type `fabric`
Créez `automations/mon_automatisation/manifest.yaml` :

```yaml
id: mon_automatisation                    # identifiant unique (minuscules, chiffres, _ ou -)
name: Encours d'un fonds
description: Ce que fait l'automatisation, en une ou deux phrases.
icon: gem                       # gem, crown, eye, scroll, table, chart, shield… (voir Icon.tsx)
category: Encours & VL          # sert aux filtres de la bibliothèque
type: fabric
estimated_minutes_saved: 15     # alimente le compteur de temps économisé
params:
  - name: as_of
    label: Date d'arrêté
    type: date                  # string | text | number | integer | date | boolean | select | multiselect | isin
    required: true
    default: today
  - name: fonds
    label: Fonds
    type: select
    options_query: >            # liste de choix alimentée par Fabric (colonnes value / label)
      SELECT DISTINCT h.ID_JUMP_FONDS AS value, h.NOM_FONDS AS label
      FROM dbo.JUMP_portfolio_holdings h
fabric:
  query_file: query.sql
  output: both                  # excel | table | both
  filename: "Encours_{fonds}_{as_of}.xlsx"
  column_labels: { ACTIF_NET_PART_EURO: Encours part (EUR) }
  number_formats: { Encours part (EUR): "#,##0" }
```

…et `automations/mon_automatisation/query.sql` en **T-SQL**, avec des paramètres nommés `:as_of`, `:fonds`. Redémarrez le serveur : l'automatisation apparaît dans la bibliothèque, avec son formulaire généré automatiquement.

### Option B — avec Python : type `python`
Un `manifest.yaml` (avec `type: python` et, en option, `steps:` pour la timeline), plus un `run.py` :

```python
def run(ctx, as_of: str, seuil: float = 10.0):
    with ctx.step("Chargement"):
        df = ctx.data.query("SELECT ... FROM dbo.JUMP_portfolio_aum WHERE DATE_VL <= :d", {"d": as_of})
    ctx.log.info("%d lignes", len(df))
    ctx.show_table(df, "Aperçu")
    ctx.save_excel({"Résultat": df}, f"resultat_{as_of}.xlsx")
    ctx.set_summary(f"{len(df)} lignes traitées.")
```

Ce que fournit `ctx` : `data` (accès Fabric), `log`, `step()`, `progress()`, `save_excel/csv/file`, `show_table`, `set_summary`, `output_dir`, `params`, `user`, et `browser`. Ce dernier est un emplacement réservé au futur navigateur Playwright : l'interface est en place, mais il lève une erreur explicite tant qu'il n'est pas implémenté. Une automatisation qui en dépend déclare `requires: [fabric, browser]`.

### Règles d'or
1. **Les tables et les colonnes viennent de `catalog/fabric_catalog.md`.** Au démarrage, l'app valide chaque requête contre le catalogue, casse comprise. Une automatisation qui cite une colonne inconnue est marquée « indisponible » et ne peut pas être lancé.
2. Les modules ne se connectent jamais à Fabric eux-mêmes : ils passent par `ctx.data`.
3. En mode démo, le T-SQL est traduit vers SQLite (sqlglot). Restez donc sur du SQL standard (SELECT, JOIN, CTE, GROUP BY, TOP, fonctions de fenêtre).

---

## L'Atelier Excel
1. Déposez un `.xlsx`/`.xlsm`, ou cliquez sur **« Essayer avec un questionnaire de démo »**.
2. l'app détecte la ligne d'en-tête, la **colonne clé** (ISIN reconnus dans le Lakehouse) et les **cellules à remplir** : vides, « ? », « TBD » ou surlignées en jaune. Les formules sont protégées.
3. Il propose des correspondances en-tête → extraction. Vous complétez par **glisser-déposer** depuis le catalogue (au clavier : sélectionnez la colonne, puis le bouton « Affecter »).
4. **Aperçu** : les valeurs tombent dans les cellules ; vous pouvez basculer Avant/Après. Le bilan distingue ce qui est à remplir, ce qui est déjà juste, ce qui est introuvable, et les différences ignorées.
5. **Exécuter** écrit `versions/<nom>_vN_<date>.xlsx` accompagné d'un journal des modifications. **L'original n'est jamais réécrit** (il est stocké en lecture seule).
6. **Enregistrer la recette** (YAML dans `data/atelier/recipes/`) pour la rejouer ou la **planifier**.

Les extractions disponibles sont décrites dans `backend/merlin/atelier/extractions.yaml`. Pour en ajouter une, il suffit de quelques lignes de YAML.

## Planification
À la demande, quotidien (jours ouvrés), hebdomadaire ou mensuel, pour les automatisations comme pour les recettes. Les dates « aujourd'hui » sont recalculées à chaque exécution. Les planifications se gèrent depuis le tableau de pilotage.

## Accessibilité et performance
- `prefers-reduced-motion` : le contenu est visible immédiatement. Plus de révélations au défilement, de parallaxe, d'inclinaison ni d'étincelles ; seuls des fondus courts subsistent.
- Navigation complète au clavier, focus toujours visible (anneau cyan), lien d'évitement, `aria-live` sur le journal et les résultats, boîtes de dialogue natives.
- 3D chargée à la demande (chunk séparé), DPR plafonné à 1,5, particules dans un seul draw call, pause hors écran. Le passage en 2D est automatique sans WebGL, sur une machine modeste ou si les FPS chutent. Le **mode économie** est aussi disponible manuellement dans le menu utilisateur.

## Easter eggs
Quelques-uns, discrets. Indices : ↑↑↓↓←→←→BA, une constellation qui réagit au clic, un mot magique tapé au clavier, une page qui n'existe pas.

## Scripts historiques
`JUMP_OMNI.py` et `OMNI_MENSUEL.py` (pilotage d'Excel, de JUMP et d'Outlook sous Windows) sont conservés tels quels. Ce sont de bons candidats pour de futures automatisations `python`, une fois le navigateur ou le pilotage desktop branché sur `ctx`.


Intègre ce lot comme bibliothèque d'exemples de wording dans mon projet RFI existant, sans remplacer la base Product Info ni écraser les versions précédentes.

