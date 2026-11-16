"""Routes de la carte : géométrie pour tous, identités à la demande selon le rôle, journal et quotas."""

import gzip
import json
import os

import pytest
from conftest import connecte, identites, indice_de, tout_le_journal

from app import journal


def lignes(etat, action):
    from sqlalchemy import select

    from app.base import Journal, JournalIndice
    with etat.base() as s:
        return [(j.utilisateur, j.role, j.nombre, sorted(s.scalars(select(JournalIndice.indice).where(
            JournalIndice.journal_id == j.id)))) for j in s.scalars(select(Journal).where(Journal.action == action))]


# ---- géométrie ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('role', ['ANALYSTE', 'AGENCE', 'DIRECTION', 'ADMIN'])
def test_geometrie_pour_tous_les_roles_compressee_avec_etag(client, etat, publication, role):
    connecte(client, etat, 'u', role)
    r = client.get('/api/carte/geometrie')
    with open(os.path.join(publication, 'geometrie.json'), encoding='utf-8') as f:
        assert r.status_code == 200 and r.json() == json.load(f)
    assert r.headers['content-encoding'] == 'gzip' and r.headers['etag'] == etat.publication.etag
    assert client.get('/api/carte/geometrie', headers={'If-None-Match': r.headers['etag']}).status_code == 304


def test_geometrie_envoyee_compressee_telle_quelle(etat):
    with open(os.path.join(etat.publication.dossier, 'geometrie.json'), 'rb') as f:
        assert gzip.decompress(etat.publication.geometrie_gz) == f.read()


# ---- noms --------------------------------------------------------------------------------------------------------
def test_noms_pour_l_analyste(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    attendus = dict(identites(publication, 'SELECT indice, nom FROM identite WHERE nom IS NOT NULL LIMIT 5'))
    r = client.post('/api/carte/noms', json={'indices': list(attendus)})
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    assert r.json() == {str(i): {'nom': n, 'lat': None} for i, n in attendus.items()}
    assert lignes(etat, 'noms') == [('ana', 'ANALYSTE', 5, sorted(attendus))]


def test_noms_pour_l_agence_mais_pas_pour_la_direction(client, etat):
    connecte(client, etat, 'agence', 'AGENCE')
    assert client.post('/api/carte/noms', json={'indices': [0]}).status_code == 200
    client.post('/api/auth/deconnexion')
    connecte(client, etat, 'dir', 'DIRECTION')
    assert client.post('/api/carte/noms', json={'indices': [0]}).status_code == 403
    assert lignes(etat, 'noms') == [('agence', 'AGENCE', 1, [0])]


@pytest.mark.parametrize('indices', [list(range(401)), [-1], [10 ** 6], ['a'], []])
def test_noms_demande_invalide(client, etat, indices):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.post('/api/carte/noms', json={'indices': indices}).status_code == 422


def test_quota_d_etiquettes_compte_les_indices_nouveaux(client_avec):
    with client_avec(CARTE_QUOTA_ETIQUETTES='5') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/noms', json={'indices': [0, 1, 2]}).status_code == 200
        assert c.post('/api/carte/noms', json={'indices': [0, 1, 2]}).status_code == 200   # déjà servis
        assert c.post('/api/carte/noms', json={'indices': [2, 3, 4]}).status_code == 200   # 5 au total
        r = c.post('/api/carte/noms', json={'indices': [5]})
        assert r.status_code == 429 and 'étiquettes' in r.json()['detail']


# ---- fiche -------------------------------------------------------------------------------------------------------
def test_fiche_d_un_inscrit(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    i = indice_de(publication, 'E:9')                      # FASSI YOUSSEF, CIN ZZ900008 (kit)
    r = client.get(f'/api/carte/noeud/{i}')
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    f = r.json()
    assert (f['nom'], f['cin'], f['type'], f['certain']) == ('FASSI YOUSSEF', 'ZZ900008', 'inscrit_personne', True)
    voisins = {l['indice'] for l in f['liens']}
    assert voisins == {indice_de(publication, 'S:1'), indice_de(publication, 'S:4')}
    assert all(set(l) == {'indice', 'libelle', 'style', 'force'} for l in f['liens'])
    assert lignes(etat, 'fiche') == [('ana', 'ANALYSTE', 1, [i])]


def test_fiche_d_une_societe_avec_ses_annonces(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    f = client.get(f"/api/carte/noeud/{indice_de(publication, 'S:1')}").json()
    assert f['rc'] == '999001' and f['tribunal'] == 'CASABLANCA' and f['type'] == 'societe'
    assert [a['date'] for a in f['annonces']] == ['2024-05-14', '2025-01-10', '2025-02-03']
    assert set(f['annonces'][0]) == {'date', 'type', 'url'}


@pytest.mark.parametrize('role', ['AGENCE', 'DIRECTION', 'ADMIN'])
def test_fiche_reservee_a_l_analyste(client, etat, role):
    connecte(client, etat, 'u', role)
    assert client.get('/api/carte/noeud/0').status_code == 403


def test_fiche_inconnue_404(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.get('/api/carte/noeud/99999').status_code == 404
    assert client.get('/api/carte/noeud/-1').status_code in (404, 422)


def test_quota_de_fiches(client_avec):
    with client_avec(CARTE_QUOTA_FICHES='2') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert [c.get(f'/api/carte/noeud/{i}').status_code for i in (0, 1, 0)] == [200, 200, 429]


# ---- recherche ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('q, ref', [('ZZ900008', 'E:9'), ('zz 900008', 'E:9'), ('fassi', 'E:9'),
                                    ('999001', 'S:1'), ('ATLAS', 'S:1')])
def test_recherche_par_cin_rc_ou_nom(client, etat, publication, q, ref):
    connecte(client, etat, 'ana', 'ANALYSTE')
    r = client.post('/api/carte/recherche', json={'q': q})
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    resultats = r.json()['resultats']
    assert indice_de(publication, ref) in {x['indice'] for x in resultats}
    assert all(set(x) == {'indice', 'type', 'nom'} for x in resultats) and len(resultats) <= 50


def test_recherche_journalisee_sans_la_requete(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    n = len(client.post('/api/carte/recherche', json={'q': 'ZZ900008'}).json()['resultats'])
    client.post('/api/carte/recherche', json={'q': 'FASSI'})
    contenu = tout_le_journal(etat)
    assert 'ZZ900008' not in contenu and 'FASSI' not in contenu and '900008' not in contenu
    assert lignes(etat, 'recherche')[0][2] == n


@pytest.mark.parametrize('q', ['', 'a', 'x' * 101])
def test_recherche_trop_courte_ou_trop_longue(client, etat, q):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.post('/api/carte/recherche', json={'q': q}).status_code == 422


def test_recherche_de_nom_de_moins_de_trois_lettres_refusee(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.post('/api/carte/recherche', json={'q': 'fa'}).status_code == 422


@pytest.mark.parametrize('role', ['AGENCE', 'DIRECTION', 'ADMIN'])
def test_recherche_reservee_a_l_analyste(client, etat, role):
    connecte(client, etat, 'u', role)
    assert client.post('/api/carte/recherche', json={'q': 'FASSI'}).status_code == 403


def test_recherche_compte_dans_le_quota_d_etiquettes(client_avec, publication):
    with client_avec(CARTE_QUOTA_ETIQUETTES='1') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/recherche', json={'q': 'ZZ900008'}).status_code == 200
        assert journal.indices_servis(etat.base, 'ana', ('noms', 'recherche')) == {indice_de(publication, 'E:9')}
        assert c.post('/api/carte/noms', json={'indices': [indice_de(publication, 'S:1')]}).status_code == 429
