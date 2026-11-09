"""Tests de publier_carte.py, uniquement sur des données fictives (jeu du kit et données générées)."""

import hashlib
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


# ---- reprise après incident ------------------------------------------------------------------------------------
def test_un_arret_en_cours_laisse_la_publication_precedente_intacte(jeu, tmp_path, monkeypatch):
    dossier = str(tmp_path / 'pub')
    avant = pc.publier(jeu['base'], jeu['chaines'], dossier)

    def panne(*_a, **_k):
        raise RuntimeError('panne simulée pendant l\'écriture du manifeste')

    monkeypatch.setattr(pc, 'manifeste', panne)
    with pytest.raises(RuntimeError):
        pc.publier(jeu['base'], jeu['chaines'], dossier)
    with open(os.path.join(dossier, 'manifeste.json'), encoding='utf-8') as f:
        assert json.load(f) == avant
    for nom, h in avant['fichiers'].items():
        assert pc.empreinte(os.path.join(dossier, nom)) == h, f'{nom} remplacé sans manifeste'
    assert sorted(os.listdir(tmp_path)) == ['pub'], 'dossier temporaire laissé derrière'


def test_publier_deux_fois_donne_une_publication_complete_et_coherente(jeu, tmp_path):
    dossier = str(tmp_path / 'pub')
    pc.publier(jeu['base'], jeu['chaines'], dossier)
    m = pc.publier(jeu['base'], jeu['chaines'], dossier)
    assert sorted(os.listdir(dossier)) == ['geometrie.json', 'identites.sqlite', 'manifeste.json']
    for nom, h in m['fichiers'].items():
        assert pc.empreinte(os.path.join(dossier, nom)) == h


# ---- référence : la publication du kit, relue à la main une fois -------------------------------------------------
sys.path.insert(0, os.path.join(RACINE, 'outils'))
import empreinte_comportement as ec  # noqa: E402


def test_publication_du_kit_conforme_a_la_reference(jeu):
    """Tout ce que la publication du kit contient, indices ramenés aux identifiants internes.

    Référence : pipeline/tests/attendu_kit.json. Si un changement voulu la modifie, la régénérer et la relire.
    """
    if os.path.basename(os.path.dirname(jeu['pub'])).startswith('genere'):
        pytest.skip('référence établie sur le jeu du kit')
    with open(os.path.join(ICI, 'attendu_kit.json'), encoding='utf-8') as f:
        attendu = json.load(f)
    assert json.loads(json.dumps(ec.forme_canonique(jeu['pub']), ensure_ascii=False)) == attendu


# ---- filtre des libellés de rôle ---------------------------------------------------------------------------------
@pytest.mark.parametrize('libelle', ['gérant', 'associé', 'associé (33.3 %)', 'associé (50 %)', 'ancien gérant',
                                     'associée de', 'cédant', 'cité', 'liquidateur', 'cessionnaire (10 %)'])
def test_libelle_de_role_connu_passe_en_couche1(libelle):
    assert pc.role_couche1(libelle) == libelle


@pytest.mark.parametrize('libelle', ['gérant TAZI', 'associé de FASSI', 'TAZI', 'محمد', 'gérant (ZZ900001)',
                                     'associé (33.3 %) X', ' gérant', 'GÉRANT', 'mandataire', '', None])
def test_libelle_inconnu_ou_porteur_d_identite_reste_en_couche2(libelle):
    assert pc.role_couche1(libelle) == ''


# ---- garde-fous : une entrée incohérente arrête la publication -----------------------------------------------------
def chaines_alterees(jeu, tmp_path, alterer):
    donnees = json.loads(json.dumps(jeu['source']))
    alterer(donnees)
    chemin = str(tmp_path / 'chaines.json')
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(donnees, f, ensure_ascii=False)
    return chemin


def test_cle_de_noeud_inconnue_arrete_la_publication(jeu, tmp_path):
    def alterer(d):
        d[0]['noeuds']['X9'] = d[0]['noeuds'].pop('R')
    with pytest.raises(SystemExit, match=r"^Clé de nœud inattendue dans chaines\.json : 'X9'$"):
        pc.publier(jeu['base'], chaines_alterees(jeu, tmp_path, alterer), str(tmp_path / 'pub'))
    assert not os.path.exists(tmp_path / 'pub')


def test_type_d_inscrit_incoherent_arrete_la_publication(jeu, tmp_path):
    def alterer(d):
        x = d[0]
        x['id'] = ('PM' if x['id'].startswith('PP') else 'PP') + x['id'][2:]
    with pytest.raises(SystemExit, match=r"^Type d'inscrit incohérent entre chaines\.json et la base\.$"):
        pc.publier(jeu['base'], chaines_alterees(jeu, tmp_path, alterer), str(tmp_path / 'pub'))


def test_societe_racine_differente_arrete_la_publication(jeu, tmp_path):
    def alterer(d):
        pm = next(x for x in d if x['type'] == 'PM')
        pm['noeuds']['R']['rc'] = '1'
    with pytest.raises(SystemExit, match=r'^Société racine introuvable pour une société inscrite : '
                                         r'la règle de chaines_dessin a changé, à revoir\.$'):
        pc.publier(jeu['base'], chaines_alterees(jeu, tmp_path, alterer), str(tmp_path / 'pub'))


# ---- manifeste, empreintes, droits -------------------------------------------------------------------------------
def test_empreinte_globale_et_horodatage(jeu):
    m = jeu['manifeste']
    attendue = hashlib.sha256((m['fichiers']['geometrie.json'] + m['fichiers']['identites.sqlite']).encode())
    assert m['empreinte'] == attendue.hexdigest()
    assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', m['date_publication'])
    assert m['date_publication'] == jeu['geo']['construction']['date'] or m['date_publication'] >= \
        jeu['geo']['construction']['date']
    with open(os.path.join(jeu['pub'], 'manifeste.json'), encoding='utf-8') as f:
        assert json.load(f) == m


def test_empreinte_d_un_gros_fichier(tmp_path):
    chemin = tmp_path / 'gros'
    contenu = os.urandom(3 * (1 << 20) + 17)
    chemin.write_bytes(contenu)
    assert pc.empreinte(str(chemin)) == hashlib.sha256(contenu).hexdigest()


def test_couche2_lisible_seulement_par_le_proprietaire_et_son_groupe(jeu):
    assert os.stat(os.path.join(jeu['pub'], 'identites.sqlite')).st_mode & 0o777 == 0o640
    assert os.stat(jeu['pub']).st_mode & 0o777 == 0o750


def test_est_fictif():
    assert pc.est_fictif(['ZZ1', 'zz2'])
    assert not pc.est_fictif(['ZZ1', 'AB2'])
    assert not pc.est_fictif([])


def test_composantes_sur_une_longue_chaine_et_des_isoles():
    aretes = [(k, k + 1) for k in range(0, 40)] + [(50, 45)]
    c = pc.composantes(60, aretes)
    assert len(set(c[:41])) == 1 and c[45] == c[50] and c[45] != c[0]
    assert len(set(c)) == 1 + 1 + (60 - 41 - 2)
    premiers = list(dict.fromkeys(c))                    # numéros attribués dans l'ordre d'apparition
    assert premiers == list(range(len(premiers)))


# ---- ligne de commande -------------------------------------------------------------------------------------------
def test_ligne_de_commande(jeu, tmp_path):
    sortie = tmp_path / 'pub'
    r = subprocess.run([sys.executable, os.path.join(PIPELINE, 'publier_carte.py'), '--base', jeu['base'],
                        '--chaines', jeu['chaines'], '--sortie', str(sortie)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = json.loads((sortie / 'manifeste.json').read_text(encoding='utf-8'))
    taille = os.path.getsize(sortie / 'geometrie.json') / 1e6
    assert r.stdout.splitlines() == [
        f"  publication : {m['noeuds']} nœuds, {m['inscrits_personnes']} personnes et {m['inscrits_societes']} "
        f"sociétés inscrites, géométrie {taille:.2f} Mo, fictive",
        f"  empreinte : {m['empreinte'][:16]}…"]


def test_ligne_de_commande_signale_des_donnees_reelles(jeu, tmp_path):
    base = str(tmp_path / 'base.sqlite')
    shutil.copy(jeu['base'], base)
    con = sqlite3.connect(base)
    con.execute("UPDATE bl_entite SET cin = 'AB123456' WHERE cin IS NOT NULL")
    con.commit()
    r = subprocess.run([sys.executable, os.path.join(PIPELINE, 'publier_carte.py'), '--base', base,
                        '--chaines', jeu['chaines'], '--sortie', str(tmp_path / 'pub')], capture_output=True, text=True)
    assert r.stdout.splitlines()[0].endswith(' Mo, DONNÉES RÉELLES')


@pytest.mark.parametrize('manque', ['--base', '--chaines', '--sortie'])
def test_ligne_de_commande_exige_ses_trois_arguments(jeu, tmp_path, manque):
    args = {'--base': jeu['base'], '--chaines': jeu['chaines'], '--sortie': str(tmp_path / 'pub')}
    del args[manque]
    r = subprocess.run([sys.executable, os.path.join(PIPELINE, 'publier_carte.py'),
                        *[x for kv in args.items() for x in kv]], capture_output=True, text=True)
    assert r.returncode == 2 and manque in r.stderr


# ---- règles fines, sur une entrée écrite à la main ---------------------------------------------------------------
def entree_main():
    return dict(id='PP:P:ZZ1', type='PP', compte={'1': 1, '2': 1, '3': 0, '4': 0}, alerte=True, chaines=[
        dict(texte='…', distance=2, fiab=0.5, force=0.2, bl='X (inscrit)'),
        dict(texte='…', distance=1, fiab=1.0, force=0.4, bl='')],
        noeuds={'R': dict(t='PP', nom='A', d=0, bl=''),
                'S7': dict(t='PM', nom='B', d=1, rc='123', trib='RABAT', ville='RABAT', dern='2025-01-02',
                           url='https://exemple.invalid/annonce/1', bl='', diss=1),
                'I3': dict(t='PP', nom='C', bl='inscrit')},          # sans « d »
        aretes=[dict(a='R', b='S7', lib='gérant', pont='', fiab=1.0, force=0.4, style='rap'),
                dict(a='S7', b='I3', lib='associé', pont='', fiab=0.5, force=0.2, style='inconnu')])


def test_carte_couche1_drapeaux_profondeur_et_style():
    ind = {'R': 10, 'S7': 11, 'I3': 12}.__getitem__
    c = pc.carte_couche1(entree_main(), ind, certain=True)
    assert c == dict(type='PP', compte={'1': 1, '2': 1, '3': 0, '4': 0}, alerte=True, certain=True,
                     noeuds=[[10, 0, 0, 0], [11, 1, 0, 1], [12, 0, 1, 0]],
                     aretes=[[10, 11, 'gérant', 1, 1.0, 0.4], [11, 12, 'associé', 0, 0.5, 0.2]],
                     chaines=[[2, 0.5, 0.2, 1], [1, 1.0, 0.4, 0]])


def test_chaine_complete_remplace_les_cles_par_les_indices():
    ind = {'R': 10, 'S7': 11, 'I3': 12}.__getitem__
    x = entree_main()
    c = pc.chaine_complete(x, ind, 10)
    assert c['id'] == 10 and c['racine'] == 10 and set(c['noeuds']) == {'10', '11', '12'}
    assert c['noeuds']['11'] == x['noeuds']['S7']
    assert [(a['a'], a['b'], a['lib']) for a in c['aretes']] == [(10, 11, 'gérant'), (11, 12, 'associé')]
    assert c['chaines'] == x['chaines'] and c['type'] == 'PP' and c['compte'] == x['compte']


def test_deux_aretes_de_meme_force_la_premiere_vue_l_emporte():
    x1 = dict(aretes=[dict(a='A', b='B', lib='gérant', fiab=1.0, force=0.3, style='')])
    x2 = dict(aretes=[dict(a='B', b='A', lib='associé', fiab=1.0, force=0.3, style='')])
    cartes = [(0, None, None, {'A': 1, 'B': 2})] * 2
    liens = pc.fusionner_liens([(x1, None, None), (x2, None, None)], cartes)
    assert liens == {(1, 2): dict(libelle='gérant', style=0, fiab=1.0, force=0.3)}


def test_fiche_inscrit_complete_par_la_carte_quand_la_liste_noire_ne_dit_rien():
    class Idx:
        ref_de = ('E:1', 'S:2')
    identite = {0: dict(nom='nom carte', rc='111', tribunal='FES', ville='FES', url='u0'),
                1: dict(nom='société', rc='222', tribunal='RABAT', ville='RABAT', derniere='2025-01-01',
                        url='https://exemple.invalid/annonce/2', dissoute=1)}
    inscrits = {'E:1': ('NOM BL', 'ZZ1', None, None, None, 'BLACKLIST', 'motif')}
    lignes = pc.lignes_identite(Idx, identite, inscrits, certains={0})
    assert lignes == [
        (0, 'NOM BL', None, 'ZZ1', '111', 'FES', 'FES', None, 'u0', None, 'BLACKLIST', 'motif', 1),
        (1, 'société', None, None, '222', 'RABAT', 'RABAT', '2025-01-01', 'https://exemple.invalid/annonce/2', 1,
         None, None, 0)]


def test_les_champs_de_la_liste_noire_priment_sur_la_carte():
    class Idx:
        ref_de = ('E:1',)
    lignes = pc.lignes_identite(Idx, {0: dict(rc='111', tribunal='FES', ville='FES')},
                                {'E:1': ('NOM', None, '999', 'CASABLANCA', 'RABAT', None, None)}, certains=set())
    assert lignes[0][4:7] == ('999', 'CASABLANCA', 'RABAT')


def test_style_inconnu_vaut_role_simple():
    assert pc.style_de(dict(style='inconnu')) == 0
    assert [pc.style_de(dict(style=s)) for s in ('', 'rap', 'pont')] == [0, 1, 2]


def test_fusion_des_noeuds_fiche_ville_et_liste_noire():
    class Idx:
        def types(self):
            return [pc.T_INSCRIT_PP, pc.T_SOCIETE, pc.T_PERSONNE, pc.T_SOCIETE]

        def __len__(self):
            return 4
    x = entree_main()
    autre = dict(noeuds={'S7': dict(nom='autre nom', ville='FES', bl='société inscrite'),
                         'S9': dict(nom='D', ville=None)})
    cartes = [(0, None, None, {'R': 0, 'S7': 1, 'I3': 2}), (5, None, None, {'S7': 1, 'S9': 3})]
    bl, ville, identite = pc.fusionner_noeuds(Idx(), [(x, None, None), (autre, None, None)], cartes)
    assert bl == [1, 1, 1, 0]                     # inscrit d'office ; S7 inscrite dans la 2e carte ; I3 « inscrit »
    assert ville == [None, 'RABAT', None, None]
    assert identite[1] == dict(nom='B', rc='123', tribunal='RABAT', ville='RABAT', derniere='2025-01-02',
                               url='https://exemple.invalid/annonce/1', dissoute=1)   # la première carte l'emporte
    assert identite[3]['nom'] == 'D' and identite[2]['url'] is None
