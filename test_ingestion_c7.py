"""Contrat C7 du webhook/JSON : uniquement les relations explicites."""
import pytest

from ingester_json_postgresql import relations_c7


def test_aucune_relation_implicite():
    assert relations_c7({'pieces': [{'fields': {'cin': 'AB123457'}}]}) is None


def test_liste_vide_est_une_suppression_explicite():
    assert relations_c7({'relationsComplementaires': []}) == []


def test_relation_caution_attestee():
    ligne = {'code': 'caution', 'cin': 'AB123457', 'source_piece': 'piece_test'}
    assert relations_c7({'relationsComplementaires': [ligne]}) == [ligne]


@pytest.mark.parametrize('valeur', [None, {}, 'caution', 12])
def test_forme_invalide_refusee(valeur):
    with pytest.raises(ValueError):
        relations_c7({'relationsComplementaires': valeur})


def test_preuve_obligatoire():
    with pytest.raises(ValueError):
        relations_c7({'relationsComplementaires': [{'code': 'caution', 'cin': 'AB123457'}]})
