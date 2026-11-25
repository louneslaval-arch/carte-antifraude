"""Copie de la base PostgreSQL de la carte (tables du kit : bl_*, rc_*, af_*, cle, noeud, arete…) vers un fichier
SQLite aux mêmes noms, pour que les scripts du kit (carte_globale.py, chaines_dessin.py, publier_*.py) la lisent comme
avant. Lecture seule ; sortie : nom de table et nombre de lignes seulement. Données réelles : Lounès seul la lance."""
import datetime
import decimal
import os
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from outils import copier_pg_sqlite as cp  # noqa: E402


def test_les_types_de_postgresql_deviennent_ceux_de_sqlite():
    assert cp.type_sqlite('integer') == cp.type_sqlite('bigint') == cp.type_sqlite('boolean') == 'INTEGER'
    assert cp.type_sqlite('double precision') == cp.type_sqlite('numeric') == cp.type_sqlite('real') == 'REAL'
    assert cp.type_sqlite('text') == cp.type_sqlite('character varying') == cp.type_sqlite('jsonb') == 'TEXT'
    assert cp.type_sqlite('timestamp without time zone') == 'TEXT' and cp.type_sqlite('bytea') == 'BLOB'


def test_les_valeurs_prennent_la_forme_que_lisaient_les_scripts():
    assert cp.valeur(True) == 1 and cp.valeur(False) == 0
    assert cp.valeur(decimal.Decimal('1.5')) == 1.5 and isinstance(cp.valeur(decimal.Decimal('1.5')), float)
    assert cp.valeur(datetime.datetime(2026, 11, 25, 9, 30, 0)) == '2026-11-25 09:30:00'
    assert cp.valeur(datetime.date(2026, 11, 25)) == '2026-11-25'
    assert cp.valeur({'b': 1, 'a': [2]}) == '{"a": [2], "b": 1}'
    assert cp.valeur(memoryview(b'ab')) == b'ab' and cp.valeur(None) is None and cp.valeur('ZZ1') == 'ZZ1'


def _source(chemin):
    cx = sqlite3.connect(str(chemin))
    cx.execute('CREATE TABLE bl_entite (entite_id INTEGER, nom TEXT, score REAL)')
    cx.executemany('INSERT INTO bl_entite VALUES (?, ?, ?)', [(i, f'ZZNOM{i}', i / 3) for i in range(2500)])
    cx.execute('CREATE TABLE "cle" (cle TEXT, n INTEGER)')
    cx.execute('INSERT INTO cle VALUES (\'ZZCLE\', 2)')
    cx.commit()
    return cx


TABLES = {'bl_entite': [('entite_id', 'integer'), ('nom', 'text'), ('score', 'double precision')],
          'cle': [('cle', 'text'), ('n', 'bigint')]}


def test_chaque_table_est_copiee_a_l_identique(tmp_path):
    src = _source(tmp_path / 'src.sqlite')
    sortie = tmp_path / 'copie.sqlite'
    comptes = cp.copier(src, str(sortie), TABLES, lot=700)
    assert comptes == {'bl_entite': 2500, 'cle': 1}
    copie = sqlite3.connect(str(sortie))
    for table in TABLES:
        assert copie.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall() == \
            src.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
    assert [c[2] for c in copie.execute('PRAGMA table_info(bl_entite)')] == ['INTEGER', 'TEXT', 'REAL']


def test_une_copie_interrompue_ne_laisse_pas_de_base_a_moitie_faite(tmp_path):
    src = _source(tmp_path / 'src.sqlite')
    sortie = tmp_path / 'copie.sqlite'
    with pytest.raises(sqlite3.OperationalError):
        cp.copier(src, str(sortie), dict(TABLES, absente=[('x', 'text')]))
    assert not sortie.exists() and not (tmp_path / 'copie.sqlite.partiel').exists()


def test_une_copie_existante_est_remplacee_en_entier(tmp_path):
    src = _source(tmp_path / 'src.sqlite')
    sortie = tmp_path / 'copie.sqlite'
    cp.copier(src, str(sortie), TABLES)
    src.execute('DELETE FROM bl_entite WHERE entite_id >= 10')
    src.commit()
    assert cp.copier(src, str(sortie), TABLES)['bl_entite'] == 10
    assert sqlite3.connect(str(sortie)).execute('SELECT count(*) FROM bl_entite').fetchone()[0] == 10


def test_la_console_ne_montre_que_des_noms_de_table_et_des_nombres(tmp_path, capsys):
    src = _source(tmp_path / 'src.sqlite')
    cp.copier(src, str(tmp_path / 'copie.sqlite'), TABLES, afficher=True)
    sortie = capsys.readouterr().out
    assert 'bl_entite' in sortie and '2500' in sortie and 'ZZ' not in sortie


def test_sans_le_garde_fou_ou_dans_le_depot_rien_ne_part(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv('CARTE_SOURCE_PG', 'host=127.0.0.1 port=1 dbname=zzbase connect_timeout=1')
    monkeypatch.delenv('CARTE_DONNEES_REELLES', raising=False)
    assert cp.main(['--sortie', str(tmp_path / 'copie.sqlite')]) == 2
    assert 'CARTE_DONNEES_REELLES' in capsys.readouterr().err
    assert cp.main(['--sortie', os.path.join(RACINE, 'jeu_essai', 'sortie', 'zz_copie.sqlite')]) == 2
    assert 'hors du dépôt' in capsys.readouterr().err
    monkeypatch.delenv('CARTE_SOURCE_PG')
    assert cp.main(['--sortie', str(tmp_path / 'copie.sqlite')]) == 2
    assert not (tmp_path / 'copie.sqlite').exists()
