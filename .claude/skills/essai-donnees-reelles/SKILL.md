---
name: essai-donnees-reelles
description: Préparer, sans jamais la lancer, la commande que Lounès exécute lui-même sur les données réelles, hors du dépôt, et la liste des seuls comptages à rapporter ; comparer ensuite ces comptages à la référence. À utiliser quand une étape doit être vérifiée sur les données réelles.
argument-hint: "[lettre de l'étape]"
---

# Essai sur données réelles — étape $ARGUMENTS

Les données réelles (liste noire, CIN, dossiers d'EQDOM) sont des données personnelles protégées par la loi 09-08.
Elles ne doivent jamais passer par une séance de Claude Code : ni lues, ni affichées, ni recopiées dans une
conversation. Le seul pont entre elles et nous, ce sont des **comptages** que Lounès lit dans son terminal et nous
rapporte. Ce skill organise ce pont.

## Ce que tu ne fais jamais

- Lancer la commande, ou une variante, toi-même : c'est Lounès qui la tape dans son terminal, hors de Claude Code.
- Lire, lister ou ouvrir le dossier des données réelles ou un fichier qu'il contient, même « pour vérifier ».
- Demander un nom, un CIN, une référence de dossier, une ligne de fichier ou une capture d'écran : seulement des
  chiffres. Si Lounès colle par erreur une donnée qui semble réelle, ne la réutilise pas, ne la recopie nulle part, et
  dis-le-lui.
- Écrire `CARTE_DONNEES_REELLES=1` ailleurs que dans la commande destinée à Lounès (ni dans le code, ni dans un test,
  ni dans un script lancé par toi).

## 1. Vérifier que le script ne sort que des comptages

Le script lancé doit avoir une sortie limitée aux comptages (option `--agregats` ou équivalent), parce que sa sortie
s'affiche dans le terminal de Lounès et peut finir collée ici. Seuls s'y ajoutent les identifiants techniques que
`CLAUDE.md` (règle 3) admet : numéro de version, nom de table, code d'erreur, jamais une clé qui contient une identité.

- S'il a cette option : relire le code qui l'imprime (aucun nom, CIN, référence, adresse, ni valeur brute ; pas de
  trace d'exception qui afficherait une ligne de données) ; aucun chiffre calculé sur moins de 5 clients.
- S'il ne l'a pas : l'écrire d'abord dans le dépôt, tests d'abord, et la tester sur le jeu d'essai
  (`jeu_essai/construire.sh`) ; vérifier sur la sortie fictive qu'aucune valeur d'identité n'apparaît. Si le script
  vient du kit importé, ne pas le modifier : écrire à part un script de comptage (`outils/comptages_<lettre>.py`) qui
  lit ses sorties.
- Ce que le script affiche en chemin (bilans intermédiaires, barres de progression, avertissements) compte aussi :
  comptages et identifiants techniques seulement.
- « Moins de 5 clients » (`CLAUDE.md`, règle 6) : un comptage qui décrit un groupe de moins de 5 clients distincts
  (une ville, une règle, un motif) ne s'affiche pas (remplacé par « < 5 »). Un total technique sur l'ensemble du lot
  (opérations reconstituées, valeurs retenues) n'est pas visé.
- `CARTE_DONNEES_REELLES=1` est le garde-fou que le code lit pour accepter des données non fictives (aujourd'hui
  `api/app/config.py`). Le garder dans la commande seulement si le script lancé le lit ; sinon, le retirer et le
  signaler dans le compte rendu (un script qui tourne sur du réel sans ce garde-fou est à corriger).

## 2. Préparer le message

Choisir dans « fini quand » de l'étape (`docs/plan_construction.md`) les comptages qui prouvent le résultat, et pour
chacun la valeur attendue (référence ci-dessous, ou résultat du jeu d'essai si l'étape n'a pas de référence réelle).
Rédiger le message exactement sur ce modèle :

```
Essai sur données réelles — étape <lettre>
À lancer dans ton terminal, pas dans Claude Code :

  cd ~/antifraude-donnees
  CARTE_DONNEES_REELLES=1 ~/carte-antifraude/.venv/bin/python ~/carte-antifraude/<script> <arguments> --agregats > essai_<lettre>_<date>.txt

Rapporte-moi seulement ces chiffres (aucun nom, aucun CIN, aucune référence) :
1. <comptage> — attendu : <valeur>
2. …
```

- Plusieurs commandes si l'étape l'exige (construction, puis comptages), numérotées, dans l'ordre.
- Fichiers d'entrée : ne jamais lister le dossier pour trouver leur nom ; écrire `<fichier de la liste noire>` dans
  la commande et laisser Lounès compléter. `<date>` au format `AAAA-MM-JJ`.
- La sortie va dans un fichier du dossier des données réelles, pas dans le dépôt.
- Le crochet `garde_commande.py` refuse toute commande Bash qui contient le chemin des données réelles, même dans un
  texte : écrire le message avec l'outil d'écriture (fichier du dépôt ou réponse), jamais par `echo` ni `cat >`.

Puis attendre les chiffres.

## 3. Comparer à la référence

| Étape | Comptage | Référence |
| --- | --- | ---: |
| A | inscrits reliés | 122 |
| A | réseaux | 16 300 |
| A | nœuds du plus grand réseau de la liste noire | 17 |
| A | chemins de retour | 301 |
| E | valeurs de l'échantillon de c1 | 182 |
| E | valeurs retenues | 160 |
| E | opérations lues | 252 |
| E | opérations reconstituées | 2 |
| E | mentions de personnes | 9 |

- Chiffre égal : le noter dans le journal de l'étape (`docs/journal_etapes.md`) et dans le compte rendu.
- Chiffre différent : Lounès rapporte seulement le chiffre. L'explication se cherche sur le jeu d'essai, en
  reproduisant la situation qui pourrait produire l'écart, jamais en demandant à voir les données réelles. Noter
  l'écart, l'hypothèse et le test qui la vérifie ; si l'écart reste inexpliqué, le remonter à Lounès comme question.
