"""Routes de la base client : chiffres, clients, dossiers et fiches."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import journal, quotas
from ..auth import Session, exige

routeur = APIRouter(prefix='/api/base')


def base_client(request: Request):
    b = request.app.state.etat.base_client
    if b is None:
        raise HTTPException(503, 'Aucune base client chargée')
    return b


class Recherche(BaseModel):
    model_config = ConfigDict(extra='forbid')
    texte: Optional[str] = Field(default=None, max_length=80)
    type: Optional[Literal['personne', 'societe']] = None
    niveau: Optional[Literal['critique', 'majeure', 'mineure', 'affiche', 'hors_alerte', 'aucun']] = None
    produit: Optional[str] = Field(default=None, max_length=40)
    avec_incoherence: Optional[bool] = None
    tri: Literal['gravite', 'recent', 'ancien', 'alpha', 'alpha_inverse', 'dossiers', 'revenu'] = 'gravite'
    page: int = Field(default=1, ge=1, le=10_000)
    taille: int = Field(default=50, ge=1, le=200)


@routeur.get('/resume')
def resume(session: Session = Depends(exige('base.resume')), b=Depends(base_client)):
    return b.resume()


@routeur.post('/clients')
def clients(demande: Recherche, request: Request, session: Session = Depends(exige('base.clients')),
            b=Depends(base_client)):
    etat = request.app.state.etat
    resultat = b.rechercher(demande.texte, demande.type, demande.niveau, demande.produit,
                            demande.avec_incoherence, demande.page, demande.taille, demande.tri)
    indices = [c['indice'] for c in resultat['items']]
    quotas.etiquettes(etat, session, indices)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche', indices,
                   ip=session.ip, epoque=b.epoque)
    return resultat


@routeur.get('/dossiers/liste')
def liste_dossiers(request: Request, page: int = Query(1, ge=1, le=10_000),
                   taille: int = Query(25, ge=1, le=100),
                   session: Session = Depends(exige('base.clients')), b=Depends(base_client)):
    """Liste paginée, y compris dossiers sans demandeur, pour la cellule fraude."""
    etat = request.app.state.etat
    resultat = b.tous_dossiers(page, taille)
    indices = [d['indice'] for d in resultat['items']]
    quotas.etiquettes(etat, session, indices)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche_dossiers', indices,
                   ip=session.ip, epoque=b.epoque)
    return resultat


def _servir(request, session, action, objet, indice):
    if objet is None:
        raise HTTPException(404, 'Introuvable')
    etat = request.app.state.etat
    b = etat.base_client
    tiers = b.fiches_nommees(objet) - {indice}
    quotas.fiches(etat, session)
    quotas.etiquettes(etat, session, tiers)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, action, [indice],
                   ip=session.ip, epoque=b.epoque)
    if tiers:
        journal.ecrire(etat.base, session.utilisateur, session.role.value, 'noms', tiers,
                       ip=session.ip, epoque=b.epoque)
    return objet


@routeur.get('/clients/{indice}')
def fiche(indice: int, request: Request, session: Session = Depends(exige('base.fiche')),
          b=Depends(base_client)):
    return _servir(request, session, 'fiche', b.fiche(indice), indice)


@routeur.get('/dossiers/{indice}')
def dossier(indice: int, request: Request, session: Session = Depends(exige('base.fiche')),
            b=Depends(base_client)):
    return _servir(request, session, 'fiche', b.dossier(indice), indice)


CARTE_ACTIVE = False  # carte des réseaux désactivée (choix du 16/11)


@routeur.get('/reseau/{indice}')
def reseau(indice: int, request: Request, session: Session = Depends(exige('base.fiche')),
           b=Depends(base_client)):
    if not CARTE_ACTIVE:
        raise HTTPException(404, 'Carte désactivée')
    return _servir(request, session, 'chaine', b.reseau(indice), indice)
