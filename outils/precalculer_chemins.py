#!/usr/bin/env python3
"""Précalcule les chemins vers la liste noire de chaque dossier de la base client, une fois pour toutes.

Sur un grand registre, la recherche des chemins prend longtemps ; l'API la faisait à chaque démarrage. Ce script la
fait une fois, en montrant sa progression, et l'écrit à côté de la base (`<base>.chemins.json`, avec l'empreinte de
la base) : l'API le lit au démarrage tant que la base n'a pas changé. Le fichier contient les références des dossiers
(ses clés), des identifiants internes de fiche, des codes de lien et des nombres, aucun nom : il se range, comme la
base, hors du dépôt. Sortie console : comptages seulement.

- `--longueur 3` : chemins de 3 liens au plus. Un chemin de 4 liens ou plus ne donne jamais d'alerte (règle du score,
  décision n°20 : « calculé à la demande, affiché en gris ») ; les niveaux critique, majeure et mineure sont les mêmes
  qu'avec la longueur de recherche de la base. Sans l'option, la longueur de la base (`c5_longueur_recherche`).
- `--processus N` : le calcul est réparti entre N processus (un contexte par processus, voisinages lus une fois).

Usage, par Lounès seulement pour une base réelle :
  python outils/precalculer_chemins.py --base BASE_CLIENT.sqlite [--longueur 3] [--processus 4]
"""
import argparse
import json
import multiprocessing
import os
import sqlite3
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'api')]

from app.base_client import BaseClient, fichier_chemins  # noqa: E402
from pipeline.couches import c5_graphe  # noqa: E402

_TRAVAIL = {}


def _contexte(base, longueur):
    cx = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    k = c5_graphe.Contexte(cx)
    if longueur is not None:
        k.p = dict(k.p, c5_longueur_recherche=min(longueur, k.p['c5_longueur_recherche']))
    return cx, k


def _initialiser(base, longueur):
    _TRAVAIL['cx'], _TRAVAIL['k'] = _contexte(base, longueur)


def _calculer(refs):
    cx, k = _TRAVAIL['cx'], _TRAVAIL['k']
    return {ref: c5_graphe.chercher(k, c5_graphe._departs(cx, ref)) for ref in refs}


def chemins(base, longueur=None, processus=1, progression=None, paquet=10):
    """{ref: chemins} pour chaque dossier de la base, du plus grave au moins grave."""
    lecture = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    try:
        refs = [r for (r,) in lecture.execute('SELECT ref FROM c3_dossier ORDER BY ref')]
    finally:
        lecture.close()
    paquets = [refs[i:i + paquet] for i in range(0, len(refs), paquet)]
    sortie = {}
    if processus <= 1:
        _initialiser(base, longueur)
        try:
            for p in paquets:
                sortie.update(_calculer(p))
                if progression:
                    progression(len(sortie), len(refs))
        finally:
            _TRAVAIL.pop('cx').close()
        return sortie
    with multiprocessing.get_context('spawn').Pool(processus, _initialiser, (base, longueur)) as pool:
        for resultat in pool.imap_unordered(_calculer, paquets):
            sortie.update(resultat)
            if progression:
                progression(len(sortie), len(refs))
    return {ref: sortie[ref] for ref in refs}


def precalculer(base, longueur=None, processus=1, afficher=False):
    epoque = BaseClient._empreinte(base)
    debut, derniere = time.time(), [0]

    def progression(k, n):
        if afficher and (k - derniere[0] >= 100 or k == n):
            derniere[0] = k
            ecoule = time.time() - debut
            print(f'  {k} / {n} dossiers · {ecoule / 60:.0f} min écoulées · environ '
                  f'{ecoule / k * (n - k) / 60:.0f} min restantes', flush=True)
    resultat = chemins(base, longueur, processus, progression)
    partiel = fichier_chemins(base) + '.partiel'
    with open(partiel, 'w', encoding='utf-8') as f:
        json.dump(dict(epoque=epoque, longueur=longueur, chemins=resultat), f, ensure_ascii=False)
    os.replace(partiel, fichier_chemins(base))
    return dict(dossiers=len(resultat), avec_chemin=sum(1 for c in resultat.values() if c))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', required=True)
    ap.add_argument('--longueur', type=int, help='longueur maximale des chemins (3 : tout ce qui peut alerter)')
    ap.add_argument('--processus', type=int, default=1, help='nombre de processus de calcul')
    a = ap.parse_args(argv)
    if os.path.realpath(a.base).startswith(os.path.realpath(RACINE) + os.sep):
        print('arrêt : la base client se range hors du dépôt (par exemple dans ~/antifraude-donnees)', file=sys.stderr)
        return 2
    if os.environ.get('CARTE_DONNEES_REELLES') != '1':
        print('arrêt : données réelles : la commande doit commencer par CARTE_DONNEES_REELLES=1', file=sys.stderr)
        return 2
    if not os.path.exists(a.base):
        print('arrêt : base introuvable', file=sys.stderr)
        return 2
    print('calcul des chemins vers la liste noire…', flush=True)
    try:
        bilan = precalculer(a.base, a.longueur, max(1, a.processus), afficher=True)
    except Exception as e:                            # noqa: BLE001  jamais de contenu dans la sortie
        print(f'arrêt : calcul interrompu ({type(e).__name__})', file=sys.stderr)
        return 1
    print(f'terminé : {bilan["dossiers"]} dossiers, dont {bilan["avec_chemin"]} reliés à la liste noire')
    return 0


if __name__ == '__main__':
    sys.exit(main())
