-- Couche 2 : une fiche maître par personne et par société, qui réunit la liste noire, le registre du commerce
-- (socle construit par le kit, recopié ici par `charger_socle`) et les dossiers de la v2 (couche 1).
-- Une « mention » est une apparition d'une personne ou d'une société dans une source ; une « fiche » réunit les
-- mentions qui partagent une clé forte. Les fiches se recalculent entièrement depuis les mentions.

-- Liste noire d'EQDOM dans la structure de `BlacklistEntry` de Kamal (noms de ses champs), plus ce que son modèle
-- n'a pas : clé de l'entité dans le kit, tribunal, ICE, date de naissance, adresse, employeur déclaré, statut daté
-- (décision n°4), type de fraude, saisies. Remplie par `charger_socle` ; une ligne par personne ou société inscrite.
CREATE TABLE ref_liste_noire (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('CLIENT', 'EMPLOYEUR', 'GERANT', 'BENEFICIAIRE', 'TIERS_BANCAIRE', 'ZONE')),
    label           TEXT NOT NULL,
    normalized      TEXT NOT NULL,
    city            TEXT,
    active          INTEGER NOT NULL CHECK (active IN (0, 1)),
    "createdAt"     TEXT,
    personne        TEXT,
    nom             TEXT,
    prenom          TEXT,
    "raisonSociale" TEXT,
    cin             TEXT,
    rc              TEXT,
    "typeListe"     TEXT,
    motif           TEXT,
    source          TEXT,
    cle_entite      TEXT NOT NULL UNIQUE,
    tribunal        TEXT,
    ice             TEXT,
    identifiant_fiscal TEXT,
    date_naissance  TEXT,
    adresse         TEXT,
    employeur       TEXT,
    statut          TEXT NOT NULL,
    date_statut     TEXT,
    type_fraude     TEXT,
    nb_inscriptions INTEGER,
    premiere_saisie TEXT,
    derniere_saisie TEXT
);

-- Pour chaque attribut d'une fiche, la source qui l'emporte (rang 1 d'abord ; « * » : tout rôle). Décision n°16
-- pour l'adresse : le relevé, puis les autres pièces, la liste noire, le registre, la CIN en dernier ; pour une
-- société, le siège inscrit au registre.
CREATE TABLE ref_regle_survie (
    type_fiche TEXT NOT NULL CHECK (type_fiche IN ('PP', 'PM')),
    attribut   TEXT NOT NULL,
    rang       INTEGER NOT NULL,
    source     TEXT NOT NULL,
    role       TEXT NOT NULL,
    PRIMARY KEY (type_fiche, attribut, rang)
);
INSERT INTO ref_regle_survie (type_fiche, attribut, rang, source, role) VALUES
    ('PP', 'nom', 1, 'v2', 'titulaire_cin'), ('PP', 'nom', 2, 'liste_noire', '*'), ('PP', 'nom', 3, 'registre', '*'),
    ('PP', 'nom', 4, 'v2', '*'),
    ('PP', 'date_naissance', 1, 'v2', 'titulaire_cin'), ('PP', 'date_naissance', 2, 'liste_noire', '*'),
    ('PP', 'date_naissance', 3, 'registre', '*'), ('PP', 'date_naissance', 4, 'v2', '*'),
    ('PP', 'adresse', 1, 'v2', 'titulaire_compte'), ('PP', 'adresse', 2, 'v2', 'titulaire_quittance'),
    ('PP', 'adresse', 3, 'v2', 'employe'), ('PP', 'adresse', 4, 'v2', 'pensionne'),
    ('PP', 'adresse', 5, 'liste_noire', '*'), ('PP', 'adresse', 6, 'registre', '*'), ('PP', 'adresse', 7, 'v2', '*'),
    ('PM', 'nom', 1, 'registre', '*'), ('PM', 'nom', 2, 'liste_noire', '*'), ('PM', 'nom', 3, 'v2', 'societe'),
    ('PM', 'nom', 4, 'v2', '*'),
    ('PM', 'adresse', 1, 'registre', '*'), ('PM', 'adresse', 2, 'v2', 'societe'), ('PM', 'adresse', 3, 'v2', '*'),
    ('PM', 'adresse', 4, 'liste_noire', '*');

-- Chaque apparition d'une personne (PP) ou d'une société (PM). `source` : liste_noire, registre (recopiés du socle),
-- v2 (reconstruits depuis c1). `fiche` et `regle` (comment la mention y est rattachée) sont calculés :
-- CIN, nom_dans_dossier, AF05, RC_TRIB, ICE, IF, AFFILIATION, propre (fiche propre à la source), gabarit, sans_nom.
CREATE TABLE c2_mention (
    id                TEXT PRIMARY KEY,
    cle_origine       TEXT NOT NULL UNIQUE,
    source            TEXT NOT NULL CHECK (source IN ('liste_noire', 'registre', 'v2')),
    type_fiche        TEXT NOT NULL CHECK (type_fiche IN ('PP', 'PM')),
    ref               TEXT,
    upstream_piece_id TEXT,
    type_piece        TEXT,
    role              TEXT,
    rang              INTEGER,
    nom               TEXT,
    nom_norm          TEXT,
    cle_nom           TEXT,
    ecriture          TEXT,
    cin               TEXT,
    cin_effectif      TEXT,
    date_naissance    TEXT,
    adresse           TEXT,
    rc                TEXT,
    tribunal          TEXT,
    rc_cle            TEXT,
    ice               TEXT,
    identifiant_fiscal TEXT,
    affiliation_cnss  TEXT,
    societe_mention   TEXT,
    societe_cle       TEXT,
    parts             TEXT,
    statut            TEXT NOT NULL CHECK (statut IN ('normal', 'gabarit')),
    inscrit           INTEGER NOT NULL CHECK (inscrit IN (0, 1)),
    fiche             TEXT,
    regle             TEXT
);
CREATE INDEX c2_mention_ref_idx ON c2_mention (ref);
CREATE INDEX c2_mention_fiche_idx ON c2_mention (fiche);
CREATE INDEX c2_mention_cin_idx ON c2_mention (cin_effectif);
CREATE INDEX c2_mention_cin_propre_idx ON c2_mention (cin);
CREATE INDEX c2_mention_rc_idx ON c2_mention (rc_cle);
CREATE INDEX c2_mention_ice_idx ON c2_mention (ice);
CREATE INDEX c2_mention_if_idx ON c2_mention (identifiant_fiscal);
CREATE INDEX c2_mention_affiliation_idx ON c2_mention (affiliation_cnss);
CREATE INDEX c2_mention_societe_cle_idx ON c2_mention (societe_cle);
CREATE INDEX c2_mention_cle_nom_idx ON c2_mention (cle_nom);
CREATE INDEX c2_mention_societe_mention_idx ON c2_mention (societe_mention);

CREATE TABLE c2_personne (
    identifiant    TEXT PRIMARY KEY,
    cle_naturelle  TEXT NOT NULL UNIQUE,
    nom            TEXT,
    cin            TEXT,
    date_naissance TEXT,
    adresse        TEXT,
    inscrit        INTEGER NOT NULL CHECK (inscrit IN (0, 1)),
    nb_mentions    INTEGER NOT NULL
);

CREATE TABLE c2_societe (
    identifiant      TEXT PRIMARY KEY,
    cle_naturelle    TEXT NOT NULL UNIQUE,
    denomination     TEXT,
    rc               TEXT,
    tribunal         TEXT,
    ice              TEXT,
    affiliation_cnss TEXT,
    adresse          TEXT,
    inscrit          INTEGER NOT NULL CHECK (inscrit IN (0, 1)),
    nb_mentions      INTEGER NOT NULL
);

-- Identifiants de fiche déjà attribués : une clé naturelle garde son identifiant ; jamais vidée.
CREATE TABLE c2_identifiant_attribue (
    cle_naturelle TEXT PRIMARY KEY,
    type_fiche    TEXT NOT NULL,
    identifiant   TEXT NOT NULL UNIQUE
);

-- Rapprochements entre deux mentions qui ne sont pas une fusion : règles du kit (R01 à R11, recopiées), règles sur
-- le périmètre d'un dossier (AF01n, AF02b, AF02d, AF07), CIN partagé par des noms incompatibles (CIN_PARTAGE).
CREATE TABLE c2_correspondance_mention (
    mention_a    TEXT NOT NULL,
    mention_b    TEXT NOT NULL,
    nature       TEXT NOT NULL,
    regle        TEXT NOT NULL,
    niveau       TEXT NOT NULL,
    statut       TEXT NOT NULL,
    cle_type     TEXT,
    cle_valeur   TEXT,
    confirmation TEXT,
    poids        DOUBLE PRECISION,
    source       TEXT NOT NULL CHECK (source IN ('kit', 'v2', 'c2')),
    ref          TEXT,
    PRIMARY KEY (mention_a, mention_b, regle)
);
CREATE INDEX c2_correspondance_mention_ref_idx ON c2_correspondance_mention (ref);

-- Décision d'un analyste sur un rapprochement. Elle se prend sur un couple de fiches et s'attache aux couples de
-- mentions qui le fondent (identifiants de mention : stables, alors qu'une fiche change d'identifiant quand sa clé
-- se renforce) ; elle survit à toutes les reconstructions.
CREATE TABLE c2_decision (
    mention_a     TEXT NOT NULL,
    mention_b     TEXT NOT NULL,
    decision      TEXT NOT NULL CHECK (decision IN ('meme_personne', 'homonyme_ecarte')),
    analyste      TEXT,
    date_decision TEXT,
    justification TEXT,
    PRIMARY KEY (mention_a, mention_b)
);

-- Périmètre des règles : toutes les mentions v2 en lot, celles d'un dossier au fil de l'eau. Même SQL.
CREATE TABLE c2_perimetre (mention TEXT PRIMARY KEY);
CREATE VIEW perimetre AS
SELECT m.* FROM c2_mention m JOIN c2_perimetre p ON p.mention = m.id;

-- Rapprochements entre deux fiches distinctes, avec la décision de l'analyste quand il y en a une.
CREATE VIEW c2_correspondance AS
SELECT x.fiche_a, x.fiche_b, x.nature, x.regle, x.niveau,
       CASE d.decision WHEN 'homonyme_ecarte' THEN 'ecarte' WHEN 'meme_personne' THEN 'confirme' ELSE x.statut END AS statut,
       x.cle_type, x.source, x.nb_mentions
FROM (
    SELECT a.fiche AS fiche_a, b.fiche AS fiche_b, c.nature, c.regle, c.source, min(c.niveau) AS niveau,
           min(c.statut) AS statut, min(c.cle_type) AS cle_type, count(*) AS nb_mentions
    FROM c2_correspondance_mention c
    JOIN c2_mention a ON a.id = c.mention_a
    JOIN c2_mention b ON b.id = c.mention_b
    WHERE a.fiche IS NOT NULL AND b.fiche IS NOT NULL AND a.fiche <> b.fiche
    GROUP BY a.fiche, b.fiche, c.nature, c.regle, c.source
) x
LEFT JOIN (
    SELECT a.fiche AS fiche_a, b.fiche AS fiche_b, min(k.decision) AS decision
    FROM c2_decision k
    JOIN c2_mention a ON a.id = k.mention_a
    JOIN c2_mention b ON b.id = k.mention_b
    GROUP BY a.fiche, b.fiche
) d ON (d.fiche_a = x.fiche_a AND d.fiche_b = x.fiche_b) OR (d.fiche_a = x.fiche_b AND d.fiche_b = x.fiche_a);

-- Graphies sous lesquelles une fiche a été lue.
CREATE VIEW c2_alias AS
SELECT fiche, nom AS alias, nom_norm AS alias_norm, ecriture, count(*) AS nb_mentions
FROM c2_mention WHERE fiche IS NOT NULL AND nom IS NOT NULL
GROUP BY fiche, nom, nom_norm, ecriture;

-- Toutes les adresses connues d'une fiche, avec leur source.
CREATE VIEW c2_adresse AS
SELECT fiche, adresse, source, role, ref, upstream_piece_id
FROM c2_mention WHERE fiche IS NOT NULL AND adresse IS NOT NULL
GROUP BY fiche, adresse, source, role, ref, upstream_piece_id;

-- Rôle d'une fiche dans une société (gérant, associé, dirigeant, salarié…), d'après chaque mention.
CREATE VIEW c2_role AS
SELECT p.fiche, s.fiche AS societe, p.role, p.parts, p.source, p.ref, p.upstream_piece_id
FROM c2_mention p JOIN c2_mention s ON s.id = p.societe_mention
WHERE p.fiche IS NOT NULL AND s.fiche IS NOT NULL
GROUP BY p.fiche, s.fiche, p.role, p.parts, p.source, p.ref, p.upstream_piece_id;

-- Identifiants portés par une fiche : ses clés fortes, et les identifiants bruts de c1 rattachés par le rôle de la
-- mention dans la pièce (RIB du titulaire ou du salarié, n° CNSS, pension, INPE, châssis et immatriculation).
CREATE VIEW c2_identifiant AS
SELECT fiche, 'CIN' AS type, cin AS valeur, source, ref, upstream_piece_id FROM c2_mention
    WHERE fiche IS NOT NULL AND cin IS NOT NULL GROUP BY fiche, cin, source, ref, upstream_piece_id
UNION ALL
SELECT fiche, 'RC_TRIB', rc_cle, source, ref, upstream_piece_id FROM c2_mention
    WHERE fiche IS NOT NULL AND rc_cle IS NOT NULL GROUP BY fiche, rc_cle, source, ref, upstream_piece_id
UNION ALL
SELECT fiche, 'ICE', ice, source, ref, upstream_piece_id FROM c2_mention
    WHERE fiche IS NOT NULL AND ice IS NOT NULL GROUP BY fiche, ice, source, ref, upstream_piece_id
UNION ALL
SELECT fiche, 'AFFILIATION_CNSS', affiliation_cnss, source, ref, upstream_piece_id FROM c2_mention
    WHERE fiche IS NOT NULL AND affiliation_cnss IS NOT NULL
    GROUP BY fiche, affiliation_cnss, source, ref, upstream_piece_id
UNION ALL
SELECT m.fiche, i.type, i.valeur, m.source, i.ref, i.upstream_piece_id
FROM c1_identifiant_brut i
JOIN c2_mention m ON m.source = 'v2' AND m.ref = i.ref AND m.upstream_piece_id = i.upstream_piece_id
WHERE m.fiche IS NOT NULL AND (
       (i.type = 'RIB' AND m.role IN ('titulaire_compte', 'employe'))
    OR (i.type IN ('CNSS', 'INPE') AND m.role = 'employe')
    OR (i.type = 'PENSION' AND m.role = 'pensionne')
    OR (i.type IN ('CHASSIS', 'IMMATRICULATION') AND m.role IN ('proprietaire', 'acheteur')))
GROUP BY m.fiche, i.type, i.valeur, m.source, i.ref, i.upstream_piece_id;

-- Employeurs lus dans les dossiers, selon le référentiel `Employeur` de Kamal : clé ICE, une ligne par graphie
-- (son tableau `noms`), nombre de lectures (`vus`).
CREATE VIEW c2_employeur AS
SELECT ice, nom, count(*) AS vus FROM c2_mention
WHERE source = 'v2' AND role = 'employeur' AND ice IS NOT NULL AND nom IS NOT NULL
GROUP BY ice, nom;
