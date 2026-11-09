from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import journal
from ..auth import COOKIE, Session, emettre, poser_cookie, revoquer, session_courante, verifier_mot_de_passe

routeur = APIRouter(prefix='/api/auth')


class Connexion(BaseModel):
    identifiant: str = Field(max_length=64)
    mot_de_passe: str = Field(max_length=256)


@routeur.post('/connexion')
def connexion(demande: Connexion, request: Request, response: Response):
    etat = request.app.state.etat
    verdict = verifier_mot_de_passe(etat, demande.identifiant, demande.mot_de_passe)
    # un identifiant inconnu n'est pas recopié dans le journal : ce pourrait être un CIN saisi par erreur
    journal.ecrire(etat.base, demande.identifiant if verdict.compte_existe else 'inconnu', verdict.role,
                   verdict.action, ip=request.client.host if request.client else '')
    if not verdict.accepte:
        raise HTTPException(401, 'Identifiant ou mot de passe incorrect, ou compte verrouillé')
    jeton = emettre(etat.reglages, demande.identifiant, verdict.role)
    poser_cookie(response, etat.reglages, jeton)
    return {'jeton': jeton, 'role': verdict.role, 'duree': etat.reglages.duree_jeton_s}


@routeur.post('/deconnexion', status_code=204)
def deconnexion(request: Request, response: Response, session: Session = Depends(session_courante)):
    etat = request.app.state.etat
    revoquer(etat, session)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'deconnexion', ip=session.ip)
    response.delete_cookie(COOKIE, path='/api', secure=etat.reglages.cookie_securise, httponly=True,
                           samesite='strict')
    if 'x-jeton' in response.headers:
        del response.headers['x-jeton']             # pas de jeton neuf pour une session qu'on ferme
