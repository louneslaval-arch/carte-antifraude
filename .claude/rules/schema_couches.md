---
paths:
  - "schema/**"
  - "pipeline/couches/**"
  - "pipeline/regles/**"
  - "pipeline/normalisation/**"
  - "construire.py"
  - "verifier.py"
  - "invariants.yaml"
---

# Règles du schéma et des couches

- Une étape = une couche = un module. Chaque couche se reconstruit entièrement depuis celle du dessous, en une
  commande, sans état caché.
- Survivent aux reconstructions, dans des tables à part : décisions d'analyste, levées, exclusions, référentiels saisis
  à la main (`ref_*`), identifiants attribués.
- Schéma versionné : `schema/NNN_<objet>.sql`, table `schema_version`, application idempotente ; jamais de modification
  à la main. Les migrations du miroir de la v2 sont générées depuis `schema.prisma`.
- SQL portable SQLite et PostgreSQL : `INSERT … ON CONFLICT` plutôt que `INSERT OR REPLACE` ; pas de fonction propre à
  un moteur ; le JSON se lit en Python, pas en SQL ; dates en ISO 8601 ; montants jamais comparés en égalité stricte
  sur des flottants.
- `construire_tout(connexion)` et `traiter(connexion, ref)` appellent les mêmes fonctions ; les règles R et AF
  s'écrivent sur la vue `perimetre`.
- Chaque fait, mention et arête garde son origine (dossier, pièce, version) ; une version relue qui perd une pièce perd
  ce que la pièce portait.
- Identifiants internes stables, jamais renumérotés ; une fiche sans mention est désactivée.
- Fusion automatique seulement sur une règle « certain » (même CIN valide, même RC + tribunal, même ICE) ; tout le reste
  devient une homonymie, à lever par un analyste.
- Valeurs gabarits et faits au statut non normal : exclus des règles d'identité.
- `verifier.py` : invariants déclarés dans `invariants.yaml` (zéro ligne, comptages) ; sortie en comptages seulement.
- Normalisation : fonctions pures, sans entrée ni sortie, testées sur toutes les formes rencontrées (tests par
  propriétés pour les montants, les dates, les CIN, les RIB).
