#!/usr/bin/env python3
"""Comptages de référence de l'étape A, lus dans `globale.json` (sortie de `carte_globale.py --json`).

Affiche seulement deux nombres : le nombre de réseaux, et la taille du plus grand réseau qui touche la liste noire.
Les deux autres chiffres de référence se lisent dans les bilans du kit (inscrits reliés : `construire_base.py` ;
chemins de retour : `chaines_dessin.py`, « dont N reliés à la liste noire »). Le script peut tourner sur des données
réelles : il n'affiche jamais une valeur lue, ni un message d'erreur détaillé.

Usage : comptages_a.py --globale globale.json
"""
import argparse
import json
import sys


def comptages(g):
    tailles = g['reseaux']
    touches = [tailles[i] for i in g.get('reseaux_bl', [])]
    return len(tailles), max(touches, default=0)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--globale', required=True)
    a = p.parse_args(argv)
    try:
        with open(a.globale, encoding='utf-8') as f:
            reseaux, plus_grand = comptages(json.load(f))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print(f'erreur : {type(e).__name__}', file=sys.stderr)
        return 2
    print(f'réseaux : {reseaux}')
    print(f'plus grand réseau touchant la liste noire : {plus_grand} nœuds')
    return 0


if __name__ == '__main__':
    sys.exit(main())
