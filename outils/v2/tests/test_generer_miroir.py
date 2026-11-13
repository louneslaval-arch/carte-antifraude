"""Tests du générateur du miroir de la v2 (étape D.2) : migrations SQL produites depuis schema.prisma."""

import os
import sqlite3
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
import generer_miroir  # noqa: E402
import lire_prisma  # noqa: E402

PRISMA = '''
enum Statut {
  OUVERT
  CLOS
}

model Dossier {
  id        String   @id @default(uuid())
  ref       String   @unique
  actif     Boolean  @default(true)
  statut    Statut   @default(OUVERT)
  genre     Statut?
  montant   Float?
  essais    Int      @default(0)
  noms      String[]
  donnees   Json?
  creeLe    DateTime @default(now()) @map("cree_le")
  jour      DateTime? @db.Date
  pieces    Piece[]

  @@index([statut])
  @@map("dossiers")
}

model Piece {
  id        String  @id
  dossierId String
  dossier   Dossier @relation(fields: [dossierId], references: [id], onDelete: Cascade)
  numero    Int
  fields    Json

  @@unique([dossierId, numero])
}
'''


@pytest.fixture
def base():
    cx = sqlite3.connect(':memory:')
    cx.execute('PRAGMA foreign_keys = ON')
    cx.executescript(generer_miroir.sql(PRISMA, 'sqlite'))
    return cx


def colonnes(cx, table):
    return {r[1]: r for r in cx.execute(f'PRAGMA table_info("{table}")')}


def test_tables_et_colonnes_aux_noms_de_la_base_de_kamal(base):
    tables = {r[0] for r in base.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {'dossiers', 'Piece'}
    assert list(colonnes(base, 'dossiers')) == ['id', 'ref', 'actif', 'statut', 'genre', 'montant', 'essais', 'noms',
                                                'donnees', 'cree_le', 'jour']
    assert list(colonnes(base, 'Piece')) == ['id', 'dossierId', 'numero', 'fields']      # la relation n'est pas une colonne


def test_cles_obligations_et_valeurs_par_defaut(base):
    c = colonnes(base, 'dossiers')
    assert c['id'][5] == 1 and c['ref'][3] == 1 and c['montant'][3] == 0          # clé primaire, NOT NULL, facultatif
    base.execute("INSERT INTO dossiers (id, ref, noms, cree_le) VALUES ('a', 'ZZ1', '[]', '2026-01-01')")
    assert base.execute('SELECT actif, statut, essais FROM dossiers').fetchone() == (1, 'OUVERT', 0)


def test_unicite_simple_et_composee(base):
    base.execute("INSERT INTO dossiers (id, ref, noms, cree_le) VALUES ('a', 'ZZ1', '[]', '2026-01-01')")
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO dossiers (id, ref, noms, cree_le) VALUES ('b', 'ZZ1', '[]', '2026-01-01')")
    base.execute("INSERT INTO Piece VALUES ('p1', 'a', 1, '{}')")
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO Piece VALUES ('p2', 'a', 1, '{}')")


@pytest.mark.parametrize('colonne, valeur', [('statut', 'INCONNU'), ('genre', 'ouvert'), ('actif', 2)])
def test_enumerations_et_booleens_controles(base, colonne, valeur):
    with pytest.raises(sqlite3.IntegrityError):
        base.execute(f"INSERT INTO dossiers (id, ref, noms, cree_le, {colonne}) VALUES ('a', 'ZZ1', '[]', '2026', ?)",
                     (valeur,))


def test_enumeration_facultative_admet_le_vide(base):
    base.execute("INSERT INTO dossiers (id, ref, noms, cree_le, genre) VALUES ('a', 'ZZ1', '[]', '2026', NULL)")


def test_cle_etrangere_et_suppression_en_cascade(base):
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO Piece VALUES ('p1', 'absent', 1, '{}')")
    base.execute("INSERT INTO dossiers (id, ref, noms, cree_le) VALUES ('a', 'ZZ1', '[]', '2026-01-01')")
    base.execute("INSERT INTO Piece VALUES ('p1', 'a', 1, '{}')")
    base.execute("DELETE FROM dossiers WHERE id = 'a'")
    assert base.execute('SELECT count(*) FROM Piece').fetchone()[0] == 0


def test_index_crees(base):
    index = {r[0] for r in base.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")}
    assert index == {'dossiers_statut_idx'}


def test_version_postgresql(base):
    texte = generer_miroir.sql(PRISMA, 'postgresql')
    for attendu in ('"donnees" JSONB', '"noms" TEXT[] NOT NULL', '"cree_le" TIMESTAMP(3) NOT NULL', '"jour" DATE',
                    '"actif" BOOLEAN NOT NULL DEFAULT true', '"montant" DOUBLE PRECISION',
                    'CHECK ("statut" IN (\'OUVERT\', \'CLOS\'))', 'REFERENCES "dossiers" ("id") ON DELETE CASCADE'):
        assert attendu in texte, attendu


def test_dialecte_inconnu_refuse():
    with pytest.raises(ValueError):
        generer_miroir.sql(PRISMA, 'oracle')


SCHEMA_KAMAL = os.path.join(RACINE, 'import', 'kamal_structure', 'schema', 'schema.prisma')
kamal = pytest.mark.skipif(not os.path.exists(SCHEMA_KAMAL), reason='structure de Kamal absente')


@kamal
def test_miroir_contient_chaque_modele_et_chaque_champ_de_kamal_et_rien_d_autre():
    with open(SCHEMA_KAMAL, encoding='utf-8') as f:
        texte = f.read()
    schema = lire_prisma.lire(texte)
    cx = sqlite3.connect(':memory:')
    cx.executescript(generer_miroir.sql(texte, 'sqlite'))
    tables = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {m.table for m in schema.modeles.values()} and len(tables) == 13
    for m in schema.modeles.values():
        assert list(colonnes(cx, m.table)) == [c.colonne for c in m.colonnes()], m.nom


@kamal
def test_migrations_du_depot_a_jour_avec_la_structure_de_kamal():
    # dérive : si schema.prisma change, ce test échoue jusqu'à `generer_miroir.py --ecrire` relu
    assert generer_miroir.a_jour(SCHEMA_KAMAL), 'miroir périmé : écrire une nouvelle migration'
