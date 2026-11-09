"""Tests de publier_carte.py, uniquement sur des données fictives (jeu du kit et données générées)."""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(ICI)
RACINE = os.path.dirname(PIPELINE)
sys.path.insert(0, PIPELINE)
import publier_carte as pc  # noqa: E402

KIT = os.path.join(RACINE, 'jeu_essai', 'donnees')


def lancer(*args):
    subprocess.run([sys.executable, *args], check=True, capture_output=True)


def construire(dossier, ln, annonces, personnes):
    base, chaines = os.path.join(dossier, 'base.sqlite'), os.path.join(dossier, 'chaines.json')
    lancer(os.path.join(PIPELINE, 'construire_base.py'), '--liste-noire', ln, '--rc-annonces', annonces,
           '--rc-personnes', personnes, '--base', base)
    lancer(os.path.join(PIPELINE, 'chaines_dessin.py'), '--base', base, '--excel', os.path.join(dossier, 'c.xlsx'),
           '--html', '', '--json', chaines)
    return base, chaines


@pytest.fixture(scope='session', params=['kit', 'genere'])
def jeu(request, tmp_path_factory):
    d = str(tmp_path_factory.mktemp(request.param))
    if request.param == 'kit':
        base, chaines = construire(d, os.path.join(KIT, 'liste_noire_fictive.csv'),
                                   os.path.join(KIT, 'rc_annonces.csv'), os.path.join(KIT, 'rc_personnes.csv'))
    else:
        g = os.path.join(d, 'donnees')
        lancer(os.path.join(RACINE, 'jeu_essai', 'generer.py'), '--echelle', 'petit', '--sortie', g)
        base, chaines = construire(d, os.path.join(g, 'liste_noire.csv'), os.path.join(g, 'rc_annonces.csv'),
                                   os.path.join(g, 'rc_personnes.csv'))
    pub = os.path.join(d, 'publication')
    m = pc.publier(base, chaines, pub)
    with open(os.path.join(pub, 'geometrie.json'), encoding='utf-8') as f:
        texte = f.read()
    with open(chaines, encoding='utf-8') as f:
        source = json.load(f)
    return dict(base=base, chaines=chaines, pub=pub, manifeste=m, texte=texte, geo=json.loads(texte),
                source=source, dossier=d)


def chaines_de(valeur):
    """Toutes les chaînes de caractères d'un objet JSON (clés comprises)."""
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for k, v in valeur.items():
            yield k
            yield from chaines_de(v)
    elif isinstance(valeur, list):
        for v in valeur:
            yield from chaines_de(v)


# ---- couche 1 : rien qui identifie ------------------------------------------------------------------------------
CIN_RE = re.compile(r'[A-Z]{1,2}\s?\d{3,}', re.I)
CHIFFRES_RE = re.compile(r'\d{4,}')                    # RC, numéros de dépôt, CIN sans lettre
ARABE_RE = re.compile('[؀-ۿ]')
# Libellés de rôle permis : le vocabulaire exact du kit, part détenue éventuelle (« associé (33.3 %) »)
ROLE_RE = pc.ROLE_PERMIS_RE


def test_couche1_sans_cin_ni_rc_ni_arabe(jeu):
    for s in chaines_de(jeu['geo']):
        if s == jeu['geo']['construction']['date']:
            continue
        assert not CIN_RE.search(s), f'chaîne ressemblant à un CIN : {s!r}'
        assert not CHIFFRES_RE.search(s), f'suite de chiffres (RC ?) : {s!r}'
        assert not ARABE_RE.search(s), f'texte arabe : {s!r}'


def test_couche1_seulement_des_chaines_permises(jeu):
    g = jeu['geo']
    permis = set(g['types']) | set(g['styles']) | set(g['villes']) | {
        'format', 'construction', 'date', 'types', 'styles', 'villes', 'noeuds', 't', 'bl', 'c', 'deg', 'ville',
        'aretes', 'a', 'b', 'style', 'force', 'reseaux', 'reseaux_bl', 'inscrits', 'i', 'type', 'compte',
        'alerte', 'certain', 'chaines', '1', '2', '3', '4', 'PP', 'PM', g['construction']['date']}
    from construire_base import VILLES
    assert set(g['villes']) <= {code for code, *_ in VILLES}
    for s in chaines_de(g):
        assert s in permis or s == '' or ROLE_RE.match(s), f'chaîne inattendue dans la couche 1 : {s!r}'


def test_couche1_ne_contient_aucune_identite_de_la_base(jeu):
    con = sqlite3.connect(jeu['base'])
    valeurs = set()
    for req in ('SELECT nom_affiche, cin, rc_num, cle_entite FROM bl_entite',
                'SELECT nom, prenom, cin FROM bl_inscription',
                'SELECT denomination, rc_num FROM rc_societe',
                'SELECT nom_complet, cin_norm FROM rc_personne'):
        for ligne in con.execute(req):
            valeurs.update(str(v) for v in ligne if v and len(str(v)) >= 4)
    textes = {t.upper() for t in chaines_de(jeu['geo'])}
    trouvees = {v for v in valeurs if any(v.upper() in t for t in textes)}
    assert not trouvees, f'identités présentes dans la couche 1 : {sorted(trouvees)[:5]}'


# ---- cohérence des deux couches ----------------------------------------------------------------------------------
def test_indices_permutation_et_tableaux_alignes(jeu):
    g, n = jeu['geo'], jeu['manifeste']['noeuds']
    for k, tableau in g['noeuds'].items():
        assert len(tableau) == n, k
    assert len(set(g['aretes']['a'])) <= n and max(g['aretes']['a'] + g['aretes']['b']) < n
    con = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite'))
    indices = [i for (i,) in con.execute('SELECT indice FROM noeud ORDER BY indice')]
    assert indices == list(range(n))
    types = dict(con.execute('SELECT indice, type FROM noeud'))
    assert all(g['types'][t] == types[i] for i, t in enumerate(g['noeuds']['t']))


def test_chaque_inscrit_a_sa_chaine_complete(jeu):
    g = jeu['geo']
    con = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite'))
    complet = {i: json.loads(d) for i, d in con.execute('SELECT indice, donnees FROM chaine')}
    assert len(complet) == len(g['inscrits']) == len(jeu['source'])
    for p, src in zip(g['inscrits'], jeu['source']):
        c = complet[p['i']]
        assert c['nom'] == src['nom'] and c['compte'] == src['compte'] == p['compte']
        assert len(c['noeuds']) == len(src['noeuds']) == len(p['noeuds'])
        assert len(c['aretes']) == len(src['aretes']) == len(p['aretes'])
        assert len(c['chaines']) == len(p['chaines'])


def test_fiche_inscrit_porte_cin_et_motifs(jeu):
    con = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite'))
    pp = con.execute("""SELECT i.cin FROM noeud n JOIN identite i USING (indice)
                        WHERE n.type = 'inscrit_personne'""").fetchall()
    assert pp and any(c for (c,) in pp)


def test_annonces_rattachees_aux_societes(jeu):
    con = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite'))
    types = {t for (t,) in con.execute('SELECT DISTINCT n.type FROM annonce a JOIN noeud n USING (indice)')}
    assert types == {'societe'}


# ---- manifeste -------------------------------------------------------------------------------------------------
def test_manifeste_empreintes_et_fictif(jeu):
    m = jeu['manifeste']
    for f, h in m['fichiers'].items():
        assert pc.empreinte(os.path.join(jeu['pub'], f)) == h
    assert m['fictif'] is True


def test_un_seul_cin_reel_suffit_a_refuser_le_fictif(jeu, tmp_path):
    base = str(tmp_path / 'base.sqlite')
    shutil.copy(jeu['base'], base)
    con = sqlite3.connect(base)
    con.execute("UPDATE bl_entite SET cin = 'AB123456' WHERE entite_id = "
                "(SELECT MIN(entite_id) FROM bl_entite WHERE cin IS NOT NULL)")
    con.commit()
    m = pc.publier(base, jeu['chaines'], str(tmp_path / 'pub'))
    assert m['fictif'] is False


def test_indices_tires_au_hasard_a_chaque_publication(jeu, tmp_path):
    if jeu['manifeste']['noeuds'] < 50:
        pytest.skip('trop peu de nœuds pour comparer deux tirages')
    pc.publier(jeu['base'], jeu['chaines'], str(tmp_path / 'p2'))
    a = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite')).execute(
        'SELECT ref_id FROM noeud ORDER BY indice').fetchall()
    b = sqlite3.connect(str(tmp_path / 'p2' / 'identites.sqlite')).execute(
        'SELECT ref_id FROM noeud ORDER BY indice').fetchall()
    assert sorted(a) == sorted(b) and a != b
