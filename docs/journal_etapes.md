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
