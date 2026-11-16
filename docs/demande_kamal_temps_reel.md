# Recevoir les dossiers de l'antifraude v2 en temps réel : ce que nous demandons à Kamal

16/11/2026 · Lounès (carte antifraude EQDOM) → Kamal (antifraude v2). Aucune donnée réelle dans ce document : les
exemples sont fictifs (références en « ZZ »).

## En bref

La base client et la carte antifraude doivent recevoir chaque dossier **dès que la v2 a fini de l'analyser** :
arrivée d'un dossier, relecture d'une pièce ou rejeu. Il nous faut deux choses :

1. **Lire les dossiers** : un compte de service en lecture seule sur l'API de la v2.
2. **Savoir qu'un dossier a changé**, sans tout relire : la liste triée par date de mise à jour, puis, mieux, une
   notification envoyée par la v2 à la fin de chaque analyse.

Nous avons déjà écrit, de notre côté, de quoi lire l'API de la v2 et de quoi recevoir une notification signée. Ils
fonctionnent sur un serveur v2 fictif. Il nous manque les accès et quelques précisions.

Il y a trois niveaux, du plus simple au plus solide. Le niveau 1 suffit pour démarrer.

| Niveau | Ce que fait la v2 | Délai d'arrivée chez nous | Travail pour Kamal |
| --- | --- | --- | --- |
| 1. Scrutation | rien de nouveau : nous interrogeons l'API toutes les minutes | 1 à 2 min | un compte de service et un filtre « modifiés depuis » sur la liste |
| 2. Notification | la v2 nous appelle à la fin de chaque analyse | environ 15 s | un appel HTTP signé, sans donnée personnelle |
| 3. Lecture directe | nous lisons ses tables, plus une table d'événements | quelques secondes, aucun oubli possible | un accès en lecture à PostgreSQL |

Volume attendu : environ 150 dossiers par jour (4 250 du 13/10 au 10/11), 3,5 pièces par dossier.

## Niveau 1 : la scrutation (à faire en premier)

### 1.1 Un compte de service en lecture seule

- Un compte dédié (pas celui d'une personne), sur la préproduction d'abord, puis sur la production.
- Droits : lecture seule, sur ces routes et rien d'autre :
  - `POST /api/auth/login`
  - `GET /api/dossiers` (avec `limit`, `offset` et `archives=true`)
  - `GET /api/dossiers/:ref`
- Le mot de passe est transmis à Lounès **en main propre ou par un canal chiffré**, jamais par courriel en clair. Chez
  nous, il vit dans une variable d'environnement, jamais dans le code ni dans une base.
- L'adresse de la v2 doit être en `https`.

**À nous dire :** la durée de vie de la session ouverte par `login`, et ce que renvoie l'API quand elle expire (401 ?).

### 1.2 Un moyen de ne lire que ce qui a changé

Aujourd'hui, nous devons relire toute la liste (environ 25 appels pour 5 000 dossiers) pour repérer les dossiers
modifiés. Nous demandons l'un des deux, au choix de Kamal :

- **Option préférée :** un filtre `GET /api/dossiers?modifies_depuis=2026-11-16T10:00:00Z` (demandé le 28/10) qui
  renvoie les dossiers dont `updatedAt` est postérieur, archives comprises ;
- **à défaut :** un tri garanti de la liste par `updatedAt` décroissant (par exemple `?tri=updatedAt`).

Dans les deux cas, chaque élément de la liste doit porter au moins `ref`, `updatedAt` et `analysisStatus`. C'est déjà
le cas dans le lot du 11/11, mais nous voulons que ce soit garanti.

### 1.3 Questions dont dépend la justesse du niveau 1

| N° | Question | Pourquoi |
| ---: | --- | --- |
| 1 | `updatedAt` du dossier change-t-il **à chaque fois** qu'une pièce, une analyse, une relecture ou un contrôle change ? Prisma ne le fait pas tout seul pour les tables liées. | Sinon, nous manquerions des versions. Si ce n'est pas garanti, merci de le mettre à jour dans la même transaction. |
| 2 | Quel est l'ordre par défaut de `GET /api/dossiers` ? Quelle valeur par défaut et quel maximum pour `limit` ? Quelle erreur pour un paramètre invalide ? | Nous avons supposé : création décroissante, 50 par défaut, 500 au plus, erreur 400. |
| 3 | `analysisStatus` : `schema.prisma` a 5 valeurs, `engine-core_types.ts` en a 3. Lesquelles peut-on voir sur un dossier, et lesquelles veulent dire « analyse terminée » ? | Nous ne calculons de contrôle ni d'alerte que sur une analyse terminée (`COMPLETE`). |
| 4 | Déclencheurs : le README dit `INITIAL`, `REPLAY`, `REANALYSIS` ; `schema.prisma` dit `INTAKE`, `REANALYSE`, `REPLAY`. Lesquels l'API renvoie-t-elle ? | Nous suivons `schema.prisma` pour l'instant. |
| 5 | Le champ `actif` (cité au README, absent de `web_types.ts`) existe-t-il dans la réponse ? Que veut dire un dossier « écarté » (`archives=true`) ? | Pour marquer les dossiers sortis du périmètre actif. |
| 6 | Un dossier peut-il être supprimé, ou seulement archivé ? | Pour savoir s'il faut gérer une disparition. |
| 7 | Y a-t-il une limite de débit sur l'API ? | Nous appelons au plus une fois par minute, plus un appel par dossier changé. |

## Niveau 2 : la notification de fin d'analyse

Quand la carte tourne sur le serveur de production (la v2 ne peut pas joindre le Mac de prototype), la v2 nous
prévient à la fin de chaque analyse. Nous allons ensuite chercher le dossier par `GET /api/dossiers/:ref` : **la
notification ne contient aucune donnée personnelle**.

### 2.1 L'appel

```
POST https://<adresse de la carte, fournie au moment du déploiement>/api/flux/v2
Content-Type: application/json
X-Horodatage: 2026-11-16T10:41:07Z
X-Signature: 5f2b…(64 caractères hexadécimaux)

{"ref":"ZZ26R0007","updatedAt":"2026-11-16T10:41:05.123Z","analysisStatus":"COMPLETE","trigger":"INTAKE"}
```

- **Corps** : exactement ces quatre champs, avec les noms et les valeurs d'énumération de la v2 ; rien d'autre (ni nom,
  ni CIN, ni montant).
- **Quand** : à la fin de chaque analyse, quel que soit le déclencheur (`INTAKE`, `REANALYSE`, `REPLAY`), et aussi
  quand une analyse échoue ou reste incomplète, avec son vrai `analysisStatus`.
- **Signature** : HMAC SHA-256 du corps brut, tel qu'il est envoyé, avec un secret partagé, écrit en hexadécimal
  minuscule dans `X-Signature`.
- **Horodatage** : heure d'envoi en ISO 8601 (UTC) dans `X-Horodatage`. Nous refusons tout appel à plus de 5 minutes
  d'écart.
- **Réponses de notre côté** : `202` si l'appel est accepté (même si nous avions déjà reçu cette version : renvoyer
  ne fait aucun mal) ; `401` pour une signature ou un horodatage refusés ; `400` pour un corps mal formé ; `413`
  au-delà de 2 Ko. Les erreurs suivent la convention de l'API de la v2 (`{"error": code}`) et ne recopient jamais ce
  qui a été reçu.
- **Si nous ne répondons pas** : merci de renvoyer quelques fois à intervalle croissant (par exemple 1 min, 5 min,
  30 min). Une notification perdue n'est pas grave : nous gardons une scrutation de secours toutes les 15 minutes.

### 2.2 À décider ensemble

- **Signer aussi l'horodatage** : nous proposons de signer `horodatage + "." + corps` plutôt que le corps seul, pour
  qu'un appel intercepté ne puisse pas être rejoué avec une autre heure. C'est le choix de Kamal ; nous nous adaptons.
- **Noms des en-têtes** : `X-Signature` et `X-Horodatage` sont provisoires ; si la v2 a déjà une convention (par
  exemple `X-Signature-256`), nous prenons la sienne.
- **Secret de signature** : généré par Kamal (32 octets aléatoires au moins), remis à Lounès par un canal chiffré,
  changé au moins une fois par an. Un secret différent en préproduction et en production.
- **Réseau** : la v2 doit pouvoir joindre notre serveur (hébergé au Maroc, comme la v2). Adresse et règles de pare-feu
  à fixer avec la DSI d'EQDOM au déploiement.

## Niveau 3 : la lecture directe (production, plus tard)

C'est la solution la plus sûre : aucun dossier ne peut être manqué, et nous recevons ce que l'API n'expose pas.

1. **Un accès PostgreSQL en lecture seule** (un rôle dédié, idéalement sur un réplica) aux tables `Dossier`, `Piece`,
   `Analysis`, `AnalysisControl`, `Reanalysis`, `IntakeMessage`, `IndicateurDossier`, `Employeur`, `BlacklistEntry`.
   Notre miroir reproduit déjà ces tables à l'identique, d'après `schema.prisma`.
2. **Une table d'événements sortants** : à chaque fin d'analyse, la v2 y écrit une ligne `(id croissant, ref,
   updatedAt, analysisStatus, trigger, créé le)` **dans la même transaction** que l'analyse. Nous la lisons avec un
   curseur sur `id`. Ainsi aucun événement n'est perdu et l'ordre est garanti.

## Ce que nous renvoyons à la v2 (pour information)

Pour chaque dossier, nous calculons un contrôle « lien avec la liste noire », rendu **au format d'un élément de
`controls[]`** de la v2, plus des indicateurs au format d'`IndicateurDossier`. Tandem le relève par
`GET /api/controles?depuis=…`. Il ne contient aucun nom de tiers. Pour cela, nous demandons à Kamal :

- de **réserver un identifiant de contrôle** (`controlId`, `numeroMetier`) et une famille dans la matrice de la v2 ;
- de nous dire comment nos niveaux (critique, majeure, mineure) correspondent à l'échelle `criticality` de la v2.

Le score ordonne la file de la cellule fraude ; il ne refuse jamais un dossier.

## Pour tester avant la production

- Les accès des niveaux 1 et 2 **sur la préproduction d'abord**.
- Une fois les accès ouverts, Lounès lance le collecteur sur la préproduction, hors du dépôt. Nous vérifions ensemble
  sur des comptages seulement : dossiers lus, versions reçues, délai moyen. Aucun contenu de dossier n'est échangé
  pour ce test.
- À chaque changement de `schema.prisma` ou des types, un nouveau lot de structure (sans le dossier `api/`), pour que
  notre miroir suive.

## Récapitulatif à cocher

| N° | Demande | Niveau | Réponse de Kamal |
| ---: | --- | :---: | --- |
| 1 | Compte de service en lecture seule (préproduction, puis production) | 1 | |
| 2 | Durée de session et code renvoyé à l'expiration | 1 | |
| 3 | `GET /api/dossiers?modifies_depuis=…`, ou tri garanti par `updatedAt` | 1 | |
| 4 | `ref`, `updatedAt`, `analysisStatus` garantis dans chaque élément de la liste | 1 | |
| 5 | `updatedAt` mis à jour à tout changement de pièce, d'analyse, de relecture ou de contrôle | 1 | |
| 6 | Ordre par défaut, `limit` par défaut et maximum, erreur d'un paramètre invalide | 1 | |
| 7 | Valeurs d'`analysisStatus` possibles, et celle qui veut dire « terminée » | 1 | |
| 8 | Noms des déclencheurs renvoyés par l'API | 1 | |
| 9 | Champ `actif`, sens d'« écarté », suppression possible ou non | 1 | |
| 10 | Limite de débit de l'API | 1 | |
| 11 | Notification signée en fin d'analyse (format du § 2.1) | 2 | |
| 12 | Signature avec ou sans l'horodatage ; noms des en-têtes | 2 | |
| 13 | Secret de signature remis par un canal chiffré, un par environnement | 2 | |
| 14 | Nouvelles tentatives en cas d'échec | 2 | |
| 15 | Accès PostgreSQL en lecture seule aux tables listées | 3 | |
| 16 | Table d'événements sortants écrite dans la transaction de l'analyse | 3 | |
| 17 | Identifiant, famille et correspondance de criticité du contrôle « lien avec la liste noire » | retour | |
| 18 | Nouveau lot de structure à chaque changement de `schema.prisma` ou des types | tous | |

Les autres demandes sur le contenu des dossiers (provenance par champ, année des dates d'opération, agence et canal,
etc.) sont listées dans `docs/source_v2.md` § 8 ; elles ne bloquent pas le temps réel.
