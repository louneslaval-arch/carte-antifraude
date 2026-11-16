"""Tests de la couche 3 (étape G) : fiche du dossier (en-tête, parties, revenus, charges, comptes, opérations,
véhicules) et incohérences entre pièces, entre dossiers et avec le registre. Tout est fictif."""

import json
import re
import os
import random
import sqlite3
import subprocess
import sys
import uuid

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import verifier  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import COUCHES  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402
from pipeline.couches import c2_identites as c2  # noqa: E402
from pipeline.couches import c3_dossier as c3  # noqa: E402

T0 = '2026-11-13T10:00:00.000Z'
TABLES = ('c3_dossier', 'c3_revenu', 'c3_charge', 'c3_compte', 'c3_operation', 'c3_vehicule', 'c3_cle_dossier',
          'c3_incoherence_locale')
VUES = ('c3_partie_dossier', 'c3_incoherence')
RIB_A, RIB_B = '999' + '0' * 21, '999' + '1' * 21


# ---- montage -------------------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture(scope='module')
def socle(jeu, tmp_path_factory):
    d = tmp_path_factory.mktemp('socle')
    g = jeu.monde
    gd.ecrire_csv(str(d / 'liste_noire.csv'), g.bl, gd.COLONNES_BL)
    gd.ecrire_csv(str(d / 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    gd.ecrire_csv(str(d / 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'construire_base.py'),
                        '--liste-noire', str(d / 'liste_noire.csv'), '--rc-annonces', str(d / 'rc_annonces.csv'),
                        '--rc-personnes', str(d / 'rc_personnes.csv'), '--base', str(d / 'socle.sqlite')],
                       capture_output=True, text=True)
    assert r.returncode == 0
    return str(d / 'socle.sqlite')


def base_de(tmp_path, dossiers=(), socle=None, meta=None):
    """Base neuve : dossiers reçus (c0), puis toutes les couches en lot, socle chargé."""
    cx = sqlite3.connect(str(tmp_path / f'base_{len(os.listdir(tmp_path))}.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for d in dossiers:
        c0.recevoir(cx, passage, d, actif=meta[d['ref']]['actif'] if meta else True, maintenant=T0)
    for couche in COUCHES[1:]:
        couche.construire_tout(cx)
    if socle:
        c2.charger_socle(cx, socle)
    return cx


@pytest.fixture(scope='module')
def base(jeu, socle, tmp_path_factory):
    cx = base_de(tmp_path_factory.mktemp('c3'), jeu.dossiers, socle, jeu.meta)
    yield cx
    cx.close()


@pytest.fixture
def cx(base):
    return base


def lignes(cx, sql, *p):
    return cx.execute(sql, p).fetchall()


def un(cx, sql, *p):
    return cx.execute(sql, p).fetchone()[0]


def contenu(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM {t}').fetchall(), key=repr) for t in TABLES + VUES}


def dossier(jeu, n, *pieces, recu='2026-09-01T08:00:00.000Z', **entete):
    """Dossier fictif minimal : une pièce par couple (type, champs) ; `entete` remplace des champs du dossier."""
    d = json.loads(json.dumps(jeu.dossiers[0]))
    modele = d['pieces'][0]
    d.update(ref=f'ZZ26T{n:04d}', id=str(uuid.uuid5(uuid.NAMESPACE_OID, f'essai-c3-{n}')), analyses=[],
             latestAnalysis=None, reanalyses=[], businessReceivedAt=recu, createdAt=recu)
    d['businessData'] = dict(d['businessData'], dossier_ref=d['ref'],
                             civil=dict(full_name='ZELMOU BAKRITA', cin=f'ZZ1{n:05d}', address=None),
                             declared=dict(employer=None, monthly_income=None, pension_organism=None))
    d.update(entete)
    d['pieces'] = [dict(modele, type=t, upstreamPieceId=f'eqdom_{t}_{k}', fields=f) for k, (t, f) in enumerate(pieces)]
    return d


def cin_de(n, adresse=None):
    return ('CIN', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': f'ZZ1{n:05d}', 'adresse': adresse})


def releve(rib=RIB_A, salaire=None, relu=True, adresse=None, mois=(7, 8)):
    champs = {'titulaire_compte': 'ZELMOU BAKRITA', 'rib': rib, 'adresse': adresse, 'banque': 'BANQUE TAZOULA',
              'mois': [{'mois': m, 'annee': 2026, 'solde_ouverture': 1000.0, 'solde_cloture': 1200.0,
                        'total_credit': 9000.0, 'total_debit': 8800.0,
                        **({'operations': [
                            {'date_operation': f'05/{m:02d}', 'date_valeur': f'06/{m:02d}',
                             'libelle': 'VIREMENT RECU DE TAZOULA NEGOCE SARL', 'debit': None, 'credit': 9000.0},
                            {'date_operation': f'28/{m:02d}', 'libelle': 'PRELEVEMENT ECHEANCE CREDIT', 'debit': 1500.0,
                             'credit': None}]} if relu else {})} for m in mois]}
    if salaire is not None:
        champs['montant_salaire'] = {f'{m:02d}/2026': salaire for m in mois}
        champs['montant_echeances_credits'] = {f'{m:02d}/2026': 1500.0 for m in mois}
    return ('RELEVE_BANCAIRE', champs)


def bulletin(net):
    return ('BULLETIN_DE_PAIE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'remuneration': {'salaire_net': net},
                                 'credits_source': '750,00'})


def incoherences(cx, ref=None):
    ou, p = (' WHERE ref = ?', (ref,)) if ref else ('', ())
    return sorted(lignes(cx, 'SELECT ref, type, gravite, ref_b FROM c3_incoherence' + ou, *p))


# ---- en-tête et parties --------------------------------------------------------------------------------------------

def test_en_tete_au_format_du_modele_dossier_de_kamal(cx, jeu):
    colonnes = ('ref', 'id', 'personType', 'csp', 'productType', 'paymentMode', 'clientName', 'agence', 'canal',
                'category', 'categoryRule', 'categoryReason', 'verdict', 'verdictProvisional', 'analysisStatus',
                'alertsMinor', 'alertsMajor', 'alertsCritical', 'commentaireScore', 'commentaireAlerte',
                'matrixVersion', 'businessReceivedAt', 'resultsReceivedAt', 'createdAt', 'updatedAt')
    liste = ', '.join(f'"{c}"' for c in colonnes)
    assert lignes(cx, f'SELECT {liste} FROM c3_dossier ORDER BY ref') == \
        lignes(cx, f'SELECT {liste} FROM "Dossier" ORDER BY ref')
    assert un(cx, 'SELECT count(*) FROM c3_dossier') == len(jeu.dossiers)
    assert lignes(cx, 'SELECT DISTINCT montant_demande, duree_mois, apport, mensualite, statut_final FROM c3_dossier') == \
        [(None, None, None, None, None)]


def test_contexte_declare_lu_et_valeur_par_defaut_marquee_jamais_comparee(cx, jeu):
    d = jeu.dossiers[0]
    assert lignes(cx, 'SELECT civil_cin, declared_employer, declared_monthly_income, agency_code '
                      'FROM c3_dossier WHERE ref = ?', d['ref']) == \
        [(d['businessData']['civil']['cin'], 'VAB', 35110.75, 'AG07')]
    assert lignes(cx, 'SELECT champ FROM c3_valeur_par_defaut WHERE ref = ?', d['ref']) == [('employeur_declare',)]
    assert un(cx, "SELECT count(*) FROM ref_valeur_defaut WHERE champ = 'employeur_declare' AND valeur = 'VAB'") == 1
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type LIKE '%declare%'") == 0


def test_T11_contexte_partiel_d_une_societe_sans_plantage(cx, jeu):
    ref = next(v['ref'] for v in jeu.verite if 'T11' in v['pieges'])
    assert lignes(cx, 'SELECT "personType", civil_cin, declared_employer, declared_monthly_income '
                      'FROM c3_dossier WHERE ref = ?', ref) == [('PM', None, None, None)]
    assert un(cx, "SELECT count(*) FROM c3_revenu WHERE ref = ? AND nature = 'declare'", ref) == 0


def test_T14_analyse_non_terminee_et_dossier_archive_marques(cx, jeu):
    en_cours = next(v['ref'] for v in jeu.verite if 'S21' in v['scenarios'])
    archive = next(v['ref'] for v in jeu.verite if 'S22' in v['scenarios'])
    assert lignes(cx, 'SELECT en_cours, actif FROM c3_dossier WHERE ref = ?', en_cours) == [(1, 1)]
    assert lignes(cx, 'SELECT en_cours, actif FROM c3_dossier WHERE ref = ?', archive) == [(0, 0)]


def test_parties_du_dossier_et_demandeur(cx, jeu):
    v = next(v for v in jeu.verite if 'S04' in v['scenarios'])
    parties = lignes(cx, 'SELECT role, type_fiche, demandeur FROM c3_partie_dossier WHERE ref = ? ORDER BY 1, 2', v['ref'])
    assert ('titulaire_cin', 'PP', 1) in parties and ('employeur', 'PM', 0) in parties
    assert un(cx, 'SELECT count(DISTINCT fiche) FROM c3_partie_dossier WHERE ref = ? AND demandeur = 1', v['ref']) == 1
    pm = next(d['ref'] for d in jeu.dossiers if d['personType'] == 'PM' and any(
        p['type'] == 'REGISTRE_COMMERCE' for p in d['pieces']))
    assert ('societe', 'PM', 1) in lignes(cx, 'SELECT role, type_fiche, demandeur FROM c3_partie_dossier WHERE ref = ?', pm)


# ---- revenus, charges, comptes, opérations, véhicules --------------------------------------------------------------

def test_revenus_declare_et_verifies_avec_leur_piece(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=9500.0),
                ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'salaire_net': 10000}))
    d['businessData']['declared']['monthly_income'] = '10 000,00'
    cx = base_de(tmp_path, [d])
    assert sorted(lignes(cx, 'SELECT nature, source, upstream_piece_id, montant, annee, mois FROM c3_revenu')) == [
        ('declare', 'businessData', None, 10000.0, None, None),
        ('verifie', 'ATTESTATION_TRAVAIL_SALAIRE', 'eqdom_ATTESTATION_TRAVAIL_SALAIRE_3', 10000.0, None, None),
        ('verifie', 'BULLETIN_DE_PAIE', 'eqdom_BULLETIN_DE_PAIE_1', 10000.0, None, None),
        ('verifie', 'RELEVE_BANCAIRE', 'eqdom_RELEVE_BANCAIRE_2', 9500.0, 2026, 7),
        ('verifie', 'RELEVE_BANCAIRE', 'eqdom_RELEVE_BANCAIRE_2', 9500.0, 2026, 8)]
    assert sorted(lignes(cx, 'SELECT nature, upstream_piece_id, montant, mois FROM c3_charge')) == [
        ('credit_source', 'eqdom_BULLETIN_DE_PAIE_1', 750.0, None),
        ('echeance_releve', 'eqdom_RELEVE_BANCAIRE_2', 1500.0, 7), ('echeance_releve', 'eqdom_RELEVE_BANCAIRE_2', 1500.0, 8)]


def test_compte_avec_rib_banque_et_titulaire(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), releve())])
    assert lignes(cx, 'SELECT upstream_piece_id, rib, banque, titulaire FROM c3_compte') == \
        [('eqdom_RELEVE_BANCAIRE_1', RIB_A, 'BANQUE TAZOULA', 'ZELMOU BAKRITA')]


def test_T01_operations_lues_avec_type_et_contrepartie(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), releve(mois=(7,)))])
    assert lignes(cx, 'SELECT date_operation, type_operation, contrepartie, debit, credit FROM c3_operation ORDER BY 1') == \
        [('2026-07-05', 'virement', 'TAZOULA NEGOCE SARL', None, 9000.0),
         ('2026-07-28', 'prelevement', 'ECHEANCE CREDIT', 1500.0, None)]


def test_contexte_sous_les_noms_de_kamal_et_valeur_nulle_non_retenue(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(1))
    d['businessData'].update(known_client=True, in_production=False,
                             declared=dict(employer='TAZOULA SARL', monthly_income=0, pension_organism='CAISSE ZIRMAK'))
    cx = base_de(tmp_path, [d])
    assert lignes(cx, 'SELECT civil_cin, civil_full_name, declared_employer, declared_monthly_income, '
                      'declared_pension_organism, known_client, in_production FROM c3_dossier') == \
        [('ZZ100001', 'ZELMOU BAKRITA', 'TAZOULA SARL', 0.0, 'CAISSE ZIRMAK', 1, 0)]
    assert un(cx, "SELECT count(*) FROM c3_revenu WHERE nature = 'declare'") == 0      # un revenu nul n'en est pas un


def test_salaire_net_mensuel_seul_sur_un_bulletin(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), ('BULLETIN_DE_PAIE', {'salaire_net_mensuel': '8 000,00'}))])
    assert lignes(cx, "SELECT repere, montant FROM c3_revenu WHERE source = 'BULLETIN_DE_PAIE'") == \
        [('salaire_net_mensuel', 8000.0)]


def test_titulaire_du_compte_d_un_bulletin_lu_dans_son_porteur(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), ('BULLETIN_DE_PAIE', {'nom': 'ZELMOU', 'rib': RIB_A}))])
    assert lignes(cx, 'SELECT type_piece, titulaire FROM c3_compte') == [('BULLETIN_DE_PAIE', 'ZELMOU')]


def test_adresse_comparee_seulement_pour_le_demandeur_et_ses_propres_pieces(jeu, tmp_path):
    autre_adresse = '45 RUE ZIRMAK IMM 2'
    tiers = dossier(jeu, 1, cin_de(1, '12 Avenue Tazoula, Appartement 3'),
                    ('DOMICILIATION', {'titulaire': 'TAGHRIZ LOUMIZA', 'adresse': autre_adresse}))
    societe = dossier(jeu, 2, cin_de(2, '12 Avenue Tazoula, Appartement 3'),
                      ('RELEVE_BANCAIRE', {'titulaire_compte': 'TAZOULA NEGOCE SARL', 'type_titulaire': 'PM',
                                           'adresse': autre_adresse}), personType='PM')
    deux_cin = dossier(jeu, 3, ('CIN', {'cartes': [
        {'nom': 'TAGHRIZ', 'prenom': 'LOUMIZA', 'cin': 'ZZ199999', 'adresse': autre_adresse},
        {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': 'ZZ100003', 'adresse': '12 Avenue Tazoula, Appartement 3'}]}),
        ('DOMICILIATION', {'titulaire': 'ZELMOU BAKRITA', 'adresse': '12 AV TAZOULA APT 3'}))
    cx = base_de(tmp_path, [tiers, societe, deux_cin])
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type = 'adresse_cin_differente'") == 0


def test_types_d_operation_d_apres_le_libelle():
    assert [c3.type_operation(x) for x in (
        'VIR RECU DE ZIRMAK', 'PRLV ASSURANCE', 'PAIEMENT CARTE 1234 TAZOULA', 'CHEQUE 123', 'RETRAIT GAB',
        'VERSEMENT ESPECES', 'FRAIS DE TENUE DE COMPTE', 'ZIRMAK', None, 'VIREMENT RECU DE STE TVA CONSEIL')] == \
        ['virement', 'prelevement', 'carte', 'cheque', 'especes', 'especes', 'frais', 'autre', 'autre', 'virement']
    assert [c3.contrepartie(x) for x in ('ZIRMAK', 'PAIEMENT CARTE 1234 TAZOULA', 'VIR RECU DE ZIRMAK')] == \
        [None, 'TAZOULA', 'ZIRMAK']


def test_T02_releve_non_relu_ni_operation_ni_incoherence_de_flux(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=5000.0, relu=False))])
    assert un(cx, 'SELECT count(*) FROM c3_operation') == 0
    assert incoherences(cx) == []
    assert lignes(cx, "SELECT DISTINCT releve_relu FROM c3_revenu WHERE source = 'RELEVE_BANCAIRE'") == [(0,)]


def test_operation_reconstituee_jamais_dans_les_operations(jeu, tmp_path):
    type_, champs = releve(mois=(7,))
    champs['mois'][0]['operations'].append({'libelle': 'SALAIRE', 'credit': 9000.0})
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), (type_, champs))])
    assert un(cx, 'SELECT count(*) FROM c3_operation') == 2 and un(cx, 'SELECT count(*) FROM c1_releve_operation') == 3


def test_vehicule_de_la_facture_et_de_la_carte_grise(cx, jeu):
    ref = next(v['ref'] for v in jeu.verite if 'S18' in v['scenarios'])
    vehicules = lignes(cx, 'SELECT type_piece, chassis, immatriculation, marque, modele, prix FROM c3_vehicule WHERE '
                           'ref = ? ORDER BY 1', ref)
    assert [v[0] for v in vehicules] == ['CARTE_GRISE', 'FACTURE_PROFORMA_VEHICULE']
    assert vehicules[0][1] == 'ZZFICTIFDOUBLE001' and vehicules[0][2] and vehicules[0][3:5] == ('MARQUE FICTIVE', 'MODELE FICTIF')
    assert vehicules[1][3:5] == ('MARQUE FICTIVE', 'MODELE FICTIF') and vehicules[1][5] > 0


# ---- incohérences entre pièces -------------------------------------------------------------------------------------

@pytest.mark.parametrize('salaire, attendu', [(9000.0, 0), (9000.5, 0), (8999.0, 1), (11000.0, 0), (11001.0, 1)])
def test_salaire_du_bulletin_contre_le_releve_tolerance_au_bord(jeu, tmp_path, salaire, attendu):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=salaire))])
    trouvees = lignes(cx, "SELECT upstream_piece_id_a, repere_a, upstream_piece_id_b, repere_b, gravite FROM "
                          "c3_incoherence WHERE type = 'salaire_bulletin_releve'")
    assert len(trouvees) == attendu
    if attendu:
        assert trouvees == [('eqdom_BULLETIN_DE_PAIE_1', 'remuneration.salaire_net', 'eqdom_RELEVE_BANCAIRE_2',
                             'mois:0', 'incoherence')]


def test_tolerance_lue_dans_les_parametres(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=8000.0))
    cx = base_de(tmp_path, [d])
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type = 'salaire_bulletin_releve'") == 1
    assert lignes(cx, "SELECT valeur, provisoire FROM c6_version_parametres WHERE nom = 'c3_tolerance_salaire'") == [(0.1, 1)]
    cx.execute("UPDATE c6_version_parametres SET valeur = 0.25 WHERE nom = 'c3_tolerance_salaire'")
    c3.traiter(cx, d['ref'])
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type = 'salaire_bulletin_releve'") == 0


def test_un_seul_mois_dans_la_tolerance_suffit(jeu, tmp_path):
    type_, champs = releve(salaire=5000.0)
    champs['montant_salaire']['08/2026'] = 10000.0
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), (type_, champs))])
    assert incoherences(cx) == []


def test_adresse_de_la_cin_contre_la_quittance_et_le_releve(jeu, tmp_path):
    quittance = lambda a: ('DOMICILIATION', {'titulaire': 'ZELMOU BAKRITA', 'nom': 'ZELMOU', 'adresse': a})  # noqa: E731
    memes = dossier(jeu, 1, cin_de(1, '12 Avenue Tazoula, Appartement 3, Casablanca'),
                    quittance('12 AV TAZOULA APT 3 CASABLANCA'), releve(adresse='12 av. Tazoula appt 3'))
    autres = dossier(jeu, 2, cin_de(2, '12 Avenue Tazoula, Appartement 3'), quittance('45 RUE ZIRMAK IMM 2'),
                     releve(rib=RIB_B, adresse='45 rue Zirmak immeuble 2'))
    sans = dossier(jeu, 3, cin_de(3, '12 Avenue Tazoula, Appartement 3'), quittance(None))
    cx = base_de(tmp_path, [memes, autres, sans])
    assert sorted(lignes(cx, "SELECT ref, upstream_piece_id_a, upstream_piece_id_b FROM c3_incoherence WHERE type = "
                             "'adresse_cin_differente'")) == \
        [('ZZ26T0002', 'eqdom_CIN_0', 'eqdom_DOMICILIATION_1'), ('ZZ26T0002', 'eqdom_CIN_0', 'eqdom_RELEVE_BANCAIRE_2')]


# ---- incohérences entre dossiers, et avec le registre --------------------------------------------------------------

def test_S18_meme_chassis_dans_deux_dossiers_double_financement(cx, jeu):
    a, b = sorted(v['ref'] for v in jeu.verite if 'S18' in v['scenarios'])
    doubles = [x for x in incoherences(cx) if x[1] == 'double_financement']
    assert doubles == [(a, 'double_financement', 'incoherence', b), (b, 'double_financement', 'incoherence', a)]
    assert lignes(cx, "SELECT DISTINCT repere_a, repere_b FROM c3_incoherence WHERE type = 'double_financement'") == \
        [('CHASSIS', 'CHASSIS')]


def test_S19_meme_rib_dans_trois_dossiers_en_moins_de_trente_jours_rafale(cx, jeu):
    refs = sorted(v['ref'] for v in jeu.verite if 'S19' in v['scenarios'])
    rafales = [x for x in incoherences(cx) if x[1] == 'dossiers_en_rafale' and x[0] in refs]
    assert len(refs) == 3 and sorted({x[0] for x in rafales}) == refs and {x[2] for x in rafales} == {'signal'}


@pytest.mark.parametrize('jours, attendu', [((0, 10, 29), 3), ((0, 10, 30), 0), ((0, 29, 58), 0), ((0, 0), 0)])
def test_rafale_au_bord_de_la_fenetre_et_du_nombre(jeu, tmp_path, jours, attendu):
    dossiers = [dossier(jeu, n + 1, cin_de(n + 1), releve(), recu=f'2026-09-{1 + j:02d}T08:00:00.000Z' if j < 30 else
                        f'2026-10-{j - 29:02d}T08:00:00.000Z') for n, j in enumerate(jours)]
    cx = base_de(tmp_path, dossiers)
    assert un(cx, "SELECT count(DISTINCT ref) FROM c3_incoherence WHERE type = 'dossiers_en_rafale'") == attendu
    assert lignes(cx, "SELECT nom, valeur FROM c6_version_parametres WHERE nom LIKE 'c3_rafale%' ORDER BY 1") == \
        [('c3_rafale_dossiers', 3.0), ('c3_rafale_jours', 30.0)]


def test_rafale_par_la_meme_adresse_declaree(jeu, tmp_path):
    dossiers = [dossier(jeu, n, cin_de(n), releve(rib='999' + str(n) * 21)) for n in (1, 2, 3)]
    for d in dossiers:
        d['businessData']['civil']['address'] = '12 Avenue Tazoula, Appartement 3, Casablanca'
    cx = base_de(tmp_path, dossiers)
    assert lignes(cx, "SELECT DISTINCT type, repere_a FROM c3_incoherence") == [('dossiers_en_rafale', 'ADRESSE')]


def test_meme_rib_dans_un_autre_dossier_d_une_autre_personne(jeu, tmp_path):
    meme_personne = dossier(jeu, 9, ('CIN', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': 'ZZ100001'}), releve())
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), releve()), dossier(jeu, 2, cin_de(2), releve()), meme_personne])
    assert [x for x in incoherences(cx) if x[1] == 'rib_autre_dossier'] == [
        ('ZZ26T0001', 'rib_autre_dossier', 'incoherence', 'ZZ26T0002'),
        ('ZZ26T0002', 'rib_autre_dossier', 'incoherence', 'ZZ26T0001'),
        ('ZZ26T0002', 'rib_autre_dossier', 'incoherence', 'ZZ26T0009'),
        ('ZZ26T0009', 'rib_autre_dossier', 'incoherence', 'ZZ26T0002')]


def test_employeur_identifie_absent_du_registre(jeu, socle, tmp_path):
    ice_connu = sqlite3.connect(socle).execute('SELECT ice FROM rc_societe WHERE ice IS NOT NULL').fetchone()[0]
    emploi = lambda ice: ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'employeur': dict(  # noqa: E731
        {'raison_sociale': 'TAZOULA NEGOCE SARL'}, **({'ice': ice} if ice else {}))})
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), emploi(ice_connu)), dossier(jeu, 2, cin_de(2), emploi(None)),
                            dossier(jeu, 3, cin_de(3), emploi('999000000009999'))], socle)
    assert lignes(cx, "SELECT ref, gravite, upstream_piece_id_a, repere_a, ref_b FROM c3_incoherence WHERE type = "
                      "'employeur_absent_du_registre'") == \
        [('ZZ26T0003', 'signal', 'eqdom_ATTESTATION_TRAVAIL_SALAIRE_1', 'employeur', None)]
    sans_socle = base_de(tmp_path, [dossier(jeu, 3, cin_de(3), emploi('999000000009999'))])
    assert incoherences(sans_socle) == []                       # sans registre chargé, rien à affirmer


def test_deux_pieces_de_meme_type_avec_revenu_dans_un_dossier(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), bulletin('10 200,00'), releve(salaire=9800.0),
                releve(rib=RIB_B, salaire=9900.0),
                ('ATTESTATION_TRAVAIL_SALAIRE', {'salaire_net': 10000}), ('ATTESTATION_TRAVAIL_SALAIRE', {'salaire_net': 10100}))
    cx = base_de(tmp_path, [d])
    assert lignes(cx, "SELECT source, count(*) FROM c3_revenu WHERE nature = 'verifie' GROUP BY 1 ORDER BY 1") == \
        [('ATTESTATION_TRAVAIL_SALAIRE', 2), ('BULLETIN_DE_PAIE', 2), ('RELEVE_BANCAIRE', 4)]
    assert incoherences(cx) == []


def test_la_couche_n_ecrit_rien_sur_la_sortie(jeu, tmp_path, capfd):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=5000.0))])
    c3.traiter(cx, 'ZZ26T0001')
    sortie = capfd.readouterr()
    assert sortie.out == '' and sortie.err == ''


# ---- défauts relevés par la relecture de code ---------------------------------------------------------------------

def test_parametre_ou_valeur_par_defaut_changes_valent_sans_retraitement(jeu, tmp_path):
    dossiers = [dossier(jeu, n, cin_de(n), bulletin('10 000,00'), releve(rib='999' + str(n) * 21, salaire=8000.0))
                for n in (1, 2)]
    for d in dossiers:
        d['businessData']['declared']['employer'] = 'NEANT'
    cx = base_de(tmp_path, dossiers)
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type = 'salaire_bulletin_releve'") == 2
    assert un(cx, 'SELECT count(*) FROM c3_valeur_par_defaut') == 0
    cx.execute("INSERT INTO c6_version_parametres (version, nom, valeur, provisoire) VALUES ('2099-01-01', "
               "'c3_tolerance_salaire', 0.25, 1)")
    cx.execute("INSERT INTO ref_valeur_defaut (champ, valeur) VALUES ('employeur_declare', 'NEANT')")
    assert un(cx, "SELECT count(*) FROM c3_incoherence WHERE type = 'salaire_bulletin_releve'") == 0
    assert un(cx, 'SELECT count(*) FROM c3_valeur_par_defaut') == 2
    cx.execute("INSERT INTO c6_version_parametres (version, nom, valeur, provisoire) VALUES ('2099-01-02', "
               "'c3_rafale_dossiers', 2, 1)")
    cx.execute("UPDATE c3_cle_dossier SET valeur = 'X' WHERE type = 'RIB'")
    assert un(cx, "SELECT count(DISTINCT ref) FROM c3_incoherence WHERE type = 'dossiers_en_rafale'") == 2


def test_parametre_absent_erreur_nommee(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1))])
    cx.execute("DELETE FROM c6_version_parametres WHERE nom = 'c3_tolerance_salaire'")
    with pytest.raises(c3.ParametreAbsent):
        c3.verifier_parametres(cx)


def test_meme_rib_meme_demandeur_n_est_pas_une_incoherence_porteur_inconnu_un_signal(jeu, tmp_path):
    sans_cin = lambda n: dossier(jeu, n, ('RELEVE_BANCAIRE', {'rib': RIB_A, 'mois': []}))  # noqa: E731
    a, b = sans_cin(1), sans_cin(2)
    b['businessData']['civil']['cin'] = a['businessData']['civil']['cin']
    c = sans_cin(3)
    cx = base_de(tmp_path, [a, b, c])
    assert sorted(lignes(cx, "SELECT ref, gravite, ref_b FROM c3_incoherence WHERE type = 'rib_autre_dossier'")) == [
        ('ZZ26T0001', 'signal', 'ZZ26T0003'), ('ZZ26T0002', 'signal', 'ZZ26T0003'),
        ('ZZ26T0003', 'signal', 'ZZ26T0001'), ('ZZ26T0003', 'signal', 'ZZ26T0002')]


def test_demandeur_unique_meme_si_le_cin_declare_n_est_pas_lu(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(7))                         # CIN déclaré ZZ100001, CIN lu ZZ100007
    e = dossier(jeu, 2, cin_de(2))
    e['businessData']['civil']['cin'] = 'INCONNU'
    cx = base_de(tmp_path, [d, e])
    assert lignes(cx, 'SELECT ref, count(DISTINCT fiche) FROM c3_partie_dossier WHERE demandeur = 1 GROUP BY 1') == \
        [('ZZ26T0001', 1), ('ZZ26T0002', 1)]
    assert lignes(cx, "SELECT civil_cin FROM c3_dossier WHERE ref = 'ZZ26T0002'") == [(None,)]
    assert lignes(cx, 'SELECT count(*) FROM c3_partie_dossier p WHERE demandeur = 0 AND EXISTS (SELECT 1 FROM '
                      'c3_partie_dossier q WHERE q.ref = p.ref AND q.fiche = p.fiche AND q.demandeur = 1)') == [(0,)]


def test_adresse_equivalente_mots_en_plus_ou_ordre_change(jeu, tmp_path):
    quittance = lambda n, a: ('DOMICILIATION', {'titulaire': 'ZELMOU BAKRITA', 'adresse': a})  # noqa: E731
    cx = base_de(tmp_path, [
        dossier(jeu, 1, cin_de(1, '12 Avenue Tazoula, Appartement 3'), quittance(1, '12 AV TAZOULA APT 3 HAY ZIRMAK')),
        dossier(jeu, 2, cin_de(2, '12 Avenue Tazoula'), quittance(2, 'AV TAZOULA 12')),
        dossier(jeu, 3, cin_de(3, '12 Avenue Tazoula'), quittance(3, '14 AV TAZOULA'))])
    assert lignes(cx, "SELECT ref FROM c3_incoherence WHERE type = 'adresse_cin_differente'") == [('ZZ26T0003',)]


def test_employeur_connu_au_registre_par_son_nom_et_une_ligne_par_employeur(jeu, socle, tmp_path):
    nom = sqlite3.connect(socle).execute('SELECT denomination FROM rc_societe WHERE ice IS NULL AND denomination '
                                         "NOT LIKE '%#%' ORDER BY societe_id").fetchone()[0]
    emploi = lambda t: (t, {'nom': 'ZELMOU', 'prenom': 'BAKRITA',  # noqa: E731
                            'employeur': {'raison_sociale': nom, 'ice': '999000000008888'}})
    inconnu = lambda t: (t, {'nom': 'ZELMOU', 'prenom': 'BAKRITA',  # noqa: E731
                             'employeur': {'raison_sociale': 'NADOUL TRANS', 'ice': '999000000009999'}})
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), emploi('ATTESTATION_TRAVAIL_SALAIRE')),
                            dossier(jeu, 2, cin_de(2), inconnu('ATTESTATION_TRAVAIL_SALAIRE'),
                                    inconnu('BULLETIN_DE_PAIE'))], socle)
    assert lignes(cx, "SELECT ref FROM c3_incoherence WHERE type = 'employeur_absent_du_registre'") == [('ZZ26T0002',)]


def test_analyse_non_terminee_ou_provisoire_hors_des_incoherences(jeu, tmp_path):
    grise = ('CARTE_GRISE', {'Numéro de chassis': 'ZZFICTIFESSAI0001'})
    a = dossier(jeu, 1, cin_de(1), grise, bulletin('10 000,00'), releve(salaire=5000.0), analysisStatus='EN_COURS')
    b = dossier(jeu, 2, cin_de(2), grise, verdictProvisional=True)
    c = dossier(jeu, 3, cin_de(3), grise)
    cx = base_de(tmp_path, [a, b, c])
    assert lignes(cx, 'SELECT ref, en_cours FROM c3_dossier ORDER BY 1') == [('ZZ26T0001', 1), ('ZZ26T0002', 1),
                                                                            ('ZZ26T0003', 0)]
    assert incoherences(cx) == []


def test_types_d_operation_malgre_la_ponctuation():
    assert [c3.type_operation(x) for x in ('VIR. RECU DE ZIRMAK', 'VIR/RECU/ZIRMAK', 'CHQ.123', 'RET.GAB',
                                           'ACHAT CARTE*1234', 'VIREMENTS RECUS', 'VIRT ZIRMAK')] == \
        ['virement', 'virement', 'cheque', 'especes', 'carte', 'virement', 'virement']
    assert c3.contrepartie('VIR. RECU DE: TAZOULA') == 'TAZOULA'


def test_salaire_nul_n_est_pas_un_salaire_repere(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=0.0))])
    assert un(cx, "SELECT count(*) FROM c3_revenu WHERE source = 'RELEVE_BANCAIRE'") == 0 and incoherences(cx) == []


def test_client_connu_seulement_par_un_booleen(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de(1))
    d['businessData']['known_client'] = 'false'
    cx = base_de(tmp_path, [d])
    assert lignes(cx, 'SELECT known_client FROM c3_dossier') == [(None,)]


# ---- flux = lot, invariants ----------------------------------------------------------------------------------------

def test_traiter_dans_un_ordre_au_hasard_depuis_une_base_vide_egale_le_lot(jeu, socle, tmp_path):
    lot = base_de(tmp_path, jeu.dossiers, socle)
    flux = base_de(tmp_path, [], socle)
    dossiers = list(jeu.dossiers)
    random.Random(5).shuffle(dossiers)
    passage = c0.ouvrir_passage(flux, 'essai', 'scrutation', T0)
    for d in dossiers:
        c0.recevoir(flux, passage, d, maintenant=T0)
        for couche in COUCHES[1:]:
            couche.traiter(flux, d['ref'])
    a, b = contenu(flux), contenu(lot)
    for t in TABLES + VUES:
        assert a[t] == b[t], t
    assert b['c3_incoherence'] and b['c3_operation']


def test_flux_version_par_version_egale_le_lot(jeu, socle, tmp_path):
    flux = base_de(tmp_path, [], socle)
    lot = base_de(tmp_path, [], socle)
    for cx_, au_fil in ((flux, True), (lot, False)):
        passage = c0.ouvrir_passage(cx_, 'essai', 'scrutation', T0)
        for e in jeu.chronologie:
            c0.recevoir(cx_, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
            for couche in COUCHES[1:] if au_fil else ():
                couche.traiter(cx_, e['ref'])
    for couche in COUCHES[1:]:
        couche.construire_tout(lot)
    a, b = contenu(flux), contenu(lot)
    for t in TABLES + VUES:
        assert a[t] == b[t], t


def test_dossier_sorti_du_miroir_plus_rien_et_l_autre_dossier_n_est_plus_en_double(jeu, tmp_path):
    grise = ('CARTE_GRISE', {'Numéro de chassis': 'ZZFICTIFESSAI0001', 'Immatriculation': 'FICTIF-1'})
    a, b = dossier(jeu, 1, cin_de(1), grise), dossier(jeu, 2, cin_de(2), grise)
    cx = base_de(tmp_path, [a, b])
    assert len(incoherences(cx)) == 2
    cx.execute('DELETE FROM "Piece" WHERE "dossierId" = ?', (a['id'],))
    cx.execute('DELETE FROM "Dossier" WHERE ref = ?', (a['ref'],))
    for couche in COUCHES[1:]:
        couche.traiter(cx, a['ref'])
    assert incoherences(cx) == []
    assert {t: un(cx, f'SELECT count(*) FROM {t} WHERE ref = ?', a['ref']) for t in TABLES} == dict.fromkeys(TABLES, 0)


@pytest.mark.parametrize('nom, viol', [
    ('c3_dossier_absent_du_miroir', "UPDATE c3_dossier SET ref = 'ZZ26ABSENT' WHERE ref = (SELECT min(ref) FROM c3_dossier)"),
    ('c3_dossier_du_miroir_non_traite', 'DELETE FROM c3_dossier WHERE ref = (SELECT min(ref) FROM c3_dossier)'),
    ('c3_revenu_verifie_sans_piece', "UPDATE c3_revenu SET upstream_piece_id = 'absente' WHERE nature = 'verifie'"),
    ('c3_incoherence_sans_ses_deux_faits', "INSERT INTO c3_incoherence_locale VALUES ('ZZ26T0001', "
                                           "'adresse_cin_differente', 'eqdom_CIN_0', 'adresse', 'absente', 'adresse')"),
    ('c3_operation_non_lue', "UPDATE c3_operation SET date_operation = NULL, date_operation_brute = NULL"),
    ('c3_ligne_sans_dossier', "UPDATE c3_compte SET ref = 'ZZ26ABSENT'"),
])
def test_chaque_invariant_de_c3_devient_rouge_quand_on_le_viole(jeu, tmp_path, capsys, nom, viol):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(1), bulletin('10 000,00'), releve(salaire=5000.0)),
                            dossier(jeu, 2, cin_de(2), releve(rib=RIB_B))])
    cx.commit()
    chemin = cx.execute('PRAGMA database_list').fetchone()[2]
    assert verifier.verifier(chemin) == 0
    cx.executescript(viol)
    cx.commit()
    assert verifier.verifier(chemin) == 1
    sortie = capsys.readouterr().out
    assert f'ÉCART  {nom} : ' in sortie and 'ZZ' not in sortie
    assert all(re.fullmatch(r'(ok    |ÉCART ) [a-z0-9_]+ : \d+|invariants vérifiés : \d+', l) for l in sortie.splitlines())


def test_la_couche_suit_c2_dans_l_ordre_des_couches():
    assert [c.nom for c in COUCHES[:4]] == ['c0', 'c1', 'c2', 'c3']
