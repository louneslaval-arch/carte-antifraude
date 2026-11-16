-- Paramètres métier, versionnés : toute valeur de seuil ou de tolérance se lit ici, jamais en dur dans le code.
-- `provisoire` vaut 1 tant que la valeur n'est pas décidée (`docs/questions_ouvertes.md`). La version en vigueur est
-- la plus grande. Les paramètres du score (barème, coût de taille, seuils) s'y ajouteront à l'étape I.
CREATE TABLE c6_version_parametres (
    version    TEXT NOT NULL,
    nom        TEXT NOT NULL,
    valeur     DOUBLE PRECISION NOT NULL,
    provisoire INTEGER NOT NULL CHECK (provisoire IN (0, 1)),
    date_effet TEXT,
    auteur     TEXT,
    PRIMARY KEY (version, nom)
);
INSERT INTO c6_version_parametres (version, nom, valeur, provisoire, date_effet, auteur) VALUES
    ('2026-11-16', 'c3_tolerance_salaire', 0.10, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c3_rafale_jours', 30, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c3_rafale_dossiers', 3, 1, '2026-11-16', 'provisoire');

-- Valeur en vigueur de chaque paramètre.
CREATE VIEW parametre AS
SELECT p.nom, p.valeur, p.provisoire, p.version FROM c6_version_parametres p
WHERE p.version = (SELECT max(q.version) FROM c6_version_parametres q WHERE q.nom = p.nom);

-- Valeurs par défaut que l'amont pose quand un champ n'est pas renseigné : jamais comparées à une valeur lue.
CREATE TABLE ref_valeur_defaut (
    champ  TEXT NOT NULL,
    valeur TEXT NOT NULL,
    PRIMARY KEY (champ, valeur)
);
INSERT INTO ref_valeur_defaut (champ, valeur) VALUES ('employeur_declare', 'VAB');
