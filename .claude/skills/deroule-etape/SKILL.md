---
name: deroule-etape
description: Déroulé standard d'une étape du plan de construction de la carte antifraude (A à N) — préalables, plan, branche, tests d'abord, code, vérifications, relectures, essai sur données réelles préparé pour Lounès, journal, compte rendu, arrêt.
disable-model-invocation: true
argument-hint: "[lettre de l'étape, A à N]"
---

# Déroulé de l'étape $ARGUMENTS

État au lancement :

!`git branch --show-current || true`

!`git status --short | head -20 || true`

!`tail -n 25 docs/journal_etapes.md || true`

## Les dix temps

1. **Préalables.** Lire l'étape $ARGUMENTS dans `docs/plan_construction.md` (but, préalables, à faire, tests, fini
   quand, pièges), les passages cités de `docs/architecture_temps_reel.md`, `docs/couches.md`, `docs/source_v2.md`,
   `docs/correspondance_v2.md`, `docs/decisions.md`, et les règles de `.claude/rules/` des dossiers touchés. Si un
   préalable manque (fichier à importer, question ouverte qui bloque l'étape) : le dire et s'arrêter.
2. **Plan.** Présenter le plan détaillé : fichiers créés ou modifiés, tables et migrations, fonctions publiques, tests
   (liste nominative), jeu d'essai ajouté, risques. En tête, les choix discutables : dépendance nouvelle, écart avec la
   spécification ou avec la structure de Kamal, valeur métier non décidée. Attendre l'accord. Si Lounès a activé le
   mode plan, s'en servir.
3. **Branche.** Partir de `main` à jour et propre : `git switch main`, puis `git switch -c etape-<lettre>-<sujet>`.
   Si l'arbre n'est pas propre, s'arrêter et montrer `git status`.
4. **Tests d'abord.** Écrire les tests et le jeu d'essai de l'étape ; les lancer ; ils échouent pour la raison attendue
   (pas d'erreur d'importation ni de syntaxe). Enregistrer : « <lettre> : tests de … ».
5. **Code.** Petites modifications, une unité cohérente par enregistrement ; les tests existants restent verts ; aucune
   valeur métier inventée (paramètres dans `c6_version_parametres`, marqués « provisoire ») ; noms et formats de la v2
   repris de Kamal.
6. **Vérifier.** `outils/verifier_tout.sh` (avant l'étape B : les commandes de `CLAUDE.md`) jusqu'au vert ; noter les
   nombres de tests réussis et sautés, avant et après.
7. **Relire.** Lancer en parallèle les sous-agents `relecteur`, `gardien-donnees` et `verificateur-spec` (en leur
   donnant la lettre de l'étape) sur `git diff main...HEAD` ; aux étapes B, E, F, H, I, aussi `testeur-mutation` sur
   les modules de l'étape ; et les skills de revue retenus (par exemple `differential-review`). Corriger ce qui est
   « bloquant » ou « à corriger » ; justifier ce qu'on écarte ; relancer la vérification.
8. **Données réelles.** Si « fini quand » demande un contrôle réel : skill `essai-donnees-reelles`. Préparer la commande
   et la liste des comptages, ne jamais la lancer, attendre les chiffres de Lounès, comparer à la référence, expliquer
   chaque écart.
9. **Documenter.** Entrée de `docs/journal_etapes.md` (date, étape, fait, tests, mutation, relectures, écarts,
   questions) ; état de l'étape dans `docs/plan_construction.md` ; `docs/correspondance_v2.md` si une table touche la
   v2 ; `LISEZMOI.md` si l'usage change ; `docs/skills.md` si un skill a servi ou manqué.
10. **Rendre compte et s'arrêter.** Compte rendu ci-dessous, puis arrêt. Pas de fusion sans « d'accord pour fusionner »
    de Lounès ; fusion par `git merge --no-ff`, puis vérification complète sur `main`.

## Conduite pendant l'étape

- Une étape = une couche = un module = une branche ; ne pas toucher à une autre couche.
- Un point de la spécification qui paraît faux ou contradictoire : s'arrêter et demander.
- Tests de mutation seulement par `testeur-mutation` (copie jetable).
- Toute sortie d'un script qui peut tourner sur des données réelles : comptages et identifiants techniques seulement.

## Modèle de compte rendu

```
## Étape <lettre> — compte rendu (<date>)
- Fait : …
- Remarqué hors périmètre (non fait) : …
- Tests : <n> réussis, <m> sautés (avant : …) ; mutation : <tués>/<total> sur <modules>
- Vérification complète et invariants : …
- Relectures (relecteur, gardien-donnees, verificateur-spec, autres) : points relevés et suite donnée
- Écarts avec la spécification ou avec la structure de Kamal : …
- Données réelles : commande préparée ; comptages rapportés et comparaison
- Skills : utilisés, manquants
- Questions pour Lounès : …
- Prochaine étape : <lettre> ; préalables manquants : …
```
