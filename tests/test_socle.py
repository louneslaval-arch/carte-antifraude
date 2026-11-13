"""Tests du socle des couches : migrations, construire.py, verifier.py (étape B)."""

import json
import os
import sqlite3
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import construire  # noqa: E402
import verifier  # noqa: E402
from pipeline import migrer  # noqa: E402


@pytest.fixture
def base(tmp_path):
    return str(tmp_path / 'base.sqlite')


@pytest.fixture
def migrations(tmp_path):
    d = tmp_path / 'schema'
    d.mkdir()
    (d / '000_schema_version.sql').write_text(open(os.path.join(RACINE, 'schema', '000_schema_version.sql'),
                                                   encoding='utf-8').read(), encoding='utf-8')
    (d / '001_essai.sql').write_text('CREATE TABLE c0_essai (id INTEGER PRIMARY KEY, nom TEXT NOT NULL);\n',
                                     encoding='utf-8')
    return str(d)


# --- migrations ---

def test_base_vide_puis_migrations(base, migrations):
    with sqlite3.connect(base) as cx:
        appliquees = migrer.appliquer(cx, migrations)
        assert appliquees == ['000_schema_version.sql', '001_essai.sql']
        assert cx.execute('SELECT count(*) FROM schema_version').fetchone()[0] == 2
        cx.execute("INSERT INTO c0_essai (nom) VALUES ('a')")


def test_migration_rejouee_sans_effet(base, migrations):
    with sqlite3.connect(base) as cx:
        migrer.appliquer(cx, migrations)
        assert migrer.appliquer(cx, migrations) == []
        assert cx.execute('SELECT count(*) FROM schema_version').fetchone()[0] == 2


def test_migration_modifiee_a_la_main_refusee(base, migrations):
    with sqlite3.connect(base) as cx:
        migrer.appliquer(cx, migrations)
    with open(os.path.join(migrations, '001_essai.sql'), 'a', encoding='utf-8') as f:
        f.write('-- retouche\n')
    with sqlite3.connect(base) as cx, pytest.raises(migrer.ErreurMigration):
        migrer.appliquer(cx, migrations)


def test_nom_de_migration_non_numerote_refuse(base, migrations):
    open(os.path.join(migrations, 'essai.sql'), 'w').close()
    with sqlite3.connect(base) as cx, pytest.raises(migrer.ErreurMigration):
        migrer.appliquer(cx, migrations)


def test_migration_en_echec_ne_laisse_rien(base, migrations):
    with open(os.path.join(migrations, '002_casse.sql'), 'w', encoding='utf-8') as f:
        f.write('CREATE TABLE c0_b (id INTEGER);\nCECI N EST PAS DU SQL;\n')
    with sqlite3.connect(base) as cx:
        with pytest.raises(migrer.ErreurMigration):
            migrer.appliquer(cx, migrations)
        tables = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert 'c0_b' not in tables
        assert cx.execute('SELECT max(numero) FROM schema_version').fetchone()[0] == 1


# --- construire.py ---

class CoucheEssai:
    def __init__(self, nom, journal):
        self.nom, self.journal = nom, journal

    def construire_tout(self, cx):
        self.journal.append((self.nom, 'tout'))

    def traiter(self, cx, ref):
        self.journal.append((self.nom, ref))


@pytest.fixture
def couches():
    journal = []
    return [CoucheEssai(f'c{i}', journal) for i in range(3)], journal


def test_construire_toutes_les_couches_dans_l_ordre(base, migrations, couches):
    liste, journal = couches
    construire.construire(base, couches=liste, schema=migrations)
    assert journal == [('c0', 'tout'), ('c1', 'tout'), ('c2', 'tout')]


def test_depuis_et_jusqua(base, migrations, couches):
    liste, journal = couches
    construire.construire(base, couches=liste, schema=migrations, depuis='c1', jusqua='c1')
    assert journal == [('c1', 'tout')]


def test_un_seul_dossier_comme_le_flux(base, migrations, couches):
    liste, journal = couches
    construire.construire(base, couches=liste, schema=migrations, dossier='ZZ000001')
    assert journal == [('c0', 'ZZ000001'), ('c1', 'ZZ000001'), ('c2', 'ZZ000001')]


def test_couche_inconnue_refusee(base, migrations, couches):
    with pytest.raises(ValueError):
        construire.construire(base, couches=couches[0], schema=migrations, depuis='c9')


# --- verifier.py ---

def _invariants(tmp_path, liste):
    p = tmp_path / 'invariants.yaml'
    p.write_text(json.dumps({'invariants': liste}, ensure_ascii=False), encoding='utf-8')
    return str(p)


def test_verifier_vert_sur_base_migree(base, migrations, tmp_path, capsys):
    with sqlite3.connect(base) as cx:
        migrer.appliquer(cx, migrations)
    inv = _invariants(tmp_path, [
        {'nom': 'migrations_sans_empreinte', 'zero': "SELECT numero FROM schema_version WHERE empreinte = ''"},
        {'nom': 'migrations', 'comptage': 'SELECT count(*) FROM schema_version', 'minimum': 1},
    ])
    assert verifier.verifier(base, inv) == 0
    sortie = capsys.readouterr().out
    assert 'migrations_sans_empreinte : 0' in sortie and 'migrations : 2' in sortie


def test_invariant_viole_expres(base, migrations, tmp_path, capsys):
    with sqlite3.connect(base) as cx:
        migrer.appliquer(cx, migrations)
        cx.execute("INSERT INTO c0_essai (nom) VALUES ('ZZ000001')")
    inv = _invariants(tmp_path, [
        {'nom': 'essai_vide', 'zero': 'SELECT nom FROM c0_essai'},
        {'nom': 'jamais_atteint', 'zero': 'SELECT 1'},
    ])
    assert verifier.verifier(base, inv) == 1
    sortie = capsys.readouterr().out
    assert 'essai_vide : 1' in sortie
    assert 'jamais_atteint' not in sortie  # arrêt au premier écart
    assert 'ZZ000001' not in sortie  # comptages seulement, jamais une valeur


def test_comptage_avec_tolerance(base, migrations, tmp_path):
    with sqlite3.connect(base) as cx:
        migrer.appliquer(cx, migrations)
    inv = _invariants(tmp_path, [{'nom': 'migrations', 'comptage': 'SELECT count(*) FROM schema_version',
                                  'attendu': 3, 'tolerance': 1}])
    assert verifier.verifier(base, inv) == 0
    inv = _invariants(tmp_path, [{'nom': 'migrations', 'comptage': 'SELECT count(*) FROM schema_version',
                                  'attendu': 5, 'tolerance': 1}])
    assert verifier.verifier(base, inv) == 1


def test_invariant_mal_declare_refuse(base, tmp_path):
    inv = _invariants(tmp_path, [{'nom': 'x'}])
    with pytest.raises(ValueError):
        verifier.verifier(base, inv)


# --- de bout en bout ---

def test_construire_puis_verifier_en_une_commande(tmp_path):
    base = str(tmp_path / 'essai.sqlite')
    env = dict(os.environ, CARTE_BASE_ESSAI=base)
    r1 = subprocess.run([sys.executable, 'construire.py', '--jeu-essai'], cwd=RACINE, env=env,
                        capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run([sys.executable, 'verifier.py', '--base', base], cwd=RACINE, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr
