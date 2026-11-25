"""Export Excel des données des dossiers EQDOM (tables af_* de la base de la carte), demandé par le comité de direction
(Lounès, 25/11/2026). Une feuille par table, CIN et RIB masqués par défaut, aucune formule exécutable, console en
comptages seulement ; données réelles : lancé par Lounès seul, fichier rangé hors du dépôt."""
import os
import sqlite3
import sys

import openpyxl
import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'pipeline')]

import charger_antifraude  # noqa: E402
from outils import exporter_dossiers_excel as ex  # noqa: E402


@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / 'carte_kit.sqlite'
    cx = sqlite3.connect(str(chemin))
    cx.executescript(charger_antifraude.SCHEMA)
    colonnes = [r[1] for r in cx.execute('PRAGMA table_info(af_dossier)')]
    for k in range(7):
        ligne = {c: None for c in colonnes}
        ligne.update(ref=f'ZZD{k:04d}', lot='prod')
        cx.execute(f'INSERT INTO af_dossier ({", ".join(ligne)}) VALUES ({", ".join("?" * len(ligne))})', list(ligne.values()))
    pcols = [r[1] for r in cx.execute('PRAGMA table_info(af_personne)')]
    for k in range(3):
        ligne = {c: None for c in pcols}
        ligne.update(af_personne_id=k, dossier_ref='ZZD0000', role='demandeur', nom='ZZNAKOU', prenom='ZZSALI',
                     cin_brut=f'ZZ12345{k}', cin_norm=f'ZZ12345{k}', adresse='=HYPERLINK("http://exemple.invalid")')
        cx.execute(f'INSERT INTO af_personne ({", ".join(ligne)}) VALUES ({", ".join("?" * len(ligne))})', list(ligne.values()))
    cx.execute("INSERT INTO af_compte (af_compte_id, dossier_ref, rib, banque) VALUES "
               "(1, 'ZZD0001', '999000111122223333444455', 'BANQUE ZZ')")
    cx.commit()
    cx.close()
    return str(chemin)


def _classeur(chemin):
    return openpyxl.load_workbook(chemin, read_only=True)


def test_une_feuille_par_table_des_dossiers_avec_toutes_les_lignes(base, tmp_path):
    sortie = str(tmp_path / 'dossiers.xlsx')
    comptes = ex.exporter(base, sortie)
    assert comptes['Dossiers'] == 7 and comptes['Personnes'] == 3 and comptes['Comptes bancaires'] == 1
    wb = _classeur(sortie)
    assert wb.sheetnames[0] == 'Lisez-moi' and set(ex.FEUILLES.values()) <= set(wb.sheetnames)
    lignes = list(wb['Dossiers'].iter_rows(values_only=True))
    assert lignes[0][0] == 'ref' and len(lignes) == 8


def test_cin_et_rib_sont_masques_par_defaut(base, tmp_path):
    sortie = str(tmp_path / 'dossiers.xlsx')
    ex.exporter(base, sortie)
    wb = _classeur(sortie)
    texte = repr([list(f.iter_rows(values_only=True)) for f in wb.worksheets])
    assert 'ZZ123450' not in texte and '999000111122223333444455' not in texte
    assert ex.masquer('ZZ123450') == 'ZZ****50' and ex.masquer('999000111122223333444455').startswith('999')
    assert 'ZZNAKOU' in texte, 'les noms restent : le comité les demande ; seuls les identifiants sont masqués'


def test_identifiants_complets_sur_demande(base, tmp_path):
    sortie = str(tmp_path / 'dossiers.xlsx')
    ex.exporter(base, sortie, masques=False)
    texte = repr(list(_classeur(sortie)['Personnes'].iter_rows(values_only=True)))
    assert 'ZZ123450' in texte


def test_aucune_valeur_ne_devient_une_formule(base, tmp_path):
    sortie = str(tmp_path / 'dossiers.xlsx')
    ex.exporter(base, sortie)
    wb = openpyxl.load_workbook(sortie)
    for cellule in (c for ligne in wb['Personnes'].iter_rows() for c in ligne):
        assert cellule.data_type != 'f'


def test_la_console_ne_montre_que_des_comptages(base, tmp_path, capsys):
    ex.exporter(base, str(tmp_path / 'dossiers.xlsx'), afficher=True)
    sortie = capsys.readouterr().out
    assert 'Dossiers : 7' in sortie and 'ZZ' not in sortie


def test_garde_fou_et_fichier_hors_du_depot(base, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('CARTE_DONNEES_REELLES', raising=False)
    assert ex.main(['--base', base, '--sortie', str(tmp_path / 'd.xlsx')]) == 2
    assert 'CARTE_DONNEES_REELLES' in capsys.readouterr().err
    assert ex.main(['--base', base, '--sortie', os.path.join(RACINE, 'jeu_essai', 'sortie', 'zz.xlsx')]) == 2
    assert 'hors du dépôt' in capsys.readouterr().err
    assert not (tmp_path / 'd.xlsx').exists()
