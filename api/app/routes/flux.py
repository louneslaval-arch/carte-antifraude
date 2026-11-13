"""Temps réel : notification signée de la v2.

`POST /api/flux/v2` reçoit `{ref, updatedAt, analysisStatus, trigger}` à la fin d'une analyse, vérifie la signature
et l'horodatage (`flux/notification.py`), puis met le dossier en file pour le collecteur. La route n'est pas
protégée par un rôle mais par la signature ; elle est inactive (503) tant que `CARTE_FLUX_V2_SECRET` et
`CARTE_FLUX_BASE` ne sont pas posés. Aucune réponse ne recopie ce qui a été reçu ; une notification en double est
acceptée sans effet. C'est la seule écriture de l'API hors de son journal : une ligne dans la file, rien d'autre.
"""
import datetime
import os
import sqlite3
import sys

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from flux import notification  # noqa: E402

routeur = APIRouter(prefix='/api/flux')
TAILLE_MAX = 2048
SOURCE = 'v2'


@routeur.post('/v2', status_code=202)
async def notification_v2(requete: Request):
    reglages = requete.app.state.etat.reglages
    if not reglages.flux_v2_secret or not reglages.flux_base:
        return JSONResponse({'detail': 'Notification inactive'}, status_code=503)
    corps = await requete.body()
    if len(corps) > TAILLE_MAX:
        return JSONResponse({'detail': 'Notification refusée'}, status_code=413)
    maintenant = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    cx = sqlite3.connect(reglages.flux_base, timeout=5)
    try:
        cx.execute("INSERT INTO flux_source (nom, adresse) VALUES (?, '') ON CONFLICT (nom) DO NOTHING", (SOURCE,))
        notification.recevoir(cx, SOURCE, corps, requete.headers.get(notification.ENTETE_SIGNATURE),
                              requete.headers.get(notification.ENTETE_HORODATAGE), reglages.flux_v2_secret, maintenant)
    except notification.NotificationRefusee as e:
        cx.rollback()
        return JSONResponse({'detail': 'Notification refusée'}, status_code=400 if e.code == 'charge' else 401)
    finally:
        cx.close()
    return {'recu': True}
