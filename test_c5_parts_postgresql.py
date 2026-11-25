"""Tests du poids des participations C5, sans PostgreSQL.

Commande : python -m pytest -q test_c5_parts_postgresql.py
"""

import pytest

from pipeline.couches.c5_graphe_postgresql import poids_participation


P = {'c5_poids_associe': 0.5, 'c5_poids_inconnu': 0.3,
     'c5_poids_gerant': 0.7}


@pytest.mark.parametrize('parts,attendu', [
    ('0', 0.3), ('25', 0.4), ('50%', 0.5), ('75,0', 0.6),
    ('100', 0.7),
])
def test_participation(parts, attendu):
    assert poids_participation(P, 'associe', parts) == pytest.approx(attendu)


@pytest.mark.parametrize('parts', [None, '', '-5', '101', 'inconnu'])
def test_part_inconnue_garde_le_parametre(parts):
    assert poids_participation(P, 'associe', parts) == 0.5


def test_gerant_reste_a_poids_fixe():
    assert poids_participation(P, 'gerant', '80') == 0.7
