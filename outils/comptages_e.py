#!/usr/bin/env python3
"""Comptages de l'étape E : reçoit des dossiers de la v2 (un JSON `DossierDetail` par fichier) dans une base neuve,
construit c0 puis c1, et n'affiche que des nombres.

Le script peut tourner sur des données réelles (lancé par Lounès, hors du dépôt) : il n'affiche jamais une valeur
lue, un nom de fichier ni le détail d'une erreur ; seulement des comptages et des noms de classes d'erreur.

Usage : comptages_e.py --base BASE_NEUVE fichier.json [fichier.json …]
Sans la variable d'environnement du garde-fou des données réelles (posée par Lounès dans sa commande, jamais
ailleurs), un dossier dont la référence ne commence pas par « ZZ » est refusé et compté.
Codes de sortie : 0 tout est lu ; 1 un fichier au moins est illisible ou refusé ; 2 arguments ou base refusés ;
3 échec (seule la classe de l'erreur est affichée).
"""
import argparse
import contextlib
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import verifier  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut, c1_faits  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GARDE_FOU = 'CARTE_DONNEES_' + 'REELLES'          # sans lui, seuls les dossiers fictifs (référence en « ZZ ») sont lus
ROLES_AJOUTES = ('titulaire_compte', 'titulaire_quittance')      # absents de l'extracteur du 11/11

COMPTAGES = (
    ('dossiers lus', 'SELECT count(*) FROM "Dossier"'),
    ('pièces', 'SELECT count(*) FROM c1_piece'),
    ('valeurs', 'SELECT count(*) FROM c1_fait'),
    ('valeurs retenues', 'SELECT count(*) FROM c1_fait_retenu'),
    ('opérations lues', "SELECT count(*) FROM c1_releve_operation WHERE nature = 'lue'"),
    ('opérations reconstituées', "SELECT count(*) FROM c1_releve_operation WHERE nature = 'reconstituee_amont'"),
    ('opérations lues sans date lisible',
     "SELECT count(*) FROM c1_releve_operation WHERE nature = 'lue' AND date_operation IS NULL"),
    ('mentions de personnes (rôles du 11/11)',
     'SELECT count(*) FROM c1_mention_personne WHERE role NOT IN (%s)' % ', '.join(f"'{r}'" for r in ROLES_AJOUTES)),
    ('mentions de personnes (toutes)', 'SELECT count(*) FROM c1_mention_personne'),
    ('mentions de sociétés', 'SELECT count(*) FROM c1_mention_societe'),
    ('identifiants bruts', 'SELECT count(*) FROM c1_identifiant_brut'),
    ('clés inconnues (distinctes)', 'SELECT count(*) FROM c1_cle_inconnue'),
    ("listes d'objets non rangées", 'SELECT coalesce(sum(nb_listes_ignorees), 0) FROM c1_piece'),
)


class _Analyseur(argparse.ArgumentParser):
    def error(self, message):                             # jamais l'argument fautif : il peut porter une référence
        print('arguments refusés (usage : comptages_e.py --base BASE_NEUVE fichier.json …)')
        raise SystemExit(2)


def _dans_le_depot(chemin):
    return os.path.commonpath([os.path.realpath(chemin), os.path.realpath(RACINE)]) == os.path.realpath(RACINE)


def _compter(a, reel):
    cx = sqlite3.connect(a.base)
    migrer.appliquer(cx)
    passage = c0_brut.ouvrir_passage(cx, 'fichiers', 'lot')
    illisibles = refuses = non_fictifs = nouvelles = 0
    for chemin in a.fichiers:
        try:
            with open(chemin, encoding='utf-8') as f:
                detail = json.load(f)
            ref = detail.get('ref') if isinstance(detail, dict) else None
            if not reel and not (isinstance(ref, str) and ref.startswith('ZZ')):
                non_fictifs += 1
                continue
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
    print(f'dossiers non fictifs refusés : {non_fictifs}')
    for libelle, sql in COMPTAGES:
        print(f'{libelle} : {cx.execute(sql).fetchone()[0]}')
    cx.commit()
    cx.close()
    with contextlib.redirect_stdout(io.StringIO()):       # le détail des invariants reste hors de la sortie
        ecart = verifier.verifier(a.base)
    print(f'invariants en écart : {1 if ecart else 0}')
    return 1 if illisibles or refuses or non_fictifs or ecart else 0


def main(argv=None):
    p = _Analyseur(description=__doc__.splitlines()[0])
    p.add_argument('--base', required=True)
    p.add_argument('fichiers', nargs='+')
    a = p.parse_args(argv)
    reel = os.environ.get(GARDE_FOU) == '1'
    if os.path.exists(a.base):
        print('refusé : la base existe déjà (donner un chemin neuf)')
        return 2
    if reel and _dans_le_depot(a.base):
        print('refusé : une base de données réelles ne se crée jamais dans le dépôt')
        return 2
    try:
        return _compter(a, reel)
    except Exception as e:                                # noqa: BLE001  ni message ni trace : seulement la classe
        print(f'échec : {type(e).__name__}')
        return 3


if __name__ == '__main__':
    sys.exit(main())
