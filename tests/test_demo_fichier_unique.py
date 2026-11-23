"""Démonstration en un seul fichier HTML (outils/demo/fichier_unique.py) : portail, base client, vue 360° et dossiers,
avec les réponses de l'API jointes ; base fictive légère ; rien d'extérieur, rien que du fictif."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'demo'))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure', 'reference', 'champs_par_type_prod.csv')
pytestmark = pytest.mark.skipif(not os.path.exists(STRUCTURE), reason='structure de Kamal absente')


@pytest.fixture(scope='module')
def page(tmp_path_factory):
    import fichier_unique as fu
    chemin = str(tmp_path_factory.mktemp('unique') / 'EQDOM_demo.html')
    comptes = fu.construire(chemin, n_clients=20, n_dossiers=300, n_societes=300)
    with open(chemin, encoding='utf-8') as f:
        return comptes, f.read()


def _donnees(html):
    m = re.search(r'<script type="application/json" id="donnees">(.*?)</script>', html, re.S)
    assert m, 'données jointes absentes'
    return json.loads(m.group(1))


def test_un_seul_fichier_sans_ressource_ni_appel_exterieur(page):
    _, html = page
    assert not re.search(r'<(script|link|img)[^>]+(src|href)=', html), 'aucun fichier voisin ni ressource externe'
    assert not re.search(r'(https?:)?//[a-z0-9.-]+\.[a-z]{2,}', html.replace('http://www.w3.org/2000/svg', ''), re.I)
    assert 'Object.assign(Commun, { api' in html, 'les appels à l’API sont remplacés par les données jointes'


def test_les_quatre_pages_et_leur_routeur(page):
    _, html = page
    for nom in ('index', 'base', 'fiche', 'dossier'):
        assert f'<template id="page-{nom}"' in html, nom
    assert 'Commun.aller' in html
    assert not re.search(r'location\.href\s*=', html), 'toute navigation passe par le routeur'


def test_donnees_jointes_coherentes(page):
    comptes, html = page
    d = _donnees(html)
    clients = d['clients']['items']
    assert len(clients) == comptes['clients'] and clients
    for c in clients:
        f = d[f'fiche/{c["indice"]}']
        assert f['vue360']['tuiles'], 'chaque fiche porte son mur de tuiles'
        for x in f['dossiers']:
            assert f'dossier/{x["indice"]}' in d
    assert d['resume']['clients'] >= 5


def test_base_legere_avec_les_trois_profils(page):
    comptes, html = page
    assert comptes['clients'] == 20 and comptes['dossiers'] <= 40 and len(html) < 8_000_000
    d = _donnees(html)
    profils = {d[f'fiche/{c["indice"]}']['vue360']['profil'] for c in d['clients']['items']}
    assert profils == {'salarie', 'entrepreneur', 'pm'}


def test_rien_que_du_fictif(page):
    _, html = page
    d = _donnees(html)
    texte = json.dumps(d, ensure_ascii=False)
    cins = set(re.findall(r'"cin": "([A-Z]{1,2}\d+)"', texte))
    assert cins and all(c.startswith('ZZ') for c in cins)
    assert 'données fictives' in html


def test_le_script_se_relit(page, tmp_path):
    _, html = page
    if not shutil.which('node'):
        pytest.skip('node absent')
    scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
    assert scripts
    js = tmp_path / 'tout.js'
    js.write_text('\n;\n'.join(scripts), encoding='utf-8')
    assert subprocess.run(['node', '--check', str(js)]).returncode == 0


def test_la_navigation_dans_une_expression_est_reecrite():
    import fichier_unique as fu
    assert fu._router("x.on('click', () => (a ? (location.href = m.lien) : ouvrir(m)));") == \
        "x.on('click', () => (a ? (Commun.aller(m.lien)) : ouvrir(m)));"
    assert fu._router("location.href = `f.html?i=${n}`;\nsuite();") == "Commun.aller(`f.html?i=${n}`);\nsuite();"
    assert fu._router("if (location.href === 'x') y();") == "if (location.href === 'x') y();"


def test_chiffres_du_portail_sur_les_clients_retenus(page):
    comptes, html = page
    r = _donnees(html)['resume']
    assert r['clients'] == comptes['clients'] and r['dossiers'] == comptes['dossiers']
    assert sum(p['nombre'] for p in r['produits'] if isinstance(p['nombre'], int)) <= comptes['dossiers']


def test_l_etoile_se_deplie_sur_deux_niveaux_dans_le_fichier(page):
    """Vue en étoile (23/11/2026) : une personne ou société citée se déplie, puis celles qu'elle cite."""
    _, html = page
    d = _donnees(html)

    def liens(f):
        return [re.match(r'fiche\.html\?i=(\d+)$', x['lien']).group(1) for b in f['vue360']['etoile']['branches']
                for x in b['lignes'] if (x.get('lien') or '').startswith('fiche.html')]
    niveau1 = {i for c in d['clients']['items'] for i in liens(d[f'fiche/{c["indice"]}'])}
    assert niveau1 and all(f'fiche/{i}' in d for i in niveau1)
    niveau2 = {j for i in niveau1 for j in liens(d[f'fiche/{i}'])}
    assert all(f'fiche/{j}' in d for j in niveau2)
