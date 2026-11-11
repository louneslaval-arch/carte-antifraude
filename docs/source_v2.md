# La v2 de Kamal : source des dossiers et règles d'alignement

SEVEN · réseaux de fraude EQDOM · 11/11/2026 · d'après le lot `antifraude_json_back_front_2026-11-11` (types, schéma Prisma, contrats, inventaire des clés de production). Aucune donnée personnelle : seulement des noms de clés, des formes et des comptages. La source de vérité reste les fichiers de Kamal (`reference/v2/` ou `import/kamal_structure/`) ; ce document dit comment les lire et comment s'y aligner.

## 1. Le lot de structure de Kamal

| Fichier | Contenu | Sert à |
| --- | --- | --- |
| `schema/schema.prisma` | modèle de stockage de la v2 (PostgreSQL) | miroir de la couche 0, généré ; carte de correspondance |
| `schema/openapi_api_v1_export_metier.json` | OpenAPI de l'export métier `/api/v1` | savoir ce qu'il ne contient pas (aucun champ extrait) |
| `types/web_types.ts` | ce que l'interface web de la v2 consomme : `DossierDetail`, `Piece`… | modèles d'échange, générateur, serveur fictif, collecteur |
| `types/engine-core_types.ts` | types et énumérations du moteur | valeurs d'énumération, format des contrôles |
| `reference/champs_par_type_prod.csv` | inventaire des clés de `fields` par type de pièce et par source, en production (colonnes `type`, `source`, `key`, `n`, `non_null`, `types_json`) | clés canoniques ; répartition des clés du générateur |
| `reference/business-data.schema.json`, `reference/tandem-results.schema.json` | schémas JSON du flux amont (EQDOM, Tandem AI) | `IntakeMessage`, le jour où il est accessible |
| `reference/CONTRAT_TANDEM_AI.md` | contrat du flux amont | règles de lecture de l'amont |
| `README.md` | un dossier = un objet ; données extraites dans `pieces[]` ; § 4 : correspondance des deux vocabulaires de clés ; § 7 « pour faire la base » : `Dossier` → `Piece` avec `fields` en JSON, tables enfants pour les opérations et les personnes | `ref_cle_canonique` (§ 4) ; structure de c1 (§ 7) |
| `api/` | vraies réponses de l'API sur la préproduction | **jamais dans le dépôt, jamais dans Claude Code** |

## 2. Les trois niveaux d'objets

| Niveau | Où | Contenu | Utile pour la base |
| --- | --- | --- | --- |
| Entrée amont | `IntakeMessage` (JSON brut, un enregistrement par réception ; 19 794 en préproduction) ; schémas `business-data` et `tandem-results` | `business.json` (contexte EQDOM : CSP, produit, mode de paiement, état civil déclaré, revenu déclaré, agence) et `tandem_results.json` (pièces, `upstream_controls[]`, `consolidated` identité, emploi, comptes) | oui : contient `quality`, `sha256` et `upstream_controls`, que l'API n'expose pas |
| Dossier analysé | `GET /api/dossiers/:ref` → `DossierDetail` | en-tête, `businessData`, `pieces[]` (les valeurs extraites), `analyses[]`, `reanalyses[]`, `synthese`, `latestAnalysis.controls[]` | oui : la source principale |
| Export métier | `GET /api/v1/dossiers/:ref` (OpenAPI) | verdict, catégorie, lecture rédigée, 55 contrôles ; `pieces[]` réduit à identifiant, type, exploitable | non pour les données : aucun champ extrait |

La base se nourrit de `GET /api/dossiers/:ref`, ou directement des tables PostgreSQL de la v2 (`Piece`, `IntakeMessage`, `AnalysisControl`, `IndicateurDossier`…), jamais de `/api/v1`.

## 3. Le dossier (`DossierDetail`)

```
Dossier ─┬─ en-tête : ref, personType (PP|PM), csp, productType (DISPO|AUTO_CLASSIQUE|LOA), paymentMode,
         │            clientName, agence, canal, category (A..E), verdict, alertes, dates
         ├─ businessData   contexte amont tel que reçu (civil, declared, known_client, in_production, agency)
         ├─ pieces[]       les données : une entrée par pièce, fields = objet clé → valeur propre au type
         ├─ analyses[]     historique (trigger INTAKE | REANALYSE | REPLAY ; status, verdict, matrixVersion, engineVersion)
         ├─ reanalyses[]   relectures (controlId, pieceId, requestedFields, status, result.avant, result.apres,
         │                 createdAt, completedAt)
         ├─ synthese       texte rédigé + constats notés (indicateur, valeur, rang, effectif, force, fiabilité, score) ;
         │                 clés observées : points, constats, constatsHorsControles
         └─ latestAnalysis.controls[55]  controlId, numeroMetier, family, label, source, outcome (dont ANOMALIE,
                                         NON_EXECUTABLE), criticality, escalade, details (valeurs comparées), missing,
                                         previousOutcome
```

Autres formes relevées : la liste `GET /api/dossiers` rend `{items, total, counts}`, chaque élément portant au moins `ref`, `updatedAt` et `analysisStatus` ; le détail d'un contrôle se lit par `GET /api/dossiers/:ref/controls/:controlId` ; la v2 a une route de suivi `GET /api/admin/monitoring`. Ces noms ont été relevés en profilant le lot le 11/11 : les types de Kamal font foi.

Deux dossiers d'exemple du lot : une PM en LOA, catégorie E, très suspecte (6 pièces, 22 analyses dont 16 rejeux, 7 relectures, 4 anomalies dont 1 critique) ; une PP retraitée du public en DISPO, catégorie A, conforme (3 pièces, 47 contrôles sur 55 non applicables). `agence` et `canal` sont vides sur les deux, et sur toute la liste de préproduction (820 dossiers actifs) : l'amont ne les envoie pas encore.

## 4. `pieces[]` : comment les valeurs sont rangées

Une pièce = `{ upstreamPieceId, type, source, extractionStatus, pdfPath, fields }`, unique sur (dossier, `upstreamPieceId`).

- `upstreamPieceId` : vocabulaire EQDOM (`eqdom_CIN`, `eqdom_releves_comptes`, `eqdom_modele_J`, `eqdom_statut`, `eqdom_facture_proforma`, `eqdom_quittance_eau`…, suffixes `_1`, `_2`) ; `type` : vocabulaire du moteur (14 types).
- `source` : `AMONT` (lu par Tandem AI) ou `REANALYSE` (relu par la v2). La relecture remplace la pièce : `fields` est alors la fusion (valeurs relues prioritaires, clés amont conservées). La provenance n'est pas connue champ par champ ; seul `reanalyses[].result.avant / apres` dit quels champs ont été relus.
- Ni confiance par champ, ni page, ni zone : `extractionStatus` (OK, PARTIAL, FAILED) vaut pour toute la pièce.

**Volumes de production** (4 250 dossiers, inventaire `champs_par_type_prod.csv`) :

| Type | Pièces | Part relue | Clés utiles pour la base |
| --- | ---: | ---: | --- |
| CIN | 3 963 | 59 % | cin, nom, prénom, date de naissance (98 %), date d'expiration, sexe, filiation, nom du père et de la mère (≈ 80 %), adresse (≈ 90 %), MRZ complète |
| RELEVE_BANCAIRE | 3 105 | 39 % | rib ou numero_compte (≈ 90 %), banque, titulaire ; `mois[]` ; agrégats mensuels amont : total crédit et débit, solde de fin de période, montant_salaire (≈ 80 %), montant_echeances_credits (≈ 80 %) |
| REGISTRE_COMMERCE | 1 389 | 49 % | numero_analytique (n° RC), tribunal_commerce ou ville_tribunal, ice, date d'immatriculation, siège, capital, objet, `gerants[]`, `dirigeants[]` (avec CIN, date de naissance, nationalité, adresse) |
| ATTESTATION_TRAVAIL_SALAIRE | 1 178 | 28 % | employé (nom, CIN, matricule, fonction), employeur, adresse de l'employeur, n° CNSS (63 %), date d'embauche (63 %), type de contrat, salaire net (60 % seulement) |
| STATUTS | 1 043 | 49 % | dénomination, forme, capital, siège, `gerants[]`, `associes[]` (parts, CIN, date de naissance, nationalité, résidence) |
| ATTESTATION_RIB | 1 027 | 3 % | rib, banque, titulaire |
| DOMICILIATION (quittances) | 927 | 7 % | adresse, ville, titulaire, mois d'émission, montant |
| ATTESTATION_PENSION | 613 | 4 % | caisse, organisme, n° de pension, CIN, montant net |
| BULLETIN_DE_PAIE | 540 | 50 % | employeur, n° d'affiliation de l'employeur, n° CNSS, matricule, CIN, rib (99 %), credits_source (99 %), rémunération (brut, net, base CNSS), situation familiale, personnes à charge |
| FACTURE_PROFORMA_VEHICULE | 484 | 16 % | marque, modèle, version, état (neuf ou occasion), prix HT et TTC, avance, concessionnaire, vendeur, acheteur |
| CARTE_GRISE | 203 | 44 % | numéro de châssis, immatriculation, marque, modèle, première mise en circulation, puissance, carburant (clés en libellés français : « Numéro de chassis ») |
| CARTE_PROFESSIONNELLE | 179 | 9 % | n° d'inscription, INPE, profession, secteur, validité |
| ATTESTATION_CNSS | 171 | 49 % | n° CNSS, employeur actuel, `historique[]` (employeur, début, fin, salaire déclaré) |

Ces treize types totalisent 14 822 pièces (environ 3,5 par dossier) ; le quatorzième type du moteur, absent de la production, est à lire dans les types de Kamal.

**Listes dans `fields`** : `mois[]` (relevé), `gerants[]` et `dirigeants[]` (RC), `gerants[]` et `associes[]` (statuts), `associes_presents[]`, `nouveau_gerant[]`, `resolutions[]` (procès-verbal d'assemblée), `historique[]` (CNSS), `cartes[]` (CIN multiple), plus des objets imbriqués (`employeur`, `employe`, `remuneration`, `vehicule`, `prix`, `vendeur`, `acheteur`, `pensionne`, `assure`).

## 5. Les pièges relevés

1. **Opérations bancaires.** Les lignes réelles (`date_operation`, `date_valeur`, `libelle`, `debit`, `credit`) n'existent que si le relevé a été relu, soit 39 % des relevés. Les dates sont au format `jj/mm` sans année : l'année vient de `mois[].annee`. Sur un relevé amont, `mois[].operations` contient une seule ligne par mois, sans date, reconstituée par l'amont (le salaire ou la pension repéré) : ce n'est pas une opération lue. Le tiers d'une opération n'existe pas comme champ : c'est le libellé.
2. **Trois vocabulaires dans les clés.** Amont (`nom_societe`, `siege_social`, `numero_cin_gerant`…), moteur (`denomination_sociale`, `adresse_siege`, `cin`…) et libellés français de la carte grise (« Numéro de chassis », « Immatriculation »). Après relecture, les deux premiers cohabitent dans la même pièce.
3. **Clés pointées et objets imbriqués en double.** `vehicule.marque` (clé plate) coexiste avec `vehicule: { marque }` ; de même `prix.prix_total_ttc`, `employeur.raison_sociale`, `remuneration.salaire_net`.
4. **Clés inventées par la relecture.** `remeration.salaire_net`, `revelation.salaire_brut` (bulletin, attestation), et des champs de CIN (`filiation_complete`, `date_expiration`, `cin`) apparus sur des RIB, des quittances, des cartes professionnelles. Taux faibles, mais à filtrer par une liste d'exclusion par type.
5. **Types mêlés.** Montants tantôt nombre, tantôt texte (« 30 000,00 ») ; agrégats mensuels tantôt objet `{"MM/AAAA": valeur}`, tantôt texte ; dates en `jj/mm/aaaa`.
6. **Contexte amont partiel.** `businessData.civil.cin` vide pour une PM ; `declared` (employeur, revenu, caisse) vide sur la PM d'exemple ; employeur déclaré « VAB » sur tous les dossiers observés (valeur par défaut) ; CSP « Retraité » indistincte. Le revenu déclaré ne peut pas encore servir de comparaison.
7. **`raison_sociale`** signifie « titulaire du compte » sur un relevé et « société » ailleurs : la correspondance des clés est propre à chaque type de pièce.

## 6. Ce que la base PostgreSQL de la v2 contient et que l'API n'expose pas

`Piece.sha256` ; `IntakeMessage` (brut amont avec `quality.legible` et `upstream_controls`) ; `IndicateurDossier` (indicateurs calculés par le moteur, chacun avec une fiabilité CERTAINE, EXTRAITE ou FRAGILE) ; `Employeur` (référentiel par ICE, avec toutes les graphies lues) ; `BlacklistEntry` (liste noire structurée : CLIENT, EMPLOYEUR, GERANT, BENEFICIAIRE, TIERS_BANCAIRE, ZONE).

## 7. Règles d'alignement sur la structure de Kamal

### 7.1 Le miroir (couche 0)

- Une table par modèle de `schema.prisma` que la carte reçoit ou recevra ; noms de tables et de colonnes tels que PostgreSQL les voit dans la base de la v2 (après `@map` et `@@map`), entre guillemets dans le SQL quand la casse l'exige ; mêmes clés primaires et contraintes d'unicité ; énumérations rangées en texte avec un contrôle des valeurs permises ; champs JSON en `jsonb` sur PostgreSQL et en texte sur SQLite.
- Généré par `outils/v2/` depuis `schema.prisma` (une migration par lot de structure), jamais écrit à la main ; un test vérifie que le miroir contient chaque modèle et chaque champ, et rien d'autre.
- Prototype : rempli depuis `DossierDetail` pour ce que l'API expose (dossier, pièces, analyses, relectures, contrôles) ; les modèles que l'API n'expose pas sont créés vides. Production : rempli par lecture directe des tables de Kamal, sans transformation.
- Ce que `DossierDetail` porte et que `schema.prisma` n'a pas reste dans la version brute (`c0_dossier_brut`) et est noté dans la carte de correspondance.

### 7.2 Les modèles d'échange

- `DossierDetail` et les objets qu'il contient, ainsi que la liste des dossiers, sont décrits en Python (modèles pydantic) d'après `web_types.ts`, champ par champ, facultatifs et listes compris. Le collecteur, le générateur et le serveur fictif les emploient ; un test compare les modèles aux types de Kamal.

### 7.3 Les énumérations

Valeurs reprises telles quelles des types de Kamal, sans traduction : `personType` (PP, PM), `productType` (DISPO, AUTO_CLASSIQUE, LOA), `category` (A à E), `source` (AMONT, REANALYSE), `extractionStatus` (OK, PARTIAL, FAILED), `trigger` (INTAKE, REANALYSE, REPLAY), fiabilité d'indicateur (CERTAINE, EXTRAITE, FRAGILE), types de `BlacklistEntry` (CLIENT, EMPLOYEUR, GERANT, BENEFICIAIRE, TIERS_BANCAIRE, ZONE), `outcome` et `criticality` des contrôles, les 14 types de pièces. Les listes complètes se lisent dans `engine-core_types.ts`.

### 7.4 Le vocabulaire des faits

- La clé canonique d'un fait est la clé « moteur » de la v2. `ref_cle_canonique` (type de pièce, clé brute → clé moteur) part de la correspondance du README de Kamal (§ 4), complétée par les libellés français de la carte grise et la liste d'exclusion des clés inventées.
- Toute clé de l'inventaire de production a une clé canonique ou figure au rapport des clés inconnues.

### 7.5 La couche 1 selon le README de Kamal

- `Piece` garde `fields` tel quel (dans le miroir) ; les tables enfants que propose le README (§ 7 : opérations et personnes) prennent ses noms et ses clés.
- Nos ajouts (faits normalisés, mois de relevé, mentions de sociétés, identifiants bruts) portent nos noms, chacun justifié dans la carte de correspondance.

### 7.6 Liste noire et employeurs

- La liste noire d'EQDOM (référence du 03/08/2026) est rangée dans la structure de `BlacklistEntry` (types et champs de Kamal), plus le statut daté actif ou retiré de la décision n°4 s'il manque ; quand sa table devient accessible, un rapport d'écart compare les deux.
- Les employeurs suivent la clé et la structure du référentiel `Employeur` (ICE, graphies lues), qui devient une source dès l'accès direct.

### 7.7 Ce qui retourne à la v2 et à Tandem

- Le contrôle « lien avec la liste noire » est rendu comme un élément de `controls[]` (mêmes champs, mêmes énumérations ; identifiant, famille et correspondance des niveaux convenus avec Kamal), le détail des chemins dans son champ de détails ; les mesures au format d'`IndicateurDossier`.
- Les routes échangées avec la v2 (notification, relève des contrôles) suivent les conventions de son API : noms de champs, pagination `limit` et `offset`, réponses `{items, total}`.

### 7.8 Ce que la v2 n'a pas (nos ajouts)

Registre du commerce (annonces légales, personnes citées), fiches maîtres et homonymies, levées, graphe et chemins, contrôle réseau et alertes, époques et modifications de la carte, journal d'audit, statistiques. Leurs tables portent nos noms, en français.

### 7.9 Quand la structure de Kamal change

Nouveau lot → import contrôlé (garde, aucun dossier `api/`) → `PROVENANCE.md` mis à jour → carte de correspondance et migrations du miroir régénérées → test de dérive relu → rapport d'écart. Rien ne change dans les couches au-dessus tant que la carte de correspondance n'a pas été relue par Lounès.

## 8. Demandes à Kamal

1. Un accès en lecture (ou une extraction) des tables `Piece`, `IntakeMessage`, `IndicateurDossier`, `Employeur`, `BlacklistEntry`, `AnalysisControl` plutôt que l'API page à page.
2. Garder la provenance par champ lors de la fusion (`fields_source: { clé: AMONT | REANALYSE }`) et la confiance de lecture quand le modèle la donne.
3. Faire passer tous les relevés en lignes d'opérations (aujourd'hui 39 %), ou au minimum marquer la ligne mensuelle reconstituée par l'amont.
4. Ajouter l'année aux dates d'opération, unifier le type des montants, sortir les libellés français de la carte grise vers le vocabulaire moteur.
5. Filtrer à la source les clés inventées (`remeration.*`, `revelation.*`, champs de CIN hors CIN).
6. Transmettre agence, canal, montant demandé, durée, apport, mensualité, statut final.
7. Accepter que sa structure (sans `api/`) soit versionnée dans le dépôt, et envoyer un nouveau lot à chaque changement de `schema.prisma` ou des types.
8. Réserver l'identifiant, la famille et l'échelle de criticité du contrôle « lien avec la liste noire » dans la matrice de la v2.
