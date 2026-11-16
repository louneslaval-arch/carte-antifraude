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


@pytest.mark.parametrize('role', ['DIRECTION', 'AGENCE'])
def test_noms_fiches_dossiers_reseau_refuses_hors_cellule_fraude(avec_base, role):
    with avec_base() as (c, etat):
        connecte(c, etat, 'u', role)
        assert c.post('/api/base/clients', json={}).status_code == 403
        for chemin in ('/api/base/clients/1', '/api/base/dossiers/1'):
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
        assert c.get(f'/api/base/reseau/{lie["indice"]}').status_code == 404      # carte désactivée
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
        servis = journal.indices_servis(etat.base, 'ana', quotas.ETIQUETTES)
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
