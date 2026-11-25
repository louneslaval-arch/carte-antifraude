"""Base client construite depuis la base de la carte (tables af_*, bl_*, rc_* du kit) : chaque dossier redevient un
`DossierDetail` (pièces et champs aux clés de production), passe par la couche 0, et toutes les couches se construisent
avec le socle de la même base. La base client et la vue 360° s'en servent telles quelles."""
import os
import shutil
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'pipeline'), os.path.join(RACINE, 'api')]
KIT = os.path.join(RACINE, 'jeu_essai', 'sortie', 'kit', 'essai.sqlite')
pytestmark = pytest.mark.skipif(not os.path.exists(KIT), reason='base du kit fictive absente (jeu_essai/construire.sh kit)')

import charger_antifraude  # noqa: E402
from outils import base_client_depuis_carte as bc  # noqa: E402

T0 = '2026-11-25T10:00:00.000Z'


def _inserer(cx, table, **valeurs):
    colonnes = [r[1] for r in cx.execute(f'PRAGMA table_info({table})')]
    ligne = {c: valeurs.get(c) for c in colonnes}
    cx.execute(f'INSERT INTO {table} ({", ".join(ligne)}) VALUES ({", ".join("?" * len(ligne))})', list(ligne.values()))


@pytest.fixture(scope='module')
def carte(tmp_path_factory):
    chemin = str(tmp_path_factory.mktemp('carte') / 'carte_kit.sqlite')
    shutil.copy(KIT, chemin)
    cx = sqlite3.connect(chemin)
    cx.executescript(charger_antifraude.SCHEMA)
    _inserer(cx, 'af_dossier', ref='ZZD001', lot='prod', actif=1, type_personne='PP', csp='SALARIE_PRIVE', produit='DISPO',
             client_nom='EL ZOUBAQIRI MOHAMED', client_cin='ZZ900001', client_cin_norm='ZZ900001',
             employeur_declare='EXEMPLE ATLAS NEGOCE', revenu_declare=12000.0, categorie='B', verdict='SUSPECT',
             statut_analyse='COMPLETE', alertes_majeures=2, recu_le='2026-10-02', nb_pieces=3)
    _inserer(cx, 'af_personne', af_personne_id=1, dossier_ref='ZZD001', lot='prod', role='demandeur',
             nom_complet='EL ZOUBAQIRI MOHAMED', nom='EL ZOUBAQIRI', prenom='MOHAMED', cin_brut='ZZ900001',
             cin_norm='ZZ900001', date_naissance='05/03/1976', adresse='12 RUE EXEMPLE CASABLANCA', piece_type='CIN',
             piece_id='p1', source='AMONT')
    _inserer(cx, 'af_societe', af_societe_id=1, dossier_ref='ZZD001', lot='prod', role='employeur',
             denomination='EXEMPLE ATLAS NEGOCE SARL', piece_type='BULLETIN_DE_PAIE', piece_id='p2', source='AMONT')
    _inserer(cx, 'af_personne', af_personne_id=2, dossier_ref='ZZD001', lot='prod', role='salarie',
             nom='EL ZOUBAQIRI', prenom='MOHAMED', cin_brut='ZZ900001', cin_norm='ZZ900001', qualite='COMPTABLE',
             piece_type='BULLETIN_DE_PAIE', piece_id='p2', source='AMONT')
    _inserer(cx, 'af_compte', af_compte_id=1, dossier_ref='ZZD001', lot='prod', rib='999000000000000000000042',
             banque='BANQUE ZZ', titulaire='EL ZOUBAQIRI MOHAMED', piece_type='ATTESTATION_RIB', piece_id='p3')
    _inserer(cx, 'af_dossier', ref='ZZD002', lot='prod', actif=1, type_personne='PM', produit='LOA',
             client_nom='EXEMPLE NOVA TRANS SARL AU', verdict='VALEUR_INCONNUE', categorie='Z', statut_analyse=None,
             recu_le='2026-10-05')
    _inserer(cx, 'af_societe', af_societe_id=2, dossier_ref='ZZD002', lot='prod', role='societe_cliente',
             denomination='EXEMPLE NOVA TRANS SARL AU', rc_brut='999004', rc_num='999004', tribunal_code='TANGER',
             capital='100000', objet='TRANSPORT', piece_type='REGISTRE_COMMERCE', piece_id='p4', source='AMONT')
    _inserer(cx, 'af_personne', af_personne_id=3, dossier_ref='ZZD002', lot='prod', role='gerant',
             nom_complet='BENTOUKAZ KARIM', nom='BENTOUKAZ', prenom='KARIM', cin_brut='ZZ900002', cin_norm='ZZ900002',
             qualite='gérant', parts='500', piece_type='REGISTRE_COMMERCE', piece_id='p4', source='AMONT')
    cx.commit()
    cx.close()
    return chemin


@pytest.fixture(scope='module')
def base(carte, tmp_path_factory):
    chemin = str(tmp_path_factory.mktemp('base') / 'base_client.sqlite')
    bilan = bc.construire(carte, chemin, maintenant=T0)
    assert bilan == dict(dossiers=2, pieces=4, miroir_refuse=0)
    return chemin


def _details(carte):
    cx = sqlite3.connect(carte)
    try:
        return {d['ref']: d for d in bc.dossiers(cx)}
    finally:
        cx.close()


def test_chaque_piece_reprend_les_cles_de_production(carte):
    d = _details(carte)['ZZD001']
    pieces = {p['type']: p['fields'] for p in d['pieces']}
    assert pieces['CIN']['cin'] == 'ZZ900001' and pieces['CIN']['nom'] == 'EL ZOUBAQIRI'
    assert pieces['BULLETIN_DE_PAIE']['employeur']['raison_sociale'] == 'EXEMPLE ATLAS NEGOCE SARL'
    assert pieces['BULLETIN_DE_PAIE']['employe']['cin'] == 'ZZ900001'
    assert pieces['ATTESTATION_RIB']['rib'] == '999000000000000000000042'
    assert d['businessData']['declared']['monthly_income'] == 12000.0
    assert d['businessData']['civil']['cin'] == 'ZZ900001' and d['verdict'] == 'SUSPECT'


def test_la_societe_porte_ses_gerants(carte):
    rc = next(p['fields'] for p in _details(carte)['ZZD002']['pieces'] if p['type'] == 'REGISTRE_COMMERCE')
    assert rc['numero_rc'] == '999004' and rc['ville_tribunal'] == 'TANGER' and rc['capital_social'] == '100000'
    assert rc['gerants'][0]['cin'] == 'ZZ900002' and rc['gerants'][0]['parts_sociales'] == '500'


def test_une_valeur_hors_des_enumerations_de_kamal_est_laissee_vide(carte):
    d = _details(carte)['ZZD002']
    assert d['verdict'] is None and d['category'] is None and d['analysisStatus'] == 'COMPLETE'


def test_la_base_client_et_la_vue_360_se_chargent(base):
    from app.base_client import BaseClient
    b = BaseClient(base)
    clients = b.clients()
    assert len(clients) == 2
    personne = next(c for c in clients if c['type'] == 'personne')
    fiche = b.fiche(personne['indice'])
    assert fiche['identite']['cin'] == 'ZZ900001' and fiche['identite']['inscrit'] is True
    assert fiche['dossiers'][0]['verdict'] == 'SUSPECT' and fiche['comptes']
    assert fiche['vue360']['etoile'] and any(s['role'] == 'salarié' for s in fiche['societes'])
    societe = next(c for c in clients if c['type'] == 'societe')
    f2 = b.fiche(societe['indice'])
    assert any(p['role'] == 'gérant' for p in f2['personnes'])


def test_garde_fou_et_base_hors_du_depot(carte, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('CARTE_DONNEES_REELLES', raising=False)
    assert bc.main(['--carte', carte, '--base', str(tmp_path / 'b.sqlite')]) == 2
    assert 'CARTE_DONNEES_REELLES' in capsys.readouterr().err
    assert bc.main(['--carte', carte, '--base', os.path.join(RACINE, 'jeu_essai', 'sortie', 'zz_b.sqlite')]) == 2
    assert 'hors du dépôt' in capsys.readouterr().err
