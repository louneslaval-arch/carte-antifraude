"""Application : assemblage des routes, de la publication courante et de la base du journal."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import journal
from .base import ouvrir
from .config import Reglages
from .debit import Debit
from .erreurs import attraper_tout, validation
from .graphe import charger
from .routes import admin, auth, carte, chaines, flux, stats

VERSION = '0.3.0'


class Etat:
    """Ce que les routes partagent. La publication est remplacée d'un bloc par /admin/recharger."""

    def __init__(self, reglages: Reglages):
        self.reglages = reglages
        self.base = ouvrir(reglages.base_url)
        journal.purger(self.base, reglages.journal_jours)        # conservation : aussi à chaque rechargement
        self.debit = Debit(reglages)
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

    app.add_exception_handler(RequestValidationError, validation)

    @app.middleware('http')
    async def pas_de_cache(request, call_next):
        reponse = await call_next(request)
        reponse.headers.setdefault('Cache-Control', 'no-store')     # identités : jamais en cache
        return reponse

    @app.middleware('http')
    async def limiter(request, call_next):
        if not app.state.etat.debit.autorise(request):
            return JSONResponse({'detail': 'Trop de requêtes, réessayez dans une minute'}, status_code=429)
        return await call_next(request)

    app.middleware('http')(attraper_tout)                           # le plus extérieur : ajouté en dernier
    if reglages.origine:
        app.add_middleware(CORSMiddleware, allow_origins=[reglages.origine], allow_credentials=True,
                           allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])

    app.include_router(auth.routeur)
    for module in (carte, chaines, stats, admin, flux):
        app.include_router(module.routeur)
    return app
