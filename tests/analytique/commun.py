"""Constantes et aides communes aux tests de la couche 7 (le montage est dans conftest.py)."""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
for chemin in (os.path.join(RACINE, 'jeu_essai', 'v2', 'statistiques'), os.path.join(RACINE, 'jeu_essai', 'v2'), RACINE):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

SANS_KAMAL = pytest.mark.skipif(
    not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
    reason='structure de Kamal absente')
ATTENDU = os.path.join(RACINE, 'pipeline', 'tests', 'attendu_statistiques.json')
CALCULE_LE = '2026-11-17T12:00:00Z'


def lignes_agregat(cx):
    noms = [c[1] for c in cx.execute('PRAGMA table_info(c7_agregat)')]
    return [dict(zip(noms, r)) for r in cx.execute('SELECT * FROM c7_agregat')]
