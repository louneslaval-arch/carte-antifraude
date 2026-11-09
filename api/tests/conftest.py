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
