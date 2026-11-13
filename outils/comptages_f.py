#!/usr/bin/env python3
"""Comptages de l'étape F : charge le socle du kit (liste noire, registre) dans une base neuve, construit c2, et
n'affiche que des nombres.

Le script peut tourner sur des données réelles (lancé par Lounès, hors du dépôt) : il n'affiche jamais une valeur
lue ni le détail d'une erreur. Un comptage par règle qui porte sur moins de 5 lignes s'affiche « < 5 ».

Usage : comptages_f.py --base-kit BASE_DU_KIT --base BASE_NEUVE
Codes de sortie : 0 fait ; 1 un invariant en écart ; 2 arguments ou base refusés ; 3 échec (classe de l'erreur).
"""
import argparse
import contextlib
import io
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import verifier  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import COUCHES, c2_identites  # noqa: E402

GARDE_FOU = 'CARTE_DONNEES_' + 'REELLES'
SEUIL = 5
TOTAUX = (
    ('inscrits rangés', 'SELECT count(*) FROM ref_liste_noire'),
    ('mentions de la liste noire', "SELECT count(*) FROM c2_mention WHERE source = 'liste_noire'"),
    ('mentions du registre', "SELECT count(*) FROM c2_mention WHERE source = 'registre'"),
    ('fiches de personnes', 'SELECT count(*) FROM c2_personne'),
    ('fiches de personnes inscrites', 'SELECT count(*) FROM c2_personne WHERE inscrit = 1'),
    ('fiches de sociétés', 'SELECT count(*) FROM c2_societe'),
    ('fiches de sociétés inscrites', 'SELECT count(*) FROM c2_societe WHERE inscrit = 1'),
    ('fiches inscrites aussi vues au registre',
     "SELECT count(DISTINCT fiche) FROM c2_mention WHERE source = 'registre' AND fiche IN "
     "(SELECT fiche FROM c2_mention WHERE source = 'liste_noire')"),
    ('rapprochements du kit repris', "SELECT count(*) FROM c2_correspondance_mention WHERE source = 'kit'"),
    ('rapprochements entre fiches', 'SELECT coalesce(sum(nb_mentions), 0) FROM c2_correspondance'),
    ('CIN partagés par des noms incompatibles',
     "SELECT count(DISTINCT cle_valeur) FROM c2_correspondance_mention WHERE regle = 'CIN_PARTAGE'"),
)
GROUPES = (
    ('mentions par règle de rattachement', "SELECT coalesce(regle, 'aucune'), count(*) FROM c2_mention GROUP BY 1 ORDER BY 1"),
    ('rapprochements entre fiches par règle', 'SELECT regle, sum(nb_mentions) FROM c2_correspondance GROUP BY 1 ORDER BY 1'),
)


class _Analyseur(argparse.ArgumentParser):
    def error(self, message):                             # jamais l'argument fautif
        print('arguments refusés (usage : comptages_f.py --base-kit BASE_DU_KIT --base BASE_NEUVE)')
        raise SystemExit(2)


def _compter(a):
    kit = sqlite3.connect(f'file:{a.base_kit}?mode=ro', uri=True)
    print(f"inscrits du kit : {kit.execute('SELECT count(*) FROM bl_entite').fetchone()[0]}")
    kit.close()
    cx = sqlite3.connect(a.base)
    migrer.appliquer(cx)
    for couche in COUCHES:                                # base sans dossier : les couches se construisent vides
        couche.construire_tout(cx)
    c2_identites.charger_socle(cx, a.base_kit)
    for libelle, sql in TOTAUX:
        print(f'{libelle} : {cx.execute(sql).fetchone()[0]}')
    for titre, sql in GROUPES:
        print(f'{titre} :')
        for nom, n in cx.execute(sql).fetchall():
            print(f'  {nom} : {n if n >= SEUIL else "< 5"}')
    cx.commit()
    cx.close()
    with contextlib.redirect_stdout(io.StringIO()):
        ecart = verifier.verifier(a.base)
    print(f'invariants en écart : {1 if ecart else 0}')
    return 1 if ecart else 0


def main(argv=None):
    p = _Analyseur(description=__doc__.splitlines()[0])
    p.add_argument('--base-kit', required=True)
    p.add_argument('--base', required=True)
    a = p.parse_args(argv)
    if os.path.exists(a.base) or not os.path.exists(a.base_kit):
        print('refusé : la base neuve existe déjà, ou la base du kit est introuvable')
        return 2
    depot = os.path.realpath(RACINE)
    if os.environ.get(GARDE_FOU) == '1' and os.path.commonpath([os.path.realpath(a.base), depot]) == depot:
        print('refusé : une base de données réelles ne se crée jamais dans le dépôt')
        return 2
    try:
        return _compter(a)
    except Exception as e:                                # noqa: BLE001  ni message ni trace : seulement la classe
        print(f'échec : {type(e).__name__}')
        return 3


if __name__ == '__main__':
    sys.exit(main())
