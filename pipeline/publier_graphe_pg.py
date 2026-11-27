#!/usr/bin/env python3
"""Prépare un export AF PostgreSQL en répertoires public/ et prive/.

Ce script ne monte aucun répertoire dans FastAPI et ne remplace jamais une
publication existante. Il ne publie pas les identités dans le répertoire public.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


SOURCES = ('geometrie.json', 'identites.json', 'statistiques.json', 'manifeste.json')


def charger(path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def empreinte(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def valider(source):
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise ValueError('La source doit être un dossier')
    for name in SOURCES:
        f = source / name
        if not f.is_file() or f.is_symlink():
            raise ValueError(f'Fichier source absent ou symbolique : {name}')
    manifeste = charger(source / 'manifeste.json')
    if manifeste.get('type') != 'graphe_af_postgresql' or manifeste.get('donnees_reelles') is not True:
        raise ValueError('Manifeste incompatible')
    expected = manifeste.get('empreintes') or {}
    if set(expected) != {'geometrie.json', 'identites.json', 'statistiques.json'}:
        raise ValueError('Liste des empreintes incomplète')
    if any(empreinte(source / name) != digest for name, digest in expected.items()):
        raise ValueError('Empreinte invalide : export altéré')

    geo, identites, stats = (charger(source / name) for name in
                             ('geometrie.json', 'identites.json', 'statistiques.json'))
    if geo.get('type') != 'graphe_af_postgresql' or geo.get('format') != 1:
        raise ValueError('Format géométrique inattendu')
    noeuds, aretes = geo['noeuds'], geo['aretes']
    if len(noeuds) != stats['noeuds'] or len(aretes) != stats['aretes']:
        raise ValueError('Comptages incohérents')
    if len(identites['liens']) != stats['liens_detailles']:
        raise ValueError('Couche détaillée incomplète')
    if not all(isinstance(a['a'], int) and isinstance(a['b'], int)
               and 0 <= a['a'] < len(noeuds) and 0 <= a['b'] < len(noeuds)
               for a in aretes):
        raise ValueError('Arête hors limites')
    # Allowlist stricte : les champs libres (noms, pièces, CIN) ne passent pas.
    champs_noeuds = {'id', 't', 'bl', 'x', 'y', 'c', 'deg', 'v'}
    champs_aretes = {'a', 'b', 'type'}
    if any(set(n) - champs_noeuds for n in noeuds):
        raise ValueError('Champ identifiant ou inconnu dans la géométrie')
    villes = geo.get('villes') or {}
    if any(n.get('v') is not None and n['v'] not in villes for n in noeuds):
        raise ValueError('Ville absente du référentiel géographique')
    if not all(isinstance(p, list) and len(p) == 2 and all(isinstance(c, (int, float)) for c in p)
               for p in villes.values()):
        raise ValueError('Coordonnées géographiques invalides')
    if any(set(a) - champs_aretes for a in aretes):
        raise ValueError('Champ libre dans une arête')
    ids_geo = {n['id'] for n in noeuds}
    ids_prive = {n['id'] for n in identites['noeuds']}
    if len(ids_geo) != len(noeuds) or ids_geo != ids_prive:
        raise ValueError('Identifiants incohérents entre les couches')
    return source, manifeste


def publier(source, destination):
    source, manifeste = valider(source)
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination déjà présente : utiliser un nouveau dossier')
    if not destination.parent.is_dir():
        raise ValueError('Le parent de destination doit exister')
    if destination == source or source in destination.parents:
        raise ValueError('Destination à l’intérieur de la source interdite')

    old_umask = os.umask(0o077)
    tmp = None
    try:
        tmp = Path(tempfile.mkdtemp(prefix='.publication-pg-', dir=destination.parent))
        public, prive = tmp / 'public', tmp / 'prive'
        public.mkdir(mode=0o750)
        prive.mkdir(mode=0o700)
        for name in ('geometrie.json', 'statistiques.json'):
            shutil.copyfile(source / name, public / name)
            os.chmod(public / name, 0o640)
        shutil.copyfile(source / 'identites.json', prive / 'identites.json')
        os.chmod(prive / 'identites.json', 0o600)
        shutil.copyfile(source / 'manifeste.json', prive / 'manifeste.json')
        os.chmod(prive / 'manifeste.json', 0o600)

        # Vérification après copie et avant bascule du dossier complet.
        for name in ('geometrie.json', 'statistiques.json'):
            if empreinte(public / name) != manifeste['empreintes'][name]:
                raise ValueError('Copie publique altérée')
        if empreinte(prive / 'identites.json') != manifeste['empreintes']['identites.json']:
            raise ValueError('Copie privée altérée')
        os.rename(tmp, destination)
        return {'publication': str(destination), 'public': ['geometrie.json', 'statistiques.json'],
                'prive': ['identites.json', 'manifeste.json']}
    finally:
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp)
        os.umask(old_umask)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True)
    ap.add_argument('--sortie', required=True)
    a = ap.parse_args()
    print(json.dumps(publier(a.source, a.sortie), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
