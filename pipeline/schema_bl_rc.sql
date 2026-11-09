-- =============================================================================
-- Base « liste noire × registre du commerce » — schéma SQLite
-- SEVEN · projet réseaux de fraude EQDOM · version du 21/10/2026
--
-- Liste noire de référence : extraction EQDOM du 03/08/2026 (elle fait foi).
-- Registre du commerce     : annonces légales collectées par Kamal
--   (Bulletin officiel en arabe, JAL Maroc, JAL du Maroc, Flash Économie,
--    annoncelegale.aumaroc.org, annoncelegale.umaroc.com).
--
-- Principe : chaque côté est réduit à des CLÉS DE COMPARAISON calculées par la
-- même fonction (table « cle »). Les règles R01 à R09 (regles_bl_rc.sql)
-- rapprochent les clés de même type, puis le graphe pondéré suit les rebonds.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- 1. Paramètres et référentiels
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parametre (
    nom          TEXT PRIMARY KEY,
    valeur       REAL,
    texte        TEXT,
    description  TEXT
);

CREATE TABLE IF NOT EXISTS ref_ville (
    ville_code   TEXT PRIMARY KEY,          -- nom canonique sans accent (CASABLANCA)
    libelle      TEXT NOT NULL,
    libelle_ar   TEXT,
    code_eqdom   TEXT,                      -- 5 premiers caractères, comme la colonne regist_tribune (CASAB)
    variantes    TEXT                       -- graphies reconnues, séparées par « | »
);

CREATE TABLE IF NOT EXISTS ref_ville_code_eqdom (   -- codes numériques de la colonne « ville » de la liste noire
    code         TEXT PRIMARY KEY,
    ville_code   TEXT REFERENCES ref_ville(ville_code),
    origine      TEXT,                      -- « déduit des adresses » tant qu'EQDOM n'a pas fourni son référentiel
    preuve       TEXT
);

CREATE TABLE IF NOT EXISTS ref_role (
    role         TEXT PRIMARY KEY,          -- gerant, associe, cedant, cessionnaire, liquidateur, administrateur, inconnu
    libelle      TEXT,
    code_lien    TEXT,                      -- code du cadrage Kamal (L08 gérant, L09 associé)
    poids        REAL,                      -- poids de départ de l'arête personne → société
    variantes    TEXT
);

CREATE TABLE IF NOT EXISTS ref_regle (
    regle        TEXT PRIMARY KEY,
    libelle      TEXT,
    nature       TEXT,                      -- identite, dirigeant, emploi, adresse
    niveau       TEXT,                      -- certain (alerte) / probable (homonymie à lever)
    cle_bl       TEXT,
    cle_rc       TEXT,
    confirmation TEXT,
    poids        TEXT
);

CREATE TABLE IF NOT EXISTS ref_correspondance_champs (   -- « les données comparables »
    ordre          INTEGER PRIMARY KEY,
    champ_bl       TEXT,
    champ_rc       TEXT,
    type_cle       TEXT,
    normalisation  TEXT,
    regles         TEXT,
    remplissage_bl TEXT,
    remplissage_rc TEXT,
    remarque       TEXT
);

CREATE TABLE IF NOT EXISTS ref_source_rc (
    source       TEXT PRIMARY KEY,
    libelle      TEXT,
    langue       TEXT,
    remarque     TEXT
);

-- -----------------------------------------------------------------------------
-- 2. Liste noire
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bl_entite (          -- une ligne par personne ou société inscrite
    entite_id        INTEGER PRIMARY KEY,
    cle_entite       TEXT NOT NULL UNIQUE,      -- P:<CIN> · M:<RC>@<ville tribunal> · M:<RC>@?:<raison sociale> · F:<IF> · P#/M#<num_seq>
    type_entite      TEXT NOT NULL CHECK (type_entite IN ('PP', 'PM')),
    nom_affiche      TEXT,
    cin              TEXT,
    rc_num           TEXT,
    tribunal_code    TEXT REFERENCES ref_ville(ville_code),
    if_num           TEXT,
    ice              TEXT,
    date_naissance   TEXT,
    ville_code       TEXT,
    adresse          TEXT,
    employeur        TEXT,
    nb_inscriptions  INTEGER,
    premiere_saisie  TEXT,
    derniere_saisie  TEXT,
    types_liste      TEXT,
    types_fraude     TEXT,
    origines         TEXT,
    motifs           TEXT,
    exposition_max   REAL,
    statut           TEXT DEFAULT 'actif',      -- actif / retiré (la liste du 03/08/2026 fait foi)
    date_reference   TEXT,
    rattachement     TEXT                       -- cle_dure (CIN ou RC) / nom / aucun
);

CREATE TABLE IF NOT EXISTS bl_inscription (     -- une ligne par ligne du fichier EQDOM
    num_seq            INTEGER PRIMARY KEY,
    entite_id          INTEGER REFERENCES bl_entite(entite_id),
    -- 28 colonnes d'origine, nettoyées (espaces, encodage cassé, séquences corrompues)
    cin TEXT, regist_com TEXT, ice TEXT, regist_tribune TEXT, cli_phy_mor TEXT, no_drpp TEXT,
    nom_ras TEXT, t_cli TEXT, date_naiss TEXT, adresse TEXT, ville TEXT, lib_emp TEXT, interm TEXT,
    part TEXT, motif TEXT, motif2 TEXT, type_liste TEXT, type_fraude TEXT, orig_liste TEXT,
    orig_agence TEXT, mt_exposition REAL, note TEXT, dat_sais TEXT, user_sais TEXT, user_maj TEXT,
    nom TEXT, prenom TEXT,
    -- valeurs normalisées
    type_entite        TEXT,
    cin_norm           TEXT,
    cin_statut         TEXT,                    -- valide, lettre_finale, rc_dans_cin, identifiant_fiscal, masque, chiffres_seuls, non_standard, absent
    rc_num             TEXT,
    rc_statut          TEXT,
    if_num             TEXT,
    ice_norm           TEXT,
    tribunal_code      TEXT,
    tribunal_statut    TEXT,
    ville_code         TEXT,
    ville_origine      TEXT,                    -- texte, code_deduit, adresse
    date_naiss_valide  TEXT,
    nom_affiche        TEXT,
    type_liste_norm    TEXT,
    type_fraude_norm   TEXT,
    statut_inscription TEXT DEFAULT 'actif',
    date_reference     TEXT
);
CREATE INDEX IF NOT EXISTS ix_bl_inscription_entite ON bl_inscription (entite_id);

CREATE TABLE IF NOT EXISTS bl_anomalie (
    id         INTEGER PRIMARY KEY,
    num_seq    INTEGER REFERENCES bl_inscription(num_seq),
    champ      TEXT,
    valeur     TEXT,
    anomalie   TEXT,
    traitement TEXT
);

-- -----------------------------------------------------------------------------
-- 3. Registre du commerce (annonces légales collectées par Kamal)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rc_societe (
    societe_id            INTEGER PRIMARY KEY,
    cle_societe           TEXT NOT NULL UNIQUE,  -- RC:<n°>@<ville>[#k] · RC:<n°>@?:<raison sociale> · RS:<raison sociale> · ANN:<annonce>
    denomination          TEXT,                  -- nom le plus fréquent, en écriture latine si possible
    autres_denominations  TEXT,
    rc_num                TEXT,
    tribunal_code         TEXT,
    ville_code            TEXT,                  -- ville du dernier siège connu
    siege                 TEXT,
    capital               TEXT,
    premiere_publication  TEXT,
    derniere_publication  TEXT,
    nb_annonces           INTEGER,
    types_actes           TEXT,
    dissoute              INTEGER DEFAULT 0,
    nb_personnes          INTEGER DEFAULT 0,
    rarete_taille         REAL DEFAULT 1.0,      -- nb_personnes^(-alpha) : une grosse société transmet peu
    ice                   TEXT,
    if_num                TEXT,
    forme_juridique       TEXT,
    rc_conflit            INTEGER DEFAULT 0,     -- 1 : ce RC + tribunal porte des noms incompatibles, séparés en #2, #3…
    fiabilite             REAL DEFAULT 1.0,      -- 0,5 si la société n'est connue que par des blocs mélangeant plusieurs annonces
    intermediaires        TEXT                   -- cabinets ou fiduciaires qui ont déposé les annonces (titre ≠ dénomination)
);

CREATE TABLE IF NOT EXISTS rc_annonce (
    annonce_id            TEXT PRIMARY KEY,      -- <source>:<identifiant_source>
    societe_id            INTEGER REFERENCES rc_societe(societe_id),
    source                TEXT,
    type_acte             TEXT,
    date_publication      TEXT,
    numero_publication    TEXT,
    url                   TEXT,
    denomination          TEXT,
    denomination_statut   TEXT,                  -- valide, ambigue (portée par ≥ 3 RC), generique, forme_seule, entete, adresse, absente
    forme_juridique       TEXT,
    rc                    TEXT,
    rc_statut             TEXT,                  -- valide, suspect_depot (= n° de dépôt), suspect_annee, suspect_long, absent…
    tribunal              TEXT,
    ice                   TEXT,
    if_brut               TEXT,
    capital               TEXT,
    siege                 TEXT,
    ville                 TEXT,
    objet                 TEXT,
    date_acte             TEXT,
    date_depot            TEXT,
    numero_depot          TEXT,
    nouvelle_denomination TEXT,
    nouveau_siege         TEXT,
    nouveau_capital       TEXT,
    nouvelle_forme        TEXT,
    total_parts           TEXT,
    lecture_complete      INTEGER,
    information_absente   INTEGER,
    bloc_mixte            INTEGER,               -- 1 : le bloc lu mélangeait plusieurs annonces
    titre                 TEXT,                  -- souvent le cabinet ou la fiduciaire qui a déposé l'annonce
    fiabilite             REAL,
    rc_num                TEXT,
    tribunal_code         TEXT,
    ville_code            TEXT
);
CREATE INDEX IF NOT EXISTS ix_rc_annonce_societe ON rc_annonce (societe_id);

CREATE TABLE IF NOT EXISTS rc_personne (         -- une ligne par personne (ou société associée) et par société
    personne_id       INTEGER PRIMARY KEY,
    cle_stable        TEXT NOT NULL UNIQUE,      -- <cle_societe>|N:<nom écrit> ou |CIN:<cin> ou |S:<raison sociale>
    societe_id        INTEGER REFERENCES rc_societe(societe_id),
    type_personne     TEXT,                      -- PP / PM (société associée)
    nom_complet       TEXT,
    ecriture          TEXT,                      -- latin / arabe
    nom_exact         TEXT,                      -- nom écrit à l'identique (sans espaces ni alifs)
    cin               TEXT,
    cin_norm          TEXT,
    cin_statut        TEXT,
    role              TEXT REFERENCES ref_role(role),   -- rôle principal (le plus lourd)
    roles             TEXT,
    poids_role        REAL,
    parts             TEXT,
    pct               REAL,
    sortant           INTEGER,                   -- 1 : n'apparaît que comme sortant ou cédant
    fiabilite         REAL,
    nb_mentions       INTEGER,
    premiere_mention  TEXT,
    derniere_mention  TEXT,
    ville_code        TEXT,
    date_naissance    TEXT,
    nationalite       TEXT,
    adresse           TEXT
);
CREATE INDEX IF NOT EXISTS ix_rc_personne_societe ON rc_personne (societe_id);
CREATE INDEX IF NOT EXISTS ix_rc_personne_cin ON rc_personne (cin_norm);

CREATE TABLE IF NOT EXISTS rc_mention (          -- chaque apparition d'une personne dans une annonce
    mention_id   INTEGER PRIMARY KEY,
    personne_id  INTEGER REFERENCES rc_personne(personne_id),
    annonce_id   TEXT REFERENCES rc_annonce(annonce_id),
    champ        TEXT,
    role         TEXT,
    role_texte   TEXT,
    texte_brut   TEXT,
    parts        TEXT,
    pct          REAL
);
CREATE INDEX IF NOT EXISTS ix_rc_mention_personne ON rc_mention (personne_id);

CREATE TABLE IF NOT EXISTS rc_rejet (            -- entrées des champs personnes écartées, avec leur motif
    id          INTEGER PRIMARY KEY,
    annonce_id  TEXT,
    champ       TEXT,
    texte_brut  TEXT,
    motif       TEXT                             -- phrase_juridique, mot_unique, gabarit, chiffres, trop_long, societe_illisible…
);

CREATE TABLE IF NOT EXISTS rc_participation (    -- associé « société » rattaché à la société du registre qui porte ce nom
    personne_id  INTEGER REFERENCES rc_personne(personne_id),
    societe_id   INTEGER REFERENCES rc_societe(societe_id)
);

CREATE TABLE IF NOT EXISTS rc_homonyme (         -- même nom écrit à l'identique, même ville, dans 2 à 5 sociétés
    cle         TEXT PRIMARY KEY,
    nom         TEXT,
    ville_code  TEXT,
    n           INTEGER,
    poids       REAL
);
CREATE TABLE IF NOT EXISTS rc_homonyme_membre (
    cle          TEXT REFERENCES rc_homonyme(cle),
    personne_id  INTEGER REFERENCES rc_personne(personne_id)
);

CREATE TABLE IF NOT EXISTS similarite_societe (  -- sociétés inscrites × sociétés du registre au même numéro RC
    bl_entite_id  INTEGER,
    societe_id    INTEGER,
    sim           REAL,                          -- similarité des raisons sociales (0 à 1)
    tribunal_bl   TEXT,
    tribunal_rc   TEXT,
    fiabilite     REAL,
    rc_conflit    INTEGER,
    regle         TEXT,                          -- R02, R02n, R03, R03t ou vide (simple homonymie de numéro)
    niveau        TEXT,
    poids         REAL,
    detail        TEXT,
    PRIMARY KEY (bl_entite_id, societe_id)
);

-- -----------------------------------------------------------------------------
-- 4. Clés de comparaison (calculées par la même fonction des deux côtés)
-- -----------------------------------------------------------------------------
-- type_cle : CIN, CIN_VAR, RC_NUM, RC_TRIB, ICE, IF, RS, RS_SQ, NOM, NOM_SQ, VILLE, DATE_NAISS, ADR
-- role     : identite, dirigeant, employeur, residence, siege, tribunal, personne
CREATE TABLE IF NOT EXISTS cle (
    cote        TEXT    NOT NULL CHECK (cote IN ('BL', 'RC')),
    objet       TEXT    NOT NULL,                 -- bl_entite / rc_societe / rc_personne
    objet_id    INTEGER NOT NULL,
    type_cle    TEXT    NOT NULL,
    role        TEXT    NOT NULL DEFAULT '',
    valeur      TEXT    NOT NULL,
    societe_id  INTEGER,                          -- côté RC : société de l'annonce
    PRIMARY KEY (cote, objet, objet_id, type_cle, role, valeur)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_cle_valeur ON cle (type_cle, valeur, cote, objet);

CREATE TABLE IF NOT EXISTS cle_frequence (      -- côté RC : combien de sociétés partagent chaque valeur
    type_cle  TEXT NOT NULL,
    valeur    TEXT NOT NULL,
    n         INTEGER,
    rarete    REAL,                                -- n^(-alpha)
    PRIMARY KEY (type_cle, valeur)
) WITHOUT ROWID;

-- -----------------------------------------------------------------------------
-- 5. Résultats : correspondances, décisions, graphe, chemins
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS correspondance (     -- toutes les règles qui se déclenchent
    id            INTEGER PRIMARY KEY,
    bl_entite_id  INTEGER NOT NULL REFERENCES bl_entite(entite_id),
    rc_objet      TEXT    NOT NULL,               -- rc_personne / rc_societe
    rc_objet_id   INTEGER NOT NULL,
    societe_id    INTEGER,
    nature        TEXT    NOT NULL,
    regle         TEXT    NOT NULL,
    niveau        TEXT    NOT NULL,
    cle_type      TEXT,
    cle_valeur    TEXT,
    confirmation  TEXT,
    poids_regle   REAL,
    rarete        REAL DEFAULT 1.0,
    fiabilite     REAL DEFAULT 1.0,              -- 0,5 si l'annonce vient d'un bloc mélangé
    poids         REAL,
    statut        TEXT,                           -- alerte / homonymie / a_verifier / confirme / ecarte
    UNIQUE (bl_entite_id, rc_objet, rc_objet_id, regle)
);

CREATE INDEX IF NOT EXISTS ix_corr_objet ON correspondance (rc_objet, rc_objet_id);

CREATE TABLE IF NOT EXISTS correspondance_retenue (   -- la meilleure règle par couple inscrit × objet du registre
    bl_entite_id     INTEGER NOT NULL,
    rc_objet         TEXT    NOT NULL,
    rc_objet_id      INTEGER NOT NULL,
    societe_id       INTEGER,
    nature           TEXT,
    regle            TEXT,
    niveau           TEXT,
    cle_type         TEXT,
    cle_valeur       TEXT,
    confirmation     TEXT,
    poids            REAL,
    statut           TEXT,
    regles_touchees  TEXT,
    PRIMARY KEY (bl_entite_id, rc_objet, rc_objet_id)
);
CREATE INDEX IF NOT EXISTS ix_corr_ret_societe ON correspondance_retenue (societe_id);

CREATE TABLE IF NOT EXISTS decision_analyste (  -- conservée d'une construction à l'autre
    id             INTEGER PRIMARY KEY,
    cle_bl         TEXT NOT NULL,                 -- bl_entite.cle_entite
    rc_objet       TEXT NOT NULL,                 -- rc_personne / rc_societe
    cle_rc         TEXT NOT NULL,                 -- rc_personne.cle_stable ou rc_societe.cle_societe
    decision       TEXT NOT NULL CHECK (decision IN ('meme_personne', 'homonyme_ecarte')),
    analyste       TEXT,
    date_decision  TEXT,
    justification  TEXT,
    UNIQUE (cle_bl, rc_objet, cle_rc)
);

CREATE TABLE IF NOT EXISTS noeud (
    type     TEXT NOT NULL,                       -- bl, rc_societe, rc_personne, rc_individu
    id       TEXT NOT NULL,
    libelle  TEXT,
    PRIMARY KEY (type, id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS arete (               -- stockée dans les deux sens
    de_type    TEXT NOT NULL,
    de_id      TEXT NOT NULL,
    vers_type  TEXT NOT NULL,
    vers_id    TEXT NOT NULL,
    code_lien  TEXT,
    poids      REAL
);
CREATE INDEX IF NOT EXISTS ix_arete_de ON arete (de_type, de_id);

CREATE TABLE IF NOT EXISTS chemin (              -- meilleur chemin d'un inscrit vers chaque nœud atteint
    bl_entite_id  INTEGER NOT NULL,
    cible_type    TEXT    NOT NULL,
    cible_id      TEXT    NOT NULL,
    profondeur    INTEGER,
    force         REAL,                           -- produit des poids des arêtes
    trace         TEXT,
    PRIMARY KEY (bl_entite_id, cible_type, cible_id)
);
CREATE INDEX IF NOT EXISTS ix_chemin_cible ON chemin (cible_type, cible_id);

-- -----------------------------------------------------------------------------
-- 6. Vues de travail
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bilan;
CREATE VIEW v_bilan AS
          SELECT 1 AS ordre, 'Inscriptions en liste noire (03/08/2026)' AS indicateur, count(*) AS valeur FROM bl_inscription
UNION ALL SELECT 2, 'Entités inscrites (personnes + sociétés)', count(*) FROM bl_entite
UNION ALL SELECT 3, '  dont personnes physiques', count(*) FROM bl_entite WHERE type_entite = 'PP'
UNION ALL SELECT 4, '  dont sociétés', count(*) FROM bl_entite WHERE type_entite = 'PM'
UNION ALL SELECT 5, 'Entités avec une clé dure (CIN ou RC)', count(*) FROM bl_entite WHERE rattachement = 'cle_dure'
UNION ALL SELECT 6, 'Entités rapprochables par le nom seulement', count(*) FROM bl_entite WHERE rattachement = 'nom'
UNION ALL SELECT 7, 'Entités sans aucune clé', count(*) FROM bl_entite WHERE rattachement = 'aucun'
UNION ALL SELECT 8, 'Anomalies relevées dans la liste noire', count(*) FROM bl_anomalie
UNION ALL SELECT 9, 'Annonces légales chargées', count(*) FROM rc_annonce
UNION ALL SELECT 10, 'Sociétés du registre', count(*) FROM rc_societe
UNION ALL SELECT 11, 'Personnes citées (une par société)', count(*) FROM rc_personne
UNION ALL SELECT 11.1, '  mentions dans les annonces', count(*) FROM rc_mention
UNION ALL SELECT 11.2, '  entrées écartées (faux noms, phrases, gabarits)', count(*) FROM rc_rejet
UNION ALL SELECT 11.3, 'Sociétés dont le RC porte des noms incompatibles (séparées)', count(*) FROM rc_societe WHERE rc_conflit = 1
UNION ALL SELECT 12, 'Correspondances certaines (alerte)', count(*) FROM correspondance_retenue WHERE niveau = 'certain' AND statut <> 'ecarte'
UNION ALL SELECT 13, 'Correspondances probables (à lever par un analyste)', count(*) FROM correspondance_retenue WHERE statut IN ('homonymie', 'a_verifier')
UNION ALL SELECT 14, 'Correspondances faibles (sous le seuil, masquées)', count(*) FROM correspondance_retenue WHERE statut = 'faible'
UNION ALL SELECT 15, 'Inscrits reliés au registre (hors liens faibles)', count(DISTINCT bl_entite_id) FROM correspondance_retenue WHERE statut NOT IN ('ecarte', 'faible')
UNION ALL SELECT 16, 'Sociétés du registre atteintes par un chemin', count(DISTINCT cible_id) FROM chemin WHERE cible_type = 'rc_societe';

DROP VIEW IF EXISTS v_bl_fiche;
CREATE VIEW v_bl_fiche AS
SELECT e.*,
       (SELECT count(*) FROM correspondance_retenue c
         WHERE c.bl_entite_id = e.entite_id AND c.niveau = 'certain' AND c.statut <> 'ecarte')  AS liens_certains,
       (SELECT count(*) FROM correspondance_retenue c
         WHERE c.bl_entite_id = e.entite_id AND c.statut IN ('homonymie', 'a_verifier'))       AS liens_probables
FROM bl_entite e;

DROP VIEW IF EXISTS v_qualite_bl;
CREATE VIEW v_qualite_bl AS
SELECT anomalie, champ, traitement, count(*) AS nb
FROM bl_anomalie GROUP BY anomalie, champ, traitement ORDER BY nb DESC;

DROP VIEW IF EXISTS v_correspondance;
CREATE VIEW v_correspondance AS
SELECT c.statut, c.niveau, c.regle, r.libelle AS regle_libelle, c.nature, round(c.poids, 3) AS poids,
       e.cle_entite, e.type_entite, e.nom_affiche AS inscrit, e.cin AS inscrit_cin, e.rc_num AS inscrit_rc,
       e.types_liste, e.motifs,
       s.denomination, s.rc_num, s.tribunal_code, s.ville_code AS ville_siege,
       p.nom_complet AS personne_registre, p.roles AS role_registre, p.cin AS cin_registre, p.nb_mentions,
       a.source, a.type_acte, a.date_publication, a.annonce_id, a.url,
       c.cle_type, c.cle_valeur, c.confirmation, c.regles_touchees,
       CASE c.rc_objet WHEN 'rc_personne' THEN p.cle_stable ELSE s.cle_societe END AS cle_rc,
       c.rc_objet, c.rc_objet_id, c.bl_entite_id
FROM correspondance_retenue c
JOIN bl_entite e             ON e.entite_id = c.bl_entite_id
LEFT JOIN ref_regle r        ON r.regle = c.regle
LEFT JOIN rc_personne p      ON c.rc_objet = 'rc_personne' AND p.personne_id = c.rc_objet_id
LEFT JOIN rc_societe s       ON s.societe_id = c.societe_id
LEFT JOIN rc_annonce a       ON a.annonce_id = coalesce(
        (SELECT m.annonce_id FROM rc_mention m WHERE m.personne_id = p.personne_id ORDER BY m.annonce_id DESC LIMIT 1),
        (SELECT x.annonce_id FROM rc_annonce x WHERE x.societe_id = s.societe_id ORDER BY x.date_publication DESC LIMIT 1));

DROP VIEW IF EXISTS v_homonymies_a_traiter;
CREATE VIEW v_homonymies_a_traiter AS
SELECT * FROM v_correspondance WHERE statut IN ('homonymie', 'a_verifier') ORDER BY poids DESC;

DROP VIEW IF EXISTS v_societe_signalee;
CREATE VIEW v_societe_signalee AS
SELECT s.societe_id, s.denomination, s.rc_num, s.tribunal_code, s.ville_code,
       max(c.nature = 'identite' AND c.rc_objet = 'rc_societe')                                        AS societe_inscrite,
       count(DISTINCT CASE WHEN c.rc_objet = 'rc_personne' AND c.niveau = 'certain'  THEN c.bl_entite_id END) AS personnes_inscrites_certaines,
       count(DISTINCT CASE WHEN c.rc_objet = 'rc_personne' AND c.niveau = 'probable' THEN c.bl_entite_id END) AS personnes_inscrites_probables,
       count(DISTINCT CASE WHEN c.nature = 'emploi' THEN c.bl_entite_id END)                           AS inscrits_employes,
       round(max(c.poids), 3) AS poids_max,
       group_concat(DISTINCT c.regle) AS regles
FROM correspondance_retenue c
JOIN rc_societe s ON s.societe_id = c.societe_id
WHERE c.statut NOT IN ('ecarte', 'faible')
GROUP BY s.societe_id;

DROP VIEW IF EXISTS v_chemin;
CREATE VIEW v_chemin AS
SELECT e.cle_entite, e.nom_affiche AS inscrit, c.cible_type, n.libelle AS cible,
       c.profondeur, round(c.force, 3) AS force, c.trace, c.bl_entite_id, c.cible_id
FROM chemin c
JOIN bl_entite e  ON e.entite_id = c.bl_entite_id
LEFT JOIN noeud n ON n.type = c.cible_type AND n.id = c.cible_id;

-- Contrôle d'un employeur : la société est-elle reliée à un inscrit, et par quel chemin ?
-- Exemple : SELECT * FROM v_controle_employeur WHERE rc_num = '123456' AND tribunal_code = 'CASABLANCA';
DROP VIEW IF EXISTS v_controle_employeur;
CREATE VIEW v_controle_employeur AS
SELECT s.societe_id, s.denomination, s.rc_num, s.tribunal_code, s.ville_code,
       count(DISTINCT c.bl_entite_id) AS inscrits_relies,
       round(max(c.force), 3)         AS force_max,
       c.profondeur                   AS profondeur_meilleur_chemin,
       e.nom_affiche                  AS inscrit_le_plus_proche,
       c.trace                        AS meilleur_chemin
FROM chemin c
JOIN rc_societe s ON s.societe_id = CAST(c.cible_id AS INTEGER)
JOIN bl_entite e  ON e.entite_id = c.bl_entite_id
WHERE c.cible_type = 'rc_societe'
GROUP BY s.societe_id;

-- Réseau entre inscrits : deux inscrits reliés à travers le registre
DROP VIEW IF EXISTS v_reseau_inscrits;
CREATE VIEW v_reseau_inscrits AS
SELECT e1.nom_affiche AS inscrit, e2.nom_affiche AS autre_inscrit, c.profondeur, round(c.force, 3) AS force, c.trace
FROM chemin c
JOIN bl_entite e1 ON e1.entite_id = c.bl_entite_id
JOIN bl_entite e2 ON e2.entite_id = CAST(c.cible_id AS INTEGER)
WHERE c.cible_type = 'bl' AND c.bl_entite_id < CAST(c.cible_id AS INTEGER);

DROP VIEW IF EXISTS v_couverture_regles;
CREATE VIEW v_couverture_regles AS
SELECT c.regle, r.libelle, c.niveau, c.nature, count(*) AS correspondances,
       count(DISTINCT c.bl_entite_id) AS inscrits, count(DISTINCT c.societe_id) AS societes
FROM correspondance c LEFT JOIN ref_regle r ON r.regle = c.regle
GROUP BY c.regle, c.niveau, c.nature ORDER BY c.regle;

DROP VIEW IF EXISTS v_rc_societe_fiche;
CREATE VIEW v_rc_societe_fiche AS
SELECT s.*,
       (SELECT group_concat(coalesce(p.nom_complet, 'CIN ' || p.cin) || ' (' || p.role || ')', ' ; ')
          FROM rc_personne p WHERE p.societe_id = s.societe_id) AS personnes_citees
FROM rc_societe s;

DROP VIEW IF EXISTS v_qualite_rc;
CREATE VIEW v_qualite_rc AS
          SELECT 'Entrée personne écartée' AS controle, motif AS detail, count(*) AS nb FROM rc_rejet GROUP BY motif
UNION ALL SELECT 'Numéro RC', rc_statut, count(*) FROM rc_annonce GROUP BY rc_statut
UNION ALL SELECT 'Dénomination', denomination_statut, count(*) FROM rc_annonce GROUP BY denomination_statut
UNION ALL SELECT 'Annonce issue d''un bloc mélangé', CAST(bloc_mixte AS TEXT), count(*) FROM rc_annonce GROUP BY bloc_mixte
UNION ALL SELECT 'Tribunal reconnu', CASE WHEN tribunal_code IS NULL THEN 'non' ELSE 'oui' END, count(*) FROM rc_annonce GROUP BY 2
ORDER BY 1, 3 DESC;

-- Cabinets ou fiduciaires qui ont déposé les annonces de sociétés reliées à la liste noire
DROP VIEW IF EXISTS v_intermediaire_signale;
CREATE VIEW v_intermediaire_signale AS
SELECT a.titre AS intermediaire, count(DISTINCT a.societe_id) AS societes_reliees,
       group_concat(DISTINCT s.denomination) AS societes
FROM rc_annonce a
JOIN rc_societe s ON s.societe_id = a.societe_id
WHERE a.titre IS NOT NULL AND a.titre <> a.denomination
  AND a.societe_id IN (SELECT societe_id FROM correspondance_retenue WHERE statut NOT IN ('ecarte', 'faible'))
GROUP BY a.titre
HAVING count(DISTINCT a.societe_id) >= 2
ORDER BY societes_reliees DESC;
