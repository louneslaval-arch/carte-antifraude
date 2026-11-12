# Registre des skills et plugins

Tout skill ou plugin actif dans ce dépôt figure ici, avec sa source exacte et son contrôle (skill `controle-skill`).
Pas d'installation sans ligne dans ce tableau ; pas de mise à jour sans nouveau contrôle.

| Nom | Nature | Source et version | Licence | Contrôle (date, résultat) | Sert à (étapes) | Coût en contexte | État |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deroule-etape | skill du projet | ce dépôt | — | — | toutes | — (lancé par Lounès seulement) | actif |
| controle-skill | skill du projet | ce dépôt, appuyé sur `outils/controle_skill.py` | — | 11/11/2026 : essai réel sur test-driven-development (admis avec réserves) | toute installation ou mise à jour | 252 caractères | actif |
| jeu-essai-v2 | skill du projet | ce dépôt | — | 11/11/2026 : essai réel sur S04, arrêt correct faute de structure de Kamal | B à K | 348 caractères ; chargé seulement dans `jeu_essai/`, les tests, `flux/`, `pipeline/couches/` | actif |
| essai-donnees-reelles | skill du projet | ce dépôt | — | 11/11/2026 : essai réel sur l'étape A, arrêt correct (aucune sortie limitée aux comptages) | A, E, puis au besoin | 276 caractères | actif |
| skill-creator | skill tiers copié | anthropics/claude-plugins-official, `plugins/skill-creator/skills/skill-creator`, `43fd1f9` | Apache 2.0 | 11/11/2026, à lire de près → retenu avec consignes d'usage | 1 (skills du projet), puis au besoin | 319 caractères | actif dès la copie |
| test-driven-development | skill tiers copié | obra/superpowers, `skills/test-driven-development`, `bb92a77` | MIT | 11/11/2026, rien à signaler | toutes | 79 caractères | actif dès la copie |
| verification-before-completion | skill tiers copié | obra/superpowers, `skills/verification-before-completion`, `bb92a77` | MIT | 11/11/2026, rien à signaler | toutes | 225 caractères | actif dès la copie |
| pyright-lsp | plugin officiel | anthropics/claude-plugins-official, `plugins/pyright-lsp`, `43fd1f9` | Apache 2.0 | 11/11/2026, rien à signaler (lance seulement `pyright-langserver --stdio` ; ni crochet ni serveur MCP) | toutes | 0 | actif ; `pyright` 1.1.414 installé le 12/11/2026 (`sudo npm install -g --ignore-scripts`) |
| property-based-testing | skill tiers à copier | trailofbits/skills, `plugins/property-based-testing/skills/property-based-testing`, `e4dd0bb` | CC BY-SA 4.0 | 11/11/2026, à lire de près → retenu | B, E, F, H, I | à mesurer | prévu à l'étape B (après accord sur hypothesis) |
| semgrep-rule-creator | skill tiers à copier | trailofbits/skills, `plugins/semgrep-rule-creator/skills/semgrep-rule-creator`, `e4dd0bb` | CC BY-SA 4.0 | 11/11/2026, à lire de près | B, J | à mesurer | prévu à l'étape B (Semgrep local, ligne `allowed-tools` à retirer : décision) |
| sharp-edges | skill tiers à copier | trailofbits/skills, `plugins/sharp-edges/skills/sharp-edges`, `e4dd0bb` | CC BY-SA 4.0 | 11/11/2026, refus automatique levé (Unicode invisible = exemple d'attaque) | J | à mesurer | prévu à l'étape J |

Natures : plugin officiel (place de marché `claude-plugins-official`, portée projet) ; skill tiers copié
(`.claude/skills/<nom>/` avec `PROVENANCE.md`) ; skill du projet.
États : actif ; prévu à l'étape X ; écarté (raison) ; retiré (date, raison).

## Consignes d'usage de skill-creator

1. Espace de travail des essais dans le bloc-notes de la séance, jamais dans `.claude/skills/`.
2. Pas de `run_eval.py`, `run_loop.py` ni `improve_description.py` sans accord de Lounès (écriture dans
   `.claude/commands/`, dizaines d'appels `claude -p`) ; le test de déclenchement se fait à la main. Pas de
   `generate_report.py` non plus : son rapport charge des polices Google (règle 4).
3. Visionneuse en `--static` seulement, sans ouverture automatique ; ne jamais suivre l'étape qui lit le dossier
   Téléchargements.
4. Ne pas suivre la consigne de descriptions « insistantes » ni la limite de 500 lignes : descriptions sobres,
   `SKILL.md` de moins de 200 lignes.
5. `quick_validate.py` refuse `argument-hint` et `paths` : ne pas s'y fier pour les skills du projet.

## Écartés

| Candidat | Raison |
| --- | --- |
| claude-code-setup | `/plugin` absent de l'app ; son analyse ne fait que proposer des pistes, toutes à repasser par la grille |
| security-guidance | son crochet `Stop` envoie le diff et le contenu des fichiers modifiés à l'API d'Anthropic (règle 4) ; code téléchargé non figé |
| pr-review-toolkit | commande `review-pr` avec Bash sans restriction et appel à GitHub ; agents sans liste d'outils ; recouvre `relecteur` |
| superpowers (plugin entier) | crochet `SessionStart` qui injecte sa méthode à chaque séance ; télémétrie vers un service externe ; seuls deux skills copiés |
| differential-review | `allowed-tools` pré-autorise Bash et Write sans restriction ; écrit hors du dépôt ; méthode reprenable dans `relecteur` |
| insecure-defaults | aucun dossier de skill installable (commande et workflow seulement) ; `references/` utilisables comme liste de lecture du `relecteur` (A, J, L, M) |
| supply-chain-risk-auditor | `allowed-tools` sans restriction ; scripts réseau qui lisent le jeton `gh` ; Lounès peut le lancer lui-même aux étapes A et L |
| static-analysis | trois skills et deux commandes à Bash libre ; à retenir pour B : `--metrics=off`, règles locales seulement |
| mutation-testing | recouvre `testeur-mutation` ; ses deux références (mutants équivalents, gravité) peuvent nourrir le sous-agent sur décision |
| modern-python | crochet et liens symboliques ; changerait l'outillage sans décision |
| spec-to-code-compliance | orienté contrats intelligents ; `verificateur-spec` couvre le besoin |
| ask-questions-if-underspecified | absent du dépôt de Trail of Bits au numéro `e4dd0bb` |
| playwright-cli (Microsoft) | à revoir à l'étape K (demande Node) |
| skills communautaires SQLite, performance, accessibilité, Prisma | éditeurs non reconnus ou hors sujet ; écrire nos propres skills si besoin |
