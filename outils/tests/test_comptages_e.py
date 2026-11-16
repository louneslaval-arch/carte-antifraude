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
    assert nombre(r.stdout, 'opérations lues sans date lisible') == 0
    assert nombre(r.stdout, "listes d'objets non rangées") == un('SELECT sum(nb_listes_ignorees) FROM c1_piece')
    assert nombre(r.stdout, 'invariants en écart') == 0


def test_invariant_en_ecart_compte_sans_detail(tmp_path, monkeypatch, capsys):
    import comptages_e
    _, chemins = fichiers(tmp_path, n=2)
    construire = comptages_e.c1_faits.construire_tout

    def construire_puis_abimer(cx):
        construire(cx)
        cx.execute('DELETE FROM c1_piece WHERE ref = (SELECT min(ref) FROM c1_piece)')
        cx.commit()
    monkeypatch.setattr(comptages_e.c1_faits, 'construire_tout', construire_puis_abimer)
    assert comptages_e.main(['--base', str(tmp_path / 'essai.sqlite'), *chemins]) == 1
    sortie = capsys.readouterr().out
    assert nombre(sortie, 'invariants en écart') == 1 and 'ZZ' not in sortie


def test_dossier_refuse_par_le_miroir_compte(tmp_path):
    jeu, chemins = fichiers(tmp_path, n=1)
    d = dict(jeu.dossiers[1], verdict='VALEUR_HORS_ENUMERATION')
    p = tmp_path / 'refuse.json'
    p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    r = lancer('--base', str(tmp_path / 'essai.sqlite'), *chemins, str(p))
    assert r.returncode == 1 and nombre(r.stdout, 'dossiers refusés par le miroir') == 1
    assert nombre(r.stdout, 'dossiers lus') == 1


def test_sortie_sans_aucune_valeur_lue(tmp_path):
    jeu, chemins = fichiers(tmp_path)
    r = lancer('--base', str(tmp_path / 'essai.sqlite'), *chemins)
    sortie = r.stdout + r.stderr
    assert 'ZZ' not in sortie
    for d in jeu.dossiers[:6]:
        assert d['clientName'] not in sortie
        for p in d['pieces']:
            for v in (p['fields'] or {}).values():
                assert not (isinstance(v, str) and len(v) >= 6 and v in sortie)


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


# ---- défauts relevés par le gardien des données --------------------------------------------------------------------

sys.path.insert(0, os.path.join(RACINE, 'outils'))
SHELL = os.path.join(RACINE, 'outils', 'essai_reel_e.sh')
GARDE_FOU = 'CARTE_DONNEES_' + 'REELLES'       # jamais écrit en entier hors de la commande destinée à Lounès


def test_echec_apres_lecture_classe_d_erreur_seulement_jamais_de_trace(tmp_path, monkeypatch, capsys):
    import comptages_e
    _, chemins = fichiers(tmp_path, n=1)

    def tomber(cx):
        raise ValueError('ZZ-SECRET dans le message')
    monkeypatch.setattr(comptages_e.c1_faits, 'construire_tout', tomber)
    assert comptages_e.main(['--base', str(tmp_path / 'essai.sqlite'), *chemins]) == 3
    sortie = capsys.readouterr()
    assert sortie.out.strip().splitlines()[-1] == 'échec : ValueError'
    assert 'ZZ' not in sortie.out + sortie.err and 'Traceback' not in sortie.out + sortie.err


def test_argument_inattendu_jamais_recopie(tmp_path):
    _, chemins = fichiers(tmp_path, n=1)
    r = lancer('--base', str(tmp_path / 'essai.sqlite'), *chemins, '--ZZ-secret.json')
    assert r.returncode == 2 and 'ZZ' not in r.stdout + r.stderr


def test_dossier_non_fictif_refuse_sans_le_garde_fou_accepte_avec(tmp_path):
    jeu, _ = fichiers(tmp_path, n=1)
    d = dict(jeu.dossiers[0], ref='DOS' + '-0001')
    p = tmp_path / 'autre.json'
    p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k != GARDE_FOU}
    r = subprocess.run([sys.executable, SCRIPT, '--base', str(tmp_path / 'a.sqlite'), str(p)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1 and nombre(r.stdout, 'dossiers non fictifs refusés') == 1
    assert nombre(r.stdout, 'dossiers lus') == 0 and 'DOS' not in r.stdout + r.stderr
    r = subprocess.run([sys.executable, SCRIPT, '--base', str(tmp_path / 'b.sqlite'), str(p)],
                       capture_output=True, text=True, env=dict(env, **{GARDE_FOU: '1'}))
    assert r.returncode == 0 and nombre(r.stdout, 'dossiers lus') == 1


def test_base_dans_le_depot_refusee_quand_les_donnees_sont_reelles(tmp_path):
    _, chemins = fichiers(tmp_path, n=1)
    base = os.path.join(RACINE, 'jeu_essai', 'sortie', 'jamais_creee.sqlite')
    r = subprocess.run([sys.executable, SCRIPT, '--base', base, *chemins], capture_output=True, text=True,
                       env=dict(os.environ, **{GARDE_FOU: '1'}))
    assert r.returncode == 2 and not os.path.exists(base)


def test_script_shell_affiche_les_comptages_et_rend_le_code(tmp_path):
    _, chemins = fichiers(tmp_path, n=2)
    r = subprocess.run(['sh', SHELL, *chemins], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0 and '(attendu 182)' in r.stdout and 'ZZ' not in r.stdout + r.stderr


def test_script_shell_dit_l_echec_et_rend_un_code_non_nul(tmp_path):
    _, chemins = fichiers(tmp_path, n=1)
    r = subprocess.run(['sh', SHELL, *chemins, '--ZZ-secret.json'], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode != 0 and 'ne pas coller' in r.stdout and 'ZZ' not in r.stdout + r.stderr


def test_script_shell_refuse_le_depot():
    r = subprocess.run(['sh', SHELL, 'x.json'], capture_output=True, text=True, cwd=os.path.join(RACINE, 'docs'))
    assert r.returncode == 9
