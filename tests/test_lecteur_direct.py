"""Lecteur direct de la base de l'antifraude (étape L) : les tables de Kamal (`Dossier`, `Piece`, `Analysis`,
`AnalysisControl`, `Reanalysis`) sont lues telles quelles, chaque dossier est remis sous la forme de `DossierDetail` et
passe par `c0_brut.recevoir` : versions brutes, miroir et couches au-dessus restent ceux du collecteur.

La source des tests est une base SQLite aux noms exacts de Kamal (le miroir de la couche 0), remplie de dossiers
fictifs ; la même lecture sur PostgreSQL tourne quand `CARTE_PG_ESSAI` désigne une base d'essai vide."""
import datetime
import os
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2'), os.path.join(RACINE, 'outils', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
from flux import lecteur_direct as ld  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut as c0, c1_faits as c1  # noqa: E402

T0 = '2026-11-24T10:00:00.000Z'
TABLES_MIROIR = ('Dossier', 'Piece', 'Analysis', 'AnalysisControl', 'Reanalysis')


def _base(chemin):
    cx = sqlite3.connect(str(chemin))
    cx.execute('PRAGMA foreign_keys = ON')
    migrer.appliquer(cx)
    return cx


def miroir(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM "{t}"').fetchall(), key=repr) for t in TABLES_MIROIR}


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=300, n_societes=300, graine=20261124)


@pytest.fixture(scope='module')
def source(jeu, tmp_path_factory):
    """La « base de l'antifraude » fictive : dossiers reçus par le collecteur, leurs tables aux noms de Kamal."""
    cx = _base(tmp_path_factory.mktemp('source') / 'antifraude.sqlite')
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for e in jeu.chronologie:
        try:
            c0.recevoir(cx, passage, e['dossier'], maintenant=T0)
        except c0.MiroirRefuse:
            pass                                       # piège du jeu : brut seulement, absent des tables
    yield cx
    cx.close()


@pytest.fixture
def cible(tmp_path):
    cx = _base(tmp_path / 'carte.sqlite')
    yield cx
    cx.close()


def _lire(source, cible, **k):
    passage = c0.ouvrir_passage(cible, 'base antifraude', 'lecture_directe', T0)
    return ld.lire(source, cible, passage, maintenant=T0, **k)


# ---- même résultat que le collecteur -------------------------------------------------------------------------------

def test_la_lecture_directe_donne_le_meme_miroir_que_le_collecteur(source, cible):
    bilan = _lire(source, cible)
    attendu = miroir(source)
    assert bilan['dossiers'] == len(attendu['Dossier']) > 100
    assert miroir(cible) == attendu


def test_les_faits_construits_sont_les_memes(source, cible, tmp_path):
    _lire(source, cible)
    copie = _base(tmp_path / 'copie.sqlite')
    source.backup(copie)
    c1.construire_tout(copie)
    c1.construire_tout(cible)
    for table in c1.TABLES:
        assert sorted(cible.execute(f'SELECT * FROM {table}').fetchall(), key=repr) == \
            sorted(copie.execute(f'SELECT * FROM {table}').fetchall(), key=repr), table
    copie.close()


def test_relire_une_base_inchangee_n_ajoute_aucune_version(source, cible):
    premier = _lire(source, cible)
    second = _lire(source, cible)
    assert premier['versions_nouvelles'] == premier['dossiers'] and second['versions_nouvelles'] == 0
    assert cible.execute('SELECT count(*) FROM c0_dossier_brut').fetchone()[0] == premier['dossiers']


def test_les_identifiants_de_kamal_sont_repris_sans_rien_deriver(source, cible):
    source_bis = sqlite3.connect(':memory:')
    source.backup(source_bis)
    source_bis.execute('UPDATE "Piece" SET id = \'pk-\' || rowid, "createdAt" = \'2026-01-02T03:04:05.006Z\'')
    source_bis.execute('UPDATE "Reanalysis" SET id = \'rk-\' || rowid')
    _lire(source_bis, cible)
    assert cible.execute('SELECT count(*) FROM "Piece" WHERE id NOT LIKE \'pk-%\'').fetchone()[0] == 0
    assert cible.execute('SELECT count(*) FROM "Piece" WHERE "createdAt" != \'2026-01-02T03:04:05.006Z\'').fetchone()[0] == 0
    assert cible.execute('SELECT count(*) FROM "Reanalysis" WHERE id NOT LIKE \'rk-%\'').fetchone()[0] == 0
    source_bis.close()


def test_seuls_les_dossiers_mis_a_jour_depuis_une_date_sont_lus(source, cible):
    dates = sorted(r[0] for r in source.execute('SELECT "updatedAt" FROM "Dossier"').fetchall())
    seuil = dates[len(dates) // 2]
    bilan = _lire(source, cible, depuis=seuil)
    assert bilan['dossiers'] == sum(1 for d in dates if d >= seuil) < len(dates)


def test_un_dossier_ecarte_reste_ecarte(source, cible):
    source_bis = sqlite3.connect(':memory:')
    source.backup(source_bis)
    ref = source_bis.execute('SELECT ref FROM "Dossier" ORDER BY ref LIMIT 1').fetchone()[0]
    source_bis.execute('UPDATE "Dossier" SET actif = 0 WHERE ref = ?', (ref,))
    _lire(source_bis, cible)
    assert cible.execute('SELECT actif FROM "Dossier" WHERE ref = ?', (ref,)).fetchone()[0] == 0
    assert cible.execute('SELECT actif FROM c0_dossier_brut WHERE ref = ?', (ref,)).fetchone()[0] == 0
    source_bis.close()


# ---- forme du dossier remis ----------------------------------------------------------------------------------------

def test_la_derniere_analyse_porte_les_controles_de_la_plus_recente(cible):
    src = _base(':memory:')
    src.execute('INSERT INTO "Dossier" (id, ref, "createdAt", "updatedAt") VALUES (\'d1\', \'ZZ-L-1\', ?, ?)', (T0, T0))
    for ident, debut in (('a-ancienne', '2026-11-01T00:00:00.000Z'), ('a-recente', '2026-11-20T00:00:00.000Z')):
        src.execute('INSERT INTO "Analysis" (id, "dossierId", "matrixVersion", "engineVersion", trigger, status, '
                    '"startedAt") VALUES (?, \'d1\', \'m\', \'e\', \'INTAKE\', \'COMPLETE\', ?)', (ident, debut))
        src.execute('INSERT INTO "AnalysisControl" (id, "analysisId", "dossierId", "controlId", applicable, '
                    '"applicabilityReason", outcome, missing, source, "computedAt") '
                    'VALUES (?, ?, \'d1\', \'IDT-01\', 1, \'\', \'CONFORME\', \'[]\', \'moteur\', ?)',
                    ('c-' + ident, ident, debut))
    (detail,) = ld.dossiers(src)
    assert detail['latestAnalysis']['id'] == 'a-recente'
    assert [c['id'] for c in detail['latestAnalysis']['controls']] == ['c-a-recente']
    assert detail['latestAnalysis']['controls'][0]['applicable'] is True
    assert [a['id'] for a in detail['analyses']] == ['a-ancienne', 'a-recente']
    assert detail['pieces'] == [] and detail['reanalyses'] == []
    src.close()


def test_les_valeurs_de_postgresql_prennent_la_forme_de_l_api():
    heure = datetime.datetime(2026, 11, 13, 10, 0, 0, 123456)
    assert ld.valeur(heure, 'date') == '2026-11-13T10:00:00.123Z'
    decalee = datetime.datetime(2026, 11, 13, 11, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    assert ld.valeur(decalee, 'date') == '2026-11-13T10:00:00.000Z'
    assert ld.valeur('2026-11-13T10:00:00.000Z', 'date') == '2026-11-13T10:00:00.000Z'
    assert ld.valeur(1, 'booleen') is True and ld.valeur(False, 'booleen') is False
    assert ld.valeur('{"a": 1}', 'json') == {'a': 1} and ld.valeur({'a': 1}, 'json') == {'a': 1}
    assert ld.valeur('["x"]', 'liste') == ['x'] and ld.valeur(['x'], 'liste') == ['x']
    assert ld.valeur(None, 'liste') is None and ld.valeur(None, 'date') is None


def test_les_types_suivent_schema_prisma():
    import lire_prisma
    with open(os.path.join(STRUCTURE, 'schema', 'schema.prisma'), encoding='utf-8') as f:
        schema = lire_prisma.lire(f.read())
    attendu = {'booleen': set(), 'json': set(), 'liste': set(), 'date': set()}
    for modele in schema.modeles.values():
        if modele.table not in TABLES_MIROIR:
            continue
        for champ in modele.colonnes():
            sorte = ('liste' if champ.liste else {'Boolean': 'booleen', 'Json': 'json', 'DateTime': 'date'}.get(champ.type))
            if sorte:
                attendu[sorte].add((modele.table, champ.colonne or champ.nom))
    assert {k: set(v) for k, v in ld.TYPES.items()} == attendu


# ---- sûreté --------------------------------------------------------------------------------------------------------

def test_un_dossier_illisible_est_compte_sans_rien_citer(source, cible, capsys):
    source_bis = sqlite3.connect(':memory:')
    source.backup(source_bis)
    ref = source_bis.execute('SELECT ref FROM "Dossier" ORDER BY ref LIMIT 1').fetchone()[0]
    source_bis.execute('PRAGMA ignore_check_constraints = ON')
    source_bis.execute('UPDATE "Dossier" SET "analysisStatus" = \'INCONNU\' WHERE ref = ?', (ref,))
    bilan = _lire(source_bis, cible)
    assert bilan['miroir_refuse'] == 1 and bilan['dossiers'] == len(miroir(source)['Dossier'])
    sortie = capsys.readouterr()
    assert ref not in sortie.out + sortie.err
    source_bis.close()


def test_sans_adresse_de_la_base_le_lecteur_s_arrete_sans_rien_citer(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('CARTE_SOURCE_PG', raising=False)
    assert ld.main(['--base', str(tmp_path / 'carte.sqlite')]) == 2
    assert 'CARTE_SOURCE_PG' in capsys.readouterr().err


def test_l_adresse_de_la_base_n_apparait_jamais_dans_une_erreur(tmp_path, capsys, monkeypatch):
    adresse = 'host=127.0.0.1 port=1 dbname=zzbase user=zzcompte password=zzsecret connect_timeout=1'
    monkeypatch.setenv('CARTE_SOURCE_PG', adresse)
    assert ld.main(['--base', str(tmp_path / 'carte.sqlite')]) == 1
    sortie = capsys.readouterr()
    for morceau in ('zzbase', 'zzcompte', 'zzsecret', '127.0.0.1'):
        assert morceau not in sortie.out + sortie.err


# ---- PostgreSQL réel (base d'essai vide, désignée par CARTE_PG_ESSAI) ----------------------------------------------

@pytest.mark.skipif(not os.environ.get('CARTE_PG_ESSAI'), reason='aucune base PostgreSQL d’essai')
def test_la_meme_lecture_sur_postgresql(source, cible):
    import psycopg
    with open(os.path.join(RACINE, 'schema', 'postgresql', '010_miroir_v2.sql'), encoding='utf-8') as f:
        ddl = f.read()
    with psycopg.connect(os.environ['CARTE_PG_ESSAI']) as pg:
        pg.execute('DROP SCHEMA IF EXISTS essai_lecteur CASCADE')
        pg.execute('CREATE SCHEMA essai_lecteur')
        pg.execute('SET search_path TO essai_lecteur')
        pg.execute(ddl)
        for table in ('Dossier', 'Piece', 'Analysis', 'AnalysisControl', 'Reanalysis'):
            curseur = source.execute(f'SELECT * FROM "{table}"')
            colonnes = [c[0] for c in curseur.description]
            for ligne in curseur.fetchall():
                valeurs = [ld.valeur(v, ld.sorte(table, c)) if ld.sorte(table, c) else v
                           for c, v in zip(colonnes, ligne)]
                valeurs = [psycopg.types.json.Jsonb(v) if ld.sorte(table, c) == 'json' and v is not None else v
                           for c, v in zip(colonnes, valeurs)]
                pg.execute(f'INSERT INTO "{table}" ({", ".join(chr(34) + c + chr(34) for c in colonnes)}) '
                           f'VALUES ({", ".join(["%s"] * len(colonnes))})', valeurs)
        pg.commit()
        _lire(pg, cible)
        pg.execute('DROP SCHEMA essai_lecteur CASCADE')
        pg.commit()
    assert miroir(cible) == miroir(source)
