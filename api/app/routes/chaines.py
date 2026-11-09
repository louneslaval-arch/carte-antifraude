import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import identites, journal, quotas
from ..auth import Session, exige
from .carte import publication

routeur = APIRouter(prefix='/api/chaines')


@routeur.get('/inscrits')
def inscrits(request: Request, session: Session = Depends(exige('chaines')), p=Depends(publication)):
    """Inscrits de départ des cartes par inscrit : nom, sans CIN ; hors quota (menu de la page)."""
    noms = identites.noms_inscrits(p)
    liste = [dict(indice=x['i'], nom=noms.get(x['i']), type=x['type'], compte=x['compte'], alerte=x['alerte'],
                  certain=x['certain']) for x in p.geometrie['inscrits']]
    journal.ecrire(request.app.state.etat.base, session.utilisateur, session.role.value, 'inscrits',
                   [x['indice'] for x in liste], ip=session.ip)
    return liste


@routeur.get('/{indice}')
def chaine(indice: int, request: Request, session: Session = Depends(exige('chaines')), p=Depends(publication)):
    etat = request.app.state.etat
    quotas.fiches(etat, session)
    donnees = identites.chaine(p, indice)
    if donnees is None:
        raise HTTPException(404, 'Pas de carte pour ce nœud')
    servis = [int(k) for k in json.loads(donnees)['noeuds']]
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'chaine', servis, ip=session.ip)
    return Response(donnees, media_type='application/json')
