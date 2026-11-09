from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from .. import identites, journal, quotas
from ..auth import Session, exige
from ..identites import forme_recherche

routeur = APIRouter(prefix='/api/carte')
MAX_NOMS = 400


def publication(request: Request):
    p = request.app.state.etat.publication
    if p is None:
        raise HTTPException(503, 'Aucune publication chargée')
    return p


def _etat(request):
    return request.app.state.etat


@routeur.get('/geometrie')
def geometrie(request: Request, response: Response, session: Session = Depends(exige('carte.geometrie')),
              p=Depends(publication)):
    entetes = {'ETag': p.etag, 'Cache-Control': 'private, no-cache', 'Vary': 'Cookie, Authorization'}
    entetes.update({k: v for k, v in response.headers.items() if k.lower() in ('x-jeton', 'set-cookie')})
    if request.headers.get('if-none-match') == p.etag:
        return Response(status_code=304, headers=entetes)
    return Response(p.geometrie_gz, media_type='application/json',
                    headers=dict(entetes, **{'Content-Encoding': 'gzip'}))


class DemandeNoms(BaseModel):
    indices: List[int] = Field(min_length=1, max_length=MAX_NOMS)


@routeur.post('/noms')
def noms(demande: DemandeNoms, request: Request, session: Session = Depends(exige('carte.noms')),
         p=Depends(publication)):
    if any(not 0 <= i < p.noeuds for i in demande.indices):
        raise HTTPException(422, 'Indice hors de la carte')
    etat = _etat(request)
    quotas.etiquettes(etat, session, demande.indices)
    resultat = identites.noms(p, set(demande.indices))
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'noms', resultat, ip=session.ip)
    return {str(i): v for i, v in resultat.items()}


@routeur.get('/noeud/{indice}')
def noeud(indice: int, request: Request, session: Session = Depends(exige('carte.noeud')), p=Depends(publication)):
    if not 0 <= indice < p.noeuds:
        raise HTTPException(404, 'Nœud inconnu')
    etat = _etat(request)
    quotas.fiches(etat, session)
    f = identites.fiche(p, indice)
    if f is None:
        raise HTTPException(404, 'Nœud inconnu')
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'fiche', [indice], ip=session.ip)
    return f


class DemandeRecherche(BaseModel):
    q: str = Field(min_length=2, max_length=100)

    @field_validator('q')
    @classmethod
    def assez_long_pour_un_nom(cls, q):
        _champs, valeur, exacte = forme_recherche(q)
        if not exacte and len(valeur) < 3:
            raise ValueError('3 caractères au moins pour chercher un nom')
        return q


@routeur.post('/recherche')
def recherche(demande: DemandeRecherche, request: Request, session: Session = Depends(exige('carte.recherche')),
              p=Depends(publication)):
    etat = _etat(request)
    resultats = identites.recherche(p, demande.q)
    quotas.etiquettes(etat, session, [r['indice'] for r in resultats])
    # la requête n'est jamais journalisée : seulement les indices trouvés et leur nombre
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche',
                   [r['indice'] for r in resultats], ip=session.ip)
    return {'resultats': resultats}
