"""Tests du script de comptage de l'étape A (sortie : comptages seulement)."""

import json
import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
SCRIPT = os.path.join(RACINE, 'outils', 'comptages_a.py')


def globale(tmp_path, **valeurs):
    g = {'noeuds': [{'n': 'ZZ900001 BENALI'}], 'aretes': [], 'reseaux': [13, 3, 2], 'reseaux_bl': [1, 2],
         'construction': '13/11/2026'}
    g.update(valeurs)
    p = tmp_path / 'globale.json'
    p.write_text(json.dumps(g), encoding='utf-8')
    return str(p)


def lancer(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def test_reseaux_et_plus_grand_reseau_de_la_liste_noire(tmp_path):
    r = lancer('--globale', globale(tmp_path))
    assert r.returncode == 0, r.stderr
    assert 'réseaux : 3' in r.stdout
    assert 'plus grand réseau touchant la liste noire : 3 nœuds' in r.stdout  # réseaux 1 et 2 : tailles 3 et 2


def test_aucune_valeur_du_fichier_dans_la_sortie(tmp_path):
    r = lancer('--globale', globale(tmp_path))
    assert 'ZZ900001' not in r.stdout + r.stderr and 'BENALI' not in r.stdout + r.stderr


def test_aucun_reseau_de_la_liste_noire(tmp_path):
    r = lancer('--globale', globale(tmp_path, reseaux_bl=[]))
    assert 'plus grand réseau touchant la liste noire : 0 nœuds' in r.stdout


def test_fichier_mal_forme_sans_detail(tmp_path):
    p = tmp_path / 'g.json'
    p.write_text('{"noeuds": [{"n": "ZZ900001"}]', encoding='utf-8')
    r = lancer('--globale', str(p))
    assert r.returncode == 2 and 'ZZ900001' not in r.stdout + r.stderr


def test_sur_le_jeu_d_essai_du_kit():
    g = os.path.join(RACINE, 'jeu_essai', 'sortie', 'kit', 'globale.json')
    if not os.path.exists(g):
        import pytest
        pytest.skip('jeu d\'essai non construit')
    r = lancer('--globale', g)
    assert 'réseaux : 3' in r.stdout and 'plus grand réseau touchant la liste noire : 13 nœuds' in r.stdout
