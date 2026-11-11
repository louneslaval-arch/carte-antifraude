# Carte antifraude EQDOM : consignes permanentes

Dépôt de la carte des réseaux de fraude au crédit d'EQDOM (SEVEN) : liste noire × registre du commerce × dossiers de
l'antifraude v2 de Kamal, mise à jour au fil de l'eau. Tout est en français, sauf les noms repris de la v2.

Documents de référence, à lire quand l'étape le demande :
- `docs/plan_construction.md` : étapes A à N, préalables, définition de fini, état ;
- `docs/journal_etapes.md` : ce qui a été fait ; sa dernière entrée dit où on en est ;
- `docs/architecture_temps_reel.md` : socle publié et couche vivante, composants, tables, routes, tests ;
- `docs/source_v2.md` : la v2 de Kamal (objets, champs, pièges) et les règles d'alignement ;
- `docs/correspondance_v2.md` (à partir de l'étape B) : chaque entité et champ de la v2 → table et colonne de la base ;
- `docs/couches.md` : contenu des couches c0 à c7 ;
- `docs/decisions.md` : décisions métier n°1 à 24 ; `docs/questions_ouvertes.md` : ce qui reste à trancher ;
- `docs/skills.md` : skills et plugins installés, leur source et leur contrôle ;
- `docs/LANCEMENT_construction_temps_reel.md` (à la racine jusqu'à la fin de l'étape 1) : la feuille de mission d'origine.

## Règles absolues

1. **Données réelles : jamais.** Tu ne lis, n'ouvres, ne copies et ne lances rien sur des données réelles. Elles vivent hors
   du dépôt : `~/antifraude-donnees/` et les emplacements de `.claude/hooks/chemins_interdits.txt`. Un essai réel, c'est
   Lounès qui le lance dans son terminal, avec la commande que tu prépares (skill `essai-donnees-reelles`) ; il ne te
   rapporte que des comptages. Si une donnée qui semble réelle apparaît, tu ne la réutilises pas et tu le signales.
2. **Seulement du fictif dans le dépôt et les tests** : CIN et références de dossier commençant par « ZZ » ; identifiants
   numériques (RIB, ICE, n° CNSS, n° d'affiliation) commençant par « 999 » ; courriels en `@exemple.invalid` ; noms tirés
   de syllabes. Une forme réelle voulue (test d'un refus) est construite par concaténation ou porte `fictif-volontaire`
   sur sa ligne.
3. **Aucune donnée personnelle** dans une URL, un journal technique, un message d'erreur, une trace d'exception, un
   événement, une modification de carte, le JSON pour Tandem, ni dans la sortie console d'un script qui peut tourner sur
   des données réelles (comptages et identifiants techniques seulement). Le journal d'audit garde des indices ; la
   requête de recherche n'est jamais journalisée.
4. **Rien vers l'extérieur** : ni bibliothèque, ni police, ni tuile, ni géolocalisation chargée par les pages ; aucun appel
   à un service externe dans le code ; aucun serveur MCP ; aucune dépendance nouvelle sans accord.
5. **Qui est fraudeur** : seules la liste noire et les fraudes confirmées par la cellule fraude le disent. Un verdict
   Tandem est un signal, jamais une étiquette ni une cible. Le score ordonne et alerte ; il ne refuse jamais un dossier
   (loi 09-08, article 11).
6. **Statistiques** : le sexe et la nationalité ne servent jamais à un taux de suspicion ; aucun chiffre sur moins de 5 clients.
7. **Garde-fous intouchables** : pas de `--no-verify`, pas d'ajout forcé d'un fichier ignoré, pas de changement de
   `core.hooksPath`, de `.claude/settings.json`, `.claude/hooks/`, `.githooks/` ou `outils/garde/` sans demande explicite
   de Lounès. Les tests de mutation ne tournent que dans le sous-agent `testeur-mutation` (copie jetable), jamais ici.

## Structure de Kamal d'abord

- Ce qui vient de la v2 ou y retourne garde ses entités, ses noms, ses clés, ses énumérations et ses formats :
  `schema.prisma`, `web_types.ts`, `engine-core_types.ts` et contrats de `reference/v2/` (ou `import/kamal_structure/`).
- Le miroir de la v2 (couche 0) reproduit les tables et colonnes de sa base à l'identique, noms compris (ceux que
  PostgreSQL voit, après `@map` et `@@map`) ; il est généré depuis `schema.prisma`, jamais écrit à la main.
- Nos tables dérivées reprennent ses noms de concepts et ses clés (`ref`, `upstreamPieceId`, `controlId`…) ; un nom
  nouveau n'existe que pour ce que la v2 n'a pas, et il est justifié dans `docs/correspondance_v2.md`.
- Le vocabulaire canonique des faits est le vocabulaire « moteur » de la v2 (correspondance du README de Kamal, § 4).
- Ce qu'on renvoie à la v2 ou à Tandem suit ses formats (un contrôle au format d'un élément de `controls[]`, des
  indicateurs au format d'`IndicateurDossier`), avec les valeurs d'énumération de ses types.
- Si la structure de Kamal change (nouveau lot), la carte de correspondance et le miroir se régénèrent ; un test le vérifie.

## Façon de travailler

- Une étape à la fois, lancée par `/deroule-etape <lettre>` ; une étape = une couche = une branche `etape-<lettre>-<sujet>`.
- Tests d'abord (rouges pour la bonne raison), puis le code. Le test « flux = lot » ne régresse jamais.
- Choix discutable (dépendance, schéma hors plan, écart avec la spécification ou avec la structure de Kamal, valeur métier
  non décidée) : tu le signales et tu attends la réponse avant de coder. Une valeur non décidée se lit dans
  `c6_version_parametres`, marquée « provisoire ».
- Fin d'étape : vérification complète ; sous-agents `relecteur`, `gardien-donnees`, `verificateur-spec` (plus
  `testeur-mutation` aux étapes B, E, F, H, I) ; journal ; compte rendu ; **arrêt**. Fusion dans `main` seulement sur accord.
- Rien hors du périmètre de l'étape, même pour améliorer : le noter dans le compte rendu.
- Une contradiction dans la spécification se remonte à Lounès ; elle ne se tranche pas en silence.

## Commandes

- Tests : `.venv/bin/python -m pytest api/tests pipeline/tests jeu_essai/tests outils/garde/tests .claude/hooks/tests`
  (à partir de l'étape B : `.venv/bin/python -m pytest`, chemins déclarés dans la configuration de pytest).
- Vérification complète (à partir de l'étape B) : `outils/verifier_tout.sh`.
- Garde des données : `.venv/bin/python outils/garde/garde_donnees.py --tout` (ou `--arbre`, `--index`).
- Jeu d'essai : `jeu_essai/construire.sh [kit|petit|moyen|grand]`. Couches (à partir de l'étape B) :
  `.venv/bin/python construire.py --jeu-essai` puis `.venv/bin/python verifier.py`.
- API locale : `api/lancer_essai.sh` (port 8710, publication fictive du kit).

## Conventions

- Français : modules, fonctions, variables, tables, colonnes, messages, commentaires, documents. Restent tels quels les
  noms imposés par une bibliothèque, un protocole ou la v2 de Kamal.
- Python du `.venv` (3.13), code compatible 3.10. Normalisation en fonctions pures dans `pipeline/normalisation/`.
- SQL portable SQLite et PostgreSQL ; schéma seulement par migrations numérotées `schema/NNN_<objet>.sql` et `schema_version`.
- Tables préfixées par couche (`c0_` à `c7_`), `flux_` pour le temps réel, `ref_` pour les référentiels saisis à la main ;
  le miroir de la v2 garde les noms exacts de Kamal. Décisions d'analyste, levées, exclusions et référentiels vivent
  hors des tables reconstruites.
- Identifiants internes stables, jamais renumérotés ; une fiche sans mention est désactivée.
- Enregistrements git en français, à l'impératif, préfixés par l'étape : « H : lire le coût de taille dans les compteurs ».

## Notions

- Lien = arête entre deux personnes ou sociétés. Un identifiant partagé (RIB, n° d'affiliation, châssis) est un nœud, pas un lien.
- Longueur d'un chemin = nombre de liens depuis l'identité du dossier la plus proche (demandeur, caution, gérant, société, employeur).
- Niveaux : 0 lien critique ; 1 ou 2 majeure ; 3 mineure ; 4 et plus affiché en gris, jamais d'alerte. Détail : `.claude/rules/score.md`.
- Un seul écrivain (le traiteur), une transaction par dossier ; la nuit fait foi ; une alerte ne baisse pas en journée.

## Arborescence

```
pipeline/      normalisation/, couches/ (c0 à c6 : construire_tout() et traiter(ref)), regles/, scripts du kit
flux/          collecteur, file, traiteur, graphe vivant, passe de nuit
schema/        migrations numérotées (dont le miroir de la v2, généré depuis schema.prisma)
api/           FastAPI : routes, rôles (table unique des droits dans app/roles.py), journal, quotas
front/         pages (aucune ressource externe)
jeu_essai/     données fictives, générateurs, v2/ (dossiers et serveur v2 fictifs, au format des types de Kamal)
reference/     référentiels (villes, grands employeurs) et v2/ : copie datée de la structure de la v2 de Kamal
outils/        garde/ (garde des données), v2/ (lecture de schema.prisma et des types), qualité, verifier_tout.sh
deploiement/   conteneurs api, traiteur, postgres, nginx
docs/          spécification, correspondance v2, décisions, plan, journal, registre des skills
.claude/       réglages, crochets, règles par dossier, sous-agents, skills
```
