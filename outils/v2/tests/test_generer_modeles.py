"""Tests du générateur de modèles d'échange pydantic depuis les types TypeScript de Kamal (étape C.1)."""

import importlib.util
import os
import sys

import pydantic
import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'v2'))
import generer_modeles  # noqa: E402

WEB = '''
import type { Genre } from '@exemple/moteur';

export type Etat = 'OUVERT' | 'CLOS';

export interface Base {
  id: string;
  ref: string;
}

export interface Libre {
  version: string;
  [cle: string]: unknown;
}

export interface Piece {
  type: string;
  fields: Record<string, unknown>;
}

export interface Dossier extends Base {
  genre: Genre | null;
  etat: Etat;
  canal: 'PHYSIQUE' | 'DIGITAL' | null;
  force: 'forte' | 'faible' | string;
  montant?: number;
  total: number;
  actif: boolean;
  noms: string[];
  pieces: Piece[];
  json: string;
  compteurs: {
    statut: Record<string, number>;
  };
  relecture: { avant?: Record<string, unknown>; apres?: Record<string, unknown> } | null;
}
'''

MOTEUR = '''
export type Genre = 'PP' | 'PM';
'''


@pytest.fixture(scope='module')
def module(tmp_path_factory):
    code = generer_modeles.generer(WEB, MOTEUR)
    chemin = tmp_path_factory.mktemp('modeles') / 'modeles_essai.py'
    chemin.write_text(code, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('modeles_essai', chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dossier(**modif):
    d = {'id': 'u1', 'ref': 'ZZ000001', 'genre': 'PP', 'etat': 'OUVERT', 'canal': None, 'force': 'autre',
         'total': 3, 'actif': True, 'noms': ['A'], 'pieces': [{'type': 'CIN', 'fields': {'cin': 'ZZ000001'}}],
         'json': 'x', 'compteurs': {'statut': {'OUVERT': 1}}, 'relecture': None}
    d.update(modif)
    return d


def test_dossier_bien_forme_accepte_et_restitue_a_l_identique(module):
    d = dossier()
    m = module.Dossier.model_validate(d)
    assert m.model_dump(by_alias=True, exclude_unset=True) == d
    assert isinstance(m.model_dump(by_alias=True)['total'], int)  # un entier reste un entier


@pytest.mark.parametrize('modif', [
    {'etat': 'INCONNU'},           # valeur d'énumération hors des types de Kamal
    {'genre': 'pp'},                # casse changée
    {'canal': 'WEB'},
    {'actif': 'oui'},
    {'noms': 'A'},
    {'pieces': [{'type': 'CIN'}]},  # champ obligatoire manquant dans un objet contenu
    {'champ_inconnu': 1},           # champ absent des types
    {'compteurs': {'statut': {'OUVERT': 'un'}}},
    {'total': '3'},                 # un nombre en texte n'est pas un nombre
    {'total': True},
    {'actif': 1},
    {'actif': 'true'},
])
def test_dossier_mal_forme_refuse(module, modif):
    with pytest.raises(pydantic.ValidationError):
        module.Dossier.model_validate(dossier(**modif))


def test_champ_obligatoire_mais_nullable(module):
    d = dossier()
    del d['genre']
    with pytest.raises(pydantic.ValidationError):
        module.Dossier.model_validate(d)


def test_champ_facultatif(module):
    assert module.Dossier.model_validate(dossier(montant=12.5)).montant == 12.5
    assert module.Dossier.model_validate(dossier()).montant is None


def test_signature_d_index_admet_des_cles_libres(module):
    assert module.Libre.model_validate({'version': '1', 'autre': 2}).model_extra == {'autre': 2}
    with pytest.raises(pydantic.ValidationError):
        module.Libre.model_validate({'autre': 2})


def test_heritage(module):
    assert issubclass(module.Dossier, module.Base)


def test_nom_reserve_par_pydantic_garde_son_nom_json(module):
    m = module.Dossier.model_validate(dossier(json='valeur'))
    assert m.model_dump(by_alias=True)['json'] == 'valeur'


def test_union_ouverte_de_chaines_accepte_toute_chaine(module):
    assert module.Dossier.model_validate(dossier(force='inattendue')).force == 'inattendue'


def test_type_inconnu_refuse_a_la_generation():
    with pytest.raises(generer_modeles.ErreurModeles):
        generer_modeles.generer('export interface X {\n  a: Map<string, string>;\n}\n', '')


def test_reference_introuvable_refusee_a_la_generation():
    with pytest.raises(generer_modeles.ErreurModeles):
        generer_modeles.generer('export interface X {\n  a: Inconnu;\n}\n', '')


TYPES_KAMAL = os.path.join(RACINE, 'import', 'kamal_structure', 'types')


@pytest.mark.skipif(not os.path.exists(os.path.join(TYPES_KAMAL, 'web_types.ts')), reason='structure de Kamal absente')
def test_modeles_du_depot_a_jour_avec_les_types_de_kamal():
    # dérive : si web_types.ts change, ce test échoue jusqu'à `generer_modeles.py --ecrire`
    assert generer_modeles.a_jour(TYPES_KAMAL), 'pipeline/modeles_v2.py périmé : le régénérer'


@pytest.mark.skipif(not os.path.exists(os.path.join(TYPES_KAMAL, 'web_types.ts')), reason='structure de Kamal absente')
def test_modeles_champ_par_champ_comme_les_types_de_kamal():
    import lire_types_ts
    sys.path.insert(0, RACINE)
    from pipeline import modeles_v2
    web = lire_types_ts.lire(open(os.path.join(TYPES_KAMAL, 'web_types.ts'), encoding='utf-8').read())
    for nom in web.interfaces:
        modele = getattr(modeles_v2, nom)
        attendus = {c.nom: c.facultatif for c in web.champs_complets(nom) if c.nom != '[index]'}
        obtenus = {(f.alias or n): not f.is_required() for n, f in modele.model_fields.items()}
        assert obtenus == attendus, nom
