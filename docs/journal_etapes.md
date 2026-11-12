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
