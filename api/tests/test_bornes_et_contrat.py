"""Bornes et détails du contrat que la mutation a trouvés non vérifiés : chaque limite est testée des deux côtés,
chaque variable d'environnement est lue sous son nom, chaque champ annoncé est présent."""

import logging
import time
from datetime import timedelta

import jwt
import pytest
from conftest import CLE, MDP, connecte, connecter, creer, identites, indice_de
from fastapi.testclient import TestClient
from sqlalchemy import update

from app import comptes, identites as couche2, journal
from app.base import Journal, Revocation, maintenant
from app.config import ReglageInvalide, Reglages, lire_reglages
from app.main import VERSION, creer_app


# ---- réglages ------------------------------------------------------------------------------------------------------
def test_valeurs_par_defaut_documentees(env):
    r = lire_reglages({'CARTE_CLE_JWT': CLE, 'CARTE_BASE_URL': env['CARTE_BASE_URL']})
    assert r == Reglages(cle_jwt=CLE, base_url=env['CARTE_BASE_URL'], publication=None, donnees_reelles=False,
                         duree_jeton_s=28_800, renouveler_apres_s=900, echecs_max=5, quota_etiquettes=20_000,
                         quota_fiches=2_000, debit='60/minute', debit_connexion='10/minute', journal_jours=365,
                         origine=None, cookie_securise=True)


@pytest.mark.parametrize('variable, valeur, champ, attendu', [
    ('CARTE_DONNEES_REELLES', '1', 'donnees_reelles', True),
    ('CARTE_DONNEES_REELLES', 'oui', 'donnees_reelles', False),
    ('CARTE_DUREE_JETON_S', '60', 'duree_jeton_s', 60),
    ('CARTE_QUOTA_ETIQUETTES', '7', 'quota_etiquettes', 7),
    ('CARTE_QUOTA_FICHES', '8', 'quota_fiches', 8),
    ('CARTE_DEBIT', '5/minute', 'debit', '5/minute'),
    ('CARTE_DEBIT_CONNEXION', '3/minute', 'debit_connexion', '3/minute'),
    ('CARTE_JOURNAL_JOURS', '30', 'journal_jours', 30),
    ('CARTE_ORIGINE', 'https://carte.exemple.invalid', 'origine', 'https://carte.exemple.invalid'),
    ('CARTE_COOKIE_NON_SECURISE', '1', 'cookie_securise', False),
    ('CARTE_QUOTA_FICHES', '', 'quota_fiches', 2_000),
])
def test_chaque_variable_lue_sous_son_nom(env, variable, valeur, champ, attendu):
    assert getattr(lire_reglages(dict(env, **{variable: valeur})), champ) == attendu


def test_zero_refuse(env):
    with pytest.raises(ReglageInvalide, match='CARTE_JOURNAL_JOURS doit être positif'):
        lire_reglages(dict(env, CARTE_JOURNAL_JOURS='0'))


def test_entier_invalide_message(env):
    with pytest.raises(ReglageInvalide, match='^CARTE_QUOTA_FICHES doit être un entier$'):
        lire_reglages(dict(env, CARTE_QUOTA_FICHES='x'))


def test_cle_de_32_caracteres_acceptee_31_refusee(env):
    assert lire_reglages(dict(env, CARTE_CLE_JWT='k' * 32)).cle_jwt == 'k' * 32
    with pytest.raises(ReglageInvalide, match=r'^CARTE_CLE_JWT absente ou trop courte \(32 caractères au moins\)$'):
        lire_reglages(dict(env, CARTE_CLE_JWT='k' * 31))


def test_base_absente_message(env):
    with pytest.raises(ReglageInvalide, match='^CARTE_BASE_URL absente$'):
        lire_reglages(dict(env, CARTE_BASE_URL=''))


# ---- connexion et jeton ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize('manque', ['sub', 'sid', 'iat', 'exp'])
def test_jeton_sans_champ_obligatoire_refuse(client, etat, manque):
    creer(etat, 'ana', 'ANALYSTE')
    t = int(time.time())
    contenu = {'sub': 'ana', 'sid': 's', 'iat': t, 'exp': t + 600}
    del contenu[manque]
    jeton = jwt.encode(contenu, CLE, algorithm='HS256')
    r = client.get('/api/stats/regles', headers={'Authorization': f'Bearer {jeton}'})
    assert r.status_code == 401 and r.json() == {'detail': 'Authentification requise'}


def test_messages_de_refus(client, etat):
    assert connecter(client, 'personne').json() == {
        'detail': 'Identifiant ou mot de passe incorrect, ou compte verrouillé'}
    connecte(client, etat, 'dir', 'DIRECTION')
    assert client.get('/api/carte/noeud/0').json() == {'detail': 'Rôle insuffisant'}


@pytest.mark.parametrize('corps', [
    {'identifiant': 'a' * 65, 'mot_de_passe': 'x'},
    {'identifiant': 'a', 'mot_de_passe': 'x' * 257},
    {'identifiant': 'a', 'mot_de_passe': 'x', 'role': 'ADMIN'},
    {'identifiant': 'a'},
])
def test_connexion_demande_invalide(client, corps):
    assert client.post('/api/auth/connexion', json=corps).status_code == 422


def test_connexion_aux_longueurs_maximales_examinee(client):
    r = client.post('/api/auth/connexion', json={'identifiant': 'a' * 64, 'mot_de_passe': 'x' * 256})
    assert r.status_code == 401


def test_adresse_journalisee(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    client.post('/api/carte/noms', json={'indices': [0]})
    with etat.base() as s:
        assert {j.ip for j in s.query(Journal)} == {'testclient'}


def test_deconnexion_efface_le_cookie_et_n_emet_pas_de_jeton_neuf(client, etat):
    creer(etat, 'ana', 'DIRECTION')
    t = int(time.time()) - 20 * 60
    vieux = jwt.encode({'sub': 'ana', 'sid': 's1', 'iat': t, 'exp': t + 3600}, CLE, algorithm='HS256')
    r = client.post('/api/auth/deconnexion', headers={'Authorization': f'Bearer {vieux}'})
    assert r.status_code == 204 and 'x-jeton' not in r.headers
    cookie = r.headers['set-cookie'].lower()
    for attribut in ('carte_jeton=""', 'max-age=0', 'path=/api', 'httponly', 'secure', 'samesite=strict'):
        assert attribut in cookie, attribut


def test_revocations_expirees_purgees(etat):
    with etat.base.begin() as s:
        s.add(Revocation(sid='vieille', expire=maintenant() - timedelta(seconds=1)))
        s.add(Revocation(sid='courante', expire=maintenant() + timedelta(hours=1)))
    journal.purger(etat.base, 365)
    with etat.base() as s:
        assert [r.sid for r in s.query(Revocation)] == ['courante']


def test_revocation_gardee_jusqu_a_la_fin_du_jeton(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    client.post('/api/auth/deconnexion')
    with etat.base() as s:
        (r,) = s.query(Revocation).all()
    assert timedelta(hours=7, minutes=59) < r.expire - maintenant() <= timedelta(hours=8)


# ---- comptes ----------------------------------------------------------------------------------------------------------
def test_identifiant_de_64_caracteres_accepte_65_refuse(etat):
    comptes.creer(etat.base, 'a' * 64, 'ANALYSTE', MDP)
    with pytest.raises(ValueError, match='^identifiant vide ou trop long$'):
        comptes.creer(etat.base, 'a' * 65, 'ANALYSTE', MDP)


def test_mot_de_passe_de_12_caracteres_accepte_11_refuse(etat):
    comptes.creer(etat.base, 'douze', 'ANALYSTE', 'x' * 12)
    with pytest.raises(ValueError, match=r'^mot de passe trop court \(12 caractères au moins\)$'):
        comptes.creer(etat.base, 'onze', 'ANALYSTE', 'x' * 11)


def test_messages_de_creation(etat):
    with pytest.raises(ValueError, match='^rôle inconnu ; rôles possibles : ANALYSTE, AGENCE, DIRECTION, ADMIN$'):
        comptes.creer(etat.base, 'x', 'CHEF', MDP)
    comptes.creer(etat.base, 'ana', 'ANALYSTE', MDP)
    with pytest.raises(ValueError, match='^le compte ana existe déjà$'):
        comptes.creer(etat.base, 'ana', 'ANALYSTE', MDP)


def test_deverrouiller_remet_les_echecs_a_zero(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    for _ in range(5):
        connecter(client, 'ana', 'faux')
    comptes.deverrouiller(etat.base, 'ana')
    for _ in range(4):
        connecter(client, 'ana', 'faux')
    assert connecter(client, 'ana').status_code == 200


def test_ligne_de_commande_sans_commande_refusee(monkeypatch):
    with pytest.raises(SystemExit) as e:
        comptes.main([])
    assert e.value.code == 2


# ---- carte -------------------------------------------------------------------------------------------------------------
def test_dernier_indice_accepte_suivant_refuse(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    n = etat.publication.noeuds
    assert client.post('/api/carte/noms', json={'indices': [n - 1]}).status_code == 200
    r = client.post('/api/carte/noms', json={'indices': [n]})
    assert r.status_code == 422 and r.json() == {'detail': 'Indice hors de la carte'}
    assert client.get(f'/api/carte/noeud/{n - 1}').status_code == 200
    r = client.get(f'/api/carte/noeud/{n}')
    assert r.status_code == 404 and r.json() == {'detail': 'Nœud inconnu'}


def test_jusqu_a_400_noms_par_demande(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    n = etat.publication.noeuds
    assert client.post('/api/carte/noms', json={'indices': [k % n for k in range(400)]}).status_code == 200


def test_noms_de_plusieurs_indices_en_une_demande(etat, publication):
    attendus = dict(identites(publication, 'SELECT indice, nom FROM identite LIMIT 3'))
    assert {i: v['nom'] for i, v in couche2.noms(etat.publication, list(attendus)).items()} == attendus


def test_noeud_absent_de_la_couche_2_404(client, etat, monkeypatch):
    connecte(client, etat, 'ana', 'ANALYSTE')
    monkeypatch.setattr(couche2, 'fiche', lambda *_a: None)
    r = client.get('/api/carte/noeud/0')
    assert r.status_code == 404 and r.json() == {'detail': 'Nœud inconnu'}


def test_fiche_complete(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    (i, certain), = identites(publication, "SELECT indice, certain FROM identite WHERE indice IN "
                                           "(SELECT indice FROM annonce) LIMIT 1")
    f = client.get(f'/api/carte/noeud/{i}').json()
    assert f['indice'] == i and f['certain'] is bool(certain)
    attendues = identites(publication, 'SELECT date, type, url FROM annonce WHERE indice = ? ORDER BY date', i)
    assert [(a['date'], a['type'], a['url']) for a in f['annonces']] == attendues


def test_geometrie_entetes_de_cache(client, etat):
    connecte(client, etat, 'dir', 'DIRECTION')
    r = client.get('/api/carte/geometrie')
    assert r.headers['cache-control'] == 'private, no-cache'
    assert r.headers['vary'] == 'Cookie, Authorization'
    assert r.headers['content-type'] == 'application/json'


def test_sans_publication_503(client_avec):
    with client_avec(CARTE_PUBLICATION='') as (c, etat):
        connecte(c, etat, 'dir', 'DIRECTION')
        r = c.get('/api/carte/geometrie')
    assert r.status_code == 503 and r.json() == {'detail': 'Aucune publication chargée'}


def test_recherche_de_nom_a_trois_lettres_acceptee(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    assert client.post('/api/carte/recherche', json={'q': 'ABC'}).status_code == 200
    r = client.post('/api/carte/recherche', json={'q': 'AB'})
    assert r.status_code == 422 and r.json() == {'detail': 'Requête invalide', 'champs': ['body.q']}


def test_recherche_espaces_ramenes_a_un_seul():
    assert couche2.forme_recherche('  fassi \t  youssef ') == (('nom',), 'FASSI YOUSSEF', False)
    assert couche2.forme_recherche('zz 900 008') == (('cin', 'rc'), 'ZZ900008', True)


@pytest.mark.parametrize('q', ['%%%', '___', '\\\\\\', 'A%C'])
def test_recherche_jokers_pris_a_la_lettre(etat, q):
    assert couche2.recherche(etat.publication, q) == []


def test_recherche_plafonnee_a_50(etat, monkeypatch):
    monkeypatch.setattr(couche2, 'MAX_RESULTATS', 2)
    assert len(couche2.recherche(etat.publication, 'A')) == 2
    monkeypatch.undo()
    assert couche2.MAX_RESULTATS == 50


def test_chaine_entetes_et_message(client, etat, publication):
    connecte(client, etat, 'ana', 'ANALYSTE')
    (i,), = identites(publication, 'SELECT indice FROM chaine LIMIT 1')
    assert client.get(f'/api/chaines/{i}').headers['content-type'] == 'application/json'
    (j,), = identites(publication, 'SELECT indice FROM noeud WHERE indice NOT IN (SELECT indice FROM chaine) LIMIT 1')
    assert client.get(f'/api/chaines/{j}').json() == {'detail': 'Pas de carte pour ce nœud'}
    client.get('/api/chaines/inscrits')
    with etat.base() as s:
        assert {j.action for j in s.query(Journal)} >= {'inscrits', 'chaine'}


def test_stats_toutes_les_villes(client, etat):
    connecte(client, etat, 'dir', 'DIRECTION')
    g = etat.publication.geometrie
    noms_types = {0: 'societes', 1: 'personnes', 2: 'inscrits', 3: 'inscrits'}
    for v in client.get('/api/stats/villes').json():
        k = g['villes'].index(v['ville'])
        types = [t for t, ville in zip(g['noeuds']['t'], g['noeuds']['ville']) if ville == k]
        for nom in ('societes', 'personnes', 'inscrits'):
            assert v[nom] == sum(1 for t in types if noms_types[t] == nom), (v['ville'], nom)


# ---- quotas ----------------------------------------------------------------------------------------------------------
def test_quota_sur_l_heure_glissante(client_avec):
    with client_avec(CARTE_QUOTA_FICHES='1') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.get('/api/carte/noeud/0').status_code == 200
        r = c.get('/api/carte/noeud/0')
        assert r.status_code == 429 and r.json() == {'detail': 'Quota de fiches de l\'heure atteint'}
        with etat.base.begin() as s:
            s.execute(update(Journal).values(horodatage=maintenant() - timedelta(minutes=61)))
        assert c.get('/api/carte/noeud/0').status_code == 200


def test_quota_d_etiquettes_sur_l_heure_glissante(client_avec):
    with client_avec(CARTE_QUOTA_ETIQUETTES='1') as (c, etat):
        connecte(c, etat, 'ana', 'ANALYSTE')
        assert c.post('/api/carte/noms', json={'indices': [0]}).status_code == 200
        r = c.post('/api/carte/noms', json={'indices': [1]})
        assert r.status_code == 429 and r.json() == {'detail': 'Quota d\'étiquettes de l\'heure atteint'}
        with etat.base.begin() as s:
            s.execute(update(Journal).values(horodatage=maintenant() - timedelta(minutes=61)))
        assert c.post('/api/carte/noms', json={'indices': [1]}).status_code == 200


# ---- erreurs, santé, CORS -------------------------------------------------------------------------------------------
def test_champs_en_erreur_nommes(client, etat):
    connecte(client, etat, 'ana', 'ANALYSTE')
    r = client.post('/api/carte/noms', json={'indices': ['a', 'b']})
    assert r.json() == {'detail': 'Requête invalide', 'champs': ['body.indices']}


def test_erreur_interne_dans_le_journal_technique_carte(env, monkeypatch, caplog):
    def panne(*_a):
        raise KeyError('x')
    monkeypatch.setattr(couche2, 'fiche', panne)
    app = creer_app(lire_reglages(env))
    with TestClient(app, base_url='https://testserver', raise_server_exceptions=False) as c:
        connecte(c, app.state.etat, 'ana', 'ANALYSTE')
        with caplog.at_level(logging.ERROR, logger='carte'):
            c.get('/api/carte/noeud/0')
    assert [(r.name, r.getMessage()) for r in caplog.records if r.name == 'carte'] == [
        ('carte', 'Erreur interne KeyError sur GET /api/carte/noeud/0')]


def test_sante_annonce_la_version(client_avec, client):
    assert client.get('/api/sante').json()['version'] == VERSION == '0.3.0'
    r = client.get('/api/sante').json()
    assert r['etat'] == 'ok' and r['fictif'] is True
    with client_avec(CARTE_PUBLICATION='') as (c, _):
        assert c.get('/api/sante').json() == {'etat': 'sans_publication', 'version': VERSION}


def test_cors_admet_post_json_avec_jeton(client_avec):
    with client_avec(CARTE_ORIGINE='https://carte.exemple.invalid') as (c, _):
        r = c.options('/api/carte/noms', headers={
            'Origin': 'https://carte.exemple.invalid', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Authorization, Content-Type'})
    assert r.status_code == 200
    assert {'GET', 'POST'} <= set(r.headers['access-control-allow-methods'].replace(' ', '').split(','))
    assert {'authorization', 'content-type'} <= set(r.headers['access-control-allow-headers'].lower()
                                                     .replace(' ', '').split(','))


# ---- administration --------------------------------------------------------------------------------------------------
def test_recharger_sans_publication_configuree(client_avec):
    with client_avec(CARTE_PUBLICATION='') as (c, etat):
        connecte(c, etat, 'admin', 'ADMIN')
        r = c.post('/api/admin/recharger')
    assert r.status_code == 409 and r.json() == {'detail': 'CARTE_PUBLICATION non défini'}


def test_recharger_reponse_et_journal(client, etat):
    connecte(client, etat, 'admin', 'ADMIN')
    journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [1])
    with etat.base.begin() as s:
        s.execute(update(Journal).where(Journal.utilisateur == 'ana')
                  .values(horodatage=maintenant() - timedelta(days=400)))
    r = client.post('/api/admin/recharger').json()
    assert r == {'date_publication': etat.publication.manifeste['date_publication'],
                 'noeuds': etat.publication.noeuds, 'journal_purge': 1}
    with etat.base() as s:
        assert [j.action for j in s.query(Journal).order_by(Journal.id)][-1] == 'recharger'


def test_recharger_refus_journalise(client_avec, publication, tmp_path):
    import shutil
    courant = str(tmp_path / 'courant')
    shutil.copytree(publication, courant)
    with client_avec(CARTE_PUBLICATION=courant) as (c, etat):
        connecte(c, etat, 'admin', 'ADMIN')
        with open(f'{courant}/geometrie.json', 'a') as f:
            f.write(' ')
        r = c.post('/api/admin/recharger')
        assert r.json()['detail'].startswith('Publication refusée : geometrie.json')
        with etat.base() as s:
            assert [j.action for j in s.query(Journal)][-1] == 'recharger_refus'


def test_journal_taille_par_defaut_100_et_bornes(client, etat):
    connecte(client, etat, 'admin', 'ADMIN')
    for k in range(105):
        journal.ecrire(etat.base, 'ana', 'ANALYSTE', 'noms', [k])
    r = client.get('/api/admin/journal').json()
    assert r['page'] == 1 and len(r['lignes']) == 100 and r['lignes'][0]['horodatage'].endswith('Z')
    assert client.get('/api/admin/journal', params={'taille': 500}).status_code == 200
    assert client.get('/api/admin/journal', params={'taille': 501}).status_code == 422
    assert client.get('/api/admin/journal', params={'taille': 1}).status_code == 200
    assert client.get('/api/admin/journal', params={'utilisateur': 'a' * 64}).status_code == 200
    assert client.get('/api/admin/journal', params={'utilisateur': 'a' * 65}).status_code == 422


def test_journal_du_et_au_inclus(client, etat):
    from datetime import datetime
    connecte(client, etat, 'admin', 'ADMIN')
    for jour, heure in (('2026-03-01', 0), ('2026-03-02', 23), ('2026-03-03', 0)):
        journal.ecrire(etat.base, 'ana', 'ANALYSTE', jour, [1])
        with etat.base.begin() as s:
            s.execute(update(Journal).where(Journal.action == jour).values(
                horodatage=datetime.fromisoformat(jour).replace(hour=heure)))
    r = client.get('/api/admin/journal', params={'utilisateur': 'ana', 'du': '2026-03-01', 'au': '2026-03-02'})
    assert sorted(l['action'] for l in r.json()['lignes']) == ['2026-03-01', '2026-03-02']
