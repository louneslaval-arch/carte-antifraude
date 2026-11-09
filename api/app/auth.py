"""Authentification V1 : comptes locaux, jeton signé de 8 h renouvelé sur activité, révocation par session.

Le jeton voyage dans un cookie httpOnly Secure SameSite=Strict, ou dans l'en-tête Authorization. Le rôle est relu
en base à chaque requête : changer le rôle ou désactiver un compte prend effet immédiatement.
"""

import secrets
import time
from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select

from .base import Revocation, Utilisateur, maintenant
from .comptes import HACHEUR
from .roles import DROITS, Role

COOKIE = 'carte_jeton'
ALGORITHME = 'HS256'
_HACHAGE_LEURRE = HACHEUR.hash('leurre-pour-temps-constant')


@dataclass(frozen=True)
class Session:
    utilisateur: str
    role: Role
    sid: str
    ip: str


def emettre(reglages, identifiant, role, sid=None, maintenant=None):
    t = int(maintenant if maintenant is not None else time.time())
    return jwt.encode({'sub': identifiant, 'role': role, 'sid': sid or secrets.token_urlsafe(24), 'iat': t,
                       'exp': t + reglages.duree_jeton_s}, reglages.cle_jwt, algorithm=ALGORITHME)


def poser_cookie(response, reglages, jeton):
    response.set_cookie(COOKIE, jeton, max_age=reglages.duree_jeton_s, httponly=True,
                        secure=reglages.cookie_securise, samesite='strict', path='/api')


def _jeton_de(request):
    entete = request.headers.get('authorization', '')
    if entete.lower().startswith('bearer '):
        return entete[7:].strip()
    return request.cookies.get(COOKIE)


def _decoder(reglages, jeton):
    try:
        return jwt.decode(jeton, reglages.cle_jwt, algorithms=[ALGORITHME],
                          options={'require': ['sub', 'sid', 'iat', 'exp']})
    except jwt.PyJWTError:
        return None


NON_AUTHENTIFIE = HTTPException(401, 'Authentification requise')


def session_courante(request: Request, response: Response) -> Session:
    etat = request.app.state.etat
    jeton = _jeton_de(request)
    contenu = _decoder(etat.reglages, jeton) if jeton else None
    if contenu is None:
        raise NON_AUTHENTIFIE
    with etat.base() as s:
        if s.get(Revocation, contenu['sid']) is not None:
            raise NON_AUTHENTIFIE
        u = s.scalar(select(Utilisateur).where(Utilisateur.identifiant == contenu['sub']))
    if u is None or not u.actif or u.verrouille:
        raise NON_AUTHENTIFIE
    if time.time() - contenu['iat'] > etat.reglages.renouveler_apres_s:
        neuf = emettre(etat.reglages, u.identifiant, u.role, sid=contenu['sid'])
        poser_cookie(response, etat.reglages, neuf)
        response.headers['X-Jeton'] = neuf
    return Session(utilisateur=u.identifiant, role=Role(u.role), sid=contenu['sid'],
                   ip=request.client.host if request.client else '')


def exige(droit):
    """Dépendance de route : session valide et rôle autorisé par la table DROITS."""
    autorises = DROITS[droit]

    def verifier(session: Session = Depends(session_courante)) -> Session:
        if session.role not in autorises:
            raise HTTPException(403, 'Rôle insuffisant')
        return session
    return verifier


@dataclass(frozen=True)
class Verdict:
    action: str                     # connexion, echec_connexion ou verrouillage
    role: str = ''                  # rôle du compte s'il existe
    compte_existe: bool = False

    @property
    def accepte(self):
        return self.action == 'connexion'


def decider(existe, bon, actif, verrouille, echecs, echecs_max):
    """(action, échecs, verrouillé) après une tentative ; un compte verrouillé ne compte plus ses échecs."""
    if not existe:
        return 'echec_connexion', 0, False
    if verrouille:
        return 'echec_connexion', echecs, True
    if bon:
        return ('connexion', 0, False) if actif else ('echec_connexion', echecs, False)
    if echecs + 1 >= echecs_max:
        return 'verrouillage', echecs + 1, True
    return 'echec_connexion', echecs + 1, False


def _mot_de_passe_bon(hachage, mot_de_passe):
    try:
        return HACHEUR.verify(hachage, mot_de_passe)
    except (VerificationError, InvalidHashError):
        return False


def verifier_mot_de_passe(etat, identifiant, mot_de_passe):
    """Vérifie le mot de passe ; compte les échecs et verrouille le compte au-delà du maximum."""
    with etat.base.begin() as s:
        u = s.scalar(select(Utilisateur).where(Utilisateur.identifiant == identifiant))
        bon = _mot_de_passe_bon(u.hachage if u else _HACHAGE_LEURRE, mot_de_passe) and u is not None
        if u is None:
            return Verdict(decider(False, bon, False, False, 0, etat.reglages.echecs_max)[0])
        action, u.echecs, u.verrouille = decider(True, bon, u.actif, u.verrouille, u.echecs,
                                                 etat.reglages.echecs_max)
        return Verdict(action, u.role, True)


def revoquer(etat, session):
    with etat.base.begin() as s:
        s.merge(Revocation(sid=session.sid, expire=maintenant() + timedelta(seconds=etat.reglages.duree_jeton_s)))
