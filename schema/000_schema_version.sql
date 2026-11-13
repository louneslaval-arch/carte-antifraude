-- Migrations appliquées : numéro, nom du fichier, empreinte SHA-256 de son contenu, date d'application (ISO 8601).
-- Une migration appliquée ne se modifie plus : toute correction passe par une nouvelle migration.
CREATE TABLE IF NOT EXISTS schema_version (
    numero      INTEGER PRIMARY KEY,
    nom         TEXT NOT NULL,
    empreinte   TEXT NOT NULL,
    applique_le TEXT NOT NULL
);
