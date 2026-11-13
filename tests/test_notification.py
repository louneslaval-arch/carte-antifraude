"""Tests de la notification signée de la v2 (étape D.4) : signature, horodatage, charge utile, doublons."""

import datetime
import hashlib
import hmac
import json
import os
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from flux import notification  # noqa: E402
from pipeline import migrer  # noqa: E402

SECRET = 'secret-fictif-de-notification'
MAINTENANT = datetime.datetime(2026, 11, 13, 12, 0, 0)
CHARGE = dict(ref='ZZ26R0001', updatedAt='2026-11-13T11:59:00.000Z', analysisStatus='COMPLETE', trigger='INTAKE')


def corps(charge=CHARGE):
    return json.dumps(charge, separators=(',', ':')).encode()


def signer(c, secret=SECRET):
    return hmac.new(secret.encode(), c, hashlib.sha256).hexdigest()


def horodatage(decalage_s=0):
    return (MAINTENANT + datetime.timedelta(seconds=decalage_s)).strftime(notification.FORMAT)


@pytest.fixture
def cx():
    connexion = sqlite3.connect(':memory:')
    migrer.appliquer(connexion)
    connexion.execute("INSERT INTO flux_source (nom, adresse) VALUES ('v2', '')")
    return connexion


def test_notification_valide_rend_la_charge():
    c = corps()
    assert notification.verifier(c, signer(c), horodatage(), SECRET, MAINTENANT) == CHARGE


@pytest.mark.parametrize('decalage', [-299, 299])
def test_horodatage_a_cinq_minutes_pres_admis(decalage):
    c = corps()
    notification.verifier(c, signer(c), horodatage(decalage), SECRET, MAINTENANT)


@pytest.mark.parametrize('cas, code', [
    (dict(signature='0' * 64), 'signature'),
    (dict(signature=None), 'signature'),
    (dict(secret_envoi='autre-secret'), 'signature'),
    (dict(horodatage=horodatage(-301)), 'horodatage'),
    (dict(horodatage=horodatage(301)), 'horodatage'),
    (dict(horodatage='hier'), 'horodatage'),
    (dict(horodatage=None), 'horodatage'),
    (dict(charge=dict(CHARGE, clientName='NOM FICTIF')), 'charge'),            # rien d'autre que les quatre champs
    (dict(charge={k: v for k, v in CHARGE.items() if k != 'trigger'}), 'charge'),
    (dict(charge=dict(CHARGE, ref=12)), 'charge'),
    (dict(charge=dict(CHARGE, trigger='INCONNU')), 'charge'),
    (dict(charge=dict(CHARGE, analysisStatus='INCONNU')), 'charge'),
    (dict(brut=b'pas du json'), 'charge'),
    (dict(brut=b'[1, 2]'), 'charge'),
])
def test_notification_refusee(cas, code):
    c = cas.get('brut') or corps(cas.get('charge', CHARGE))
    signature = cas['signature'] if 'signature' in cas else signer(c, cas.get('secret_envoi', SECRET))
    with pytest.raises(notification.NotificationRefusee) as erreur:
        notification.verifier(c, signature, cas.get('horodatage', horodatage()), SECRET, MAINTENANT)
    assert erreur.value.code == code and 'ZZ26R0001' not in str(erreur.value)


@pytest.mark.parametrize('secret', ['', None])
def test_sans_secret_la_route_est_inactive(secret):
    c = corps()
    with pytest.raises(notification.NotificationRefusee) as erreur:
        notification.verifier(c, signer(c), horodatage(), secret, MAINTENANT)
    assert erreur.value.code == 'inactive'


def test_notification_met_un_travail_en_file_et_un_doublon_est_sans_effet(cx):
    c = corps()
    assert notification.recevoir(cx, 'v2', c, signer(c), horodatage(), SECRET, MAINTENANT) is True
    assert notification.recevoir(cx, 'v2', c, signer(c), horodatage(), SECRET, MAINTENANT) is False
    assert cx.execute('SELECT ref, updated_at, etat FROM flux_travail').fetchall() == \
        [('ZZ26R0001', '2026-11-13T11:59:00.000Z', 'en_attente')]


def test_notification_refusee_n_ecrit_rien(cx):
    c = corps()
    with pytest.raises(notification.NotificationRefusee):
        notification.recevoir(cx, 'v2', c, 'fausse', horodatage(), SECRET, MAINTENANT)
    assert cx.execute('SELECT count(*) FROM flux_travail').fetchone()[0] == 0


@pytest.mark.parametrize('h', ['2026-11-13T12:00:00.123Z', '2026-11-13T12:00:00Z', '2026-11-13T12:00:00.000Z',
                               '2026-11-13T13:00:00.000+01:00'])
def test_horodatage_iso_avec_ou_sans_millisecondes(h):
    c = corps()
    notification.verifier(c, signer(c), h, SECRET, MAINTENANT)


def test_declencheurs_egaux_a_ceux_de_la_base_de_kamal():
    schema = os.path.join(RACINE, 'import', 'kamal_structure', 'schema', 'schema.prisma')
    if not os.path.exists(schema):
        pytest.skip('structure de Kamal absente')
    sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
    import lire_prisma
    with open(schema, encoding='utf-8') as f:
        attendus = {v.nom for v in lire_prisma.lire(f.read()).enums['AnalysisTrigger'].valeurs}
    assert notification.DECLENCHEURS == attendus
