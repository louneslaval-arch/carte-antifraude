---
paths:
  - "schema/**"
  - "outils/v2/**"
  - "reference/v2/**"
  - "jeu_essai/v2/**"
  - "flux/**"
  - "pipeline/couches/c0_*.py"
  - "pipeline/couches/c1_*.py"
  - "pipeline/couches/c2_*.py"
  - "pipeline/couches/c3_*.py"
  - "pipeline/couches/c6_*.py"
  - "api/app/routes/flux*.py"
  - "api/app/routes/controles*.py"
---

# Alignement sur la v2 de Kamal

- Source de vérité : les fichiers de Kamal (`reference/v2/`, sinon `import/kamal_structure/`) : `schema.prisma`,
  `web_types.ts`, `engine-core_types.ts`, contrats de `reference/`, README (§ 4 vocabulaire, § 7 base). Jamais le
  dossier `api/` du lot, qui contient de vrais dossiers.
- Ces fichiers ne se modifient pas ; ils se lisent par `outils/v2/` (lecteurs de `schema.prisma` et des types).
- Miroir (c0) : généré depuis `schema.prisma` ; mêmes noms de tables et de colonnes que la base de la v2 (après `@map`
  et `@@map`), mêmes clés et contraintes, énumérations en texte contrôlé, JSON en `jsonb` ou en texte. Jamais écrit à la main.
- Modèles d'échange (pydantic) d'après `web_types.ts` ; le collecteur, le générateur et le serveur fictif les emploient.
- Énumérations : valeurs de Kamal, sans traduction ni changement de casse.
- Clé canonique d'un fait = clé « moteur » de la v2 (`ref_cle_canonique`, depuis le README § 4).
- c1 : tables enfants du README § 7 avec ses noms et ses clés ; nos ajouts justifiés dans `docs/correspondance_v2.md`.
- Liste noire au format `BlacklistEntry` ; employeurs selon `Employeur` ; sortie au format d'un élément de
  `controls[]` ; indicateurs au format d'`IndicateurDossier` ; routes échangées avec la v2 selon les conventions de son API.
- Un nom nouveau pour un concept que la v2 a déjà : interdit sans accord. Un concept absent de la v2 : nom français,
  noté dans la carte de correspondance.
- Tout écart volontaire à la structure de Kamal est un choix discutable : le signaler avant de coder.
- Test de dérive : si les fichiers de Kamal changent, la carte de correspondance et le miroir se régénèrent et sont relus.
