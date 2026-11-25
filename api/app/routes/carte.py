from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    return _geometrie(request, response, p)


class DemandeNoms(BaseModel):
    model_config = ConfigDict(extra='forbid')
    indices: List[int] = Field(min_length=1, max_length=MAX_NOMS)


def _noms(demande, request, session, p, epoque=''):
    if any(not 0 <= i < p.noeuds for i in demande.indices):
        raise HTTPException(422, 'Indice hors de la carte')
    etat = _etat(request)
    quotas.etiquettes(etat, session, demande.indices, epoque)
    resultat = identites.noms(p, set(demande.indices))
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'noms', resultat, ip=session.ip, epoque=epoque)
    return {str(i): v for i, v in resultat.items()}


def _noeud(indice, request, session, p, globale=False, epoque=''):
    etat = _etat(request)
    quotas.fiches(etat, session)
    f = (identites.fiche_globale if globale else identites.fiche)(p, indice)      # lues à l'appel (tests)
    if f is None:
        raise HTTPException(404, 'Nœud inconnu')
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'fiche', [indice], ip=session.ip, epoque=epoque)
    return f


@routeur.post('/noms')
def noms(demande: DemandeNoms, request: Request, session: Session = Depends(exige('carte.noms')),
         p=Depends(publication)):
    return _noms(demande, request, session, p, epoque=p.epoque)


@routeur.get('/noeud/{indice}')
def noeud(indice: int, request: Request, session: Session = Depends(exige('carte.noeud')), p=Depends(publication)):
    return _noeud(indice, request, session, p, epoque=p.epoque)


class DemandeRecherche(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str = Field(min_length=2, max_length=100)

    @field_validator('q')
    @classmethod
    def assez_long_pour_un_nom(cls, q):
        _champs, valeur, exacte = forme_recherche(q)
        if not exacte and len(valeur) < 3:
            raise ValueError('3 caractères au moins pour chercher un nom')
        return q


def _recherche(demande, request, session, p, epoque=''):
    etat = _etat(request)
    resultats = identites.recherche(p, demande.q)
    quotas.etiquettes(etat, session, [r['indice'] for r in resultats], epoque)
    # la requête n'est jamais journalisée : seulement les indices trouvés et leur nombre
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche',
                   [r['indice'] for r in resultats], ip=session.ip, epoque=epoque)
    return {'resultats': resultats}


@routeur.post('/recherche')
def recherche(demande: DemandeRecherche, request: Request, session: Session = Depends(exige('carte.recherche')),
              p=Depends(publication)):
    return _recherche(demande, request, session, p, epoque=p.epoque)


# ---- carte globale (registre × liste noire) : même découpage en deux couches, sa propre publication ----------------
def publication_globale(request: Request):
    p = request.app.state.etat.publication_globale
    if p is None:
        raise HTTPException(503, 'Aucune carte globale chargée')
    return p


def _geometrie(request, response, p):
    entetes = {'ETag': p.etag, 'Cache-Control': 'private, no-cache', 'Vary': 'Cookie, Authorization'}
    entetes.update({k: v for k, v in response.headers.items() if k.lower() in ('x-jeton', 'set-cookie')})
    if request.headers.get('if-none-match') == p.etag:
        return Response(status_code=304, headers=entetes)
    return Response(p.geometrie_gz, media_type='application/json',
                    headers=dict(entetes, **{'Content-Encoding': 'gzip'}))


@routeur.get('/globale')
def globale(request: Request, response: Response, session: Session = Depends(exige('carte.globale')),
            p=Depends(publication_globale)):
    return _geometrie(request, response, p)


@routeur.post('/globale/noms')
def globale_noms(demande: DemandeNoms, request: Request, session: Session = Depends(exige('carte.globale')),
                 p=Depends(publication_globale)):
    return _noms(demande, request, session, p, epoque=p.epoque)


@routeur.get('/globale/noeud/{indice}')
def globale_noeud(indice: int, request: Request, session: Session = Depends(exige('carte.globale')),
                  p=Depends(publication_globale)):
    return _noeud(indice, request, session, p, globale=True, epoque=p.epoque)


@routeur.post('/globale/recherche')
def globale_recherche(demande: DemandeRecherche, request: Request, session: Session = Depends(exige('carte.globale')),
                      p=Depends(publication_globale)):
    return _recherche(demande, request, session, p, epoque=p.epoque)
