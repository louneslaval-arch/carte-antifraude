"""Contrat des six relations : python -m pytest -q test_c7_relations_complementaires.py"""

import pytest

from pipeline.couches import c7_relations_complementaires as c7


@pytest.mark.parametrize('code', ['caution', 'coemprunteur', 'reference_personnelle', 'signataire'])
def test_personne_exige_cin(code):
    result = c7.preparer({'code': code, 'cin': 'AB123457', 'source_piece': 'piece_fictive'})
    assert result[0] == code and result[2] == 'PP'
    assert 'AB123457' not in result[1]
    with pytest.raises(ValueError):
        c7.preparer({'code': code, 'nom': 'NOM SEUL', 'source_piece': 'piece_fictive'})


def test_cabinet_exige_ice():
    r = c7.preparer({'code': 'cabinet_comptable', 'ice': '123456789012345',
                    'source_piece': 'piece_fictive'})
    assert r[2] == 'PM' and len(r[1]) == 24
    with pytest.raises(ValueError):
        c7.preparer({'code': 'cabinet_comptable', 'ice': '123', 'source_piece': 'p'})


def test_immeuble_exige_adresse_precise():
    r = c7.preparer({'code': 'meme_immeuble', 'adresse': '12 RUE DES ACACIAS BATIMENT B',
                    'ville': 'Casablanca', 'source_piece': 'piece_fictive'})
    assert r[2] == 'IMMEUBLE'
    with pytest.raises(ValueError):
        c7.preparer({'code': 'meme_immeuble', 'adresse': 'Casablanca',
                     'ville': 'Casablanca', 'source_piece': 'p'})


def test_source_obligatoire():
    with pytest.raises(ValueError):
        c7.preparer({'code': 'caution', 'cin': 'AB123457'})
