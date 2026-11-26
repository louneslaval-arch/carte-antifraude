"""Tests unitaires sans accès à AWS : pytest -q tests/test_carte_globale_pg.py"""

import pytest

from api.app.carte_globale_pg import CarteGlobalePG, _opaque


def test_identifiants_opaques_stables():
    secret = 'a' * 40
    assert _opaque('i', 123, secret) == _opaque('i', 123, secret)
    assert _opaque('i', 123, secret) != _opaque('bl', 123, secret)
    assert '123' not in _opaque('i', 123, secret)


def test_secret_obligatoire():
    with pytest.raises(ValueError):
        CarteGlobalePG('postgresql://example', 'trop-court')


def test_limites_avant_connexion():
    service = CarteGlobalePG('postgresql://example', 'a' * 40)
    with pytest.raises(ValueError):
        service.graphe(501)
