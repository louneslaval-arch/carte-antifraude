"""Vue 360° d'une entité : profil (personne salariée, personne entrepreneur, personne morale), synthèse des revenus,
contrôles rangés par famille. Fonctions pures, puis la fiche servie par l'API. Fictif."""
import os
import sqlite3
import sys

import pytest

from conftest import RACINE, connecte

sys.path.insert(0, os.path.join(RACINE, 'api'))
from app import vue360  # noqa: E402

from test_base_client import avec_base, base_demo, pytestmark as _sans_base  # noqa: E402,F401


# ---- profil -----------------------------------------------------------------------------------------------------------
def test_une_societe_est_une_personne_morale():
    assert vue360.profil('societe', 'SOCIETE', []) == ('pm', False)
    assert vue360.profil('societe', None, ['gerant']) == ('pm', False)


@pytest.mark.parametrize('csp', ['SALARIE_PRIVE', 'FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE'])
def test_une_csp_salariee_donne_le_profil_salarie(csp):
    assert vue360.profil('personne', csp, []) == ('salarie', False)


@pytest.mark.parametrize('csp', ['RETRAITE_PUBLIC', 'RETRAITE_CIMR', 'RETRAITE_INDETERMINE'])
def test_un_retraite_est_range_avec_les_salaries(csp):
    assert vue360.profil('personne', csp, []) == ('salarie', True)


@pytest.mark.parametrize('csp', ['PROFESSION_LIBERALE', 'LOUEUR'])
def test_une_csp_independante_donne_le_profil_entrepreneur(csp):
    assert vue360.profil('personne', csp, []) == ('entrepreneur', False)


def test_la_csp_du_dossier_l_emporte_sur_le_registre():
    """Salarié et associé d'une société : profil salarié (la société est signalée à part)."""
    assert vue360.profil('personne', 'SALARIE_PRIVE', ['associe', 'gerant']) == ('salarie', False)


@pytest.mark.parametrize('csp', [None, 'AUTRE'])
def test_sans_csp_parlante_un_gerant_ou_associe_est_entrepreneur(csp):
    assert vue360.profil('personne', csp, ['gerant']) == ('entrepreneur', False)
    assert vue360.profil('personne', csp, ['associe']) == ('entrepreneur', False)


def test_un_role_termine_ne_fait_pas_un_entrepreneur():
    assert vue360.profil('personne', None, ['gerant_sortant', 'cedant', 'liquidateur']) == ('salarie', False)


# ---- sociétés « aussi » -----------------------------------------------------------------------------------------------
def test_un_salarie_associe_garde_ses_societes_en_bandeau():
    societes = [dict(indice=7, nom='Société A', role='associé'), dict(indice=8, nom='Société B', role='salarié'),
                dict(indice=9, nom='Société C', role='gérant sortant')]
    aussi = vue360.aussi('salarie', societes)
    assert [s['indice'] for s in aussi] == [7]


def test_aucun_bandeau_pour_un_entrepreneur_ou_une_societe():
    societes = [dict(indice=7, nom='Société A', role='gérant')]
    assert vue360.aussi('entrepreneur', societes) == [] and vue360.aussi('pm', societes) == []


# ---- revenus ----------------------------------------------------------------------------------------------------------
def test_synthese_des_revenus_garde_le_dernier_montant_de_chaque_piece_et_l_ecart():
    revenus = [
        dict(nature='declare', source='businessData', montant=9000, annee=None, mois=None),
        dict(nature='verifie', source='BULLETIN_DE_PAIE', montant=8000, annee=2026, mois=8),
        dict(nature='verifie', source='BULLETIN_DE_PAIE', montant=8200, annee=2026, mois=9),
        dict(nature='verifie', source='ATTESTATION_TRAVAIL_SALAIRE', montant=8200, annee=2026, mois=7),
        dict(nature='verifie', source='RELEVE_BANCAIRE', montant=6150, annee=2026, mois=9),
        dict(nature='verifie', source='RELEVE_BANCAIRE', montant=6000, annee=2026, mois=7),
    ]
    s = vue360.synthese_revenus(revenus)
    assert s['declare'] == 9000
    assert s['pieces'] == {'BULLETIN_DE_PAIE': 8200, 'ATTESTATION_TRAVAIL_SALAIRE': 8200, 'RELEVE_BANCAIRE': 6150}
    assert s['ecart'] == pytest.approx(0.25)          # (8200 − 6150) / 8200


def test_synthese_sans_revenu_ni_ecart():
    assert vue360.synthese_revenus([]) == dict(declare=None, pieces={}, ecart=None)
    seul = vue360.synthese_revenus([dict(nature='verifie', source='ATTESTATION_PENSION', montant=4000, annee=2026,
                                         mois=1)])
    assert seul['ecart'] is None


# ---- contrôles --------------------------------------------------------------------------------------------------------
def test_controles_ranges_par_famille_dans_l_ordre_du_profil_avec_le_catalogue():
    donnees = [dict(dossier=3, controles=[
        dict(controle='EMP-02', resultat='ANOMALIE', criticite='CRITIQUE'),
        dict(controle='IDT-01', resultat='CONFORME', criticite='CRITIQUE'),
        dict(controle='PRO-01', resultat='CONFORME', criticite='MINEURE'),
        dict(controle='ZZZ-99', resultat='CONFORME', criticite=None)])]
    familles = vue360.controles(donnees, 'salarie')
    assert [f['famille'] for f in familles][:2] == ['Revenus et employeur', 'Identité']
    emp = familles[0]['controles'][0]
    assert emp['libelle'] == 'Source du revenu au nom du demandeur' and emp['description']
    assert emp['resultat'] == 'ANOMALIE' and emp['dossier'] == 3
    assert familles[0]['anomalies'] == 1
    autre = next(f for f in familles if f['famille'] == 'Autres')
    assert autre['controles'][0]['libelle'] == 'ZZZ-99'


def test_une_societe_voit_d_abord_les_controles_de_ses_dirigeants():
    donnees = [dict(dossier=1, controles=[dict(controle='EMP-03', resultat='CONFORME', criticite='MAJEURE'),
                                          dict(controle='IDT-17', resultat='CONFORME', criticite='CRITIQUE')])]
    assert vue360.controles(donnees, 'pm')[0]['famille'] == 'Identité'


# ---- fiche servie -----------------------------------------------------------------------------------------------------
def _fiche(c, b, fiche):
    return c.get(f'/api/base/clients/{b.indice_fiche[fiche]}').json()


def test_la_fiche_porte_sa_vue_360_selon_le_profil(avec_base, base_demo):  # noqa: F811
    cx = sqlite3.connect(base_demo)
    salarie = cx.execute("SELECT d.fiche FROM c3_demandeur d JOIN c3_dossier x ON x.ref = d.ref "
                         "WHERE x.csp = 'SALARIE_PRIVE' LIMIT 1").fetchone()
    liberal = cx.execute("SELECT d.fiche FROM c3_demandeur d JOIN c3_dossier x ON x.ref = d.ref "
                         "WHERE x.csp = 'PROFESSION_LIBERALE' AND d.fiche NOT IN (SELECT d2.fiche FROM c3_demandeur d2 "
                         "JOIN c3_dossier x2 ON x2.ref = d2.ref WHERE x2.csp <> 'PROFESSION_LIBERALE') LIMIT 1").fetchone()
    societe = cx.execute("SELECT d.fiche FROM c3_demandeur d JOIN c3_dossier x ON x.ref = d.ref "
                         "WHERE x.\"personType\" = 'PM' LIMIT 1").fetchone()
    if not (salarie and liberal and societe):
        pytest.skip('profils absents de cette base')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        v = _fiche(c, b, salarie[0])['vue360']
        assert v['profil'] == 'salarie' and v['csp'] == 'SALARIE_PRIVE'
        assert {'revenus', 'controles', 'aussi', 'retraite', 'tuiles'} <= set(v)
        assert v['tuiles'][0]['groupe'] == 'Liste noire' and 8 <= sum(len(g['tuiles']) for g in v['tuiles']) <= 24
        assert 'employeur_clients' in v['entite']
        assert _fiche(c, b, liberal[0])['vue360']['profil'] == 'entrepreneur'
        assert _fiche(c, b, societe[0])['vue360']['profil'] == 'pm'


def test_une_fiche_citee_seulement_n_a_ni_revenu_ni_controle(avec_base, base_demo):  # noqa: F811
    cx = sqlite3.connect(base_demo)
    ligne = cx.execute("SELECT m.fiche FROM c2_mention m WHERE m.source = 'v2' AND m.fiche LIKE 'pp_%' AND m.fiche NOT IN "
                       "(SELECT fiche FROM c3_demandeur) LIMIT 1").fetchone()
    if ligne is None:
        pytest.skip('aucune fiche citée seulement')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        v = _fiche(c, etat.base_client, ligne[0])['vue360']
        assert v['csp'] is None and v['revenus']['pieces'] == {} and v['controles'] == []
