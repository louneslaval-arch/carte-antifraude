---
paths:
  - "flux/**"
  - "api/app/routes/flux*.py"
---

# Règles du temps réel

- Un seul écrivain : le traiteur. L'API lit seulement. Une transaction par dossier : tout ou rien ; en cas d'échec,
  rien n'est écrit et le travail repasse en attente.
- Idempotence : une version dont l'empreinte est déjà traitée ne change rien et ne produit ni modification ni alerte.
- File : `en_attente` → `en_cours` → `fait` ; `erreur` → nouvelle tentative à intervalle croissant ; `bloque` après
  5 échecs, visible dans l'administration ; une version plus récente fait sauter l'ancienne encore en attente.
- Analyse non terminée (`analysisStatus` différent de `COMPLETE`) : stockée et dessinée « en cours », sans contrôle ni alerte.
- Propagation : dossiers dont une identité est à 3 liens au plus d'un élément modifié ; au-delà de 200 dossiers
  touchés, renvoi à la nuit, noté.
- Une alerte ne baisse jamais en journée (« chemin modifié ») ; le déclassement se fait la nuit, avec sa trace. La
  nuit fait foi ; un écart non expliqué empêche la bascule.
- Rien de global figé dans une arête : coût de taille et rareté lus dans les compteurs au moment du calcul ; une règle
  à seuil est réévaluée pour les clés qui franchissent le seuil.
- Journaux techniques : identifiants techniques, durées, codes d'erreur ; jamais de contenu de dossier, de nom, de CIN, de RIB.
- Secrets (compte de service de la v2, clé de signature) : variables d'environnement seulement.
- SQLite en mode WAL pour le prototype, une seule base (transactions atomiques) ; PostgreSQL :
  `SELECT … FOR UPDATE SKIP LOCKED`, `LISTEN/NOTIFY`.
- Le collecteur écrit la version brute et le miroir ; le traiteur lit le miroir : la couche 1 ne dépend pas de la source.
- Test central : flux = lot (mêmes tables c1 à c5 et mêmes contrôles qu'une construction par lot, dans l'ordre et dans
  un ordre tiré au hasard).
