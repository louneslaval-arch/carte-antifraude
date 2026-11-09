"""Point d'entrée du serveur : « uvicorn app.serveur:app ». Réglages lus dans l'environnement."""

from .config import lire_reglages
from .main import creer_app

app = creer_app(lire_reglages())
