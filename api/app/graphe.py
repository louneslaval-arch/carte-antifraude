"""Publication courante : couche 1 en mémoire, couche 2 par chemin, le tout vérifié contre le manifeste."""

import gzip
import hashlib
import json
import os
from dataclasses import dataclass

FORMAT = 1
FICHIERS = ('geometrie.json', 'identites.sqlite', 'statistiques.json')


class PublicationRefusee(Exception):
    pass


@dataclass(frozen=True)
class Publication:
    dossier: str
    manifeste: dict
    geometrie: dict
    geometrie_gz: bytes          # servie telle quelle, compressée une fois au chargement
    statistiques: dict

    @property
    def etag(self):
        return '"' + self.manifeste['empreinte'] + '"'

    @property
    def noeuds(self):
        n = self.geometrie['noeuds']                       # colonnes (carte des chaînes) ou liste (carte globale)
        return len(n) if isinstance(n, list) else len(n['t'])

    @property
    def epoque(self):
        return self.manifeste['empreinte'][:16]

    @property
    def identites(self):
        return os.path.join(self.dossier, 'identites.sqlite')


def _empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def _manifeste(dossier):
    try:
        with open(os.path.join(dossier, 'manifeste.json'), encoding='utf-8') as f:
            m = json.load(f)
    except (OSError, ValueError):
        raise PublicationRefusee(f'manifeste absent ou illisible dans {dossier}') from None
    if m.get('format') != FORMAT:
        raise PublicationRefusee(f'format de publication {m.get("format")!r} inconnu (attendu {FORMAT})')
    return m


def charger(dossier, donnees_reelles):
    """Lit et vérifie une publication. Refuse des données réelles sans l'autorisation du serveur."""
    dossier = os.path.realpath(dossier)          # « courant » est un lien : on fige la cible
    m = _manifeste(dossier)
    if not m.get('fictif') and not donnees_reelles:
        raise PublicationRefusee('publication de données réelles : CARTE_DONNEES_REELLES=1 requis sur ce serveur')
    for nom in FICHIERS:
        chemin = os.path.join(dossier, nom)
        if not os.path.exists(chemin) or _empreinte(chemin) != m['fichiers'].get(nom):
            raise PublicationRefusee(f'{nom} absent ou différent du manifeste')
    with open(os.path.join(dossier, 'geometrie.json'), 'rb') as f:
        brut = f.read()
    with open(os.path.join(dossier, 'statistiques.json'), encoding='utf-8') as f:
        statistiques = json.load(f)
    return Publication(dossier=dossier, manifeste=m, geometrie=json.loads(brut),
                       geometrie_gz=gzip.compress(brut, mtime=0), statistiques=statistiques)
