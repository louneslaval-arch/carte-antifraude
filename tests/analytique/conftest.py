"""Montage commun des tests de la couche 7 : la base fictive du jeu d'essai des statistiques (600 dossiers, couches c0
à c5), puis les tables c7 construites une fois. Tout est fictif."""
import json

import pytest

from .commun import ATTENDU, CALCULE_LE


@pytest.fixture(scope='session')
def jeu_stats():
    import generer_v2_fictif as g
    return g


@pytest.fixture(scope='session')
def base_stats(jeu_stats, tmp_path_factory):
    """Base fictive avec c7 construite (toutes les tranches de filtre, sans noms de sociétés)."""
    from pipeline.analytique import agregats
    chemin = str(tmp_path_factory.mktemp('stats') / 'base.sqlite')
    cx = jeu_stats.construire_base(chemin, jeu_stats.dossiers())
    agregats.construire(cx, calcule_le=CALCULE_LE)
    yield cx
    cx.close()


@pytest.fixture(scope='session')
def plan_stats(jeu_stats):
    return {p['ref']: p for p in jeu_stats.plan()}


@pytest.fixture(scope='session')
def attendu():
    with open(ATTENDU, encoding='utf-8') as f:
        return json.load(f)
