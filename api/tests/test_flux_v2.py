"""Route POST /api/flux/v2 : notification signée de la v2, prête mais inactive sans secret (étape D.4)."""

import datetime
import hashlib
import hmac
import json
import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from conftest import CLE

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RACINE)
from flux import notification  # noqa: E402
from pipeline import migrer  # noqa: E402

SECRET = 'secret-fictif-de-notification-0123456789'
CHARGE = dict(ref='ZZ26R0001', updatedAt='2026-11-13T11:59:00.000Z', analysisStatus='COMPLETE', trigger='INTAKE')


def appli(env_supplementaire, tmp_path):
    from app.config import lire_reglages
    from app.main import creer_app
    env = {'CARTE_CLE_JWT': CLE, 'CARTE_BASE_URL': f'sqlite:///{tmp_path}/carte.db', **env_supplementaire}
    return TestClient(creer_app(lire_reglages(env)), base_url='https://testserver')


@pytest.fixture
def base(tmp_path):
    chemin = str(tmp_path / 'flux.sqlite')
    with sqlite3.connect(chemin) as cx:
        migrer.appliquer(cx)
    return chemin


@pytest.fixture
def client(base, tmp_path):
    with appli({'CARTE_FLUX_V2_SECRET': SECRET, 'CARTE_FLUX_BASE': base}, tmp_path) as c:
        yield c


def envoyer(client, charge=CHARGE, secret=SECRET, decalage_s=0, corps=None):
    corps = corps if corps is not None else json.dumps(charge, separators=(',', ':')).encode()
    quand = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=decalage_s)
    return client.post('/api/flux/v2', content=corps, headers={
        notification.ENTETE_SIGNATURE: hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest(),
        notification.ENTETE_HORODATAGE: quand.strftime(notification.FORMAT), 'Content-Type': 'application/json'})


def travaux(base):
    with sqlite3.connect(base) as cx:
        return cx.execute('SELECT ref, updated_at, etat FROM flux_travail').fetchall()


def test_notification_acceptee_met_le_dossier_en_file(client, base):
    r = envoyer(client)
    assert r.status_code == 202 and 'ZZ26R0001' not in r.text
    assert travaux(base) == [('ZZ26R0001', '2026-11-13T11:59:00.000Z', 'en_attente')]


def test_notification_en_double_sans_effet(client, base):
    assert envoyer(client).status_code == 202 and envoyer(client).status_code == 202
    assert len(travaux(base)) == 1


@pytest.mark.parametrize('cas, statut', [
    (dict(secret='un-autre-secret'), 401), (dict(decalage_s=-400), 401), (dict(decalage_s=400), 401),
    (dict(charge=dict(CHARGE, clientName='NOM FICTIF')), 400), (dict(corps=b'pas du json'), 400)])
def test_notification_refusee_sans_rien_ecrire_ni_recopier(client, base, cas, statut):
    r = envoyer(client, **cas)
    assert r.status_code == statut and r.json() == {'detail': 'Notification refusée'}
    assert travaux(base) == []


def test_corps_trop_long_refuse(client, base):
    assert envoyer(client, corps=b'{"ref": "' + b'Z' * 5000 + b'"}').status_code == 413
    assert travaux(base) == []


@pytest.mark.parametrize('env', [{}, {'CARTE_FLUX_V2_SECRET': SECRET}, {'CARTE_FLUX_BASE': 'x.sqlite'}])
def test_route_inactive_sans_secret_ou_sans_base(env, tmp_path):
    with appli(env, tmp_path) as c:
        r = envoyer(c)
        assert r.status_code == 503 and r.json() == {'detail': 'Notification inactive'}


def test_secret_trop_court_refuse_au_demarrage(tmp_path):
    from app.config import ReglageInvalide
    with pytest.raises(ReglageInvalide):
        appli({'CARTE_FLUX_V2_SECRET': 'court', 'CARTE_FLUX_BASE': 'x.sqlite'}, tmp_path)
