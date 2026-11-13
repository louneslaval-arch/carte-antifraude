# Correspondance entre la v2 de Kamal et la base de la carte

Source de vérité : les fichiers de Kamal (`reference/v2/`, sinon `import/kamal_structure/`). La partie générée
ci-dessous se refait par `outils/v2/carte_correspondance.py --ecrire` ; un test échoue tant qu'elle ne correspond
pas aux fichiers de Kamal (dérive).

## Nos ajouts (écrits à la main, chacun justifié)

| Nom | Où | Pourquoi la v2 ne l'a pas |
| --- | --- | --- |
| `schema_version` | toutes couches | numéro des migrations appliquées (`schema/000_schema_version.sql`) ; propre à notre base |
| `c0_export` | c0 | un passage de collecte (date, source, mode, comptages) : la v2 ne trace pas qui la lit |
| `c0_dossier_brut` | c0 | chaque version reçue d'un dossier, JSON complet et empreinte, pour tout rejouer ; `updated_at` reprend `updatedAt` |
| `flux_source`, `flux_curseur`, `flux_travail` | temps réel | état de notre collecteur et de sa file ; `ref`, `updated_at`, `actif` reprennent les notions de la v2 |
| `Piece.id`, `Reanalysis.id` | miroir | non exposés par l'API : dérivés de l'identifiant du dossier (`<id>:<upstreamPieceId>`, `<id>:relecture:<rang>`) ; viendront de la base de Kamal en lecture directe |
| `Piece.createdAt`, `Piece.updatedAt` | miroir | non exposés par l'API : ceux du dossier, en attendant la lecture directe |
| `Dossier.actif` | miroir | non exposé dans le détail : connu en lisant la liste avec et sans `archives=true` |
| `AnalysisControl.applicabilityReason` | miroir | obligatoire dans la base, mais l'API peut le rendre vide : rangé en chaîne vide |
| `Synthese`, `ConstatLibre`, `label`, `family`, `numeroMetier`, `previousOutcome` d'un contrôle | version brute seulement | l'API n'en donne pas les clés (`Synthese.id`, `analysisId`) ou les calcule à l'affichage ; lisibles dans `c0_dossier_brut` (`pipeline/couches/c0_brut.py`, `PLACES`) |
| `c1_releve_mois`, `c1_releve_operation` | c1 | tables enfants `releve_mois` et `releve_operation` du README § 7, noms et clés repris (`ref`, `upstream_piece_id` = `upstreamPieceId`, rang du mois, rang de l'opération) ; ajouts : `salaire_detecte`, `echeances_credits` (agrégats amont « MM/AAAA »), `nb_operations_lues`, `nature` (`lue` ou `reconstituee_amont`), date complétée avec l'année du mois |
| `c1_mention_personne` et la vue `c1_societe_personne` | c1 | table enfant `societe_personne` du README § 7 (gérants, dirigeants, associés d'un RC ou de statuts) élargie à toute personne citée par une pièce : la vue rend exactement le périmètre de Kamal ; rôles ajoutés : `titulaire_cin`, `employe` (assuré compris), `pensionne`, `proprietaire`, `acheteur`, `associe_present`, `nouveau_gerant`, `titulaire_compte`, `titulaire_quittance` (les deux derniers absents de l'extracteur du 11/11) ; `statut` (`gabarit` pour un nom d'exemple) |
| `c1_piece` | c1 | une ligne par pièce du miroir, avec la version du dossier (`updatedAt`), le nombre de champs lus et relus et le nombre de listes d'objets non rangées : la v2 ne compte pas. Les relectures restent dans `"Reanalysis"` (miroir) : c1 n'en garde que l'origine de chaque fait et `nb_champs_relus` |
| `c1_fait`, vue `c1_fait_retenu` | c1 | `Piece.fields` est un JSON libre dans la v2 ; ici une ligne par valeur aplatie : clé brute, clé canonique (clé moteur de la v2), texte normalisé, nombre, date, origine (`amont`, `relue_ciblee`, `fusion`), statut (normal, clé inventée, champ de CIN hors CIN, gabarit) |
| `c1_cle_inconnue` (vue) | c1 | rapport des clés absentes de `ref_cle_canonique` : jamais acceptées en silence |
| `c1_mention_societe` | c1 | société citée par une pièce (société du RC et des statuts, employeur, concessionnaire, banque), avec RC, tribunal, ICE, n° d'affiliation : la v2 les laisse dans `fields` |
| `c1_identifiant_brut` | c1 | identifiant normalisé porté par une pièce (RIB, CIN, CNSS, pension, châssis, immatriculation, INPE, RC + tribunal, ICE, affiliation) : un nœud du graphe, pas un lien |
| `upstream_piece_id`, `extraction_status` | c1 | `upstreamPieceId` et `extractionStatus` de Kamal, écrits en minuscules avec tiret bas comme toutes nos tables dérivées (SQL portable sans guillemets ; même choix que `c0_dossier_brut.updated_at`, question ouverte n°16) ; les valeurs sont celles de Kamal |
| `c1_fait.origine` | c1 | `amont`, `relue_ciblee`, `fusion` : notion propre à c1 (d'où vient la valeur d'un champ), distincte de l'énumération `source` de la pièce (`AMONT`, `REANALYSE`), gardée telle quelle dans `c1_piece.source` |
| `numero_chassis`, `immatriculation`, `marque`, `modele`, `date_mise_circulation` | `ref_cle_canonique` | cibles des libellés français de la carte grise (« Numéro de chassis »…), reprises de l'extracteur du 11/11 : le vocabulaire moteur de la v2 n'a pas de clé pour la carte grise |
| `ref_cle_canonique` | référentiel | table de passage clé brute → clé moteur par type de pièce, traductions du README § 4 de Kamal (`pipeline/normalisation/cles.py`) et toutes les clés de son inventaire par type de pièce (`vocabulaire_v2.py`, généré par `outils/v2/vocabulaire_cles.py`), versionnée ; le module fait foi ; la v2 la porte dans son code, pas dans sa base |

<!-- DEBUT PARTIE GENEREE : outils/v2/carte_correspondance.py --ecrire ; ne pas modifier à la main -->

## Sources lues

| Fichier | sha256 |
| --- | --- |
| `schema/schema.prisma` | `3897d3c9febea48dd3544e308d9532f6430dcd501e3d23a6a062900a36a5ba09` |
| `types/web_types.ts` | `0c036cbaeedbc1ff9c0526332f989e5f0d4a0e60ff27af83249880f3909af88a` |
| `types/engine-core_types.ts` | `d300ba990dfd27dfbe06f068d60e2d5aee067346be19d9bc108b188bebf374ed` |
| `README.md` | `02daee3a7fe37e385bc8a7918749b183ea5c038bb3d07a6cfd068c902a5f3247` |

## Modèles de schema.prisma → miroir c0 (repris à l'identique)

Couverture : 13 modèles, 175 champs, 13 énumérations de schema.prisma ; 100 % repris dans le miroir c0 (étape D), noms de tables et de colonnes tels que PostgreSQL les voit.

| Table | Champ | Colonne | Type | Facultatif | Clé, unicité | Destination |
| --- | --- | --- | --- | --- | --- | --- |
| `Dossier` | `id` | `id` | String | non | clé | miroir c0, repris |
| `Dossier` | `ref` | `ref` | String | non | unique | miroir c0, repris |
| `Dossier` | `actif` | `actif` | Boolean | non |  | miroir c0, repris |
| `Dossier` | `personType` | `personType` | PersonType | oui |  | miroir c0, repris |
| `Dossier` | `csp` | `csp` | String | oui |  | miroir c0, repris |
| `Dossier` | `productType` | `productType` | String | oui |  | miroir c0, repris |
| `Dossier` | `paymentMode` | `paymentMode` | String | oui |  | miroir c0, repris |
| `Dossier` | `clientName` | `clientName` | String | oui |  | miroir c0, repris |
| `Dossier` | `agence` | `agence` | String | oui |  | miroir c0, repris |
| `Dossier` | `canal` | `canal` | String | oui |  | miroir c0, repris |
| `Dossier` | `businessData` | `businessData` | Json | oui |  | miroir c0, repris |
| `Dossier` | `category` | `category` | RiskCategory | oui |  | miroir c0, repris |
| `Dossier` | `categoryRule` | `categoryRule` | Int | oui |  | miroir c0, repris |
| `Dossier` | `categoryReason` | `categoryReason` | String | oui |  | miroir c0, repris |
| `Dossier` | `analysisStatus` | `analysisStatus` | AnalysisStatus | non |  | miroir c0, repris |
| `Dossier` | `verdict` | `verdict` | FraudVerdict | oui |  | miroir c0, repris |
| `Dossier` | `verdictProvisional` | `verdictProvisional` | Boolean | non |  | miroir c0, repris |
| `Dossier` | `alertsMinor` | `alertsMinor` | Int | non |  | miroir c0, repris |
| `Dossier` | `alertsMajor` | `alertsMajor` | Int | non |  | miroir c0, repris |
| `Dossier` | `alertsCritical` | `alertsCritical` | Int | non |  | miroir c0, repris |
| `Dossier` | `matrixVersion` | `matrixVersion` | String | oui |  | miroir c0, repris |
| `Dossier` | `businessReceivedAt` | `businessReceivedAt` | DateTime | oui |  | miroir c0, repris |
| `Dossier` | `resultsReceivedAt` | `resultsReceivedAt` | DateTime | oui |  | miroir c0, repris |
| `Dossier` | `commentaireScore` | `commentaireScore` | Float | oui |  | miroir c0, repris |
| `Dossier` | `commentaireAlerte` | `commentaireAlerte` | Boolean | non |  | miroir c0, repris |
| `Dossier` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `Dossier` | `updatedAt` | `updatedAt` | DateTime | non |  | miroir c0, repris |
| `Dossier` | `pieces` | — | Piece | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Dossier` | `analyses` | — | Analysis | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Dossier` | `intakes` | — | IntakeMessage | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Dossier` | `reanalyses` | — | Reanalysis | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Dossier` | `indicateurs` | — | IndicateurDossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Dossier` | `constats` | — | ConstatLibre | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `IntakeMessage` | `id` | `id` | String | non | clé | miroir c0, repris |
| `IntakeMessage` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `IntakeMessage` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `IntakeMessage` | `kind` | `kind` | IntakeKind | non |  | miroir c0, repris |
| `IntakeMessage` | `payload` | `payload` | Json | oui |  | miroir c0, repris |
| `IntakeMessage` | `filePath` | `filePath` | String | oui |  | miroir c0, repris |
| `IntakeMessage` | `sha256` | `sha256` | String | oui |  | miroir c0, repris |
| `IntakeMessage` | `receivedAt` | `receivedAt` | DateTime | non |  | miroir c0, repris |
| `Piece` | `id` | `id` | String | non | clé | miroir c0, repris |
| `Piece` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `Piece` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Piece` | `upstreamPieceId` | `upstreamPieceId` | String | non |  | miroir c0, repris |
| `Piece` | `type` | `type` | String | non |  | miroir c0, repris |
| `Piece` | `pdfPath` | `pdfPath` | String | oui |  | miroir c0, repris |
| `Piece` | `sha256` | `sha256` | String | oui |  | miroir c0, repris |
| `Piece` | `extractionStatus` | `extractionStatus` | String | non |  | miroir c0, repris |
| `Piece` | `fields` | `fields` | Json | non |  | miroir c0, repris |
| `Piece` | `source` | `source` | ExtractionSource | non |  | miroir c0, repris |
| `Piece` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `Piece` | `updatedAt` | `updatedAt` | DateTime | non |  | miroir c0, repris |
| `Piece` | unicité (dossierId, upstreamPieceId) | | | | unique | miroir c0, repris |
| `Analysis` | `id` | `id` | String | non | clé | miroir c0, repris |
| `Analysis` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `Analysis` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Analysis` | `matrixVersion` | `matrixVersion` | String | non |  | miroir c0, repris |
| `Analysis` | `engineVersion` | `engineVersion` | String | non |  | miroir c0, repris |
| `Analysis` | `trigger` | `trigger` | AnalysisTrigger | non |  | miroir c0, repris |
| `Analysis` | `status` | `status` | AnalysisStatus | non |  | miroir c0, repris |
| `Analysis` | `verdict` | `verdict` | FraudVerdict | oui |  | miroir c0, repris |
| `Analysis` | `provisional` | `provisional` | Boolean | non |  | miroir c0, repris |
| `Analysis` | `startedAt` | `startedAt` | DateTime | non |  | miroir c0, repris |
| `Analysis` | `endedAt` | `endedAt` | DateTime | oui |  | miroir c0, repris |
| `Analysis` | `error` | `error` | String | oui |  | miroir c0, repris |
| `Analysis` | `controls` | — | AnalysisControl | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Analysis` | `reanalyses` | — | Reanalysis | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `AnalysisControl` | `id` | `id` | String | non | clé | miroir c0, repris |
| `AnalysisControl` | `analysisId` | `analysisId` | String | non |  | miroir c0, repris |
| `AnalysisControl` | `analysis` | — | Analysis | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `AnalysisControl` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `AnalysisControl` | `controlId` | `controlId` | String | non |  | miroir c0, repris |
| `AnalysisControl` | `applicable` | `applicable` | Boolean | non |  | miroir c0, repris |
| `AnalysisControl` | `applicabilityReason` | `applicabilityReason` | String | non |  | miroir c0, repris |
| `AnalysisControl` | `outcome` | `outcome` | ControlOutcome | non |  | miroir c0, repris |
| `AnalysisControl` | `criticality` | `criticality` | Criticality | oui |  | miroir c0, repris |
| `AnalysisControl` | `escalade` | `escalade` | Escalade | oui |  | miroir c0, repris |
| `AnalysisControl` | `explanation` | `explanation` | String | oui |  | miroir c0, repris |
| `AnalysisControl` | `details` | `details` | Json | oui |  | miroir c0, repris |
| `AnalysisControl` | `missing` | `missing` | String[] | non |  | miroir c0, repris |
| `AnalysisControl` | `source` | `source` | String | non |  | miroir c0, repris |
| `AnalysisControl` | `computedAt` | `computedAt` | DateTime | non |  | miroir c0, repris |
| `AnalysisControl` | unicité (analysisId, controlId) | | | | unique | miroir c0, repris |
| `Reanalysis` | `id` | `id` | String | non | clé | miroir c0, repris |
| `Reanalysis` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `Reanalysis` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Reanalysis` | `analysisId` | `analysisId` | String | oui |  | miroir c0, repris |
| `Reanalysis` | `analysis` | — | Analysis | oui |  | relation, pas de colonne (jointure par la clé étrangère) |
| `Reanalysis` | `controlId` | `controlId` | String | non |  | miroir c0, repris |
| `Reanalysis` | `pieceId` | `pieceId` | String | oui |  | miroir c0, repris |
| `Reanalysis` | `requestedFields` | `requestedFields` | String[] | non |  | miroir c0, repris |
| `Reanalysis` | `status` | `status` | ReanalysisStatus | non |  | miroir c0, repris |
| `Reanalysis` | `attempts` | `attempts` | Int | non |  | miroir c0, repris |
| `Reanalysis` | `model` | `model` | String | oui |  | miroir c0, repris |
| `Reanalysis` | `costUsd` | `costUsd` | Float | oui |  | miroir c0, repris |
| `Reanalysis` | `result` | `result` | Json | oui |  | miroir c0, repris |
| `Reanalysis` | `error` | `error` | String | oui |  | miroir c0, repris |
| `Reanalysis` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `Reanalysis` | `completedAt` | `completedAt` | DateTime | oui |  | miroir c0, repris |
| `BlacklistEntry` | `id` | `id` | String | non | clé | miroir c0, repris |
| `BlacklistEntry` | `kind` | `kind` | BlacklistKind | non |  | miroir c0, repris |
| `BlacklistEntry` | `label` | `label` | String | non |  | miroir c0, repris |
| `BlacklistEntry` | `normalized` | `normalized` | String | non |  | miroir c0, repris |
| `BlacklistEntry` | `city` | `city` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `active` | `active` | Boolean | non |  | miroir c0, repris |
| `BlacklistEntry` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `BlacklistEntry` | `personne` | `personne` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `nom` | `nom` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `prenom` | `prenom` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `raisonSociale` | `raisonSociale` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `cin` | `cin` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `rc` | `rc` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `typeListe` | `typeListe` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `motif` | `motif` | String | oui |  | miroir c0, repris |
| `BlacklistEntry` | `source` | `source` | String | oui |  | miroir c0, repris |
| `Employeur` | `ice` | `ice` | String | non | clé | miroir c0, repris |
| `Employeur` | `noms` | `noms` | String[] | non |  | miroir c0, repris |
| `Employeur` | `vus` | `vus` | Int | non |  | miroir c0, repris |
| `Employeur` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `Employeur` | `updatedAt` | `updatedAt` | DateTime | non |  | miroir c0, repris |
| `Synthese` | `id` | `id` | String | non | clé | miroir c0, repris |
| `Synthese` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `Synthese` | `analysisId` | `analysisId` | String | non | unique | miroir c0, repris |
| `Synthese` | `vueEnsemble` | `vueEnsemble` | String | oui |  | miroir c0, repris |
| `Synthese` | `avisComplementaire` | `avisComplementaire` | String | oui |  | miroir c0, repris |
| `Synthese` | `points` | `points` | Json | oui |  | miroir c0, repris |
| `Synthese` | `status` | `status` | String | non |  | miroir c0, repris |
| `Synthese` | `error` | `error` | String | oui |  | miroir c0, repris |
| `Synthese` | `costUsd` | `costUsd` | Float | oui |  | miroir c0, repris |
| `Synthese` | `score` | `score` | Float | oui |  | miroir c0, repris |
| `Synthese` | `alerte` | `alerte` | Boolean | non |  | miroir c0, repris |
| `Synthese` | `noteeLe` | `noteeLe` | DateTime | oui |  | miroir c0, repris |
| `Synthese` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `Synthese` | `completedAt` | `completedAt` | DateTime | oui |  | miroir c0, repris |
| `Synthese` | `constats` | — | ConstatLibre | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `IndicateurDossier` | `id` | `id` | String | non | clé | miroir c0, repris |
| `IndicateurDossier` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `IndicateurDossier` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `IndicateurDossier` | `indicateur` | `indicateur` | String | non |  | miroir c0, repris |
| `IndicateurDossier` | `valeur` | `valeur` | Float | non |  | miroir c0, repris |
| `IndicateurDossier` | `source` | `source` | String | non |  | miroir c0, repris |
| `IndicateurDossier` | `details` | `details` | Json | oui |  | miroir c0, repris |
| `IndicateurDossier` | `updatedAt` | `updatedAt` | DateTime | non |  | miroir c0, repris |
| `IndicateurDossier` | unicité (dossierId, indicateur) | | | | unique | miroir c0, repris |
| `ConstatLibre` | `id` | `id` | String | non | clé | miroir c0, repris |
| `ConstatLibre` | `syntheseId` | `syntheseId` | String | non |  | miroir c0, repris |
| `ConstatLibre` | `synthese` | — | Synthese | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `ConstatLibre` | `dossierId` | `dossierId` | String | non |  | miroir c0, repris |
| `ConstatLibre` | `dossier` | — | Dossier | non |  | relation, pas de colonne (jointure par la clé étrangère) |
| `ConstatLibre` | `ordre` | `ordre` | Int | non |  | miroir c0, repris |
| `ConstatLibre` | `texte` | `texte` | String | non |  | miroir c0, repris |
| `ConstatLibre` | `indicateur` | `indicateur` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `valeurCitee` | `valeurCitee` | Float | oui |  | miroir c0, repris |
| `ConstatLibre` | `unite` | `unite` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `base` | `base` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `famille` | `famille` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `piece` | `piece` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `source` | `source` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `retenu` | `retenu` | Boolean | non |  | miroir c0, repris |
| `ConstatLibre` | `motifNonRetenu` | `motifNonRetenu` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `valeurCalculee` | `valeurCalculee` | Float | oui |  | miroir c0, repris |
| `ConstatLibre` | `rang` | `rang` | Float | oui |  | miroir c0, repris |
| `ConstatLibre` | `effectif` | `effectif` | Int | oui |  | miroir c0, repris |
| `ConstatLibre` | `force` | `force` | Int | oui |  | miroir c0, repris |
| `ConstatLibre` | `fiabilite` | `fiabilite` | Float | oui |  | miroir c0, repris |
| `ConstatLibre` | `score` | `score` | Float | oui |  | miroir c0, repris |
| `ConstatLibre` | `note` | `note` | String | oui |  | miroir c0, repris |
| `ConstatLibre` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `User` | `id` | `id` | String | non | clé | miroir c0, repris |
| `User` | `email` | `email` | String | non | unique | miroir c0, repris |
| `User` | `passwordHash` | `passwordHash` | String | non |  | miroir c0, repris |
| `User` | `fullName` | `fullName` | String | oui |  | miroir c0, repris |
| `User` | `role` | `role` | UserRole | non |  | miroir c0, repris |
| `User` | `createdAt` | `createdAt` | DateTime | non |  | miroir c0, repris |
| `LlmBudget` | `day` | `day` | DateTime (@db.Date) | non | clé | miroir c0, repris |
| `LlmBudget` | `costUsd` | `costUsd` | Float | non |  | miroir c0, repris |
| `LlmBudget` | `calls` | `calls` | Int | non |  | miroir c0, repris |

## Énumérations

Valeurs reprises telles quelles, sans traduction ni changement de casse (texte contrôlé dans le miroir).

| Énumération | Source | Valeurs | Remarque |
| --- | --- | --- | --- |
| `PersonType` | schema.prisma | PP, PM |  |
| `RiskCategory` | schema.prisma | A, B, C, D, E, NON_CLASSIFIABLE |  |
| `Criticality` | schema.prisma | MINEURE, MAJEURE, CRITIQUE, INFORMATION |  |
| `ControlOutcome` | schema.prisma | CONFORME, ANOMALIE, NON_EXECUTABLE, ERREUR_TECHNIQUE, NON_APPLICABLE |  |
| `FraudVerdict` | schema.prisma | CONFORME, OK_ALERTES_MINEURES, SUSPECT, TRES_SUSPECT |  |
| `AnalysisStatus` | schema.prisma | EN_ATTENTE_DONNEES, EN_COURS, COMPLETE, INCOMPLETE, EN_ERREUR | écart avec engine-core_types.ts : COMPLETE, INCOMPLETE, EN_ERREUR |
| `IntakeKind` | schema.prisma | BUSINESS_DATA, TANDEM_RESULTS, PDF |  |
| `ExtractionSource` | schema.prisma | AMONT, REANALYSE |  |
| `AnalysisTrigger` | schema.prisma | INTAKE, REANALYSE, REPLAY |  |
| `ReanalysisStatus` | schema.prisma | PENDING, RUNNING, DONE, FAILED |  |
| `UserRole` | schema.prisma | ANALYST, ADMIN, SUPERADMIN |  |
| `BlacklistKind` | schema.prisma | CLIENT, EMPLOYEUR, GERANT, BENEFICIAIRE, TIERS_BANCAIRE, ZONE |  |
| `Escalade` | schema.prisma | CONSEILLER_CLIENTELE, DIRECTEUR_AGENCE, CELLULE_FRAUDES |  |
| `DossierStatus` | web_types.ts | EN_ATTENTE_DONNEES, EN_COURS, COMPLETE, INCOMPLETE, EN_ERREUR | absente de schema.prisma (texte libre en base) |
| `Verdict` | engine-core_types.ts | CONFORME, OK_ALERTES_MINEURES, SUSPECT, TRES_SUSPECT | absente de schema.prisma (texte libre en base) |
| `ControlFamily` | engine-core_types.ts | IDENTITE, EMPLOI_REVENUS, BANCAIRE, AUTOMOBILE, PM_PRO, BLACKLIST_GEO | absente de schema.prisma (texte libre en base) |
| `PieceType` | engine-core_types.ts | CIN, ATTESTATION_TRAVAIL_SALAIRE, BULLETIN_DE_PAIE, ATTESTATION_PENSION, ATTESTATION_CNSS, RELEVE_BANCAIRE, ATTESTATION_RIB, REGISTRE_COMMERCE, STATUTS, PV_ASSEMBLEE_GENERALE, FACTURE_PROFORMA_VEHICULE, CARTE_GRISE, CARTE_PROFESSIONNELLE, DOMICILIATION | absente de schema.prisma (texte libre en base) |
| `Applicability` | engine-core_types.ts | OUI, NON, SELON_PROFIL, SELON_PIECES, SI_AUTO, SI_REQUIS, SI_RETRAITE, SI_STATUTS | absente de schema.prisma (texte libre en base) |
| `ProductFamily` | engine-core_types.ts | AUTO, NON_AUTO | absente de schema.prisma (texte libre en base) |
| `PaymentMode` | engine-core_types.ts | PRELEVEMENT_SOURCE, PRELEVEMENT_BANCAIRE | absente de schema.prisma (texte libre en base) |
| `Csp` | engine-core_types.ts | FONCTIONNAIRE, EMPLOYE_COMMUNE, MILITAIRE, SALARIE_PRIVE, RETRAITE_PUBLIC, RETRAITE_CIMR, RETRAITE_INDETERMINE, PROFESSION_LIBERALE, LOUEUR, SOCIETE, AUTRE | absente de schema.prisma (texte libre en base) |

## Types d'échange → modèles d'échange, générateur et collecteur

| Interface | Source | Champs | Destination |
| --- | --- | --- | --- |
| `Dossier` | web_types.ts | 25 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `DossiersResponse` | web_types.ts | 3 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `Piece` | web_types.ts | 6 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `AnalysisControl` | web_types.ts | 16 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `AnalysisSummary` | web_types.ts | 10 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `ReanalysisInfo` | web_types.ts | 7 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `LatestAnalysis` | web_types.ts | 11 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `BusinessData` | web_types.ts | 3 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `ConstatLibre` | web_types.ts | 18 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `ConstatHorsControles` | web_types.ts | 6 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `Synthese` | web_types.ts | 10 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `DossierDetail` | web_types.ts | 31 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `Monitoring` | web_types.ts | 5 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `BlacklistEntry` | web_types.ts | 6 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `LoginResponse` | web_types.ts | 3 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `ControlDefinition` | engine-core_types.ts | 22 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `CategorizationInput` | engine-core_types.ts | 4 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `CategorizationResult` | engine-core_types.ts | 3 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `ControlResultInput` | engine-core_types.ts | 5 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `VerdictResult` | engine-core_types.ts | 4 | modèle d'échange (pydantic), générateur et serveur v2 fictifs (étape C), collecteur (étape D) |
| `OnAnomaly` | engine-core_types.ts | — | alias repris tel quel dans les modèles d'échange |

## Vocabulaire amont → moteur (README § 4) → `ref_cle_canonique`

La clé canonique d'un fait est la clé moteur (colonne de droite).

| Clés amont | Clé moteur | Précision |
| --- | --- | --- |
| `nom_societe` | `denomination_sociale` |  |
| `siege_social` | `adresse_siege` |  |
| `capital` | `capital_social` |  |
| `forme_juridique` | `type_statuts` | statuts |
| `tribunal_commerce` | `ville_tribunal` |  |
| `numero_ice` | `ice` |  |
| `objet_commerce` | `objet_social` |  |
| `date_emission` | `date_generation_document` |  |
| `date_immatriculation`, `date_debut` | `date_creation` |  |
| `dirigeants` | `gerants` |  |
| `nom_gerant+prenom_gerant`, `nom+prenom` | `nom_complet` |  |
| `numero_cin`, `numero_cin_gerant` | `cin` |  |
| `id_document_recto` | `cin` | CIN |
| `nom_prenom`, `raison_sociale` | `titulaire_compte` |  |
| `rib` | `numero_compte` | relevé |

## Tables enfants proposées (README § 7) → c1 (étape E)

| Table | Destination |
| --- | --- |
| `releve_mois` | c1, nom et clés repris |
| `releve_operation` | c1, nom et clés repris |
| `societe_personne` | c1, nom et clés repris |

<!-- FIN PARTIE GENEREE -->
