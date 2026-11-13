"""Tests du lecteur des types TypeScript de Kamal : un petit extrait fictif couvre chaque construction."""

import os
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
import lire_types_ts  # noqa: E402

TYPES = '''
import type {
  Genre,
  Statut,
} from '@exemple/moteur';

/** Statut d'un dossier. */
export type Etat = 'OUVERT' | 'CLOS'; // commentaire de fin de ligne

export type Couleur =
  | 'ROUGE'
  | 'VERT';

export type Action =
  | { kind: 'ARRET' }
  | { kind: 'REPRISE'; motif?: string };

export interface Base {
  id: string;
  /** Référence métier, « ZZ » dans le fictif. */
  ref: string;
}

export interface Dossier extends Base {
  genre: Genre | null;
  canal: 'PHYSIQUE' | 'DIGITAL' | null;
  montant?: number;
  noms: string[];
  champs: Record<string, unknown>;
  compteurs: {
    statut: Record<string, number>;
    total: number;
  };
  etat: Etat;
}
'''


@pytest.fixture(scope='module')
def types():
    return lire_types_ts.lire(TYPES)


def test_importations(types):
    assert types.importations == {'Genre': '@exemple/moteur', 'Statut': '@exemple/moteur'}


def test_union_de_chaines_est_une_enumeration(types):
    assert types.enumerations['Etat'] == ['OUVERT', 'CLOS']
    assert types.enumerations['Couleur'] == ['ROUGE', 'VERT']


def test_alias_non_enumeration_garde_son_texte(types):
    assert 'Action' not in types.enumerations
    assert "kind: 'REPRISE'" in types.alias['Action']


def test_interface_champs_et_heritage(types):
    d = types.interfaces['Dossier']
    assert d.parents == ['Base']
    assert [c.nom for c in d.champs] == ['genre', 'canal', 'montant', 'noms', 'champs', 'compteurs', 'etat']
    assert d.champ('montant').facultatif and not d.champ('genre').facultatif


def test_types_de_champ(types):
    d = types.interfaces['Dossier']
    assert d.champ('genre').type == 'Genre | null' and d.champ('genre').nullable
    assert d.champ('canal').valeurs == ['PHYSIQUE', 'DIGITAL']
    assert d.champ('noms').type == 'string[]'
    assert d.champ('champs').type == 'Record<string, unknown>'
    assert d.champ('etat').references == ['Etat']
    assert d.champ('genre').references == ['Genre']


def test_objet_imbrique(types):
    compteurs = types.interfaces['Dossier'].champ('compteurs')
    assert [c.nom for c in compteurs.sous_champs] == ['statut', 'total']


def test_documentation_de_champ(types):
    assert 'Référence métier' in types.interfaces['Base'].champ('ref').doc


def test_champs_herites(types):
    assert [c.nom for c in types.champs_complets('Dossier')][:2] == ['id', 'ref']


def test_declaration_illisible_refusee():
    with pytest.raises(lire_types_ts.ErreurTypes):
        lire_types_ts.lire('export interface X {\n  a: string;\n')


FICHIERS_KAMAL = [os.path.join(RACINE, 'import', 'kamal_structure', 'types', n)
                  for n in ('web_types.ts', 'engine-core_types.ts')]


@pytest.mark.skipif(not all(os.path.exists(f) for f in FICHIERS_KAMAL), reason='structure de Kamal absente')
def test_types_de_kamal_lus_entierement():
    web = lire_types_ts.lire(open(FICHIERS_KAMAL[0], encoding='utf-8').read())
    moteur = lire_types_ts.lire(open(FICHIERS_KAMAL[1], encoding='utf-8').read())
    assert 'DossierDetail' in web.interfaces and web.interfaces['DossierDetail'].parents == ['Dossier']
    assert len(moteur.enumerations['PieceType']) == 14
    assert 'COMPLETE' in moteur.enumerations['AnalysisStatus']
