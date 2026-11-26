"""API du graphe PostgreSQL, accès ANALYSTE uniquement."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import journal, quotas
from ..auth import Session, exige
from ..publication_pg import depuis_environnement

routeur = APIRouter(prefix='/api/graphe-pg')


def publication():
    try:
        return depuis_environnement()
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=503, detail='Publication PostgreSQL indisponible') from None


class DemandeNoms(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(min_length=1, max_length=50)


@routeur.get('/resume')
def resume(session: Session = Depends(exige('carte.globale')),
           p=Depends(publication)):
    return p.stats


@routeur.get('/geometrie')
def geometrie(session: Session = Depends(exige('carte.globale')),
              p=Depends(publication)):
    return p.geo


@routeur.post('/identites')
def identites(demande: DemandeNoms, request: Request,
              session: Session = Depends(exige('carte.globale')),
              p=Depends(publication)):
    try:
        result = p.noms(demande.ids)
    except (KeyError, ValueError):
        raise HTTPException(status_code=422, detail='Nœud inconnu ou demande invalide') from None
    indices = [p.indice[i] for i in demande.ids]
    etat = request.app.state.etat
    quotas.etiquettes(etat, session, indices, p.epoque)
    journal.ecrire(etat.base, session.utilisateur, session.role.value,
                   'noms', indices, ip=session.ip, epoque=p.epoque)
    return {'noms': result}
