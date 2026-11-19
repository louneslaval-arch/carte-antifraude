"""Carte globale servie par l'API : couche 1 sans identité, noms, fiche et recherche à la demande, réservés à la cellule
fraude, journalisés avec l'époque de la carte. Données fictives du kit."""

import json
import os

import pytest

from conftest import connecte, identites, tout_le_journal

ROUTES = (('get', '/api/carte/globale', None), ('post', '/api/carte/globale/noms', {'indices': [0]}),
          ('get', '/api/carte/globale/noeud/0', None), ('post', '/api/carte/globale/recherche', {'q': 'ZZ900008'}))


@pytest.fixture
def avec_globale(client_avec, publication_globale):
    return lambda **r: client_avec(CARTE_PUBLICATION_GLOBALE=publication_globale, **r)


def appeler(c, methode, chemin, corps):
    return c.post(chemin, json=corps) if methode == 'post' else c.get(chemin)


def manifeste(publication_globale):
    with open(os.path.join(publication_globale, 'manifeste.json'), encoding='utf-8') as f:
        return json.load(f)


@pytest.mark.parametrize('role', ['DIRECTION', 'AGENCE', 'ADMIN'])
def test_carte_globale_reservee_a_la_cellule_fraude(avec_globale, role):
    from app.roles import DROITS, Role
    assert DROITS['carte.globale'] == frozenset({Role.ANALYSTE})
    with avec_globale() as (c, etat):
        for methode, chemin, corps in ROUTES:
            assert appeler(c, methode, chemin, corps).status_code == 401, chemin
        connecte(c, etat, 'u', role)
        for methode, chemin, corps in ROUTES:
            assert appeler(c, methode, chemin, corps).status_code == 403, chemin


def test_couche1_compressee_avec_etag_et_sans_identite(avec_globale, publication_globale):
    with avec_globale() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        r = c.get('/api/carte/globale')
        assert r.status_code == 200 and r.headers['content-encoding'] == 'gzip'
        geo = r.json()
        assert geo['type'] == 'globale' and len(geo['noeuds']) == manifeste(publication_globale)['noeuds']
        noms = [n for (n,) in identites(publication_globale, 'SELECT nom FROM identite WHERE nom IS NOT NULL')]
        cins = [x for (x,) in identites(publication_globale, 'SELECT cin FROM identite WHERE cin IS NOT NULL')]
        assert noms and cins and not any(v in r.text for v in noms + cins)
        assert c.get('/api/carte/globale', headers={'If-None-Match': r.headers['etag']}).status_code == 304


def test_noms_fiche_et_recherche_a_la_demande(avec_globale, publication_globale):
    inscrit, nom, cin = identites(publication_globale, "SELECT n.indice, i.nom, i.cin FROM noeud n JOIN identite i "
                                                       "USING (indice) WHERE n.type = 'inscrit' AND i.cin = 'ZZ900008'")[0]
    with avec_globale() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/globale/noms', json={'indices': [inscrit]}).json() == {str(inscrit): {'nom': nom, 'lat': None}}
        f = c.get(f'/api/carte/globale/noeud/{inscrit}').json()
        assert (f['nom'], f['cin'], f['type'], f['liste_noire']) == (nom, cin, 'inscrit', 'inscrit')
        assert f['liens'] and all(set(l) == {'indice', 'libelle', 'style', 'force'} for l in f['liens'])
        assert any(l['libelle'].startswith('rapprochement') for l in f['liens'])
        trouves = c.post('/api/carte/globale/recherche', json={'q': 'zz 900008'}).json()['resultats']
        assert any(x['indice'] == inscrit for x in trouves)
        mot = nom.split()[-1]
        assert any(x['indice'] == inscrit for x in c.post('/api/carte/globale/recherche', json={'q': mot.lower()}).json()['resultats'])


def test_journal_avec_l_epoque_de_la_carte_sans_identite_ni_requete(avec_globale, publication_globale):
    epoque = manifeste(publication_globale)['empreinte'][:16]
    nom = identites(publication_globale, "SELECT nom FROM identite i JOIN noeud n USING (indice) WHERE n.type = 'inscrit'")[0][0]
    with avec_globale() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        c.post('/api/carte/globale/noms', json={'indices': [0, 1]})
        c.get('/api/carte/globale/noeud/0')
        c.post('/api/carte/globale/recherche', json={'q': nom})
        journal = tout_le_journal(etat)
        assert journal.count(epoque) >= 3
        assert nom not in journal and nom.upper() not in journal


def test_indice_hors_carte_et_noeud_inconnu(avec_globale, publication_globale):
    n = manifeste(publication_globale)['noeuds']
    with avec_globale() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/globale/noms', json={'indices': [n]}).status_code == 422
        assert c.get(f'/api/carte/globale/noeud/{n}').status_code == 404


def test_sans_publication_globale_la_carte_repond_503(client_avec):
    with client_avec() as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.get('/api/carte/globale').status_code == 503


def test_publication_globale_reelle_refusee_sans_autorisation(publication_globale, tmp_path):
    import shutil

    from app.graphe import PublicationRefusee, charger
    copie = str(tmp_path / 'globale')
    shutil.copytree(publication_globale, copie)
    m = manifeste(copie)
    m['fictif'] = False
    with open(os.path.join(copie, 'manifeste.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f)
    with pytest.raises(PublicationRefusee):
        charger(copie, donnees_reelles=False)
    assert charger(publication_globale, donnees_reelles=False).noeuds == m['noeuds']


def test_une_publication_d_un_autre_type_est_refusee(publication, publication_globale, client_avec):
    from app.graphe import PublicationRefusee, charger
    with pytest.raises(PublicationRefusee):
        charger(publication, donnees_reelles=False, type='globale')
    with pytest.raises(PublicationRefusee):
        charger(publication_globale, donnees_reelles=False, type='chaines')
    with pytest.raises(PublicationRefusee):
        with client_avec(CARTE_PUBLICATION_GLOBALE=publication):
            pass


def test_quota_d_etiquettes_compte_chaque_carte_a_part(avec_globale):
    with avec_globale(CARTE_QUOTA_ETIQUETTES='2') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/noms', json={'indices': [0, 1]}).status_code == 200
        # l'indice 0 de la carte globale n'est pas le nœud 0 de la carte des chaînes : il compte en plus
        assert c.post('/api/carte/globale/noms', json={'indices': [0]}).status_code == 429


def test_page_de_la_carte_sans_style_ni_gestionnaire_en_ligne_et_lots_de_noms_bornes():
    import re

    from app.routes.carte import MAX_NOMS
    racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html = open(os.path.join(racine, 'front', 'carte.html'), encoding='utf-8').read()
    js = open(os.path.join(racine, 'front', 'carte.js'), encoding='utf-8').read()
    interdit = re.compile(r'\sstyle\s*=|\son[a-z]+\s*=')      # bloqués par la politique de sécurité du contenu
    assert not interdit.search(html)
    for chaine in re.findall(r'`[^`]*`|\'[^\'\n]*\'', js):
        assert not interdit.search(chaine), chaine[:60]
    assert f'.slice(0, {MAX_NOMS})' in js


def test_la_carte_s_ouvre_sur_la_vue_du_maroc_3d_quand_le_contour_est_publie():
    racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    js = open(os.path.join(racine, 'front', 'carte.js'), encoding='utf-8').read()
    fin = js[js.rindex('aide(); angles(); taille(); filtrer();'):]
    assert "if (G) basculer('maroc');" in fin           # première vue : la carte du Maroc 3D ; sinon la vue réseau
