"""Tests du serveur v2 fictif (étape C.3) : mêmes routes, paramètres, réponses et erreurs que la v2 de Kamal,
chronologie avec horloge réglable, notification signée."""

import datetime
import hashlib
import hmac
import json
import os
import sys

import pytest
from starlette.testclient import TestClient

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import serveur_v2  # noqa: E402
from pipeline import modeles_v2  # noqa: E402

SECRET = 'secret-fictif-de-notification'
COMPTE = {'email': 'analyste@exemple.invalid', 'password': 'mot-de-passe-fictif'}
FIN = datetime.datetime(2027, 1, 1)


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture
def serveur(jeu):
    recues = []
    appli = serveur_v2.creer_application(jeu, secret=SECRET, notifier=lambda corps, entetes: recues.append((corps, entetes)))
    appli.state.horloge.regler(FIN)
    recues.clear()
    client = TestClient(appli)
    jeton = client.post('/api/auth/login', json=COMPTE).json()['token']
    client.headers['Authorization'] = 'Bearer ' + jeton
    return client, appli, recues


def ref_de(jeu, code, **notes):
    return next(v['ref'] for v in jeu.verite if (code in v['scenarios'] or code in v['pieges'])
                and all(v['notes'].get(k) == x for k, x in notes.items()))


# ---- connexion -----------------------------------------------------------------------------------------------------

def test_connexion_rend_jeton_role_et_nom(jeu):
    client = TestClient(serveur_v2.creer_application(jeu, secret=SECRET))
    r = client.post('/api/auth/login', json=COMPTE)
    assert r.status_code == 200
    modeles_v2.LoginResponse.model_validate(r.json())


def test_connexion_refusee_sans_recopier_ce_qui_est_recu(jeu):
    client = TestClient(serveur_v2.creer_application(jeu, secret=SECRET))
    r = client.post('/api/auth/login', json={'email': 'inconnu@exemple.invalid', 'password': 'faux'})
    assert r.status_code == 401 and 'inconnu' not in r.text


@pytest.mark.parametrize('route', ['/api/dossiers', '/api/dossiers/ZZ26R0001', '/api/dossiers/ZZ26R0001/controls/IDT-01'])
def test_route_sans_jeton_refusee(jeu, route):
    client = TestClient(serveur_v2.creer_application(jeu, secret=SECRET))
    r = client.get(route)
    assert r.status_code == 401 and r.json() == {'error': 'unauthorized'}
    assert client.get(route, headers={'Authorization': 'Bearer faux'}).status_code == 401


# ---- liste ---------------------------------------------------------------------------------------------------------

def test_liste_au_format_de_la_v2_sans_pieces(serveur, jeu):
    client, _, _ = serveur
    r = client.get('/api/dossiers', params={'limit': 20})
    liste = modeles_v2.DossiersResponse.model_validate(r.json())
    actifs = sum(1 for m in jeu.meta.values() if m['actif'])
    assert len(liste.items) == 20 and liste.total == actifs
    assert 'pieces' not in r.json()['items'][0]
    assert sum(r.json()['counts']['status'].values()) == actifs


def test_pagination_par_limit_et_offset(serveur):
    client, _, _ = serveur
    tout = client.get('/api/dossiers', params={'limit': 500}).json()['items']
    page = client.get('/api/dossiers', params={'limit': 7, 'offset': 10}).json()['items']
    assert [d['ref'] for d in page] == [d['ref'] for d in tout[10:17]]
    assert len({d['ref'] for d in tout}) == len(tout)


def test_archives_hors_de_la_liste_sauf_si_demandes(serveur, jeu):
    client, _, _ = serveur
    archive = ref_de(jeu, 'S22')
    sans = {d['ref'] for d in client.get('/api/dossiers', params={'limit': 500}).json()['items']}
    avec = client.get('/api/dossiers', params={'limit': 500, 'archives': 'true'}).json()
    assert archive not in sans and archive in {d['ref'] for d in avec['items']}
    assert avec['total'] == len(jeu.dossiers)
    assert client.get('/api/dossiers/' + archive).status_code == 200      # consultable par lien direct


def test_filtres_de_la_liste(serveur, jeu):
    client, _, _ = serveur
    en_cours = client.get('/api/dossiers', params={'status': 'EN_COURS', 'limit': 500}).json()
    assert en_cours['items'] and all(d['analysisStatus'] == 'EN_COURS' for d in en_cours['items'])
    assert en_cours['total'] == len(en_cours['items'])
    categorie = client.get('/api/dossiers', params={'category': 'A', 'limit': 500}).json()['items']
    assert categorie and all(d['category'] == 'A' for d in categorie)
    ref = jeu.dossiers[0]['ref']
    assert [d['ref'] for d in client.get('/api/dossiers', params={'search': ref}).json()['items']] == [ref]
    jour = jeu.dossiers[0]['createdAt'][:10]
    du_jour = client.get('/api/dossiers', params={'from': jour, 'to': jour, 'limit': 500}).json()['items']
    assert du_jour and all(d['createdAt'].startswith(jour) for d in du_jour)


@pytest.mark.parametrize('parametres', [{'limit': 0}, {'limit': 100000}, {'offset': -1}, {'status': 'INCONNU'},
                                        {'from': '20260901'}, {'to': 'hier'}, {'limit': 'dix'}])
def test_parametre_invalide_refuse_sans_etre_recopie(serveur, parametres):
    client, _, _ = serveur
    r = client.get('/api/dossiers', params=parametres)
    assert r.status_code == 400 and r.json() == {'error': 'parametre_invalide'}


# ---- détail --------------------------------------------------------------------------------------------------------

def test_detail_d_un_dossier(serveur, jeu):
    client, _, _ = serveur
    ref = jeu.dossiers[0]['ref']
    r = client.get('/api/dossiers/' + ref)
    assert r.status_code == 200 and r.json() == jeu.dossiers[0]
    modeles_v2.DossierDetail.model_validate(r.json())


def test_dossier_inconnu_sans_recopier_la_reference(serveur):
    client, _, _ = serveur
    r = client.get('/api/dossiers/ZZ99X9999')
    assert r.status_code == 404 and r.json() == {'error': 'dossier_inconnu'} and 'ZZ99X9999' not in r.text


def test_detail_d_un_controle(serveur, jeu):
    client, _, _ = serveur
    d = next(x for x in jeu.dossiers if x['latestAnalysis'])
    r = client.get(f"/api/dossiers/{d['ref']}/controls/IDT-01")
    assert r.status_code == 200 and r.json()['controlId'] == 'IDT-01'
    assert {'label', 'family', 'numeroMetier', 'sourcePrincipale'} <= set(r.json())
    assert client.get(f"/api/dossiers/{d['ref']}/controls/ZZZ-99").json() == {'error': 'controle_inconnu'}


# ---- chronologie ---------------------------------------------------------------------------------------------------

def test_avant_la_premiere_arrivee_la_liste_est_vide(serveur, jeu):
    client, appli, _ = serveur
    appli.state.horloge.regler(datetime.datetime(2026, 1, 1))
    assert client.get('/api/dossiers').json()['total'] == 0
    assert client.get('/api/dossiers/' + jeu.dossiers[0]['ref']).status_code == 404


def test_les_dossiers_arrivent_au_fil_de_l_horloge(serveur, jeu):
    client, appli, _ = serveur
    dixieme = datetime.datetime.strptime(jeu.chronologie[9]['instant'], '%Y-%m-%dT%H:%M:%S.000Z')
    appli.state.horloge.regler(dixieme)
    assert client.get('/api/dossiers', params={'archives': 'true'}).json()['total'] == 10
    appli.state.horloge.avancer(minutes=38)
    assert client.get('/api/dossiers', params={'archives': 'true'}).json()['total'] == 11


def test_relecture_servie_a_partir_de_son_instant(serveur, jeu):
    client, appli, _ = serveur
    ref = ref_de(jeu, 'S17')
    versions = [e for e in jeu.chronologie if e['ref'] == ref]
    instant = lambda e: datetime.datetime.strptime(e['instant'], '%Y-%m-%dT%H:%M:%S.000Z')  # noqa: E731
    appli.state.horloge.regler(instant(versions[0]))
    assert client.get('/api/dossiers/' + ref).json() == versions[0]['dossier']
    appli.state.horloge.regler(instant(versions[1]))
    assert client.get('/api/dossiers/' + ref).json() == versions[1]['dossier']


# ---- notification signée -------------------------------------------------------------------------------------------

def neuf(jeu):
    """Serveur dont l'horloge n'a pas encore avancé : une notification ne part qu'une fois par événement."""
    recues = []
    appli = serveur_v2.creer_application(jeu, secret=SECRET, notifier=lambda c, e: recues.append((c, e)))
    return appli, recues


def test_notification_signee_a_chaque_evenement(jeu):
    appli, recues = neuf(jeu)
    cinquieme = datetime.datetime.strptime(jeu.chronologie[4]['instant'], '%Y-%m-%dT%H:%M:%S.000Z')
    appli.state.horloge.regler(cinquieme)
    assert len(recues) == 5
    corps, entetes = recues[0]
    charge = json.loads(corps)
    assert set(charge) == {'ref', 'updatedAt', 'analysisStatus', 'trigger'}     # aucune donnée personnelle
    assert charge['ref'] == jeu.chronologie[0]['ref'] and charge['trigger'] == 'INTAKE'
    attendue = hmac.new(SECRET.encode(), corps, hashlib.sha256).hexdigest()
    assert entetes[serveur_v2.ENTETE_SIGNATURE] == attendue and entetes[serveur_v2.ENTETE_HORODATAGE]
    appli.state.horloge.regler(cinquieme)                                       # rien de nouveau : rien d'envoyé
    assert len(recues) == 5


def test_notification_jamais_renvoyee_si_l_horloge_recule(jeu):
    appli, recues = neuf(jeu)
    appli.state.horloge.regler(FIN)
    appli.state.horloge.regler(datetime.datetime(2026, 1, 1))
    appli.state.horloge.regler(FIN)
    assert len(recues) == len(jeu.chronologie)


def test_notification_de_relecture(jeu):
    appli, recues = neuf(jeu)
    appli.state.horloge.regler(FIN)
    assert len(recues) == len(jeu.chronologie)
    declencheurs = {json.loads(c)['trigger'] for c, _ in recues}
    assert declencheurs == {'INTAKE', 'REANALYSE', 'REPLAY'}        # valeurs de schema.prisma


def test_sans_destinataire_aucune_notification(jeu):
    appli = serveur_v2.creer_application(jeu, secret=SECRET)
    appli.state.horloge.regler(FIN)      # ne plante pas


# ---- la notification ne part que vers cette machine ----------------------------------------------------------------

@pytest.mark.parametrize('adresse', ['http://127.0.0.1:8710/api/flux/v2', 'http://localhost:8710/api/flux/v2'])
def test_adresse_locale_admise(adresse):
    assert serveur_v2.adresse_locale(adresse)


@pytest.mark.parametrize('adresse', [
    'http://127.0.0.1.exemple.invalid/api/flux/v2',      # hôte distant au nom trompeur
    'http://localhost.exemple.invalid/',
    'http://127.0.0.1@exemple.invalid/',                 # partie « utilisateur@ »
    'http://localhost:8710@exemple.invalid/',
    'https://exemple.invalid/', 'ftp://127.0.0.1/', 'fichier', ''])
def test_adresse_distante_refusee(adresse):
    assert not serveur_v2.adresse_locale(adresse)
    with pytest.raises(ValueError):
        serveur_v2._notifier_par_http(adresse)


@pytest.mark.parametrize('corps', [{'email': ['a'], 'password': 'x'}, {'email': {'a': 1}, 'password': 'x'},
                                   {'email': 'analyste@exemple.invalid', 'password': 'é' * 8}, [1, 2], 'texte'])
def test_connexion_mal_formee_refusee_proprement(jeu, corps):
    client = TestClient(serveur_v2.creer_application(jeu, secret=SECRET))
    r = client.post('/api/auth/login', json=corps)
    assert r.status_code == 401 and r.json() == {'error': 'unauthorized'}


def test_horodatage_de_la_notification_est_l_heure_d_envoi(jeu):
    maintenant = datetime.datetime(2026, 11, 13, 12, 0, 0)
    recues = []
    appli = serveur_v2.creer_application(jeu, secret=SECRET, notifier=lambda c, e: recues.append(e),
                                         heure_d_envoi=lambda: maintenant)
    appli.state.horloge.regler(FIN)
    assert {e[serveur_v2.ENTETE_HORODATAGE] for e in recues} == {'2026-11-13T12:00:00.000Z'}
