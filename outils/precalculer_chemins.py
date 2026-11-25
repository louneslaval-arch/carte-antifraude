#!/usr/bin/env python3
"""Précalcule les chemins vers la liste noire de chaque dossier de la base client, une fois pour toutes.

Sur un grand registre, la recherche des chemins (jusqu'à 4 liens) prend longtemps ; l'API la faisait à chaque
démarrage. Ce script la fait une fois, en montrant sa progression, et l'écrit à côté de la base
(`<base>.chemins.json`, avec l'empreinte de la base) : l'API le lit au démarrage tant que la base n'a pas changé.
Le fichier ne contient que des identifiants internes de fiche, des codes de lien et des nombres, aucun nom.

Usage, par Lounès seulement pour une base réelle : python outils/precalculer_chemins.py --base BASE_CLIENT.sqlite
"""
import argparse
import json
import os
import sqlite3
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'api')]

from app.base_client import BaseClient, calculer_chemins, fichier_chemins  # noqa: E402


def precalculer(base, afficher=False):
    epoque = BaseClient._empreinte(base)
    cx = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    try:
        refs = [r for (r,) in cx.execute('SELECT ref FROM c3_dossier ORDER BY ref')]
        debut = time.time()

        def progression(k, n):
            if afficher and (k % 100 == 0 or k == n):
                ecoule = time.time() - debut
                reste = ecoule / k * (n - k)
                print(f'  {k} / {n} dossiers · {ecoule / 60:.0f} min écoulées · environ {reste / 60:.0f} min restantes',
                      flush=True)
        chemins = calculer_chemins(cx, refs, progression)
    finally:
        cx.close()
    partiel = fichier_chemins(base) + '.partiel'
    with open(partiel, 'w', encoding='utf-8') as f:
        json.dump(dict(epoque=epoque, chemins=chemins), f, ensure_ascii=False)
    os.replace(partiel, fichier_chemins(base))
    return dict(dossiers=len(chemins), avec_chemin=sum(1 for c in chemins.values() if c))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', required=True)
    a = ap.parse_args(argv)
    if not os.path.exists(a.base):
        print('arrêt : base introuvable', file=sys.stderr)
        return 2
    print('calcul des chemins vers la liste noire…', flush=True)
    try:
        bilan = precalculer(a.base, afficher=True)
    except Exception as e:                            # noqa: BLE001  jamais de contenu dans la sortie
        print(f'arrêt : calcul interrompu ({type(e).__name__})', file=sys.stderr)
        return 1
    print(f'terminé : {bilan["dossiers"]} dossiers, dont {bilan["avec_chemin"]} reliés à la liste noire')
    return 0


if __name__ == '__main__':
    sys.exit(main())
