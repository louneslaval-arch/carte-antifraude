# EQDOM · Plateforme clients (démonstration)

Une base client construite à partir des dossiers de l'antifraude, du registre du commerce et de la liste noire, et
un front pour la parcourir. **Toutes les données de ce dépôt sont fictives** : CIN et références en « ZZ », RIB, ICE
et numéros CNSS en « 999 », noms tirés de syllabes, adresses « RUE EXEMPLE ». Aucune donnée réelle n'entre ici ; une
garde (`outils/garde/`) le vérifie à chaque enregistrement.

## Lancer la démonstration

Prérequis : Python 3.10 ou plus récent.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt -r api/requirements.txt
api/lancer_demo.sh
```

Puis ouvrir <http://127.0.0.1:8720/>. La base fictive livrée (`jeu_essai/demo/base_demo.sqlite.gz`, 1 500 dossiers)
et la carte globale du même jeu (`jeu_essai/demo/carte_globale_demo.tar.gz`) sont dépliées au premier lancement.

| Compte | Mot de passe | Ce qu'il voit |
| --- | --- | --- |
| `analyste-demo` | `analyste-demo-2026` | tout : liste des clients, fiches complètes, dossiers |
| `direction-demo` | `direction-demo-2026` | chiffres agrégés seulement (jamais sous 5 clients) |

Ces comptes n'existent que sur la machine où la démonstration tourne (base temporaire recréée à chaque lancement).

## Ce qu'il y a à voir

- **Portail** (`/`) : la base client au centre, les modules et les usages autour.
- **Base client** (`/base.html`) : chiffres clés, répartition des produits, liste des clients filtrable (nom, type,
  produit) et triable (date de la demande, nom, revenu vérifié).
- **Fiche client** (`/fiche.html?i=…`) : identité retenue, dossiers, revenus déclarés et vérifiés sur pièce, comptes,
  véhicules, sociétés, adresses et graphies, inscription sur la liste noire, mentions au registre, liens avec la
  liste noire, et **toutes les données** : chaque valeur lue dans chaque pièce de chaque dossier.
- **Dossier** (`/dossier.html?i=…`) : en-tête au format de la v2, parties, pièces, revenus et charges, opérations du
  relevé.
- **Carte antifraude** (`/carte.html`, cellule fraude) : la carte globale, tout le registre relié avec la liste noire
  par-dessus (3 351 nœuds sur la démonstration) ; vue réseau et carte du Maroc en relief, filtres (liste noire seulement,
  rayon, départs certains, rôles terminés, sociétés reliées, force), recherche, détail au clic, isolement d'un réseau.
  La page reçoit la carte sans aucun nom : noms, fiches et recherche sont demandés au serveur au moment de les montrer
  (`pipeline/publier_globale.py`, routes `/api/carte/globale…`).
- **Vue réseau d'un client** (`/reseau.html?i=…`, cellule fraude) : depuis la fiche, « Voir son réseau sur la carte »
  ouvre la carte globale centrée sur le client quand il y figure (même CIN ou même RC), sinon son réseau à deux liens ;
  niveaux de criticité masqués pour l'instant.

Les URL ne portent que des indices opaques, tirés au hasard à chaque démarrage : jamais un nom ni un CIN.

## Comment la base est construite

Des couches qui se reconstruisent chacune depuis celle du dessous :

| Couche | Contenu | Code |
| --- | --- | --- |
| c0 | versions brutes des dossiers de la v2 et miroir de sa base (tables et colonnes à l'identique) | `pipeline/couches/c0_brut.py`, `schema/001`, `010` |
| c1 | chaque valeur de chaque pièce, normalisée, avec son origine ; relevés, mentions, identifiants | `pipeline/couches/c1_faits.py`, `pipeline/normalisation/` |
| c2 | une fiche par personne et par société (liste noire, registre, dossiers), rapprochements, décisions | `pipeline/couches/c2_identites.py` |
| c3 | fiche du dossier : en-tête, revenus, charges, comptes, opérations, véhicules, incohérences | `pipeline/couches/c3_dossier.py` |
| c5 | graphe (rôles, identifiants partagés) et chemins vers la liste noire (barème, coût de taille) | `pipeline/couches/c5_graphe.py` |

- Schéma : migrations numérotées dans `schema/` ; invariants dans `invariants.yaml`, vérifiés par `verifier.py`.
- API de lecture : `api/app/base_client.py`, `api/app/routes/base.py` (FastAPI, droits dans `api/app/roles.py`).
- Front : `front/` (HTML, CSS et JavaScript natifs, aucune bibliothèque ni ressource externe ; politique de sécurité
  du contenu `default-src 'self'`).
- Ce dépôt est un extrait de démonstration, publié en un seul enregistrement : la documentation interne (décisions,
  journal, questions ouvertes) n'y est pas.

Inspecter la base directement :

```bash
sqlite3 jeu_essai/demo/base_demo.sqlite ".tables"
.venv/bin/python verifier.py --base jeu_essai/demo/base_demo.sqlite
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

Le générateur de dossiers fictifs et une partie des tests ont besoin de la structure de la v2 (`import/kamal_structure/`),
qui n'est pas dans ce dépôt : ces tests sont alors sautés, et la base livrée tient lieu de jeu d'essai.

## Limites connues

- Données fictives : leurs proportions (niveaux de lien, incohérences) reflètent des scénarios de test, pas la
  réalité ; un même scénario (un employeur de 201 dossiers) pèse encore lourd.
- La carte des réseaux, la propagation des alertes et la passe de nuit ne sont pas terminées (étapes I et suivantes).
- SQLite seulement pour l'instant ; PostgreSQL est prévu.
