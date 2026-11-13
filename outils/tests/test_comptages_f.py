"""Tests du script de comptage de l'étape F (sortie : comptages seulement, aucun groupe de moins de 5)."""
import os
import re
import sqlite3
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
SCRIPT = os.path.join(RACINE, 'outils', 'comptages_f.py')
sys.path[:0] = [os.path.join(RACINE, 'jeu_essai', 'v2'), os.path.join(RACINE, 'outils')]

import generer_dossiers as gd  # noqa: E402


@pytest.fixture(scope='module')
def kit(tmp_path_factory):
    d = tmp_path_factory.mktemp('kit')
    g = gd.generer(n_dossiers=300, n_societes=300, graine=20261113).monde
    gd.ecrire_csv(str(d / 'liste_noire.csv'), g.bl, gd.COLONNES_BL)
    gd.ecrire_csv(str(d / 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    gd.ecrire_csv(str(d / 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'construire_base.py'),
                        '--liste-noire', str(d / 'liste_noire.csv'), '--rc-annonces', str(d / 'rc_annonces.csv'),
                        '--rc-personnes', str(d / 'rc_personnes.csv'), '--base', str(d / 'socle.sqlite')],
                       capture_output=True, text=True)
    assert r.returncode == 0
    return str(d / 'socle.sqlite')


def lancer(*args, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)


def nombre(sortie, libelle):
    return int(re.search(rf'^{re.escape(libelle)} : (\d+)', sortie, re.M).group(1))


def test_comptages_egaux_au_contenu_de_la_base_et_aucune_valeur(kit, tmp_path):
    base = str(tmp_path / 'essai.sqlite')
    r = lancer('--base-kit', kit, '--base', base)
    assert r.returncode == 0, r.stderr
    cx, source = sqlite3.connect(base), sqlite3.connect(kit)
    un = lambda c, sql: c.execute(sql).fetchone()[0]  # noqa: E731
    assert nombre(r.stdout, 'inscrits du kit') == un(source, 'SELECT count(*) FROM bl_entite') == \
        nombre(r.stdout, 'inscrits rangés') == un(cx, 'SELECT count(*) FROM ref_liste_noire')
    assert nombre(r.stdout, 'fiches de personnes') == un(cx, 'SELECT count(*) FROM c2_personne')
    assert nombre(r.stdout, 'fiches de sociétés') == un(cx, 'SELECT count(*) FROM c2_societe')
    assert nombre(r.stdout, 'rapprochements du kit repris') == un(source, 'SELECT count(*) FROM correspondance_retenue')
    assert nombre(r.stdout, 'invariants en écart') == 0
    noms = [n for (n,) in source.execute('SELECT nom_affiche FROM bl_entite WHERE nom_affiche IS NOT NULL')]
    assert 'ZZ' not in r.stdout + r.stderr and not any(n in r.stdout for n in noms)


def test_groupe_de_moins_de_cinq_masque(kit, tmp_path):
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'essai.sqlite'))
    groupes = re.findall(r'^  (\S+) : (.+)$', r.stdout, re.M)
    assert groupes and any(v == '< 5' for _, v in groupes)
    assert all(v == '< 5' or int(v) >= 5 for _, v in groupes)


def test_echec_classe_seulement_et_base_refusee(kit, tmp_path, monkeypatch, capsys):
    import comptages_f
    monkeypatch.setattr(comptages_f.c2_identites, 'charger_socle',
                        lambda cx, chemin: (_ for _ in ()).throw(ValueError('ZZ-SECRET')))
    assert comptages_f.main(['--base-kit', kit, '--base', str(tmp_path / 'a.sqlite')]) == 3
    sortie = capsys.readouterr()
    assert sortie.out.strip().splitlines()[-1] == 'échec : ValueError' and 'ZZ' not in sortie.out + sortie.err
    assert comptages_f.main(['--base-kit', kit, '--base', str(tmp_path / 'a.sqlite')]) == 2      # la base existe déjà
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'b.sqlite'), '--ZZ-secret')
    assert r.returncode == 2 and 'ZZ' not in r.stdout + r.stderr


def test_base_dans_le_depot_refusee_quand_les_donnees_sont_reelles(kit):
    base = os.path.join(RACINE, 'jeu_essai', 'sortie', 'jamais_creee_f.sqlite')
    r = lancer('--base-kit', kit, '--base', base, env=dict(os.environ, CARTE_DONNEES_REELLES='1'))
    assert r.returncode == 2 and not os.path.exists(base)


def test_script_shell_affiche_les_comptages_et_refuse_le_depot(kit, tmp_path):
    shell = os.path.join(RACINE, 'outils', 'essai_reel_f.sh')
    r = subprocess.run(['sh', shell, kit], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0 and 'invariants en écart : 0' in r.stdout and 'ZZ' not in r.stdout + r.stderr
    assert subprocess.run(['sh', shell, kit], capture_output=True, cwd=os.path.join(RACINE, 'docs')).returncode == 9
    assert subprocess.run(['sh', shell, 'absente.sqlite'], capture_output=True, cwd=str(tmp_path)).returncode == 8
