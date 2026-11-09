"""Limites de débit (bibliothèque « limits », celle sur laquelle repose slowapi).

- connexion : par adresse (CARTE_DEBIT_CONNEXION, 10 par minute) ;
- toutes les autres routes : par utilisateur authentifié, sinon par adresse (CARTE_DEBIT, 60 par minute).
Compteurs en mémoire du processus : avec plusieurs processus, chacun compte pour lui (voir déploiement).
"""

import jwt
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from .auth import ALGORITHME, _jeton_de

CHEMIN_CONNEXION = '/api/auth/connexion'


class Debit:
    def __init__(self, reglages):
        self._limiteur = MovingWindowRateLimiter(MemoryStorage())
        self._cle_jwt = reglages.cle_jwt
        self._general = parse(reglages.debit)
        self._connexion = parse(reglages.debit_connexion)

    def _utilisateur(self, request):
        jeton = _jeton_de(request)
        if not jeton:
            return None
        try:
            return jwt.decode(jeton, self._cle_jwt, algorithms=[ALGORITHME])['sub']
        except (jwt.PyJWTError, KeyError):
            return None

    def autorise(self, request):
        adresse = request.client.host if request.client else ''
        if request.url.path == CHEMIN_CONNEXION:
            return self._limiteur.hit(self._connexion, 'connexion', adresse)
        utilisateur = self._utilisateur(request)
        cle = ('u', utilisateur) if utilisateur else ('ip', adresse)
        return self._limiteur.hit(self._general, *cle)
