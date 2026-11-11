# Architecture de la carte antifraude en temps réel

SEVEN · réseaux de fraude EQDOM · 11/11/2026 · version du dépôt, sans aucune donnée réelle. Le contenu de chaque couche est dans `docs/couches.md`, la v2 de Kamal dans `docs/source_v2.md`, les décisions métier dans `docs/decisions.md`, l'ordre de construction dans `docs/plan_construction.md`.

**Objet.** La carte se complète au fil de l'eau : chaque dossier analysé par l'antifraude v2 entre dans la base, rattache ses identités, met à jour le réseau, déclenche le contrôle « lien avec la liste noire » et apparaît sur la carte des analystes, sans attendre une reconstruction.

## 1. Ce que « temps réel » veut dire ici

| Événement | Ce qui doit se passer | Délai visé |
| --- | --- | --- |
| Une analyse se termine dans la v2 (arrivée, relecture, rejeu) | dossier stocké tel quel, rangé dans le miroir, décomposé, identités rattachées, réseau mis à jour, contrôle « lien avec la liste noire » calculé | 2 min au plus en scrutation, 15 s avec notification ; traitement lui-même sous 5 s pour 95 % des dossiers |
| Contrôle calculé | sortie au format d'un contrôle de la v2, disponible pour Tandem | même délai |
| Alerte critique ou majeure | cellule fraude prévenue (bandeau sur la carte ouverte, file des alertes) | même délai |
| Carte ouverte chez un analyste | nouveaux nœuds et liens dessinés sans recharger, marqués « nouveau » | quelques secondes après le traitement |
| Un dossier déjà en base devient relié à cause d'un nouveau dossier | recontrôle, alerte « nouvellement relié » | même délai (sinon la nuit) |
| Chaque nuit | reconstruction complète, rapprochement avec l'état vivant, nouvelle époque | environ 15 min sur les données réelles |
| Nouvel export du registre, nouvelle liste noire | reconstruction du socle, par lot, pas par le flux | à la réception |

Volume à tenir : le lot de production compte 4 250 dossiers du 13/10 au 10/11, soit environ 150 par jour, avec 3,5 pièces par dossier. Un seul processus de traitement suffit largement.

## 2. Principe : un socle publié, une couche vivante

```
Antifraude v2 ──(scrutation chaque minute ; plus tard notification signée, ou lecture directe de ses tables)──▶ COLLECTEUR
                                                                                    │ JSON complet + empreinte
                                                                                    ▼
                      c0 : versions brutes + miroir de la v2 (tables de Kamal à l'identique) ──▶ FILE DE TRAITEMENT
                                                                                    │ un dossier à la fois
                                                                                    ▼
                               TRAITEUR  traiter_dossier(ref) : c1 → c2 → c3 → c5 → c6 → propagation
                                          une transaction ; mêmes fonctions que la construction par lot
                ┌──────────────────────────────┼──────────────────────────────┐
                ▼                              ▼                              ▼
  modifications de la carte        contrôle « lien avec la liste     alertes de la cellule fraude
  (anonymes, numérotées)           noire » au format d'un élément    (critique, majeure)
                                   de controls[] de la v2
                │                              │                              │
                ▼                              ▼                              ▼
  API : socle publié + modifications vivantes ; identités à la demande selon le rôle ; journal
                │ flux d'événements du serveur (format text/event-stream)
                ▼
  Pages : carte du Maroc et réseau, mises à jour en direct

Chaque nuit : reconstruction complète depuis c0 et les exports → rapport d'écart avec l'état vivant
              → nouvelle publication (époque suivante) → bascule atomique
```

- **Socle** : registre du commerce, liste noire, disposition des réseaux. Ne change que par lot (export de Kamal, nouvelle liste, nuit).
- **Couche vivante** : ce que les dossiers EQDOM ajoutent depuis la dernière publication. Fondue dans le socle chaque nuit.

**Huit règles de construction :**

1. **Une seule logique, deux modes.** Chaque couche expose `construire_tout()` (lot) et `traiter(ref)` (un dossier), qui appellent les mêmes fonctions. Les règles R01–R11 et AF01–AF20 s'écrivent sur une vue `perimetre` : toutes les mentions en lot, celles du dossier au fil de l'eau. Même SQL.
2. **Un seul écrivain.** Seul le traiteur écrit ; l'API ne fait que lire. Pas de verrou disputé, pas d'état à moitié écrit : une transaction par dossier.
3. **Tout se rejoue.** c0 garde chaque version reçue ; rejouer c0 dans l'ordre reproduit l'état vivant.
4. **La nuit fait foi.** Un écart entre l'état vivant et la reconstruction est rapporté ; c'est la reconstruction qui est publiée.
5. **Rien de global n'est figé dans une arête.** Le coût de taille et la rareté dépendent de comptages qui bougent à chaque dossier : ils sont lus dans des compteurs au moment du calcul des chemins. Une règle d'existence qui dépend d'un seuil (« nom présent dans 5 sociétés au plus ») est réévaluée pour les clés dont le comptage franchit le seuil.
6. **Une alerte ne baisse pas en journée.** Une force peut baisser quand un nœud grossit, ou un chemin disparaître après une relecture : l'alerte reste ouverte avec la mention « chemin modifié » ; le déclassement ne se fait que la nuit, avec sa trace.
7. **Aucune identité dans ce qui part vers tous les rôles** : modifications de la carte, événements, sortie pour Tandem. Un test le vérifie (motifs de CIN, RIB, RC, noms du jeu d'essai), comme pour la publication.
8. **La structure de Kamal fait foi.** Le miroir de la couche 0 reproduit les tables de la v2 à l'identique ; c1 lit le miroir, pas la réponse d'API, si bien que le passage de l'API à la lecture directe de ses tables ne change rien au-dessus ; ce qui retourne à la v2 suit ses formats (`docs/source_v2.md` § 7).

## 3. Les composants

### 3.1 Collecteur

| Mode | Quand | Fonctionnement |
| --- | --- | --- |
| Scrutation | dès maintenant ; seul mode possible sur le Mac, que la v2 ne peut pas joindre | compte de service ; `POST /api/auth/login` ; `GET /api/dossiers?limit=200&offset=…&archives=true` ; comparaison de `updatedAt` au curseur ; `GET /api/dossiers/:ref` pour les seuls dossiers changés. Intervalle réglable (60 s). Si la liste est triée par mise à jour décroissante, une page suffit ; sinon relecture complète toutes les 5 min (environ 25 appels pour 5 000 dossiers), en attendant `modifies_depuis` |
| Notification | quand Kamal l'ajoute, sur le serveur de production | la v2 appelle `POST /api/flux/v2` à la fin de chaque analyse avec `{ref, updatedAt, analysisStatus, trigger}`, signé (HMAC SHA-256 sur le corps, horodatage à 5 min près), sans aucune donnée personnelle ; le collecteur va ensuite chercher le dossier. La scrutation reste en filet de sécurité toutes les 15 min |
| Lecture directe, table d'événements sortants | si Kamal ouvre sa base en lecture | le miroir se remplit depuis ses tables, sans transformation ; la v2 écrit un événement dans la même transaction que l'analyse et le collecteur le lit avec un curseur : aucun événement perdu, ordre garanti |

Ce qu'il écrit : `c0_dossier_brut` (une ligne nouvelle seulement si l'empreinte change), le miroir de la v2 (la dernière version) et une entrée dans `flux_travail`.

Règles : une analyse non terminée (`analysisStatus` différent de `COMPLETE`, ou analyse provisoire) est stockée et dessinée « en cours d'analyse », sans contrôle ni alerte ; nouvelles tentatives à intervalle croissant ; aucun contenu de dossier dans les journaux techniques ; les dossiers écartés du périmètre actif sont repris (`archives=true`) et marqués.

### 3.2 File de traitement

`flux_travail` : `en_attente → en_cours → fait`, ou `erreur` (nouvelle tentative) puis `bloque` après 5 échecs, visible dans l'administration. Une seule version en cours par dossier ; si une version plus récente arrive, l'ancienne encore en attente est sautée. SQLite : un seul processus de traitement. PostgreSQL : `SELECT … FOR UPDATE SKIP LOCKED`, réveil par `LISTEN/NOTIFY`.

### 3.3 Traiteur : `traiter_dossier(ref)`

| N° | Couche | Ce qui est fait, pour ce dossier seulement |
| ---: | --- | --- |
| 1 | c0 | lire la dernière version du miroir ; si son empreinte est déjà traitée, s'arrêter |
| 2 | c1 | supprimer puis réécrire les tables enfants de la pièce (opérations, personnes, selon le README de Kamal), les faits normalisés, les mois de relevé, les mentions de sociétés, les identifiants bruts |
| 3 | c2 | rattacher chaque mention à une fiche maître par clé forte (CIN valide hors gabarit ; RC + tribunal ; ICE ; n° d'affiliation CNSS pour un employeur) ; sinon fiche propre au dossier, identifiant attribué une fois et conservé ; règles R et AF sur le périmètre du dossier ; un rapprochement probable crée une homonymie, jamais une fusion |
| 4 | c3 | dossier, parties (demandeur, co-emprunteur, caution, gérant, société, employeur), revenus déclarés et vérifiés, charges, comptes, opérations, véhicules ; incohérences dans le dossier et d'un dossier à l'autre (même RIB, même châssis, même fichier) par recherche dans les index |
| 5 | c5 | retirer les arêtes dont ce dossier est la source, ajouter les nouvelles (barème n°23), mettre à jour les compteurs de taille ; calculer les positions provisoires des nouveaux nœuds ; produire la liste des modifications (nœuds et arêtes ajoutés, retirés, modifiés) |
| 6 | c6 | contrôle réseau (§ 3.4), avec l'instantané des entrées et la version des paramètres ; alerte si le niveau l'exige et si aucune levée d'analyste ne couvre le couple (dossier, inscrit) |
| 7 | c6 | propagation : les dossiers dont une identité est à 3 liens au plus d'un élément modifié sont recontrôlés ; un niveau qui monte crée une alerte « nouvellement relié » ; au-delà de 200 dossiers touchés (gros nœud), renvoi à la nuit, noté |
| 8 | sorties | écrire les modifications de la carte (numérotées dans l'époque) et la sortie pour Tandem, valider la transaction, réveiller l'API |

Si une étape échoue, rien n'est écrit et le travail repasse en attente. Chaque arête garde son dossier et sa pièce d'origine : un dossier relu qui perd une pièce ou change de CIN perd aussi les arêtes qu'elle portait. Une fiche qui n'a plus aucune mention est désactivée, jamais renumérotée.

### 3.4 Calcul des chemins

- **Graphe en mémoire dans le traiteur** : listes d'adjacence avec poids de départ et fiabilités, chargées au démarrage depuis c5 et mises à jour à chaque dossier. Avec tout le registre, de l'ordre d'un million d'arêtes : à garder sous forme de tableaux, comme la carte globale. Les personnes du registre présentes dans une seule société et sans lien avec la liste noire ne servent que de point d'arrivée : elles peuvent être chargées à la demande.
- **Un identifiant partagé est un nœud, pas un lien.** A – RIB – B vaut un lien « même RIB » (0,9 × coût du RIB selon le nombre de porteurs). La longueur d'un chemin se compte en liens entre personnes ou sociétés, depuis l'identité du dossier la plus proche (demandeur, caution, gérant, société ou employeur) : c'est ce qui donne les niveaux de la n°20.
- **Recherche bornée** : meilleure force par nœud et par longueur, sur 3 liens au plus pour les alertes, en écartant ce qui passe sous la force minimale d'affichage. Les chemins de 4 liens et plus ne sont calculés qu'à la demande, pour le panneau de l'analyste, avec le curseur.
- **Force** = produit des poids de départ × produit des coûts de taille des nœuds traversés (1 si n ≤ 2, sinon √(2/n), jamais aux deux bouts) × produit des fiabilités des rapprochements et des passages d'une société à l'autre (× 0,5 par rôle lu seulement dans une annonce mélangée).
- **Niveau d'un chemin** = niveau maximal selon la longueur (n°20), plafonné à « mineure » par une homonymie non levée à un bout (n°22) ou par un lien de foyer (n°24), puis comparé aux seuils de force (§ 4). **Niveau du dossier** = le plus haut de ses chemins ; on garde les trois meilleurs (niveau, puis force) et le nombre d'inscrits atteints.

### 3.5 API : le socle plus les modifications vivantes

- **Époque.** Chaque publication de nuit ouvre une époque. Les indices du socle restent tirés au hasard ; les nœuds ajoutés en journée prennent les indices suivants (N, N+1…), ce qui ne révèle que leur ordre d'arrivée. `flux_indice` garde, époque par époque, la correspondance indice ↔ identifiant interne ; le journal d'audit enregistre l'époque avec chaque ligne, pour rester lisible des mois après.
- **Identités des nœuds vivants** : servies par les mêmes routes (`/api/carte/noms`, `/api/carte/noeud/{indice}`, `/api/carte/recherche`), lues dans la base vivante quand l'indice dépasse le socle ; mêmes droits, mêmes quotas, même journal.
- **Rôles** : ANALYSTE = cellule fraude (tout) ; AGENCE = autres utilisateurs (agences, service client) : identité, coordonnées, historique des dossiers, rien sur la liste noire, les liens ni les alertes (n°10 ; écart actuel : `docs/questions_ouvertes.md` n°1) ; DIRECTION = statistiques agrégées et carte anonyme ; ADMIN ; nouveau rôle technique `TANDEM` : contrôles des dossiers, sans nom de tiers. À confirmer avec la direction informatique et la conformité d'EQDOM.
- **Conventions** : les routes échangées avec la v2 et Tandem suivent celles de l'API de Kamal (noms de champs, pagination `limit` et `offset`, réponses `{items, total}`) ; les routes des analystes gardent les conventions actuelles du dépôt.
- Routes ajoutées : § 6.

### 3.6 Pages

- Au chargement : géométrie du socle (avec `ETag`), puis les modifications de l'époque depuis 0 ; ensuite abonnement au flux d'événements (`EventSource`, natif au navigateur : aucune bibliothèque externe). Un événement « modification n » déclenche `GET /api/carte/modifications?depuis=…` ; un événement « époque » déclenche le rechargement.
- Nouveaux nœuds marqués « nouveau », filtre « arrivées du jour », compteur ; dossier en cours d'analyse en pointillé ; chemins de 4 liens et plus en gris, « hors alerte » ; liens par indice (tiers bancaire lu dans un libellé) signalés comme tels.
- **Disposition provisoire** des nouveaux nœuds, calculée par le traiteur : vue réseau, à côté d'un voisin déjà placé (angle d'or, décalage déterministe) ; réseau entièrement nouveau, bande « arrivées du jour » ; vue Maroc, ville de l'adresse qui fait foi (n°16), sinon zone « sans ville connue ». La disposition définitive est recalculée la nuit.
- ANALYSTE : un bandeau pour chaque alerte critique ou majeure, avec accès direct au dossier sur la carte.

### 3.7 Passe de nuit

1. Mettre le traiteur en pause (les dossiers continuent d'arriver dans la file).
2. Reconstruire toutes les couches dans une base neuve, depuis les versions de c0 (qui régénèrent le miroir), l'export du registre et la liste noire.
3. Rapprocher l'état vivant et la reconstruction, table par table et contrôle par contrôle (`comparer_bases.py` étendu). Écart attendu : nul, sauf ce qu'explique un changement d'export, de paramètres ou de taille de nœud.
4. Publier (nouvelle époque, nouveaux indices tirés au hasard, disposition recalculée), basculer de façon atomique, appeler `/admin/recharger`, envoyer l'événement « époque ».
5. Relancer le traiteur sur la nouvelle base ; il traite ce qui est arrivé pendant la reconstruction.
6. Envoyer à la cellule fraude la liste des dossiers nouvellement reliés depuis la nuit précédente (n°9) et celle des déclassements.

Si la reconstruction échoue ou si l'écart n'est pas expliqué, pas de bascule : l'état vivant continue et l'administrateur est prévenu. Durée attendue sur les données réelles : environ 15 min (base 6 min, chaînes 1 min, carte globale 3 min, dossiers et contrôles).

### 3.8 Où tournent les données

- **Prototype** : sur le Mac, hors du dépôt et hors de tout dossier synchronisé (SQLite verrouille mal les fichiers d'un dossier synchronisé), dans `~/antifraude-donnees/` ; base SQLite en mode `WAL` ; `CARTE_DONNEES_REELLES=1` posé seulement là. Le dépôt reste sans aucune donnée réelle. Trois processus : le traiteur (avec le collecteur), l'API, la passe de nuit (tâche planifiée à 3 h). Claude Code n'accède jamais à ce dossier : Lounès lance les commandes.
- **Production** : PostgreSQL, comme la v2 ; conteneurs `api`, `traiteur`, `postgres`, `nginx` ; hébergement au Maroc ; notification de la v2, ou lecture directe de ses tables, à la place de la scrutation.

### 3.9 Arborescence du dépôt

```
pipeline/
  normalisation/   noms, CIN, RC, tribunal, RIB, montants, dates, villes : fonctions pures tirées de
                   construire_base.py et d'extraire_json_v2.py
  couches/         c0_brut.py … c6_controle.py : chacun construire_tout() et traiter(ref)
  regles/          R01–R11 et AF01–AF20 en SQL sur la vue perimetre
  (scripts du kit, inchangés, tant que les couches ne les remplacent pas)
flux/
  collecteur.py    scrutation, notification, curseur
  file.py          file de traitement
  traiteur.py      boucle : prendre un travail, traiter_dossier, publier les modifications
  graphe_vivant.py graphe en mémoire, compteurs de taille, recherche bornée, positions provisoires
  nuit.py          reconstruction, rapport d'écart, publication, bascule
schema/            000_schema_version.sql, 001_brut.sql, migrations du miroir générées depuis schema.prisma…
outils/v2/         lecture de schema.prisma et des types de Kamal, carte de correspondance, génération du miroir
reference/         villes, grands employeurs ; v2/ : copie datée de la structure de Kamal (si versionnée)
construire.py, verifier.py, invariants.yaml
jeu_essai/v2/      générateur de dossiers v2 fictifs, serveur v2 fictif, vérité attendue
api/               routes existantes + flux, modifications, événements, contrôles, alertes, dossiers
front/             pages
deploiement/       conteneurs api, traiteur, postgres, nginx ; tâche de nuit
```

## 4. Règles de score

Les règles complètes (décisions n°19 à 24) sont dans `.claude/rules/score.md` et `docs/decisions.md`. Les paramètres existent dès le code, avec une valeur provisoire, dans `c6_version_parametres` ; les questions encore ouvertes sont dans `docs/questions_ouvertes.md` (n°2 à 7).

| Question | Proposition provisoire |
| --- | --- |
| Seuils de force | majeure à partir de 0,20 ; mineure à partir de 0,08 ; affichage par défaut à partir de 0,05. Le gérant de 8 sociétés entre l'employeur et une société inscrite (0,245) reste majeur ; le liquidateur de 40 sociétés (0,056) est affiché sans alerte |
| Victime | tout inscrit actif pèse 1 ; une inscription qui désigne une victime ne compte qu'à 0 lien ; en attendant le dictionnaire des motifs d'EQDOM, toutes propagent |
| Temps | rôles terminés aux poids actuels des anciens rôles (0,3 à 0,5) ; pas de demi-vie tant que ce n'est pas décidé |
| Même identifiant dans plusieurs dossiers récents | signal à part, sans multiplier la force : incohérence « dossiers en rafale » (même RIB, même adresse ou même employeur inconnu dans plusieurs dossiers en moins de 30 jours) |
| Plusieurs inscrits atteints | niveau et force du meilleur chemin (n°9) ; le nombre d'inscrits atteints affiché à côté |
| Liens du JSON v2 hors barème | même châssis dans deux dossiers : incohérence « double financement » plutôt que lien ; même concessionnaire : hors score, comme l'apporteur |
| Levée d'alerte puis nouveau chemin | la levée vaut pour le couple (dossier, inscrit) ; un chemin d'une autre nature qui fait monter le niveau rouvre l'alerte |

## 5. Tables ajoutées pour le temps réel

Les couches c0 à c7 sont décrites dans `docs/couches.md` (préfixes `c0_` à `c7_` ; le miroir de la v2 garde les noms de Kamal). S'y ajoutent :

| Table | Clé | Contenu |
| --- | --- | --- |
| `flux_source` | nom | instance v2 (adresse, mode scrutation, notification ou lecture directe, intervalle) ; le secret du compte de service reste dans une variable d'environnement |
| `flux_curseur` | source | dernier `updatedAt` vu, dernière scrutation, dernière réussite |
| `flux_travail` | id | ref, empreinte, reçu le, état, essais, prochaine tentative, durée, code d'erreur (sans donnée) |
| `flux_epoque` | n° | début, fin, publication, nombre de nœuds du socle |
| `flux_indice` | (époque, indice) | identifiant interne, type, créé le |
| `flux_modification` | (époque, n°) | type (nœud ajouté, arête ajoutée, retirée, modifiée), contenu anonyme, dossier source (jamais servi) |
| `c5_compteur` | nœud | taille n pour le coût (sociétés, dirigeants, clients déclarants, porteurs distincts) |
| `c6_controle_reseau` | id | ref, version du dossier, déclencheur (arrivée, propagation, nuit), horodatage, version des paramètres, niveau, force, inscrits atteints, trois chemins, instantané des entrées |
| `c6_alerte` | id | ref, inscrit, niveau, état (ouverte, confirmée, levée, close), première émission, dernière mise à jour, motif (arrivée, propagation, nuit) |
| `c6_levee` | (ref, inscrit) | décision d'analyste, justification, analyste, date ; survit à toutes les reconstructions |
| `c6_version_parametres` | version | barème, coût, seuils, limites de longueur, date, auteur |
| `sortie_tandem` | n° | ref, sortie au format d'un élément de `controls[]` de la v2, indicateurs au format d'`IndicateurDossier`, émis le, relevé le |

Les 55 contrôles de la v2 ne sont pas copiés dans une table à nous : ils se lisent dans le miroir. Le journal d'audit de l'API gagne une colonne `epoque`.

## 6. Routes ajoutées à l'API

| Route | Rôle | Entrée | Sortie |
| --- | --- | --- | --- |
| `POST /api/flux/v2` | v2 (signature) | `{ref, updatedAt, analysisStatus, trigger}` | 202 ; sans effet si déjà reçu |
| `GET /api/carte/modifications?epoque=E&depuis=S` | tous | — | nœuds (indice, type, liste noire, réseau, ville, positions), arêtes (a, b, style, force), retraits ; 409 si l'époque est close |
| `GET /api/carte/evenements` | tous | — | flux : « modification » (numéro seul), « époque » ; pour ANALYSTE, « alerte » (indice, niveau) |
| `GET /api/controles/{ref}` | TANDEM, ANALYSTE | — | sortie pour Tandem |
| `GET /api/controles?depuis=S` | TANDEM | — | `{items, total}` : contrôles calculés depuis S, pour que Tandem relève les nouveaux sans appeler dossier par dossier |
| `GET /api/alertes?etat=ouverte` | ANALYSTE | — | file de la cellule fraude, par niveau puis force |
| `POST /api/alertes/{id}/decision` | ANALYSTE | `{decision, justification}` (décision : confirmée ou levée) | levée attachée au couple (dossier, inscrit) |
| `GET /api/dossiers/{ref}` | ANALYSTE (tout), AGENCE (sans liste noire ni liens) | — | fiche du dossier |
| `GET /api/admin/flux` | ADMIN | — | état du collecteur et de la file : en attente, erreurs, délais ; aucune donnée de dossier |

**Sortie pour Tandem** : un élément au format de `controls[]` de la v2 (champs relevés dans le lot : `controlId`, `numeroMetier`, `family`, `label`, `source`, `outcome`, `criticality`, `escalade`, `details`, `missing`, `previousOutcome`) ; types et valeurs exacts à caler sur `engine-core_types.ts`, identifiant et famille à convenir avec Kamal. Valeurs fictives ; aucun nom de tiers : les noms ne se voient que sur la carte, par la cellule fraude.

```
{ "ref": "ZZ600001",
  "control": {
    "controlId": "<réservé par Kamal>", "numeroMetier": "<réservé par Kamal>", "family": "<famille convenue>",
    "label": "Lien avec la liste noire", "source": "<valeur de la v2 pour un contrôle externe>",
    "outcome": "ANOMALIE", "criticality": "<niveau « majeure » dans l'échelle de la v2>",
    "escalade": "<selon le type de la v2>", "missing": "<selon le type de la v2>", "previousOutcome": null,
    "details": { "versionDossier": "sha256:…", "calculeLe": "2026-11-12T10:41:07Z", "parametres": "2026-11-09.1",
                 "niveau": "majeure", "force": 0.42, "inscritsAtteints": 1,
                 "chemins": [ { "depart": "employeur", "liens": 1, "niveau": "majeure", "force": 0.42,
                                "libelle": "Employeur : son gérant est inscrit en liste noire",
                                "homonymieALever": false } ] } },
  "indicateurs": [ { "indicateur": "<nom convenu>", "valeur": 0.42, "fiabilite": "<CERTAINE, EXTRAITE ou FRAGILE>" } ] }
```

## 7. Ce qui garantit qu'on ne casse rien

Les règles communes du plan restent. Le temps réel ajoute ces tests, tous sur des données fictives :

1. **Flux = lot** : rejouer les dossiers du jeu d'essai un par un dans le traiteur, dans l'ordre puis dans un ordre tiré au hasard, donne exactement les mêmes tables c1 à c5 et les mêmes contrôles recalculés qu'une construction par lot. C'est le test central.
2. **Sans effet au second passage** : le même dossier reçu deux fois ne change rien et ne produit ni modification ni alerte.
3. **Correction** : un dossier relu dont le CIN change perd ses anciennes arêtes ; l'état final égale la construction par lot.
4. **Propagation dans les deux sens** : B arrive avec le RIB de A, déjà relié, donc B est relié ; A arrive relié après B, donc B devient « nouvellement relié ».
5. **Levée respectée** : une alerte levée ne revient ni au dossier suivant ni la nuit, sauf chemin d'une autre nature qui fait monter le niveau.
6. **Aucune fuite** dans les modifications, les événements et la sortie pour Tandem (motifs de CIN, RIB, RC, noms du jeu d'essai).
7. **Arrêt brutal** du traiteur au milieu d'un dossier : au redémarrage, base cohérente, file reprise.
8. **Délai** : 95 % des dossiers sous 5 s sur le grand jeu d'essai (61 043 sociétés) plus 1 000 dossiers fictifs.
9. **Nuit** : écart nul entre l'état vivant et la reconstruction sur le jeu d'essai ; refus de bascule quand on fabrique un écart.
10. **Époque** : un indice d'une époque close est refusé (409) et la page recharge.

Ces tests demandent deux outils (étape C) :

- un **générateur de dossiers v2 fictifs** au format exact des types de Kamal, avec tous les pièges du lot (relevé relu et non relu avec sa ligne mensuelle reconstituée, CIN multiple, clés en double, clés inventées, montants en texte, dates `jj/mm`, trois vocabulaires), branché sur le registre et la liste noire fictifs pour que des chemins connus existent (employeur dont le gérant est inscrit, RIB partagé avec un inscrit, homonyme, foyer, victime), avec sa vérité attendue ;
- un **serveur v2 fictif** (mêmes routes que la v2, notification comprise) qui fait arriver et relire des dossiers au fil du temps, pour tester le collecteur de bout en bout sans Kamal ni donnée réelle.
