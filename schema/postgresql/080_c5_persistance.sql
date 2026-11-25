-- Persistance des résultats du graphe C5

-- 1. Chemins entre dossiers et identités inscrites
CREATE TABLE IF NOT EXISTS c5_chemin (
    ref TEXT NOT NULL,
    cible TEXT NOT NULL,
    longueur INTEGER NOT NULL,
    force DOUBLE PRECISION NOT NULL,
    niveau TEXT NOT NULL,
    homonymie BOOLEAN NOT NULL DEFAULT FALSE,
    foyer BOOLEAN NOT NULL DEFAULT FALSE,
    etapes JSONB NOT NULL DEFAULT '[]'::jsonb,
    calcule_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ref, cible)
);

CREATE INDEX IF NOT EXISTS idx_c5_chemin_cible
ON c5_chemin(cible);


-- 2. Groupes d'entités connectées
CREATE TABLE IF NOT EXISTS c5_composante (
    composante_id TEXT NOT NULL,
    noeud TEXT NOT NULL,
    calcule_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (composante_id, noeud)
);

CREATE INDEX IF NOT EXISTS idx_c5_composante_noeud
ON c5_composante(noeud);


-- 3. Indicateurs du réseau
CREATE TABLE IF NOT EXISTS c5_mesure (
    noeud TEXT PRIMARY KEY,
    degre INTEGER NOT NULL DEFAULT 0,
    taille_composante INTEGER NOT NULL DEFAULT 1,
    nb_chemins_liste_noire INTEGER NOT NULL DEFAULT 0,
    calcule_le TIMESTAMPTZ NOT NULL DEFAULT NOW()
);