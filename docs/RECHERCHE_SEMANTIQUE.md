# Recherche sémantique de la bibliothèque Qvidian

Objectif : retrouver la bonne réponse type quelle que soit la façon dont le RFP pose la question (autres mots, autre langue,
fonds précis), en tenant compte du **niveau** du texte (société, stratégie, fonds, part) et de son **usage** réel
(nombre d'utilisations, dernière utilisation). Tout tourne sur le poste : aucune donnée n'est envoyée à un service externe.

## 1. État de l'art retenu (recherche novembre 2026)

| Constat | Ce que l'app en fait |
|---|---|
| La référence de production est un **hybride en deux temps** : rappel lexical (BM25) + dense, fusion par rangs réciproques (RRF), puis **reranking** par cross-encoder ([sidhya.studio, 2026](https://sidhya.studio/posts/hybrid-bm25-vector-rerank-2026-reference), [arXiv 2604.01733](https://arxiv.org/pdf/2604.01733)). | Exactement ce pipeline (`merlin/search/engine.py`). |
| BM25 reste très fort, parfois meilleur que le dense seul ; l'hybride l'emporte sur les données multilingues (MIRACL, [arXiv 2305.06300](https://arxiv.org/pdf/2305.06300)). | Le lexical n'est jamais abandonné : il fonctionne seul sans aucun modèle. |
| RRF est la base robuste car insensible aux échelles de score ; les poids se valident sur ses propres questions ([Redis](https://redis.io/blog/reciprocal-rank-fusion.md), [arXiv 2609.01617](https://arxiv.org/pdf/2609.01617)). | RRF pondérée (k = 60), poids mesurés sur notre banc. |
| Encodeurs multilingues compacts sur processeur : multilingual-e5, EmbeddingGemma, Qwen3-Embedding, granite multilingual ([BentoML](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models), [supermemory](https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/)). | **multilingual-e5-small / base** en ONNX int8 (licence MIT, ~100 langues, 136 / 296 Mo). |
| Rerankers multilingues : bge-reranker-v2-m3 (Apache-2.0), jina-reranker-v2 (licence non commerciale : écarté), mMiniLM mMARCO. | **mMiniLM-L12 mMARCO** par défaut (Apache-2.0, 136 Mo) ; BGE-v2-m3 en option. |
| MMR / regroupement contre les quasi-doublons ([HelixDB](https://docs.helix-db.com/rerankers)). | Les versions d'un même texte forment une famille : un résultat, variantes listées. |

## 2. Le pipeline

1. **Question** : normalisation, mots vides et mots de consigne FR / EN / ES / IT (« veuillez », « please », « avez-vous »…),
   racinisation légère commune (pluriels, -ation, -ement, -ité, terminaisons verbales : « rémunérés » = « rémunération »),
   bigrammes ; espagnol / italien réécrits vers le français de l'ontologie (lexique pivot du compléteur RFI) ;
   **thésaurus métier** (`merlin/search/thesaurus.yaml`, ~75 groupes FR / EN : « actionnariat » ↔ « who owns »,
   « PCA » ↔ « business continuity »…), poids réduit pour les équivalents.
2. **Rappel** (100 candidats par voie) : BM25F à champs pondérés (question type ×3, question soumise ×2,5, termes
   appris ×1,6, texte ×1, dossier ×0,6) puis **RM3** (rétroaction sur les 8 meilleurs) ; n-grammes de caractères
   (fautes, dérivations) ; **vecteurs denses** E5 (texte découpé en passages de 160 mots, score = meilleur passage).
3. **Fusion RRF** pondérée (BM25 1,0 · dense 1,1 · n-grammes 0,35) + couverture de la question par la question type
   (mots rares d'abord, équivalents du thésaurus comptés) + expression exacte.
4. **Reranking** des 20 premiers par cross-encoder, fusionné par rangs avec la première passe (mesuré plus robuste
   qu'un mélange de scores : voir §4).
5. **Couche métier** (`merlin/qvidian/library_search.py`) :
   - pertinence × (1 + 0,18 × popularité log(utilisations) + 0,08 × récence d'usage, demi-vie 365 j) ;
   - **portée** : même fonds +0,12, texte propre à un autre fonds −0,28, même niveau +0,05, question société et texte
     de fonds −0,06 ; langue (question anglaise : textes anglais légèrement préférés) ;
   - qualité : expiré −0,22, désactivé −0,5, défaut grave de la carte des erreurs −0,12, texte vide −0,6 ;
   - familles de versions, facettes (niveau, thème, fonds, dossier, langue), explications par résultat.

## 3. Niveau société / stratégie / fonds / part (`merlin/qvidian/levels.py`, `levels.yaml`)

Lu sur le dossier (poids 3), la question type (2) et le texte (1). Les fonds viennent des **dossiers de fonds** de Qvidian
et du **répertoire Product Info** ; un alias de fonds n'est retenu que s'il est propre à un seul fonds (« Horizon »),
jamais un mot commun (« Imaginaire », « Europe »). Une question qui vise une part précise d'un fonds nommé (« part I »,
ISIN, minimum de souscription) passe en portée « part ». Chaque décision garde ses indices, affichés dans la fiche.

## 4. Mesures (bibliothèque de démonstration, 68 contenus fictifs)

Deux jeux de questions : `tests/qvidian_search_eval.yaml` (55 questions, **a servi au réglage**) et
`tests/qvidian_search_holdout.yaml` (40 questions **écrites après le réglage**, mesure honnête).

| Configuration | nDCG@10 réglage | nDCG@10 jamais vu | MRR@10 jamais vu | ms / question |
|---|---|---|---|---|
| Lexical seul (BM25F + RM3 + thésaurus + n-grammes) | 0,960 | 0,901 | 0,863 | ~55 |
| + e5-small | — | 0,904 | 0,865 | ~105 |
| + e5-base | — | 0,913 | 0,884 | ~105 |
| + e5-base + reranker mMiniLM, mélange 50/50 des scores | 0,936 | 0,882 | 0,872 | ~850 |
| **+ e5-small + reranker mMiniLM, fusion par rangs (défaut)** | 0,955 | **0,954** | **0,942** | ~720 |
| + e5-small + reranker BGE-v2-m3 | 0,948 | 0,954 | 0,942 | ~2 800 |

Enseignements : un reranker mal fusionné **dégrade** (0,913 → 0,882) ; fusionné par rangs il apporte +4 points.
BGE-v2-m3 n'apporte rien de plus ici pour 4 × le temps. Profondeur 20 au lieu de 30 : même qualité, −30 % de temps.
Biais assumé : un corpus de 68 contenus est petit ; sur la vraie bibliothèque, écrire 30 à 50 questions réelles
(mêmes clés YAML) et relancer la mesure avant de toucher un poids :

    cd backend && python -m merlin.qvidian.evaluate --models ../data/models --eval mes_questions.yaml --details

### Apprentissage par les anciens RFI

Avec les questions des anciens RFI rattachées aux textes choisis (5 anciens questionnaires fictifs de démonstration) :

| Configuration | nDCG@10 réglage | nDCG@10 jamais vu |
|---|---|---|
| Lexical | 0,960 | 0,901 |
| Lexical + historique | 0,955 | **0,938** |
| e5-small + reranker | 0,955 | 0,954 |
| e5-small + reranker + historique | — | 0,955 |

Première version sans garde-fou : 0,77 (un texte souvent choisi remontait partout). Corrigé : une question passée ne
compte que si elle couvre au moins la moitié de la question posée (mots rares d'abord, mot inconnu = le plus
informatif), et « choisi dans N RFI » ne pèse que pour cette question-là.

## 5. Installation des modèles (facultatif)

Écran **Qvidian › API & moteur** → « Installer » (téléchargement explicite, écriture atomique dans `data/models/<id>/`,
proxy et certificats de l'entreprise respectés). Recommandé : **e5-small + mMiniLM** (2 × 136 Mo). L'index sémantique
se construit en arrière-plan ; en attendant, la recherche lexicale répond. Les vecteurs sont gardés
(`data/qvidian/<instantané>.<modèle>.vectors.npz`) : seuls les textes nouveaux ou modifiés sont réencodés.
Réseau fermé : `MERLIN_MODELS_URL` = miroir interne (même arborescence que Hugging Face), ou copie manuelle de
`model.onnx` + `tokenizer.json` dans le dossier du modèle. Sans `onnxruntime` / `tokenizers`, rien ne casse.

## 6. Limites connues

- Le score affiché (0–100) est une échelle de lecture, pas une probabilité calibrée.
- Le thésaurus a été enrichi sur des formulations du jeu de réglage : la mesure « jamais vu » est la référence.
- Le classement par niveau dépend de l'organisation des dossiers Qvidian ; un dossier mal rangé brouille le niveau
  (les indices affichés permettent de le voir).
