#!/usr/bin/env python3
"""Comptages de l'étape F : charge le socle du kit (liste noire, registre) dans une base neuve, construit c2 et les
couches du dessus (c3, c5), et n'affiche que des nombres.

Le script peut tourner sur des données réelles (lancé par Lounès, hors du dépôt) : il n'affiche jamais une valeur
lue ni le détail d'une erreur. Aucun chiffre de 1 à 4 ne s'affiche (« < 5 ») ; un comptage par règle qui porte sur
moins de 5 fiches distinctes est réuni aux autres. Sans la variable d'environnement du garde-fou des données réelles
(posée par Lounès dans sa commande, jamais ailleurs), un kit dont un CIN ne commence pas par « ZZ » est refusé.

Usage : comptages_f.py --base-kit BASE_DU_KIT --base BASE_NEUVE
Codes de sortie : 0 fait ; 1 un invariant en écart ; 2 arguments ou base refusés ; 3 échec (classe de l'erreur).
"""
import argparse
import contextlib
import io
import os
import re
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
# (titre, requête : libellé, nombre de lignes, nombre de fiches distinctes concernées)
GROUPES = (
    ('mentions par règle de rattachement',
     "SELECT coalesce(regle, 'aucune'), count(*), count(DISTINCT coalesce(fiche, id)) FROM c2_mention GROUP BY 1"),
    ('rapprochements entre fiches par règle',
     'SELECT regle, sum(nb_mentions), count(DISTINCT fiche_a) FROM c2_correspondance GROUP BY 1'),
)
LIBELLE = re.compile(r'[A-Za-z0-9_]{1,24}')
AUTRES = 'autres (sous le seuil)'


class _Analyseur(argparse.ArgumentParser):
    def error(self, message):                             # jamais l'argument fautif
        print('arguments refusés (usage : comptages_f.py --base-kit BASE_DU_KIT --base BASE_NEUVE)')
        raise SystemExit(2)


def _affiche(n):
    """Aucun chiffre sur moins de 5 : un comptage de 1 à 4 s'affiche « < 5 »."""
    return n if n == 0 or n >= SEUIL else '< 5'


def _groupes(rangs):
    """Groupes affichables : ceux qui portent sur 5 fiches distinctes au moins et dont le libellé est un nom de
    règle ; les autres sont réunis (avec le plus petit groupe affiché tant que la réunion reste sous le seuil), pour
    qu'aucun ne se retrouve par soustraction."""
    grands = sorted(((nom, n) for nom, n, fiches in rangs if fiches >= SEUIL and LIBELLE.fullmatch(nom or '')),
                    key=lambda g: (g[1], g[0]))
    reste = sum(n for nom, n, fiches in rangs) - sum(n for _, n in grands)
    while 0 < reste < SEUIL and grands:
        reste += grands.pop(0)[1]
    return sorted(grands) + ([(AUTRES, _affiche(reste))] if reste else [])


def _fictif(kit):
    """Vrai si le kit ne porte que des CIN fictifs (« ZZ ») : sans le garde-fou, rien d'autre n'est lu."""
    return kit.execute("SELECT (SELECT count(*) FROM bl_entite WHERE cin IS NOT NULL AND cin NOT LIKE 'ZZ%') + "
                       "(SELECT count(*) FROM rc_personne WHERE cin_norm IS NOT NULL AND cin_norm NOT LIKE 'ZZ%')"
                       ).fetchone()[0] == 0


def _compter(a, reel):
    kit = sqlite3.connect(f'file:{a.base_kit}?mode=ro', uri=True)
    try:
        if not reel and not _fictif(kit):
            print('refusé : kit non fictif, et garde-fou des données réelles absent de la commande')
            return 2
        print(f"inscrits du kit : {_affiche(kit.execute('SELECT count(*) FROM bl_entite').fetchone()[0])}")
    finally:
        kit.close()
    cx = sqlite3.connect(a.base)
    migrer.appliquer(cx)
    for couche in COUCHES:                                # base sans dossier : les couches se construisent vides
        couche.construire_tout(cx)
    c2_identites.charger_socle(cx, a.base_kit)
    for couche in COUCHES[COUCHES.index(c2_identites) + 1:]:        # le socle change c2 : le dessus se refait
        couche.construire_tout(cx)
    for libelle, sql in TOTAUX:
        print(f'{libelle} : {_affiche(cx.execute(sql).fetchone()[0])}')
    for titre, sql in GROUPES:
        print(f'{titre} :')
        for nom, n in _groupes(cx.execute(sql).fetchall()):
            print(f'  {nom} : {n}')
    cx.commit()
    cx.close()
    with contextlib.redirect_stdout(io.StringIO()) as sortie:
        ecart = verifier.verifier(a.base)
    print(f'invariants en écart : {1 if ecart else 0}')
    for ligne in sortie.getvalue().splitlines():          # le nom seulement : ni le comptage ni une valeur
        nom = re.fullmatch(r'ÉCART\s+([a-z0-9_]+) : .*', ligne)
        if nom:
            print(f'premier invariant en écart : {nom.group(1)}')
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
    reel = os.environ.get(GARDE_FOU) == '1'
    if reel and os.path.commonpath([os.path.realpath(a.base), depot]) == depot:
        print('refusé : une base de données réelles ne se crée jamais dans le dépôt')
        return 2
    try:
        return _compter(a, reel)
    except Exception as e:                                # noqa: BLE001  ni message ni trace : seulement la classe
        print(f'échec : {type(e).__name__}')
        return 3


if __name__ == '__main__':
    sys.exit(main())
