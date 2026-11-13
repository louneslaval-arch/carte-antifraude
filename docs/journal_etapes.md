# Journal des étapes

Une entrée par étape ou par reprise, la plus récente en bas. Le rappel de début de séance affiche la fin de ce fichier.

## 11/11/2026 — préparation

- Document de lancement déposé à la racine (`LANCEMENT_construction_temps_reel.md`).
- État du dépôt : section 2 du document de lancement (mutation de `graphe.py` à annuler, kit du 22/10, structure de
  Kamal absente, rôle AGENCE à trancher).
- Prochaine action : étape 1, point 1.1.

## 11/11/2026 — étape 1, points 1.1 et 1.2 (branche `etape-1-outillage`)

- **Cadre d'exécution** : Claude Code tourne dans l'onglet Code de l'app Claude, pas dans le CLI (`claude` absent du
  PATH). `claude --version` et `claude plugin list` non relevés ; `/hooks`, `/permissions`, `/plugin`, `/skill-doctor`,
  `/doctor`, `/context` ne sont pas disponibles ici. Choix de Lounès : continuer dans l'app et adapter.
- **Inventaire** : `main` seule en `be678ba` ; Python 3.13.5 ; git, node, npm présents ; brew, pyright, semgrep, ruff
  absents ; aucun skill livré avec les paquets du `.venv`.
- **Mutation** : le diff de `api/app/graphe.py` était la seule sentinelle de `_empreinte` ; annulée avec l'accord de
  Lounès (`git checkout -- api/app/graphe.py`).
- **Tests avant** : 263 réussis, 2 sautés. **Après 1.2** : 343 réussis, 2 sautés (+53 garde, +27 crochets).
- **Emplacements de données réelles** donnés par Lounès : `~/Downloads`, en plus de `~/antifraude-donnees/` et
  `~/Documents/antifraude-eqdom/` ; ajouté à `chemins_interdits.txt`, `permissions.deny` et `sandbox.filesystem.denyRead`.
- **Cadre posé** : bloc G.2 dans `.gitignore` ; `outils/extraire_lancement.py` (25 fichiers extraits, puis les
  réglages) ; `outils/garde/` (motifs, ligne de commande, tests) ; crochet git actif (`core.hooksPath .githooks`, essai :
  un CIN de forme réelle indexé fait échouer l'enregistrement) ; crochets de Claude Code (`.claude/hooks/`, tests).
- **Écarts aux réglages de l'annexe G.1**, validés par Lounès : `mcp__*` retiré de `deny` (les outils de l'app, dont la
  liste des tâches, sont des outils MCP ; la règle 4 de `CLAUDE.md` reste) ; `github.com` ajouté aux domaines du bac à
  sable (clones du point 1.4 ; `git clone` reste en « ask ») ; `Read(!**/.env.exemple)` retiré (négation non reconnue).
- **Choix d'interprétation** : « dossier `api/` du lot de Kamal » = un dossier `api/` sous `import/`, `reference/v2/` ou
  un dossier `kamal_structure` (notre `api/` reste lisible) ; `mutmut run` est refusé partout dans le dépôt principal,
  sauf sous `.claude/worktrees/`.
- **Marque `fictif-volontaire`** ajoutée sur 4 lignes existantes : `api/tests/conftest.py:43`,
  `pipeline/tests/test_publier_carte.py:145` et `:312` (CIN de forme réelle voulu, refus d'une publication non
  fictive) ; `jeu_essai/generer.py:312` (CIN masqué fictif, pris pour une trace de mutation).
- **Constats en attente pour l'étape A** (non corrigés) : `pipeline/LISEZMOI-kit.md` lignes 45, 47, 77, 136 (écriture
  arabe) et 127, 128 (forme de CIN) ; `jeu_essai/donnees/liste_noire_fictive.csv` lignes 4 et 5 (numéros de registre
  fictifs en « RC999… » pris pour une forme de CIN : ajuster la garde ou le jeu d'essai, à décider).
- **Prochaine action** : arrêt 1 ; nouvelle séance de Claude Code dans ce dossier, puis « Reprends l'étape 1 au point 1.3 ».

## 11/11/2026 — étape 1, point 1.3 (interrompu)

- Séance ouverte sur `~` au lieu de `~/carte-antifraude` : les réglages du projet (crochets, `permissions.deny`, bac à
  sable) n'étaient pas chargés ; aucun rappel de début de séance.
- Essai 1 (lecture du témoin) et essai 2 (`cat` du témoin) **non refusés** : réponse « fichier inexistant ». Le témoin
  `~/antifraude-donnees/essai_garde.txt` semble absent (préalable 0.1, point 3).
- Crochets appelés à la main avec une entrée simulée : `garde_commande.py` et `garde_fichier.py` refusent (code 2). Ils
  sont justes ; c'est leur chargement qui manquait.
- Essais 3 à 8 non joués (sans barrière, les essais 4 et 5 auraient eu un effet réel).
- **Prochaine action** : créer le témoin, ouvrir une séance sur le dossier `~/carte-antifraude`, puis « Reprends l'étape 1
  au point 1.3 » ; rejouer les huit essais.

## 11/11/2026 — étape 1, point 1.3 (reprise dans la même séance, dossier `~/carte-antifraude`)

| N° | Essai | Résultat |
| ---: | --- | --- |
| 1 | lecture du témoin (outil Read) | refusé par `permissions.deny` |
| 2 | `cat` du témoin | refusé par le classifieur du mode auto (crochet non prouvé) |
| 3 | script Python, chemin par concaténation | refusé par le classifieur du mode auto (bac à sable non prouvé par l'essai ; `denyRead` présent dans la configuration du bac à sable chargée) |
| 4 | Write d'un CIN de forme réelle | **NON REFUSÉ** : fichier créé, supprimé aussitôt |
| 5 à 7 | `--no-verify`, `git add -f`, `mutmut run` | non joués (barrière des crochets défaillante) |
| 8 | tests de la garde et des crochets | accepté sans demande, 80 réussis |

- **Cause probable de l'essai 4** : les commandes des crochets s'appuient sur `$CLAUDE_PROJECT_DIR`, vide dans cette
  séance de l'app ; le chemin devient `/.claude/hooks/…`, Python échoue avec un code non bloquant et l'action passe
  (crochets « ouverts en cas d'échec »). Appelé à la main, `garde_fichier.py` refuse bien (code 2).
- **Correction proposée** (réglages, accord explicite de Lounès requis, règle 7) : chemin absolu du dépôt dans les
  commandes des crochets PreToolUse, et échec fermé (`|| exit 2`).
- **Prochaine action** : accord sur la correction, puis rejouer les huit essais.

## 11/11/2026 — étape 1, point 1.3 (après correction des crochets)

- **Correction des réglages**, faite sur demande explicite de Lounès : les cinq commandes de crochets font un `cd` vers
  le chemin absolu du dépôt, fixent `CLAUDE_PROJECT_DIR`, puis lancent `.venv/bin/python .claude/hooks/<script>.py` ; les
  deux crochets PreToolUse finissent par `|| exit 2` (une panne du crochet bloque). Vérifié hors de l'app : forme réelle
  → 2, fictif → 0, crochet introuvable → 2.

| N° | Essai | Résultat |
| ---: | --- | --- |
| 1 | lecture du témoin (Read) | refusé par `permissions.deny` |
| 2 | `cat` du témoin | refusé par le crochet `garde_commande.py` |
| 3 | lecture par script, chemin concaténé | refusé par le classifieur du mode auto ; **refus du bac à sable non prouvé** (deux essais sans lecture de données, sur des chemins inexistants : réponse « introuvable », sans conclusion) |
| 4 | Write d'un CIN de forme réelle | refusé par le crochet `garde_fichier.py` ; aucun fichier créé |
| 5 | `git commit --allow-empty --no-verify` | refusé par le crochet |
| 6 | `git add -f essai.xlsx` | refusé par le crochet ; fichier jamais créé |
| 7 | `.venv/bin/mutmut run` | refusé par le crochet |
| 8 | tests de la garde et des crochets | accepté sans demande ; suite complète : 343 réussis, 2 sautés |

- Un `cat >>` du journal qui citait le dossier des données a été refusé par le crochet : la garde tient aussi sur les
  commandes d'écriture.
- **Reste ouvert** : preuve de la barrière du système (essai 3). La configuration chargée du bac à sable interdit la
  lecture des trois emplacements de données réelles ; il reste à vérifier que le fichier témoin existe bien.

## 11/11/2026 — étape 1, points 1.4 à 1.6

- **1.4** : `claude-code-setup` non lancé (`/plugin` absent de l'app). Sources récupérées dans `.verif/` par archives
  figées (le bac à sable interdit à git d'écrire `.git/config`, donc aucun clone ; il a aussi refusé d'extraire les
  `.mcp.json` et `.zshrc` des archives) : claude-plugins-official `43fd1f9`, anthropics/skills `2c5958e`,
  trailofbits/skills `e4dd0bb`, obra/superpowers `bb92a77` (figé par la place de marché officielle). Aucun skill livré
  avec les paquets du `.venv`. Recherche web : seuls playwright-cli (Microsoft, étape K) et le skill du paquet FastAPI
  (SSE natif à partir de 0.135 seulement) sont crédibles ; rien pour Prisma depuis Python, SQLite, performance.
- **1.5** : `outils/controle_skill.py` et 75 tests ; 16 candidats contrôlés (grilles H.1 dans `.verif/rapports/`, lues
  par quatre sous-agents). Arrêt 2 : Lounès retient verification-before-completion, test-driven-development,
  pyright-lsp et skill-creator maintenant ; property-based-testing (B), semgrep-rule-creator (B) et sharp-edges (J)
  pour plus tard. Registre : `docs/skills.md`.
- **1.6** : skill-creator copié comme skill (il n'a ni crochet ni serveur). Copies exactes préparées dans
  `.verif/a_copier/` (le bac à sable interdit l'écriture dans `.claude/skills/`) ; Lounès lance la copie.
  pyright-lsp en attente : il faut ajouter la place de marché et `enabledPlugins` dans `.claude/settings.json`
  (accord explicite, règle 7) et installer `pyright`.
- **pyright-lsp**, sur accord explicite de Lounès : place de marché `claude-plugins-official` (source GitHub) et
  `enabledPlugins` ajoutés à `.claude/settings.json`. `pyright` figé à 1.1.414 (10/09/2026), installé par Lounès avec
  npm ; le paquet de PyPI est écarté parce qu'il télécharge Node à son premier lancement.

## 11/11/2026 — étape 1, points 1.7 à 1.9

- **Consigne de Lounès** (même jour) : « tu peux tout faire, arrête de me demander ». Les choix qui auraient attendu sa
  réponse sont tranchés au plus prudent et inscrits dans `docs/questions_ouvertes.md` (n°20 à 23).
- **Copie des skills** (1.6) : lancée par Lounès ; `diff -r` contre la source : seuls `PROVENANCE.md` et `LICENSE`
  diffèrent. Deux pages `.html` de skill-creator étaient ignorées par `*.html` : exception
  `!.claude/skills/**/*.html` ajoutée, pages versionnées. `pyright` : l'installation par npm n'a rien laissé dans
  `/usr/local` (dossier `~/.npm` appartenant à root, d'après npm) ; le plugin reste inactif tant que
  `pyright-langserver` n'est pas dans le PATH.
- **1.7** : `controle-skill`, `jeu-essai-v2`, `essai-donnees-reelles` rédigés avec skill-creator (sans ses scripts
  d'évaluation), 100, 85 et 89 lignes. Essai de déclenchement à la main (15 demandes, 3 qui doivent déclencher et 2 qui
  ne doivent pas, par skill) : 13 justes ; 2 écarts sur `jeu-essai-v2`, dont la description est imposée par H.2
  (question n°21). Usage réel : `controle-skill` sur test-driven-development (admis avec réserves) ;
  `essai-donnees-reelles` sur l'étape A (arrêt correct : aucun script n'a de sortie limitée aux comptages, trois des
  quatre chiffres de référence ne sont produits par aucun script présent) ; `jeu-essai-v2` sur S04 (arrêt correct :
  structure de Kamal absente ; contradiction S04 / S12 relevée, question n°20). Chaque skill corrigé d'après ces essais.
  Commandes d'état de `deroule-etape` exécutées ; sa présence dans le menu `/` reste à voir par Lounès.
- **1.8** : `relecteur` : forme courte `-n` de l'option qui saute le crochet git, `core.hookspath` en minuscules et
  `git -C . add -f` passaient le crochet ; garde aveugle aux fichiers indexés d'un dossier ignoré et aux textes UTF-16 ;
  crochet de fin de tour muet en cas d'erreur ; tout corrigé, tests d'abord (rouges puis verts). Aussi : chemins de
  données comparés sans la casse (le disque du Mac ne la distingue pas) ; bloc Tags d'Unicode ajouté au contrôle des
  skills. Non corrigé : tests et code dans un même enregistrement en 1.2 (historique déjà écrit). `verificateur-spec` :
  1.1, 1.2, 1.4, 1.5 faits ; manques repris ici. `gardien-donnees` : retrouve les constats connus de la notice du kit et
  du jeu d'essai ; constats hors étape notés (question n°23). `testeur-mutation` : bloqué par le bac à sable (pas de
  pseudo-terminal pour mutmut), sans contournement ; état du dépôt identique avant et après (question n°22).
- **1.9, essais de 1.3 rejoués** : 1, 2, 4, 5 (et sa forme `-n`), 6, 7 refusés ; 3 prouvé par équivalence (ouvrir un
  fichier existant du dossier personnel, sans le lire : erreur d'accès du système, le crochet ne voyant aucun chemin
  interdit) ; 8 accepté.
- **Tests** : 439 réussis, 2 sautés (début d'étape : 263 réussis, 2 sautés).
- **Coût en contexte** : avant, 0 caractère de description de skill du projet ; après, 1 499 caractères (environ
  375 jetons) par séance, `deroule-etape` non compté (lancé par Lounès seulement).

## 12/11/2026 — fusion de l'étape 1

- Premier essai de fusion (`git switch main`) : le bac à sable a laissé git retirer `outils/garde/` mais pas
  `.claude/` ; les crochets, fermés en cas d'échec, ont tout bloqué, et le crochet de fin de tour bouclait (il lisait
  `stop_hook_active` après l'importation de la garde). Lounès a remis la branche (`git reset --hard`).
- Défaut corrigé, test d'abord : `stop_hook_active` lu avant toute importation.
- Fusion par un commit à deux parents créé sans toucher aux fichiers (`git commit-tree`, puis `update-ref`) :
  équivalent de `git merge --no-ff`, `main` n'ayant rien en propre.
- Sur `main` : 440 réussis, 2 sautés ; garde `--tout` : les 8 constats connus, réservés à l'étape A.
- **Prochaine action** : étape A, quand Lounès aura déposé les fichiers dans `import/` (préalables du plan).

## 12/11/2026 — étape A, début (branche `etape-a-remise-a-niveau`)

- **Préalables manquants** : `import/` n'existe pas (structure de Kamal, kit du 11/11, référentiels du 21/10) ; pas
  de réponse de Kamal (question n°15). Les points A.3 à A.6 et A.8 en dépendent.
- **A.1** : `api/app/graphe.py` sans mutation ; 440 réussis, 2 sautés.
- **A.2, jeu d'essai** : lignes 4 et 5 de `jeu_essai/donnees/liste_noire_fictive.csv` (numéros de registre fictifs
  « RC999… », de la forme d'un CIN) marquées `fictif-volontaire` dans la note, sans toucher à la garde ; la note
  n'entre dans aucun résultat attendu ; tests inchangés.
- **A.2, notice du kit** : constats laissés en place ; `pipeline/LISEZMOI-kit.md` sera remplacée par la notice du kit
  du 11/11 en A.4, et ses constats seront tranchés sur la nouvelle version (exemples de CIN → « ZZ… » ; mots arabes :
  exemples de translittération sans identifiant associé, à confirmer par Lounès, question n°13).
- **A.7** : `requirements-dev.txt` aux versions figées (pytest 9.2.0, coverage 7.17.2, mutmut 2.5.1, ruff 0.17.4,
  mypy 2.4.1, hypothesis 6.170.15) ; installés seulement pytest, coverage et mutmut ; les autres à l'étape B.
- **A.8** : non préparé ; trois des quatre chiffres de référence viennent de `carte_globale.py` (kit du 11/11), et
  aucun script n'a encore de sortie limitée aux comptages.
- **Prochaine action** : dès que `import/` est déposé, A.2 (contrôle de l'import), A.3, A.4, A.5, A.6, puis A.8.

## 13/11/2026 — étape A, import (partielle)

- **Structure de Kamal** : extraite par Lounès de `antifraude_json_back_front_2026-11-11.zip` (seulement `types/`,
  `schema/`, `reference/`, `README.md` ; aucun `api/`) dans `import/kamal_structure/` : 9 fichiers. Garde : 4 fichiers
  refusés par extension (JSON et CSV, attendu) ; 3 constats « reference_dossier » : de vraies références de dossiers de
  la préproduction dans `README.md` (lignes 3 et 75), `reference/CONTRAT_TANDEM_AI.md` (ligne 92) et les exemples de
  `schema/openapi_api_v1_export_metier.json` (lignes 37 et 58). Ne jamais les réutiliser ; à remplacer par des
  références « ZZ » si la structure est un jour versionnée. `champs_par_type_prod.csv` : inventaire des clés avec
  comptages, sans valeur ; 13 types de pièces (le plan en annonce 14 : à vérifier à l'étape C).
- **A.3** : sans réponse de Kamal (question n°15), la structure reste dans `import/` (ignoré) ; seule la carte de
  correspondance de l'étape B sera versionnée.
- **A.4** : le kit fourni (`kit_base_liste_noire_RC.zip`) est l'ancien : ses 4 fichiers sont identiques à ceux de
  `pipeline/`. Le kit du 11/11 (`carte_globale.py`, `translitteration.py`, `geo_maroc.py`…) reste à fournir.
- **A.5** : référentiels non encore localisés (prototype du 21/10).
- **Étape A fusionnée partielle** (consigne du 13/11) ; restent A.4, A.5, A.6, A.8 et la notice du kit.

## 13/11/2026 — étape B, socle des couches (branche `etape-b-socle`, fusionnée partielle)

- **Fait** : arborescence (`pipeline/normalisation`, `couches`, `regles`, `flux/`, `schema/`, `tests/`, `jeu_essai/v2/`,
  `outils/v2/`) ; `schema/000_schema_version.sql` et `pipeline/migrer.py` (idempotent, tout ou rien, migration
  modifiée après coup refusée) ; `construire.py` (`--jeu-essai`, `--base`, `--depuis`, `--jusqua`, `--dossier`) ;
  `verifier.py` et `invariants.yaml` (zéro ligne, comptage avec tolérance ou minimum, arrêt au premier écart,
  comptages seulement) ; `outils/v2/lire_prisma.py`, `lire_types_ts.py`, `carte_correspondance.py` ;
  `docs/correspondance_v2.md` générée (13 modèles, 175 champs, 13 énumérations de schema.prisma ; 20 interfaces) avec
  test de dérive ; `pytest.ini` (un seul `pytest` lance tout) ; `outils/verifier_tout.sh`.
- **Tests** : 492 réussis, 2 sautés (avant : 440). Tests et code dans les mêmes enregistrements : l'ordre « tests
  d'abord » a été suivi (chaque test vu rouge) mais n'est pas lisible dans l'historique.
- **Relectures** : `gardien-donnees` sans constat bloquant (aucune référence réelle de Kamal dans les fichiers
  suivis) ; corrigé : sortie d'erreur de `construire.py` réduite au type, `--depuis` après `--jusqua` refusé,
  comptage vide ou nul traité comme un écart, invariant « zéro » compté en SQL, carte vérifiée aussi depuis
  `reference/v2/` et contrôle de carte obligatoire dans `verifier_tout.sh`.
- **Non fait** : B.5 `comparer_bases.py` (kit du 11/11 absent) ; tests par propriétés (pas encore de fonction de
  normalisation reprise du kit ; hypothesis non installé) ; `testeur-mutation` (bac à sable, question n°22).
- **Choix provisoires** : `invariants.yaml` en forme JSON du YAML (aucune dépendance) ; `migrer.py` propre à SQLite,
  à rendre portable à l'étape L.
- **Hors périmètre, fait** : notice du kit (A.2) : exemples de CIN remplacés par « ZZ », mots en écriture arabe par
  « [arabe] » (choix prudent de la question n°13, réversible).
- **Bloqué de mon côté** : pip ne démarre pas dans le bac à sable (accès aux certificats du système refusé) ;
  `verifier_tout.sh` reste rouge à l'étape ruff tant que Lounès n'a pas lancé
  `.venv/bin/python -m pip install -r requirements-dev.txt`.

## 13/11/2026 — étape A, import du kit du 11/11 (branche `etape-a-import-kit`)

- **Kit du 11/11** trouvé : `kit_base_liste_noire_RC_2.zip` (fichiers datés du 11/11). Extrait par Lounès sans
  `jeu_essai/`, sans `modele_export_kamal/`, sans base, classeur, CSV ni JSON. 15 fichiers, copiés dans `pipeline/`
  (empreintes d'origine ci-dessous). `rapport_croisement.py`, `regles_bl_rc.sql`, `schema_bl_rc.sql` inchangés.
- **Contrôle (A.2)** : écriture arabe attendue dans `construire_base.py`, `chaines_dessin.py`, `translitteration.py`
  (déjà autorisés). Modifications de **commentaires seulement** dans `charger_antifraude.py` : marque
  `fictif-volontaire` sur les lignes 59 et 181 (valeurs gabarits), raison sociale d'exemple (ligne 484) remplacée par
  une description. Notice : mots arabes → « [arabe] », CIN d'exemple → « ZZ », valeur gabarit marquée.
  **En attente de Lounès** : `pipeline/carte_globale_modele.html:96` et `pipeline/carte_chaines_modele.html:135`
  (lettres arabes d'aide à la lecture et un nom très courant en exemple) : l'ajout de ces deux fichiers à
  `outils/garde/arabe_autorise.txt` a été refusé par la protection de l'app (affaiblissement d'une garde) ; à faire
  par Lounès s'il l'approuve.
- **Deux incompatibilités de `publier_carte.py` avec le kit, corrigées (tests d'abord)** :
  1. styles d'arête composés du kit (`certain`, `ancien`, `ancien rap`…) rangés en silence dans le style simple :
     liste `STYLES` étendue (numéros existants inchangés), style inconnu désormais refusé ;
  2. rôles datés (« gérant (06/2025) », « ancien associé (cédé 02/2025) », rôles multiples) : la couche 1 les
     perdait tous ; elle garde maintenant le rôle et la part, **jamais la date** (une date d'annonce désignerait la
     société via le registre public) ; la date reste en couche 2.
- **`attendu_kit.json` régénéré**, chaque écart expliqué par la notice du kit :
  libellés datés en couche 2 (rôles datés) ; « cessionnaire » → « associé », « cédant » → « ancien associé »
  (`ROLES_FR`) ; E:6–S:4 et E:9–S:4 `rap` → `certain` (rapprochement certain distingué) ; E:9–S:1 et I:2–S:1 →
  `ancien…`, force 0,25 → 0,15 (rôle terminé, poids 0,3 à 0,5) ; passage I:3 → S:3 par un nom courant refusé (nom rare
  ou indice exigé) : nouvelle personne I:7, 14 réseaux au lieu de 13, 18 nœuds au lieu de 17, une identité et une
  entrée de recherche de plus.
- **Dépendance nouvelle (provisoire)** : `networkx==3.7` pour `carte_globale.py` (`requirements.txt`) ; à installer
  par Lounès. **Fichier manquant** : `maroc_regions.json` (contour Natural Earth lu par `geo_maroc.py`).
- **Référentiels** (A.5) : `referentiel_villes.json` (données géographiques GeoNames, sans personne) et
  `grands_employeurs.txt` (106 expressions de raisons sociales) restent dans `import/reference/` : un JSON se
  versionne seulement après ajout à `outils/garde/fichiers_autorises.txt` (décision de Lounès). Aucun script ne les
  lit encore (étapes G et H).
- **Tests** : 513 réussis, 2 sautés.
| Fichier du kit | sha256 d'origine | Destination |
| --- | --- | --- |
| `LISEZMOI.md` | `d7ed9f29417e1fd7cb6bce3a74821fda9d88761986bada2ac669b2a73bf053ee` | `pipeline/LISEZMOI-kit.md` |
| `carte_chaines_modele.html` | `9f4c27b82eaee855a5a738541c3a0013e58775ffb2e82cb171a7d4004762be36` | `pipeline/carte_chaines_modele.html` |
| `carte_globale.py` | `b3918af8349167287e7a3f2f8d60b8041e8a09d8b5155bebc8d1353ab93d4340` | `pipeline/carte_globale.py` |
| `carte_globale_modele.html` | `0980f6fbd7c863319d22395dc673f7b8ec8a07124b29a0c91ea8a8525572bd93` | `pipeline/carte_globale_modele.html` |
| `chaines_dessin.py` | `fe79255405d6c3fc0dbb7e316bacae220425b14737d9feb03604e04225097696` | `pipeline/chaines_dessin.py` |
| `charger_antifraude.py` | `6fdac8811cf3f558eb8d22136c1f9e2534ceb8b56f829281b6ed62d02ecb2753` | `pipeline/charger_antifraude.py` |
| `comparer_bases.py` | `e3bfb167bac299d2d2a79c7e6905b3ed74ae1b27cda856552dc0e4ab32a6f80a` | `pipeline/comparer_bases.py` |
| `construire_base.py` | `bb2aad88dcef7cb54b5252cb68876abb96bbb51639131e83e98bb84116dc6395` | `pipeline/construire_base.py` |
| `geo_maroc.py` | `ed5513629373a14b6c6e5264ed6ef10264bdf00fcfc7ccbb5f1d15fd953be61c` | `pipeline/geo_maroc.py` |
| `nettoyer_liste_noire.py` | `2dfac356623aae92b59d351629fb518e3fc7a434c375e2ff41806fcf98eeb29e` | `pipeline/nettoyer_liste_noire.py` |
| `rapport_antifraude.py` | `504e84eadf689023963fbd47c0a697c173b3c3ed6e123ccc036ebe995d282d0c` | `pipeline/rapport_antifraude.py` |
| `rapport_croisement.py` | `f2fddcfa7aa294bfe8905d0f1984c24ebb44ce0ff80f502db84425f475173111` | `pipeline/rapport_croisement.py` |
| `regles_bl_rc.sql` | `dc831f638deb1ed9ba2ca8cb84d80ba9f426aaf487f8f212427c080c27c8219a` | `pipeline/regles_bl_rc.sql` |
| `schema_bl_rc.sql` | `959fe036b74f7fa7011e59b86f15a024acd21c77838eed0e6560bf765957ffd2` | `pipeline/schema_bl_rc.sql` |
| `translitteration.py` | `c979bdb04467a5ad8678d8c6c13a8a4548075fb90c8ac9abac76efeedab248a6` | `pipeline/translitteration.py` |

## 13/11/2026 — étape A, carte globale et commande de référence

- `networkx` installé par Lounès ; `pipeline/maroc_regions.json` présent (contour Natural Earth, ignoré par git
  comme tout JSON : à réautoriser dans `outils/garde/fichiers_autorises.txt` si on veut le versionner).
- `jeu_essai/construire.sh` : la carte globale du jeu d'essai va dans le dossier de sortie (sans `--html`,
  `carte_globale.py` écrivait à la racine du dépôt, sous le nom de la vraie carte).
- Jeu d'essai du kit : 18 nœuds, 3 réseaux, plus grand 13 nœuds ; bilans de `construire_base.py`,
  `chaines_dessin.py` et `carte_globale.py` vérifiés sans aucune valeur du jeu d'essai (comptages seulement).
- `outils/comptages_a.py` (5 tests) : réseaux et plus grand réseau touchant la liste noire, depuis `globale.json`.
- **A.8** : commande de référence préparée (skill `essai-donnees-reelles`), à lancer par Lounès. Les scripts du kit
  ne lisent pas `CARTE_DONNEES_REELLES` : variable retirée de la commande ; à noter pour l'étape où ces scripts
  passent dans les couches (un script qui tourne sur du réel sans ce garde-fou est à corriger).
- **Premier essai réel (13/11, Lounès)** : étapes 1 (nettoyage) et 2 (construction) faites ; étape 3 en échec
  (`AttributeError`). Cause, reproduite sur la base fictive : l'archive de l'export contient son propre dossier,
  `1_donnees_prod` était un niveau plus bas, aucun lot n'a été chargé, et `charger_antifraude.py` du kit plante quand
  aucun lot n'est trouvé (défaut du kit, noté, non corrigé : le kit s'importe sans modification). `essai_reel_a.sh`
  cherche désormais les sous-dossiers un niveau plus bas.
