"""Notification signée de la v2 (`POST /api/flux/v2`) : vérification et mise en file.

La v2 annonce la fin d'une analyse par une charge utile `{ref, updatedAt, analysisStatus, trigger}`, aux noms et aux
valeurs d'énumération de Kamal, sans aucune donnée personnelle. Le corps est signé (HMAC SHA-256, secret partagé en
variable d'environnement) et daté : un horodatage à plus de 5 minutes est refusé. Une notification déjà reçue est
sans effet. Le collecteur va ensuite chercher le dossier.

Provisoire, tant que Kamal n'a pas fixé le format (questions ouvertes n°31) : noms des en-têtes, signature sur le
corps seul (l'horodatage n'est donc pas signé). Un refus ne cite jamais ce qui a été reçu.
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
from typing import get_args

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flux import file  # noqa: E402
from pipeline import modeles_v2  # noqa: E402

ENTETE_SIGNATURE = 'X-Signature'
ENTETE_HORODATAGE = 'X-Horodatage'
FORMAT = file.FORMAT
TOLERANCE_S = 300
CHAMPS = {'ref', 'updatedAt', 'analysisStatus', 'trigger'}
DECLENCHEURS = {'INTAKE', 'REANALYSE', 'REPLAY'}                   # AnalysisTrigger de schema.prisma
STATUTS = set(get_args(modeles_v2.DossierStatus))


class NotificationRefusee(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def verifier(corps, signature, horodatage, secret, maintenant):
    """Rend la charge utile si la notification est authentique, récente et bien formée ; sinon la refuse."""
    if not secret:
        raise NotificationRefusee('inactive')
    attendue = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature.encode(), attendue.encode()):
        raise NotificationRefusee('signature')
    try:
        ecart = abs((maintenant - datetime.datetime.strptime(horodatage, FORMAT)).total_seconds())
    except (TypeError, ValueError):
        raise NotificationRefusee('horodatage') from None
    if ecart > TOLERANCE_S:
        raise NotificationRefusee('horodatage')
    try:
        charge = json.loads(corps)
    except ValueError:
        raise NotificationRefusee('charge') from None
    if not isinstance(charge, dict) or set(charge) != CHAMPS or not all(isinstance(v, str) and v for v in charge.values()) \
            or charge['trigger'] not in DECLENCHEURS or charge['analysisStatus'] not in STATUTS:
        raise NotificationRefusee('charge')
    return charge


def recevoir(cx, source, corps, signature, horodatage, secret, maintenant):
    """Vérifie la notification et met le dossier en file. Rend faux si cette version était déjà annoncée."""
    charge = verifier(corps, signature, horodatage, secret, maintenant)
    nouveau = file.annoncer(cx, source, charge['ref'], charge['updatedAt'], True, maintenant)
    cx.commit()
    return nouveau
