"""Tests de la normalisation (étape E) : fonctions pures reprises d'extraire_json_v2.py, une forme par test,
et propriétés (jamais d'exception, stabilité)."""

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from pipeline.normalisation import cles, valeurs  # noqa: E402

CIN_DEMO = 'A' + '123456'          # forme de démonstration, construite ici pour passer la garde
MASQUE = 'X' * 6


# ---- montant -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('brut, attendu', [
    ('30 000,00', 30000.0), ('1.250,50 DH', 1250.5), ('1,250.50', 1250.5), ('12500', 12500.0), ('12500.5', 12500.5),
    ('12 500', 12500.0), ('9000,5', 9000.5), (' 8 800,00 MAD ', 8800.0), ('-150,25', -150.25), (12500, 12500.0),
    (12500.5, 12500.5), (0, 0.0), ('0', 0.0), ('30 000,00', 30000.0), ('1.250.000,00', 1250000.0),
])
def test_montant_formes_rencontrees(brut, attendu):
    assert valeurs.montant(brut) == pytest.approx(attendu)


@pytest.mark.parametrize('brut', [None, '', '   ', 'DH', 'néant', '-', '--', '1-2', '1,2,3.4.5', True, False,
                                  [], {}, '12/03/2026', float('nan'), float('inf')])
def test_montant_illisible_rend_rien(brut):
    assert valeurs.montant(brut) is None


@given(st.text())
@settings(max_examples=300)
def test_montant_ne_leve_jamais_et_est_stable(texte):
    m = valeurs.montant(texte)
    assert m is None or (isinstance(m, float) and m == m and abs(m) != float('inf'))
    assert valeurs.montant(m) == m


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12))
def test_montant_d_un_nombre_est_ce_nombre(x):
    assert valeurs.montant(x) == x


# ---- dates ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('brut, annee, attendu', [
    ('05/03/2026', None, '2026-03-05'), ('5/3/2026', None, '2026-03-05'), ('05-03-2026', None, '2026-03-05'),
    ('05.03.2026', None, '2026-03-05'), ('2026-03-05', None, '2026-03-05'), ('2026-03-05T10:00:00.000Z', None, '2026-03-05'),
    ('05/03', 2026, '2026-03-05'), ('28/12', 2025, '2025-12-28'), ('  05/03/2026 ', None, '2026-03-05'),
])
def test_date_formes_rencontrees(brut, annee, attendu):
    assert valeurs.date_iso(brut, annee) == attendu


@pytest.mark.parametrize('brut, annee', [
    ('05/03', None),                    # jj/mm sans année connue : jamais la date du jour
    ('31/02/2026', None), ('00/01/2026', None), ('15/13/2026', None), ('99/99', 2026),     # dates impossibles
    ('mars 2026', None), ('', None), (None, None), (20260305, None), ('05/03/26', None),
])
def test_date_illisible_ou_impossible_rend_rien(brut, annee):
    assert valeurs.date_iso(brut, annee) is None


@given(st.text(), st.one_of(st.none(), st.integers(min_value=-5, max_value=10 ** 6)))
@settings(max_examples=300)
def test_date_ne_leve_jamais_et_est_stable(texte, annee):
    d = valeurs.date_iso(texte, annee)
    assert d is None or (len(d) == 10 and valeurs.date_iso(d) == d)


# ---- texte, CIN, RIB -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('brut, attendu', [
    ('  Hôtel   Zérafi ', 'HOTEL ZERAFI'), ('élève', 'ELEVE'), ('', None), (None, None), ('   ', None),
    (12, '12'),
])
def test_texte_norm(brut, attendu):
    assert valeurs.texte_norm(brut) == attendu


def test_texte_non_latin_est_garde():
    arabe = ''.join(chr(c) for c in (0x0645, 0x062D, 0x0645, 0x062F))
    assert valeurs.texte_norm(' ' + arabe + ' ') == arabe


@pytest.mark.parametrize('brut, attendu', [
    ('ZZ123456', 'ZZ123456'), ('zz 123456', 'ZZ123456'), ('ZZ-123.456', 'ZZ123456'), ('Z' + '1234', 'Z' + '1234'),
    (CIN_DEMO, None), ('AB' + '123456', None), (MASQUE, None), ('N/A', None), ('', None), (None, None),
    ('123456', None), ('ZZZ123456', None), ('ZZ12', None), ('ZZ12345678', None),
])
def test_cin_norm(brut, attendu):
    assert valeurs.cin_norm(brut) == attendu


@pytest.mark.parametrize('brut, attendu', [
    ('999000000000000000000001', '999000000000000000000001'), ('999 780 0000000000000001 23', '999780000000000000000123'),
    ('9990000000000001', '9990000000000001'), ('12345', None), ('', None), (None, None), ('RIB illisible', None),
])
def test_rib_norm(brut, attendu):
    assert valeurs.rib_norm(brut) == attendu


@given(st.text())
@settings(max_examples=200)
def test_normalisations_stables_sur_une_chaine_quelconque(texte):
    for f in (valeurs.texte_norm, valeurs.cin_norm, valeurs.rib_norm):
        une_fois = f(texte)
        assert f(une_fois) == une_fois


# ---- aplatissement -------------------------------------------------------------------------------------------------

def test_aplatir_objets_agregats_et_listes():
    champs = {'nom': 'A', 'employeur': {'raison_sociale': 'B', 'adresse': None},
              'montant_salaire': {'07/2026': 9000.0, '08/2026': '9 100,00'},
              'mois': [{'mois': 7}], 'gerants': [{'cin': 'ZZ000001'}], 'missing': ['a', 'b'], 'vide': {}, 'liste_vide': []}
    assert valeurs.aplatir(champs) == [
        ('nom', 'A'), ('employeur.raison_sociale', 'B'), ('employeur.adresse', None),
        ('montant_salaire[07/2026]', 9000.0), ('montant_salaire[08/2026]', '9 100,00'),
        ('missing', '["a", "b"]'), ('liste_vide', '[]')]


@pytest.mark.parametrize('champs', [None, [], 'texte', 3, {'a': {'b': {'c': {'d': 1}}}}, {1: 2}])
def test_aplatir_ne_leve_jamais(champs):
    assert isinstance(valeurs.aplatir(champs), list)


# ---- clés ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('type_piece, cle, attendu', [
    ('REGISTRE_COMMERCE', 'nom_societe', 'denomination_sociale'), ('STATUTS', 'siege_social', 'adresse_siege'),
    ('REGISTRE_COMMERCE', 'numero_cin_gerant', 'cin'), ('CIN', 'numero_cin', 'cin'),
    ('RELEVE_BANCAIRE', 'raison_sociale', 'titulaire_compte'),        # titulaire sur un relevé…
    ('ATTESTATION_TRAVAIL_SALAIRE', 'raison_sociale', 'raison_sociale'),   # … société ailleurs
    ('RELEVE_BANCAIRE', 'rib', 'numero_compte'), ('BULLETIN_DE_PAIE', 'rib', 'rib'),
    ('CARTE_GRISE', 'Numéro de chassis', 'numero_chassis'), ('STATUTS', 'capital', 'capital_social'),
    ('FACTURE_PROFORMA_VEHICULE', 'capital', 'capital'), ('CIN', 'cin', 'cin'), ('CIN', 'cle_jamais_vue', 'cle_jamais_vue'),
])
def test_cle_canonique_propre_au_type_de_piece(type_piece, cle, attendu):
    assert cles.canon(type_piece, cle) == attendu


@pytest.mark.parametrize('type_piece, cle, valeur, attendu', [
    ('BULLETIN_DE_PAIE', 'remeration.salaire_net', '1', 'cle_inventee'),
    ('ATTESTATION_TRAVAIL_SALAIRE', 'revelation.salaire_brut', '1', 'cle_inventee'),
    ('ATTESTATION_RIB', 'filiation_complete', None, 'champ_cin_hors_cin'),
    ('DOMICILIATION', 'date_expiration', None, 'champ_cin_hors_cin'),
    ('CARTE_PROFESSIONNELLE', 'mrz_name', 'X', 'champ_cin_hors_cin'),
    ('CIN', 'filiation_complete', 'A', 'normal'), ('CARTE_GRISE', 'date_expiration', '01/01/2030', 'normal'),
    ('CIN', 'nom', 'JOHN DOE', 'gabarit'), ('CIN', 'cin', CIN_DEMO, 'gabarit'), ('CIN', 'cin', ' n/a ', 'gabarit'),
    ('CIN', 'cin', MASQUE, 'gabarit'), ('CIN', 'nom', 'DOE', 'normal'), ('CIN', 'cin', 'ZZ123456', 'normal'),
])
def test_statut_d_une_cle(type_piece, cle, valeur, attendu):
    assert cles.statut_cle(type_piece, cle, valeur) == attendu


def test_table_de_reference_couvre_la_correspondance_du_readme_de_kamal():
    lignes = cles.lignes_de_reference()
    assert ('*', 'nom_societe', 'denomination_sociale') in lignes
    assert ('*', 'numero_cin', 'cin') in lignes and ('RELEVE_BANCAIRE', 'rib', 'numero_compte') in lignes
    assert len({(t, c) for t, c, _ in lignes}) == len(lignes)          # une seule cible par (type, clé)
    for type_piece, cle, cible in lignes:
        if type_piece != '*':
            assert cles.canon(type_piece, cle) == cible


# ---- défauts relevés par les relectures ----------------------------------------------------------------------------

def test_montant_en_chiffres_d_une_autre_ecriture():
    from pipeline.normalisation.valeurs import montant
    assert montant('\u0661\u0662\u0663') == 123.0 and montant('1\u0662\u0663') == 123.0
    assert montant('\u0661\u0662\u0663,\u0665\u0660') == 123.5


def test_date_suivie_d_autres_chiffres_n_est_pas_une_date():
    from pipeline.normalisation.valeurs import date_iso
    assert date_iso('06.12.' + '345678') is None and date_iso('2026-01-155') is None
    assert date_iso('06/12/2025 10:30') == '2025-12-06' and date_iso('2025-12-06T10:30:00.000Z') == '2025-12-06'


@pytest.mark.parametrize('type_piece, attendu', [
    ('CIN', 'normal'), ('CARTE_GRISE', 'normal'), ('BULLETIN_DE_PAIE', 'normal'), ('REGISTRE_COMMERCE', 'normal'),
    ('ATTESTATION_RIB', 'champ_cin_hors_cin'), ('DOMICILIATION', 'champ_cin_hors_cin'),
    ('CARTE_PROFESSIONNELLE', 'champ_cin_hors_cin'),
])
def test_cin_lu_hors_d_une_piece_qui_le_porte(type_piece, attendu):
    from pipeline.normalisation import cles
    assert cles.statut_cle(type_piece, 'cin', 'ZZ' + '123456') == attendu
