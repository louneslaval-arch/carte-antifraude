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
| 3 | interface de programmation en lecture | à faire |
| 4 | pages branchées sur l'interface | à faire |
| 5 | déploiement | à faire |
| 6 | proximité, décisions, jeton Tandem | à faire |
| 7 | pseudonymisation du stockage | à faire |

## Règle de base

**Aucune donnée réelle dans ce dépôt ni sur un poste de développement.** Le développement et les tests se font
uniquement sur `jeu_essai/donnees/` (entièrement fictif). Le `.gitignore` refuse les bases, classeurs, CSV,
JSON, pages générées et fichiers de secrets.

## Publication

`pipeline/publier_carte.py --base … --chaines chaines.json --sortie publication/<date>` écrit trois fichiers :

| Fichier | Contenu |
| --- | --- |
| `geometrie.json` | couche 1 : pour chaque nœud (indice opaque) son type, l'indicateur liste noire, son réseau, son degré, sa ville ; les arêtes (style, force) ; pour chaque inscrit la structure de sa carte (nœuds, arêtes avec le libellé du rôle, chaînes réduites à distance, fiabilité, force, liste noire oui ou non) |
| `identites.sqlite` | couche 2 : `noeud` (indice → identifiant interne), `identite` (nom, CIN, RC, tribunal, ville, listes, motifs), `lien`, `annonce`, `chaine` (chaîne complète au format de la carte actuelle), `recherche` (nom, CIN, RC) |
| `manifeste.json` | date, nombre de nœuds et d'inscrits, `fictif` (vrai seulement si tous les CIN commencent par « ZZ »), empreintes SHA-256 |

Les indices sont tirés au hasard à chaque publication : ils ne révèlent ni l'ordre alphabétique ni le RC.
Un libellé de rôle hors du vocabulaire du kit ne passe pas en couche 1. Tests : `python3 -m pytest pipeline/tests`.

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

| Taille | Sociétés | Annonces | Inscriptions | Base + chaînes |
| --- | ---: | ---: | ---: | ---: |
| petit | 424 | 666 | 68 | 1 s |
| moyen | 8 273 | 12 750 | 354 | 11 s |
| grand | 61 041 | 96 563 | 2 714 | 95 s |

## Décisions prises

- **Deux quotas distincts** (remplace « 2 000 identités par heure ») : les **étiquettes** (nom seul, au zoom) sont
  comptées en indices *nouveaux* par session, le cache du navigateur n'étant pas recompté, avec un plafond large ;
  les **fiches complètes** (CIN, RC, motifs, annonces) restent limitées à 2 000 par heure et par analyste.
  Sans cela, 5 déplacements de zoom à 400 étiquettes épuisaient le quota de l'heure.
- **Couche 1** : envoyée telle quelle à tous les rôles, indicateur liste noire compris (choix assumé).

## Contenu

| Dossier | Rôle |
| --- | --- |
| `pipeline/` | scripts du kit, inchangés (règles R01 à R11, chaînes, rapport) ; leur notice : `pipeline/LISEZMOI-kit.md` |
| `api/` | interface de programmation (étape 3) |
| `front/` | pages de l'analyste (étape 4) |
| `deploiement/` | conteneurs, serveur frontal, notice d'hébergement (étape 5) |
| `jeu_essai/` | données fictives et script de construction |
