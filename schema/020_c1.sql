-- Couche 1 : chaque valeur lue dans une pièce devient une ligne, normalisée, avec son origine.
-- Source : le miroir (fields de "Piece", "Reanalysis"), jamais la réponse d'API. Tables reconstruites entièrement
-- depuis la couche 0. Une pièce se désigne comme chez Kamal : (ref du dossier, upstreamPieceId).
-- Les noms `releve_mois`, `releve_operation` et `societe_personne` sont ceux que propose le README de Kamal (§ 7),
-- avec ses colonnes ; ils portent le préfixe de la couche.

-- Clé brute → clé moteur de la v2, par type de pièce (« * » : tous les types). Saisie depuis le README de Kamal
-- (pipeline/normalisation/cles.py), versionnée ; survit aux reconstructions.
CREATE TABLE ref_cle_canonique (
    type_piece TEXT NOT NULL,
    cle_brute  TEXT NOT NULL,
    cle_moteur TEXT NOT NULL,
    version    TEXT NOT NULL,
    PRIMARY KEY (type_piece, cle_brute)
);

-- Une pièce, et la version du dossier d'où elle est lue (updatedAt).
CREATE TABLE c1_piece (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type              TEXT NOT NULL,
    source            TEXT,
    extraction_status TEXT,
    version           TEXT NOT NULL,
    nb_champs         INTEGER NOT NULL,
    nb_champs_relus   INTEGER NOT NULL,
    PRIMARY KEY (ref, upstream_piece_id)
);

-- Une valeur d'une pièce. `cle` est la clé canonique (moteur) ; `cle_connue` vaut 0 quand la clé brute n'est pas
-- dans ref_cle_canonique. Origine : amont, relue_ciblee (champ demandé à la relecture), fusion (pièce relue : valeur
-- relue ou clé amont gardée, indiscernables). Tout statut autre que « normal » sort des règles d'identité.
CREATE TABLE c1_fait (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type              TEXT NOT NULL,
    cle_brute         TEXT NOT NULL,
    cle               TEXT NOT NULL,
    valeur            TEXT,
    texte_norm        TEXT,
    nombre            DOUBLE PRECISION,
    date              TEXT,
    origine           TEXT NOT NULL CHECK (origine IN ('amont', 'relue_ciblee', 'fusion')),
    statut            TEXT NOT NULL CHECK (statut IN ('normal', 'cle_inventee', 'champ_cin_hors_cin', 'gabarit')),
    cle_connue        INTEGER NOT NULL CHECK (cle_connue IN (0, 1))
);
CREATE INDEX c1_fait_ref_idx ON c1_fait (ref, upstream_piece_id);
CREATE INDEX c1_fait_cle_idx ON c1_fait (type, cle);

-- Une valeur par pièce et par clé canonique : relue ciblée, puis fusion, puis amont ; à origine égale, la clé déjà
-- écrite dans le vocabulaire moteur, puis une valeur non vide.
CREATE VIEW c1_fait_retenu AS
SELECT ref, upstream_piece_id, type, cle_brute, cle, valeur, texte_norm, nombre, date, origine, statut, cle_connue
FROM (
    SELECT f.*, ROW_NUMBER() OVER (
        PARTITION BY ref, upstream_piece_id, cle
        ORDER BY CASE origine WHEN 'relue_ciblee' THEN 0 WHEN 'fusion' THEN 1 ELSE 2 END,
                 CASE WHEN cle_brute = cle THEN 0 ELSE 1 END,
                 CASE WHEN valeur IS NULL THEN 1 ELSE 0 END, cle_brute) AS rang
    FROM c1_fait f WHERE statut = 'normal'
) classement WHERE rang = 1;

-- Rapport des clés inconnues : jamais acceptées en silence.
CREATE VIEW c1_cle_inconnue AS
SELECT type, cle_brute, count(*) AS nombre FROM c1_fait WHERE cle_connue = 0 GROUP BY type, cle_brute;

CREATE TABLE c1_releve_mois (
    ref                TEXT NOT NULL,
    upstream_piece_id  TEXT NOT NULL,
    rang               INTEGER NOT NULL,
    annee              INTEGER,
    mois               INTEGER,
    solde_ouverture    DOUBLE PRECISION,
    solde_cloture      DOUBLE PRECISION,
    total_credit       DOUBLE PRECISION,
    total_debit        DOUBLE PRECISION,
    salaire_detecte    DOUBLE PRECISION,
    echeances_credits  DOUBLE PRECISION,
    nb_operations_lues INTEGER NOT NULL,
    PRIMARY KEY (ref, upstream_piece_id, rang)
);

-- Une opération d'un relevé. « lue » : ligne du relevé relu, datée (l'année vient du mois du relevé). 
-- « reconstituee_amont » : ligne sans date, reconstruite par l'amont ; jamais comptée comme une opération lue.
CREATE TABLE c1_releve_operation (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    rang_mois         INTEGER NOT NULL,
    rang              INTEGER NOT NULL,
    annee             INTEGER,
    mois              INTEGER,
    date_operation    TEXT,
    date_valeur       TEXT,
    libelle           TEXT,
    libelle_norm      TEXT,
    debit             DOUBLE PRECISION,
    credit            DOUBLE PRECISION,
    nature            TEXT NOT NULL CHECK (nature IN ('lue', 'reconstituee_amont')),
    PRIMARY KEY (ref, upstream_piece_id, rang_mois, rang)
);

-- Une personne citée par une pièce : nom tel que lu, sans rapprochement (couche 2).
CREATE TABLE c1_mention_personne (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type_piece        TEXT NOT NULL,
    role              TEXT NOT NULL,
    rang              INTEGER NOT NULL,
    nom_complet       TEXT,
    nom_norm          TEXT,
    cin               TEXT,
    date_naissance    TEXT,
    qualite           TEXT,
    parts_sociales    DOUBLE PRECISION,
    nationalite       TEXT,
    adresse           TEXT,
    PRIMARY KEY (ref, upstream_piece_id, role, rang)
);

-- Table enfant proposée par Kamal : gérants, associés et dirigeants d'une société.
CREATE VIEW c1_societe_personne AS
SELECT ref, upstream_piece_id, role, rang, nom_complet, cin, qualite, parts_sociales
FROM c1_mention_personne WHERE role IN ('gerant', 'associe', 'dirigeant');

CREATE TABLE c1_mention_societe (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type_piece        TEXT NOT NULL,
    role              TEXT NOT NULL,
    nom               TEXT,
    nom_norm          TEXT,
    rc                TEXT,
    tribunal          TEXT,
    ice               TEXT,
    affiliation_cnss  TEXT,
    adresse           TEXT,
    PRIMARY KEY (ref, upstream_piece_id, role)
);

-- Identifiant lu dans une pièce (RIB, CIN, n° CNSS, châssis, RC, ICE…), normalisé, avec son porteur tel que lu.
CREATE TABLE c1_identifiant_brut (
    ref               TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    type              TEXT NOT NULL,
    valeur            TEXT NOT NULL,
    porteur           TEXT,
    PRIMARY KEY (ref, upstream_piece_id, type, valeur)
);
CREATE INDEX c1_identifiant_brut_valeur_idx ON c1_identifiant_brut (type, valeur);
