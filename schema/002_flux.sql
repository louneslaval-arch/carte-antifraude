-- Temps réel : source, curseur et file de travail du collecteur (docs/architecture_temps_reel.md § 5).
-- Aucune donnée de dossier ici : références, empreintes, états, codes d'erreur sans valeur.

-- Une instance de la v2. Le secret du compte de service reste dans une variable d'environnement.
CREATE TABLE flux_source (
    nom          TEXT PRIMARY KEY,
    adresse      TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'scrutation' CHECK (mode IN ('scrutation', 'notification', 'lecture_directe')),
    intervalle_s INTEGER NOT NULL DEFAULT 60,
    liste_triee  INTEGER CHECK (liste_triee IN (0, 1))
);

CREATE TABLE flux_curseur (
    source                    TEXT PRIMARY KEY REFERENCES flux_source (nom),
    dernier_updated_at        TEXT,
    derniere_scrutation       TEXT,
    derniere_reussite         TEXT,
    derniere_lecture_complete TEXT,
    echecs                    INTEGER NOT NULL DEFAULT 0,
    prochaine_scrutation      TEXT
);

-- Un dossier à aller chercher. Une même version annoncée deux fois (scrutation, notification) ne fait qu'un travail.
-- États (.claude/rules/flux.md) : en_attente → en_cours → fait ; erreur → nouvelle tentative à intervalle croissant ;
-- bloque après 5 échecs, ou si la v2 ne connaît pas le dossier : visible dans l'administration, jamais effacé.
CREATE TABLE flux_travail (
    id                  TEXT PRIMARY KEY,
    source              TEXT NOT NULL REFERENCES flux_source (nom),
    ref                 TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    empreinte           TEXT,
    recu_le             TEXT NOT NULL,
    etat                TEXT NOT NULL DEFAULT 'en_attente' CHECK (etat IN ('en_attente', 'en_cours', 'fait', 'erreur', 'bloque')),
    essais              INTEGER NOT NULL DEFAULT 0,
    prochaine_tentative TEXT,
    duree_ms            INTEGER,
    code_erreur         TEXT,
    UNIQUE (source, ref, updated_at)
);
CREATE INDEX flux_travail_etat_idx ON flux_travail (etat, prochaine_tentative);
