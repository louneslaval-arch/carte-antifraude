-- Couche 7 : analytique des dossiers (avance sur l'étape N : statistiques des demandes et de ce que l'antifraude en
-- dit ; la table d'analyse avec le défaut à 12 mois viendra avec la couche 4). Tables reconstruites entièrement par
-- `stats_dossiers.py` depuis c1, c3 et le miroir de la v2. Le verdict est celui de l'antifraude : « jugé suspect »,
-- jamais une fraude constatée. Aucune valeur sur moins de 5 dossiers dans `c7_agregat` (secret primaire et
-- secondaire) ; le sexe et la nationalité ne découpent jamais un verdict ni un contrôle.

-- Dictionnaire des indicateurs, versionné (`pipeline/analytique/indicateurs.py` fait foi).
CREATE TABLE c7_indicateur (
    nom        TEXT PRIMARY KEY,
    libelle    TEXT NOT NULL,
    definition TEXT NOT NULL,
    formule    TEXT NOT NULL,
    source     TEXT NOT NULL,
    unite      TEXT NOT NULL,
    version    TEXT NOT NULL
);

-- Une ligne par dossier (dernière version) : les variables dérivées, NULL quand elles ne se calculent pas (jamais
-- devinées). Table de travail : jamais servie telle quelle.
CREATE TABLE c7_variable_dossier (
    ref                     TEXT PRIMARY KEY,
    actif                   INTEGER NOT NULL CHECK (actif IN (0, 1)),
    date_reference          TEXT,
    semaine                 TEXT,
    type_personne           TEXT,
    csp                     TEXT,
    produit                 TEXT,
    mode_paiement           TEXT,
    categorie               TEXT,
    verdict                 TEXT,
    juge_suspect            INTEGER CHECK (juge_suspect IN (0, 1)),
    statut_analyse          TEXT,
    nb_alertes_mineures     INTEGER,
    nb_alertes_majeures     INTEGER,
    nb_alertes_critiques    INTEGER,
    age                     INTEGER,
    tranche_age             TEXT,
    sexe                    TEXT,
    nationalite             TEXT,
    situation_familiale     TEXT,
    personnes_a_charge      INTEGER,
    revenu_verifie          DOUBLE PRECISION,
    source_revenu           TEXT,
    tranche_revenu          TEXT,
    revenu_declare          DOUBLE PRECISION,
    ecart_revenu            DOUBLE PRECISION,
    tranche_ecart_revenu    TEXT,
    anciennete_emploi       DOUBLE PRECISION,
    tranche_anciennete      TEXT,
    type_contrat            TEXT,
    banque                  TEXT,
    ville                   TEXT,
    region                  TEXT,
    source_ville            TEXT,
    vehicule_etat           TEXT,
    prix_vehicule           DOUBLE PRECISION,
    tranche_prix_vehicule   TEXT,
    marque_vehicule         TEXT,
    apport_pct              DOUBLE PRECISION,
    age_societe             DOUBLE PRECISION,
    tranche_age_societe     TEXT,
    associe_unique          INTEGER CHECK (associe_unique IN (0, 1)),
    capital_tranche         TEXT,
    nb_pieces               INTEGER NOT NULL,
    nb_pieces_relues        INTEGER NOT NULL,
    taux_relecture          DOUBLE PRECISION,
    releve_lignes_lues      INTEGER CHECK (releve_lignes_lues IN (0, 1)),
    employeur               TEXT,
    concessionnaire         TEXT
);

-- Une case par (indicateur, tranche de filtre, dimensions). Les dimensions absentes valent '' (une clé primaire ne
-- compare pas des NULL). Case masquée : aucune valeur, ni numérateur, ni dénominateur, ni fourchette.
CREATE TABLE c7_agregat (
    indicateur       TEXT NOT NULL,
    filtre_produit   TEXT NOT NULL,
    filtre_categorie TEXT NOT NULL,
    dimension1       TEXT NOT NULL DEFAULT '',
    valeur1          TEXT NOT NULL DEFAULT '',
    dimension2       TEXT NOT NULL DEFAULT '',
    valeur2          TEXT NOT NULL DEFAULT '',
    numerateur       INTEGER,
    denominateur     INTEGER,
    valeur           DOUBLE PRECISION,
    borne_basse      DOUBLE PRECISION,
    borne_haute      DOUBLE PRECISION,
    masque           INTEGER NOT NULL CHECK (masque IN (0, 1)),
    motif_masque     TEXT CHECK (motif_masque IN ('moins de 5', 'secret secondaire')),
    periode_debut    TEXT NOT NULL,
    periode_fin      TEXT NOT NULL,
    version          TEXT NOT NULL,
    calcule_le       TEXT NOT NULL,
    PRIMARY KEY (indicateur, filtre_produit, filtre_categorie, dimension1, valeur1, dimension2, valeur2),
    CHECK (masque = 0 OR (valeur IS NULL AND numerateur IS NULL AND denominateur IS NULL
                          AND borne_basse IS NULL AND borne_haute IS NULL AND motif_masque IS NOT NULL))
);
