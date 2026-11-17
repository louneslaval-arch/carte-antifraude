-- EQDOM: adaptation des 16 vues SQLite pour PostgreSQL 17.
-- Pre-requis : tables importees et donnees controlees.
-- Execution conseillee: psql -v ON_ERROR_STOP=1 -f vues_postgresql.sql
-- Toutes les vues sont creees dans une transaction : aucune creation partielle.
BEGIN;

CREATE OR REPLACE VIEW v_af_dossier_signale AS
  SELECT d.ref, d.lot, d.type_personne, d.client_nom, d.verdict, d.recu_le, l.regle, l.niveau, di.role, i.nom AS identite, l.cible, l.cible_id, l.detail
  FROM af_lien l JOIN af_identite i USING (identite_id) JOIN af_dossier_identite di USING (identite_id) JOIN af_dossier d ON d.ref = di.dossier_ref
  WHERE l.cible = 'bl_entite';

CREATE OR REPLACE VIEW v_af_identite_multi AS
  SELECT i.*, (SELECT string_agg(dossier_ref::text || ' (' || role::text || ')', ' ; ' ORDER BY dossier_ref::text, role::text) FROM af_dossier_identite d WHERE d.identite_id = i.identite_id) AS dossiers
  FROM af_identite i WHERE i.nb_dossiers >= 2 AND i.niveau_cle = 'fort';

CREATE OR REPLACE VIEW v_af_lien AS
  SELECT l.lien_id, l.regle, l.niveau, i.type_identite, i.nom AS nom_dossier, i.cin_norm, i.rc_num, i.tribunal_code,
         i.nb_dossiers, i.roles, l.dossier_ref, l.cible, l.cible_id, l.cle_type, l.cle_valeur, l.detail,
         CASE l.cible WHEN 'bl_entite' THEN (SELECT nom_affiche FROM bl_entite WHERE entite_id::text = l.cible_id::text)
                      WHEN 'rc_societe' THEN (SELECT denomination FROM rc_societe WHERE societe_id::text = l.cible_id::text)
                      WHEN 'rc_personne' THEN (SELECT nom_complet FROM rc_personne WHERE personne_id::text = l.cible_id::text) END AS nom_cible
  FROM af_lien l LEFT JOIN af_identite i USING (identite_id);

CREATE OR REPLACE VIEW v_bilan AS
          SELECT 1 AS ordre, 'Inscriptions en liste noire (03/08/2026)' AS indicateur, count(*) AS valeur FROM bl_inscription
UNION ALL SELECT 2, 'Entités inscrites (personnes + sociétés)', count(*) FROM bl_entite
UNION ALL SELECT 3, '  dont personnes physiques', count(*) FROM bl_entite WHERE type_entite = 'PP'
UNION ALL SELECT 4, '  dont sociétés', count(*) FROM bl_entite WHERE type_entite = 'PM'
UNION ALL SELECT 5, 'Entités avec une clé dure (CIN ou RC)', count(*) FROM bl_entite WHERE rattachement = 'cle_dure'
UNION ALL SELECT 6, 'Entités rapprochables par le nom seulement', count(*) FROM bl_entite WHERE rattachement = 'nom'
UNION ALL SELECT 7, 'Entités sans aucune clé', count(*) FROM bl_entite WHERE rattachement = 'aucun'
UNION ALL SELECT 8, 'Anomalies relevées dans la liste noire', count(*) FROM bl_anomalie
UNION ALL SELECT 9, 'Annonces légales chargées', count(*) FROM rc_annonce
UNION ALL SELECT 10, 'Sociétés du registre', count(*) FROM rc_societe
UNION ALL SELECT 11, 'Personnes citées (une par société)', count(*) FROM rc_personne
UNION ALL SELECT 11.1, '  mentions dans les annonces', count(*) FROM rc_mention
UNION ALL SELECT 11.2, '  entrées écartées (faux noms, phrases, gabarits)', count(*) FROM rc_rejet
UNION ALL SELECT 11.3, 'Sociétés dont le RC porte des noms incompatibles (séparées)', count(*) FROM rc_societe WHERE rc_conflit::text IN ('1', 'true', 't')
UNION ALL SELECT 12, 'Correspondances certaines (alerte)', count(*) FROM correspondance_retenue WHERE niveau = 'certain' AND statut <> 'ecarte'
UNION ALL SELECT 13, 'Correspondances probables (à lever par un analyste)', count(*) FROM correspondance_retenue WHERE statut IN ('homonymie', 'a_verifier')
UNION ALL SELECT 14, 'Correspondances faibles (sous le seuil, masquées)', count(*) FROM correspondance_retenue WHERE statut = 'faible'
UNION ALL SELECT 15, 'Inscrits reliés au registre (hors liens faibles)', count(DISTINCT bl_entite_id) FROM correspondance_retenue WHERE statut NOT IN ('ecarte', 'faible')
UNION ALL SELECT 16, 'Sociétés du registre atteintes par un chemin', count(DISTINCT cible_id) FROM chemin WHERE cible_type = 'rc_societe';

CREATE OR REPLACE VIEW v_bl_fiche AS
SELECT e.*,
       (SELECT count(*) FROM correspondance_retenue c
         WHERE c.bl_entite_id = e.entite_id AND c.niveau = 'certain' AND c.statut <> 'ecarte')  AS liens_certains,
       (SELECT count(*) FROM correspondance_retenue c
         WHERE c.bl_entite_id = e.entite_id AND c.statut IN ('homonymie', 'a_verifier'))       AS liens_probables
FROM bl_entite e;

CREATE OR REPLACE VIEW v_chemin AS
SELECT e.cle_entite, e.nom_affiche AS inscrit, c.cible_type, n.libelle AS cible,
       c.profondeur, round(c.force::numeric, 3) AS force, c.trace, c.bl_entite_id, c.cible_id
FROM chemin c
JOIN bl_entite e  ON e.entite_id = c.bl_entite_id
LEFT JOIN noeud n ON n.type = c.cible_type AND n.id::text = c.cible_id::text;

-- SQLite returned arbitrary non-grouped columns here. PostgreSQL version
-- deterministically selects the strongest path for each company.
CREATE OR REPLACE VIEW v_controle_employeur AS
WITH chemins AS (
  SELECT s.societe_id, s.denomination, s.rc_num, s.tribunal_code, s.ville_code,
         c.bl_entite_id, c.force, c.profondeur, c.trace,
         e.nom_affiche,
         row_number() OVER (
           PARTITION BY s.societe_id
           ORDER BY c.force DESC NULLS LAST, c.profondeur ASC NULLS LAST,
                    c.bl_entite_id ASC
         ) AS rang
  FROM chemin c
  JOIN rc_societe s ON s.societe_id::text = c.cible_id::text
  JOIN bl_entite e ON e.entite_id = c.bl_entite_id
  WHERE c.cible_type = 'rc_societe'
), totaux AS (
  SELECT societe_id, count(DISTINCT bl_entite_id) AS inscrits_relies,
         round(max(force)::numeric, 3) AS force_max
  FROM chemins GROUP BY societe_id
)
SELECT ch.societe_id, ch.denomination, ch.rc_num, ch.tribunal_code, ch.ville_code,
       t.inscrits_relies, t.force_max,
       ch.profondeur AS profondeur_meilleur_chemin,
       ch.nom_affiche AS inscrit_le_plus_proche,
       ch.trace AS meilleur_chemin
FROM chemins ch JOIN totaux t ON t.societe_id = ch.societe_id
WHERE ch.rang = 1;

CREATE OR REPLACE VIEW v_correspondance AS
SELECT c.statut, c.niveau, c.regle, r.libelle AS regle_libelle, c.nature, round(c.poids::numeric, 3) AS poids,
       e.cle_entite, e.type_entite, e.nom_affiche AS inscrit, e.cin AS inscrit_cin, e.rc_num AS inscrit_rc,
       e.types_liste, e.motifs,
       s.denomination, s.rc_num, s.tribunal_code, s.ville_code AS ville_siege,
       p.nom_complet AS personne_registre, p.roles AS role_registre, p.cin AS cin_registre, p.nb_mentions,
       a.source, a.type_acte, a.date_publication, a.annonce_id, a.url,
       c.cle_type, c.cle_valeur, c.confirmation, c.regles_touchees,
       CASE c.rc_objet WHEN 'rc_personne' THEN p.cle_stable ELSE s.cle_societe END AS cle_rc,
       c.rc_objet, c.rc_objet_id, c.bl_entite_id
FROM correspondance_retenue c
JOIN bl_entite e             ON e.entite_id = c.bl_entite_id
LEFT JOIN ref_regle r        ON r.regle = c.regle
LEFT JOIN rc_personne p      ON c.rc_objet = 'rc_personne' AND p.personne_id::text = c.rc_objet_id::text
LEFT JOIN rc_societe s       ON s.societe_id::text = c.societe_id::text
LEFT JOIN rc_annonce a       ON a.annonce_id = coalesce(
        (SELECT m.annonce_id FROM rc_mention m WHERE m.personne_id = p.personne_id ORDER BY m.annonce_id DESC LIMIT 1),
        (SELECT x.annonce_id FROM rc_annonce x WHERE x.societe_id = s.societe_id ORDER BY x.date_publication DESC LIMIT 1));

CREATE OR REPLACE VIEW v_couverture_regles AS
SELECT c.regle, r.libelle, c.niveau, c.nature, count(*) AS correspondances,
       count(DISTINCT c.bl_entite_id) AS inscrits, count(DISTINCT c.societe_id) AS societes
FROM correspondance c LEFT JOIN ref_regle r ON r.regle = c.regle
GROUP BY c.regle, r.libelle, c.niveau, c.nature ORDER BY c.regle;

CREATE OR REPLACE VIEW v_homonymies_a_traiter AS
SELECT * FROM v_correspondance WHERE statut IN ('homonymie', 'a_verifier') ORDER BY poids DESC;

CREATE OR REPLACE VIEW v_intermediaire_signale AS
SELECT a.titre AS intermediaire, count(DISTINCT a.societe_id) AS societes_reliees,
       string_agg(DISTINCT s.denomination::text, ',') AS societes
FROM rc_annonce a
JOIN rc_societe s ON s.societe_id::text = a.societe_id::text
WHERE a.titre IS NOT NULL AND a.titre <> a.denomination
  AND a.societe_id IN (SELECT societe_id FROM correspondance_retenue WHERE statut NOT IN ('ecarte', 'faible'))
GROUP BY a.titre
HAVING count(DISTINCT a.societe_id) >= 2
ORDER BY societes_reliees DESC;

CREATE OR REPLACE VIEW v_qualite_bl AS
SELECT anomalie, champ, traitement, count(*) AS nb
FROM bl_anomalie GROUP BY anomalie, champ, traitement ORDER BY nb DESC;

CREATE OR REPLACE VIEW v_qualite_rc AS
          SELECT 'Entrée personne écartée' AS controle, motif AS detail, count(*) AS nb FROM rc_rejet GROUP BY motif
UNION ALL SELECT 'Numéro RC', rc_statut, count(*) FROM rc_annonce GROUP BY rc_statut
UNION ALL SELECT 'Dénomination', denomination_statut, count(*) FROM rc_annonce GROUP BY denomination_statut
UNION ALL SELECT 'Annonce issue d''un bloc mélangé', CAST(bloc_mixte AS TEXT), count(*) FROM rc_annonce GROUP BY bloc_mixte
UNION ALL SELECT 'Tribunal reconnu', CASE WHEN tribunal_code IS NULL THEN 'non' ELSE 'oui' END, count(*) FROM rc_annonce GROUP BY 2
ORDER BY 1, 3 DESC;

CREATE OR REPLACE VIEW v_rc_societe_fiche AS
SELECT s.*,
       (SELECT string_agg(coalesce(p.nom_complet::text, 'CIN ' || p.cin::text) || ' (' || p.role::text || ')', ' ; ' ORDER BY p.personne_id)
          FROM rc_personne p WHERE p.societe_id = s.societe_id) AS personnes_citees
FROM rc_societe s;

CREATE OR REPLACE VIEW v_reseau_inscrits AS
SELECT e1.nom_affiche AS inscrit, e2.nom_affiche AS autre_inscrit, c.profondeur, round(c.force::numeric, 3) AS force, c.trace
FROM chemin c
JOIN bl_entite e1 ON e1.entite_id = c.bl_entite_id
JOIN bl_entite e2 ON e2.entite_id::text = c.cible_id::text
WHERE c.cible_type = 'bl' AND c.bl_entite_id < CAST(c.cible_id AS BIGINT);

CREATE OR REPLACE VIEW v_societe_signalee AS
SELECT s.societe_id, s.denomination, s.rc_num, s.tribunal_code, s.ville_code,
       bool_or(c.nature = 'identite' AND c.rc_objet = 'rc_societe')::integer                                        AS societe_inscrite,
       count(DISTINCT CASE WHEN c.rc_objet = 'rc_personne' AND c.niveau = 'certain'  THEN c.bl_entite_id END) AS personnes_inscrites_certaines,
       count(DISTINCT CASE WHEN c.rc_objet = 'rc_personne' AND c.niveau = 'probable' THEN c.bl_entite_id END) AS personnes_inscrites_probables,
       count(DISTINCT CASE WHEN c.nature = 'emploi' THEN c.bl_entite_id END)                           AS inscrits_employes,
       round(max(c.poids)::numeric, 3) AS poids_max,
       string_agg(DISTINCT c.regle::text, ',') AS regles
FROM correspondance_retenue c
JOIN rc_societe s ON s.societe_id::text = c.societe_id::text
WHERE c.statut NOT IN ('ecarte', 'faible')
GROUP BY s.societe_id;
COMMIT;
