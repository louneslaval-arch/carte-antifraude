import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


source = Path(__file__).resolve().parents[1] / 'api' / 'app' / 'publication_pg.py'
spec = importlib.util.spec_from_file_location('publication_pg_test', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_publication(tmp_path):
    public, prive = tmp_path / 'public', tmp_path / 'prive'
    public.mkdir(); prive.mkdir()
    files = {'geometrie.json': public, 'statistiques.json': public,
             'identites.json': prive}
    data = {'geometrie.json': {'noeuds': [{'id': 'opaque1'}], 'aretes': []},
            'statistiques.json': {'noeuds': 1, 'aretes': 0},
            'identites.json': {'noeuds': [{'id': 'opaque1', 'nom': 'Sensible'}], 'liens': []}}
    signatures = {}
    for name, directory in files.items():
        b = json.dumps(data[name]).encode()
        (directory / name).write_bytes(b)
        signatures[name] = hashlib.sha256(b).hexdigest()
    (prive / 'manifeste.json').write_text(json.dumps({'type': 'graphe_af_postgresql',
                                                    'empreintes': signatures}))
    return tmp_path


def test_noms_pour_id_opaque(tmp_path):
    pub = module.PublicationPG(fixture_publication(tmp_path))
    assert pub.noms(['opaque1']) == {'opaque1': 'Sensible'}


def test_id_inconnu_refuse(tmp_path):
    pub = module.PublicationPG(fixture_publication(tmp_path))
    with pytest.raises(KeyError):
        pub.noms(['inconnu'])


def test_empreinte_modifiee_refusee(tmp_path):
    p = fixture_publication(tmp_path)
    (p / 'prive' / 'identites.json').write_text('{}')
    with pytest.raises(ValueError):
        module.PublicationPG(p)
