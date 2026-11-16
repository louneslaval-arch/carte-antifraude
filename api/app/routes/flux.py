"""Temps réel : notification signée de la v2.

`POST /api/flux/v2` reçoit `{ref, updatedAt, analysisStatus, trigger}` à la fin d'une analyse. Dans l'ordre : la
route est inactive (503) tant que `CARTE_FLUX_V2_SECRET` et `CARTE_FLUX_BASE` ne sont pas posés ; le corps est borné
à la réception ; la signature et l'horodatage sont vérifiés (`flux/notification.py`) ; alors seulement la base est
ouverte et le dossier mis en file pour le collecteur. Une requête non signée n'écrit donc rien et ne prend aucun
verrou. La route n'est pas protégée par un rôle mais par la signature (`roles.HORS_ROLES`).

Réponses aux conventions de l'API de Kamal (`{"error": code}`), sans jamais recopier ce qui a été reçu ; une
notification en double est acceptée sans effet. C'est la seule écriture de l'API hors de son journal : une ligne
dans la file, rien d'autre (exception à « l'API lit seulement », questions ouvertes n°34).
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


def _erreur(code, statut):
    return JSONResponse({'error': code}, status_code=statut)


async def _corps_borne(requete):
    """Corps de la requête, ou None s'il dépasse la borne : rien n'est gardé au-delà."""
    annonce = requete.headers.get('content-length')
    if annonce is not None and (not annonce.isdigit() or int(annonce) > TAILLE_MAX):
        return None
    morceaux, taille = [], 0
    async for morceau in requete.stream():
        taille += len(morceau)
        if taille > TAILLE_MAX:
            return None
        morceaux.append(morceau)
    return b''.join(morceaux)


@routeur.post('/v2', status_code=202)
async def notification_v2(requete: Request):
    reglages = requete.app.state.etat.reglages
    if not reglages.flux_v2_secret or not reglages.flux_base:
        return _erreur('inactif', 503)
    corps = await _corps_borne(requete)
    if corps is None:
        return _erreur('trop_long', 413)
    maintenant = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    try:
        charge = notification.verifier(corps, requete.headers.get(notification.ENTETE_SIGNATURE),
                                       requete.headers.get(notification.ENTETE_HORODATAGE),
                                       reglages.flux_v2_secret, maintenant)
    except notification.NotificationRefusee as e:
        return _erreur('charge_invalide', 400) if e.code == 'charge' else _erreur('unauthorized', 401)
    cx = sqlite3.connect(reglages.flux_base, timeout=5)
    try:
        cx.execute("INSERT INTO flux_source (nom, adresse) VALUES (?, '') ON CONFLICT (nom) DO NOTHING", (SOURCE,))
        notification.mettre_en_file(cx, SOURCE, charge, maintenant)
    finally:
        cx.close()
    return {'ok': True}
