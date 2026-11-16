"""Chaînes d'un inscrit, statistiques sans identité, administration ; matrice complète des droits."""

import json
import os
import shutil
from datetime import timedelta

import pytest
from conftest import connecte, identites, indice_de

from app import journal
from app.roles import DROITS, Role

ROUTES = [  # (méthode, chemin, corps, droit)
    ('get', '/api/carte/geometrie', None, 'carte.geometrie'),
    ('post', '/api/carte/noms', {'indices': [0]}, 'carte.noms'),
    ('get', '/api/carte/noeud/0', None, 'carte.noeud'),
    ('post', '/api/carte/recherche', {'q': 'QIBOUSI'}, 'carte.recherche'),
    ('get', '/api/chaines/inscrits', None, 'chaines'),
    ('get', '/api/chaines/{inscrit}', None, 'chaines'),
    ('get', '/api/stats/villes', None, 'stats'),
    ('get', '/api/stats/regles', None, 'stats'),
    ('post', '/api/admin/recharger', None, 'admin'),
    ('get', '/api/admin/journal', None, 'admin'),
]


@pytest.mark.parametrize('role', list(Role))
def test_matrice_des_droits(client, etat, publication, role):
    connecte(client, etat, 'u', role.value)
    inscrit = indice_de(publication, 'E:9')
    for methode, chemin, corps, droit in ROUTES:
        r = getattr(client, methode)(chemin.format(inscrit=inscrit), **({'json': corps} if corps else {}))
        attendu = 200 if role in DROITS[droit] else 403
        assert r.status_code == attendu, (role, chemin, r.status_code)


def test_toute_route_sans_jeton_401(client, publication):
    for methode, chemin, corps, _ in ROUTES:
        r = getattr(client, methode)(chemin.format(inscrit=0), **({'json': corps} if corps else {}))
        assert r.status_code == 401, chemin


# ---- chaînes -------------------------------------------------------------------------------------------------------
def test_liste_des_inscrits_sans_cin(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    r = client.get('/api/chaines/inscrits').json()
    geo = etat.publication.geometrie['inscrits']
    assert [x['indice'] for x in r] == [p['i'] for p in geo]
    assert all(set(x) == {'indice', 'nom', 'type', 'compte', 'alerte', 'certain'} for x in r)
    qibousi = next(x for x in r if x['indice'] == indice_de(publication, 'E:9'))
    assert qibousi['nom'] == 'QIBOUSI YOUSSEF' and qibousi['certain'] is True and qibousi['type'] == 'PP'
    texte = json.dumps(r)
    assert 'ZZ9000' not in texte


def test_chaine_d_un_inscrit_au_format_de_la_carte(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    i = indice_de(publication, 'E:9')
    r = client.get(f'/api/chaines/{i}')
    attendu = json.loads(identites(publication, 'SELECT donnees FROM chaine WHERE indice = ?', i)[0][0])
    assert r.status_code == 200 and r.json() == attendu and r.headers['cache-control'] == 'no-store'
    from test_carte import lignes
    servis = lignes(etat, 'chaine')
    assert servis == [('ana', 'ANALYSTE', len(attendu['noeuds']), sorted(int(k) for k in attendu['noeuds']))]


def test_chaine_d_un_noeud_qui_n_est_pas_un_inscrit_404(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.get(f"/api/chaines/{indice_de(publication, 'I:1')}").status_code == 404


def test_chaines_comptent_dans_le_quota_de_fiches(client_avec, publication):
    with client_avec(CARTE_QUOTA_FICHES='1') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.get(f"/api/chaines/{indice_de(publication, 'E:9')}").status_code == 200
        assert c.get('/api/carte/noeud/0').status_code == 429


# ---- statistiques --------------------------------------------------------------------------------------------------
def test_stats_villes_depuis_la_geometrie(client, etat):
    connecte(client, etat, 'dir', 'DIRECTION')
    r = client.get('/api/stats/villes').json()
    g = etat.publication.geometrie
    casa = next(v for v in r if v['ville'] == 'CASABLANCA')
    k = g['villes'].index('CASABLANCA')
    dans = [i for i, v in enumerate(g['noeuds']['ville']) if v == k]
    assert casa == dict(ville='CASABLANCA', noeuds=len(dans),
                        societes=sum(1 for i in dans if g['noeuds']['t'][i] == 0),
                        personnes=sum(1 for i in dans if g['noeuds']['t'][i] == 1),
                        inscrits=sum(1 for i in dans if g['noeuds']['t'][i] in (2, 3)),
                        liste_noire=sum(g['noeuds']['bl'][i] for i in dans))
    assert {v['ville'] for v in r} == set(g['villes'])


def test_stats_regles_depuis_la_publication(client, etat, publication):
    connecte(client, etat, 'dir', 'DIRECTION')
    with open(os.path.join(publication, 'statistiques.json'), encoding='utf-8') as f:
        assert client.get('/api/stats/regles').json() == json.load(f)


# ---- administration ------------------------------------------------------------------------------------------------
def test_recharger_une_nouvelle_publication(client_avec, kit, publication, tmp_path):
    import publier_carte
    courant = str(tmp_path / 'courant')
    shutil.copytree(publication, courant)
    with client_avec(CARTE_PUBLICATION=courant) as (c, etat):
        connecte(c, etat, 'admin', 'ADMIN')
        avant = etat.publication.etag
        publier_carte.publier(kit['base'], kit['chaines'], courant)          # nouveau tirage d'indices
        r = c.post('/api/admin/recharger')
        assert r.status_code == 200 and r.json()['noeuds'] == etat.publication.noeuds
        assert etat.publication.etag != avant


def test_recharger_refuse_une_publication_alteree_et_garde_l_ancienne(client_avec, publication, tmp_path):
    courant = str(tmp_path / 'courant')
    shutil.copytree(publication, courant)
    with client_avec(CARTE_PUBLICATION=courant) as (c, etat):
        connecte(c, etat, 'admin', 'ADMIN')
        avant = etat.publication
        with open(os.path.join(courant, 'geometrie.json'), 'a') as f:
            f.write(' ')
        r = c.post('/api/admin/recharger')
        assert r.status_code == 409 and 'geometrie.json' in r.json()['detail']
        assert etat.publication is avant


def test_journal_pour_l_administrateur_filtre_et_pagine(client, etat):
    connecte(client, etat, 'admin', 'ADMIN')
    for k in range(7):
        journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [k, k + 1], ip='10.0.0.1')
    r = client.get('/api/admin/journal', params={'utilisateur': 'ana', 'taille': 3, 'page': 2}).json()
    assert r['total'] == 7 and len(r['lignes']) == 3
    assert set(r['lignes'][0]) == {'id', 'horodatage', 'utilisateur', 'role', 'action', 'nombre', 'ip', 'indices'}
    assert [l['indices'] for l in r['lignes']] == [[3, 4], [2, 3], [1, 2]]
    tout = client.get('/api/admin/journal', params={'utilisateur': 'ana', 'taille': 50}).json()['lignes']
    assert [l['indices'] for l in tout] == [[k, k + 1] for k in range(6, -1, -1)]   # plus récent d'abord
    assert client.get('/api/admin/journal', params={'taille': 1000}).status_code == 422


def test_journal_filtre_par_date(client, etat):
    connecte(client, etat, 'admin', 'ADMIN')
    journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [1])
    r = client.get('/api/admin/journal', params={'du': '2000-01-01', 'au': '2000-01-02'}).json()
    assert r['total'] == 0
    r = client.get('/api/admin/journal', params={'du': '2000-01-01', 'utilisateur': 'ana'}).json()
    assert r['total'] == 1


def test_purge_du_journal(etat):
    from sqlalchemy import update

    from app.base import Journal, maintenant
    journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [1, 2])
    journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [3])
    with etat.base.begin() as s:
        s.execute(update(Journal).where(Journal.id == 1).values(horodatage=maintenant() - timedelta(days=400)))
    assert journal.purger(etat.base, 365) == 1
    assert journal.indices_servis(etat.base, 'ana', ('noms',), depuis=timedelta(days=1000)) == {3}
