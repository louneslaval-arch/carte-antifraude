"""Ce que le générateur promet : des données reconnaissables comme fictives, reproductibles, et qui exercent
chacune des règles de rapprochement annoncées."""

import csv
import json
import os
import sqlite3
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
GENERER = os.path.join(RACINE, 'jeu_essai', 'generer.py')
PIPELINE = os.path.join(RACINE, 'pipeline')


def generer(dossier, *args):
    subprocess.run([sys.executable, GENERER, '--echelle', 'petit', '--sortie', str(dossier), *args],
                   check=True, capture_output=True)
    return {f: lire(os.path.join(dossier, f)) for f in ('liste_noire.csv', 'rc_annonces.csv', 'rc_personnes.csv')}


def lire(chemin):
    with open(chemin, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope='module')
def jeu(tmp_path_factory):
    d = tmp_path_factory.mktemp('genere')
    fichiers = generer(d)
    base = d / 'base.sqlite'
    subprocess.run([sys.executable, os.path.join(PIPELINE, 'construire_base.py'),
                    '--liste-noire', str(d / 'liste_noire.csv'), '--rc-annonces', str(d / 'rc_annonces.csv'),
                    '--rc-personnes', str(d / 'rc_personnes.csv'), '--base', str(base)],
                   check=True, capture_output=True)
    with open(d / 'verite.json', encoding='utf-8') as f:
        verite = json.load(f)
    return dict(dossier=d, fichiers=fichiers, base=str(base), verite=verite)


def test_tout_cin_porte_le_prefixe_fictif(jeu):
    cins = [l['cin'] for l in jeu['fichiers']['liste_noire.csv'] if l['cin']]
    cins += [l['cin'] for l in jeu['fichiers']['rc_personnes.csv'] if l['cin']]
    cins = [c for c in cins if not c.startswith('X')]          # saisie masquée « XXXXXXXX », voulue
    assert cins and all(c.replace(' ', '').startswith('ZZ') for c in cins)


def test_tout_lien_pointe_vers_le_domaine_reserve(jeu):
    urls = [l['url'] for l in jeu['fichiers']['rc_annonces.csv']]
    assert urls and all(u.startswith('https://exemple.invalid/') for u in urls)


def test_toute_inscription_est_marquee_fictive(jeu):
    assert all(l['note'] == 'Exemple fictif' for l in jeu['fichiers']['liste_noire.csv'])


def test_meme_graine_memes_donnees_autre_graine_autres_donnees(jeu, tmp_path):
    assert generer(tmp_path / 'a') == jeu['fichiers']
    assert generer(tmp_path / 'b', '--graine', '7') != jeu['fichiers']


def test_societes_demandees(tmp_path):
    subprocess.run([sys.executable, GENERER, '--societes', '50', '--sortie', str(tmp_path)], check=True,
                   capture_output=True)
    with open(tmp_path / 'verite.json', encoding='utf-8') as f:
        assert json.load(f)['societes'] >= 50


def test_chaque_regle_annoncee_trouve_des_correspondances(jeu):
    con = sqlite3.connect(jeu['base'])
    regles = {r for (r,) in con.execute('SELECT DISTINCT regle FROM correspondance')}
    assert {'R01', 'R01v', 'R02', 'R03', 'R04', 'R07', 'R08'} <= regles


def test_les_ponts_entre_societes_existent(jeu):
    """Des personnes dirigent plusieurs sociétés : c'est ce qui donne des chaînes de 3 et 4 arêtes."""
    con = sqlite3.connect(jeu['base'])
    multi = con.execute("""SELECT COUNT(*) FROM (SELECT nom_complet FROM rc_personne GROUP BY nom_complet
                           HAVING COUNT(DISTINCT societe_id) >= 2)""").fetchone()[0]
    assert multi >= 20


def test_les_ecritures_arabe_et_latine_sont_presentes(jeu):
    noms = [l['nom_complet'] for l in jeu['fichiers']['rc_personnes.csv']]
    arabes = sum(1 for n in noms if any('؀' <= ch <= 'ۿ' for ch in n))
    assert 0.2 < arabes / len(noms) < 0.8


def test_verite_decrit_chaque_inscription_de_personne_ou_societe(jeu):
    cas = jeu['verite']['cas']
    assert {c['regle'] for c in cas} >= {'R01', 'R01v', 'R02', 'R03', 'R04', 'R07', 'R08', 'absent'}
    reseaux = [c for c in cas if c['type'] == 'reseau_rc_consecutifs']
    assert reseaux


def test_saisies_abimees_signalees_comme_anomalies(jeu):
    con = sqlite3.connect(jeu['base'])
    assert con.execute('SELECT COUNT(*) FROM bl_anomalie').fetchone()[0] >= 2
