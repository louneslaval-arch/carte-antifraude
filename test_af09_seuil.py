from unittest.mock import Mock

import pytest

from pipeline.couches.c6_regles_postgresql import _af09_admissible


@pytest.mark.parametrize(
    "nombre,attendu",
    [
        (1, False),
        (2, True),
        (12, True),
        (13, False),
    ],
)
def test_seuil_af09(nombre, attendu):
    cx = Mock()

    resultat_ribs = Mock()
    resultat_ribs.fetchall.return_value = [("RIB_FICTIF",)]

    resultat_nombre = Mock()
    resultat_nombre.fetchone.return_value = (nombre,)

    cx.execute.side_effect = [
        resultat_ribs,
        resultat_nombre,
    ]

    assert _af09_admissible(cx, "DOSSIER_A", "DOSSIER_B") is attendu