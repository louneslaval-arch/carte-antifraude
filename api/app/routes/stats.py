from collections import defaultdict

from fastapi import APIRouter, Depends

from ..auth import Session, exige
from .carte import publication

routeur = APIRouter(prefix='/api/stats')
T_SOCIETE, T_PERSONNE = 0, 1


@routeur.get('/villes')
def villes(session: Session = Depends(exige('stats')), p=Depends(publication)):
    """Comptes par ville, tirés de la couche 1 : aucun nom, aucun indice."""
    n = p.geometrie['noeuds']
    comptes = defaultdict(lambda: dict(noeuds=0, societes=0, personnes=0, inscrits=0, liste_noire=0))
    for t, bl, v in zip(n['t'], n['bl'], n['ville']):
        if v < 0:
            continue
        c = comptes[v]
        c['noeuds'] += 1
        c['societes' if t == T_SOCIETE else 'personnes' if t == T_PERSONNE else 'inscrits'] += 1
        c['liste_noire'] += bl
    return [dict(ville=p.geometrie['villes'][v], **c) for v, c in sorted(comptes.items())]


@routeur.get('/regles')
def regles(session: Session = Depends(exige('stats')), p=Depends(publication)):
    return p.statistiques
