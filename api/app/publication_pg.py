"""Lecture strictement contrôlée de la publication du graphe AF PostgreSQL."""

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path


def _json(path):
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicationPG:
    def __init__(self, dossier):
        p = Path(dossier).resolve(strict=True)
        if not p.is_dir():
            raise ValueError('Publication introuvable')
        manifest = _json(p / 'prive' / 'manifeste.json')
        if manifest.get('type') != 'graphe_af_postgresql':
            raise ValueError('Type de publication incompatible')
        attendu = manifest.get('empreintes') or {}
        chemins = {
            'geometrie.json': p / 'public' / 'geometrie.json',
            'statistiques.json': p / 'public' / 'statistiques.json',
            'identites.json': p / 'prive' / 'identites.json',
        }
        if set(attendu) != set(chemins):
            raise ValueError('Manifeste incomplet')
        if any(_sha(chemin) != attendu[nom] for nom, chemin in chemins.items()):
            raise ValueError('Empreinte de publication invalide')
        self.geo = _json(chemins['geometrie.json'])
        self.stats = _json(chemins['statistiques.json'])
        private = _json(chemins['identites.json'])
        nodes = self.geo['noeuds']
        if len(nodes) != len(private['noeuds']):
            raise ValueError('Nombre de nœuds incohérent')
        self.indice = {n['id']: i for i, n in enumerate(nodes)}
        self.identites = {n['id']: n for n in private['noeuds']}
        if len(self.indice) != len(nodes) or set(self.indice) != set(self.identites):
            raise ValueError('Identifiants incompatibles')
        self.epoque = attendu['geometrie.json'][:16]

    def noms(self, ids):
        if len(set(ids)) != len(ids):
            raise ValueError('Identifiants dupliqués')
        if any(i not in self.indice for i in ids):
            raise KeyError('Nœud inconnu')
        return {i: self.identites[i].get('nom') for i in ids}


@lru_cache(maxsize=4)
def _charger(dossier):
    return PublicationPG(dossier)


def depuis_environnement():
    dossier = os.environ.get('AF_GRAPH_PUBLICATION')
    if not dossier:
        raise ValueError('AF_GRAPH_PUBLICATION absente')
    return _charger(dossier)
