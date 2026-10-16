# Qvidian dans l'app : ce que l'API permet vraiment, et ce qui a été branché

Source de l'analyse : le paquet `qpa_Oct26_consolidated.zip` (racine du dépôt).

Guide officiel consulté : [Guidelines for using Qvidian Web Services](https://help.uplandsoftware.com/qvidian/prod/ws/devqvidian/html/GuidlinesForUsing.htm), [Authentication Tokens](https://help.uplandsoftware.com/qvidian/prod/ws/devqvidian/html/AuthenticationTokens.htm), [Error Handling](https://help.uplandsoftware.com/qvidian/prod/ws/devqvidian/html/ErrorHandling.htm), [Authentication Web Service](https://help.uplandsoftware.com/qvidian/prod/ws/devqvidian/html/e79e26c4-32ed-4439-8412-249c0dec8c1b.htm) et [Qvidian Web Service](https://help.uplandsoftware.com/qvidian/prod/ws/devqvidian/html/15ee468b-a8d1-4835-b440-28f04ad82fc5.htm).

Contrôle du WSDL d'authentification : `https://qpalogin.qvidian.com/QvidianAuthentication.asmx?WSDL` répond HTTP 200. Le service en ligne et `WSDL/QvidianAuthentication.wsdl` exposent les mêmes quatre opérations (`Connect`, `ConnectByAPIKey`, `ConnectByAuthToken`, `ConnectionTerminate`). Le WSDL du zip annonce une adresse `localhost`, celui en ligne `qpalogin.qvidian.com`; les documents ne sont donc pas identiques octet pour octet et la correspondance constatée porte sur les opérations, pas sur une identité complète de schéma.

**Ce qui a été lu :**
- les deux WSDL :
  - `WSDL/Qvidian.wsdl` : 101 opérations ;
  - `WSDL/QvidianAuthentication.wsdl` : 4 opérations ;
- le guide `SSO For Web Service Applications.docx` ;
- les exemples :
  - `WSQvidianManual` : C#, application Windows ;
  - `WSQvidianTest.UI` : VB.NET, banc de test web de toutes les opérations ;
  - `SSOQvidianWebServices` : C#, connexion SSO.

**Comment l'analyse a été faite :**
- chaque opération du WSDL a été comparée au code des exemples : 98 opérations sur 101 y sont appelées au moins une fois ;
- `dropDownItemDelete`, `projectsRemove` et `reportParamsSave` n'ont aucun exemple ;
- aucun appel réel n'a été possible depuis l'environnement de développement : le serveur Qvidian n'est pas joignable.

Légende :
- ✅ **confirmé** : présent dans le WSDL **et** utilisé dans un exemple fourni ;
- 🟡 **à confirmer** : présent dans le WSDL, mais son comportement n'est pas documenté ;
- ❌ **manquant** : information absente du paquet.

## 1. Authentification

| Point | Statut | Détail |
|---|---|---|
| Service d'authentification | ✅ | `QvidianAuthentication.asmx`. Le guide et l'appel HTTPS testé utilisent `https://qpalogin.qvidian.com/QvidianAuthentication.asmx`; le WSDL en ligne annonce une URL SOAP en HTTP et le zip conserve `localhost` comme adresse de développement. |
| `Connect(userName, password)` | ✅ | Renvoie `ConnectionBinding` : `AuthToken`, `AuthUserName`, `QvidianURL` (adresse du service principal), `LibraryURL`, `ProjectsURL`, etc. |
| `ConnectByAPIKey(userName, apiKey)` | ✅ | Même retour. Utilisée par le banc de test si une clé d'API est fournie. |
| `ConnectByAuthToken(userName, authToken)` | ✅ | Jeton SSO, ou « Reconnect » avec le jeton courant (exemple du banc de test). |
| `ConnectionTerminate(authenticationToken)` | ✅ | Fermeture de session. |
| En-tête SOAP | ✅ | `QvidianCredentialHeader/AuthenticationToken` sur chaque appel à `Qvidian.asmx`. Le service d'authentification accepte aussi `IgnoreLockedOut`. |
| SSO | ✅ exemple du paquet | Redirection vers le portail QPA avec `SSOWebService` (URL de retour en Base64) et, si connu, `SubscriberSuffix`. L'exemple de retour contient `SSOToken` et `SSOLogin`; `SSOUserID` est facultatif et l'app ne l'utilise pas. L'app passe le jeton et le login à `ConnectByAuthToken`. |
| Limite du SSO | ✅ | En cas d'échec chez le fournisseur d'identité, QPA affiche une page d'erreur et ne rappelle jamais l'app (guide SSO, § *Limitations*). |
| Durée de vie du jeton | ✅ guide | « Authentication Tokens » : le jeton vaut le temps de la connexion, jusqu'à `ConnectionTerminate` ou l'expiration de la session — réglage serveur `ConnectionTimeout`, **1200 s (20 min) par défaut**. L'app garde la session ouverte par un petit appel de lecture toutes les 10 min (`QVIDIAN_KEEPALIVE_MINUTES`) ; si la session a quand même expiré, elle tente une reconnexion avec le jeton, sinon demande de refaire le SSO. |
| Mode de connexion de l'abonnement | ❌ | Explicite, SSO seul ou mixte (guide SSO) : à demander à l'administrateur Qvidian. |
| Valeur de `SubscriberSuffix` | ✅ facultatif dans l'exemple | L'exemple `SSOQvidianWebServices/Default.aspx.cs` redirige sans lui quand il est vide (`?SSOWebService=…` seul) : l'app fait de même. Sa valeur réelle reste à demander à l'administrateur Qvidian. |

### Précisions du guide en ligne (pages des méthodes de connexion) ✅
- `Connect` : le mot de passe ne peut pas être vide. **Un compte qui se connecte uniquement par SSO n'a pas de mot de passe Qvidian** : il passe par le bouton SSO (ou une clé d'API).
- `ConnectByAPIKey` : la clé d'API est générée pour l'utilisateur dans l'administration Qvidian; aucun identifiant ou exemple de clé n'est conservé dans ce dépôt.
- `ConnectByAuthToken` : le jeton doit être un GUID. Sinon Qvidian renvoie `AuthenticationTokenMismatch`, et l'app le vérifie avant l'appel.
- Le guide indique que `Connect` exige nom d'utilisateur et mot de passe; un compte SSO seul doit passer par le SSO ou une clé d'API. Les codes de rejet sont propres à l'opération; le client n'en implémente pas encore une traduction exhaustive (❌).
- `ConnectionBinding` renvoie aussi les adresses des anciens services (Administration, Common, Projects, Library, ContentLibrary). Le guide confirme qu'on peut tout faire avec le seul `Qvidian.asmx` (`QvidianURL`) : c'est ce que fait l'app.

## 2. Rechercher et récupérer les contenus

| Opération | Statut | Paramètres → retour |
|---|---|---|
| `libraryFolderGetTop()` | ✅ | → `LibraryFolder` racine : id, titre, `ChildFolderCount`, `ContentCount`, droits. |
| `libraryFoldersGetList(parentFolderID)` | ✅ | → sous-dossiers. |
| `libraryFolderContentGetList(folderID)` | ✅ limité | Le guide indique un maximum de 500 éléments et un ensemble de champs réduit. L'app ne l'utilise plus pour la synchronisation. |
| `librarySearchRequestInit()` puis `librarySearch(LibrarySearchRequest)` | ✅ | Recommandé par le guide pour les dossiers : filtre `LibraryFolderID`, champs choisis et pagination. L'app synchronise désormais chaque dossier de cette façon. |
| `libraryContentDetailsGet(contentID)` | ✅ | → un `Content` complet. |
| `libraryContentGet(contentID)` / `libraryContentGetWithMergeCodes` | ✅ | → fichier (`fileName`, `fileContent` en Base64). |
| `libraryContentPreviewHTMLGet(contentID, revision)` | ✅ | → `htmlContent`. Dépend sans doute du droit `AllowPreviewHTML` (🟡). |
| `librarySavedSearchGetList` / `librarySavedSearchGet` | ✅ | Recherches enregistrées. |
| `projectList(projectListType, pageSize, currentPage)` | ✅ | → `ProjectInfo[]` : nom, type, dates, statut, propriétaires. Mode `AllProjects`, `MyProjects`, `MyProjectsArchived`… |
| `projectSearch(projectListType, pageSize, currentPage, columnsToReturn, searchFilter, orderOn)` | ✅ | Filtres typés : chaîne, nombre, date, booléen, imbriqués (`QvidianProjectQuerying.cs`). |
| `projectDocumentsGetList(projectID)` / `projectDocumentGet(projectID, projectDocID)` | ✅ | Documents d'un projet (fichiers). |
| `projectBuiltDocumentsGetList` / `projectBuiltDocumentGet` | ✅ | Documents générés d'un projet. |
| `projectRFPFileGetList(projectID, componentID)` | ✅ | Fichiers RFP du projet (`ProjectRFPFile`). |
| `projectFileListGetList(projectID, componentID)` | ✅ | Contenus choisis dans une liste de fichiers (`SelectedFile` : `ContentID`, `Revision`, `OutOfDate`). |
| `projectSelectionItemGetList(...)` | ✅ | Éléments sélectionnés dans un projet. |
| `eventAuditSearch(SimpleSearchCriteria)` | ✅ | Journal d'audit : `EventID`, objet, utilisateur, date. |
| `HasPermissions(Permission)` | ✅ | Vérifie un droit, par exemple `EditAllContent`. |

**Détail de la recherche (`librarySearch`).** On initialise la requête avec `librarySearchRequestInit`, puis on règle :
- `searchCriteria` :
  - pagination : `pageSize`, `pageIndex` ;
  - tri : `sortField`, `sortDesc` ;
  - colonnes renvoyées : `searchFields` ;
  - filtres : `filtersAND` / `filtersOR`, avec `FilterCriteria` (propriété, métadonnée personnalisée, mot-clé, dossier) et des opérateurs `EqualTo`, `MatchesAny`, `Contains`… ;
- `searchTermsCriteria` :
  - mots cherchés : `terms` ;
  - mode de recherche : `defaultBehavior`, au choix `AnyOfTheseWords`, `AllOfTheseWords`, `ExactPhrase`, `SemanticSearch` ;
  - champs fouillés : `foundInFields` (`Title`, `Content`, `Comments`, `SearchTerms`…) ;
  - langues : `languageIDs` ;
- ou une recherche système (`systemSearchType`) : `AllExpiredContent`, `AllExpiringContent`, `BulkLoaded`…

Le résultat (`contentDataList`) est un tableau de `Content`, avec `totalCount`.

**Champs utiles d'un `Content`** (présence confirmée dans le WSDL du paquet ✅) :
- identification : `ContentID`, `Revision`, `GUID` ;
- contenu : `Title` (la question type), `ContentText`, `ContentType` (`QA`, `Item`, `Slide`, `File`) ;
- emplacement : `LibraryFolderPath` ;
- langue : `LCID`, `LCIDLanguage` ;
- état : `Enabled`, `Expired`, `DateToExpire` ;
- historique : `DateCreated`, `DateLastModified`, `DateContentUpdated` ;
- usage : `TimesUsedCount`, `DateLastUsed`, `LastUsedByUserName`. Ces champs sont présents dans le type `Content`; l'app les demande parmi les champs de recherche étendus, mais le serveur peut les refuser. Le guide ne précise pas si le compteur correspond spécifiquement à une sélection dans un projet RFP (🟡) ;
- droits et blocages : `CheckedOut`, `CheckedOutByUserName`, `InlineEdit`, `EditPerm` ;
- termes : `LearnedTerms`, `AssignedTerms` ;
- `SubmittedContentMetadata.QuestionText` (la question d'origine d'un contenu soumis depuis un projet) ;
- `AIAssistExcluded`, `AIEngineGenerated`.

### Erreurs (guide « Error Handling ») ✅
Deux voies complémentaires :
- un objet renvoyé porte `HasErrors = true` et des codes (`errors`, énumération `ErrorCodes`) ; ses autres champs ne sont alors pas remplis ;
- sinon, une `SoapException` dont le détail contient `<Error>` avec `Number`, `Message`, `Source`.

L'app gère les deux :
- un contenu en erreur est écarté d'une liste, ou signalé avec son code ;
- une exception est traduite en phrase claire.

Le guide confirme que chaque code est unique, défini par l'énumération `ErrorCodes`, et que les codes possibles sont détaillés dans les pages des méthodes. Le client récupère le numéro, le message et la source d'une `SoapException`, mais ne traduit pas encore les codes Qvidian en libellés métier (❌). Pour un objet `HasErrors`, il écarte les entrées en erreur sans lire les autres champs, conformément au guide.

### Audit et usage
- ✅ Le WSDL fournit `TimesUsedCount` et `DateLastUsed` sur `Content`; l'app les conserve pour le classement, sans en déduire un lien vers un projet.
- ✅ `AuditEventType` est une énumération de types d'audit (`Connect`, `Download`, `Preview`, `Search`, `SavedSearch`).
- ❌ La correspondance entre ces types et les numéros `EventID` du journal n'est pas publiée dans le guide consulté. Les numéros 301, 308, 309 et 310 sont seulement des valeurs présentes dans l'exemple de recherche d'audit; ne pas les interpréter comme une table complète.

## 3. Écrire dans Qvidian

| Opération | Statut | Usage dans l'app |
|---|---|---|
| `libraryContentDetailsUpdate(contentIDs[], ContentUpdates)` | ✅ | Modifications en masse, une seule et même modification pour tous les contenus. Chaque champ a son drapeau `…Updated` : seuls les champs marqués sont modifiés. Le banc de test considère qu'une liste vide en retour veut dire « succès » ; sinon chaque contenu renvoyé porte ses codes d'erreur. |
| `libraryContentRevisionAdd(contentID, fileData)` | ✅ | Nouvelle révision d'un contenu fichier. **Non branchée.** |
| `libraryContentAdd` / `libraryContentNew` / `libraryContentDelete` | ✅ | **Non branchées** : l'app ne crée et ne supprime rien. |

Champs modifiables par `ContentUpdates` :
- `Enabled` ;
- `DateToExpire` ;
- `AlertText`, `AlertEnabled` ;
- `Comments` ;
- `Title` ;
- `ContentText` ;
- `LibraryFolderID` ;
- `OwnerIDs` ;
- `KeywordIDs`, `LearnedTerms` ;
- `LCID` ;
- `ProjectRestrictions` ;
- `ContentCustomX` (métadonnées personnalisées).

## 4. Ce qui manque (à demander à l'administrateur Qvidian ou à tester sur le poste)

1. L'adresse réelle du service d'authentification de l'abonnement, et le `SubscriberSuffix` pour le SSO.
2. Le droit d'utiliser l'API pour le compte, ou une clé d'API (`ConnectByAPIKey`).
3. Le lien entre une question d'un projet RFP et le contenu retenu pour y répondre (le guide confirme seulement que `TimesUsedCount` est « le nombre de fois où ce contenu a été utilisé », calculé par le serveur ; il ne dit pas dans quel contexte). **Aucune opération ne le renvoie directement.**
   - Il existe :
     - les compteurs `TimesUsedCount` et `DateLastUsed` de chaque contenu ;
     - la question d'origine des contenus soumis (`SubmittedContentMetadata.QuestionText`) ;
     - les documents des projets (`projectDocumentGet`) ;
     - le journal d'audit.
   - Les numéros d'événement de l'audit (`EventID`) ne sont pas documentés : seuls 301, 308, 309 et 310 (connexions) apparaissent dans un exemple.
4. Le contenu de `ContentText` pour un contenu Q&A : texte de la réponse, HTML, ou vide pour un contenu « fichier ». La mise à jour de `ContentText` pour un contenu fichier n'est pas documentée.
   - L'app lit `ContentText`, puis l'aperçu HTML s'il est vide.
   - En écriture, elle avertit pour les contenus non éditables en ligne.
5. Les colonnes acceptées dans `searchFields` au-delà de celles des exemples :
   - colonnes des exemples : `ContentID`, `Revision`, `ContentTypeName`, `Title`, `ContentFileExt`, `LCIDLanguage`, `Enabled`, `ContentText` ;
   - l'app tente aussi `DateLastUsed`, `TimesUsedCount`… et revient aux colonnes des exemples si Qvidian les refuse.
6. Le format compressé des résultats (`contentDataCompressed`) : non documenté, l'app le désactive.
7. Les limites de débit et la taille maximale des lots.

## 5. Intégration réalisée

Le moteur Fabric n'est pas modifié. Seuls ont changé les points demandés :
- le compléteur RFI : ajout de la source Qvidian, du classement agrégé et du correctif de lenteur ;
- une nouvelle fenêtre.

| Où | Quoi |
|---|---|
| `backend/merlin/qvidian/soap.py`, `transport.py`, `client.py` | Client SOAP sans dépendance supplémentaire. Chaque requête part par Python (certificats et proxy de Windows), sinon par la connexion de Windows (comme Edge). Les erreurs Qvidian sont traduites en phrases claires. |
| `snapshot.py` | Instantané local SQLite avec recherche plein texte, dans `data/qvidian/` (jamais committé). La synchronisation parcourt les dossiers. Chaque version de texte déjà vue est gardée : les réponses évoluent. |
| `suggest.py`, `backend/merlin/rfi/aggregate.py` | Réponse qualitative la plus choisie récemment (voir § 6). |
| `audit.py`, `rules.yaml` | Carte des erreurs : code informatique dans les textes, textes à compléter, textes dépassés, contenus expirés, doublons, langue, contenus jamais utilisés. Règles modifiables sans toucher au code. |
| `ai.py` | Analyse IA par Copilot, sans API : prompt à copier (identifiants `C<id>`, tableau imposé), réponse collée relue. Les constats apparaissent dans la carte et sont liés à la révision du contenu. |
| `bulk.py` | Modifications en masse protégées (§ 7). |
| `demo.py` | Bibliothèque de démonstration fictive avec des défauts volontaires. **Jamais mélangée aux vraies données** : instantané séparé, et utilisée dans les RFI seulement en mode démonstration. |
| `api/qvidian.py`, `frontend/src/pages/Qvidian.tsx` | Fenêtre « Qvidian » : connexion, synchronisation, carte, liste, analyse IA, modifications, réponse type, import des projets. |
| `backend/merlin/rfi/service.py` | Source Qvidian dans l'analyse. Chaque case reçoit `choices` (toutes les sources classées). Cache des cases. |
| `frontend/src/components/rfi/review/SourceCarousel.tsx` | Carrousel « comparer et choisir » du compléteur. |

## 6. Agrégation : la réponse la plus choisie, la plus récente, dans sa dernière rédaction

**Questions retenues.** Pour une question de RFI, l'app garde les contenus Qvidian qui répondent à **la même question** :
- la similarité des mots porteurs est pondérée par leur rareté dans la bibliothèque ;
- un contenu doit être proche de la meilleure correspondance ;
- une question voisine moins proche n'est pas mélangée.

**Score.** Chaque contenu, ancien RFI, valeur Fabric, extrait de DIC ou réponse Copilot est un vote. Les textes proches (mises à jour, reformulations) forment une famille. Le score d'une famille est la somme, sur ses votes, de :

```
poids(source) × similarité × récence × (1 + log2(utilisations)) × contrôle
```

- **Récence** : `0,5 ^ (âge en jours / 365)`. Une réponse choisie il y a un an pèse moitié moins ; la demi-vie se règle avec `QVIDIAN_HALF_LIFE_DAYS`. Fabric, les documents officiels et la bibliothèque validée ne vieillissent pas.
- **Poids des sources** :

  | Source | Poids |
  |---|---|
  | Fabric | 3 |
  | DIC, prospectus, réponse validée | 2,5 |
  | Copilot | 1,5 |
  | Qvidian, ancien RFI | 1 |

- **Contrôle** : vérifié dans Fabric × 1,5 ; contredit × 0,3 ; réutilisation bloquée × 0,3.

**Texte proposé.** C'est la **version la plus récente** de la famille la mieux classée.

**Garde-fous :**
- une réponse Qvidian n'est **jamais automatique** : toujours « à vérifier » ;
- elle n'entre jamais dans une liste déroulante hors des choix du client.

## 7. Écritures : lecture seule par défaut, mot de passe pour passer en force

1. **Prévisualiser** (aucune écriture, pas de mot de passe) : avant et après pour chaque contenu, avec les alertes.
2. **Écrire** : il faut le mot de passe `QVIDIAN_WRITE_PASSWORD`, défini dans le `.env` du poste et jamais dans le code.
   - Chaque contenu est relu dans Qvidian juste avant l'écriture.
   - Les contenus en alerte sont laissés de côté :
     - extrait par quelqu'un ;
     - modifié depuis la synchronisation ;
     - sans droit d'édition ;
     - texte d'un contenu fichier.
   - **Passer en force** (même mot de passe) les écrit quand même.
3. Cinq mots de passe faux bloquent l'écriture pendant 5 minutes.
4. Chaque lot est journalisé dans `data/qvidian/journal.jsonl`, avec la valeur d'avant et la valeur d'après, et peut être **annulé**.

Actions disponibles :
- désactiver ou réactiver ;
- fixer une date d'expiration ;
- poser ou retirer une alerte ;
- remplacer le commentaire ;
- rechercher et remplacer dans le titre ou dans le texte.

## 8. Projets Qvidian vers anciens RFI

« Importer les projets » fait trois choses :
- il liste les projets (`projectList`) ;
- il télécharge leurs documents Excel et Word (`projectDocumentsGetList`, puis `projectDocumentGet`) ;
- il les verse dans les anciens RFI du compléteur, avec l'origine `qvidian`.

Ces réponses sont ensuite comparées à Fabric. Elles ne sont jamais copiées d'office : `auto_copy_allowed` reste toujours faux.

## 9. Réglages (`.env`)

```
QVIDIAN_MODE=auto                 # auto | demo | off
QVIDIAN_AUTH_URL=https://qpalogin.qvidian.com/QvidianAuthentication.asmx
QVIDIAN_USER=                     # facultatif : sinon connexion depuis la fenêtre
QVIDIAN_PASSWORD=                 # ou QVIDIAN_API_KEY=
QVIDIAN_SUBSCRIBER_SUFFIX=        # SSO
QVIDIAN_WRITE_PASSWORD=           # mot de passe des modifications en masse (jamais committé)
QVIDIAN_HALF_LIFE_DAYS=365
```

## 10. Compléteur RFI : « Choisir » sans attendre

**Avant :**
- chaque clic sur « Choisir » relançait l'analyse complète du questionnaire : Fabric, précédents SharePoint, documents officiels ;
- soit environ 40 secondes, avec l'atelier grisé.

**Maintenant :**
- l'analyse garde chaque case calculée (cache en mémoire, par document et contexte) ;
- un choix ne recalcule que la case concernée, sans relire Fabric : test `test_choose_recomputes_only_the_chosen_cell` ;
- le choix s'affiche immédiatement, et l'atelier n'est plus grisé ;
- le bouton « Analyser » repart de zéro.
