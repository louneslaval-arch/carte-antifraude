---
name: jeu-essai-v2
description: Conventions, pièges et scénarios de référence du jeu d'essai fictif des dossiers de l'antifraude v2, au format exact des types de Kamal (DossierDetail, identifiants fictifs ZZ et 999, chemins vers la liste noire connus d'avance, vérité attendue). À utiliser pour écrire ou modifier un test, un dossier fictif, le générateur ou le serveur v2 fictif.
paths:
  - "jeu_essai/**"
  - "tests/**"
  - "**/tests/**"
  - "flux/**"
  - "pipeline/couches/**"
---

# Jeu d'essai des dossiers v2

Le jeu d'essai remplace les données réelles partout dans le dépôt : un test qui passe sur lui doit prouver quelque
chose sur la production. Il faut donc qu'il soit **fictif sans ambiguïté** (rien ne peut être pris pour une vraie
personne) et **fidèle au format de la v2** (un dossier fictif doit casser le code exactement comme un vrai dossier le
ferait).

## 1. Fictif sans ambiguïté (`CLAUDE.md`, règle 2 ; `.claude/rules/jeu_essai.md`)

- CIN et références de dossier en « ZZ » ; RIB, ICE, n° CNSS, n° d'affiliation en « 999 » ; courriels en
  `@exemple.invalid` ; liens vers `exemple.invalid` ; noms tirés de syllabes (latin et arabe).
- Forme réelle voulue (test d'un refus) : construite par concaténation, ou ligne marquée `fictif-volontaire`.
- Noms : réutiliser le tirage de syllabes de `jeu_essai/generer.py` (méthode `_syllabe`), jamais un nom « au hasard »
  écrit à la main.
- Graine fixe ; deux générations donnent les mêmes octets ; sorties dans `jeu_essai/sortie/` (ignoré), seuls les
  `attendu_*.json` figés sont versionnés.
- La vérité attendue est produite par le générateur, jamais retouchée à la main.

## 2. Fidèle au format de la v2

- Les modèles d'échange viennent de `web_types.ts` (`DossierDetail` pour `GET /api/dossiers/:ref` ; liste au format de
  `GET /api/dossiers` : `items`, `total`, `counts`) ; les énumérations, des types de Kamal ; les clés de `fields`, de
  son inventaire de production (`champs_par_type_prod.csv`), par type de pièce et par source. Source :
  `reference/v2/` (ou `import/kamal_structure/`) et `docs/source_v2.md`.
- Ne jamais inventer une clé, une valeur d'énumération ou un type de pièce : si l'inventaire ne l'a pas, le signaler.
  Les clés « inventées » du piège T05 sont celles que la v2 produit vraiment, pas les nôtres.
- Les 14 types de pièces de la v2 sont tous représentés.
- Si la structure de Kamal manque (ni `reference/v2/` ni `import/kamal_structure/`) : ne pas écrire de dossier v2,
  même partiel. C'est un préalable manquant : le dire et s'arrêter. Un dossier « à peu près au format » ferait passer
  des tests qui casseraient sur la vraie v2.

## 3. Pièges et scénarios

Les pièges T01 à T15 (formats de dates, montants en texte, clés en double, trois vocabulaires, relecture, contexte
amont partiel, valeurs gabarits…) et les scénarios S01 à S24 (du demandeur inscrit au chemin de 4 liens, homonymies,
foyer, rafales, propagation renvoyée à la nuit…), avec le résultat attendu de chacun, sont dans
[references/pieges_scenarios.md](references/pieges_scenarios.md). Le lire avant d'écrire un dossier fictif ou un test
de couche : chaque piège doit apparaître au moins une fois dans le jeu, et chaque scénario a son test.

Les résultats attendus des scénarios suivent les paramètres **provisoires** (majeure à partir de 0,20, mineure à partir
de 0,08, affichage à partir de 0,05 ; barème de `.claude/rules/score.md`). Un test lit ces valeurs dans
`c6_version_parametres`, jamais en dur : si la cellule fraude les recalibre, les attendus se régénèrent.

## 4. `verite_v2.json`

Produit par `jeu_essai/v2/generer_dossiers.py` (étape F du plan), une entrée par dossier fictif :

- `ref` (en « ZZ ») et les numéros de scénario et de piège qu'il porte ;
- mentions attendues (personnes et sociétés citées, par pièce) ;
- identités attendues après rapprochement ;
- liens attendus (nature, extrémités, poids de départ) ;
- niveau (critique, majeure, mineure, gris « hors alerte », aucun) et force attendus, avec le chemin ;
- incohérences attendues (par exemple « double financement »).

Les noms des champs se fixent à l'étape F avec le générateur, puis ne changent plus sans migration du générateur et
des tests qui le lisent. Avant l'étape F, il n'y a ni générateur v2 ni `verite_v2.json` : un exemple de dossier ne
s'écrit pas à la main pour en tenir lieu.

Un scénario dont l'attendu contredit les règles de score (par exemple un employeur reconnu par son seul nom, que
`.claude/rules/score.md` plafonne à « mineure ») ne se corrige pas en silence : préciser dans le générateur la clé qui
fait reconnaître l'entité (ICE, RC + tribunal, CIN), et si la spécification ne la donne pas, remonter la question à
Lounès.

## 5. Ajouter un scénario

1. **Vérité d'abord** : écrire dans le générateur ce que le scénario doit produire (entrée de `verite_v2.json`), avec
   le calcul de la force à la main en commentaire (exemple : 0,7 × 0,5 × 0,7 = 0,245).
2. **Génération** : construire les dossiers, le registre et la liste noire fictifs qui rendent ce chemin possible, en
   s'appuyant sur `jeu_essai/generer.py` pour que les inscrits existent.
3. **Test** : un test par comportement, nommé en français d'après lui
   (`test_gerant_de_huit_societes_donne_une_majeure`) ; il échoue d'abord pour la bonne raison.
4. Régénérer deux fois et comparer : mêmes octets.
5. Ajouter le scénario au tableau de [references/pieges_scenarios.md](references/pieges_scenarios.md) avec le numéro
   suivant.
