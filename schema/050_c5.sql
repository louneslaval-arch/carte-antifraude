-- Couche 5 : le graphe. Les fiches de c2 (personnes, sociétés) sont des nœuds ; les rôles dans une société sont des
-- liens ; les identifiants partagés (RIB, logement, siège) sont des nœuds intermédiaires : A – RIB – B vaut un lien
-- « même RIB ». Les homonymies de c2 (rapprochements non fusionnés) sont lues dans c2 au moment de la recherche.
-- Chaque arête vient d'une mention de c2 et garde son origine ; le coût de taille n'est jamais figé dans une arête :
-- il se lit dans `c5_compteur` au moment du calcul. Barème n°23, seuils et limites dans `c6_version_parametres`.

INSERT INTO c6_version_parametres (version, nom, valeur, provisoire, date_effet, auteur) VALUES
    ('2026-11-16', 'c5_seuil_majeure', 0.20, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_seuil_mineure', 0.08, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_seuil_affichage', 0.05, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_longueur_alerte', 3, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_longueur_recherche', 4, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_fiabilite_homonymie', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_foyer', 0.1, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_meme_rib', 0.9, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_meme_logement', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_meme_siege', 0.4, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_gerant', 0.7, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_dirigeant', 0.7, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_nouveau_gerant', 0.7, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_administrateur', 0.7, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_associe', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_associe_present', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_liquidateur', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_cessionnaire', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_gerant_sortant', 0.5, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_cedant', 0.3, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_associe_sortant', 0.3, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_representant', 0.3, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_inconnu', 0.3, 1, '2026-11-16', 'provisoire'),
    ('2026-11-16', 'c5_poids_employe', 0.6, 1, '2026-11-16', 'provisoire');

-- Adresse normalisée d'une mention (la normalisation est en Python) ; fonction du seul texte de la mention.
CREATE TABLE c5_cle_adresse (
    mention TEXT PRIMARY KEY,
    ref     TEXT,
    cle     TEXT NOT NULL
);
CREATE INDEX c5_cle_adresse_ref_idx ON c5_cle_adresse (ref);

-- Une arête par mention : `role` (personne → société, code = rôle) ou `identifiant` (fiche → nœud d'identifiant,
-- code = RIB, LOGEMENT, SIEGE). `de` et `vers` sont les fiches de c2 au moment de la construction ; un invariant
-- vérifie qu'elles sont toujours celles de c2.
CREATE TABLE c5_arete (
    cle       TEXT PRIMARY KEY,
    type      TEXT NOT NULL CHECK (type IN ('role', 'identifiant')),
    mention   TEXT NOT NULL,
    mention_b TEXT,
    de        TEXT NOT NULL,
    vers      TEXT NOT NULL,
    code      TEXT NOT NULL,
    parts     TEXT,
    source    TEXT NOT NULL,
    ref       TEXT
);
CREATE INDEX c5_arete_de_idx ON c5_arete (de);
CREATE INDEX c5_arete_vers_idx ON c5_arete (vers);
CREATE INDEX c5_arete_mention_idx ON c5_arete (mention);
CREATE INDEX c5_arete_ref_idx ON c5_arete (ref);

-- Taille n de chaque nœud, pour le coût √(2/n) : personne → ses sociétés ; société → personnes qui y ont un rôle
-- (dirigeants, associés, salariés déclarés) ; identifiant → fiches distinctes qui le portent.
CREATE TABLE c5_compteur (
    noeud TEXT PRIMARY KEY,
    n     INTEGER NOT NULL CHECK (n > 0)
);

-- Les nœuds du graphe : fiches et identifiants partagés, avec leur taille.
CREATE VIEW c5_noeud AS
SELECT c.noeud,
       CASE WHEN c.noeud LIKE 'pp\_%' ESCAPE '\' THEN 'personne' WHEN c.noeud LIKE 'pm\_%' ESCAPE '\' THEN 'societe'
            ELSE 'identifiant' END AS type,
       c.n,
       coalesce((SELECT p.inscrit FROM c2_personne p WHERE p.identifiant = c.noeud),
                (SELECT s.inscrit FROM c2_societe s WHERE s.identifiant = c.noeud), 0) AS inscrit
FROM c5_compteur c;
