"""Base client : résumé agrégé, recherche, fiche, dossier, réseau. Rôles, non-fuite, indices opaques. Fictif."""
import json
import os
import re
import shutil
import sqlite3
import sys

import pytest

from conftest import RACINE, connecte

STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure', 'reference', 'champs_par_type_prod.csv')
LIVREE = os.path.join(RACINE, 'jeu_essai', 'demo', 'base_demo.sqlite.gz')
CARTE_LIVREE = os.path.join(RACINE, 'jeu_essai', 'demo', 'carte_globale_demo.tar.gz')
pytestmark = pytest.mark.skipif(not os.path.exists(STRUCTURE) and not os.path.exists(LIVREE),
                                reason='ni structure de Kamal ni base de démonstration livrée')
MOTIFS = (re.compile(r'\bZZ\d{4,}'), re.compile(r'999\d{8,}'), re.compile(r'\b(pp|pm)_[0-9a-f]{16}\b'))


@pytest.fixture(scope='session')
def base_demo(tmp_path_factory):
    """Base générée (structure de Kamal présente), sinon la base livrée dans le dépôt, décompressée."""
    chemin = str(tmp_path_factory.mktemp('demo') / 'base_demo.sqlite')
    if os.path.exists(STRUCTURE):
        sys.path.insert(0, os.path.join(RACINE, 'outils', 'demo'))
        import construire_demo
        construire_demo.construire(chemin, n_dossiers=300, n_societes=300, graine=20261116)
    else:
        import gzip
        with gzip.open(LIVREE, 'rb') as source, open(chemin, 'wb') as cible:
            shutil.copyfileobj(source, cible)
    return chemin


@pytest.fixture(scope='session')
def carte_demo(base_demo, tmp_path_factory):
    """Carte globale publiée du même jeu que `base_demo` : générée avec lui, sinon celle livrée avec la base livrée."""
    d = str(tmp_path_factory.mktemp('carte_demo') / 'carte')
    if os.path.exists(STRUCTURE):
        sys.path.insert(0, os.path.join(RACINE, 'outils', 'demo'))
        import construire_demo
        construire_demo.construire(None, n_dossiers=300, n_societes=300, graine=20261116, carte=d)
    else:
        import tarfile
        os.makedirs(d)
        with tarfile.open(CARTE_LIVREE) as t:
            t.extractall(d, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
    return d


@pytest.fixture
def avec_base(client_avec, base_demo):
    def ouvrir(**surcharges):
        return client_avec(CARTE_BASE_CLIENT=base_demo, CARTE_FRONT=os.path.join(RACINE, 'front'), **surcharges)
    return ouvrir


def noms_du_jeu(base):
    cx = sqlite3.connect(base)
    return {n for (n,) in cx.execute('SELECT nom FROM c2_personne WHERE nom IS NOT NULL LIMIT 300')}


def test_resume_agrege_pour_la_direction_sans_nom_ni_chiffre_sous_cinq(avec_base, base_demo):
    with avec_base() as (c, etat):
        connecte(c, etat, 'dir', 'DIRECTION')
        r = c.get('/api/base/resume')
        assert r.status_code == 200
        corps = r.json()
        assert corps['clients'] >= 5 and corps['dossiers'] >= 5 and corps['mise_a_jour']
        nombres = [corps[k] for k in ('clients', 'dossiers', 'dossiers_lies', 'societes_registre', 'inscrits')]
        for bloc in ('produits', 'csp', 'niveaux', 'incoherences'):
            nombres += [x['nombre'] for x in corps[bloc]]
        assert all(n == '< 5' or n == 0 or n >= 5 for n in nombres)
        texte = r.text
        assert not any(m.search(texte) for m in MOTIFS) and not any(n in texte for n in noms_du_jeu(base_demo))
        assert r.headers['Content-Security-Policy'].startswith("default-src 'self'")


@pytest.mark.parametrize('role', ['DIRECTION', 'AGENCE', 'ADMIN'])
def test_noms_fiches_dossiers_reseau_refuses_hors_cellule_fraude(avec_base, role):
    with avec_base() as (c, etat):
        connecte(c, etat, 'u', role)
        assert c.post('/api/base/clients', json={}).status_code == 403
        for chemin in ('/api/base/clients/1', '/api/base/dossiers/1', '/api/base/reseau/1', '/api/base/carte/1'):
            assert c.get(chemin).status_code == 403, chemin


def test_sans_session_tout_est_refuse(avec_base):
    with avec_base() as (c, etat):
        assert c.get('/api/base/resume').status_code == 401
        assert c.post('/api/base/clients', json={}).status_code == 401


def test_recherche_par_le_corps_filtres_pagination_et_journal_sans_requete(avec_base, base_demo):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        tout = c.post('/api/base/clients', json={'taille': 200}).json()
        assert tout['total'] > 50 and len(tout['items']) == 200
        premier = tout['items'][0]
        assert set(premier) == {'indice', 'nom', 'type', 'dossiers', 'produits', 'derniere_demande', 'ville',
                                'inscrit', 'niveau', 'niveau_libelle', 'incoherences', 'revenu'}
        assert premier['niveau'] in ('critique', 'majeure')         # trié du plus grave au moins grave
        nom = premier['nom']
        trouves = c.post('/api/base/clients', json={'texte': nom[:6].lower()}).json()
        assert any(x['indice'] == premier['indice'] for x in trouves['items'])
        critiques = c.post('/api/base/clients', json={'niveau': 'critique'}).json()
        assert critiques['total'] >= 1 and all(x['niveau'] == 'critique' for x in critiques['items'])
        page2 = c.post('/api/base/clients', json={'page': 2, 'taille': 10}).json()
        assert page2['items'] == tout['items'][10:20]
        from conftest import tout_le_journal
        assert nom not in tout_le_journal(etat) and nom[:6].lower() not in tout_le_journal(etat)
        assert c.post('/api/base/clients', json={'texte': 'x' * 81}).status_code == 422
        assert c.post('/api/base/clients', json={'inconnu': 1}).status_code == 422


def test_tri_de_la_liste_des_clients_au_choix(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')

        def liste(tri):
            return c.post('/api/base/clients', json={'taille': 200, 'tri': tri}).json()['items']

        recents = [x['derniere_demande'] for x in liste('recent') if x['derniere_demande']]
        assert recents and recents == sorted(recents, reverse=True)
        anciens = [x['derniere_demande'] for x in liste('ancien') if x['derniere_demande']]
        assert anciens == sorted(anciens)
        noms = [x['nom'].upper() for x in liste('alpha')]
        assert noms == sorted(noms)
        inverses = [x['nom'].upper() for x in liste('alpha_inverse')]
        assert inverses == sorted(inverses, reverse=True) and inverses[0] >= noms[-1]
        nb = [x['dossiers'] for x in liste('dossiers')]
        assert nb == sorted(nb, reverse=True)
        revenus = [x['revenu'] for x in liste('revenu') if x['revenu'] is not None]
        assert revenus == sorted(revenus, reverse=True)
        p1 = c.post('/api/base/clients', json={'tri': 'alpha', 'page': 1, 'taille': 10}).json()['items']
        p2 = c.post('/api/base/clients', json={'tri': 'alpha', 'page': 2, 'taille': 10}).json()['items']
        assert p1[-1]['nom'].upper() <= p2[0]['nom'].upper()      # le tri s'applique avant la pagination
        assert c.post('/api/base/clients', json={'tri': 'inconnu'}).status_code == 422


def test_carte_reseau_servie_sans_valeur_d_identifiant_et_journalisee(avec_base, base_demo):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        clients = c.post('/api/base/clients', json={'taille': 200, 'niveau': 'majeure'}).json()['items']
        lie = next(x for x in clients if x['type'] == 'personne')
        r = c.get(f'/api/base/reseau/{lie["indice"]}')
        assert r.status_code == 200
        carte = r.json()
        ids = {n['id'] for n in carte['noeuds']}
        assert [n for n in carte['noeuds'] if n.get('depart')][0]['id'] == lie['indice']
        assert any(n['inscrit'] for n in carte['noeuds'])
        assert all(l['de'] in ids and l['vers'] in ids for l in carte['liens'])
        assert all(n['type'] != 'identifiant' or not any(ch.isdigit() for ch in n['nom']) for n in carte['noeuds'])
        assert not any(m.search(r.text) for m in MOTIFS)   # ni référence, ni RIB ou identifiant, ni identifiant interne
        from conftest import tout_le_journal
        journal = tout_le_journal(etat)
        assert 'reseau' in journal and 'noms' in journal              # consultation et tiers nommés journalisés
        assert lie['nom'] not in journal
        assert c.get('/api/base/reseau/1').status_code == 404


def _voisins_affiches(carte):
    """Voisins de chaque fiche dans le dessin, un nœud d'identifiant partagé valant un pas (A – RIB – B)."""
    ident = {n['id'] for n in carte['noeuds'] if n['type'] == 'identifiant'}
    adj = {}
    for l in carte['liens']:
        adj.setdefault(l['de'], set()).add(l['vers'])
        adj.setdefault(l['vers'], set()).add(l['de'])
    sortie = {}
    for n in carte['noeuds']:
        if n['type'] == 'identifiant':
            continue
        v = set()
        for x in adj.get(n['id'], ()):
            v |= (adj[x] - {n['id']}) if x in ident else {x}
        sortie[n['id']] = v
    return sortie


def _clients_relies(c):
    relies = []
    for niveau in ('critique', 'majeure', 'mineure'):
        page = 1
        while True:
            r = c.post('/api/base/clients', json={'niveau': niveau, 'taille': 200, 'page': page}).json()
            relies += r['items']
            if page * 200 >= r['total']:
                break
            page += 1
    return relies


def test_carte_reseau_garde_tout_inscrit_atteignable_meme_derriere_un_noeud_replie(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        inscrits = lambda carte: {n['id'] for n in carte['noeuds'] if n['inscrit']}
        for indice in sorted(b.indice_fiche.values()):                   # toutes les fiches de la base
            assert inscrits(b.reseau(indice)) == inscrits(b.reseau(indice, plafond=10 ** 6, limite=10 ** 6)), indice


def test_carte_reseau_compte_exactement_ce_qui_n_est_pas_affiche(avec_base, base_demo):
    """Pour chaque nœud déployé : voisins affichés (avec leur lien) + `autres` = tous ses voisins. Vrai aussi quand la
    limite du nombre de nœuds s'applique."""
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        cx = sqlite3.connect(base_demo)
        gros = cx.execute("SELECT vers, count(DISTINCT de) n FROM c5_arete WHERE type = 'role' GROUP BY vers "
                          'ORDER BY n DESC LIMIT 1').fetchone()
        salarie = cx.execute("SELECT de FROM c5_arete WHERE type = 'role' AND vers = ? LIMIT 1", (gros[0],)).fetchone()[0]
        departs = [b.indice_fiche[salarie], b.indice_fiche[gros[0]]] + sorted(b.indice_fiche.values())
        for depart in departs:
            for limite in ((120, 25) if depart in departs[:2] else (120,)):
                carte = b.reseau(depart, limite=limite)
                complet = _voisins_affiches(b.reseau(depart, plafond=10 ** 6, limite=10 ** 6))
                affiches = _voisins_affiches(carte)
                presents = set(affiches)
                for n in carte['noeuds']:
                    if n['type'] == 'identifiant' or n['niveau'] >= 2:
                        continue                              # seuls les nœuds déployés (niveaux 0 et 1) comptent
                    tous = complet[n['id']]
                    assert affiches[n['id']] == tous & presents, (depart, limite)     # voisin présent = lien dessiné
                    assert n['autres'] == len(tous - presents), (depart, limite)      # le reste est compté
        noeud = next(n for n in b.reseau(b.indice_fiche[salarie])['noeuds'] if n['id'] == b.indice_fiche[gros[0]])
        assert noeud['autres'] > 150                          # l'employeur de 200 salariés est replié


def _voisins_sql(cx, fiche, cache):
    """Voisinage d'une fiche recalculé en SQL, sans passer par `reseau()` : rôles dans les deux sens, et fiches qui
    partagent un identifiant porté par 30 fiches au plus, elle comprise."""
    if fiche not in cache:
        v = {r[0] for r in cx.execute("SELECT vers FROM c5_arete WHERE type = 'role' AND de = ? UNION "
                                      "SELECT de FROM c5_arete WHERE type = 'role' AND vers = ?", (fiche, fiche))}
        for (noeud,) in cx.execute("SELECT DISTINCT vers FROM c5_arete WHERE type = 'identifiant' AND de = ?",
                                   (fiche,)).fetchall():
            porteurs = {r[0] for r in cx.execute('SELECT DISTINCT de FROM c5_arete WHERE vers = ?', (noeud,))}
            if len(porteurs) <= 30:
                v |= porteurs
        cache[fiche] = v - {fiche}
    return cache[fiche]


def test_carte_reseau_coherente_avec_un_voisinage_recalcule_sur_toutes_les_fiches(avec_base, base_demo):
    """Pour chaque fiche, avec les réglages par défaut et avec de tout petits plafonds : aucun lien vers une fiche
    absente du dessin ; distances justes ; tout inscrit à deux liens au plus dessiné ; pour chaque nœud déployé,
    voisins dessinés avec leur lien et `autres` exact, d'après le voisinage recalculé en SQL."""
    with avec_base() as (c, etat):
        b = etat.base_client
        cx = sqlite3.connect(base_demo)
        cache = {}
        for fiche, indice in sorted(b.indice_fiche.items()):
            n1 = _voisins_sql(cx, fiche, cache)
            atteints = {fiche} | n1 | {x for v in n1 for x in _voisins_sql(cx, v, cache)}
            for reglage in ({}, {'plafond': 2, 'limite': 6}):
                carte = b.reseau(indice, **reglage)
                fiches = {b.fiche_de[n['id']]: n for n in carte['noeuds'] if n['type'] != 'identifiant'}
                ids = {n['id'] for n in carte['noeuds']}
                assert all(l['de'] in ids and l['vers'] in ids for l in carte['liens']), (indice, reglage)
                assert {f for f, n in fiches.items() if n['inscrit']} == atteints & b.inscrits, (indice, reglage)
                affiches = _voisins_affiches(carte)
                for f, n in fiches.items():
                    assert n['niveau'] == (0 if f == fiche else 1 if f in n1 else 2), (indice, reglage)
                    if n['niveau'] <= 1:
                        tous = _voisins_sql(cx, f, cache)
                        assert {b.fiche_de[i] for i in affiches[n['id']]} == tous & set(fiches), (indice, reglage)
                        assert n['autres'] == len(tous - set(fiches)), (indice, reglage)


def test_carte_reseau_ne_lit_que_les_fiches_dessinees(avec_base, base_demo):
    """Le coût d'une carte suit ce qu'elle dessine, pas la taille du voisinage : depuis l'employeur de 200 salariés, le
    voisinage de chaque salarié n'est pas lu (en données réelles, un employeur peut en déclarer des milliers)."""
    with avec_base() as (c, etat):
        b = etat.base_client
        cx = sqlite3.connect(base_demo)
        gros = cx.execute("SELECT vers, count(DISTINCT de) n FROM c5_arete WHERE type = 'role' GROUP BY vers "
                          'ORDER BY n DESC LIMIT 1').fetchone()[0]
        b.reseau(b.indice_fiche[gros])                     # premier appel : ce qui se calcule une fois est fait
        requetes, ouvrir = [], b.connexion

        def connexion():
            cx2 = ouvrir()
            cx2.set_trace_callback(requetes.append)
            return cx2
        b.connexion = connexion
        carte = b.reseau(b.indice_fiche[gros])
        dessinees = sum(1 for n in carte['noeuds'] if n['type'] != 'identifiant')
        # quelques requêtes par fiche dessinée (son voisinage si elle est déployée, son nom), jamais une par collègue
        assert dessinees >= 10 and len(requetes) <= 6 * dessinees + 20, (dessinees, len(requetes))


def test_carte_reseau_stable_sans_valeur_et_client_isole(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        relie = _clients_relies(c)[0]['indice']
        assert b.reseau(relie) == b.reseau(relie)            # même dessin d'un appel à l'autre
        carte = b.reseau(relie)
        for n in carte['noeuds']:
            if n['type'] == 'identifiant':
                assert n['nom'] in ('RIB', 'LOGEMENT', 'SIEGE') and re.fullmatch(r'id\d+', n['id'])
        isole = next(i for i in sorted(b.indice_fiche.values()) if len(b.reseau(i)['noeuds']) == 1)
        assert b.reseau(isole)['liens'] == []


def test_carte_reseau_a_son_propre_droit_et_son_action_de_journal(avec_base):
    from app.roles import DROITS, Role
    assert DROITS['base.reseau'] == frozenset({Role.ANALYSTE})
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        relie = _clients_relies(c)[0]['indice']
        assert c.get(f'/api/base/reseau/{relie}').status_code == 200
        from conftest import tout_le_journal
        assert 'reseau' in tout_le_journal(etat)


def test_fiche_dossier_et_reseau_par_indice_opaque(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        clients = c.post('/api/base/clients', json={'taille': 200}).json()['items']
        lie = next(x for x in clients if x['niveau'] in ('majeure', 'mineure') and x['type'] == 'personne')
        f = c.get(f'/api/base/clients/{lie["indice"]}').json()
        assert f['identite']['nom'] == lie['nom'] and f['dossiers'] and f['chemins']
        assert {'identite', 'alias', 'adresses', 'sources', 'dossiers', 'societes', 'personnes', 'revenus',
                'comptes', 'vehicules', 'chemins'} <= set(f)
        assert all(r['rib'].startswith('••• ') for r in f['comptes'])
        assert len({r['rib'] for r in f['comptes']}) == len(f['comptes'])     # un compte par RIB
        assert f['donnees'] and all(x['pieces'] and x['contexte'] for x in f['donnees'] if x['demandeur'])
        faits = [fait for x in f['donnees'] for p in x['pieces'] for fait in p['faits']]
        assert len(faits) > 20 and {'cle', 'valeur', 'origine', 'statut'} == set(faits[0])
        assert all(not (fait['valeur'] or '').startswith('999') or fait['cle'] not in ('rib', 'numero_compte')
                   for fait in faits)
        chemin = f['chemins'][0]
        assert chemin['inscrit']['indice'] and chemin['etapes']
        d = c.get(f'/api/base/dossiers/{f["dossiers"][0]["indice"]}').json()
        assert d['entete']['reference'].startswith('ZZ') and d['pieces'] and d['parties']
        assert {'charges', 'operations', 'incoherences', 'identifiants'} <= set(f)
        assert all(r['dossier'] for r in f['revenus'] if r['nature'] == 'verifie')
        assert all(set(i) == {'type', 'valeur', 'dossier'} for i in f['identifiants'])
        assert all(i['type'] != 'RIB' for i in f['identifiants'])            # le RIB reste masqué, dans les comptes
        texte = json.dumps(f)
        assert not re.search(r'999\d{18,}', texte) and not MOTIFS[2].search(texte)   # ni RIB complet, ni identifiant interne
        assert c.get('/api/base/clients/1').status_code == 404
        assert c.get('/api/base/dossiers/abc').status_code == 422


def test_indices_tires_au_hasard_a_chaque_chargement(client_avec, base_demo):
    with client_avec(CARTE_BASE_CLIENT=base_demo) as (_, a), client_avec(CARTE_BASE_CLIENT=base_demo) as (_, b):
        assert sorted(a.base_client.indice_fiche.items())[:20] != sorted(b.base_client.indice_fiche.items())[:20]


def test_base_non_fictive_refusee_sans_le_garde_fou(client_avec, base_demo, tmp_path):
    copie = str(tmp_path / 'base.sqlite')
    shutil.copy(base_demo, copie)
    cx = sqlite3.connect(copie)
    cx.execute("UPDATE c2_personne SET cin = ? WHERE rowid = (SELECT min(rowid) FROM c2_personne WHERE cin IS NOT NULL)",
               ('AB' + '123456',))
    cx.commit()
    cx.close()
    with pytest.raises(PermissionError):
        with client_avec(CARTE_BASE_CLIENT=copie):
            pass


def test_pages_servies_a_la_racine_sans_ressource_externe(avec_base):
    with avec_base() as (c, etat):
        r = c.get('/')
        assert r.status_code == 200 and '<html' in r.text.lower()
        assert "default-src 'self'" in r.headers['Content-Security-Policy']
    for racine, _, fichiers in os.walk(os.path.join(RACINE, 'front')):
        for nom in fichiers:
            texte = open(os.path.join(racine, nom), encoding='utf-8').read().replace('http://www.w3.org/2000/svg', '')
            assert not re.search(r'(https?:)?//[a-z0-9.-]+\.[a-z]{2,}', texte, re.I), nom
            assert 'fraudeur' not in texte.lower(), nom


def test_fiche_d_un_salarie_porte_ses_identifiants_charges_et_incoherences(avec_base, base_demo):
    cx = sqlite3.connect(base_demo)
    ref = cx.execute("SELECT i.ref FROM c3_incoherence i JOIN c3_charge c ON c.ref = i.ref "
                     "JOIN c1_identifiant_brut b ON b.ref = i.ref AND b.type = 'CNSS' LIMIT 1").fetchone()
    if ref is None:
        pytest.skip('aucun dossier avec incohérence, charge et n° CNSS dans cette base')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        fiche = next(f for f, in cx.execute('SELECT fiche FROM c3_demandeur WHERE ref = ?', ref))
        f = c.get(f'/api/base/clients/{b.indice_fiche[fiche]}').json()
        assert f['charges'] and f['incoherences'] and any(i['type'] == 'CNSS' for i in f['identifiants'])
        assert all({'libelle', 'gravite', 'dossier'} <= set(i) for i in f['incoherences'])


def _fiche_citee_seulement(cx):
    """Une fiche citée dans des dossiers (salarié d'un employeur, société) sans en être demandeur."""
    return cx.execute(
        "SELECT m.fiche FROM c2_mention m WHERE m.source = 'v2' AND m.fiche NOT IN (SELECT fiche FROM c3_demandeur) "
        "GROUP BY m.fiche ORDER BY count(DISTINCT m.ref) DESC LIMIT 1").fetchone()


def test_fiche_citee_seulement_ne_montre_rien_des_dossiers_des_autres(avec_base, base_demo):
    cx = sqlite3.connect(base_demo)
    ligne = _fiche_citee_seulement(cx)
    if ligne is None:
        pytest.skip('aucune fiche citée seulement dans cette base')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        indice = b.indice_fiche[ligne[0]]
        f = c.get(f'/api/base/clients/{indice}').json()
        assert f['dossiers'], 'la fiche est citée dans au moins un dossier'
        for cle in ('revenus', 'vehicules', 'charges', 'operations', 'incoherences'):
            assert f[cle] == [], cle
        for d in f['dossiers']:
            assert d['demandeur'] is False and d['revenu_declare'] is None and d['verdict'] is None
            assert d['niveau'] is None
        for x in f['donnees']:
            assert x['demandeur'] is False and x['contexte'] == [] and x['controles'] == []
            for piece in x['pieces']:
                assert piece['mois'] == []
                assert {fa['cle'] for fa in piece['faits']} <= set(b.CHAMPS_MENTION)
        for ch in f['chemins']:
            depart = ch['etapes'][0]['de']['indice'] if ch['etapes'] else ch['inscrit']['indice']
            assert depart == indice


def test_identites_de_tiers_servies_journalisees_et_comptees(avec_base, base_demo):
    cx = sqlite3.connect(base_demo)
    societe = cx.execute("SELECT r.societe FROM c2_role r GROUP BY r.societe HAVING count(DISTINCT r.fiche) >= 3 "
                         "LIMIT 1").fetchone()
    if societe is None:
        pytest.skip('aucune société avec trois personnes dans cette base')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        f = c.get(f'/api/base/clients/{b.indice_fiche[societe[0]]}').json()
        tiers = {p['indice'] for p in f['personnes'] if p['indice']}
        assert len(tiers) >= 3
        from app import journal, quotas
        servis = {i for _e, i in journal.indices_servis(etat.base, 'ana', quotas.ETIQUETTES)}
        assert tiers <= servis


def test_journal_garde_l_epoque_de_la_base(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        assert re.fullmatch(r'[0-9a-f]{16}', b.epoque)
        indice = next(iter(b.fiche_de))
        c.get(f'/api/base/clients/{indice}')
        from app.base import Journal
        with etat.base() as s:
            derniere = s.query(Journal).filter(Journal.action == 'fiche').order_by(Journal.id.desc()).first()
        assert derniere.epoque == b.epoque


def test_resume_sans_compte_masque_retrouvable_par_difference(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'dir', 'DIRECTION')
        r = c.get('/api/base/resume').json()
        assert 'dossiers_total' not in r
        for bloc in ('produits', 'csp', 'niveaux'):
            masques = [x for x in r[bloc] if x['nombre'] == '< 5']
            assert len(masques) != 1, bloc
        lies = r['dossiers_lies']
        assert lies == '< 5' or lies == 0 or lies >= 5


def test_rib_masque_dans_toute_valeur_quelle_que_soit_la_cle(avec_base, base_demo):
    cx = sqlite3.connect(base_demo)
    ribs = {v for v, in cx.execute("SELECT DISTINCT valeur FROM c2_identifiant WHERE type = 'RIB'")}
    ref = cx.execute("SELECT x.fiche FROM c3_demandeur x JOIN c2_identifiant i ON i.ref = x.ref AND i.type = 'RIB' "
                     "LIMIT 1").fetchone()
    if not ribs or ref is None:
        pytest.skip('aucun RIB dans cette base')
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        texte = c.get(f'/api/base/clients/{b.indice_fiche[ref[0]]}').text
        assert not re.search(r'\d{20,}', texte)
        assert not any(r in texte for r in ribs)


@pytest.mark.skipif(shutil.which('node') is None, reason='node absent')
def test_scripts_des_pages_sans_erreur_de_syntaxe():
    import subprocess
    dossier = os.path.join(RACINE, 'front')
    for nom in sorted(os.listdir(dossier)):
        if nom.endswith('.js'):
            r = subprocess.run(['node', '--check', os.path.join(dossier, nom)], capture_output=True, text=True)
            assert r.returncode == 0, nom


def test_fiche_retrouvee_sur_la_carte_globale_par_son_cin_ou_son_rc(avec_base, carte_demo, base_demo):
    compact = lambda v: re.sub(r'\s+', '', str(v)).upper()          # noqa: E731
    g = sqlite3.connect(os.path.join(carte_demo, 'identites.sqlite'))
    cins = {compact(c) for (c,) in g.execute('SELECT cin FROM identite WHERE cin IS NOT NULL')}
    rcs = {compact(r) for (r,) in g.execute("SELECT rc FROM identite JOIN noeud USING (indice) "
                                            "WHERE type = 'societe' AND rc IS NOT NULL")}
    cx = sqlite3.connect(base_demo)
    with avec_base(CARTE_PUBLICATION_GLOBALE=carte_demo) as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        b = etat.base_client
        personnes = [(f, cin) for f, cin in cx.execute('SELECT identifiant, cin FROM c2_personne WHERE cin IS NOT NULL')]
        presente = next((f, cin) for f, cin in personnes if compact(cin) in cins)
        absente = next(f for f, cin in personnes if compact(cin) not in cins)
        r = c.get(f'/api/base/carte/{b.indice_fiche[presente[0]]}')
        assert r.status_code == 200 and set(r.json()) == {'indice'}
        trouve = g.execute('SELECT cin FROM identite WHERE indice = ?', (r.json()['indice'],)).fetchone()[0]
        assert compact(trouve) == compact(presente[1])
        assert c.get(f'/api/base/carte/{b.indice_fiche[absente]}').status_code == 404
        societe = next(f for f, rc in cx.execute('SELECT identifiant, rc FROM c2_societe WHERE rc IS NOT NULL')
                       if compact(rc) in rcs)
        r = c.get(f'/api/base/carte/{b.indice_fiche[societe]}')
        assert r.status_code == 200
        typ, rc = g.execute('SELECT type, rc FROM noeud JOIN identite USING (indice) WHERE indice = ?',
                            (r.json()['indice'],)).fetchone()
        assert typ == 'societe' and compact(rc) == compact(cx.execute('SELECT rc FROM c2_societe WHERE identifiant = ?',
                                                                       (societe,)).fetchone()[0])
        assert c.get('/api/base/carte/1').status_code == 404
        from conftest import tout_le_journal
        journal = tout_le_journal(etat)
        epoque_carte = json.load(open(os.path.join(carte_demo, 'manifeste.json'), encoding='utf-8'))['empreinte'][:16]
        assert 'carte' in journal and epoque_carte in journal          # indice servi sur la carte, avec son époque
    with avec_base(CARTE_PUBLICATION_GLOBALE=carte_demo, CARTE_QUOTA_FICHES='1') as (c, etat):
        connecte(c, etat, 'ana2', 'ANALYSTE')
        b = etat.base_client
        assert c.get(f'/api/base/carte/{b.indice_fiche[presente[0]]}').status_code == 200
        assert c.get(f'/api/base/carte/{b.indice_fiche[presente[0]]}').status_code == 429   # compte au quota de fiches


def test_fiche_vers_la_carte_sans_carte_globale_503(avec_base, base_demo):
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        indice = next(iter(etat.base_client.indice_fiche.values()))
        assert c.get(f'/api/base/carte/{indice}').status_code == 503


def test_meme_rc_dans_un_autre_tribunal_n_est_pas_la_meme_societe(client_avec, carte_demo, base_demo, tmp_path):
    compact = lambda v: re.sub(r'\s+', '', str(v)).upper()          # noqa: E731
    copie = str(tmp_path / 'carte')
    shutil.copytree(carte_demo, copie)
    cx = sqlite3.connect(base_demo)
    g = sqlite3.connect(os.path.join(copie, 'identites.sqlite'))
    noeuds = {(compact(rc), t): i for i, rc, t in g.execute(
        "SELECT indice, rc, tribunal FROM identite JOIN noeud USING (indice) WHERE type = 'societe' AND rc IS NOT NULL")}
    fiche, rc, trib = next((f, r, t) for f, r, t in cx.execute(
        'SELECT identifiant, rc, tribunal FROM c2_societe WHERE rc IS NOT NULL AND tribunal IS NOT NULL')
        if (compact(r), t) in noeuds)
    i = noeuds[(compact(rc), trib)]
    g.execute("UPDATE identite SET tribunal = 'AUTRE' WHERE indice = ?", (i,))   # même RC, autre tribunal
    g.commit()
    g.close()
    m = os.path.join(copie, 'manifeste.json')
    manifeste = json.load(open(m, encoding='utf-8'))
    sys.path.insert(0, os.path.join(RACINE, 'pipeline'))
    import publier_carte as pc
    manifeste['fichiers']['identites.sqlite'] = pc.empreinte(os.path.join(copie, 'identites.sqlite'))
    json.dump(manifeste, open(m, 'w', encoding='utf-8'))
    with client_avec(CARTE_BASE_CLIENT=base_demo, CARTE_PUBLICATION_GLOBALE=copie) as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        r = c.get(f'/api/base/carte/{etat.base_client.indice_fiche[fiche]}')
        assert r.status_code == 404 or r.json()['indice'] != i



# ---- vitesse : les vues lourdes sont lues une fois, la fiche passe par les index ----------------------------------------
def _vues_directes(base):
    """Ce que la base client lisait avant dans les vues, requête par requête : la référence des lectures gardées."""
    cx = sqlite3.connect(base)
    inc = {}
    for ref, t, g, ref_b in cx.execute('SELECT ref, type, gravite, ref_b FROM c3_incoherence'):
        inc.setdefault(ref, []).append((t, g, ref_b))
    dem = set(cx.execute('SELECT ref, fiche FROM c3_demandeur'))
    return cx, inc, dem


def test_les_lectures_gardees_en_memoire_sont_celles_des_vues(base_demo):
    from app.base_client import BaseClient
    b = BaseClient(base_demo)
    cx, inc, dem = _vues_directes(base_demo)
    assert inc, 'le jeu de démonstration doit porter des incohérences'
    assert {r: sorted(v) for r, v in b._incoherences_par_ref().items()} == {r: sorted(v) for r, v in inc.items()}
    assert b._demandeurs()[0] == dem


def test_l_entite_lue_par_les_index_est_celle_des_vues(base_demo):
    from app.base_client import BaseClient
    b = BaseClient(base_demo)
    cx, _, _ = _vues_directes(base_demo)
    salaries = [f for f, in cx.execute("SELECT DISTINCT fiche FROM c2_role WHERE role = 'employe'")]
    societes = [f for f, in cx.execute('SELECT identifiant FROM c2_societe')]
    assert salaries and societes
    lecture = b.connexion()
    for f in salaries:
        attendu = cx.execute(
            "SELECT max(n) FROM (SELECT count(DISTINCT d.fiche) AS n FROM c2_role r JOIN c2_role e ON "
            "e.societe = r.societe AND e.role = 'employe' JOIN c3_demandeur d ON d.fiche = e.fiche "
            "WHERE r.fiche = ? AND r.role = 'employe' GROUP BY r.societe) x", (f,)).fetchone()[0]
        assert b._entite(lecture, f, 'salarie') == dict(employeur_clients=attendu)
    avec_soeurs = 0
    for f in societes:
        soeurs = [n for n, in cx.execute(
            "SELECT DISTINCT s.denomination FROM c2_role a JOIN c2_role b ON b.fiche = a.fiche AND b.societe <> a.societe "
            "JOIN c2_societe s ON s.identifiant = b.societe WHERE a.societe = ? AND s.denomination IS NOT NULL "
            "AND s.denomination <> coalesce((SELECT denomination FROM c2_societe WHERE identifiant = a.societe), '') "
            "ORDER BY 1 LIMIT 50", (f,))]
        avec_soeurs += bool(soeurs)
        assert b._entite(lecture, f, 'pm')['soeurs'] == soeurs
    assert avec_soeurs, 'le jeu de démonstration doit porter des sociétés sœurs'


def test_la_page_et_la_fiche_ne_relisent_pas_les_vues_lourdes(base_demo):
    """Base en lecture seule : incohérences, demandeurs et chiffres du résumé sont calculés une fois ; ensuite ni la page
    (résumé, liste) ni une fiche ni un dossier ne relisent ces vues, ni ne croisent la vue des rôles avec elle-même."""
    from app.base_client import BaseClient
    b = BaseClient(base_demo)
    lues = []
    ouvrir = b.connexion

    def tracee():
        cx = ouvrir()
        cx.set_trace_callback(lues.append)
        return cx
    b.connexion = tracee
    b.resume()
    clients = b.clients()
    lues.clear()
    assert b.resume() and b.rechercher(page=1)['items']
    for c in clients[:15]:
        f = b.fiche(c['indice'])
        for d in f['dossiers'][:2]:
            b.dossier(d['indice'])
    lourdes = [q for q in lues if 'c3_incoherence' in q or 'c3_demandeur' in q or re.search(r'c2_role \w+ JOIN c2_role', q)]
    assert lues and lourdes == []


# ---- organisation par dossier : la liste des dossiers et la vue 360° d'un dossier ---------------------------------------
def test_liste_des_dossiers_une_ligne_par_dossier_avec_son_demandeur(avec_base, base_demo):
    cx = sqlite3.connect(base_demo)
    n_dossiers = cx.execute('SELECT count(*) FROM c3_dossier').fetchone()[0]
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        tout = c.post('/api/base/dossiers', json={'taille': 200}).json()
        assert tout['total'] == n_dossiers and len(tout['items']) == min(200, n_dossiers)
        premier = tout['items'][0]
        assert set(premier) == {'indice', 'reference', 'client', 'nom', 'type', 'inscrit', 'produit', 'recu', 'ville',
                                'actif', 'revenu_declare', 'verdict', 'niveau', 'niveau_libelle', 'incoherences'}
        assert all(x['reference'].startswith('ZZ') for x in tout['items'])
        assert len({x['indice'] for x in tout['items']}) == len(tout['items'])
        recus = [x['recu'] for x in tout['items'] if x['recu']]
        assert recus == sorted(recus, reverse=True)                     # par défaut : le plus récent d'abord
        cible = next(x for x in tout['items'] if x['client'])
        par_ref = c.post('/api/base/dossiers', json={'texte': cible['reference'].lower()}).json()
        assert [x['indice'] for x in par_ref['items']] == [cible['indice']]
        par_nom = c.post('/api/base/dossiers', json={'texte': cible['nom'][:6], 'taille': 200}).json()
        assert any(x['indice'] == cible['indice'] for x in par_nom['items'])
        avec = c.post('/api/base/dossiers', json={'avec_incoherence': True, 'taille': 200}).json()
        assert avec['total'] >= 1 and all(x['incoherences'] for x in avec['items'])
        noms = [x['nom'].upper() for x in c.post('/api/base/dossiers', json={'taille': 200, 'tri': 'alpha'}).json()['items']]
        assert noms == sorted(noms)
        from conftest import tout_le_journal
        assert cible['nom'][:6] not in tout_le_journal(etat)              # la recherche n'est jamais journalisée
        assert c.post('/api/base/dossiers', json={'inconnu': 1}).status_code == 422


@pytest.mark.parametrize('role', ['DIRECTION', 'AGENCE', 'ADMIN'])
def test_liste_des_dossiers_reservee_a_la_cellule_fraude(avec_base, role):
    with avec_base() as (c, etat):
        connecte(c, etat, 'u', role)
        assert c.post('/api/base/dossiers', json={}).status_code == 403
    with avec_base() as (c, etat):
        assert c.post('/api/base/dossiers', json={}).status_code == 401


def test_vue_360_d_un_dossier_ne_porte_que_ce_dossier(avec_base):
    """La vue 360° d'un dossier : l'étoile de son demandeur, remplie des seules données de ce dossier (pièces, relevés,
    revenus, contrôles, incohérences, chemins) ; l'historique du client reste, pour aller à ses autres dossiers."""
    with avec_base() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        clients = c.post('/api/base/clients', json={'taille': 200}).json()['items']
        personnes = [x for x in clients if x['type'] == 'personne'][:40]
        fiches = [(x, c.get(f'/api/base/clients/{x["indice"]}').json()) for x in personnes]
        multi, f = max(fiches, key=lambda xf: len(xf[1]['dossiers']))      # cité aussi ailleurs, si le jeu en a
        propre = next(d for d in f['dossiers'] if d['demandeur'])
        d = c.get(f'/api/base/dossiers/{propre["indice"]}').json()
        assert d['entete']['reference'].startswith('ZZ') and d['pieces'] and d['parties']   # l'en-tête d'avant reste
        v = d['vue']
        assert v['identite']['nom'] == f['identite']['nom'] and v['vue360']['etoile']
        assert [x['dossier'] for x in v['donnees']] == [propre['indice']]                 # un seul dossier, le sien
        assert v['donnees'][0]['pieces'] and v['donnees'][0]['contexte']
        assert all(r['dossier'] == propre['indice'] for r in v['revenus'])
        assert all(i['dossier'] == propre['indice'] for i in v['incoherences'])
        assert all(ch['dossier'] == propre['indice'] for ch in v['chemins'])
        assert len(v['dossiers']) == len(f['dossiers'])                                  # historique complet du client
        assert d['client'] == multi['indice']
        texte = json.dumps(d)
        assert not re.search(r'999\d{18,}', texte) and not MOTIFS[2].search(texte)


def test_le_resume_dit_si_la_base_est_fictive(avec_base):
    with avec_base() as (c, etat):
        connecte(c, etat, 'dir', 'DIRECTION')
        assert c.get('/api/base/resume').json()['fictive'] is True
