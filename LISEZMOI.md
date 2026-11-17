# Carte antifraude EQDOM

Application qui remplace les cartes HTML autonomes (toutes les données embarquées) par une page servie par une
interface de programmation qui contrôle l'accès aux identités et journalise chaque consultation.

- **Couche 1 « géométrie »** : positions, types, indicateur liste noire, réseaux, villes. N'identifie personne.
  Envoyée entière au chargement.
- **Couche 2 « identité »** : noms, CIN, RC, rôles, annonces, motifs. Servie à la demande, selon le rôle,
  journalisée.

## État

| Étape | Contenu | État |
| --- | --- | --- |
| 1 | dépôt, jeu d'essai, scripts du kit | fait |
| 2 | `publier_carte.py` (couches 1 et 2, manifeste) | fait pour la carte par inscrit ; carte globale en attente de `carte_globale.py` |
| 3 | interface de programmation en lecture | fait (journal testé sur SQLite ; PostgreSQL à l'étape 5) |
| 4 | pages branchées sur l'interface | à faire |
| 5 | déploiement | à faire |
| 6 | proximité, décisions, jeton Tandem | à faire |
| 7 | pseudonymisation du stockage | à faire |

## Règle de base

**Aucune donnée réelle dans ce dépôt ni sur un poste de développement.** Le développement et les tests se font
uniquement sur `jeu_essai/donnees/` (entièrement fictif). Le `.gitignore` refuse les bases, classeurs, CSV,
JSON, pages générées et fichiers de secrets.

## Publication

`pipeline/publier_carte.py --base … --chaines chaines.json --sortie publication/<date>` écrit quatre fichiers :

| Fichier | Contenu |
| --- | --- |
| `geometrie.json` | couche 1 : pour chaque nœud (indice opaque) son type, l'indicateur liste noire, son réseau, son degré, sa ville ; les arêtes (style, force) ; pour chaque inscrit la structure de sa carte (nœuds, arêtes avec le libellé du rôle, chaînes réduites à distance, fiabilité, force, liste noire oui ou non) |
| `identites.sqlite` | couche 2 : `noeud` (indice → identifiant interne), `identite` (nom, CIN, RC, tribunal, ville, listes, motifs), `lien`, `annonce`, `chaine` (chaîne complète au format de la carte actuelle), `recherche` (nom, CIN, RC) |
| `statistiques.json` | agrégats sans identité : correspondances retenues par règle et niveau, et par statut |
| `manifeste.json` | date, nombre de nœuds et d'inscrits, `fictif` (vrai seulement si tous les CIN commencent par « ZZ »), empreintes SHA-256 |

Les indices sont tirés au hasard à chaque publication : ils ne révèlent ni l'ordre alphabétique ni le RC.
Un libellé de rôle hors du vocabulaire du kit ne passe pas en couche 1. Tests : `python3 -m pytest pipeline/tests jeu_essai/tests`.

## Interface de programmation (`api/`)

```
.venv/bin/pip install -r api/requirements.txt pytest
jeu_essai/construire.sh kit && api/lancer_essai.sh          # essai local sur le kit fictif, port 8710
```

Réglages (variables d'environnement, jamais dans le dépôt) :

| Variable | Rôle | Par défaut |
| --- | --- | --- |
| `CARTE_CLE_JWT` | clé de signature des jetons, 32 caractères au moins | obligatoire |
| `CARTE_BASE_URL` | base des comptes, révocations et journal (PostgreSQL en service) | obligatoire |
| `CARTE_PUBLICATION` | dossier de la publication courante | aucune (503) |
| `CARTE_DONNEES_REELLES` | `1` pour accepter une publication dont un CIN n'est pas en « ZZ » | refus |
| `CARTE_QUOTA_ETIQUETTES` | indices distincts nommés par heure et par utilisateur | 20 000 |
| `CARTE_QUOTA_FICHES` | fiches et chaînes par heure et par utilisateur | 2 000 |
| `CARTE_DEBIT`, `CARTE_DEBIT_CONNEXION` | requêtes par utilisateur ; connexions par adresse | 60/minute, 10/minute |
| `CARTE_JOURNAL_JOURS` | conservation du journal d'audit | 365 |
| `CARTE_ORIGINE` | seule origine admise par CORS | aucune |
| `CARTE_DUREE_JETON_S` | durée du jeton | 28 800 (8 h) |

Comptes : `python -m app.comptes creer IDENTIFIANT ROLE` (mot de passe demandé, 12 caractères au moins),
`deverrouiller`, `desactiver`, `lister` — lancé depuis `api/` avec les mêmes variables.

Routes : `/api/sante` (public) ; `/api/auth/connexion`, `/api/auth/deconnexion` ; `/api/carte/geometrie` (tous) ;
`/api/carte/noms` (analyste, agence) ; `/api/carte/noeud/{indice}`, `/api/carte/recherche`,
`/api/chaines/inscrits`, `/api/chaines/{indice}` (analyste) ; `/api/stats/villes`, `/api/stats/regles` (tous) ;
`/api/admin/recharger`, `/api/admin/journal` (administrateur). Droits : table unique dans `api/app/roles.py`.

Garanties vérifiées par les tests (`.venv/bin/python -m pytest api/tests`) : aucune réponse d'erreur ne recopie
une valeur reçue ; aucune trace d'exception ne part avec son message ; la requête de recherche n'est jamais
journalisée ; un identifiant de connexion inconnu est écrit « inconnu » ; toute réponse porte
`Cache-Control: no-store`, sauf la géométrie (ETag). Au démarrage et à chaque rechargement, le journal plus
ancien que `CARTE_JOURNAL_JOURS` et les révocations de jetons expirés sont purgés.

## Construire le jeu d'essai

```
jeu_essai/construire.sh            # petit jeu du kit (9 inscrits)
jeu_essai/construire.sh moyen      # données générées : petit, moyen ou grand
```

Produit dans `jeu_essai/sortie/<taille>/` : la base `essai.sqlite`, son bilan, les chaînes (classeur, carte
autonome, JSON) et le rapport de croisement. Python 3.9 ou plus, avec pandas et openpyxl.

`jeu_essai/generer.py` fabrique un registre et une liste noire fictifs à l'échelle voulue, au format d'entrée du
pipeline : noms tirés de syllabes (en latin et en arabe), homonymies fréquentes, dirigeants présents dans plusieurs
sociétés, inscrits retrouvables par chacune des règles R01 à R08, sociétés aux RC consécutifs, saisies abîmées.
Il écrit aussi `verite.json` (ce qui a été caché exprès), pour mesurer ce que le pipeline retrouve.
Tous les CIN commencent par « ZZ », tous les liens pointent vers `exemple.invalid`.

| Taille | Sociétés | Annonces | Inscriptions | Construction complète |
| --- | ---: | ---: | ---: | ---: |
| petit | 423 | 660 | 68 | 1 s |
| moyen | 8 272 | 12 743 | 354 | 13 s |
| grand | 61 043 | 96 519 | 2 714 | 125 s |

## Statistiques des dossiers (couche 7)

Vue chiffrée des demandes et de ce que l'antifraude en dit : volumes, profils, verdicts par segment, contrôles,
qualité des données. Ces chiffres servent de taux de base aux autres modules. Le verdict est celui de l'antifraude
(« jugé suspect par l'antifraude ») : un signal, jamais une fraude constatée.

```
.venv/bin/python construire.py --base CHEMIN.sqlite            # couches c0 à c5 (les données réelles : Lounès, hors du dépôt)
.venv/bin/python stats_dossiers.py --base CHEMIN.sqlite \
    [--periode-debut 2026-10-13] [--periode-fin 2026-11-10] [--avec-archives] \
    [--html CHEMIN/statistiques_dossiers.html] [--avec-noms-societes]
```

Sur données réelles, la base et la page restent hors du dépôt, dans le dossier des données réelles ; jamais dans le
dossier courant.

Sur le jeu d'essai (600 dossiers fictifs dont 11 archivés, construits en 3 s) :

```
.venv/bin/python jeu_essai/v2/statistiques/generer_v2_fictif.py --base      # jeu_essai/sortie/statistiques_essai.sqlite
.venv/bin/python stats_dossiers.py --base jeu_essai/sortie/statistiques_essai.sqlite --html jeu_essai/sortie/statistiques_dossiers.html
```

- **Tables** (`schema/070_c7_analytique.sql`), reconstruites entièrement à chaque exécution (deux exécutions de suite
  donnent la même table, hors horodatage) : `c7_indicateur` (dictionnaire, version 1, `pipeline/analytique/indicateurs.py`
  fait foi) ; `c7_variable_dossier` (une ligne par dossier, table de travail jamais servie) ; `c7_agregat` (une case par
  indicateur, tranche de filtre produit × catégorie et découpage).
- **Sources** : `c3_dossier`, `c3_revenu`, `c3_compte`, `c3_vehicule`, `c1_fait_retenu`, `c1_mention_personne`,
  `c1_piece`, `c1_releve_mois`, et les contrôles du miroir (`"AnalysisControl"`, dernière analyse ; la famille vient
  de la version brute). Montants, dates et villes : normalisation et référentiel du dépôt.
- **Secret statistique** (`pipeline/analytique/secret.py`, `agregats.proteger`) : aucune valeur sur moins de 5 dossiers
  (l'effectif compte toujours des dossiers, jamais des pièces ni des occurrences) ; un taux de verdict ou de contrôle
  n'est pas publié sur 1 à 4 dossiers, ni quand il désigne tous les dossiers d'un groupe à moins de 5 près (« 7 sur 7 ») ;
  une répartition qui n'aurait qu'une case masquée en masque une seconde (la plus petite), ligne par ligne et colonne par
  colonne pour un croisement ; un compte masqué l'est sous tous les indicateurs qui le publient (médiane, taux,
  remplissage de la variable), jusqu'à stabilité. Une case masquée n'a aucune valeur dans la table (ni nombre, ni
  effectif, ni fourchette) ; la page l'affiche grisée, hachurée, « secret ». Médianes à partir de 5 valeurs, jamais de
  minimum ni de maximum. Texte venu des pièces (nationalité, situation familiale, marque, sociétés, éléments manquants) :
  une valeur citée par moins de 5 dossiers est regroupée avant le calcul, elle ne sort jamais.
- **Critères interdits** : le sexe et la nationalité ne servent qu'en répartition simple des demandeurs, dans la tranche
  « tous × toutes » seulement : jamais croisés avec un verdict, un contrôle, un produit, une catégorie ni une autre
  dimension (constantes `DIMENSIONS_TAUX` et `DIMENSIONS_REPARTITION_SEULE`).
- **Noms de sociétés** (banques, employeurs, concessionnaires) : seulement avec `--avec-noms-societes` (à valider avec la
  conformité), et seulement ceux qui comptent 5 dossiers ou plus ; les autres sont regroupés, leur nom ne sort jamais.
- **Page** : un seul fichier HTML (`pipeline/statistiques_modele.html` + cases non masquées en JSON), hors ligne, sans
  aucune ressource externe ; cinq onglets (demandes, profils, verdicts, contrôles, qualité des données), filtres produit
  et catégorie, chaque taux avec son effectif et sa fourchette de Wilson à 95 %, tableau dépliable et copiable sous
  chaque graphique.
- **Limites** : le secret secondaire protège chaque répartition, pas la soustraction entre tranches de filtre (par
  exemple LOA = tous − DISPO − AUTO dans une catégorie) ; les régions sont dessinées en barres (le contour du dépôt
  suit l'ancien découpage en 16 régions) ; agence, canal, montant demandé et remboursements manquent encore à la v2.

## Décisions prises

- **Deux quotas distincts** (remplace « 2 000 identités par heure ») : les **étiquettes** (nom seul, au zoom) sont
  comptées en indices *nouveaux* par session, le cache du navigateur n'étant pas recompté, avec un plafond large ;
  les **fiches complètes** (CIN, RC, motifs, annonces) restent limitées à 2 000 par heure et par analyste.
  Sans cela, 5 déplacements de zoom à 400 étiquettes épuisaient le quota de l'heure.
- **Couche 1** : envoyée telle quelle à tous les rôles, indicateur liste noire compris (choix assumé).
- **Garde-fou des données réelles** : fondé sur le préfixe « ZZ » de tous les CIN (manifeste `fictif`), et non
  sur un seuil de 5 000 inscrits que la vraie liste (4 717 personnes) ne dépasse pas.
- **Quotas** calculés depuis le journal d'audit (une seule source, valable avec plusieurs processus) ; les
  limites de débit, elles, sont comptées en mémoire par processus.
- **Limites de débit** : bibliothèque `limits` directement (slowapi 0.1.9 plante sur une limite calculée).
- **Recherche** : la requête n'est jamais journalisée, même quand ce n'est pas un CIN (un nom est une identité).
- **Verrouillage** : après 5 échecs, jusqu'au déverrouillage par l'administrateur (pas de délai automatique).

## Travailler avec Claude Code

- Ouvrir la séance **sur ce dossier** : les réglages (`.claude/settings.json`), les crochets et le bac à sable ne se
  chargent que là. Le rappel de début de séance (fin du journal, règles) prouve qu'ils sont actifs.
- Consignes permanentes : `CLAUDE.md`. Une étape se lance par `/deroule-etape <lettre>` ; elle s'arrête d'elle-même en
  fin d'étape, et rien n'est fusionné dans `main` sans accord.
- Garde-fous, testés (`.claude/hooks/tests`, `outils/garde/tests`) : les permissions, les crochets (`.claude/hooks/`)
  et le bac à sable refusent toute lecture des emplacements de données réelles (`.claude/hooks/chemins_interdits.txt`),
  toute écriture d'une forme réelle, le contournement du crochet git et mutmut hors d'une copie jetable ; le crochet git
  (`.githooks/pre-commit`) refuse d'enregistrer une forme réelle. Un crochet qui tombe en panne bloque au lieu de
  laisser passer.
- Données réelles : jamais dans une séance. Le skill `essai-donnees-reelles` prépare la commande que Lounès lance dans
  son terminal ; il ne rapporte que des comptages.
- Skills et plugins : registre dans `docs/skills.md` ; rien ne s'installe sans le contrôle du skill `controle-skill`
  (`outils/controle_skill.py`, grille de sécurité, version figée, `PROVENANCE.md`).
- Sous-agents de fin d'étape : `relecteur`, `gardien-donnees`, `verificateur-spec`, `testeur-mutation`
  (`.claude/agents/`).

## Contenu

| Dossier | Rôle |
| --- | --- |
| `pipeline/` | scripts du kit, inchangés (règles R01 à R11, chaînes, rapport) ; leur notice : `pipeline/LISEZMOI-kit.md` |
| `api/` | interface de programmation (étape 3) |
| `front/` | pages de l'analyste (étape 4) |
| `deploiement/` | conteneurs, serveur frontal, notice d'hébergement (étape 5) |
| `jeu_essai/` | données fictives et script de construction |
