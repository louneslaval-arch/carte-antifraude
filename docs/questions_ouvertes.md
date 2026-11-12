*Ce qui reste à trancher. Tant qu'une question n'est pas tranchée, le code applique la proposition provisoire, la lit dans un paramètre et la marque « provisoire ». Claude Code ajoute les nouvelles questions ; seul Lounès les clôt.*

| N° | Question | Proposition provisoire | Qui tranche | Bloque |
| ---: | --- | --- | --- | --- |
| 1 | Droits du rôle AGENCE : il reçoit aujourd'hui l'indicateur liste noire et `carte.noms` | les lui retirer (décision n°10), ou faire valider l'écart par la conformité | Lounès, conformité EQDOM | J |
| 2 | Seuils de force | majeure à partir de 0,20 ; mineure à partir de 0,08 ; affichage par défaut à partir de 0,05 | Lounès et cellule fraude (calibrage sur les fraudes confirmées) | mise en service |
| 3 | Victime (question 8 du 09/11) | tout inscrit actif pèse 1 ; une inscription qui désigne une victime ne compte qu'à 0 lien ; en attendant le dictionnaire des motifs, toutes propagent | EQDOM (dictionnaire des motifs) | I |
| 4 | Effet du temps | rôles terminés aux poids actuels des anciens rôles (0,3 à 0,5) ; pas de demi-vie | Lounès | H |
| 5 | Même identifiant dans plusieurs dossiers récents | signal à part « dossiers en rafale » (même RIB, même adresse ou même employeur inconnu dans plusieurs dossiers en moins de 30 jours), sans toucher à la force | Lounès | G |
| 6 | Liens du JSON v2 hors barème | même châssis : incohérence « double financement » ; même concessionnaire : hors score, comme l'apporteur | Lounès | G, H |
| 7 | Levée d'alerte puis nouveau chemin | la levée vaut pour le couple (dossier, inscrit) ; un chemin d'une autre nature qui fait monter le niveau rouvre l'alerte | Lounès | I |
| 8 | Sens du retour vers Tandem | Tandem relève `GET /api/controles?depuis=…` | Kamal | I, J |
| 9 | Outils de développement | ruff en vérification seule, mypy (normalisation, lecteurs de structure), hypothesis, mutmut 2.5.1 figé, pyright | Lounès | A |
| 10 | Intégration continue | crochet git local et `verifier_tout.sh` tant qu'il n'y a pas de dépôt distant | Lounès | B |
| 11 | Bibliothèque de dessin des pages | aucune : SVG et Canvas natifs | Lounès | K |
| 12 | Pseudonymisation du stockage | à proposer à l'étape M | Lounès, conformité | M |
| 13 | Exemples de noms et identifiants de la notice du kit | les remplacer par des exemples fictifs s'ils viennent des données réelles | Lounès | A |
| 14 | Montée de version de FastAPI (le skill officiel est livré avec le paquet) | à décider à l'étape J, tests à l'appui | Lounès | J |
| 15 | Versionner la structure de Kamal (sans `api/`) dans `reference/v2/` | oui, copie datée avec empreintes ; sinon elle reste dans `import/` et seule la carte de correspondance est versionnée | Kamal, Lounès | A |
| 16 | Noms dans nos tables dérivées | le miroir garde les noms exacts de Kamal ; nos tables dérivées reprennent ses mots en minuscules à tirets bas (`upstreamPieceId` devient `upstream_piece_id`) pour un SQL simple sur les deux moteurs ; autre choix possible : noms exacts partout, entre guillemets | Lounès | B |
| 17 | Le contrôle « lien avec la liste noire » dans la matrice de la v2 | un identifiant de contrôle réservé, une famille propre au réseau, une correspondance critique, majeure, mineure vers l'échelle de criticité de la v2 | Kamal | I |
| 18 | PostgreSQL dès le prototype, comme la v2 | SQLite reste sur le Mac ; le miroir et les migrations sont aussi testés sur PostgreSQL dès l'étape D si Lounès l'installe en local | Lounès | D |
| 19 | S'aligner aussi sur la technique de Kamal (TypeScript, Prisma) | non : le code reste en Python (acquis, tests) ; même modèle, mêmes noms, mêmes formats | Lounès | — |
| 20 | Scénario S04 contre la règle d'homonymie : l'attestation de travail ne porte que le nom de l'employeur, que `score.md` plafonne à « mineure » (S12), alors que S04 attend « majeure, 0,7 » | S04 suppose un employeur reconnu par une clé sûre (ICE ou RC + tribunal tirés d'une autre pièce) ; le générateur de l'étape F le dira explicitement | Lounès, cellule fraude | F |
| 21 | Description de `jeu-essai-v2` (imposée par l'annexe H.2) : elle se déclenche aussi pour une liste noire fictive de charge et pour une question sur le format de `DossierDetail` (2 écarts sur 15 à l'essai de déclenchement) | retirer `DossierDetail` de la description et ajouter « pas pour une question sur le format réel de la v2, ni pour des données de charge » | Lounès | F |
| 22 | Tests de mutation : le bac à sable interdit les pseudo-terminaux dont mutmut a besoin ; le sous-agent `testeur-mutation` ne peut donc pas tourner | soit Lounès lance mutmut dans la copie de travail et donne les résultats au sous-agent, soit le bac à sable autorise les pseudo-terminaux (affaiblit le cadre : à éviter) | Lounès | B (première étape avec mutation) |
| 23 | Constats de `gardien-donnees` hors de l'étape 1 : identifiant d'inscrit gardé dans le stockage du navigateur (`pipeline/carte_chaines_modele.html:194`) ; statistiques par ville et par règle servies à tous les rôles sans masque sous 5 (`api/app/routes/stats.py`) ; message 409 qui recopie un chemin du serveur ; lien externe sans `noreferrer` | à corriger à l'étape où ces fichiers sont repris (A pour la page, J pour l'API) | Lounès | A, J |

### À obtenir

| De qui | Quoi | Bloque |
| --- | --- | --- |
| Lounès | la structure du lot de Kamal (sans `api/`), le kit du 11/11, les référentiels du 21/10, dans `import/` | A |
| Lounès | `extraire_json_v2.py` et `profil_json.py` dans `import/v2/` | E |
| Kamal | accord pour versionner sa structure ; nouveau lot de structure à chaque changement de `schema.prisma` ou des types | A, puis à chaque changement |
| Kamal | un compte de service en lecture sur `/api/dossiers` et `/api/dossiers/:ref` (avec `archives`) | D sur la v2 réelle |
| Kamal | la liste triée par mise à jour, ou `GET /api/dossiers?modifies_depuis=…` (demandé le 28/10), avec `updatedAt` et `analysisStatus` dans chaque élément | délai de la scrutation |
| Kamal | la notification signée à la fin de chaque analyse, ou une table d'événements sortants | M (15 s au lieu de 2 min) |
| Kamal | un accès en lecture (ou une extraction) des tables `Piece`, `IntakeMessage`, `IndicateurDossier`, `Employeur`, `BlacklistEntry`, `AnalysisControl` | miroir complet, puis production |
| Kamal | l'identifiant, la famille et l'échelle de criticité du contrôle « lien avec la liste noire » ; le sens du retour | I, J |
| Kamal | les demandes déjà faites : relecture de tous les relevés, provenance par champ, année des dates d'opération, clés inventées filtrées, champs du dossier (montant, durée, apport, mensualité, agence, canal, statut final), empreinte des pièces | qualité des liens |
| EQDOM | dictionnaire des motifs de la liste noire (victime ou auteur) ; profils et droits ; feu vert de la conformité | I, L |
