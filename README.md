# RFP_Operations
J’ai analysé le paquet Qvidian et branché l’intégration sans toucher au moteur Fabric. Les 98 tests passent et c’est poussé sur claude/cool-archimedes-g7477l. Je n’ai fait aucun appel réel à Qvidian (serveur injoignable d’ici) : tout est vérifié sur un Qvidian simulé et une bibliothèque de démonstration fictive. Le détail est dans docs/QVIDIAN.md.

Ce que l’API permet (analyse du WSDL et des exemples)

98 des 101 opérations sont utilisées dans les exemples fournis.

Confirmé (WSDL + exemple)

Connexion : identifiant + mot de passe, ou clé d’API, ou jeton SSO. Qvidian renvoie un jeton à joindre à chaque appel, plus l’adresse du service.
SSO : on renvoie l’utilisateur vers le portail QPA, qui le ramène dans l’app avec un jeton.
Rechercher : par mots (tous, l’un des mots, phrase exacte, recherche sémantique), avec filtres, tri et pagination.
Récupérer : dossiers, contenus avec leurs détails, fichiers, aperçu HTML, projets et leurs documents, journal d’audit.
Chaque contenu porte son nombre d’utilisations, sa dernière utilisation, sa révision, sa date d’expiration, son état « extrait par quelqu’un ».
Écrire en masse : activer ou désactiver, date d’expiration, alerte, commentaire, titre, texte, propriétaires.

Manquant, à demander à l’administrateur Qvidian

L’adresse réelle du service. J’ai mis par défaut celle de l’exemple, qpalogin.qvidian.com.
L’identifiant d’abonnement nécessaire au SSO.
Le droit d’utiliser l’API, ou une clé d’API.
La durée de vie du jeton (non documentée).
Point important : aucune opération ne donne « question du projet → contenu retenu ». J’utilise à la place :
les compteurs d’utilisation et la date de dernière utilisation ;
la question d’origine des contenus soumis depuis un projet ;
les documents des projets, importables comme anciens RFI.
Ce que contient le texte d’un contenu Q&A, et si sa mise à jour marche pour un contenu de type fichier : à tester.
Ce qui est livré
Réponses qualitatives tirées de Qvidian : l’app garde les contenus qui répondent à la même question, regroupe les versions d’un même texte et propose la plus récente de la famille la mieux classée.
Classement : utilisations × récence, une utilisation d’il y a un an comptant moitié moins.
Toujours « à vérifier », jamais automatique, jamais hors des choix d’une liste déroulante.
Carrousel dans le compléteur RFI : une carte par réponse possible (Fabric, DIC / prospectus, anciens RFI, Qvidian, Copilot, votre saisie).
Classées avec la même agrégation, avec une barre de score et des filtres par source.
On le parcourt avec ← / →, puis « Choisir » ou « Modifier avant ».
Les 40 secondes au clic « Choisir » : chaque clic relançait toute l’analyse (Fabric, précédents SharePoint, documents).
Désormais seule la case choisie est recalculée, sans relire Fabric. Un test le vérifie.
Le choix s’affiche tout de suite et l’atelier n’est plus grisé. Le bouton « Analyser » recalcule tout.
Nouvelle fenêtre Qvidian :
Carte des erreurs : un tableau dossiers × catégories (code informatique dans les textes, à compléter, texte dépassé, expiré, doublon, langue, peu utilisé).
Les règles sont dans rules.yaml et se modifient sans toucher au code.
Analyse IA par Copilot en copier-coller, comme pour les RFI.
Réponse type : on tape une question, l’app montre la réponse que l’équipe choisit le plus.
Import des projets Qvidian comme anciens RFI.
Modifications en masse : lecture seule par défaut.
On prévisualise avant / après, sans mot de passe.
On écrit avec le mot de passe. Les contenus en alerte (extraits par quelqu’un, modifiés entre-temps…) sont laissés de côté, sauf si on coche « Passer en force ».
Chaque lot est journalisé et peut être annulé.
Cinq essais faux bloquent l’écriture pendant 5 minutes.
À faire sur votre poste
Ajoutez au fichier .env local (jamais committé) :
QVIDIAN_WRITE_PASSWORD=Lafineequipe

Le mot de passe n’est pas dans le code, conformément à la règle du projet. Sans cette ligne, l’écriture reste désactivée.

Connectez-vous depuis la fenêtre Qvidian (identifiant + mot de passe, ou clé d’API, ou SSO si QVIDIAN_SUBSCRIBER_SUFFIX est renseigné), puis cliquez « Synchroniser ».

Tant que vous n’êtes pas connecté, la fenêtre montre une bibliothèque de démonstration fictive. Elle n’est jamais mélangée à vos vrais RFI. Le dépôt contient aussi deux copies identiques du zip Qvidian ; une seule suffit.
