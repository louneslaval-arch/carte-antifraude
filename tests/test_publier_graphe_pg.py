"""Tests sans connexion AWS : pytest -q tests/test_publier_graphe_pg.py"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


source = Path(__file__).resolve().parents[1] / 'pipeline' / 'publier_graphe_pg.py'
spec = importlib.util.spec_from_file_location('publier_graphe_pg', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def preparer(tmp_path):
    base = tmp_path / 'export'
    base.mkdir()
    nodes = [{'id': 'abc', 't': 'personne', 'bl': 0, 'x': 0, 'y': 0, 'c': 0, 'deg': 0}]
    values = {'geometrie.json': {'type': 'graphe_af_postgresql', 'format': 1,
                                 'noeuds': nodes, 'aretes': []},
              'identites.json': {'noeuds': [{'id': 'abc', 'nom': 'Nom sensible'}], 'liens': []},
              'statistiques.json': {'noeuds': 1, 'aretes': 0, 'liens_detailles': 0}}
    checksums = {}
    for name, data in values.items():
        contents = json.dumps(data).encode()
        (base / name).write_bytes(contents)
        checksums[name] = hashlib.sha256(contents).hexdigest()
    (base / 'manifeste.json').write_text(json.dumps({'type': 'graphe_af_postgresql',
         'donnees_reelles': True, 'empreintes': checksums}))
    return base


def test_public_prive_separes(tmp_path):
    source = preparer(tmp_path)
    sortie = tmp_path / 'publication'
    module.publier(source, sortie)
    assert (sortie / 'public' / 'geometrie.json').is_file()
    assert not (sortie / 'public' / 'identites.json').exists()
    assert (sortie / 'prive' / 'identites.json').is_file()
    assert not (sortie / 'public' / 'manifeste.json').exists()


def test_pas_de_remplacement(tmp_path):
    source = preparer(tmp_path)
    sortie = tmp_path / 'publication'
    module.publier(source, sortie)
    with pytest.raises(ValueError):
        module.publier(source, sortie)


def test_geometrie_avec_nom_refusee(tmp_path):
    source = preparer(tmp_path)
    p = source / 'geometrie.json'
    data = json.loads(p.read_text())
    data['noeuds'][0]['nom'] = 'sensible'
    p.write_text(json.dumps(data))
    man = json.loads((source / 'manifeste.json').read_text())
    man['empreintes']['geometrie.json'] = module.empreinte(p)
    (source / 'manifeste.json').write_text(json.dumps(man))
    with pytest.raises(ValueError):
        module.publier(source, tmp_path / 'publication')


def test_empreinte_invalide_refusee(tmp_path):
    source = preparer(tmp_path)
    (source / 'geometrie.json').write_text('{}')
    with pytest.raises(ValueError):
        module.publier(source, tmp_path / 'publication')
