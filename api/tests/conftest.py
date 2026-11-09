"""Publications fictives et application de test. Aucune donnée réelle : tout vient de jeu_essai/."""

import os
import shutil
import sqlite3
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path.insert(0, os.path.join(RACINE, 'api'))
sys.path.insert(0, os.path.join(RACINE, 'jeu_essai'))
sys.path.insert(0, os.path.join(RACINE, 'pipeline'))
import fabrique  # noqa: E402
import publier_carte  # noqa: E402

CLE = 'cle-de-test-' + 'x' * 40


@pytest.fixture(scope='session')
def kit(tmp_path_factory):
    """Base et chaînes du kit, construites une fois."""
    d = str(tmp_path_factory.mktemp('kit'))
    base, chaines = fabrique.du_kit(d)
    return dict(dossier=d, base=base, chaines=chaines)


@pytest.fixture(scope='session')
def publication(kit):
    dossier = os.path.join(kit['dossier'], 'publication')
    publier_carte.publier(kit['base'], kit['chaines'], dossier)
    return dossier


@pytest.fixture(scope='session')
def publication_reelle(kit, tmp_path_factory):
    """Publication dont un CIN ne porte pas le préfixe fictif : doit être refusée sans autorisation."""
    d = str(tmp_path_factory.mktemp('reelle'))
    base = os.path.join(d, 'base.sqlite')
    shutil.copy(kit['base'], base)
    con = sqlite3.connect(base)
    con.execute("UPDATE bl_entite SET cin = 'AB123456' WHERE entite_id = "
                "(SELECT MIN(entite_id) FROM bl_entite WHERE cin IS NOT NULL)")
    con.commit()
    con.close()
    dossier = os.path.join(d, 'publication')
    publier_carte.publier(base, kit['chaines'], dossier)
    return dossier


@pytest.fixture
def env(publication, tmp_path):
    return {'CARTE_CLE_JWT': CLE, 'CARTE_BASE_URL': f'sqlite:///{tmp_path}/carte.db',
            'CARTE_PUBLICATION': publication}


# ---- application, comptes et connexion -------------------------------------------------------------------------
MDP = 'mot-de-passe-de-test-1'


@pytest.fixture
def app_test(env):
    from fastapi.testclient import TestClient

    from app.config import lire_reglages
    from app.main import creer_app
    app = creer_app(lire_reglages(env))
    with TestClient(app, base_url='https://testserver') as client:
        yield client, app.state.etat


@pytest.fixture
def client(app_test):
    return app_test[0]


@pytest.fixture
def etat(app_test):
    return app_test[1]


def creer(etat, identifiant, role, mdp=MDP):
    from app import comptes
    comptes.creer(etat.base, identifiant, role, mdp)


def connecter(client, identifiant, mdp=MDP):
    return client.post('/api/auth/connexion', json={'identifiant': identifiant, 'mot_de_passe': mdp})


@pytest.fixture
def analyste(client, etat):
    """Client connecté en analyste (cookie posé)."""
    creer(etat, 'analyste1', 'ANALYSTE')
    assert connecter(client, 'analyste1').status_code == 200
    return client


@pytest.fixture
def client_avec(env):
    """Fabrique d'applications aux réglages modifiés : with client_avec(CARTE_QUOTA_FICHES='2') as (c, etat)."""
    import contextlib

    from fastapi.testclient import TestClient

    from app.config import lire_reglages
    from app.main import creer_app

    @contextlib.contextmanager
    def fabriquer(**surcharges):
        app = creer_app(lire_reglages(dict(env, **surcharges)))
        with TestClient(app, base_url='https://testserver') as c:
            yield c, app.state.etat
    return fabriquer


def connecte(client, etat, identifiant, role):
    creer(etat, identifiant, role)
    assert connecter(client, identifiant).status_code == 200
    return client


def identites(publication, requete, *params):
    con = sqlite3.connect(os.path.join(publication, 'identites.sqlite'))
    try:
        return con.execute(requete, params).fetchall()
    finally:
        con.close()


def indice_de(publication, ref):
    return identites(publication, 'SELECT indice FROM noeud WHERE ref_id = ?', ref)[0][0]


def tout_le_journal(etat):
    """Toutes les valeurs de toutes les lignes du journal, en texte, pour y chercher une fuite."""
    from sqlalchemy import text
    with etat.base() as s:
        lignes = s.execute(text('SELECT * FROM journal')).fetchall() + \
            s.execute(text('SELECT * FROM journal_indice')).fetchall()
    return ' '.join(str(v) for l in lignes for v in l)
