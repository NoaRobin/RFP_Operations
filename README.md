# ◍ MERIDIAN — RFP Operations

> *Les RFP, mais sans les sacrifices humains.*

MERIDIAN regroupe les automatisations de l'équipe RFP dans une seule application : une **bibliothèque** d'automatisations lancées en un clic (ou au clavier avec **⌘K / Ctrl+K**), un **Atelier Excel** qui remplit les questionnaires à partir du Lakehouse Fabric, un **tableau de pilotage** et un **historique** complet.

Sans connexion Fabric, MERIDIAN démarre en **mode démonstration** avec un Lakehouse fictif. Vous pouvez donc tout voir dès la première minute.

---

> Identité : **corporate premium** — encre, ivoire, champagne ; Instrument Serif + Inter Tight. Le package Python s'appelle toujours `merlin` (nom technique interne), l'application s'appelle MERIDIAN.

## Démarrage rapide

Prérequis : **Python 3.11+** et **Node 20+**.

```bash
# 1. Configuration (facultative pour la démo)
cp .env.example .env

# 2. Backend (API + jobs + planificateur)
cd backend
python -m venv .venv
# Windows : .venv\Scripts\activate    macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
uvicorn merlin.main:app --reload --port 8000

# 3. Frontend (autre terminal)
cd frontend
npm install
npm run dev            # → http://localhost:5173
```

**Version « un seul serveur »** : `cd frontend && npm run build`, puis lancez seulement le backend. Il sert l'interface compilée sur http://localhost:8000.

Tests backend : `cd backend && pip install -r requirements-dev.txt && pytest`.

### Brancher Fabric
Renseignez `FABRIC_SQL_ENDPOINT` dans `.env`. Pour le trouver : Lakehouse › *SQL analytics endpoint* › *Copier la chaîne de connexion*. Ensuite :
```bash
pip install pyodbc        # + « ODBC Driver 18 for SQL Server » installé sur le poste
```
Avec `MERLIN_DATA_MODE=auto` (par défaut), MERIDIAN utilise Fabric s'il est joignable et revient sinon au mode démo. Le badge en haut de l'écran indique la source active. L'authentification passe par Entra ID (`ActiveDirectoryInteractive` sur un poste, `ActiveDirectoryServicePrincipal` sur un serveur). **Aucun secret dans le code.**

---

## Arborescence

```
catalog/
  fabric_schema.csv        ← export INFORMATION_SCHEMA (source de vérité machine)
  fabric_catalog.md        ← catalogue lisible : tables, colonnes, clés, relations, « À CONFIRMER »
CLAUDE.md                  ← règles du projet (ne jamais deviner un nom de colonne)
automations/               ← UN DOSSIER = UNE AUTOMATISATION (découverts au démarrage)
  aum_par_part/            · type fabric  : manifest.yaml + query.sql
  top_lignes_portefeuille/ · type fabric
  controle_encours/        · type python  : manifest.yaml + run.py
backend/merlin/
  data/        access.py   ← couche d'accès UNIQUE (Fabric | mock), validation contre le catalogue
               catalog.py, mock.py
  plugins/     manifest.py (schéma), registry.py (découverte), context.py (ctx), fabric_type.py
  jobs/        manager.py (1 processus par exécution, SSE), worker.py
  atelier/     analyzer.py, extractions.yaml, engine.py (aperçu + versions), store.py (recettes YAML)
  api/         core.py, atelier.py
  scheduler.py (APScheduler) · db.py (historique SQLite) · main.py
frontend/src/
  content/texts.ts         ← TOUS les textes de l'interface (et l'humour)
  motion/tokens.ts         ← courbes, durées, distances : le vocabulaire d'animation
  styles/tokens.css        ← couleurs, typographies, ombres
  components/three/        ← constellation de données 3D (R3F, InstancedMesh) + repli 2D automatique
  components/fx/           ← champ de points, lueur du curseur, Lenis, easter eggs
  components/CommandPalette.tsx ← palette ⌘K
  pages/                   ← Intro, Library, AutomationPage, Run, Atelier, Dashboard, History, About, NotFound
data/                      ← (généré, ignoré par git) historique, fichiers, versions, mock
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
1. **Les tables et les colonnes viennent de `catalog/fabric_catalog.md`.** Au démarrage, MERIDIAN valide chaque requête contre le catalogue, casse comprise. Une automatisation qui cite une colonne inconnue est marquée « indisponible » et ne peut pas être lancé.
2. Les modules ne se connectent jamais à Fabric eux-mêmes : ils passent par `ctx.data`.
3. En mode démo, le T-SQL est traduit vers SQLite (sqlglot). Restez donc sur du SQL standard (SELECT, JOIN, CTE, GROUP BY, TOP, fonctions de fenêtre).

---

## L'Atelier Excel
1. Déposez un `.xlsx`/`.xlsm`, ou cliquez sur **« Essayer avec un questionnaire de démo »**.
2. MERIDIAN détecte la ligne d'en-tête, la **colonne clé** (ISIN reconnus dans le Lakehouse) et les **cellules à remplir** : vides, « ? », « TBD » ou surlignées en jaune. Les formules sont protégées.
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
