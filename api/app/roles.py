"""Rôles et droits : la seule table qui dit qui peut faire quoi."""

from enum import Enum


class Role(str, Enum):
    ANALYSTE = 'ANALYSTE'
    AGENCE = 'AGENCE'
    DIRECTION = 'DIRECTION'
    ADMIN = 'ADMIN'


TOUS = frozenset(Role)

# Routes sans rôle, et pourquoi : toute autre route exige une session (un test le vérifie).
HORS_ROLES = {
    '/api/sante': 'état du service, sans donnée',
    '/api/auth/connexion': 'ouvre la session',
    '/api/auth/deconnexion': 'ferme la session',
    '/api/flux/v2': 'appelée par la v2 : protégée par la signature de la notification, pas par un rôle',
}

DROITS = {
    'carte.geometrie': TOUS,
    'carte.noms': frozenset({Role.ANALYSTE, Role.AGENCE}),
    'carte.noeud': frozenset({Role.ANALYSTE}),
    'carte.recherche': frozenset({Role.ANALYSTE}),
    'chaines': frozenset({Role.ANALYSTE}),
    'stats': TOUS,
    'admin': frozenset({Role.ADMIN}),
    # base client : chiffres agrégés pour tous ; noms, fiches, dossiers et réseau pour la cellule fraude seulement
    # (AGENCE : décision n°1 en attente, questions ouvertes)
    'base.resume': TOUS,
    'base.clients': frozenset({Role.ANALYSTE}),
    'base.fiche': frozenset({Role.ANALYSTE}),
    # carte réseau : liens et liste noire, jamais pour AGENCE (règles de l'API), même si elle reçoit un jour la fiche
    'base.reseau': frozenset({Role.ANALYSTE}),
}
