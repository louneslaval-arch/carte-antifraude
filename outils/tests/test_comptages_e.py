"""Tests du script de comptage de l'étape E (sortie : comptages seulement, jamais une valeur lue)."""
import json
import os
import re
import sqlite3
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
SCRIPT = os.path.join(RACINE, 'outils', 'comptages_e.py')
sys.path.insert(0, os.path.join(RACINE, 'jeu_essai', 'v2'))

import generer_dossiers as gd  # noqa: E402


def fichiers(tmp_path, n=6):
    jeu = gd.generer(n_dossiers=300, n_societes=300, graine=20261113)
    chemins = []
    for k, d in enumerate(jeu.dossiers[:n]):
        p = tmp_path / f'dossier_{k}.json'
        p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        chemins.append(str(p))
    return jeu, chemins


def lancer(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def nombre(sortie, libelle):
    return int(re.search(rf'^{re.escape(libelle)} : (\d+)', sortie, re.M).group(1))


def test_comptages_egaux_au_contenu_de_la_base_construite(tmp_path):
    _, chemins = fichiers(tmp_path)
    base = str(tmp_path / 'essai.sqlite')
    r = lancer('--base', base, *chemins)
    assert r.returncode == 0, r.stderr
    cx = sqlite3.connect(base)
    un = lambda sql: cx.execute(sql).fetchone()[0]  # noqa: E731
    assert nombre(r.stdout, 'dossiers lus') == 6 == un('SELECT count(*) FROM "Dossier"')
    assert nombre(r.stdout, 'valeurs') == un('SELECT count(*) FROM c1_fait') > 0
    assert nombre(r.stdout, 'valeurs retenues') == un('SELECT count(*) FROM c1_fait_retenu') > 0
    assert nombre(r.stdout, 'opérations lues') == un("SELECT count(*) FROM c1_releve_operation WHERE nature = 'lue'")
    assert nombre(r.stdout, 'opérations reconstituées') == \
        un("SELECT count(*) FROM c1_releve_operation WHERE nature = 'reconstituee_amont'")
    assert nombre(r.stdout, 'mentions de personnes (rôles du 11/11)') == un(
        "SELECT count(*) FROM c1_mention_personne WHERE role NOT IN ('titulaire_compte', 'titulaire_quittance')")
    assert nombre(r.stdout, 'mentions de personnes (toutes)') == un('SELECT count(*) FROM c1_mention_personne')


def test_sortie_sans_aucune_valeur_lue(tmp_path):
    jeu, chemins = fichiers(tmp_path)
    r = lancer('--base', str(tmp_path / 'essai.sqlite'), *chemins)
    sortie = r.stdout + r.stderr
    assert 'ZZ' not in sortie and '999' not in sortie
    for d in jeu.dossiers[:6]:
        assert d['clientName'] not in sortie


def test_fichier_illisible_compte_sans_detail_et_code_d_erreur(tmp_path):
    _, chemins = fichiers(tmp_path, n=2)
    mauvais = tmp_path / 'ZZ_mauvais.json'
    mauvais.write_text('{"ref": "ZZ-SECRET", pas du json', encoding='utf-8')
    r = lancer('--base', str(tmp_path / 'essai.sqlite'), *chemins, str(mauvais))
    assert r.returncode == 1
    assert nombre(r.stdout, 'fichiers illisibles') == 1 and nombre(r.stdout, 'dossiers lus') == 2
    assert 'ZZ' not in r.stdout + r.stderr


def test_refuse_une_base_qui_existe_deja(tmp_path):
    _, chemins = fichiers(tmp_path, n=1)
    base = tmp_path / 'essai.sqlite'
    base.write_text('', encoding='utf-8')
    r = lancer('--base', str(base), *chemins)
    assert r.returncode == 2 and 'ZZ' not in r.stdout + r.stderr
