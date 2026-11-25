"""Tests unitaires C6 sans base : python -m pytest -q test_c6_regles.py"""

from unittest.mock import patch

from pipeline.couches import c6_regles_postgresql as c6


class ConnexionFictive:
    def execute(self, sql, params):
        assert 'c3_incoherence' in sql
        return [
            ('rib_autre_dossier', 'incoherence', 'p1', 'RIB', 'd2', 'p2', 'RIB'),
            ('dossiers_en_rafale', 'signal', 'p1', 'RIB', None, None, None),
        ]


def test_regles_documentaires_et_signal():
    with patch.object(c6.c5, 'chemins', return_value=[]), \
        patch.object(c6, '_af09_admissible', return_value=True):
            alertes = c6.calculer(ConnexionFictive(), 'd1')
    assert len(alertes) == 2
    assert {a[3] for a in alertes} == {'incoherence', 'signal'}
    assert all(a[4] is None for a in alertes)


def test_lien_critique_et_homonymie():
    chemins = [
        dict(cible='pp_x', longueur=0, niveau='critique', homonymie=False),
        dict(cible='pm_y', longueur=2, niveau='mineure', homonymie=True),
    ]
    with patch.object(c6.c5, 'chemins', return_value=chemins), \
        patch.object(c6, '_af09_admissible', return_value=True):
            alertes = c6.calculer(ConnexionFictive(), 'd1')
    assert len(alertes) == 4
    assert any(a[2] == 'inscrit_direct' and a[4] == 'critique' for a in alertes)
    assert any('homonymie à valider' in a[5] for a in alertes)


def test_stabilite_et_absence_de_valeur_en_clair():
    assert c6._cle('RIB', 'valeur_confidentielle') == c6._cle('RIB', 'valeur_confidentielle')
    assert 'valeur_confidentielle' not in c6._cle('RIB', 'valeur_confidentielle')
