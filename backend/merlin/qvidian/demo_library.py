"""Contenus de démonstration supplémentaires (tous fictifs) : société, équipe, trois fonds imaginaires et leurs parts,
ESG, risques, opérations, conformité, en français et en anglais.

Ils servent à montrer la recherche sémantique (paraphrases, questions anglaises sur des textes français, réponses
propres à un fonds à ne pas confondre avec celles d'un autre) et au banc d'évaluation tests/qvidian_search_eval.yaml.
Même format que demo._C : (id, dossier, question, texte, révision, utilisations, dernière utilisation, modifié, créé, extras).
"""
from __future__ import annotations

EN = {"LCID": "1033", "LCIDLanguage": "English"}

FOLDERS_EXTRA = [
    (13, 10, "Organisation et effectifs"), (14, 10, "Conformité"), (15, 10, "Continuité et sécurité"),
    (23, 20, "Équipe de gestion"), (33, 30, "Exclusions et climat"), (43, 40, "Ordres et règlement"),
    (53, 50, "Fonds Imaginaire Boréal"), (60, 1, "English library"), (61, 60, "Company (EN)"), (62, 60, "Funds (EN)"),
]

CONTENTS_EXTRA = [
    # ------------------------------------------------------------------ société
    (1021, 11, "Qui sont les actionnaires de la société ?",
     "Le capital est détenu à 62 % par les associés dirigeants et à 38 % par la Fondation Imaginaire, actionnaire de long "
     "terme. Aucun actionnaire extérieur ne dispose d'un droit de veto sur les décisions de gestion.", 3, 41, "2026-08-02", "2025-12-01", "2016-01-01", {}),
    (1022, 11, "Racontez l'historique et les grandes étapes de votre maison.",
     "Fondée en 1998 par trois gérants, la maison a lancé son premier fonds actions européennes en 1999, ouvert un bureau "
     "à Luxembourg en 2008, puis créé son pôle d'investissement responsable en 2015.", 2, 23, "2026-05-10", "2024-10-01", "2016-01-01", {}),
    (1023, 13, "Combien de collaborateurs compte la maison ?",
     "La maison compte 140 collaborateurs, dont 38 professionnels de l'investissement (gérants et analystes), 25 personnes "
     "dédiées au contrôle des risques et à la conformité, et 30 au service client.", 4, 36, "2026-09-01", "2026-01-20", "2017-01-01", {}),
    (1024, 13, "Où sont situés vos bureaux ?",
     "Le siège est à Paris ; la maison dispose de bureaux à Luxembourg, Genève et Milan pour accompagner ses clients européens.",
     2, 19, "2026-03-15", "2025-06-01", "2018-01-01", {}),
    (1025, 13, "Quelle est la typologie de vos clients ?",
     "Nos clients sont à 70 % des investisseurs institutionnels (assureurs, caisses de retraite, mutuelles) et à 30 % des "
     "distributeurs et banques privées.", 1, 11, "2025-11-03", "2025-02-01", "2019-01-01", {}),
    (1026, 11, "Répartition de l'encours par classe d'actifs",
     "Au 30/06/2026 : actions 48 %, obligations 32 %, multi-actifs 15 %, monétaire 5 %. Total des actifs gérés : 14,2 milliards d'euros.",
     5, 28, "2026-09-20", "2026-07-05", "2019-01-01", {}),
    (1027, 14, "Décrivez votre dispositif de lutte contre le blanchiment.",
     "Chaque client est identifié avant toute souscription (KYC), les opérations atypiques sont analysées par le "
     "responsable de la conformité et, le cas échéant, déclarées à Tracfin. Le dispositif est revu chaque année.", 2, 17, "2026-06-11", "2025-09-15", "2018-01-01", {}),
    (1028, 14, "Comment les conflits d'intérêts sont-ils prévenus ?",
     "Une politique de gestion des conflits d'intérêts recense les situations à risque ; un registre est tenu par la "
     "conformité et les collaborateurs déclarent leurs transactions personnelles.", 1, 14, "2026-02-02", "2024-11-11", "2018-01-01", {}),
    (1029, 14, "Quelle est votre politique de sélection des intermédiaires ?",
     "Les intermédiaires sont évalués deux fois par an selon le prix, la qualité d'exécution, la recherche et la solidité "
     "financière ; la meilleure exécution est contrôlée par la table de négociation et la conformité.", 2, 9, "2025-12-12", "2025-03-03", "2018-01-01", {}),
    (1030, 14, "Décrivez la politique de rémunération.",
     "La rémunération variable des gérants dépend pour moitié des performances sur trois ans glissants et pour moitié de "
     "critères qualitatifs, dont le respect des risques et des critères ESG ; une partie est différée.", 2, 12, "2026-04-04", "2025-05-05", "2019-01-01", {}),
    (1031, 15, "Disposez-vous d'un plan de continuité d'activité ?",
     "Oui. Le plan de continuité d'activité prévoit un site de repli à 20 km, le télétravail sécurisé de l'ensemble des "
     "équipes et un test complet chaque année ; le dernier test a eu lieu en mars 2026.", 3, 22, "2026-07-07", "2026-03-30", "2017-01-01", {}),
    (1032, 15, "Comment protégez-vous vos systèmes contre les cyberattaques ?",
     "Authentification forte, chiffrement des postes, supervision par un centre opérationnel de sécurité et tests "
     "d'intrusion annuels par un cabinet indépendant ; les collaborateurs suivent une formation chaque semestre.", 2, 15, "2026-08-08", "2025-10-10", "2019-01-01", {}),
    (1033, 15, "Quelles assurances avez-vous souscrites ?",
     "La maison est couverte par une assurance responsabilité civile professionnelle et une assurance fraude, souscrites "
     "auprès de l'Assureur Imaginaire.", 1, 4, "2024-01-15", "2023-01-01", "2019-01-01", {}),
    (1034, 12, "Qui est le commissaire aux comptes de la société ?",
     "Les comptes de la société sont certifiés par le Cabinet d'Audit Imaginaire, mandaté depuis 2019.", 1, 10, "2026-01-08", "2024-12-01", "2019-01-01", {}),
    # ------------------------------------------------------------------ équipe
    (1035, 23, "Présentez l'équipe de gestion actions.",
     "L'équipe actions réunit huit gérants et cinq analystes, avec en moyenne 17 ans d'expérience ; elle est dirigée par "
     "le directeur des investissements, présent depuis 2004.", 3, 27, "2026-09-09", "2026-02-02", "2017-01-01", {}),
    (1036, 23, "Que se passe-t-il en cas de départ d'un gérant clé ?",
     "Chaque fonds est cogéré par deux gérants ; une clause de personne clé prévoit l'information des porteurs et le "
     "remplacement par le cogérant, qui connaît le portefeuille.", 2, 8, "2026-06-06", "2025-01-01", "2018-01-01", {}),
    (1037, 23, "Quel a été le taux de rotation des équipes ?",
     "Sur les cinq dernières années, deux professionnels de l'investissement ont quitté la maison, soit un taux de "
     "rotation annuel inférieur à 2 %.", 1, 6, "2025-09-09", "2025-01-01", "2019-01-01", {}),
    # ------------------------------------------------------------------ gestion, risques, ESG (niveau société)
    (1038, 21, "Comment construisez-vous les portefeuilles ?",
     "Les portefeuilles sont construits à partir des convictions des gérants : 40 à 60 lignes, poids maximal de 5 % par "
     "émetteur, contrôle de la liquidité et du budget de risque avant chaque ordre.", 2, 21, "2026-07-21", "2025-11-11", "2018-01-01", {}),
    (1039, 22, "Quelles limites de risque appliquez-vous ?",
     "Les limites portent sur l'exposition par émetteur, par secteur et par pays, la tracking error, la VaR et la "
     "liquidité ; elles sont paramétrées avant négociation et contrôlées chaque jour.", 2, 16, "2026-05-15", "2025-08-08", "2018-01-01", {}),
    (1040, 22, "Comment gérez-vous la liquidité des fonds ?",
     "La liquidité est mesurée chaque semaine par des tests de résistance de rachat ; les fonds ouverts disposent d'un "
     "mécanisme de swing pricing et, pour les fonds obligataires, de gates en cas de rachats exceptionnels.", 3, 18, "2026-08-18", "2026-02-20", "2019-01-01", {}),
    (1041, 33, "Quelle est votre politique d'exclusion ?",
     "Sont exclus de tous les fonds : les armes controversées, le tabac, le charbon thermique (plus de 10 % du chiffre "
     "d'affaires) et les sociétés en violation grave du Pacte mondial des Nations unies.", 4, 39, "2026-09-28", "2026-04-01", "2018-01-01", {}),
    (1042, 33, "Avez-vous une stratégie climat ?",
     "La maison a rejoint l'initiative Net Zero Asset Managers en 2022 : réduction de 50 % de l'intensité carbone des "
     "portefeuilles d'ici 2030 et sortie du charbon thermique en 2030 pour les pays de l'OCDE.", 2, 20, "2026-09-02", "2026-03-03", "2021-01-01", {}),
    (1043, 32, "Comment menez-vous l'engagement auprès des émetteurs ?",
     "L'engagement est mené par l'équipe d'investissement responsable avec les gérants : dialogue individuel, "
     "engagements collaboratifs et escalade jusqu'au vote contre la direction ou à l'exclusion.", 2, 13, "2026-07-12", "2025-12-12", "2019-01-01", {}),
    (1044, 31, "Êtes-vous signataire des PRI ?",
     "Oui, la maison est signataire des Principes pour l'investissement responsable (PRI) depuis 2012.", 1, 25, "2026-10-01", "2024-01-01", "2016-01-01", {}),
    (1045, 31, "Combien de fonds sont classés article 8 ou 9 SFDR ?",
     "Douze fonds sont classés article 8 et deux fonds article 9 au sens du règlement SFDR, soit 78 % de l'encours ouvert.",
     3, 19, "2026-09-15", "2026-06-30", "2021-03-10", {}),
    (1046, 31, "Comment intégrez-vous les critères ESG dans l'analyse ?",
     "Chaque émetteur reçoit une note ESG interne combinant des données externes et l'analyse des gérants ; la note "
     "intervient dans le choix des titres et dans la taille des positions.", 2, 17, "2026-08-25", "2025-10-01", "2019-01-01", {}),
    # ------------------------------------------------------------------ opérations
    (1047, 43, "Quelle est l'heure limite de centralisation des ordres ?",
     "Les ordres de souscription et de rachat sont centralisés chaque jour ouvré à 12 h 00 (heure de Paris) et exécutés "
     "sur la valeur liquidative du jour ; règlement à J+2.", 2, 30, "2026-09-19", "2025-06-06", "2016-01-01", {}),
    (1048, 43, "Qui est l'agent de transfert ?",
     "La tenue du registre et la centralisation des ordres sont confiées à Teneur de Registre Imaginaire.", 1, 12, "2026-02-12", "2024-02-01", "2016-01-01", {}),
    (1049, 41, "Comment les titres peu liquides sont-ils valorisés ?",
     "Les titres sans cours fiable sont valorisés par un comité de valorisation indépendant de la gestion, à partir de "
     "prix de contributeurs ou d'un modèle documenté.", 1, 7, "2025-08-08", "2024-09-09", "2019-01-01", {}),
    # ------------------------------------------------------------------ Fonds Imaginaire Horizon (actions européennes)
    (1050, 51, "Décrivez la stratégie du Fonds Imaginaire Horizon.",
     "Le Fonds Imaginaire Horizon investit dans 40 à 50 grandes et moyennes capitalisations européennes de qualité, "
     "sélectionnées pour la régularité de leurs résultats ; l'exposition actions est comprise entre 90 % et 100 %.", 3, 24, "2026-09-12", "2026-01-15", "2020-01-01", {}),
    (1051, 51, "Quel est l'indicateur de référence du Fonds Imaginaire Horizon ?",
     "L'indicateur de référence du Fonds Imaginaire Horizon est l'indice Imaginaire Europe Actions dividendes réinvestis.",
     1, 15, "2026-06-01", "2024-05-05", "2020-01-01", {}),
    (1052, 51, "Quel est le minimum de souscription de la part I du Fonds Imaginaire Horizon ?",
     "La part I (ISIN QZ0000000037), réservée aux investisseurs institutionnels, a un minimum de souscription initiale "
     "de 1 000 000 EUR ; la part C (ISIN QZ0000000011) n'a pas de minimum.", 2, 9, "2026-07-07", "2025-07-07", "2020-01-01", {}),
    (1053, 51, "Quels sont les frais de gestion des parts du Fonds Imaginaire Horizon ?",
     "Frais de gestion financière maximum : 1,60 % pour la part C, 0,80 % pour la part I ; commission de surperformance "
     "de 15 % au-delà de l'indicateur de référence, avec high water mark.", 2, 14, "2026-08-30", "2025-12-31", "2020-01-01", {}),
    # ------------------------------------------------------------------ Fonds Imaginaire Aurore (obligations)
    (1054, 52, "Décrivez le processus de gestion du Fonds Imaginaire Aurore.",
     "Le Fonds Imaginaire Aurore est un fonds obligataire euro : la sensibilité est pilotée entre 0 et 6, les émetteurs "
     "sont sélectionnés par l'analyse crédit interne et la part du haut rendement est limitée à 20 %.", 2, 12, "2026-05-25", "2025-04-04", "2021-08-08", {}),
    (1055, 52, "Quel est l'indicateur de référence du Fonds Imaginaire Aurore ?",
     "L'indicateur de référence du Fonds Imaginaire Aurore est l'indice Imaginaire Obligations Euro Agrégé.", 1, 6, "2025-10-10", "2024-03-03", "2021-08-08", {}),
    (1056, 52, "Le Fonds Imaginaire Aurore peut-il utiliser des dérivés ?",
     "Oui, le Fonds Imaginaire Aurore utilise des contrats à terme de taux et des swaps de défaut à des fins de couverture "
     "et d'exposition, sans effet de levier supérieur à 100 % de l'actif.", 1, 5, "2025-12-01", "2025-01-10", "2021-08-08", {}),
    # ------------------------------------------------------------------ Fonds Imaginaire Boréal (multi-actifs)
    (1057, 53, "Quel est l'objectif de gestion du Fonds Imaginaire Boréal ?",
     "Le Fonds Imaginaire Boréal est un fonds multi-actifs flexible : il vise une performance annualisée supérieure à "
     "€STR + 3 % sur cinq ans, avec une volatilité cible inférieure à 8 %.", 2, 10, "2026-09-05", "2026-02-15", "2022-01-01", {}),
    (1058, 53, "Comment est réalisée l'allocation du Fonds Imaginaire Boréal ?",
     "Un comité d'allocation mensuel fixe les poids des actions (0 à 50 %), des obligations (0 à 100 %) et des devises ; "
     "les gérants ajustent l'exposition au jour le jour à l'aide de contrats à terme.", 1, 7, "2026-04-14", "2025-09-01", "2022-01-01", {}),
    (1059, 53, "Quels sont les frais du Fonds Imaginaire Boréal ?",
     "Frais de gestion maximum de 1,20 % pour la part R et 0,60 % pour la part I ; pas de commission de surperformance.",
     1, 3, "2025-07-01", "2025-01-01", "2022-01-01", {}),
    # ------------------------------------------------------------------ anglais
    (1060, 61, "Please describe the firm and its ownership.",
     "Imaginary Asset Management is an independent asset manager founded in 1998. 62% of the capital is held by its "
     "managing partners and 38% by the Imaginary Foundation, a long-term shareholder.", 2, 18, "2026-09-22", "2026-01-11", "2018-01-01", EN),
    (1061, 61, "What are the firm's assets under management?",
     "As of 30 June 2026 the firm managed EUR 14.2 billion: 48% equities, 32% fixed income, 15% multi-asset and 5% money market.",
     3, 21, "2026-09-25", "2026-07-05", "2018-01-01", EN),
    (1062, 61, "Describe your business continuity plan.",
     "Our business continuity plan includes a backup site 20 km from Paris, secure remote working for all staff and a "
     "full annual test, last performed in March 2026.", 1, 9, "2026-06-30", "2026-03-30", "2019-01-01", EN),
    (1063, 62, "Describe the investment process of Imaginary Horizon Fund.",
     "Fonds Imaginaire Horizon (Imaginary Horizon Fund) invests in 40 to 50 high-quality European large and mid caps "
     "selected for the consistency of their earnings, with 90% to 100% equity exposure.", 2, 11, "2026-08-14", "2026-01-15", "2020-01-01", EN),
    (1064, 62, "What is your exclusion policy?",
     "All funds exclude controversial weapons, tobacco, thermal coal (above 10% of revenue) and companies in severe "
     "breach of the UN Global Compact.", 2, 16, "2026-09-18", "2026-04-01", "2019-01-01", EN),
    # ------------------------------------------------------------------ pièges : textes voisins, dépassés, vides
    (1065, 21, "Quelle est votre philosophie d'investissement ?",
     "Nous croyons qu'une analyse fondamentale exigeante, menée par des gérants qui rencontrent les entreprises, permet "
     "de battre durablement les marchés ; nos portefeuilles sont concentrés et de long terme.", 3, 33, "2026-09-30", "2026-02-02", "2015-01-01", {}),
    (1066, 21, "Quelle est votre philosophie d'investissement ?",
     "Nous croyons à l'analyse fondamentale et aux portefeuilles concentrés de long terme.", 1, 4, "2021-01-01", "2020-01-01", "2015-01-01", {}),
    (1067, 31, "Quels labels vos fonds ont-ils obtenus ?",
     "Six fonds bénéficient du label ISR et un fonds du label Towards Sustainability.", 2, 12, "2026-05-30", "2025-11-30", "2020-01-01", {}),
    (1068, 13, "Votre société emploie-t-elle des stagiaires ?",
     "TBD", 1, 0, None, "2022-02-02", "2022-02-02", {}),
]

__all__ = ["FOLDERS_EXTRA", "CONTENTS_EXTRA"]
