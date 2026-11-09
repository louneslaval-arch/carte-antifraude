"""Réponses d'erreur qui ne recopient jamais une valeur reçue ni le message d'une exception.

FastAPI renvoie d'ordinaire, dans une erreur 422, la valeur fautive : un CIN tapé dans une recherche trop longue
reviendrait dans la réponse. Ici, seuls les noms des champs en cause sont donnés.
"""

import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

journal_technique = logging.getLogger('carte')


async def validation(_request, exc: RequestValidationError):
    champs = sorted({'.'.join(str(x) for x in e.get('loc', ()) if not isinstance(x, int)) for e in exc.errors()})
    return JSONResponse({'detail': 'Requête invalide', 'champs': champs}, status_code=422)


async def attraper_tout(request, call_next):
    """Dernier filet : aucune trace contenant le message de l'exception ne part vers les journaux du serveur."""
    try:
        return await call_next(request)
    except Exception as e:                                          # noqa: BLE001
        journal_technique.error('Erreur interne %s sur %s %s', type(e).__name__, request.method, request.url.path)
        return JSONResponse({'detail': 'Erreur interne'}, status_code=500)
