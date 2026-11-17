"""Page autonome des statistiques : aucune donnée individuelle, aucune ressource externe, seulement des cases non
masquées (les cases masquées n'y sont que des clés), des données pour chaque onglet. Tout est fictif."""
import json
import re
import subprocess
import sys

import pytest

from .commun import RACINE, SANS_KAMAL
from pipeline.analytique import page_statistiques

pytestmark = SANS_KAMAL


@pytest.fixture(scope='module')
def page(base_stats, tmp_path_factory):
    chemin = tmp_path_factory.mktemp('page') / 'statistiques_dossiers.html'
    page_statistiques.generer(base_stats, str(chemin))
    return chemin.read_text(encoding='utf-8')


def donnees(html):
    m = re.search(r'<script type="application/json" id="donnees">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1))


def test_aucune_forme_de_cin_rib_rc_ni_nom_du_jeu(page, plan_stats, jeu_stats):
    assert not re.search(r'\b[A-Z]{1,2}\d{4,7}\b', page)
    assert not re.search(r'\d{16,}', page)
    assert not re.search(r'\bRC\s*\d', page)
    assert not any(ref in page for ref in plan_stats)
    for nom in jeu_stats.NOMS + jeu_stats.PRENOMS:
        assert nom not in page.upper(), nom


def test_aucune_ressource_externe_ni_adresse_web(page):
    assert 'http://' not in page and 'https://' not in page
    for motif in ('<script src=', '<link', '@import', 'url(', '<img', '<iframe', 'fetch(', 'XMLHttpRequest'):
        assert motif not in page, motif


def test_le_json_embarque_ne_porte_aucune_valeur_masquee(page):
    d = donnees(page)
    assert d['cases']
    for c in d['cases']:
        if c.get('m'):
            assert set(c) <= {'i', 'p', 'c', 'd1', 'v1', 'd2', 'v2', 'm'}, c


def test_chaque_onglet_a_des_donnees(page):
    d = donnees(page)
    indicateurs = {d['indicateurs'][c['i']]['nom'] for c in d['cases'] if not c.get('m')}
    for onglet in (('nb_dossiers', 'part_dossiers'), ('part_dossiers',), ('taux_juge_suspect', 'part_verdict'),
                   ('taux_anomalie_controle', 'taux_non_executable_controle', 'controle_decisif'),
                   ('taux_remplissage', 'taux_relecture_piece', 'part_statut_extraction')):
        assert set(onglet) <= indicateurs, onglet
    assert d['entete']['dossiers'] == 600


def test_mention_et_vocabulaire(page):
    assert "Verdicts de l'antifraude, pas des fraudes constatées" in page
    assert 'Aucune valeur sur moins de 5 dossiers' in page
    texte = re.sub(r'<script.*?</script>', '', page, flags=re.S).lower()
    assert 'fraudeur' not in texte
    assert 'fraude' not in texte.replace('fraudes constatées', '').replace('antifraude', '')


def test_taille_sous_un_mo(page):
    assert len(page.encode('utf-8')) < 1_000_000


def test_le_script_de_la_page_se_relit_sans_erreur_de_syntaxe(page, tmp_path):
    scripts = re.findall(r'<script>(.*?)</script>', page, re.S)
    assert scripts
    noeud = subprocess.run(['node', '--version'], capture_output=True)
    if noeud.returncode != 0:
        pytest.skip('node absent')
    f = tmp_path / 'page.js'
    f.write_text('\n'.join(scripts), encoding='utf-8')
    r = subprocess.run(['node', '--check', str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_ligne_de_commande_construit_les_tables_et_la_page(tmp_path, jeu_stats):
    base = tmp_path / 'b.sqlite'
    jeu_stats.construire_base(str(base), jeu_stats.dossiers()).close()
    html = tmp_path / 's.html'
    r = subprocess.run([sys.executable, f'{RACINE}/stats_dossiers.py', '--base', str(base), '--html', str(html)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert html.exists() and 'ZZ' not in r.stdout
