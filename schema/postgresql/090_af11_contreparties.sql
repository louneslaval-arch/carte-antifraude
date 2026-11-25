CREATE TABLE c6_af11_candidat (
    ref TEXT NOT NULL,
    upstream_piece_id TEXT NOT NULL,
    rang_mois INTEGER NOT NULL,
    rang INTEGER NOT NULL,
    identifiant_inscrit TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'a_verifier',
    motif TEXT NOT NULL,
    detecte_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        ref,
        upstream_piece_id,
        rang_mois,
        rang,
        identifiant_inscrit
    ),

    FOREIGN KEY (
        ref,
        upstream_piece_id,
        rang_mois,
        rang
    )
    REFERENCES c3_operation (
        ref,
        upstream_piece_id,
        rang_mois,
        rang
    )
    ON DELETE CASCADE
);

CREATE INDEX idx_c6_af11_identifiant
ON c6_af11_candidat(identifiant_inscrit);