"""Tests des crochets de Claude Code : entrée JSON simulée, code de sortie attendu.
Les formes réelles sont construites par concaténation."""

import json
import os
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
CROCHETS = os.path.dirname(ICI)
RACINE = os.path.dirname(os.path.dirname(CROCHETS))
DONNEES = os.path.expanduser('~/' + 'antifraude' + '-donnees')
CIN_REEL = 'AB' + '123456'
CIN_FICTIF = 'ZZ' + '123456'
MARQUE = 'fictif-' + 'volontaire'


def lancer(script, entree, cwd=RACINE):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=RACINE)
    r = subprocess.run([sys.executable, os.path.join(CROCHETS, script)], input=json.dumps(entree),
                       capture_output=True, text=True, cwd=cwd, env=env, timeout=60)
    return r


def bash(commande, cwd=RACINE):
    return lancer('garde_commande.py', {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
                                        'tool_input': {'command': commande}, 'cwd': cwd}, cwd=cwd)


def outil(nom, tool_input):
    return lancer('garde_fichier.py', {'hook_event_name': 'PreToolUse', 'tool_name': nom,
                                       'tool_input': tool_input, 'cwd': RACINE})


# --- garde_commande.py ---

def test_commande_sur_le_dossier_de_donnees_refusee():
    r = bash('ls ' + DONNEES)
    assert r.returncode == 2 and r.stderr.strip()


def test_commande_sur_les_telechargements_refusee():
    assert bash('ls ~/Down' + 'loads').returncode == 2


@pytest.mark.parametrize('commande', [
    'git commit -m essai --no' + '-verify',
    'git config core.hooks' + 'Path /tmp',
    'git add -f essai.xlsx',
    'git add --force essai.xlsx',
    'git add -Af .',
    'CARTE_DONNEES_REELLES' + '=1 python x.py',
    # forme courte de --no-verify, seule ou groupée, avec ou sans options avant la sous-commande
    'git commit -n -m x',
    'git commit -anm x',
    'git -C . commit -n -m x',
    'git commit --amend -n',
    # git ne distingue pas la casse des clés de configuration
    'git config core.hooks' + 'path /dev/null',
    'git -c core.HOOKS' + 'PATH=/dev/null commit -m x',
    # options entre git et add
    'git -C . add -f essai.xlsx',
    'git --git-dir=.git add --force essai.xlsx',
])
def test_commande_interdite_refusee(commande):
    assert bash(commande).returncode == 2


def test_chemin_de_donnees_refuse_quelle_que_soit_la_casse():
    # le disque du Mac ne distingue pas la casse : ~/downloads ouvre le même dossier que ~/Downloads
    assert bash('ls ~/down' + 'loads').returncode == 2
    assert bash('cat ' + DONNEES.upper()).returncode == 2
    assert outil('Read', {'file_path': DONNEES.replace('antifraude', 'AntiFraude') + '/x.txt'}).returncode == 2


@pytest.mark.parametrize('commande', [
    '.venv/bin/python -m pytest outils/garde/tests -q',
    'git add docs/journal_etapes.md',
    'git status --short',
    'git commit -m "essai"',
    'git log -n 5 --oneline',
    'git -C . status',
])
def test_commande_ordinaire_acceptee(commande):
    r = bash(commande)
    assert r.returncode == 0, r.stderr


def test_mutmut_refuse_depuis_la_racine():
    assert bash('.venv/bin/mutmut run').returncode == 2


def test_mutmut_refuse_depuis_un_sous_dossier_du_depot():
    assert bash('mutmut run', cwd=os.path.join(RACINE, 'api')).returncode == 2


def test_mutmut_accepte_depuis_une_copie_de_travail(tmp_path):
    assert bash('mutmut run', cwd=str(tmp_path)).returncode == 0


# --- garde_fichier.py ---

def test_lecture_dans_le_dossier_de_donnees_refusee():
    r = outil('Read', {'file_path': os.path.join(DONNEES, 'essai_garde.txt')})
    assert r.returncode == 2 and r.stderr.strip()


def test_recherche_dans_le_dossier_de_donnees_refusee():
    assert outil('Grep', {'pattern': 'x', 'path': DONNEES}).returncode == 2
    assert outil('Glob', {'pattern': DONNEES + '/**'}).returncode == 2


def test_lecture_du_dossier_api_de_kamal_refusee():
    r = outil('Read', {'file_path': os.path.join(RACINE, 'import', 'kamal_structure', 'api', 'x.ts')})
    assert r.returncode == 2


def test_lecture_de_notre_api_acceptee():
    assert outil('Read', {'file_path': os.path.join(RACINE, 'api', 'app', 'graphe.py')}).returncode == 0


def test_ecriture_d_un_cin_de_forme_reelle_refusee():
    r = outil('Write', {'file_path': os.path.join(RACINE, 'essai_garde.py'),
                        'content': 'cin = "' + CIN_REEL + '"\n'})
    assert r.returncode == 2
    assert CIN_REEL not in r.stderr


def test_ecriture_avec_la_marque_acceptee():
    r = outil('Write', {'file_path': os.path.join(RACINE, 'essai_garde.py'),
                        'content': 'cin = "' + CIN_REEL + '"  # ' + MARQUE + '\n'})
    assert r.returncode == 0, r.stderr


def test_ecriture_d_un_cin_fictif_acceptee():
    r = outil('Write', {'file_path': os.path.join(RACINE, 'essai_garde.py'),
                        'content': 'cin = "' + CIN_FICTIF + '"\n'})
    assert r.returncode == 0, r.stderr


def test_modification_d_un_cin_de_forme_reelle_refusee():
    r = outil('Edit', {'file_path': os.path.join(RACINE, 'x.py'), 'old_string': 'a',
                       'new_string': 'cin = "' + CIN_REEL + '"'})
    assert r.returncode == 2


# --- verif_python.py ---

def test_verif_python_refuse_un_fichier_qui_ne_compile_pas(tmp_path):
    f = tmp_path / 'casse.py'
    f.write_text('def f(:\n')
    r = lancer('verif_python.py', {'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
                                   'tool_input': {'file_path': str(f)}})
    assert r.returncode == 2


def test_verif_python_accepte_un_fichier_correct(tmp_path):
    f = tmp_path / 'bon.py'
    f.write_text('def f():\n    return 1\n')
    r = lancer('verif_python.py', {'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
                                   'tool_input': {'file_path': str(f)}})
    assert r.returncode == 0, r.stderr


def test_verif_python_ignore_un_autre_fichier(tmp_path):
    f = tmp_path / 'note.md'
    f.write_text('def f(:\n')
    r = lancer('verif_python.py', {'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
                                   'tool_input': {'file_path': str(f)}})
    assert r.returncode == 0


# --- garde_arbre.py ---

def test_garde_arbre_ne_bloque_pas_si_deja_relance():
    r = lancer('garde_arbre.py', {'hook_event_name': 'Stop', 'stop_hook_active': True})
    assert r.returncode == 0


def test_garde_arbre_bloque_si_la_garde_echoue(tmp_path):
    # une garde qui ne peut pas tourner (dépôt introuvable, erreur git) ne doit pas laisser conclure en silence
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    r = subprocess.run([sys.executable, os.path.join(CROCHETS, 'garde_arbre.py')],
                       input=json.dumps({'hook_event_name': 'Stop'}), capture_output=True, text=True,
                       cwd=str(tmp_path), env=env, timeout=60)
    assert r.returncode == 2
    assert 'garde' in r.stderr


def test_garde_arbre_introuvable_ne_bloque_pas_deux_fois(tmp_path):
    # garde absente et deuxième tentative de fin de tour : ne pas boucler, le crochet git reste la barrière
    copie = tmp_path / 'crochets'
    copie.mkdir()
    for nom in ('garde_arbre.py', '_commun.py'):
        (copie / nom).write_text(open(os.path.join(CROCHETS, nom), encoding='utf-8').read(), encoding='utf-8')
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    r = subprocess.run([sys.executable, str(copie / 'garde_arbre.py')],
                       input=json.dumps({'hook_event_name': 'Stop', 'stop_hook_active': True}),
                       capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=60)
    assert r.returncode == 0, r.stderr


# --- rappel_session.py ---

def test_rappel_de_seance():
    r = lancer('rappel_session.py', {'hook_event_name': 'SessionStart', 'source': 'startup'})
    assert r.returncode == 0
    lignes = r.stdout.strip().splitlines()
    assert 0 < len(lignes) <= 30
    assert 'Données réelles' in r.stdout
