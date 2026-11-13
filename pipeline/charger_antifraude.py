#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
charger_antifraude.py — ajoute à la base les données extraites des dossiers de l'antifraude (export « antifraude_export_complet »),
reconstitue une identité par personne et par société, puis crée les liens avec la liste noire et le registre du commerce.

  python3 charger_antifraude.py --base bl_rc.sqlite --export antifraude_export_complet_2026-11-10

Lots lus : 1_donnees_prod (référence) et 2_donnees_preprod (historique depuis juillet). Rien n'est modifié dans les tables
bl_* et rc_* : tout est dans des tables af_* (supprimées et recréées à chaque passage).

Tables
  af_dossier            un dossier (contexte métier, verdict, date)
  af_personne           une personne lue dans une pièce d'un dossier (CIN, statuts, extrait RC, attestation, bulletin, RIB…)
  af_societe            une société lue dans une pièce (extrait RC, statuts, employeur, vendeur)
  af_compte             un RIB lu dans un relevé ou une attestation de RIB
  af_tiers              tiers bancaires par dossier (libellés des virements, agrégés) — aide de lecture, jamais une identité
  af_identite           une personne (clé = CIN) ou une société (clé = RC + tribunal, sinon ICE, sinon nom dans le dossier)
  af_dossier_identite   qui apparaît dans quel dossier, avec quel rôle
  af_relation           personne –gérant / associé / dirigeant / salarié– société, d'après les dossiers
  af_lien               liens créés : identité ↔ liste noire, ↔ société du registre, ↔ personne du registre, RIB partagés…
  af_cin_apporte        CIN qu'un dossier apporte à une personne du registre qui n'en avait pas

Règles de lien (af_lien.regle)
  AF01  personne d'un dossier = personne inscrite (même CIN)                                   certain
  AF01n personne d'un dossier sans CIN = inscrit sans CIN (même nom, mêmes mots)               à vérifier
  AF02  société d'un dossier = société inscrite (même RC et même tribunal, noms compatibles)   certain
  AF02n même RC et même tribunal, noms différents                                              à vérifier
  AF02b même RC, liste noire sans tribunal, noms compatibles (le dossier donne le tribunal)    probable
  AF02c même ICE                                                                               certain
  AF02d même raison sociale et même ville, liste noire sans RC                                 à vérifier
  AF03  société d'un dossier = société du registre (même RC et même tribunal, noms compatibles) certain
  AF03n même RC et même tribunal, noms différents                                              à vérifier
  AF04  personne d'un dossier = personne du registre (même CIN)                                certain
  AF05  gérant ou associé d'un dossier = personne du registre de la même société (AF03) au nom compatible :
        le dossier apporte le CIN                                                              certain (société + nom)
  AF07  employeur d'un dossier = société inscrite ou employeur déclaré d'un inscrit (même raison sociale)  à vérifier
  AF03b même RC et même tribunal, dénomination non lue au registre (le dossier la donne)       probable
  AF09  même RIB dans des dossiers de clients différents et sans lien entre eux                indice
  AF11  tiers bancaire d'un relevé = inscrit (mêmes mots du nom ou de la raison sociale)       indice (faible si nom courant)
  AF20  identité d'un dossier retrouvée au registre et située sur un chemin partant d'un inscrit  réseau à N arêtes
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import construire_base as cb  # noqa: E402

csv.field_size_limit(10 ** 9)
LOTS = (('prod', '1_donnees_prod'), ('preprod', '2_donnees_preprod'))
CIN_FACTICES = {'12345', '123456', '1234567', '000000', '0000000', '111111', '999999'}
NOMS_FACTICES = {'JOHN DOE', 'JANE DOE', 'NOM PRENOM', 'PRENOM NOM', 'XXX XXX', 'TEST TEST'}  # fictif-volontaire : valeurs gabarits écartées
VIDES = {'', 'NEANT', 'NULL', 'NONE', 'N/A', 'NA', 'NAN', '-', '--', 'NON RENSEIGNE', 'INCONNU', '{}', '[]'}

SCHEMA = """
DROP TABLE IF EXISTS af_dossier; DROP TABLE IF EXISTS af_personne; DROP TABLE IF EXISTS af_societe; DROP TABLE IF EXISTS af_compte;
DROP TABLE IF EXISTS af_tiers; DROP TABLE IF EXISTS af_identite; DROP TABLE IF EXISTS af_dossier_identite; DROP TABLE IF EXISTS af_relation;
DROP TABLE IF EXISTS af_lien; DROP TABLE IF EXISTS af_cin_apporte;
DROP VIEW IF EXISTS v_af_lien; DROP VIEW IF EXISTS v_af_identite_multi; DROP VIEW IF EXISTS v_af_dossier_signale;
CREATE TABLE af_dossier (
  ref TEXT PRIMARY KEY, lot TEXT NOT NULL,            -- prod / preprod
  actif INTEGER, type_personne TEXT,                  -- PP / PM
  csp TEXT, produit TEXT, mode_paiement TEXT,
  client_nom TEXT, client_cin TEXT, client_cin_norm TEXT, client_adresse TEXT, ville_code TEXT,
  client_connu INTEGER, employeur_declare TEXT, revenu_declare REAL, organisme_pension TEXT,
  categorie TEXT, verdict TEXT, statut_analyse TEXT, alertes_mineures INTEGER, alertes_majeures INTEGER, alertes_critiques INTEGER,
  recu_le TEXT, nb_pieces INTEGER DEFAULT 0);
CREATE TABLE af_personne (
  af_personne_id INTEGER PRIMARY KEY, dossier_ref TEXT NOT NULL REFERENCES af_dossier(ref), lot TEXT,
  role TEXT NOT NULL,                                 -- demandeur, representant, gerant, associe, dirigeant, signataire, salarie, pensionne, titulaire_compte, titulaire_carte_grise
  nom_complet TEXT, nom TEXT, prenom TEXT, cle_nom TEXT,
  cin_brut TEXT, cin_norm TEXT, cin_statut TEXT,
  date_naissance TEXT, lieu_naissance TEXT, adresse TEXT, ville_code TEXT, nom_pere TEXT, nom_mere TEXT, nationalite TEXT,
  qualite TEXT, parts TEXT,
  piece_type TEXT, piece_id TEXT, source TEXT,        -- AMONT (lecture EQDOM / Tandem AI) ou REANALYSE (relecture)
  societe_af_id INTEGER,                              -- société de la même pièce (gérant, associé) ou employeur
  identite_id INTEGER);
CREATE TABLE af_societe (
  af_societe_id INTEGER PRIMARY KEY, dossier_ref TEXT NOT NULL REFERENCES af_dossier(ref), lot TEXT,
  role TEXT NOT NULL,                                 -- societe_cliente, societe_du_client, employeur, vendeur
  denomination TEXT, cle_rs TEXT, forme_juridique TEXT,
  rc_brut TEXT, rc_num TEXT, tribunal_code TEXT, ice TEXT,
  adresse TEXT, ville_code TEXT, date_creation TEXT, capital TEXT, objet TEXT, origine_fonds TEXT,
  piece_type TEXT, piece_id TEXT, source TEXT, identite_id INTEGER);
CREATE TABLE af_compte (
  af_compte_id INTEGER PRIMARY KEY, dossier_ref TEXT NOT NULL REFERENCES af_dossier(ref), lot TEXT,
  rib TEXT NOT NULL, banque TEXT, titulaire TEXT, type_titulaire TEXT, piece_type TEXT, piece_id TEXT);
CREATE TABLE af_tiers (
  dossier_ref TEXT NOT NULL, lot TEXT, tiers TEXT NOT NULL, cle TEXT, type_cle TEXT,     -- NOM (personne) ou RS (société)
  nb_operations INTEGER, total_credit REAL, total_debit REAL, PRIMARY KEY (dossier_ref, tiers));
CREATE TABLE af_identite (
  identite_id INTEGER PRIMARY KEY, type_identite TEXT NOT NULL,     -- PP / PM
  cle TEXT UNIQUE NOT NULL,                           -- C:<CIN> · N:<dossier>:<nom> · R:<RC>@<tribunal> · I:<ICE> · D:<dossier>:<raison sociale> · E:<raison sociale> (employeur, vendeur)
  niveau_cle TEXT NOT NULL,                           -- fort (CIN, RC + tribunal, ICE) ou faible (nom seul)
  nom TEXT, autres_noms TEXT, cin_norm TEXT, rc_num TEXT, tribunal_code TEXT, ice TEXT,
  date_naissance TEXT, ville_code TEXT, adresse TEXT,
  nb_dossiers INTEGER DEFAULT 0, roles TEXT, premier_dossier TEXT, dernier_dossier TEXT);
CREATE TABLE af_dossier_identite (
  dossier_ref TEXT NOT NULL, identite_id INTEGER NOT NULL, role TEXT NOT NULL, piece_types TEXT,
  PRIMARY KEY (dossier_ref, identite_id, role));
CREATE TABLE af_relation (
  relation_id INTEGER PRIMARY KEY, pp_identite_id INTEGER NOT NULL, pm_identite_id INTEGER NOT NULL,
  role TEXT NOT NULL, qualite TEXT, parts TEXT, dossier_ref TEXT, piece_type TEXT, source TEXT);
CREATE TABLE af_lien (
  lien_id INTEGER PRIMARY KEY, regle TEXT NOT NULL, niveau TEXT NOT NULL,       -- certain / probable / à vérifier / indice
  identite_id INTEGER, dossier_ref TEXT,
  cible TEXT NOT NULL,                                -- bl_entite / rc_societe / rc_personne / af_dossier
  cible_id TEXT NOT NULL, cle_type TEXT, cle_valeur TEXT, detail TEXT);
CREATE TABLE af_cin_apporte (
  personne_id INTEGER NOT NULL,                       -- rc_personne
  societe_id INTEGER NOT NULL, cin_norm TEXT NOT NULL, identite_id INTEGER NOT NULL,
  nom_dossier TEXT, nom_registre TEXT, role_dossier TEXT, dossier_ref TEXT,
  etat TEXT NOT NULL,                                 -- apporte (le registre n'avait pas de CIN) / confirme (même CIN) / conflit (CIN différent)
  PRIMARY KEY (personne_id, cin_norm));
CREATE INDEX af_personne_dossier ON af_personne(dossier_ref); CREATE INDEX af_personne_cin ON af_personne(cin_norm);
CREATE INDEX af_personne_ident ON af_personne(identite_id); CREATE INDEX af_societe_dossier ON af_societe(dossier_ref);
CREATE INDEX af_societe_ident ON af_societe(identite_id); CREATE INDEX af_compte_rib ON af_compte(rib);
CREATE INDEX af_lien_ident ON af_lien(identite_id); CREATE INDEX af_lien_cible ON af_lien(cible, cible_id);
CREATE INDEX af_di_ident ON af_dossier_identite(identite_id); CREATE INDEX af_tiers_cle ON af_tiers(cle);
CREATE VIEW v_af_lien AS
  SELECT l.lien_id, l.regle, l.niveau, i.type_identite, i.nom AS nom_dossier, i.cin_norm, i.rc_num, i.tribunal_code,
         i.nb_dossiers, i.roles, l.dossier_ref, l.cible, l.cible_id, l.cle_type, l.cle_valeur, l.detail,
         CASE l.cible WHEN 'bl_entite' THEN (SELECT nom_affiche FROM bl_entite WHERE entite_id = l.cible_id)
                      WHEN 'rc_societe' THEN (SELECT denomination FROM rc_societe WHERE societe_id = l.cible_id)
                      WHEN 'rc_personne' THEN (SELECT nom_complet FROM rc_personne WHERE personne_id = l.cible_id) END AS nom_cible
  FROM af_lien l LEFT JOIN af_identite i USING (identite_id);
CREATE VIEW v_af_identite_multi AS
  SELECT i.*, (SELECT group_concat(dossier_ref || ' (' || role || ')', ' ; ') FROM af_dossier_identite d WHERE d.identite_id = i.identite_id) AS dossiers
  FROM af_identite i WHERE i.nb_dossiers >= 2 AND i.niveau_cle = 'fort';
CREATE VIEW v_af_dossier_signale AS
  SELECT d.ref, d.lot, d.type_personne, d.client_nom, d.verdict, d.recu_le, l.regle, l.niveau, di.role, i.nom AS identite, l.cible, l.cible_id, l.detail
  FROM af_lien l JOIN af_identite i USING (identite_id) JOIN af_dossier_identite di USING (identite_id) JOIN af_dossier d ON d.ref = di.dossier_ref
  WHERE l.cible = 'bl_entite';
"""


# ---- lecture ------------------------------------------------------------------------------------------------------
def v(x):
    """Valeur nettoyée ou None (« Neant », « null », vide…)."""
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return x or None
    s = ' '.join(str(x).split())
    return None if cb.latin_maj(s) in VIDES or not s else s


def lire_csv(chemin):
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def lire_jsonl(chemin):
    if not os.path.exists(chemin):
        return []
    out = []
    with open(chemin, encoding='utf-8') as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                out.append(json.loads(ligne))
    return out


def norm_cin(x):
    x = v(x)
    if not x or isinstance(x, (dict, list)):
        return None, None, 'absent'
    n, st = cb.normalise_cin(x)
    if st not in ('valide', 'lettre_finale'):
        return x, None, st
    if re.sub(r'\D', '', n) in CIN_FACTICES:                    # « A123456 », « BK12345 » : valeur d'exemple rendue par le modèle de lecture  # fictif-volontaire
        return x, None, 'factice'
    return x, n, st


def norm_rc(x):
    x = v(x)
    if not x or isinstance(x, (dict, list)):
        return None, None
    t = re.sub(r'(?<=\d)[\s.](?=\d)', '', str(x))              # « 12 345 » → 12345
    num, _ind, st = cb.normalise_rc(t)
    return x, (num if st == 'rc' and num and num != '0' else None)


def norm_ice(x):
    x = v(x)
    if not x or isinstance(x, (dict, list)):
        return None
    t = re.sub(r'\D', '', str(x))
    return t if len(t) == 15 and t.strip('0') else None


def ville(*textes):
    for t in textes:
        t = v(t)
        if t and not isinstance(t, (dict, list)):
            c = cb.villes_dans(t)
            if c:
                return c
    return None


def nom_complet(nom, prenom, complet=None):
    nom, prenom, complet = v(nom), v(prenom), v(complet)
    if isinstance(complet, (dict, list)):
        complet = None
    if nom and prenom:
        return f'{prenom} {nom}'.upper() if not cb.est_arabe(nom + prenom) else f'{prenom} {nom}'
    return (complet or nom or prenom or '').upper() or None


def sous(d, *cles):
    """Premier champ non vide parmi des clés, y compris imbriquées « employeur.raison_sociale »."""
    for c in cles:
        cur = d
        ok = True
        for part in c.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and c in d:
            cur = d[c]
        if ok:
            x = v(cur)
            if x is not None and not isinstance(x, (dict, list)):
                return x
        if c in d:
            x = v(d[c])
            if x is not None and not isinstance(x, (dict, list)):
                return x
    return None


class Chargeur:
    def __init__(self, con):
        self.con = con
        self.personnes, self.societes, self.comptes = [], [], []
        self.dossiers = {}
        self.soc_par_piece = {}

    def personne(self, ref, lot, role, nom=None, prenom=None, complet=None, cin=None, piece_type=None, piece_id=None, source=None,
                 societe=None, **k):
        nc = nom_complet(nom, prenom, complet)
        cin_brut, cin_norm, cin_statut = norm_cin(cin)
        if not nc and not cin_norm:
            return None
        if nc and (len(nc) < 3 or cb.latin_maj(nc) in VIDES or cb.latin_maj(nc) in NOMS_FACTICES):
            nc = None
            if not cin_norm:
                return None
        p = dict(dossier_ref=ref, lot=lot, role=role, nom_complet=nc, nom=(v(nom) or None), prenom=(v(prenom) or None),
                 cle_nom=cb.cle_nom(nc) if nc else None, cin_brut=cin_brut, cin_norm=cin_norm, cin_statut=cin_statut,
                 date_naissance=cb.date_iso(v(k.get('date_naissance'))) if not isinstance(v(k.get('date_naissance')), (dict, list)) else None,
                 lieu_naissance=v(k.get('lieu_naissance')), adresse=v(k.get('adresse')),
                 ville_code=ville(k.get('ville'), k.get('adresse')), nom_pere=v(k.get('nom_pere')), nom_mere=v(k.get('nom_mere')),
                 nationalite=v(k.get('nationalite')), qualite=v(k.get('qualite')), parts=v(k.get('parts')),
                 piece_type=piece_type, piece_id=piece_id, source=source, societe=societe)
        for c in ('lieu_naissance', 'adresse', 'nom_pere', 'nom_mere', 'nationalite', 'qualite', 'parts'):
            if isinstance(p[c], (dict, list)):
                p[c] = None
            elif p[c] is not None:
                p[c] = str(p[c])
        self.personnes.append(p)
        return p

    def societe(self, ref, lot, role, denomination=None, rc=None, tribunal=None, ice=None, piece_type=None, piece_id=None, source=None, **k):
        den = v(denomination)
        if isinstance(den, (dict, list)):
            den = None
        rc_brut, rc_num = norm_rc(rc)
        ice_n = norm_ice(ice)
        if not den and not rc_num and not ice_n:
            return None
        trib = None
        t = v(tribunal)
        if t and not isinstance(t, (dict, list)):
            trib = cb.tribunal_code(t)[0]
        s = dict(dossier_ref=ref, lot=lot, role=role, denomination=den.upper() if den and not cb.est_arabe(den) else den,
                 cle_rs=cb.cle_rs(den) if den else None, forme_juridique=v(k.get('forme')), rc_brut=rc_brut, rc_num=rc_num,
                 tribunal_code=trib, ice=ice_n, adresse=v(k.get('adresse')), ville_code=ville(k.get('ville'), k.get('adresse')) or (trib if role in ('societe_cliente', 'societe_du_client') else None),
                 date_creation=cb.date_iso(v(k.get('date_creation'))) if not isinstance(v(k.get('date_creation')), (dict, list)) else None,
                 capital=v(k.get('capital')), objet=v(k.get('objet')), origine_fonds=v(k.get('origine_fonds')),
                 piece_type=piece_type, piece_id=piece_id, source=source)
        for c in ('forme_juridique', 'adresse', 'capital', 'objet', 'origine_fonds'):
            if isinstance(s[c], (dict, list)):
                s[c] = None
            elif s[c] is not None:
                s[c] = str(s[c])[:600]
        self.societes.append(s)
        if piece_id and role in ('societe_cliente', 'societe_du_client'):
            self.soc_par_piece[piece_id] = s
        return s

    # ---- un lot ----
    def lot(self, lot, dossier):
        t0 = time.time()
        for r in lire_csv(os.path.join(dossier, 'dossiers.csv')):
            cin_brut, cin_norm, _st = norm_cin(r.get('bd_civil_cin'))
            self.dossiers[r['ref']] = dict(
                ref=r['ref'], lot=lot, actif=1 if r.get('actif') == 'true' else 0, type_personne=v(r.get('personType')),
                csp=v(r.get('csp')), produit=v(r.get('productType')), mode_paiement=v(r.get('paymentMode')),
                client_nom=(v(r.get('bd_civil_full_name')) or v(r.get('clientName')) or None),
                client_cin=cin_brut, client_cin_norm=cin_norm, client_adresse=v(r.get('bd_civil_address')),
                ville_code=ville(r.get('bd_civil_address')), client_connu=1 if r.get('bd_known_client') == 'true' else 0 if r.get('bd_known_client') == 'false' else None,
                employeur_declare=v(r.get('bd_declared_employer')),
                revenu_declare=float(r['bd_declared_monthly_income']) if re.fullmatch(r'\d+(\.\d+)?', r.get('bd_declared_monthly_income') or '') else None,
                organisme_pension=v(r.get('bd_declared_pension_organism')), categorie=v(r.get('category')), verdict=v(r.get('verdict')),
                statut_analyse=v(r.get('analysisStatus')), alertes_mineures=int(r.get('alertsMinor') or 0),
                alertes_majeures=int(r.get('alertsMajor') or 0), alertes_critiques=int(r.get('alertsCritical') or 0),
                recu_le=(v(r.get('businessReceivedAt')) or v(r.get('createdAt')) or '')[:10] or None, nb_pieces=0)
        refs = {r for r, d in self.dossiers.items() if d['lot'] == lot}

        def tp(ref):
            return self.dossiers[ref]['type_personne'] if ref in self.dossiers else None

        # contexte métier : le client déclaré
        for ref in refs:
            d = self.dossiers[ref]
            if d['type_personne'] == 'PM':
                if d['client_nom']:
                    self.societe(ref, lot, 'societe_cliente', d['client_nom'], adresse=d['client_adresse'], piece_type='CONTEXTE', source='AMONT')
                if d['client_cin_norm']:
                    self.personne(ref, lot, 'representant', cin=d['client_cin'], piece_type='CONTEXTE', source='AMONT')
            elif d['client_nom'] or d['client_cin_norm']:
                self.personne(ref, lot, 'demandeur', complet=d['client_nom'], cin=d['client_cin'], adresse=d['client_adresse'],
                              piece_type='CONTEXTE', source='AMONT')
        # CIN
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'cin.csv')):
            ref = r['dossier_ref']
            if ref not in refs:
                continue
            self.dossiers[ref]['nb_pieces'] += 1
            self.personne(ref, lot, 'representant' if tp(ref) == 'PM' else 'demandeur', r.get('nom'), r.get('prenom'),
                          cin=v(r.get('cin')) or v(r.get('id_document_recto')) or v(r.get('mrz_optional_data')),
                          date_naissance=r.get('date_naissance'), lieu_naissance=r.get('lieu_naissance'), adresse=r.get('adresse'),
                          ville=r.get('ville_residence'), nom_pere=r.get('nom_pere'), nom_mere=r.get('nom_mere'), nationalite=r.get('nationalite'),
                          piece_type='CIN', piece_id=r['piece_id'], source=r.get('source'))
        # extraits du registre du commerce et statuts
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'registre_commerce.csv')):
            ref = r['dossier_ref']
            if ref not in refs:
                continue
            self.dossiers[ref]['nb_pieces'] += 1
            self.societe(ref, lot, 'societe_cliente' if tp(ref) == 'PM' else 'societe_du_client', r.get('denomination_sociale'), r.get('numero_rc'),
                         r.get('ville_tribunal'), r.get('ice'), forme=r.get('forme_juridique'),
                         adresse=v(r.get('adresse_siege')) or v(r.get('adresse_principal_etablissement')), date_creation=r.get('date_creation'),
                         capital=r.get('capital_social'), objet=r.get('objet_social'), origine_fonds=r.get('origine_fond'),
                         piece_type='REGISTRE_COMMERCE', piece_id=r['piece_id'], source=r.get('source'))
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'statuts.csv')):
            ref = r['dossier_ref']
            if ref not in refs:
                continue
            self.dossiers[ref]['nb_pieces'] += 1
            self.societe(ref, lot, 'societe_cliente' if tp(ref) == 'PM' else 'societe_du_client', r.get('denomination_sociale'),
                         forme=r.get('forme_juridique'), adresse=r.get('adresse_siege'), capital=r.get('capital_social'), objet=r.get('objet_social'),
                         piece_type='STATUTS', piece_id=r['piece_id'], source=r.get('source'))
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'gerants_associes_dirigeants.csv')):
            ref = r['dossier_ref']
            if ref not in refs:
                continue
            tpers = cb.latin_maj(r.get('type_personne') or '')
            if 'MORALE' in tpers:
                continue                                           # associé personne morale : pas une personne physique
            role = {'gerant': 'gerant', 'associe': 'associe', 'dirigeant': 'dirigeant', 'signataire': 'signataire',
                    'associe_present': 'associe', 'nouveau_gerant': 'gerant'}.get(r.get('role'), r.get('role') or 'dirigeant')
            dn = r.get('date_naissance')
            if dn in ('01/01/1900', '01/01/1990'):                 # valeurs par défaut du formulaire
                dn = None
            self.personne(ref, lot, role, r.get('nom'), r.get('prenom'), r.get('nom_complet'), r.get('cin'), date_naissance=dn,
                          adresse=r.get('adresse'), ville=r.get('ville_residence'), nationalite=r.get('nationalite'), qualite=r.get('qualite'),
                          parts=v(r.get('parts_sociales')) or v(r.get('nombre_actions')), piece_type=r.get('piece_type'), piece_id=r['piece_id'],
                          source=r.get('source'), societe=self.soc_par_piece.get(r['piece_id']))
        # relevés et attestations de RIB
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'releves.csv')):
            ref = r['dossier_ref']
            if ref not in refs:
                continue
            self.dossiers[ref]['nb_pieces'] += 1
            rib = re.sub(r'\D', '', r.get('rib') or '')
            if len(rib) == 24:
                self.comptes.append(dict(dossier_ref=ref, lot=lot, rib=rib, banque=v(r.get('banque')), titulaire=v(r.get('titulaire_compte')),
                                         type_titulaire=v(r.get('type_titulaire')), piece_type='RELEVE_BANCAIRE', piece_id=r['piece_id']))
        for p in lire_jsonl(os.path.join(dossier, 'pieces', 'ATTESTATION_RIB.jsonl')):
            ref, f = p['dossier_ref'], p.get('fields') or {}
            if ref not in refs:
                continue
            self.dossiers[ref]['nb_pieces'] += 1
            rib = re.sub(r'\D', '', str(f.get('rib') or ''))
            if len(rib) == 24:
                self.comptes.append(dict(dossier_ref=ref, lot=lot, rib=rib, banque=v(f.get('banque')) if not isinstance(v(f.get('banque')), (dict, list)) else None,
                                         titulaire=sous(f, 'titulaire_compte', 'nom_prenom', 'raison_sociale'),
                                         type_titulaire=sous(f, 'type_titulaire'), piece_type='ATTESTATION_RIB', piece_id=p['piece_id']))
        # employeurs : attestations de travail, bulletins de paie, attestations CNSS
        for typ in ('ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE', 'ATTESTATION_CNSS'):
            for p in lire_jsonl(os.path.join(dossier, 'pieces', f'{typ}.jsonl')):
                ref, f = p['dossier_ref'], p.get('fields') or {}
                if ref not in refs:
                    continue
                self.dossiers[ref]['nb_pieces'] += 1
                emp = sous(f, 'employeur.raison_sociale', 'employeur.nom', 'employeur_actuel', 'raison_sociale')
                s = None
                if emp and not re.fullmatch(r'[\d\s]+', emp):
                    s = self.societe(ref, lot, 'employeur', emp, ice=sous(f, 'employeur.ice'), adresse=sous(f, 'employeur.adresse', 'adresse_employeur'),
                                     piece_type=typ, piece_id=p['piece_id'], source=p.get('source'))
                self.personne(ref, lot, 'salarie', f.get('nom'), f.get('prenom'), sous(f, 'employe.nom_complet', 'assure.nom_complet'),
                              sous(f, 'numero_cin', 'employe.cin', 'assure.cin'), date_naissance=f.get('date_naissance'),
                              adresse=sous(f, 'adresse_employe'), qualite=sous(f, 'fonction', 'profession'), piece_type=typ, piece_id=p['piece_id'],
                              source=p.get('source'), societe=s)
        for p in lire_jsonl(os.path.join(dossier, 'pieces', 'ATTESTATION_PENSION.jsonl')):
            ref, f = p['dossier_ref'], p.get('fields') or {}
            if ref in refs:
                self.dossiers[ref]['nb_pieces'] += 1
                self.personne(ref, lot, 'pensionne', f.get('nom'), f.get('prenom'), sous(f, 'pensionne.nom_complet'), sous(f, 'numero_cin', 'pensionne.cin'),
                              date_naissance=f.get('date_naissance'), adresse=f.get('adresse'), piece_type='ATTESTATION_PENSION', piece_id=p['piece_id'], source=p.get('source'))
        for p in lire_jsonl(os.path.join(dossier, 'pieces', 'CARTE_PROFESSIONNELLE.jsonl')):
            ref, f = p['dossier_ref'], p.get('fields') or {}
            if ref in refs:
                self.dossiers[ref]['nb_pieces'] += 1
                self.personne(ref, lot, 'demandeur', f.get('nom'), f.get('prenom'), sous(f, 'nom_complet'), sous(f, 'numero_cin', 'cin'),
                              qualite=sous(f, 'profession'), piece_type='CARTE_PROFESSIONNELLE', piece_id=p['piece_id'], source=p.get('source'))
        for p in lire_jsonl(os.path.join(dossier, 'pieces', 'CARTE_GRISE.jsonl')):
            ref, f = p['dossier_ref'], p.get('fields') or {}
            if ref in refs:
                self.dossiers[ref]['nb_pieces'] += 1
                self.personne(ref, lot, 'titulaire_carte_grise', f.get('nom'), f.get('prenom'), cin=sous(f, 'cin'), adresse=sous(f, 'adresse'),
                              piece_type='CARTE_GRISE', piece_id=p['piece_id'], source=p.get('source'))
        for p in lire_jsonl(os.path.join(dossier, 'pieces', 'FACTURE_PROFORMA_VEHICULE.jsonl')):
            ref, f = p['dossier_ref'], p.get('fields') or {}
            if ref in refs:
                self.dossiers[ref]['nb_pieces'] += 1
                vend = sous(f, 'vendeur.nom', 'nom_concessionnaire')
                if vend:
                    self.societe(ref, lot, 'vendeur', vend, piece_type='FACTURE_PROFORMA_VEHICULE', piece_id=p['piece_id'], source=p.get('source'))
        for typ in ('DOMICILIATION',):
            for p in lire_jsonl(os.path.join(dossier, 'pieces', f'{typ}.jsonl')):
                if p['dossier_ref'] in refs:
                    self.dossiers[p['dossier_ref']]['nb_pieces'] += 1
        # tiers bancaires : virements, versements, chèques et remises nominatifs, agrégés par dossier
        tiers = defaultdict(lambda: [0, 0.0, 0.0])
        nominatif = re.compile(r'\b(VIR|VIREMENT|VIRT|VERSEMENT|VERST|CHEQUE|CHQ|REMISE|TRANSFERT|MISE A DISPOSITION|MAD)\b')
        for r in lire_csv(os.path.join(dossier, 'aplatis', 'tiers_bancaires_operations.csv')):
            ref, t = r.get('dossier_ref'), v(r.get('tiers_candidat'))
            if ref not in refs or not t or len(t.split()) < 2 or not nominatif.search(cb.latin_maj(r.get('libelle') or '')):
                continue
            a = tiers[(ref, t.upper())]
            a[0] += 1
            for i, c in ((1, 'credit'), (2, 'debit')):
                try:
                    a[i] += float(r.get(c) or 0)
                except ValueError:
                    pass
        self.tiers = getattr(self, 'tiers', {})
        for (ref, t), (n, cr, db) in tiers.items():
            k_rs, k_nom = cb.cle_rs(t), cb.cle_nom(t)
            societe = bool(set(cb.latin_maj(t).split()) & (cb.MARQUES_SOCIETE | {'STE', 'SOCIETE', 'SARL', 'SA', 'SARLAU'}))
            self.tiers[(ref, t)] = (lot, k_rs if societe else k_nom, 'RS' if societe else 'NOM', n, round(cr, 2), round(db, 2))
        print(f'  lot {lot} : {len(refs)} dossiers ({time.time() - t0:.0f} s)', flush=True)


# ---- identités ------------------------------------------------------------------------------------------------------
def rs_proches(a, b):
    ka, kb = cb.cle_rs(a or ''), cb.cle_rs(b or '')
    if not ka or not kb:
        return False
    if ka == kb or cb._ratio(ka, kb) >= 0.8:
        return True
    ma, mb = set(ka.split()), set(kb.split())
    return bool(ma and mb) and (ma <= mb or mb <= ma)


def sq_proches(a, b):
    """Raisons sociales proches par leur squelette de consonnes (une raison sociale en latin et la même en écriture arabe)."""
    sa, sb = cb.squelette_rs(a or ''), cb.squelette_rs(b or '')
    return bool(sa and sb) and cb._ratio(sa, sb) >= 0.8


PRENOMS_COURANTS = {'MOHAMED', 'MOHAMMED', 'MOHAMAD', 'AHMED', 'FATIMA', 'RACHID', 'SAID', 'HASSAN', 'BRAHIM', 'IBRAHIM', 'MUSTAPHA', 'MOSTAFA',
                    'YOUSSEF', 'ABDELLAH', 'ALI', 'OMAR', 'KHALID', 'JAMAL', 'AZIZ', 'HAMID', 'LAHCEN', 'DRISS', 'KARIM', 'HICHAM', 'AMAR'}


def identites(ch):
    """Affecte une clé d'identité à chaque personne et à chaque société lue."""
    # personnes : CIN, sinon rattachement à une personne du même dossier au nom compatible, sinon nom dans le dossier
    par_dossier = defaultdict(list)
    for p in ch.personnes:
        par_dossier[p['dossier_ref']].append(p)
    for ref, ps in par_dossier.items():
        avec = [p for p in ps if p['cin_norm']]
        for p in ps:
            if p['cin_norm']:
                p['cle'], p['niveau'] = 'C:' + p['cin_norm'], 'fort'
                continue
            cible = None
            if p['nom_complet']:
                cands = {q['cin_norm'] for q in avec if q['nom_complet'] and (
                    (p['cle_nom'] and p['cle_nom'] == q['cle_nom']) or cb.mots_latins_proches(p['nom_complet'], q['nom_complet']))}
                if len(cands) == 1:
                    cible = cands.pop()
            if cible:
                p['cle'], p['niveau'] = 'C:' + cible, 'fort'
            else:
                p['cle'], p['niveau'] = f"N:{ref}:{p['cle_nom'] or cb.latin_maj(p['nom_complet'])}", 'faible'
    # sociétés : RC + tribunal, sinon ICE, sinon même société que celle du dossier qui a une clé, sinon nom dans le dossier
    ice_vers = {}
    for s in ch.societes:
        if s['rc_num'] and s['tribunal_code'] and s['ice']:
            ice_vers.setdefault(s['ice'], f"R:{s['rc_num']}@{s['tribunal_code']}")
    soc_dossier = defaultdict(list)
    for s in ch.societes:
        soc_dossier[s['dossier_ref']].append(s)
    for ref, ss in soc_dossier.items():
        for s in ss:
            if s['role'] in ('employeur', 'vendeur'):
                if s['ice']:
                    s['cle'], s['niveau'] = ice_vers.get(s['ice'], 'I:' + s['ice']), 'fort'
                else:
                    s['cle'], s['niveau'] = 'E:' + (s['cle_rs'] or cb.latin_maj(s['denomination'])), 'faible'
            elif s['rc_num'] and s['tribunal_code']:
                s['cle'], s['niveau'] = f"R:{s['rc_num']}@{s['tribunal_code']}", 'fort'
            elif s['ice']:
                s['cle'], s['niveau'] = ice_vers.get(s['ice'], 'I:' + s['ice']), 'fort'
            else:
                s['cle'] = None
        fortes = [s for s in ss if s.get('cle') and s['niveau'] == 'fort' and s['role'] not in ('employeur', 'vendeur')]
        cles_fortes = {s['cle'] for s in fortes}
        for s in ss:
            if s.get('cle'):
                continue
            cands = {q['cle'] for q in fortes if rs_proches(s['denomination'], q['denomination'])}
            if not cands and len(cles_fortes) == 1 and s['piece_type'] in ('STATUTS', 'CONTEXTE') and not s['rc_num']:
                # dossier d'une seule société : ses statuts et son nom déclaré sont les siens, même écrits autrement
                if ch.dossiers[ref]['type_personne'] == 'PM':
                    cands = set(cles_fortes)
            if len(cands) == 1:
                s['cle'], s['niveau'] = cands.pop(), 'fort'
            elif s['rc_num']:
                s['cle'], s['niveau'] = f"R:{s['rc_num']}@?:{s['cle_rs'] or ''}", 'faible'
            else:
                s['cle'], s['niveau'] = f"D:{ref}:{s['cle_rs'] or cb.latin_maj(s['denomination'] or '')}", 'faible'


def ecrire(con, ch):
    con.executescript(SCHEMA)
    con.executemany("""INSERT INTO af_dossier VALUES (:ref,:lot,:actif,:type_personne,:csp,:produit,:mode_paiement,:client_nom,:client_cin,
        :client_cin_norm,:client_adresse,:ville_code,:client_connu,:employeur_declare,:revenu_declare,:organisme_pension,:categorie,:verdict,
        :statut_analyse,:alertes_mineures,:alertes_majeures,:alertes_critiques,:recu_le,:nb_pieces)""", list(ch.dossiers.values()))
    # identités
    groupes = defaultdict(list)
    for p in ch.personnes:
        groupes[('PP', p['cle'], p['niveau'])].append(p)
    for s in ch.societes:
        groupes[('PM', s['cle'], s['niveau'])].append(s)
    ident = {}
    lignes = []
    for iid, ((typ, cle, niveau), objs) in enumerate(sorted(groupes.items(), key=lambda x: (x[0][0], x[0][1])), start=1):
        ident[(typ, cle)] = iid
        refs = sorted({o['dossier_ref'] for o in objs}, key=lambda r: (ch.dossiers[r]['recu_le'] or '', r))
        if typ == 'PP':
            # nom : celui de la pièce CIN en priorité, sinon le plus fréquent
            noms = Counter()
            for o in objs:
                if o['nom_complet']:
                    noms[o['nom_complet']] += 3 if o['piece_type'] == 'CIN' else 1
            nom = noms.most_common(1)[0][0] if noms else None
            autres = sorted({n for n in noms if n != nom and cb.cle_nom(n) != cb.cle_nom(nom or '')})
            lignes.append((iid, 'PP', cle, niveau, nom, ' ; '.join(autres[:6]) or None, cle[2:] if cle.startswith('C:') else None, None, None, None,
                           next((o['date_naissance'] for o in objs if o['date_naissance'] and o['piece_type'] == 'CIN'), None)
                           or next((o['date_naissance'] for o in objs if o['date_naissance']), None),
                           next((o['ville_code'] for o in objs if o['ville_code']), None),
                           next((o['adresse'] for o in objs if o['adresse']), None), len(refs),
                           ', '.join(sorted({o['role'] for o in objs})), refs[0], refs[-1]))
        else:
            noms = Counter()
            for o in objs:
                if o['denomination']:
                    noms[o['denomination']] += 3 if o['piece_type'] == 'REGISTRE_COMMERCE' else 1
            nom = noms.most_common(1)[0][0] if noms else None
            autres = sorted({n for n in noms if n != nom and cb.cle_rs(n) != cb.cle_rs(nom or '')})
            rc = next((o['rc_num'] for o in objs if o['rc_num']), None)
            trib = next((o['tribunal_code'] for o in objs if o['tribunal_code']), None)
            lignes.append((iid, 'PM', cle, niveau, nom, ' ; '.join(autres[:6]) or None, None, rc, trib,
                           next((o['ice'] for o in objs if o['ice']), None), None,
                           next((o['ville_code'] for o in objs if o['ville_code']), None),
                           next((o['adresse'] for o in objs if o['adresse']), None), len(refs),
                           ', '.join(sorted({o['role'] for o in objs})), refs[0], refs[-1]))
    con.executemany('INSERT INTO af_identite VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', lignes)
    for i, s in enumerate(ch.societes, start=1):
        s['af_id'], s['identite_id'] = i, ident[('PM', s['cle'])]
    con.executemany("""INSERT INTO af_societe VALUES (:af_id,:dossier_ref,:lot,:role,:denomination,:cle_rs,:forme_juridique,:rc_brut,:rc_num,
        :tribunal_code,:ice,:adresse,:ville_code,:date_creation,:capital,:objet,:origine_fonds,:piece_type,:piece_id,:source,:identite_id)""", ch.societes)
    for i, p in enumerate(ch.personnes, start=1):
        p['af_id'], p['identite_id'] = i, ident[('PP', p['cle'])]
        p['societe_af_id'] = p['societe']['af_id'] if p.get('societe') else None
    con.executemany("""INSERT INTO af_personne VALUES (:af_id,:dossier_ref,:lot,:role,:nom_complet,:nom,:prenom,:cle_nom,:cin_brut,:cin_norm,
        :cin_statut,:date_naissance,:lieu_naissance,:adresse,:ville_code,:nom_pere,:nom_mere,:nationalite,:qualite,:parts,:piece_type,:piece_id,
        :source,:societe_af_id,:identite_id)""", ch.personnes)
    con.executemany('INSERT INTO af_compte (dossier_ref, lot, rib, banque, titulaire, type_titulaire, piece_type, piece_id) VALUES (:dossier_ref,:lot,:rib,:banque,:titulaire,:type_titulaire,:piece_type,:piece_id)', ch.comptes)
    con.executemany('INSERT INTO af_tiers VALUES (?,?,?,?,?,?,?,?)', [(ref, lot, t, cle, tc, n, cr, db) for (ref, t), (lot, cle, tc, n, cr, db) in ch.tiers.items()])
    # qui apparaît dans quel dossier, relations personne – société
    di = defaultdict(set)
    for o in ch.personnes + ch.societes:
        di[(o['dossier_ref'], o['identite_id'], o['role'])].add(o['piece_type'])
    con.executemany('INSERT INTO af_dossier_identite VALUES (?,?,?,?)', [(r, i, role, ', '.join(sorted(x for x in pt if x))) for (r, i, role), pt in di.items()])
    rel = {}
    for p in ch.personnes:
        s = p.get('societe')
        if s:
            rel.setdefault((p['identite_id'], s['identite_id'], p['role'], p['dossier_ref']),
                           (p['identite_id'], s['identite_id'], p['role'], p['qualite'], p['parts'], p['dossier_ref'], p['piece_type'], p['source']))
    # gérants et associés lus dans une pièce dont la société n'a pas été rattachée : la société cliente du dossier
    cliente = {}
    for s in ch.societes:
        if s['role'] in ('societe_cliente', 'societe_du_client') and s['niveau'] == 'fort':
            cliente.setdefault(s['dossier_ref'], set()).add(s['identite_id'])
    for p in ch.personnes:
        if p['role'] in ('gerant', 'associe', 'dirigeant', 'signataire') and not p.get('societe'):
            c = cliente.get(p['dossier_ref'], set())
            if len(c) == 1:
                sid = next(iter(c))
                rel.setdefault((p['identite_id'], sid, p['role'], p['dossier_ref']),
                               (p['identite_id'], sid, p['role'], p['qualite'], p['parts'], p['dossier_ref'], p['piece_type'], p['source']))
    con.executemany('INSERT INTO af_relation (pp_identite_id, pm_identite_id, role, qualite, parts, dossier_ref, piece_type, source) VALUES (?,?,?,?,?,?,?,?)', list(rel.values()))
    con.commit()
    return ident


# ---- liens ----------------------------------------------------------------------------------------------------------
def liens(con):
    t0 = time.time()
    L = []

    def lien(regle, niveau, identite_id, cible, cible_id, cle_type=None, cle_valeur=None, detail=None, dossier_ref=None):
        L.append((regle, niveau, identite_id, dossier_ref, cible, str(cible_id), cle_type, cle_valeur, detail))

    ids = con.execute('SELECT identite_id, type_identite, cle, niveau_cle, nom, autres_noms, cin_norm, rc_num, tribunal_code, ice, ville_code, roles FROM af_identite').fetchall()
    bl = con.execute('SELECT entite_id, type_entite, nom_affiche, cin, rc_num, tribunal_code, ice, ville_code, employeur FROM bl_entite').fetchall()
    bl_cin, bl_rc, bl_ice, bl_nom, bl_rs, bl_emp = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    noms_bl = defaultdict(set)
    for eid, nom, prenom, ras in con.execute('SELECT entite_id, nom, prenom, nom_ras FROM bl_inscription'):
        for n in (' '.join(x for x in (nom, prenom) if x), ras):
            if n:
                noms_bl[eid].add(n)
    for eid, typ, nom, cin, rc, trib, ice, vil, emp in bl:
        if nom:
            noms_bl[eid].add(nom)
        if typ == 'PP':
            if cin:
                n, st = cb.normalise_cin(cin)
                if st in ('valide', 'lettre_finale'):
                    bl_cin[n].append(eid)
            for n in noms_bl[eid]:
                k = cb.cle_nom(n)
                if k:
                    bl_nom[k].append((eid, bool(cin)))
            if emp and cb.cle_rs(emp):
                bl_emp[cb.cle_rs(emp)].append(eid)
        else:
            if rc:
                bl_rc[rc].append((eid, trib))
            if ice:
                bl_ice[ice].append(eid)
            for n in noms_bl[eid]:
                k = cb.cle_rs(n)
                if k:
                    bl_rs[k].append((eid, rc, vil))
    rc_trib = defaultdict(list)
    for sid, den, autres, rc, trib in con.execute('SELECT societe_id, denomination, autres_denominations, rc_num, tribunal_code FROM rc_societe WHERE rc_num IS NOT NULL AND tribunal_code IS NOT NULL'):
        rc_trib[(rc, trib)].append((sid, [den] + [x for x in (autres or '').split(' | ') if x]))
    rc_cin = defaultdict(list)
    for pid, sid, cin in con.execute("SELECT personne_id, societe_id, cin_norm FROM rc_personne WHERE cin_norm IS NOT NULL AND type_personne = 'PP'"):
        rc_cin[cin].append((pid, sid))

    def noms_ident(nom, autres):
        return [n for n in [nom] + (autres or '').split(' ; ') if n]

    soc_registre = {}                                   # identité PM → société du registre (AF03 certain)
    for iid, typ, cle, niv, nom, autres, cin, rc, trib, ice, vil, roles in ids:
        noms = noms_ident(nom, autres)
        if typ == 'PP':
            if cin:
                for eid in bl_cin.get(cin, []):
                    lien('AF01', 'certain', iid, 'bl_entite', eid, 'CIN', cin)
                for pid, sid in rc_cin.get(cin, []):
                    lien('AF04', 'certain', iid, 'rc_personne', pid, 'CIN', cin, f'société du registre n° {sid}')
            else:
                k = cb.cle_nom(nom or '')
                for eid, a_cin in bl_nom.get(k, []) if k else []:
                    if not a_cin:
                        lien('AF01n', 'à vérifier', iid, 'bl_entite', eid, 'NOM', k, 'ni le dossier ni la liste noire ne donnent de CIN')
        else:
            if rc and trib:
                for eid, btrib in bl_rc.get(rc, []):
                    compat = cb.noms_compatibles(noms, next(iter(noms_bl[eid]), ''), societe=True) or any(
                        cb.noms_compatibles(noms, n, societe=True) or rs_proches(n, nom) for n in noms_bl[eid])
                    if btrib == trib:
                        lien('AF02' if compat else 'AF02n', 'certain' if compat else 'à vérifier', iid, 'bl_entite', eid, 'RC_TRIB', f'{rc}@{trib}',
                             None if compat else 'même RC et même tribunal, raisons sociales différentes')
                    elif not btrib and compat:
                        lien('AF02b', 'probable', iid, 'bl_entite', eid, 'RC', rc, f'tribunal apporté par le dossier : {trib}')
                for sid, dens in rc_trib.get((rc, trib), []):
                    dens = [d for d in dens if d]
                    compat = any(rs_proches(d, n) or sq_proches(d, n) for d in dens for n in noms)
                    if compat:
                        lien('AF03', 'certain', iid, 'rc_societe', sid, 'RC_TRIB', f'{rc}@{trib}')
                        soc_registre.setdefault(iid, sid)
                    elif not dens:
                        lien('AF03b', 'probable', iid, 'rc_societe', sid, 'RC_TRIB', f'{rc}@{trib}', f'dénomination non lue au registre ; le dossier donne : {nom}')
                        soc_registre.setdefault(iid, sid)
                    else:
                        lien('AF03n', 'à vérifier', iid, 'rc_societe', sid, 'RC_TRIB', f'{rc}@{trib}', f'dossier : {nom} · registre : {dens[0]}')
            if ice:
                for eid in bl_ice.get(ice, []):
                    lien('AF02c', 'certain', iid, 'bl_entite', eid, 'ICE', ice)
            k = cb.cle_rs(nom or '')
            if k and len(k.split()) >= 1 and len(k) >= 5:
                if roles and ('employeur' in roles):
                    for eid, brc, bvil in bl_rs.get(k, []):
                        lien('AF07', 'à vérifier', iid, 'bl_entite', eid, 'RS', k, 'employeur d\'un dossier = société inscrite (même raison sociale)')
                    for eid in bl_emp.get(k, []):
                        lien('AF07', 'à vérifier', iid, 'bl_entite', eid, 'RS', k, 'même employeur que celui déclaré par un inscrit')
                if roles and ('societe_cliente' in roles or 'societe_du_client' in roles):
                    for eid, brc, bvil in bl_rs.get(k, []):
                        if not brc and (not bvil or not vil or bvil == vil):
                            lien('AF02d', 'à vérifier', iid, 'bl_entite', eid, 'RS', k, 'liste noire sans RC ; même raison sociale' + (', même ville' if bvil and bvil == vil else ''))
    # AF05 : le dossier apporte le CIN d'une personne du registre (même société, nom compatible)
    apportes = {}
    pers_soc = defaultdict(list)
    sids = set(soc_registre.values())
    for pid, sid, nom, ecr, cin, nlat in con.execute("SELECT personne_id, societe_id, nom_complet, ecriture, cin_norm, nom_latin FROM rc_personne WHERE type_personne = 'PP' AND nom_complet IS NOT NULL"):
        if sid in sids:
            pers_soc[sid].append((pid, nom, ecr, cin, nlat))
    ident = {r[0]: r for r in ids}
    for pp, pm, role, ref in con.execute("SELECT DISTINCT pp_identite_id, pm_identite_id, role, dossier_ref FROM af_relation WHERE role IN ('gerant', 'associe', 'dirigeant', 'signataire')"):
        sid = soc_registre.get(pm)
        cin = ident[pp][6]
        if not sid or not cin:
            continue
        noms = noms_ident(ident[pp][4], ident[pp][5])
        cands = []
        for pid, nom, ecr, rcin, nlat in pers_soc.get(sid, []):
            if ecr == 'arabe':
                ok = any(cb.profils_compatibles(n, nom) for n in noms)
            else:
                ok = any(cb.mots_latins_proches(n, nom) for n in noms)
            if ok:
                cands.append((pid, nom, rcin))
        for pid, nom, rcin in cands:
            etat = 'apporte' if not rcin else 'confirme' if rcin == cin else 'conflit'
            if (pid, cin) not in apportes:
                apportes[(pid, cin)] = (pid, sid, cin, pp, ident[pp][4], nom, role, ref, etat)
                lien('AF05', 'certain' if etat != 'conflit' else 'à vérifier', pp, 'rc_personne', pid, 'CIN', cin,
                     {'apporte': 'le dossier apporte le CIN', 'confirme': 'CIN déjà connu du registre, confirmé', 'conflit': f'le registre porte un autre CIN ({rcin})'}[etat]
                     + f' · société du registre n° {sid}', ref)
    con.executemany('INSERT INTO af_cin_apporte VALUES (?,?,?,?,?,?,?,?,?)', list(apportes.values()))
    # AF09 : même RIB, clients différents
    lies = set(con.execute('SELECT pp_identite_id, pm_identite_id FROM af_relation'))
    for ref_, in con.execute('SELECT DISTINCT dossier_ref FROM af_dossier_identite'):
        membres = [i for i, in con.execute('SELECT DISTINCT identite_id FROM af_dossier_identite WHERE dossier_ref = ?', (ref_,))]
        if len(membres) <= 12:
            lies.update((x, y) for x in membres for y in membres if x != y)      # présents dans un même dossier
    client = {}
    for ref, iid, role in con.execute("SELECT dossier_ref, identite_id, role FROM af_dossier_identite WHERE role IN ('demandeur', 'societe_cliente')"):
        client.setdefault(ref, set()).add(iid)
    par_rib = defaultdict(set)
    for rib, ref in con.execute('SELECT rib, dossier_ref FROM af_compte'):
        par_rib[rib].add(ref)
    for rib, refs in par_rib.items():
        if not 2 <= len(refs) <= 12:
            continue                                          # au-delà : compte d'une banque ou d'un organisme lu par erreur
        refs = sorted(refs)
        forts = [frozenset(i for i in client.get(r, ()) if ident[i][3] == 'fort') for r in refs]
        for a in range(len(refs)):
            for b in range(a + 1, len(refs)):
                if forts[a] and forts[b] and not (forts[a] & forts[b]):
                    # le gérant ou l'associé d'une société cliente qui dépose aussi un dossier à son nom : même compte, rien d'anormal
                    if any((x, y) in lies or (y, x) in lies for x in forts[a] for y in forts[b]):
                        continue
                    if any(ident[x][4] and ident[y][4] and ident[x][1] == ident[y][1] == 'PP' and cb.mots_latins_proches(ident[x][4], ident[y][4])
                           for x in forts[a] for y in forts[b]):
                        continue                              # même personne, CIN lu différemment d'un dossier à l'autre
                    ia = next(iter(forts[a]))
                    lien('AF09', 'indice', ia, 'af_dossier', refs[b], 'RIB', rib, f'même RIB que le dossier {refs[a]} ({ident[ia][4]}), client différent', refs[a])
    # AF11 : tiers bancaire = inscrit (mêmes mots)
    for ref, t, cle, tc, n, cr, db in con.execute('SELECT dossier_ref, tiers, cle, type_cle, nb_operations, total_credit, total_debit FROM af_tiers WHERE cle IS NOT NULL'):
        if tc == 'NOM' and len(cle.split()) >= 2:
            courant = len(cle.split()) == 2 and bool(set(cle.split()) & PRENOMS_COURANTS)
            for eid, a_cin in bl_nom.get(cle, []):
                lien('AF11', 'indice faible' if courant else 'indice', None, 'bl_entite', eid, 'NOM', cle,
                     f'tiers « {t} » : {n} opération(s), crédit {cr:.0f}, débit {db:.0f}' + (' · nom courant' if courant else ''), ref)
        elif tc == 'RS' and len(cle) >= 6:
            for eid, brc, bvil in bl_rs.get(cle, []):
                lien('AF11', 'indice', None, 'bl_entite', eid, 'RS', cle, f'tiers « {t} » : {n} opération(s), crédit {cr:.0f}, débit {db:.0f}', ref)
    # AF20 : une identité d'un dossier retrouvée au registre (AF03, AF04, AF05) se trouve sur un chemin partant d'un inscrit
    directs = defaultdict(set)
    for l in L:
        if l[4] == 'bl_entite' and l[2]:
            directs[l[2]].add(l[5])
    ancrages = defaultdict(set)                       # (type du registre, id) → identités des dossiers
    for l in L:
        if l[0] in ('AF03', 'AF03b', 'AF04', 'AF05') and l[1] in ('certain', 'probable'):
            ancrages[(l[4], l[5])].add(l[2])
    meilleurs = {}
    for eid, ct, cid, prof, force, trace in con.execute("SELECT bl_entite_id, cible_type, cible_id, profondeur, force, trace FROM chemin WHERE cible_type IN ('rc_societe', 'rc_personne')"):
        for iid in ancrages.get((ct, str(cid)), ()):
            if str(eid) in directs.get(iid, ()):
                continue
            k = (iid, eid)
            if k not in meilleurs or (prof, -force) < (meilleurs[k][0], -meilleurs[k][1]):
                meilleurs[k] = (prof, force, trace, ct, cid)
    for (iid, eid), (prof, force, trace, ct, cid) in meilleurs.items():
        lien('AF20', f'réseau à {prof} arête' + ('s' if prof > 1 else ''), iid, 'bl_entite', eid, 'CHEMIN', f'{ct}:{cid}',
             f'force {force:.2f} · {trace}'[:600])
    vus, uniques = set(), []
    for l in L:
        k = (l[0], l[2], l[3], l[4], l[5], l[7])
        if k not in vus:
            vus.add(k)
            uniques.append(l)
    con.executemany('INSERT INTO af_lien (regle, niveau, identite_id, dossier_ref, cible, cible_id, cle_type, cle_valeur, detail) VALUES (?,?,?,?,?,?,?,?,?)', uniques)
    con.execute("""UPDATE af_identite SET nb_dossiers = (SELECT count(DISTINCT dossier_ref) FROM af_dossier_identite d WHERE d.identite_id = af_identite.identite_id)""")
    con.commit()
    print(f'  liens : {len(uniques)} ({time.time() - t0:.0f} s)', flush=True)


def bilan(con):
    q = lambda s: con.execute(s).fetchall()
    print('\n  Dossiers', q("SELECT lot, count(*), sum(type_personne = 'PP'), sum(type_personne = 'PM') FROM af_dossier GROUP BY 1"))
    print('  Personnes lues', q('SELECT count(*), count(cin_norm) FROM af_personne')[0], '· sociétés lues', q('SELECT count(*), count(rc_num), sum(rc_num IS NOT NULL AND tribunal_code IS NOT NULL), count(ice) FROM af_societe')[0])
    print('  Identités', q('SELECT type_identite, niveau_cle, count(*), sum(nb_dossiers >= 2) FROM af_identite GROUP BY 1, 2'))
    print('  Relations personne – société', q('SELECT role, count(*) FROM af_relation GROUP BY 1'))
    print('  Comptes', q('SELECT count(*), count(DISTINCT rib) FROM af_compte')[0], '· tiers', q('SELECT count(*) FROM af_tiers')[0])
    print('  Liens par règle :')
    for r in q('SELECT regle, niveau, count(*), count(DISTINCT identite_id), count(DISTINCT cible_id) FROM af_lien GROUP BY 1, 2 ORDER BY 1'):
        print(f'    {r[0]:6} {r[1]:11} {r[2]:6} liens · {r[3]:5} identités · {r[4]:5} cibles')
    print('  CIN apportés au registre', q('SELECT etat, count(*), count(DISTINCT cin_norm) FROM af_cin_apporte GROUP BY 1'))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True)
    ap.add_argument('--export', required=True, help='dossier de l\'export antifraude (contient 1_donnees_prod et 2_donnees_preprod)')
    a = ap.parse_args()
    t0 = time.time()
    con = sqlite3.connect(a.base)
    ch = Chargeur(con)
    for lot, sous_dossier in LOTS:
        d = os.path.join(a.export, sous_dossier)
        if os.path.isdir(d):
            ch.lot(lot, d)
    identites(ch)
    ecrire(con, ch)
    liens(con)
    for nom, val, desc in (('antifraude_dossiers', len(ch.dossiers), 'dossiers antifraude chargés'),
                           ('antifraude_date', 0, 'chargement antifraude : ' + time.strftime('%Y-%m-%d') + ' · ' + os.path.basename(os.path.normpath(a.export)))):
        con.execute('INSERT OR REPLACE INTO parametre (nom, valeur, texte, description) VALUES (?,?,?,?)', (nom, val, None, desc))
    con.commit()
    bilan(con)
    print(f'\n  Terminé en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
