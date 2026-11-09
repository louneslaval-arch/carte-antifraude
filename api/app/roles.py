"""Rôles et droits : la seule table qui dit qui peut faire quoi."""

from enum import Enum


class Role(str, Enum):
    ANALYSTE = 'ANALYSTE'
    AGENCE = 'AGENCE'
    DIRECTION = 'DIRECTION'
    ADMIN = 'ADMIN'


TOUS = frozenset(Role)

DROITS = {
    'carte.geometrie': TOUS,
    'carte.noms': frozenset({Role.ANALYSTE, Role.AGENCE}),
    'carte.noeud': frozenset({Role.ANALYSTE}),
    'carte.recherche': frozenset({Role.ANALYSTE}),
    'chaines': frozenset({Role.ANALYSTE}),
    'stats': TOUS,
    'admin': frozenset({Role.ADMIN}),
}
