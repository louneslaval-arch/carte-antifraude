"""Tests métier du moteur de chemins C5 (sans connexion à la base).

Usage: python -m pytest -q test_c5_relations_completes.py
Les arêtes sont des scénarios fictifs : la présence de ces relations en base
doit être vérifiée avec des tests d'intégration supplémentaires.
"""

import pytest

from pipeline.couches.c5_graphe_postgresql import chercher, cout, niveau, poids_participation


P = dict(
    c5_seuil_majeure=0.2,
    c5_seuil_mineure=0.1,
    c5_seuil_affichage=0.02,
    c5_longueur_alerte=3,
    c5_longueur_recherche=5,
    c5_poids_associe=0.5,
    c5_poids_inconnu=0.3,
)


class GrapheFictif:
    def __init__(self, relations, inscrits, tailles=None):
        self.p = P
        self.inscrits = set(inscrits)
        self._relations = {}
        self._tailles = tailles or {}
        for a, b, code, poids, identifiant in relations:
            for src, dst in ((a, b), (b, a)):
                self._relations.setdefault(src, []).append((
                    dst, 1, poids,
                    dict(type='identifiant' if identifiant else 'role', code=code, de=src, vers=dst),
                    None, False, identifiant,
                ))

    def liens(self, noeud):
        return self._relations.get(noeud, ())

    def n(self, noeud):
        return self._tailles.get(noeud, 1)


def _relation(a, b, code, poids, identifiant=None):
    return a, b, code, poids, identifiant


def test_inscrit_lui_meme_critique():
    chemin = chercher(GrapheFictif([], {'pp_inscrit'}), ['pp_inscrit'])
    assert chemin[0]['niveau'] == 'critique'
    assert chemin[0]['longueur'] == 0


def test_meme_rib_vers_inscrit():
    g = GrapheFictif([_relation('pp_a', 'pp_inscrit', 'RIB', 0.9, 'rib_fictif')], {'pp_inscrit'})
    c = chercher(g, ['pp_a'])[0]
    assert c['niveau'] == 'majeure' and c['longueur'] == 1
    assert c['etapes'][0]['code'] == 'RIB'


def test_employeur_et_gerant_inscrit():
    g = GrapheFictif([
        _relation('pp_a', 'pm_employeur', 'employe', 0.6),
        _relation('pm_employeur', 'pp_inscrit', 'gerant', 0.7),
    ], {'pp_inscrit'})
    c = chercher(g, ['pp_a'])[0]
    assert c['longueur'] == 2 and c['niveau'] == 'majeure'


def test_reseau_de_trois_liens_plafonne_mineure():
    g = GrapheFictif([
        _relation('pp_a', 'pm_1', 'gerant', 0.7),
        _relation('pm_1', 'pp_b', 'associe', 0.7),
        _relation('pp_b', 'pm_inscrit', 'gerant', 0.7),
    ], {'pm_inscrit'})
    assert chercher(g, ['pp_a'])[0]['niveau'] == 'mineure'


def test_reseau_de_quatre_liens_sans_alerte():
    g = GrapheFictif([
        _relation('pp_a', 'pm_1', 'gerant', 0.9),
        _relation('pm_1', 'pp_b', 'associe', 0.9),
        _relation('pp_b', 'pm_2', 'gerant', 0.9),
        _relation('pm_2', 'pp_inscrit', 'associe', 0.9),
    ], {'pp_inscrit'})
    assert chercher(g, ['pp_a'])[0]['niveau'] == 'hors_alerte'


def test_siege_partage_dilue_par_taille():
    g = GrapheFictif([
        _relation('pm_a', 'pm_inscrit', 'SIEGE', 0.4, 'siege_fictif'),
    ], {'pm_inscrit'}, {'siege_fictif': 40})
    c = chercher(g, ['pm_a'])
    assert c and c[0]['force'] == pytest.approx(0.4 * cout(40), abs=1e-6)


def test_associe_avec_part_dynamique():
    assert poids_participation(P, 'associe', '75') == pytest.approx(0.6)


def test_score_ne_fait_pas_fraude_confirmee():
    assert niveau(P, 1, 0.9) == 'majeure'
    assert niveau(P, 4, 0.9) == 'hors_alerte'
