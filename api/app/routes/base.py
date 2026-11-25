"""Base client : résumé agrégé (tous les rôles), recherche, fiche, dossier et réseau (cellule fraude).

Aucune donnée personnelle dans une URL : la recherche passe dans le corps d'une requête POST, les fiches et les
dossiers se désignent par un indice opaque. Le journal garde les indices servis, jamais la requête de recherche.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import identites, journal, quotas
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
    resultat = b.rechercher(demande.texte, demande.type, demande.niveau, demande.produit, demande.avec_incoherence,
                            demande.page, demande.taille, demande.tri)
    indices = [c['indice'] for c in resultat['items']]
    quotas.etiquettes(etat, session, indices, b.epoque)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche', indices, ip=session.ip,
                   epoque=b.epoque)
    return resultat


@routeur.post('/dossiers')
def dossiers(demande: Recherche, request: Request, session: Session = Depends(exige('base.clients')),
             b=Depends(base_client)):
    """Liste des dossiers (une ligne par dossier, son demandeur nommé) : même droit et même journal que la liste des
    clients ; le journal garde les indices des demandeurs nommés, jamais la recherche."""
    etat = request.app.state.etat
    tri = demande.tri if 'tri' in demande.model_fields_set else 'recent'
    resultat = b.rechercher_dossiers(demande.texte, demande.type, demande.niveau, demande.produit,
                                     demande.avec_incoherence, demande.page, demande.taille, tri)
    indices = sorted({x['client'] for x in resultat['items'] if x['client']})
    quotas.etiquettes(etat, session, indices, b.epoque)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recherche', indices, ip=session.ip,
                   epoque=b.epoque)
    return resultat


def _servir(request, session, action, objet, indice):
    """Une fiche ou un dossier : la consultation compte au quota de fiches ; chaque tiers nommé dans la réponse
    compte au quota d'étiquettes et entre dans le journal (action « noms »), avec l'époque de la base."""
    if objet is None:
        raise HTTPException(404, 'Introuvable')
    etat = request.app.state.etat
    b = etat.base_client
    tiers = b.fiches_nommees(objet) - {indice}
    quotas.fiches(etat, session)
    quotas.etiquettes(etat, session, tiers, b.epoque)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, action, [indice], ip=session.ip,
                   epoque=b.epoque)
    if tiers:
        journal.ecrire(etat.base, session.utilisateur, session.role.value, 'noms', tiers, ip=session.ip,
                       epoque=b.epoque)
    return objet


@routeur.get('/clients/{indice}')
def fiche(indice: int, request: Request, session: Session = Depends(exige('base.fiche')), b=Depends(base_client)):
    return _servir(request, session, 'fiche', b.fiche(indice), indice)


@routeur.get('/dossiers/{indice}')
def dossier(indice: int, request: Request, session: Session = Depends(exige('base.fiche')), b=Depends(base_client)):
    return _servir(request, session, 'fiche', b.dossier(indice), indice)


CARTE_ACTIVE = True                   # vue réseau rallumée le 16/11 (Lounès), niveaux de criticité masqués


@routeur.get('/reseau/{indice}')
def reseau(indice: int, request: Request, session: Session = Depends(exige('base.reseau')), b=Depends(base_client)):
    if not CARTE_ACTIVE:
        raise HTTPException(404, 'Carte désactivée')
    return _servir(request, session, 'reseau', b.reseau(indice), indice)


@routeur.get('/carte/{indice}')
def carte(indice: int, request: Request, session: Session = Depends(exige('carte.globale')), b=Depends(base_client)):
    """Position d'une fiche sur la carte globale (indice de la carte), retrouvée par son CIN ou par son RC : la page
    de la fiche ouvre la carte centrée sur le client, sinon la vue réseau. Aucune identité dans la réponse."""
    etat = request.app.state.etat
    globale = etat.publication_globale
    if globale is None:
        raise HTTPException(503, 'Aucune carte globale chargée')
    quotas.fiches(etat, session)                     # dire si un client figure sur la carte vaut une consultation
    cle = b.cle_carte(indice)
    n = identites.indice_par_cle(globale, cle) if cle else None
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'carte', [indice], ip=session.ip,
                   epoque=b.epoque)
    if n is None:
        raise HTTPException(404, 'Absente de la carte')
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'carte', [n], ip=session.ip,
                   epoque=globale.epoque)
    return {'indice': n}

