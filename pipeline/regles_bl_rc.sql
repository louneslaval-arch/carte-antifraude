-- =============================================================================
-- Règles de rapprochement liste noire × registre du commerce
-- À relancer après chaque chargement, changement de paramètre ou décision
-- d'analyste :  python3 construire_base.py --base bl_rc.sqlite --regles-seulement
--
-- Niveaux (décisions du 21/10/2026) :
--   certain  : même CIN pour une personne, ou même RC et même tribunal pour une
--              société → statut « alerte » ;
--   probable : même nom normalisé + un élément qui confirme (société, date de
--              naissance, ville…) → statut provisoire « homonymie », levé par un
--              analyste (« même personne » ou « homonyme écarté ») ;
--   nom seul : jamais un lien.
-- Poids = poids de la règle × rareté de la valeur partagée (n^-alpha).
-- =============================================================================

-- Statistiques des index : sans elles, SQLite peut choisir un ordre de jointure
-- quadratique sur une grosse base (plusieurs minutes au lieu d'une fraction de seconde).
ANALYZE;

DELETE FROM correspondance;

-- R01 · même CIN : l'inscrit est une personne citée dans une annonce -----------
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, r.objet, r.objet_id, r.societe_id, 'identite', 'R01', 'certain', 'CIN', b.valeur, NULL, 1.0, 1.0
FROM cle b
JOIN cle r ON r.type_cle = 'CIN' AND r.valeur = b.valeur AND r.cote = 'RC'
WHERE b.cote = 'BL' AND b.type_cle = 'CIN' AND b.role = 'identite';

-- R01b · CIN saisi sur une société inscrite = personne citée (son dirigeant) ---
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, r.objet, r.objet_id, r.societe_id, 'dirigeant', 'R01b', 'certain', 'CIN', b.valeur,
       'CIN saisi sur la ligne de la société inscrite', 1.0, 1.0
FROM cle b
JOIN cle r ON r.type_cle = 'CIN' AND r.valeur = b.valeur AND r.cote = 'RC'
WHERE b.cote = 'BL' AND b.type_cle = 'CIN' AND b.role = 'dirigeant';

-- R01v · CIN saisi avec une lettre finale parasite ----------------------------
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, r.objet, r.objet_id, r.societe_id, 'identite', 'R01v', 'probable', 'CIN_VAR', b.valeur,
       'CIN de la liste noire saisi avec une lettre finale', 0.8, 1.0
FROM cle b
JOIN cle r ON r.type_cle = 'CIN' AND r.valeur = b.valeur AND r.cote = 'RC'
WHERE b.cote = 'BL' AND b.type_cle = 'CIN_VAR';

-- R02 / R02n / R03 / R03t · même numéro RC : la règle dépend du tribunal et de la similarité des noms
-- (table similarite_societe, recalculée par le script avant chaque passage des règles)
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT s.bl_entite_id, 'rc_societe', s.societe_id, s.societe_id, 'identite', s.regle, s.niveau, 'RC_NUM',
       (SELECT rc_num FROM rc_societe WHERE societe_id = s.societe_id), s.detail, s.poids, 1.0
FROM similarite_societe s
WHERE s.regle IS NOT NULL;

-- R10 · même ICE ; R11 · même identifiant fiscal -------------------------------
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'identite',
       CASE b.type_cle WHEN 'ICE' THEN 'R10' ELSE 'R11' END, 'certain', b.type_cle, b.valeur, NULL, 1.0, 1.0
FROM cle b
JOIN cle r ON r.type_cle = b.type_cle AND r.valeur = b.valeur AND r.cote = 'RC' AND r.objet = 'rc_societe'
WHERE b.cote = 'BL' AND b.type_cle IN ('ICE', 'IF');

-- R04 · même raison sociale et même ville (siège ou tribunal) -----------------
-- (d'abord la clé exacte, puis le squelette consonantique qui traverse l'arabe)
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'identite', 'R04', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.7, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_societe' AND rv.objet_id = r.objet_id AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'RS' AND b.role = 'identite';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'identite', 'R04', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.6, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_societe' AND rv.objet_id = r.objet_id AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'RS_SQ' AND b.role = 'identite';

-- R04u · option (paramètre r04_sans_ville = 1) : raison sociale unique au registre
-- La dénomination est protégée au niveau national (certificat négatif OMPIC).
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'identite', 'R04u', 'probable', 'RS', b.valeur,
       'raison sociale unique au registre', 0.6, 1.0
FROM cle b
JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = 'RS' AND r.valeur = b.valeur
JOIN cle_frequence f ON f.type_cle = 'RS' AND f.valeur = b.valeur AND f.n = 1
WHERE b.cote = 'BL' AND b.type_cle = 'RS' AND b.role = 'identite'
  AND (SELECT valeur FROM parametre WHERE nom = 'r04_sans_ville') = 1;

-- R05 · même nom de personne et même société (employeur déclaré = société de l'annonce)
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R05', 'probable', b.type_cle, b.valeur,
       'même société : ' || be.valeur, 0.8, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle be ON be.cote = 'BL' AND be.objet = 'bl_entite' AND be.objet_id = b.objet_id
           AND be.role = 'employeur' AND be.type_cle IN ('RS', 'RS_SQ')
JOIN cle rs ON rs.cote = 'RC' AND rs.objet = 'rc_societe' AND rs.objet_id = r.societe_id
           AND rs.type_cle = be.type_cle AND rs.valeur = be.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R05', 'probable', b.type_cle, b.valeur,
       'même société : ' || be.valeur, 0.7, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle be ON be.cote = 'BL' AND be.objet = 'bl_entite' AND be.objet_id = b.objet_id
           AND be.role = 'employeur' AND be.type_cle IN ('RS', 'RS_SQ')
JOIN cle rs ON rs.cote = 'RC' AND rs.objet = 'rc_societe' AND rs.objet_id = r.societe_id
           AND rs.type_cle = be.type_cle AND rs.valeur = be.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM_SQ';

-- R05b · même nom de personne et société de l'annonce reliée à une société inscrite
-- (la liste noire inscrit souvent la société ET son gérant)
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R05b', 'probable', b.type_cle, b.valeur,
       'société inscrite : ' || (SELECT nom_affiche FROM bl_entite WHERE entite_id = c2.bl_entite_id),
       CASE b.type_cle WHEN 'NOM' THEN 0.8 ELSE 0.7 END, f.rarete
FROM cle b
JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN correspondance c2 ON c2.rc_objet = 'rc_societe' AND c2.rc_objet_id = r.societe_id AND c2.nature = 'identite'
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle IN ('NOM', 'NOM_SQ') AND c2.bl_entite_id <> b.objet_id;

-- R06 · même nom de personne et même date de naissance ------------------------
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R06', 'probable', b.type_cle, b.valeur,
       'même date de naissance : ' || bd.valeur, CASE b.type_cle WHEN 'NOM' THEN 0.8 ELSE 0.7 END, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bd ON bd.cote = 'BL' AND bd.objet = 'bl_entite' AND bd.objet_id = b.objet_id AND bd.type_cle = 'DATE_NAISS'
JOIN cle rd ON rd.cote = 'RC' AND rd.objet = 'rc_personne' AND rd.objet_id = r.objet_id
           AND rd.type_cle = 'DATE_NAISS' AND rd.valeur = bd.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle IN ('NOM', 'NOM_SQ');

-- R07 · même nom de personne et même ville -------------------------------------
-- ville de la société de l'annonce (siège ou tribunal), puis ville propre de la personne
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R07', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.5, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_societe' AND rv.objet_id = r.societe_id
           AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R07', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.5, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_personne' AND rv.objet_id = r.objet_id
           AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R07', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.4, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_societe' AND rv.objet_id = r.societe_id
           AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM_SQ';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_personne', r.objet_id, r.societe_id, 'identite', 'R07', 'probable', b.type_cle, b.valeur,
       'même ville : ' || bv.valeur, 0.4, f.rarete
FROM cle b
JOIN cle r  ON r.cote = 'RC' AND r.objet = 'rc_personne' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle bv ON bv.cote = 'BL' AND bv.objet = 'bl_entite' AND bv.objet_id = b.objet_id AND bv.type_cle = 'VILLE'
JOIN cle rv ON rv.cote = 'RC' AND rv.objet = 'rc_personne' AND rv.objet_id = r.objet_id
           AND rv.type_cle = 'VILLE' AND rv.valeur = bv.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'NOM_SQ';

-- R08 · employeur déclaré de l'inscrit = société du registre (lien L06) -------
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'emploi', 'R08', 'probable', b.type_cle, b.valeur,
       'employeur déclaré dans la liste noire', 0.6, f.rarete
FROM cle b
JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.role = 'employeur' AND b.type_cle = 'RS';

INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'emploi', 'R08', 'probable', b.type_cle, b.valeur,
       'employeur déclaré dans la liste noire', 0.5, f.rarete
FROM cle b
JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = b.type_cle AND r.valeur = b.valeur
JOIN cle_frequence f ON f.type_cle = b.type_cle AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.role = 'employeur' AND b.type_cle = 'RS_SQ';

-- R09 · même adresse précise (adresse de l'inscrit = siège d'une société) -----
INSERT OR IGNORE INTO correspondance
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids_regle, rarete)
SELECT b.objet_id, 'rc_societe', r.objet_id, r.objet_id, 'adresse', 'R09', 'probable', 'ADR', b.valeur, NULL, 0.4, f.rarete
FROM cle b
JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = 'ADR' AND r.valeur = b.valeur
JOIN cle_frequence f ON f.type_cle = 'ADR' AND f.valeur = b.valeur
WHERE b.cote = 'BL' AND b.type_cle = 'ADR';

-- Poids et statut --------------------------------------------------------------
-- « faible » : poids sous le seuil poids_min_lien (nom très répandu, adresse de domiciliation…) :
-- le lien est gardé mais n'entre ni dans la file des analystes ni dans le graphe.
-- ==== ÉTAPE 2 : contrôle des squelettes fait par le script, puis poids, statuts et graphe ====
-- fiabilité de l'objet du registre (0,5 s'il ne vient que de blocs mélangeant plusieurs annonces)
UPDATE correspondance
SET fiabilite = coalesce(CASE rc_objet
        WHEN 'rc_personne' THEN (SELECT fiabilite FROM rc_personne WHERE personne_id = correspondance.rc_objet_id)
        ELSE (SELECT fiabilite FROM rc_societe WHERE societe_id = correspondance.rc_objet_id) END, 1.0);
-- un lien certain tiré d'une annonce douteuse redevient probable
UPDATE correspondance SET niveau = 'probable' WHERE niveau = 'certain' AND fiabilite < 1;

UPDATE correspondance
SET poids  = poids_regle * coalesce(rarete, 1.0) * fiabilite,
    statut = CASE WHEN niveau = 'certain' THEN 'alerte'
                  WHEN poids_regle * coalesce(rarete, 1.0) * fiabilite
                       < (SELECT valeur FROM parametre WHERE nom = 'poids_min_lien') THEN 'faible'
                  WHEN nature = 'identite' THEN 'homonymie'
                  ELSE 'a_verifier' END;

-- Décisions des analystes (« homonyme écarté » retire le lien des contrôles) ---
UPDATE correspondance SET statut = 'ecarte'
WHERE EXISTS (
    SELECT 1 FROM decision_analyste d
    JOIN bl_entite e ON e.cle_entite = d.cle_bl
    WHERE e.entite_id = correspondance.bl_entite_id
      AND d.rc_objet = correspondance.rc_objet
      AND d.decision = 'homonyme_ecarte'
      AND d.cle_rc = CASE correspondance.rc_objet
            WHEN 'rc_personne' THEN (SELECT p.cle_stable  FROM rc_personne p WHERE p.personne_id = correspondance.rc_objet_id)
            ELSE                    (SELECT s.cle_societe FROM rc_societe  s WHERE s.societe_id  = correspondance.rc_objet_id) END);

-- (« même personne » rend le lien certain)
UPDATE correspondance SET statut = 'confirme', niveau = 'certain', poids = 1.0
WHERE EXISTS (
    SELECT 1 FROM decision_analyste d
    JOIN bl_entite e ON e.cle_entite = d.cle_bl
    WHERE e.entite_id = correspondance.bl_entite_id
      AND d.rc_objet = correspondance.rc_objet
      AND d.decision = 'meme_personne'
      AND d.cle_rc = CASE correspondance.rc_objet
            WHEN 'rc_personne' THEN (SELECT p.cle_stable  FROM rc_personne p WHERE p.personne_id = correspondance.rc_objet_id)
            ELSE                    (SELECT s.cle_societe FROM rc_societe  s WHERE s.societe_id  = correspondance.rc_objet_id) END);

-- Meilleure règle par couple inscrit × objet du registre ----------------------
DELETE FROM correspondance_retenue;
INSERT INTO correspondance_retenue
      (bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids, statut, regles_touchees)
SELECT bl_entite_id, rc_objet, rc_objet_id, societe_id, nature, regle, niveau, cle_type, cle_valeur, confirmation, poids, statut, regles
FROM (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY bl_entite_id, rc_objet, rc_objet_id
                              ORDER BY (statut IN ('ecarte', 'faible')), (niveau = 'certain') DESC, poids DESC, regle) AS rang,
           group_concat(regle, ' ') OVER (PARTITION BY bl_entite_id, rc_objet, rc_objet_id)              AS regles
    FROM correspondance c
)
WHERE rang = 1;

-- =============================================================================
-- Graphe pondéré et chemins (les rebonds)
-- =============================================================================
DELETE FROM noeud;
INSERT INTO noeud (type, id, libelle)
SELECT 'bl', CAST(entite_id AS TEXT),
       'Inscrit LN ' || coalesce(nom_affiche, '?') ||
       coalesce(' [' || coalesce(cin, 'RC ' || rc_num) || ']', '')
FROM bl_entite;
INSERT INTO noeud (type, id, libelle)
SELECT 'rc_societe', CAST(societe_id AS TEXT),
       'Société ' || coalesce(denomination, '?') ||
       coalesce(' [RC ' || rc_num || coalesce(' ' || tribunal_code, '') || ']', '')
FROM rc_societe;
INSERT INTO noeud (type, id, libelle)
SELECT 'rc_personne', CAST(personne_id AS TEXT),
       coalesce(nom_complet, 'Personne') || ' (' || coalesce(roles, role, 'inconnu') || ')' || coalesce(' [CIN ' || cin_norm || ']', '')
FROM rc_personne;
INSERT INTO noeud (type, id, libelle)
SELECT 'rc_homonyme', cle, 'Même nom au registre : ' || nom || ' (' || ville_code || ', ' || n || ' sociétés)'
FROM rc_homonyme;
INSERT OR IGNORE INTO noeud (type, id, libelle)
SELECT DISTINCT 'rc_individu', cin_norm, 'Individu CIN ' || cin_norm
FROM rc_personne WHERE cin_norm IS NOT NULL AND cin_statut = 'valide';

DELETE FROM arete;
-- inscrit ≡ objet du registre (correspondances retenues, hors liens écartés ou faibles)
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT 'bl', CAST(bl_entite_id AS TEXT), rc_objet, CAST(rc_objet_id AS TEXT), regle, poids
FROM correspondance_retenue WHERE statut NOT IN ('ecarte', 'faible');
-- personne citée → société de l'annonce (rôle, atténué par la taille de la société)
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT 'rc_personne', CAST(p.personne_id AS TEXT), 'rc_societe', CAST(p.societe_id AS TEXT),
       r.code_lien || ' ' || r.role, p.poids_role * coalesce(s.rarete_taille, 1.0) * coalesce(p.fiabilite, 1.0)
FROM rc_personne p
JOIN ref_role r   ON r.role = p.role
JOIN rc_societe s ON s.societe_id = p.societe_id;
-- société associée (personne morale) ≡ société du registre qui porte ce nom
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT 'rc_personne', CAST(personne_id AS TEXT), 'rc_societe', CAST(societe_id AS TEXT), 'même société', 1.0
FROM rc_participation;
-- même nom écrit à l'identique dans la même ville, dans peu de sociétés
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT 'rc_personne', CAST(m.personne_id AS TEXT), 'rc_homonyme', m.cle, 'même nom', h.poids
FROM rc_homonyme_membre m JOIN rc_homonyme h ON h.cle = m.cle;
-- personne citée → individu (même CIN dans plusieurs annonces)
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT 'rc_personne', CAST(personne_id AS TEXT), 'rc_individu', cin_norm, 'même CIN', 1.0
FROM rc_personne WHERE cin_norm IS NOT NULL AND cin_statut = 'valide';
-- sens retour
INSERT INTO arete (de_type, de_id, vers_type, vers_id, code_lien, poids)
SELECT vers_type, vers_id, de_type, de_id, code_lien, poids FROM arete;

DELETE FROM chemin;
WITH RECURSIVE
  param(seuil, prof) AS (
      SELECT (SELECT valeur FROM parametre WHERE nom = 'seuil_chemin'),
             (SELECT valeur FROM parametre WHERE nom = 'profondeur_max')),
  parcours(bl, t, i, d, force, visite, trace) AS (
      SELECT CAST(a.de_id AS INTEGER), a.vers_type, a.vers_id, 1, a.poids,
             '|bl:' || a.de_id || '|' || a.vers_type || ':' || a.vers_id || '|',
             '[' || a.code_lien || '] ' || na.libelle
      FROM arete a
      JOIN noeud na ON na.type = a.vers_type AND na.id = a.vers_id, param
      WHERE a.de_type = 'bl' AND a.poids >= param.seuil
      UNION ALL
      SELECT p.bl, a.vers_type, a.vers_id, p.d + 1, p.force * a.poids,
             p.visite || a.vers_type || ':' || a.vers_id || '|',
             p.trace || ' → [' || a.code_lien || '] ' || na.libelle
      FROM parcours p
      JOIN arete a  ON a.de_type = p.t AND a.de_id = p.i
      JOIN noeud na ON na.type = a.vers_type AND na.id = a.vers_id, param
      WHERE p.t <> 'bl'
        AND p.d < param.prof
        AND p.force * a.poids >= param.seuil
        AND instr(p.visite, '|' || a.vers_type || ':' || a.vers_id || '|') = 0
  )
INSERT INTO chemin (bl_entite_id, cible_type, cible_id, profondeur, force, trace)
SELECT bl, t, i, d, max(force), trace
FROM parcours
GROUP BY bl, t, i;
