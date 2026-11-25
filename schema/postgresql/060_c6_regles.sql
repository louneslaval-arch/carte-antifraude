-- C6 : alertes métier calculées, aucune fraude n'est déclarée automatiquement.
-- Exécuter une fois sur eqdom_pipeline_test après les migrations C0-C5.
CREATE TABLE IF NOT EXISTS c6_alerte (
    ref TEXT NOT NULL,
    cle TEXT NOT NULL,
    code TEXT NOT NULL,
    nature TEXT NOT NULL CHECK (nature IN ('lien_liste_noire', 'incoherence', 'signal')),
    niveau TEXT CHECK (niveau IN ('critique', 'majeure', 'mineure', 'affiche', 'hors_alerte')),
    justification TEXT NOT NULL,
    calcule_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ref, cle)
);
CREATE INDEX IF NOT EXISTS c6_alerte_ref_niveau_idx ON c6_alerte (ref, niveau);
