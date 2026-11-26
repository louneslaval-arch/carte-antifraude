import importlib.util
from pathlib import Path


source = Path(__file__).resolve().parents[1] / 'pipeline' / 'exporter_graphe_postgresql.py'
spec = importlib.util.spec_from_file_location('exporter_graphe_postgresql', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_relations_inter_pages_conservees():
    identites = [dict(identite_id=i, type_identite='PP', nom=f'P{i}') for i in range(1, 5)]
    relations = [dict(relation_id=1, pp_identite_id=1, pm_identite_id=4, role='associe')]
    links = [dict(lien_id=1, identite_id=4, entite_id=99, regle='AF01', niveau='certain', nom_affiche='LN', type_entite='PP')]
    geo, noms = module.construire(identites, relations, links)
    assert len(geo['noeuds']) == 5
    assert len(geo['aretes']) == 2
    assert sum(x['bl'] for x in geo['noeuds']) == 1
    assert not any('nom' in n for n in geo['noeuds'])
    assert any(n['nom'] == 'LN' for n in noms['noeuds'])
    assert geo['reseaux_bl']
    assert len(noms['liens']) == 2


def test_duplicate_blacklist_node():
    ids = [dict(identite_id=i, type_identite='PM', nom=f'S{i}') for i in (1,2)]
    links = [dict(lien_id=i, identite_id=i, entite_id=99, regle='AF01', niveau='certain', nom_affiche='LN', type_entite='PP') for i in (1,2)]
    geo, _ = module.construire(ids, [], links)
    assert len(geo['noeuds']) == 3
    assert len(geo['aretes']) == 2


def test_lien_sans_identite_avec_dossier():
    links = [dict(lien_id=1, identite_id=None, dossier_ref='D-42',
                  entite_id=99, regle='AF01', niveau='certain',
                  nom_affiche='LN', type_entite='PP')]
    geo, private = module.construire([], [], links)
    assert len(geo['noeuds']) == 2
    assert len(geo['aretes']) == 1
    assert private['liens_liste_noire_sans_rattachement'] == 0
    assert any(n['type'] == 'dossier' for n in private['noeuds'])


def test_lien_sans_identite_ni_dossier():
    links = [dict(lien_id=1, identite_id=None, dossier_ref=None,
                  entite_id=99, regle='AF01', niveau='indice',
                  nom_affiche='LN', type_entite='PP')]
    geo, private = module.construire([], [], links)
    assert len(geo['noeuds']) == 1
    assert len(geo['aretes']) == 0
    assert private['liens_liste_noire_sans_rattachement'] == 1
    assert len(private['liens']) == 1


def test_doublons_gardes_en_details():
    identities = [dict(identite_id=i, type_identite='PP', nom=f'P{i}') for i in (1,2)]
    rels = [dict(relation_id=j, pp_identite_id=1, pm_identite_id=2, role='associe') for j in (1,2)]
    geo, private = module.construire(identities, rels, [])
    assert len(geo['aretes']) == 1
    assert len(private['liens']) == 2
