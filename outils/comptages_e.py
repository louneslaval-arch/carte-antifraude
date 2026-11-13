#!/usr/bin/env python3
"""Comptages de l'étape E : reçoit des dossiers de la v2 (un JSON `DossierDetail` par fichier) dans une base neuve,
construit c0 puis c1, et n'affiche que des nombres.

Le script peut tourner sur des données réelles (lancé par Lounès, hors du dépôt) : il n'affiche jamais une valeur
lue, un nom de fichier ni le détail d'une erreur ; seulement des comptages et des noms de classes d'erreur.

Usage : comptages_e.py --base BASE_NEUVE fichier.json [fichier.json …]
Codes de sortie : 0 tout est lu ; 1 un fichier au moins est illisible ou refusé ; 2 la base existe déjà.
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut, c1_faits  # noqa: E402

ROLES_AJOUTES = ('titulaire_compte', 'titulaire_quittance')      # absents de l'extracteur du 11/11

COMPTAGES = (
    ('dossiers lus', 'SELECT count(*) FROM "Dossier"'),
    ('pièces', 'SELECT count(*) FROM c1_piece'),
    ('valeurs', 'SELECT count(*) FROM c1_fait'),
    ('valeurs retenues', 'SELECT count(*) FROM c1_fait_retenu'),
    ('opérations lues', "SELECT count(*) FROM c1_releve_operation WHERE nature = 'lue'"),
    ('opérations reconstituées', "SELECT count(*) FROM c1_releve_operation WHERE nature = 'reconstituee_amont'"),
    ('mentions de personnes (rôles du 11/11)',
     'SELECT count(*) FROM c1_mention_personne WHERE role NOT IN (%s)' % ', '.join(f"'{r}'" for r in ROLES_AJOUTES)),
    ('mentions de personnes (toutes)', 'SELECT count(*) FROM c1_mention_personne'),
    ('mentions de sociétés', 'SELECT count(*) FROM c1_mention_societe'),
    ('identifiants bruts', 'SELECT count(*) FROM c1_identifiant_brut'),
    ('clés inconnues (distinctes)', 'SELECT count(*) FROM c1_cle_inconnue'),
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--base', required=True)
    p.add_argument('fichiers', nargs='+')
    a = p.parse_args(argv)
    if os.path.exists(a.base):
        print('refusé : la base existe déjà (donner un chemin neuf)')
        return 2
    cx = sqlite3.connect(a.base)
    migrer.appliquer(cx)
    passage = c0_brut.ouvrir_passage(cx, 'fichiers', 'lot')
    illisibles = refuses = nouvelles = 0
    for chemin in a.fichiers:
        try:
            with open(chemin, encoding='utf-8') as f:
                detail = json.load(f)
            nouvelles += bool(c0_brut.recevoir(cx, passage, detail))
        except c0_brut.MiroirRefuse:
            refuses += 1
        except Exception:                                 # noqa: BLE001  jamais de détail : le contenu peut être réel
            cx.rollback()
            illisibles += 1
    c0_brut.fermer_passage(cx, passage, len(a.fichiers), nouvelles)
    c1_faits.construire_tout(cx)
    print(f'fichiers illisibles : {illisibles}')
    print(f'dossiers refusés par le miroir : {refuses}')
    for libelle, sql in COMPTAGES:
        print(f'{libelle} : {cx.execute(sql).fetchone()[0]}')
    cx.close()
    return 1 if illisibles or refuses else 0


if __name__ == '__main__':
    sys.exit(main())
