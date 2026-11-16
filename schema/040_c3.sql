-- Couche 3 : la fiche du dossier et les incohérences. Les tables propres à un dossier (en-tête, revenus, charges,
-- comptes, opérations, véhicules, clés, incohérences entre ses pièces) se réécrivent dossier par dossier depuis le
-- miroir, c1 et c2. Ce qui croise les dossiers ou le registre (parties, double financement, RIB vu ailleurs,
-- dossiers en rafale, employeur absent du registre) est une vue : toujours à jour, au fil de l'eau comme en lot.
-- Les 55 contrôles de la v2 ne sont pas recalculés : ils se lisent dans le miroir ("AnalysisControl").

-- En-tête au format du modèle `Dossier` de Kamal (ses champs, sous ses noms), plus le contexte `businessData` mis à
-- plat. Colonnes prévues, vides tant que la v2 ne les envoie pas : montant, durée, apport, mensualité, statut final.
CREATE TABLE c3_dossier (
    ref                  TEXT PRIMARY KEY,
    id                   TEXT NOT NULL,
    "personType"         TEXT,
    csp                  TEXT,
    "productType"        TEXT,
    "paymentMode"        TEXT,
    "clientName"         TEXT,
    agence               TEXT,
    canal                TEXT,
    category             TEXT,
    verdict              TEXT,
    "verdictProvisional" INTEGER,
    "analysisStatus"     TEXT,
    actif                INTEGER,
    "businessReceivedAt" TEXT,
    "createdAt"          TEXT,
    "updatedAt"          TEXT NOT NULL,
    en_cours             INTEGER NOT NULL CHECK (en_cours IN (0, 1)),   -- analyse non terminée : ni contrôle ni alerte
    jour                 INTEGER,                                       -- jours depuis le 01/01/1970 (réception)
    cin_declare          TEXT,
    nom_declare          TEXT,
    adresse_declaree     TEXT,
    employeur_declare    TEXT,
    employeur_declare_defaut INTEGER NOT NULL CHECK (employeur_declare_defaut IN (0, 1)),
    revenu_declare       DOUBLE PRECISION,
    organisme_pension_declare TEXT,
    client_connu         INTEGER,
    agence_code          TEXT,
    agence_ville         TEXT,
    montant_demande      DOUBLE PRECISION,
    duree_mois           INTEGER,
    apport               DOUBLE PRECISION,
    mensualite           DOUBLE PRECISION,
    statut_final         TEXT
);

-- Revenu déclaré (contexte EQDOM) ou vérifié (bulletin, attestation, pension, salaire repéré sur le relevé), avec
-- sa pièce. `releve_relu` : le mois du relevé porte des opérations lues (sinon l'agrégat vient de l'amont seul).
CREATE TABLE c3_revenu (
    ref               TEXT NOT NULL,
    nature            TEXT NOT NULL CHECK (nature IN ('declare', 'verifie')),
    source            TEXT NOT NULL,
    upstream_piece_id TEXT,
    repere            TEXT NOT NULL,
    annee             INTEGER,
    mois              INTEGER,
    montant           DOUBLE PRECISION NOT NULL,
    releve_relu       INTEGER,
    piece             TEXT NOT NULL,          -- pièce du revenu ; « businessData » pour le revenu déclaré
    PRIMARY KEY (ref, piece, repere)
);

CREATE TABLE c3_charge (
    ref               TEXT NOT NULL,
    nature            TEXT NOT NULL CHECK (nature IN ('echeance_releve', 'credit_source')),
    upstream_piece_id TEXT NOT NULL,
    repere            TEXT NOT NULL,
    annee             INTEGER,
    mois              INTEGER,
    montant           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (ref, upstream_piece_id, repere)
);

CREATE TABLE c3_compte (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type_piece        TEXT NOT NULL,
    rib               TEXT NOT NULL,
    banque            TEXT,
    titulaire         TEXT,
    PRIMARY KEY (ref, upstream_piece_id, rib)
);

-- Opérations lues d'un relevé (jamais une ligne reconstituée par l'amont), avec le type d'opération et la
-- contrepartie tirés du libellé : un indice, jamais une identité.
CREATE TABLE c3_operation (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    rang_mois         INTEGER NOT NULL,
    rang              INTEGER NOT NULL,
    date_operation    TEXT,
    date_operation_brute TEXT,
    libelle           TEXT,
    debit             DOUBLE PRECISION,
    credit            DOUBLE PRECISION,
    type_operation    TEXT NOT NULL CHECK (type_operation IN ('virement', 'prelevement', 'carte', 'cheque', 'especes', 'frais', 'autre')),
    contrepartie      TEXT,
    PRIMARY KEY (ref, upstream_piece_id, rang_mois, rang)
);

CREATE TABLE c3_vehicule (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type_piece        TEXT NOT NULL,
    chassis           TEXT,
    immatriculation   TEXT,
    marque            TEXT,
    modele            TEXT,
    etat              TEXT,
    prix              DOUBLE PRECISION,
    PRIMARY KEY (ref, upstream_piece_id)
);

-- Identifiants par lesquels un dossier peut en croiser un autre : RIB, châssis, adresse déclarée (normalisée).
CREATE TABLE c3_cle_dossier (
    ref               TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN ('RIB', 'CHASSIS', 'ADRESSE')),
    valeur            TEXT NOT NULL,
    upstream_piece_id TEXT,
    jour              INTEGER,
    PRIMARY KEY (ref, type, valeur)
);
CREATE INDEX c3_cle_dossier_valeur_idx ON c3_cle_dossier (type, valeur);

-- Incohérence entre deux pièces d'un même dossier, avec ses deux faits (pièce et repère dans la pièce).
CREATE TABLE c3_incoherence_locale (
    ref                 TEXT NOT NULL,
    type                TEXT NOT NULL CHECK (type IN ('salaire_bulletin_releve', 'adresse_cin_differente')),
    upstream_piece_id_a TEXT NOT NULL,
    repere_a            TEXT NOT NULL,
    upstream_piece_id_b TEXT NOT NULL,
    repere_b            TEXT NOT NULL,
    PRIMARY KEY (ref, type, upstream_piece_id_a, repere_a, upstream_piece_id_b, repere_b)
);

-- Rôle de chaque fiche dans le dossier. `demandeur` : la fiche qui porte le CIN déclaré (à défaut, le titulaire de
-- la CIN) ; pour une personne morale, la société du dossier.
CREATE VIEW c3_partie_dossier AS
SELECT m.ref, m.fiche, m.type_fiche, m.role,
       max(CASE WHEN d."personType" = 'PM' THEN CASE WHEN m.type_fiche = 'PM' AND m.role = 'societe' THEN 1 ELSE 0 END
                WHEN d.cin_declare IS NOT NULL THEN CASE WHEN m.cin_effectif = d.cin_declare THEN 1 ELSE 0 END
                WHEN m.role = 'titulaire_cin' AND m.rang = 0 THEN 1 ELSE 0 END) AS demandeur,
       count(*) AS nb_mentions
FROM c2_mention m JOIN c3_dossier d ON d.ref = m.ref
WHERE m.source = 'v2' AND m.fiche IS NOT NULL
GROUP BY m.ref, m.fiche, m.type_fiche, m.role;

-- Toutes les incohérences et tous les signaux d'un dossier. `gravite` : incoherence, ou signal (à part, sans effet
-- sur la force). Chaque ligne pointe ses deux faits : (pièce, repère) du dossier, et (dossier, pièce, repère) en face.
CREATE VIEW c3_incoherence AS
SELECT ref, type, 'incoherence' AS gravite, upstream_piece_id_a, repere_a, ref AS ref_b, upstream_piece_id_b, repere_b
FROM c3_incoherence_locale
UNION ALL
-- même châssis dans deux dossiers : double financement
SELECT a.ref, 'double_financement', 'incoherence', a.upstream_piece_id, 'CHASSIS', b.ref, b.upstream_piece_id, 'CHASSIS'
FROM c3_cle_dossier a JOIN c3_cle_dossier b ON b.type = a.type AND b.valeur = a.valeur AND b.ref <> a.ref
WHERE a.type = 'CHASSIS'
UNION ALL
-- même RIB dans un autre dossier, sans aucune fiche commune parmi ses porteurs
SELECT a.ref, 'rib_autre_dossier', 'incoherence', a.upstream_piece_id, 'RIB', b.ref, b.upstream_piece_id, 'RIB'
FROM c3_cle_dossier a JOIN c3_cle_dossier b ON b.type = a.type AND b.valeur = a.valeur AND b.ref <> a.ref
WHERE a.type = 'RIB' AND NOT EXISTS (
    SELECT 1 FROM c2_identifiant ia JOIN c2_identifiant ib ON ib.fiche = ia.fiche
    WHERE ia.type = 'RIB' AND ia.valeur = a.valeur AND ia.ref = a.ref
      AND ib.type = 'RIB' AND ib.valeur = a.valeur AND ib.ref = b.ref)
UNION ALL
-- dossiers en rafale : le même RIB ou la même adresse dans N dossiers reçus dans une fenêtre de J jours
SELECT a.ref, 'dossiers_en_rafale', 'signal', a.upstream_piece_id, a.type, NULL, NULL, NULL
FROM c3_cle_dossier a
WHERE a.type IN ('RIB', 'ADRESSE') AND a.jour IS NOT NULL AND EXISTS (
    SELECT 1 FROM c3_cle_dossier s
    WHERE s.type = a.type AND s.valeur = a.valeur AND s.jour <= a.jour
      AND a.jour < s.jour + (SELECT valeur FROM parametre WHERE nom = 'c3_rafale_jours')
      AND (SELECT count(DISTINCT f.ref) FROM c3_cle_dossier f
           WHERE f.type = s.type AND f.valeur = s.valeur AND f.jour >= s.jour
             AND f.jour < s.jour + (SELECT valeur FROM parametre WHERE nom = 'c3_rafale_jours'))
          >= (SELECT valeur FROM parametre WHERE nom = 'c3_rafale_dossiers'))
UNION ALL
-- employeur identifié (ICE ou RC + tribunal) que le registre chargé ne connaît pas
SELECT m.ref, 'employeur_absent_du_registre', 'signal', m.upstream_piece_id, m.role, NULL, NULL, NULL
FROM c2_mention m
WHERE m.source = 'v2' AND m.role = 'employeur' AND m.fiche IS NOT NULL AND (m.ice IS NOT NULL OR m.rc_cle IS NOT NULL)
  AND EXISTS (SELECT 1 FROM c2_mention r WHERE r.source = 'registre')
  AND NOT EXISTS (SELECT 1 FROM c2_mention r WHERE r.source = 'registre' AND r.fiche = m.fiche);
