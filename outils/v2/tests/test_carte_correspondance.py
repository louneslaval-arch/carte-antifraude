"""Tests de la carte de correspondance v2 → base : partie générée, partie écrite à la main conservée, dérive."""

import os
import shutil
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
import carte_correspondance as carte  # noqa: E402

PRISMA = '''
enum Statut {
  OUVERT
  CLOS
}

model Dossier {
  id     String  @id @default(uuid())
  ref    String  @unique
  statut Statut
  creeLe DateTime @map("cree_le")
  pieces Piece[]

  @@map("dossiers")
}

model Piece {
  id        String  @id
  dossierId String
  dossier   Dossier @relation(fields: [dossierId], references: [id])
  fields    Json
}
'''

WEB = '''
export type Statut = 'OUVERT' | 'CLOS' | 'ARCHIVE';

export interface Dossier {
  ref: string;
  statut: Statut;
}
'''

MOTEUR = '''
export type Genre = 'PP' | 'PM';
'''

README = '''# Lot fictif

## 4. pieces

L'inventaire est dans **`reference/inventaire.csv`** (4 dossiers). Table de correspondance amont → moteur : `nom_societe→denomination_sociale`, `numero_cin|numero_cin_gerant→cin`.

## 7. Pour faire la base

- tables enfants : `releve_mois` (piece, mois) → `releve_operation` (libelle) ; `societe_personne` (piece, role).
'''


@pytest.fixture
def structure(tmp_path):
    s = tmp_path / 'structure'
    (s / 'schema').mkdir(parents=True)
    (s / 'types').mkdir()
    (s / 'schema' / 'schema.prisma').write_text(PRISMA, encoding='utf-8')
    (s / 'types' / 'web_types.ts').write_text(WEB, encoding='utf-8')
    (s / 'types' / 'engine-core_types.ts').write_text(MOTEUR, encoding='utf-8')
    (s / 'README.md').write_text(README, encoding='utf-8')
    return s


def test_chaque_colonne_du_miroir_est_listee(structure):
    texte = carte.generer(str(structure))
    assert '| `dossiers` | `creeLe` | `cree_le` |' in texte
    assert '| `Piece` | `dossierId` | `dossierId` |' in texte
    # une relation n'est pas une colonne
    assert '`pieces`' in texte and 'relation, pas de colonne' in texte


def test_enumerations_et_ecarts_entre_prisma_et_types(structure):
    texte = carte.generer(str(structure))
    assert '`Statut`' in texte and 'OUVERT, CLOS' in texte
    assert 'ARCHIVE' in texte and 'écart' in texte


def test_vocabulaire_amont_moteur(structure):
    texte = carte.generer(str(structure))
    assert '| `nom_societe` | `denomination_sociale` |' in texte
    assert '| `numero_cin`, `numero_cin_gerant` | `cin` |' in texte
    assert 'inventaire' not in texte.split('Vocabulaire amont')[1]


def test_tables_enfants_du_readme(structure):
    texte = carte.generer(str(structure))
    for t in ('releve_mois', 'releve_operation', 'societe_personne'):
        assert f'`{t}`' in texte


def test_couverture_complete(structure):
    texte = carte.generer(str(structure))
    assert 'Couverture : 2 modèles, 9 champs, 1 énumérations de schema.prisma ; 100 %' in texte


def test_empreintes_des_fichiers_sources(structure):
    texte = carte.generer(str(structure))
    assert 'schema/schema.prisma' in texte and 'sha256' in texte


def test_partie_ecrite_a_la_main_conservee(structure, tmp_path):
    doc = tmp_path / 'correspondance.md'
    doc.write_text('# Titre\n\nNotre ajout justifié.\n\n' + carte.DEBUT + '\nvieux\n' + carte.FIN + '\n\nFin à la main.\n',
                   encoding='utf-8')
    carte.ecrire(str(structure), str(doc))
    texte = doc.read_text(encoding='utf-8')
    assert 'Notre ajout justifié.' in texte and 'Fin à la main.' in texte
    assert 'vieux' not in texte and '`dossiers`' in texte


def test_document_neuf_cree_avec_les_reperes(structure, tmp_path):
    doc = tmp_path / 'neuf.md'
    carte.ecrire(str(structure), str(doc))
    texte = doc.read_text(encoding='utf-8')
    assert carte.DEBUT in texte and carte.FIN in texte


def test_derive_detectee(structure, tmp_path):
    doc = tmp_path / 'correspondance.md'
    carte.ecrire(str(structure), str(doc))
    assert carte.a_jour(str(structure), str(doc))
    (structure / 'schema' / 'schema.prisma').write_text(PRISMA.replace('ref    String  @unique',
                                                                        'ref    String  @unique\n  note String?'),
                                                         encoding='utf-8')
    assert not carte.a_jour(str(structure), str(doc))


STRUCTURE_KAMAL = os.path.join(RACINE, 'import', 'kamal_structure')
DOC = os.path.join(RACINE, 'docs', 'correspondance_v2.md')


@pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE_KAMAL, 'schema', 'schema.prisma')),
                    reason='structure de Kamal absente')
def test_carte_du_depot_a_jour_avec_la_structure_de_kamal():
    # dérive : si le lot de Kamal change, ce test échoue jusqu'à `carte_correspondance.py --ecrire` relu
    assert carte.a_jour(STRUCTURE_KAMAL, DOC), 'carte de correspondance périmée : la régénérer et la relire'
