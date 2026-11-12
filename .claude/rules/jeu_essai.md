---
paths:
  - "jeu_essai/**"
  - "tests/**"
  - "**/tests/**"
---

# Règles du jeu d'essai et des tests

- Tout est fictif : CIN et références de dossier en « ZZ », identifiants numériques (RIB, ICE, n° CNSS, n°
  d'affiliation) en « 999 », courriels en `@exemple.invalid`, noms tirés de syllabes (latin et arabe), liens vers
  `exemple.invalid`.
- Une forme réelle voulue (test d'un refus) : construite par concaténation, ou ligne marquée `fictif-volontaire`.
- Graine fixe ; deux générations identiques ; la vérité attendue est produite par le générateur, jamais retouchée à
  la main après coup.
- Dossiers v2 fictifs au format exact des types de Kamal ; pièges et scénarios de référence : skill `jeu-essai-v2`.
- Un test par comportement ; noms de tests en français qui disent le comportement
  (`test_relecture_qui_change_le_cin_retire_les_aretes`).
- Aucun test sur des données réelles : les comptages réels sont vérifiés par Lounès hors du dépôt.
- Sorties de génération dans `jeu_essai/sortie/` (ignoré) ; seuls les résultats attendus figés (`attendu_*.json`)
  sont versionnés.
