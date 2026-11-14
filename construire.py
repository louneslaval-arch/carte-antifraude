#!/usr/bin/env python3
"""Construit la base couche par couche, en une commande, sans état caché.

Usage :
    construire.py --jeu-essai | --base CHEMIN  [--socle BASE_DU_KIT] [--depuis cN] [--jusqua cN] [--dossier REF]

--jeu-essai  base fictive (`jeu_essai/sortie/base_essai.sqlite`, ou $CARTE_BASE_ESSAI)
--base       base désignée (les données réelles ne se construisent que hors du dépôt, par Lounès)
--socle      base du kit (liste noire, registre) recopiée dans la couche 2 après la construction
--depuis / --jusqua  ne reconstruit que les couches demandées
--dossier    un seul dossier, comme le flux (traiter(ref) de chaque couche)

Sortie : comptages et identifiants techniques seulement.
"""
import argparse
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
from pipeline import migrer  # noqa: E402
from pipeline.couches import COUCHES  # noqa: E402

BASE_ESSAI = os.path.join(RACINE, 'jeu_essai', 'sortie', 'base_essai.sqlite')


def _nom(couche):
    return getattr(couche, 'nom', None) or couche.__name__.rsplit('.', 1)[-1].split('_', 1)[0]


def _selection(couches, depuis, jusqua):
    noms = [_nom(c) for c in couches]
    for borne in (depuis, jusqua):
        if borne is not None and borne not in noms:
            raise ValueError(f'couche inconnue : {borne}')
    debut = noms.index(depuis) if depuis else 0
    fin = noms.index(jusqua) + 1 if jusqua else len(noms)
    if (depuis or jusqua) and fin <= debut:
        raise ValueError(f'--depuis {depuis} vient après --jusqua {jusqua}')
    return couches[debut:fin]


def construire(base, couches=None, schema=migrer.SCHEMA, depuis=None, jusqua=None, dossier=None, socle=None):
    couches = COUCHES if couches is None else couches
    choisies = _selection(couches, depuis, jusqua)
    with sqlite3.connect(base) as cx:
        appliquees = migrer.appliquer(cx, schema)
        for couche in choisies:
            if dossier is None:
                couche.construire_tout(cx)
            else:
                couche.traiter(cx, dossier)
        if socle is not None:
            from pipeline.couches import c2_identites
            c2_identites.charger_socle(cx, socle)
    return appliquees, [_nom(c) for c in choisies]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cible = p.add_mutually_exclusive_group(required=True)
    cible.add_argument('--jeu-essai', action='store_true')
    cible.add_argument('--base')
    p.add_argument('--depuis')
    p.add_argument('--jusqua')
    p.add_argument('--dossier')
    p.add_argument('--socle')
    a = p.parse_args(argv)
    base = a.base
    if a.jeu_essai:
        base = os.environ.get('CARTE_BASE_ESSAI', BASE_ESSAI)
        os.makedirs(os.path.dirname(base), exist_ok=True)
    try:
        appliquees, faites = construire(base, depuis=a.depuis, jusqua=a.jusqua, dossier=a.dossier, socle=a.socle)
    except (ValueError, sqlite3.Error, migrer.ErreurMigration) as e:
        print(f'erreur : {type(e).__name__} (détail retiré : la sortie ne cite jamais une valeur)', file=sys.stderr)
        return 2
    print(f'migrations appliquées : {len(appliquees)} ; couches construites : {len(faites)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
