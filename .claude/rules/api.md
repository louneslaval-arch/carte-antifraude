---
paths:
  - "api/**"
---

# Règles de l'API

- Une seule table des droits : `api/app/roles.py` (`DROITS`). Toute route nouvelle y déclare son droit ; un test vérifie
  que chaque route est couverte.
- Rôles : ANALYSTE (cellule fraude : tout) ; AGENCE (identité, coordonnées, historique des dossiers ; rien sur la liste
  noire, les liens, les alertes : droits actuels à mettre en conformité, `docs/questions_ouvertes.md` n°1) ; DIRECTION
  (statistiques agrégées, carte anonyme) ; ADMIN ; TANDEM (contrôles des dossiers sans nom de tiers, étape J).
- Aucune réponse d'erreur ne recopie une valeur reçue ; aucune trace d'exception ne part ; un identifiant de connexion
  inconnu est écrit « inconnu ».
- `Cache-Control: no-store` partout, sauf la géométrie (ETag).
- La requête de recherche n'est jamais journalisée, même quand c'est un nom.
- Journal d'audit : qui, quand, quel indice, quelle époque ; jamais une identité.
- Quotas calculés depuis le journal d'audit ; limites de débit en mémoire (bibliothèque `limits`).
- Identités servies à la demande, selon le rôle, avec quotas ; indices opaques tirés au hasard à chaque publication ;
  nœuds vivants : indices N, N+1… dans l'époque ; 409 si l'époque demandée est close.
- Garde-fou : `CARTE_DONNEES_REELLES=1` seulement hors du dépôt ; une publication non fictive est refusée sinon.
- Flux d'événements : `text/event-stream` ; événements « modification » (numéro seul), « époque », « alerte »
  (ANALYSTE : indice et niveau) ; reprise par `Last-Event-ID`.
- Notification de la v2 : charge utile aux noms de la v2 (`ref`, `updatedAt`, `analysisStatus`, `trigger`) ; HMAC
  SHA-256 du corps ; horodatage à 5 min près ; sans donnée personnelle ; idempotente.
- Routes échangées avec la v2 et Tandem : conventions de l'API de Kamal (noms de champs, `limit` et `offset`,
  `{items, total}`) ; routes des analystes : conventions actuelles du dépôt.
- Chaque route a un test de rôle (refus aux autres rôles) et un test de non-fuite (aucun motif de CIN, RIB, RC ni nom du
  jeu d'essai dans une réponse destinée à un rôle qui n'y a pas droit).
