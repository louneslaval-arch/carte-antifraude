#!/usr/bin/env python3
"""Vérifie la base contre les invariants déclarés dans `invariants.yaml`.

Chaque invariant porte un `nom` et soit `zero` (requête qui doit rendre zéro ligne), soit `comptage` (requête qui
rend un nombre) avec `attendu` et `tolerance`, ou `minimum`. Arrêt au premier écart. Sortie : le nom et un comptage,
jamais une valeur de ligne (le script peut tourner sur une base réelle).

`invariants.yaml` est écrit dans la forme JSON du YAML (YAML valide, lu sans dépendance ; choix provisoire de
l'étape B, à revoir si une forme plus libre devient utile).

Usage : verifier.py [--base CHEMIN] [--invariants FICHIER]   (par défaut, la base du jeu d'essai)
"""
import argparse
import json
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
INVARIANTS = os.path.join(RACINE, 'invariants.yaml')
BASE_ESSAI = os.path.join(RACINE, 'jeu_essai', 'sortie', 'base_essai.sqlite')


def charger(chemin):
    with open(chemin, encoding='utf-8') as f:
        donnees = json.load(f)
    liste = donnees.get('invariants', [])
    for inv in liste:
        if 'nom' not in inv or ('zero' in inv) == ('comptage' in inv):
            raise ValueError('invariant mal déclaré : il faut un nom et exactement une clé zero ou comptage')
        if 'comptage' in inv and 'attendu' not in inv and 'minimum' not in inv:
            raise ValueError(f'invariant {inv["nom"]} : comptage sans attendu ni minimum')
    return liste


def verifier(base, invariants=INVARIANTS):
    liste = charger(invariants)
    with sqlite3.connect(base) as cx:
        for inv in liste:
            if 'zero' in inv:
                n = cx.execute(f'SELECT count(*) FROM ({inv["zero"]})').fetchone()[0]
                ok = n == 0
            else:
                ligne = cx.execute(inv['comptage']).fetchone()
                n = ligne[0] if ligne else None
                if not isinstance(n, (int, float)):
                    print(f'ÉCART  {inv["nom"]} : aucun nombre')
                    return 1
                if 'attendu' in inv:
                    ok = abs(n - inv['attendu']) <= inv.get('tolerance', 0)
                else:
                    ok = n >= inv['minimum']
            print(f'{"ok    " if ok else "ÉCART "} {inv["nom"]} : {n}')
            if not ok:
                return 1
    print(f'invariants vérifiés : {len(liste)}')
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--base', default=os.environ.get('CARTE_BASE_ESSAI', BASE_ESSAI))
    p.add_argument('--invariants', default=INVARIANTS)
    a = p.parse_args(argv)
    if not os.path.exists(a.base):
        print('erreur : base introuvable (lancer construire.py)', file=sys.stderr)
        return 2
    try:
        return verifier(a.base, a.invariants)
    except (ValueError, sqlite3.Error) as e:
        print(f'erreur : {type(e).__name__}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
