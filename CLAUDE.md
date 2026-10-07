# CLAUDE.md — règles du projet MERLIN

## Source de vérité des données
- `catalog/fabric_catalog.md` (lisible) et `catalog/fabric_schema.csv` (machine) décrivent **toutes** les tables Fabric connues.
- **Ne jamais deviner un nom de table ou de colonne.** Si une colonne n'existe pas dans le catalogue, elle n'existe pas. Demander à l'équipe plutôt qu'inventer.
- Tout ce qui est déduit (clés, relations, sens métier) est marqué « À CONFIRMER » dans le catalogue : ne pas le présenter comme certain.
- Le backend valide les requêtes SQL des automatisations `fabric` contre `fabric_schema.csv` au démarrage (`merlin/data/catalog.py`). Une requête qui cite une colonne inconnue est refusée.
- Si le schéma évolue : remplacer `fabric_schema.csv` par un nouvel export `INFORMATION_SCHEMA.COLUMNS` (mêmes en-têtes) puis mettre à jour `fabric_catalog.md`.

## Architecture (rappel)
- `backend/merlin` : FastAPI. Accès aux données **uniquement** via `merlin.data.access.DataAccess` (jamais de connexion Fabric directe dans un module).
- `automations/<id>/` : un plugin = `manifest.yaml` (+ `run.py` exposant `run(ctx, **params)` pour le type `python`, ou `query.sql` pour le type `fabric`).
- Les jobs tournent dans des processus séparés (`merlin/jobs`). Logs et statut diffusés en SSE.
- `frontend/` : React + Vite + TS. Textes de l'interface centralisés dans `src/content/texts.ts`, tokens de motion dans `src/motion/tokens.ts`, tokens visuels dans `src/styles/tokens.css`.

## Règles
- Aucun secret dans le code : variables d'environnement (voir `.env.example`).
- Aucune donnée réelle dans les exemples, mocks ou tests (ISIN fictifs préfixés `QZ`, fonds imaginaires).
- Les fichiers Excel déposés dans l'Atelier ne sont **jamais** modifiés : chaque exécution écrit une nouvelle version.
- SQL des automatisations écrit en dialecte T-SQL (Fabric). En mode mock, il est traduit automatiquement vers SQLite (sqlglot) : rester sur du SQL standard (SELECT, JOIN, GROUP BY, TOP, CTE).
- `prefers-reduced-motion` doit toujours être respecté ; le fun ne bloque jamais une action.
- Les scripts historiques `JUMP_OMNI.py` et `OMNI_MENSUEL.py` (Windows/Excel/Outlook) sont conservés tels quels ; ils ne font pas partie de Merlin.

## Commandes
- Backend : `cd backend && pip install -r requirements.txt && uvicorn merlin.main:app --reload`
- Tests backend : `cd backend && pytest`
- Frontend : `cd frontend && npm install && npm run dev` (build : `npm run build`)
