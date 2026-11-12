---
paths:
  - "front/**"
---

# Règles des pages

- Aucune ressource externe : ni script, ni feuille de style, ni police, ni image, ni tuile, ni géolocalisation.
  Politique de sécurité du contenu « default-src 'self' » servie par l'API ou nginx ; un essai dans le navigateur vérifie
  qu'aucune requête ne sort de l'origine.
- Pas de bibliothèque chargée depuis internet ; une bibliothèque copiée dans le dépôt seulement après décision
  (`docs/questions_ouvertes.md` n°11).
- Mises à jour en direct par `EventSource` (natif).
- Fond de carte des 12 régions officielles, provinces du Sud comprises, intégré à la page.
- Deux vues synchronisées : carte (où) et réseau (qui) ; curseur de force ; inscrits en rouge, homonymies en pointillé,
  chemins de 4 liens et plus en gris « hors alerte », nœuds nouveaux marqués, dossiers en cours d'analyse en pointillé,
  liens par indice signalés, opérations reconstituées marquées.
- DIRECTION : aucun nom, aucune fiche. AGENCE : selon la décision sur ses droits.
- Aucune donnée personnelle dans l'URL (indices seulement), ni dans le stockage du navigateur au-delà de la session.
- Textes en français ; contrastes et navigation au clavier vérifiés.
