#!/usr/bin/env python3
"""Statistiques des dossiers (couche 7) : (re)construit `c7_variable_dossier`, `c7_agregat` et `c7_indicateur` dans la
base indiquée (construite par `construire.py`), puis écrit la page autonome si `--html` est donné.

Usage :
    stats_dossiers.py --base CHEMIN.sqlite [--periode-debut AAAA-MM-JJ] [--periode-fin AAAA-MM-JJ] [--avec-archives]
                      [--html statistiques_dossiers.html] [--avec-noms-societes]

Les données réelles ne se traitent que hors du dépôt, par Lounès. Sortie console : comptages seulement.
"""
import argparse
import datetime
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
from pipeline import migrer  # noqa: E402
from pipeline.analytique import agregats, page_statistiques  # noqa: E402


def _date(v):
    datetime.date.fromisoformat(v)
    return v


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--base', required=True)
    p.add_argument('--periode-debut', type=_date)
    p.add_argument('--periode-fin', type=_date)
    p.add_argument('--avec-archives', action='store_true')
    p.add_argument('--html')
    p.add_argument('--avec-noms-societes', action='store_true',
                   help='banques, employeurs et concessionnaires de 5 dossiers et plus (à valider avec la conformité)')
    a = p.parse_args(argv)
    if not os.path.exists(a.base):
        print('base introuvable', file=sys.stderr)
        return 2
    try:
        with sqlite3.connect(a.base) as cx:
            migrer.appliquer(cx)
            comptes = agregats.construire(cx, a.periode_debut, a.periode_fin, a.avec_archives, a.avec_noms_societes)
            print(f"dossiers : {comptes['dossiers']} ; cases : {comptes['cases']} ; masquées : {comptes['masquees']}")
            if a.html:
                taille = page_statistiques.generer(cx, a.html)
                print(f'page : {taille // 1024} Ko')
    except Exception as e:                    # noqa: BLE001  données réelles : jamais de trace ni de message (valeur lue)
        print(f'échec ({type(e).__name__})', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
