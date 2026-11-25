"""Vérification de l'intégration C7 dans le graphe C5 (sans PostgreSQL)."""
from pipeline.couches import c5_graphe_postgresql as c5


POIDS = {'c7_poids_caution': 0.8, 'c7_poids_coemprunteur': 0.9,
         'c7_poids_reference_personnelle': 0.5, 'c7_poids_signataire': 0.5,
         'c7_poids_cabinet_comptable': 0.4, 'c7_poids_meme_immeuble': 0.2}


def test_caution_relativement_a_un_demandeur():
    voisins, tailles = c5._graphe_c7([('D1', 'caution', 'pp_2', 'n1')], {'D1': {'pp_1'}}, POIDS)
    assert voisins['pp_1'][0][0] == 'pp_2'
    assert voisins['pp_1'][0][2] == 0.8
    assert voisins['pp_2'][0][0] == 'pp_1'
    assert tailles == {}


def test_cle_commune_entre_deux_dossiers():
    voisins, tailles = c5._graphe_c7(
        [('D1', 'cabinet_comptable', None, 'noeud_secret'),
         ('D2', 'cabinet_comptable', None, 'noeud_secret')],
        {'D1': {'pp_1'}, 'D2': {'pp_2'}}, POIDS)
    assert voisins['pp_1'][0][0] == 'pp_2'
    assert voisins['pp_1'][0][2] == 0.4
    assert tailles['noeud_secret'] == 2
    assert 'noeud_secret' not in voisins['pp_1'][0][3].values()


def test_une_seule_piece_ne_cree_pas_de_lien():
    voisins, tailles = c5._graphe_c7(
        [('D1', 'meme_immeuble', None, 'n1')], {'D1': {'pp_1', 'pp_2'}}, POIDS)
    assert not voisins
    assert not tailles


def test_cles_distinctes_ne_lient_pas():
    voisins, _ = c5._graphe_c7(
        [('D1', 'signataire', None, 'n1'), ('D2', 'signataire', None, 'n2')],
        {'D1': {'pp_1'}, 'D2': {'pp_2'}}, POIDS)
    assert not voisins
