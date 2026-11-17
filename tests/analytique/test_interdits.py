"""Critères interdits (annexe C) : le sexe et la nationalité ne découpent jamais un verdict ni un contrôle ; ils ne
se croisent avec rien. Parcours de toute la table construite sur le jeu d'essai, pas d'un échantillon."""
import inspect

from .commun import SANS_KAMAL, lignes_agregat
from pipeline.analytique import agregats, indicateurs


def test_les_dimensions_autorisees_sont_une_constante_unique():
    assert not set(indicateurs.DIMENSIONS_TAUX) & set(indicateurs.DIMENSIONS_REPARTITION_SEULE)
    assert {'sexe', 'nationalite'} == set(indicateurs.DIMENSIONS_REPARTITION_SEULE)
    for a, b in indicateurs.CROISEMENTS:
        assert a in indicateurs.DIMENSIONS_TAUX and b in indicateurs.DIMENSIONS_TAUX
    # le calcul relit la constante, il n'en garde pas une copie
    source = inspect.getsource(agregats)
    assert 'DIMENSIONS_TAUX' in source and "'sexe'" not in source and "'nationalite'" not in source


@SANS_KAMAL
def test_aucun_verdict_ni_controle_decoupe_par_sexe_ou_nationalite(base_stats):
    interdits = set(indicateurs.DIMENSIONS_REPARTITION_SEULE)
    for r in lignes_agregat(base_stats):
        if r['indicateur'] in indicateurs.INDICATEURS_VERDICT_CONTROLE:
            assert r['dimension1'] not in interdits and r['dimension2'] not in interdits, r


@SANS_KAMAL
def test_sexe_et_nationalite_en_repartition_simple_seulement(base_stats):
    vus = False
    for r in lignes_agregat(base_stats):
        if r['dimension1'] in ('sexe', 'nationalite') or r['dimension2'] in ('sexe', 'nationalite'):
            vus = True
            assert r['indicateur'] in ('nb_dossiers', 'part_dossiers', 'taux_remplissage') and not r['dimension2'], r
    assert vus


@SANS_KAMAL
def test_aucun_indicateur_de_verdict_ou_de_controle_hors_des_criteres_autorises(base_stats):
    permis = set(indicateurs.DIMENSIONS_TAUX) | {'', 'verdict', 'famille', 'controle', 'manquant'}
    for r in lignes_agregat(base_stats):
        if r['indicateur'] in indicateurs.INDICATEURS_VERDICT_CONTROLE:
            assert r['dimension1'] in permis and r['dimension2'] in permis, r
