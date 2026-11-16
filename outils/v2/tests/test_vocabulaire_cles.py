"""Vocabulaire des clés par type de pièce : généré depuis l'inventaire de Kamal, sans valeur ni comptage."""
import os
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))

import vocabulaire_cles as vc  # noqa: E402


def inventaire(tmp_path, lignes):
    dossier = tmp_path / 'structure' / 'reference'
    dossier.mkdir(parents=True)
    (dossier / 'champs_par_type_prod.csv').write_text(
        'type,source,key,n,non_null,types_json\n' + '\n'.join(lignes) + '\n', encoding='utf-8')
    return str(tmp_path / 'structure')


def test_une_liste_triee_de_cles_par_type_sans_comptage(tmp_path):
    structure = inventaire(tmp_path, ['CIN,AMONT,nom,86,86,string', 'CIN,REANALYSE,nom,3,3,string',
                                      'CIN,AMONT,cin,86,80,string', 'STATUTS,AMONT,gerants,4,4,array'])
    espace = {}
    exec(vc.generer(structure), espace)
    assert espace['VOCABULAIRE'] == {'CIN': ('cin', 'nom'), 'STATUTS': ('gerants',)}
    assert '86' not in repr(espace['VOCABULAIRE']) and len(espace['SHA256']) == 64


def test_derive_detectee_quand_l_inventaire_change(tmp_path):
    structure = inventaire(tmp_path, ['CIN,AMONT,nom,1,1,string'])
    sortie = str(tmp_path / 'vocabulaire.py')
    assert vc.main(['--verifier', '--structure', structure, '--sortie', sortie]) == 1
    assert vc.main(['--ecrire', '--structure', structure, '--sortie', sortie]) == 0
    assert vc.main(['--verifier', '--structure', structure, '--sortie', sortie]) == 0
    with open(os.path.join(structure, 'reference', 'champs_par_type_prod.csv'), 'a', encoding='utf-8') as f:
        f.write('CIN,AMONT,prenom,1,1,string\n')
    assert vc.main(['--verifier', '--structure', structure, '--sortie', sortie]) == 1


def test_fichier_versionne_a_jour_avec_l_inventaire_de_kamal():
    if not os.path.exists(os.path.join(vc.STRUCTURE_DEFAUT, vc.INVENTAIRE)):
        pytest.skip('inventaire de Kamal absent')
    assert vc.a_jour(vc.STRUCTURE_DEFAUT, vc.SORTIE_DEFAUT)
