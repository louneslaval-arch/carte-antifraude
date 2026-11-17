"""Démonstration autonome (outils/demo/exporter_autonome.py) : pages, données jointes, rien que du fictif, rien
d'extérieur. Exportée sur 5 clients de la base livrée."""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'demo'))
import exporter_autonome as ea  # noqa: E402


@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    sortie = str(tmp_path_factory.mktemp('autonome') / 'EQDOM_demo')
    comptes = ea.main(['--sortie', sortie, '--clients', '5'])
    assert comptes == 0
    return sortie


def donnee(demo, cle):
    with open(os.path.join(demo, 'donnees', cle + '.js'), encoding='utf-8') as f:
        texte = f.read()
    m = re.fullmatch(r'Demo\.recevoir\((".*?"), (.*)\);\n', texte, re.S)
    assert m and json.loads(m.group(1)) == cle
    return json.loads(m.group(2))


def test_pages_avec_demo_js_juste_apres_commun_js(demo):
    for nom in ea.PAGES:
        html = open(os.path.join(demo, nom), encoding='utf-8').read()
        assert ea.SCRIPT_COMMUN + '\n<script src="demo.js" defer></script>' in html, nom
    assert os.path.exists(os.path.join(demo, 'demo.js')) and os.path.exists(os.path.join(demo, 'LISEZ-MOI.txt'))
    if shutil.which('node'):
        assert subprocess.run(['node', '--check', os.path.join(demo, 'demo.js')]).returncode == 0


def test_chaque_client_a_sa_fiche_son_reseau_et_ses_dossiers(demo):
    clients = donnee(demo, 'clients')['items']
    assert len(clients) == 5
    for c in clients:
        f = donnee(demo, f'fiche/{c["indice"]}')
        assert f['identite']['nom'] == c['nom']
        assert donnee(demo, f'reseau/{c["indice"]}')['noeuds']
        for d in f['dossiers']:
            assert donnee(demo, f'dossier/{d["indice"]}')['entete']['reference'].startswith('ZZ')
    geo = donnee(demo, 'carte/geometrie')
    assert len(donnee(demo, 'carte/fiches')) == len(geo['noeuds']) >= len(donnee(demo, 'carte/noms')) > 0


def test_rien_que_du_fictif_et_rien_d_exterieur(demo):
    cin = re.compile(r'"cin":"([^"]+)"')
    adresse = re.compile(r'https?://([a-z0-9.-]+)')
    for d, _s, noms in os.walk(demo):
        for nom in noms:
            texte = open(os.path.join(d, nom), encoding='utf-8').read()
            assert all(v.upper().startswith('ZZ') for v in cin.findall(texte)), nom
            assert set(adresse.findall(texte)) <= {'exemple.invalid', 'www.w3.org'}, nom
