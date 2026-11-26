"""Routes protégées de la carte globale PostgreSQL."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import Session, exige
from ..carte_globale_pg import depuis_environnement

routeur = APIRouter(prefix='/api/carte-globale-pg', tags=['Carte globale PostgreSQL'])


@routeur.get('/resume')
def resume(session: Session = Depends(exige('carte.globale'))):
    try:
        return depuis_environnement().resume()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@routeur.get('/graphe')
def graphe(limite: int = Query(150, ge=1, le=500),
           debut: int = Query(0, ge=0, le=1_000_000),
           session: Session = Depends(exige('carte.globale'))):
    try:
        return depuis_environnement().graphe(limite, debut)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
