-- Relations complémentaires : en attente de champs explicitement fournis par Tandem.
-- Aucune relation ne découle d'un nom seul.
CREATE TABLE IF NOT EXISTS c7_relation (
    ref TEXT NOT NULL REFERENCES c3_dossier(ref),
    code TEXT NOT NULL CHECK (code IN ('caution','coemprunteur','reference_personnelle',
                                      'signataire','cabinet_comptable','meme_immeuble')),
    cle TEXT NOT NULL,
    fiche TEXT,
    noeud TEXT,
    source_piece TEXT NOT NULL,
    PRIMARY KEY (ref, code, cle)
);
CREATE INDEX IF NOT EXISTS c7_relation_noeud_idx ON c7_relation(noeud);
CREATE INDEX IF NOT EXISTS c7_relation_fiche_idx ON c7_relation(fiche);
INSERT INTO c6_version_parametres (version,nom,valeur,provisoire,date_effet,auteur) VALUES
 ('2026-11-19','c7_poids_caution',0.8,1,'2026-11-19','catalogue'),
 ('2026-11-19','c7_poids_coemprunteur',0.9,1,'2026-11-19','catalogue'),
 ('2026-11-19','c7_poids_reference_personnelle',0.5,1,'2026-11-19','catalogue'),
 ('2026-11-19','c7_poids_signataire',0.5,1,'2026-11-19','catalogue'),
 ('2026-11-19','c7_poids_cabinet_comptable',0.4,1,'2026-11-19','catalogue'),
 ('2026-11-19','c7_poids_meme_immeuble',0.2,1,'2026-11-19','catalogue')
ON CONFLICT (version,nom) DO NOTHING;
