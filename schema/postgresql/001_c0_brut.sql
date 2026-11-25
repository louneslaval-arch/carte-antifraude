-- Couche 0 : chaque version reçue de chaque dossier, gardée telle quelle avec son empreinte, pour tout rejouer.
-- Rien n'est interprété ici. Identifiants en texte (uuid posés par le code) : SQL portable SQLite et PostgreSQL.

-- Un passage de collecte.
CREATE TABLE c0_export (
    id                 TEXT PRIMARY KEY,
    source             TEXT NOT NULL,
    mode               TEXT NOT NULL CHECK (mode IN ('scrutation', 'notification', 'lecture_directe', 'lot')),
    commence_le        TEXT NOT NULL,
    termine_le         TEXT,
    dossiers           INTEGER NOT NULL DEFAULT 0,
    versions_nouvelles INTEGER NOT NULL DEFAULT 0,
    version_serveur    TEXT
);

-- Une version d'un dossier : le JSON complet reçu de la v2. Une empreinte = un JSON.
-- `updated_at` reprend `updatedAt` de la v2 ; `actif` vaut 0 pour un dossier écarté (archives).
CREATE TABLE c0_dossier_brut (
    ref        TEXT NOT NULL,
    empreinte  TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    json       TEXT NOT NULL,
    actif      INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    passage    TEXT NOT NULL REFERENCES c0_export (id),
    recu_le    TEXT NOT NULL,
    PRIMARY KEY (ref, empreinte)
);
CREATE INDEX c0_dossier_brut_ref_idx ON c0_dossier_brut (ref, updated_at);
