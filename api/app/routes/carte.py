from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import Session, exige

routeur = APIRouter(prefix='/api/carte')


def publication(request: Request):
    p = request.app.state.etat.publication
    if p is None:
        raise HTTPException(503, 'Aucune publication chargée')
    return p


@routeur.get('/geometrie')
def geometrie(request: Request, response: Response, session: Session = Depends(exige('carte.geometrie')),
              p=Depends(publication)):
    entetes = {'ETag': p.etag, 'Cache-Control': 'private, no-cache', 'Vary': 'Cookie, Authorization'}
    entetes.update({k: v for k, v in response.headers.items() if k.lower() in ('x-jeton', 'set-cookie')})
    if request.headers.get('if-none-match') == p.etag:
        return Response(status_code=304, headers=entetes)
    return Response(p.geometrie_gz, media_type='application/json',
                    headers=dict(entetes, **{'Content-Encoding': 'gzip'}))
