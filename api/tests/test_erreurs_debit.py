"""Erreurs qui ne recopient jamais une donnée ; limites de débit ; CORS fermé."""

import logging

import pytest
from conftest import CLE, connecte, connecter, creer
from fastapi.testclient import TestClient

from app import identites
from app.config import lire_reglages
from app.main import creer_app

CIN = 'ZZ900008'


@pytest.mark.parametrize('chemin, corps', [
    ('/api/carte/recherche', {'q': CIN * 20}),
    ('/api/carte/recherche', {'q': CIN, 'autre': CIN}),
    ('/api/carte/noms', {'indices': [CIN]}),
    ('/api/carte/noms', {'indices': CIN}),
])
def test_erreur_de_validation_sans_la_valeur_saisie(client, etat, chemin, corps):
    connecte(client, etat, 'ana', 'ANALYSTE')
    r = client.post(chemin, json=corps)
    assert r.status_code == 422
    assert CIN not in r.text and '900008' not in r.text
    assert r.json()['detail'] == 'Requête invalide' and r.json()['champs']


def test_connexion_invalide_sans_la_valeur_saisie(client):
    r = client.post('/api/auth/connexion', json={'identifiant': CIN * 10, 'mot_de_passe': 'x'})
    assert r.status_code == 422 and CIN not in r.text


def test_erreur_interne_generique_et_rien_dans_les_journaux_techniques(env, monkeypatch, caplog):
    def panne(*_a):
        raise KeyError(f'{CIN} FASSI YOUSSEF')
    monkeypatch.setattr(identites, 'fiche', panne)
    app = creer_app(lire_reglages(env))
    with TestClient(app, base_url='https://testserver', raise_server_exceptions=False) as c:
        connecte(c, app.state.etat, 'ana', 'ANALYSTE')
        with caplog.at_level(logging.DEBUG):
            r = c.get('/api/carte/noeud/0')
    assert r.status_code == 500 and r.json() == {'detail': 'Erreur interne'}
    assert CIN not in caplog.text and 'FASSI' not in caplog.text
    assert 'KeyError' in caplog.text and '/api/carte/noeud' in caplog.text


def test_debit_limite_par_utilisateur(client_avec):
    with client_avec(CARTE_DEBIT='3/minute') as (c, etat):
        connecte(c, etat, 'ana', 'DIRECTION')
        codes = [c.get('/api/stats/regles').status_code for _ in range(4)]
        assert codes[:3] == [200, 200, 200] and codes[3] == 429
        c.cookies.clear()
        connecte(c, etat, 'autre', 'DIRECTION')
        assert c.get('/api/stats/regles').status_code == 200                 # compteur distinct


def test_debit_de_connexion_limite_par_adresse(client_avec):
    with client_avec(CARTE_DEBIT_CONNEXION='3/minute') as (c, etat):
        creer(etat, 'ana', 'ANALYSTE')
        codes = [connecter(c, 'ana', 'faux').status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]


def test_message_de_debit_en_francais(client_avec):
    with client_avec(CARTE_DEBIT='1/minute') as (c, etat):
        connecte(c, etat, 'ana', 'DIRECTION')
        c.get('/api/stats/regles')
        r = c.get('/api/stats/regles')
        assert r.status_code == 429 and r.json() == {'detail': 'Trop de requêtes, réessayez dans une minute'}


def test_cors_ferme_sauf_l_origine_de_l_application(client_avec):
    with client_avec(CARTE_ORIGINE='https://carte.exemple.invalid') as (c, _):
        bonne = c.options('/api/sante', headers={'Origin': 'https://carte.exemple.invalid',
                                                 'Access-Control-Request-Method': 'GET'})
        mauvaise = c.options('/api/sante', headers={'Origin': 'https://ailleurs.invalid',
                                                    'Access-Control-Request-Method': 'GET'})
    assert bonne.headers.get('access-control-allow-origin') == 'https://carte.exemple.invalid'
    assert 'access-control-allow-origin' not in mauvaise.headers


def test_sans_origine_configuree_aucun_cors(client):
    r = client.get('/api/sante', headers={'Origin': 'https://ailleurs.invalid'})
    assert 'access-control-allow-origin' not in r.headers
