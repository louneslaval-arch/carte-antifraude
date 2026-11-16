"""Comptes locaux (V1) : création, verrouillage, désactivation. Utilisable en ligne de commande par l'administrateur.

  python -m app.comptes creer IDENTIFIANT ROLE        (mot de passe demandé, jamais en argument)
  python -m app.comptes deverrouiller IDENTIFIANT
  python -m app.comptes desactiver IDENTIFIANT
  python -m app.comptes lister
"""

import argparse
import getpass
import sys

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .base import Utilisateur
from .roles import Role

HACHEUR = PasswordHasher()
LONGUEUR_MIN = 12


def creer(fabrique, identifiant, role, mot_de_passe):
    if not identifiant or len(identifiant) > 64:
        raise ValueError('identifiant vide ou trop long')
    if role not in Role.__members__:
        raise ValueError(f'rôle inconnu ; rôles possibles : {", ".join(Role.__members__)}')
    if len(mot_de_passe) < LONGUEUR_MIN:
        raise ValueError(f'mot de passe trop court ({LONGUEUR_MIN} caractères au moins)')
    try:
        with fabrique.begin() as s:
            s.add(Utilisateur(identifiant=identifiant, role=role, hachage=HACHEUR.hash(mot_de_passe)))
    except IntegrityError:
        raise ValueError(f'le compte {identifiant} existe déjà') from None


def _modifier(fabrique, identifiant, **champs):
    with fabrique.begin() as s:
        u = s.scalar(select(Utilisateur).where(Utilisateur.identifiant == identifiant))
        if u is None:
            raise ValueError(f'compte {identifiant} introuvable')
        for k, v in champs.items():
            setattr(u, k, v)


def deverrouiller(fabrique, identifiant):
    _modifier(fabrique, identifiant, verrouille=False, echecs=0)


def desactiver(fabrique, identifiant):
    _modifier(fabrique, identifiant, actif=False)


def hachage_de(fabrique, identifiant):
    with fabrique() as s:
        return s.scalar(select(Utilisateur.hachage).where(Utilisateur.identifiant == identifiant))


def lister(fabrique):
    with fabrique() as s:
        return [(u.identifiant, u.role, u.actif, u.verrouille) for u in s.scalars(
            select(Utilisateur).order_by(Utilisateur.identifiant))]


def main(argv=None):
    from .base import ouvrir
    from .config import lire_reglages
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = ap.add_subparsers(dest='commande', required=True)
    c = sous.add_parser('creer')
    c.add_argument('identifiant')
    c.add_argument('role', choices=list(Role.__members__))
    for nom in ('deverrouiller', 'desactiver'):
        sous.add_parser(nom).add_argument('identifiant')
    sous.add_parser('lister')
    a = ap.parse_args(argv)
    fabrique = ouvrir(lire_reglages().base_url)
    try:
        if a.commande == 'creer':
            creer(fabrique, a.identifiant, a.role, getpass.getpass('Mot de passe : '))
        elif a.commande == 'lister':
            for ligne in lister(fabrique):
                print(*ligne, sep='\t')
        else:
            globals()[a.commande](fabrique, a.identifiant)
    except ValueError as e:
        print(f'Refusé : {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
