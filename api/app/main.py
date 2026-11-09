"""Application : assemblage des routes, de la publication courante et de la base du journal."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .base import ouvrir
from .config import Reglages
from .graphe import charger
from .routes import auth, carte

VERSION = '0.3.0'


class Etat:
    """Ce que les routes partagent. La publication est remplacée d'un bloc par /admin/recharger."""

    def __init__(self, reglages: Reglages):
        self.reglages = reglages
        self.base = ouvrir(reglages.base_url)
        self.publication = charger(reglages.publication, reglages.donnees_reelles) if reglages.publication else None


def creer_app(reglages: Reglages) -> FastAPI:
    app = FastAPI(title='Carte antifraude', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.etat = Etat(reglages)

    @app.get('/api/sante')
    def sante():
        p = app.state.etat.publication
        if p is None:
            return JSONResponse({'etat': 'sans_publication', 'version': VERSION}, status_code=503)
        return {'etat': 'ok', 'version': VERSION, 'date_publication': p.manifeste['date_publication'],
                'noeuds': p.noeuds, 'fictif': p.manifeste['fictif']}

    @app.middleware('http')
    async def pas_de_cache(request, call_next):
        reponse = await call_next(request)
        reponse.headers.setdefault('Cache-Control', 'no-store')     # identités : jamais en cache
        return reponse

    app.include_router(auth.routeur)
    app.include_router(carte.routeur)
    return app
