"""Tests de publier_globale.py : la carte globale (carte_globale.py) publiée en deux couches. Données fictives seulement
(jeu du kit et données générées)."""

import json
import os
import re
import sqlite3
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(ICI)
RACINE = os.path.dirname(PIPELINE)
sys.path.insert(0, PIPELINE)
import publier_carte as pc  # noqa: E402
import publier_globale as pg  # noqa: E402

sys.path.insert(0, os.path.join(RACINE, 'jeu_essai'))
import fabrique  # noqa: E402


def carte_globale(base, dossier):
    """Sortie de carte_globale.py --json pour une base construite."""
    chemin = os.path.join(dossier, 'globale.json')
    fabrique.lancer(os.path.join(PIPELINE, 'carte_globale.py'), '--base', base, '--json', chemin,
                    '--html', os.path.join(dossier, 'carte_globale.html'))
    return chemin


@pytest.fixture(scope='session', params=['kit', 'genere'])
def jeu(request, tmp_path_factory):
    d = str(tmp_path_factory.mktemp('globale-' + request.param))
    base, _chaines = fabrique.du_kit(d) if request.param == 'kit' else fabrique.generee(d)
    globale = carte_globale(base, d)
    pub = os.path.join(d, 'publication_globale')
    m = pg.publier(globale, pub)
    with open(os.path.join(pub, 'geometrie.json'), encoding='utf-8') as f:
        texte = f.read()
    with open(globale, encoding='utf-8') as f:
        source = json.load(f)
    con = sqlite3.connect(os.path.join(pub, 'identites.sqlite'))
    ref = dict(con.execute('SELECT indice, ref_id FROM noeud'))
    con.close()
    return dict(base=base, globale=globale, source=source, pub=pub, manifeste=m, texte=texte,
                geo=json.loads(texte), ref=ref, dossier=d)


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


def identites(jeu, requete):
    con = sqlite3.connect(os.path.join(jeu['pub'], 'identites.sqlite'))
    try:
        return con.execute(requete).fetchall()
    finally:
        con.close()


# ---- couche 1 : la carte, sans rien qui identifie --------------------------------------------------------------------
CIN_RE = re.compile(r'[A-Z]{1,2}\s?\d{3,}', re.I)
CHIFFRES_RE = re.compile(r'\d{4,}')                    # RC, CIN sans lettre, dates d'annonce
ARABE_RE = re.compile('[؀-ۿ]')
ROLE = pc.ROLE_PERMIS_RE.pattern[1:-1]
ROLE_RE = re.compile('^(' + ROLE + ')(, (' + ROLE + '))*$')
RAPPROCHEMENT_RE = re.compile(r'^rapprochement R\d{2}[a-z]? \((certain|probable)(, même CIN, dossier)?(, poids \d\.\d{2})?\)$')


def test_couche1_sans_cin_ni_suite_de_chiffres_ni_arabe(jeu):
    dates = {jeu['geo']['construction']['date'], jeu['geo']['date_carte']}
    for s in chaines_de(jeu['geo']):
        if s in dates:
            continue
        assert not CIN_RE.search(s), f'chaîne ressemblant à un CIN : {s!r}'
        assert not CHIFFRES_RE.search(s), f'suite de chiffres (RC, date ?) : {s!r}'
        assert not ARABE_RE.search(s), f'texte arabe : {s!r}'


def test_couche1_ne_contient_aucune_identite(jeu):
    valeurs = set()
    for n in jeu['source']['noeuds']:
        for champ in ('nom', 'lat', 'cin', 'rc', 'url', 'dern', 'dos', 'listes', 'motifs', 'bl'):
            v = n.get(champ)
            if isinstance(v, str) and len(v) >= 4 and v != 'inscrit':
                valeurs.add(v.upper())
    con = sqlite3.connect(jeu['base'])
    for req in ('SELECT nom_affiche, cin, rc_num, cle_entite FROM bl_entite', 'SELECT nom, prenom, cin FROM bl_inscription',
                'SELECT denomination, rc_num FROM rc_societe', 'SELECT nom_complet, cin_norm FROM rc_personne'):
        for ligne in con.execute(req):
            valeurs.update(str(v).upper() for v in ligne if v and len(str(v)) >= 4)
    con.close()
    textes = {t.upper() for t in chaines_de(jeu['geo'])}
    trouvees = {v for v in valeurs if any(v in t for t in textes)}
    assert not trouvees, f'identités présentes dans la couche 1 : {sorted(trouvees)[:5]}'


def test_couche1_seulement_des_champs_et_des_valeurs_permis(jeu):
    g = jeu['geo']
    assert set(g) == {'format', 'type', 'construction', 'date_carte', 'noeuds', 'aretes', 'reseaux', 'reseaux_bl', 'geo'}
    assert g['type'] == 'globale'
    for n in g['noeuds']:
        assert set(n) <= pg.CHAMPS_COUCHE1, set(n) - pg.CHAMPS_COUCHE1
        assert n['t'] in ('societe', 'personne', 'inscrit') and n['bl'] in (0, 1)
        assert n.get('o', 'r') in ('r', 'd', 'rd') and n.get('certain', 0) in (0, 1)
    for a in g['aretes']:
        assert set(a) == {'a', 'b', 'force', 'style', 'lib'}
        assert a['lib'] in ('', 'société associée') or ROLE_RE.match(a['lib']) or RAPPROCHEMENT_RE.match(a['lib']), a['lib']


def test_toute_la_carte_est_publiee_positions_aretes_reseaux_geographie(jeu):
    g, src, ref = jeu['geo'], jeu['source'], jeu['ref']
    assert len(g['noeuds']) == len(src['noeuds']) == jeu['manifeste']['noeuds'] == len(ref)
    par_id = {n['id']: n for n in src['noeuds']}
    for i, n in enumerate(g['noeuds']):
        s = par_id[ref[i]]
        for champ in ('x', 'y', 'mx', 'my', 'deg', 'c', 't', 'ville', 'o', 'ns'):
            assert n.get(champ) == s.get(champ), (champ, ref[i])
        assert n['bl'] == (1 if s.get('bl') else 0)
        assert n.get('certain', 0) == (1 if s.get('certain') else 0)
    ids = [n['id'] for n in src['noeuds']]
    assert sorted((ids[a['a']], ids[a['b']], a['force'], a['style']) for a in src['aretes']) == \
        sorted((ref[a['a']], ref[a['b']], a['force'], a['style']) for a in g['aretes'])
    assert (g['reseaux'], g['reseaux_bl'], g['geo'], g['date_carte']) == \
        (src['reseaux'], src['reseaux_bl'], src['geo'], src['construction'])


def test_libelles_de_role_sans_date_en_couche1_et_complets_en_couche2(jeu):
    src, ref = jeu['source'], jeu['ref']
    ids = [n['id'] for n in src['noeuds']]
    complets = {(ids[a['a']], ids[a['b']]): (a['lib'], a['force']) for a in src['aretes']}
    couche2 = {(ref[a], ref[b]): (lib, force) for a, b, lib, force in identites(
        jeu, 'SELECT indice_a, indice_b, libelle, force FROM lien')}
    assert couche2 == complets
    for a in jeu['geo']['aretes']:
        lib = complets[(ref[a['a']], ref[a['b']])][0]
        attendu = pc.role_couche1(lib) or (lib if lib == 'société associée' or RAPPROCHEMENT_RE.match(lib) else '')
        assert a['lib'] == attendu, lib


def test_couche2_porte_chaque_identite(jeu):
    ref = jeu['ref']
    par_id = {n['id']: n for n in jeu['source']['noeuds']}
    lignes = identites(jeu, 'SELECT i.indice, n.type, i.nom, i.lat, i.cin, i.rc, i.tribunal, i.ville, i.derniere, i.url, '
                            'i.dissoute, i.listes, i.motifs, i.certain, g.liste_noire, g.personnes, g.nb_dossiers, '
                            'g.dossiers FROM identite i JOIN noeud n USING (indice) JOIN fiche_globale g USING (indice)')
    assert len(lignes) == len(ref)
    for (i, typ, nom, lat, cin, rc, trib, ville, dern, url, diss, listes, motifs, certain, bl, np_, nd, dos) in lignes:
        s = par_id[ref[i]]
        assert typ == s['t']
        assert (nom, lat, cin, rc, trib, ville, dern, url, listes, motifs) == (
            s.get('nom'), s.get('lat'), s.get('cin'), s.get('rc'), s.get('trib'), s.get('ville'), s.get('dern'),
            s.get('url'), s.get('listes'), s.get('motifs'))
        assert (diss, certain) == (1 if s.get('diss') else 0, 1 if s.get('certain') else 0)
        assert (bl, np_, nd, dos) == (s.get('bl') or None, s.get('np'), s.get('nd'), s.get('dos'))


def test_recherche_par_nom_ecriture_latine_cin_et_rc(jeu):
    ref = jeu['ref']
    par_id = {n['id']: n for n in jeu['source']['noeuds']}
    formes = set(identites(jeu, 'SELECT indice, champ, valeur FROM recherche'))
    for i, r in ref.items():
        s = par_id[r]
        if s.get('nom'):
            assert (i, 'nom', s['nom'].upper()) in formes
        if s.get('lat'):
            assert (i, 'nom', s['lat'].upper()) in formes
        if s.get('cin'):
            assert (i, 'cin', re.sub(r'\s+', '', s['cin']).upper()) in formes
        if s.get('rc'):
            assert (i, 'rc', re.sub(r'\s+', '', str(s['rc'])).upper()) in formes


def test_indices_tires_au_hasard_a_chaque_publication_pour_le_meme_contenu(jeu, tmp_path):
    pub2 = str(tmp_path / 'publication_2')
    pg.publier(jeu['globale'], pub2)
    con = sqlite3.connect(os.path.join(pub2, 'identites.sqlite'))
    ref2 = dict(con.execute('SELECT indice, ref_id FROM noeud'))
    con.close()
    with open(os.path.join(pub2, 'geometrie.json'), encoding='utf-8') as f:
        g2 = json.load(f)

    def canonique(g, ref):
        noeuds = sorted((ref[i], json.dumps(n, sort_keys=True)) for i, n in enumerate(g['noeuds']))
        aretes = sorted((ref[a['a']], ref[a['b']], a['force'], a['style'], a['lib']) for a in g['aretes'])
        return noeuds, aretes
    assert canonique(g2, ref2) == canonique(jeu['geo'], jeu['ref'])
    if len(ref2) > 6:
        assert [ref2[i] for i in range(len(ref2))] != [jeu['ref'][i] for i in range(len(ref2))]


def test_manifeste_fictif_type_et_empreintes(jeu):
    m = jeu['manifeste']
    assert (m['format'], m['type'], m['fictif']) == (1, 'globale', True)
    assert set(m['fichiers']) == set(pc.FICHIERS)
    for nom, h in m['fichiers'].items():
        assert pc.empreinte(os.path.join(jeu['pub'], nom)) == h
    assert m['inscrits'] == sum(1 for n in jeu['source']['noeuds'] if n['t'] == 'inscrit')


def test_un_cin_non_fictif_marque_la_publication_comme_reelle(jeu, tmp_path):
    src = json.loads(json.dumps(jeu['source']))
    n = next(x for x in src['noeuds'] if x.get('cin'))
    n['cin'] = 'A' + 'B' + '123456'                    # forme réelle construite par concaténation
    chemin = str(tmp_path / 'globale.json')
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(src, f, ensure_ascii=False)
    assert pg.publier(chemin, str(tmp_path / 'pub'))['fictif'] is False


def test_un_style_d_arete_inconnu_arrete_la_publication(jeu, tmp_path):
    src = json.loads(json.dumps(jeu['source']))
    src['aretes'][0]['style'] = 'nouveau style'
    chemin = str(tmp_path / 'globale.json')
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(src, f, ensure_ascii=False)
    with pytest.raises(ValueError):
        pg.publier(chemin, str(tmp_path / 'pub'))
    assert not os.path.exists(str(tmp_path / 'pub'))         # rien d'écrit


# ---- tout ce que carte_globale.py peut produire --------------------------------------------------------------------
# styles d'arête : rôle actuel ou terminé (« ancien »), annonce mélangée (« melange »), rôle confirmé ou lu dans un
# dossier (« dossier »), rapprochements (« rap », « certain ») — carte_globale.py, lignes 117-119, 125, 139, 250-254, 270
STYLES_PRODUITS = sorted({'', 'ancien', 'melange', 'ancien melange', 'dossier', 'ancien dossier', 'melange dossier',
                          'ancien melange dossier', 'rap', 'certain'})


def publier_modifiee(jeu, tmp_path, modifier):
    src = json.loads(json.dumps(jeu['source']))
    modifier(src)
    chemin = str(tmp_path / 'globale.json')
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(src, f, ensure_ascii=False)
    pub = str(tmp_path / 'pub')
    pg.publier(chemin, pub)
    with open(os.path.join(pub, 'geometrie.json'), encoding='utf-8') as f:
        texte = f.read()
    con = sqlite3.connect(os.path.join(pub, 'identites.sqlite'))
    return src, json.loads(texte), texte, con


def test_tous_les_styles_que_carte_globale_produit_sont_publies(jeu, tmp_path):
    if len(jeu['source']['aretes']) < len(STYLES_PRODUITS):
        pytest.skip('pas assez d\'arêtes dans ce jeu')

    def modifier(src):
        for a, style in zip(src['aretes'], STYLES_PRODUITS):
            a['style'] = style
    _src, geo, _texte, _con = publier_modifiee(jeu, tmp_path, modifier)
    assert set(STYLES_PRODUITS) <= {a['style'] for a in geo['aretes']}


def test_dossiers_et_regles_af_publies_sans_reference_en_couche1(jeu, tmp_path):
    ref_dossier = 'ZZ26R' + '0001'

    def modifier(src):
        a0, a1, a2 = src['aretes'][:3]
        a0.update(lib=f"gérant d'après le dossier {ref_dossier}", style='dossier')
        a1.update(lib=f'associé (06/2025) · confirmé par le dossier {ref_dossier}', style='dossier')
        a2.update(lib='rapprochement AF02b (certain, même CIN, dossier)', style='certain')
        n = next(x for x in src['noeuds'] if x['t'] == 'personne')
        n.update(o='d', nd=2, dos=f'{ref_dossier} (conforme), ZZ26R0002 (suspect)')
    src, geo, texte, con = publier_modifiee(jeu, tmp_path, modifier)
    assert 'ZZ26R' not in texte
    ref = dict(con.execute('SELECT indice, ref_id FROM noeud'))
    ids = [n['id'] for n in src['noeuds']]
    libs = {(ref[a['a']], ref[a['b']]): a['lib'] for a in geo['aretes']}
    a0, a1, a2 = src['aretes'][:3]
    assert libs[(ids[a0['a']], ids[a0['b']])] == ''
    assert libs[(ids[a1['a']], ids[a1['b']])] == 'associé'
    assert libs[(ids[a2['a']], ids[a2['b']])] == 'rapprochement AF02b (certain, même CIN, dossier)'
    n = next(x for x in src['noeuds'] if x.get('dos'))
    i = next(k for k, r in ref.items() if r == n['id'])
    assert geo['noeuds'][i]['o'] == 'd' and 'dos' not in geo['noeuds'][i] and 'nd' not in geo['noeuds'][i]
    assert con.execute('SELECT nb_dossiers, dossiers FROM fiche_globale WHERE indice = ?', (i,)).fetchone() == (2, n['dos'])
