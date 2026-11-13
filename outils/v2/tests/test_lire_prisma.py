"""Tests du lecteur de schema.prisma : un petit schéma fictif couvre chaque construction."""

import os
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
import lire_prisma  # noqa: E402

SCHEMA = '''
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

/// Genre de personne
enum Genre {
  PP
  PM  @map("personne_morale")

  @@map("genre_personne")
}

model Dossier {
  id        String   @id @default(uuid())
  /// Référence métier
  ref       String   @unique
  actif     Boolean  @default(true)
  genre     Genre?
  montant   Float?
  noms      String[]
  donnees   Json?
  creeLe    DateTime @default(now()) @map("cree_le")
  majLe     DateTime @updatedAt

  pieces    Piece[]

  @@index([genre])
  @@map("dossiers")
}

model Piece {
  id         String  @id @default(uuid())
  dossierId  String
  dossier    Dossier @relation(fields: [dossierId], references: [id], onDelete: Cascade)
  numero     Int     @default(0)
  type       String

  @@unique([dossierId, numero])
  @@index([dossierId, type])
}

model Lien {
  a  String
  b  String

  @@id([a, b])
}
'''


@pytest.fixture(scope='module')
def schema():
    return lire_prisma.lire(SCHEMA)


def test_generator_et_datasource_ignores(schema):
    assert set(schema.modeles) == {'Dossier', 'Piece', 'Lien'}
    assert set(schema.enums) == {'Genre'}


def test_enum_valeurs_et_map(schema):
    genre = schema.enums['Genre']
    assert [v.nom for v in genre.valeurs] == ['PP', 'PM']
    assert genre.valeurs[1].nom_base == 'personne_morale'
    assert genre.valeurs[0].nom_base == 'PP'
    assert genre.nom_base == 'genre_personne'
    assert genre.doc == 'Genre de personne'


def test_table_par_defaut_et_par_map(schema):
    assert schema.modeles['Dossier'].table == 'dossiers'
    assert schema.modeles['Piece'].table == 'Piece'


def test_champ_scalaire_et_attributs(schema):
    d = schema.modeles['Dossier']
    ident = d.champ('id')
    assert ident.type == 'String' and ident.cle_primaire and ident.defaut == 'uuid()'
    ref = d.champ('ref')
    assert ref.unique and not ref.facultatif and ref.doc == 'Référence métier'
    assert d.champ('actif').defaut == 'true'
    assert d.champ('montant').facultatif
    assert d.champ('noms').liste and not d.champ('noms').facultatif
    assert d.champ('majLe').mis_a_jour_auto


def test_map_de_colonne(schema):
    cree = schema.modeles['Dossier'].champ('creeLe')
    assert cree.colonne == 'cree_le'
    assert schema.modeles['Dossier'].champ('ref').colonne == 'ref'


def test_enum_reconnue_et_relation_reconnue(schema):
    d = schema.modeles['Dossier']
    assert d.champ('genre').enum and not d.champ('genre').relation
    assert d.champ('pieces').relation and d.champ('pieces').liste
    p = schema.modeles['Piece'].champ('dossier')
    assert p.relation
    assert p.relation_champs == ['dossierId'] and p.relation_references == ['id']
    assert p.relation_suppression == 'Cascade'


def test_colonnes_excluent_les_relations(schema):
    assert [c.nom for c in schema.modeles['Piece'].colonnes()] == ['id', 'dossierId', 'numero', 'type']


def test_contraintes_de_modele(schema):
    p = schema.modeles['Piece']
    assert p.uniques == [['dossierId', 'numero']]
    assert p.index == [['dossierId', 'type']]
    assert schema.modeles['Dossier'].index == [['genre']]
    assert schema.modeles['Lien'].cle_primaire == ['a', 'b']
    assert schema.modeles['Dossier'].cle_primaire == ['id']


def test_attribut_inconnu_refuse():
    with pytest.raises(lire_prisma.ErreurPrisma):
        lire_prisma.lire('model X {\n  id String @id @inconnu\n}\n')


def test_bloc_non_ferme_refuse():
    with pytest.raises(lire_prisma.ErreurPrisma):
        lire_prisma.lire('model X {\n  id String @id\n')


def test_type_inconnu_refuse():
    with pytest.raises(lire_prisma.ErreurPrisma):
        lire_prisma.lire('model X {\n  id Truc @id\n}\n')


SCHEMA_KAMAL = os.path.join(RACINE, 'import', 'kamal_structure', 'schema', 'schema.prisma')


@pytest.mark.skipif(not os.path.exists(SCHEMA_KAMAL), reason='structure de Kamal absente')
def test_schema_de_kamal_lu_entierement():
    with open(SCHEMA_KAMAL, encoding='utf-8') as f:
        s = lire_prisma.lire(f.read())
    assert 'Dossier' in s.modeles and 'BlacklistEntry' in s.modeles
    assert s.modeles['Piece'].uniques == [['dossierId', 'upstreamPieceId']]
    assert 'COMPLETE' in [v.nom for v in s.enums['AnalysisStatus'].valeurs]


def test_type_natif_db():
    s = lire_prisma.lire('model Budget {\n  jour DateTime @id @db.Date\n  total Float\n}\n')
    jour = s.modeles['Budget'].champ('jour')
    assert jour.type_natif == 'Date' and jour.cle_primaire
    assert s.modeles['Budget'].champ('total').type_natif is None
