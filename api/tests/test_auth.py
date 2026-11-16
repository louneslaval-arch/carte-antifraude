"""Connexion, jeton, renouvellement, révocation, verrouillage, comptes."""

import time

import jwt
import pytest
from conftest import CLE, MDP, connecter, creer

from app import comptes


def test_connexion_renvoie_jeton_role_duree_et_cookie_protege(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    r = connecter(client, 'ana')
    assert r.status_code == 200
    corps = r.json()
    assert corps['role'] == 'ANALYSTE' and corps['duree'] == 8 * 3600 and corps['jeton']
    cookie = r.headers['set-cookie']
    for attribut in ('carte_jeton=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/api'):
        assert attribut.lower() in cookie.lower(), attribut
    contenu = jwt.decode(corps['jeton'], CLE, algorithms=['HS256'])
    assert contenu['sub'] == 'ana' and contenu['exp'] - contenu['iat'] == 8 * 3600 and contenu['sid']


def test_mauvais_mot_de_passe_et_compte_inconnu_meme_reponse(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    a, b = connecter(client, 'ana', 'faux'), connecter(client, 'personne', 'faux')
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_verrouillage_apres_cinq_echecs(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    for _ in range(5):
        assert connecter(client, 'ana', 'faux').status_code == 401
    assert connecter(client, 'ana').status_code == 401              # bon mot de passe, compte verrouillé
    comptes.deverrouiller(etat.base, 'ana')
    assert connecter(client, 'ana').status_code == 200


def test_une_connexion_reussie_remet_le_compteur_a_zero(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    for _ in range(4):
        connecter(client, 'ana', 'faux')
    assert connecter(client, 'ana').status_code == 200
    for _ in range(4):
        connecter(client, 'ana', 'faux')
    assert connecter(client, 'ana').status_code == 200


def test_sans_jeton_401(client):
    assert client.get('/api/carte/geometrie').status_code == 401


@pytest.mark.parametrize('jeton', [
    'nimporte-quoi',
    jwt.encode({'sub': 'ana', 'role': 'ADMIN', 'sid': 's', 'iat': int(time.time()), 'exp': int(time.time()) + 60},
               'une-autre-cle-' + 'y' * 40, algorithm='HS256'),
    jwt.encode({'sub': 'ana', 'role': 'ANALYSTE', 'sid': 's', 'iat': int(time.time()) - 100,
                'exp': int(time.time()) - 10}, CLE, algorithm='HS256'),
    jwt.encode({'sub': 'ana', 'role': 'ANALYSTE', 'sid': 's', 'iat': int(time.time()), 'exp': int(time.time()) + 60},
               CLE, algorithm='HS512'),
])
def test_jeton_invalide_expire_ou_mal_signe_401(client, etat, jeton):
    creer(etat, 'ana', 'ANALYSTE')
    assert client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {jeton}'}).status_code == 401


def test_jeton_par_en_tete(client, etat):
    creer(etat, 'ana', 'DIRECTION')
    jeton = connecter(client, 'ana').json()['jeton']
    client.cookies.clear()
    assert client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {jeton}'}).status_code == 200


def test_deconnexion_revoque_le_jeton(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    jeton = connecter(client, 'ana').json()['jeton']
    assert client.post('/api/auth/deconnexion').status_code == 204
    client.cookies.clear()
    assert client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {jeton}'}).status_code == 401


def test_role_lu_en_base_et_non_dans_le_jeton(client, etat):
    """Un jeton dont le rôle a été modifié, ou un compte désactivé, ne donne plus accès."""
    creer(etat, 'ana', 'DIRECTION')
    jeton = connecter(client, 'ana').json()['jeton']
    comptes.desactiver(etat.base, 'ana')
    client.cookies.clear()
    assert client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {jeton}'}).status_code == 401


def jeton_vieilli(etat, identifiant, role, age):
    from app.auth import emettre
    return emettre(etat.reglages, identifiant, role, sid='session-1', maintenant=time.time() - age)


def test_jeton_renouvele_sur_activite_meme_session(client, etat):
    creer(etat, 'ana', 'DIRECTION')
    vieux = jeton_vieilli(etat, 'ana', 'DIRECTION', 20 * 60)
    r = client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {vieux}'})
    assert r.status_code == 200
    neuf = r.headers['x-jeton']
    a, b = (jwt.decode(j, CLE, algorithms=['HS256']) for j in (vieux, neuf))
    assert b['sid'] == a['sid'] and b['exp'] > a['exp'] and 'carte_jeton=' in r.headers['set-cookie']


def test_jeton_recent_non_renouvele(client, etat):
    creer(etat, 'ana', 'DIRECTION')
    recent = jeton_vieilli(etat, 'ana', 'DIRECTION', 60)
    r = client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {recent}'})
    assert r.status_code == 200 and 'x-jeton' not in r.headers


def test_deconnexion_revoque_aussi_les_jetons_renouveles(client, etat):
    creer(etat, 'ana', 'DIRECTION')
    vieux = jeton_vieilli(etat, 'ana', 'DIRECTION', 20 * 60)
    neuf = client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {vieux}'}).headers['x-jeton']
    client.cookies.clear()
    assert client.post('/api/auth/deconnexion', headers={'Authorization': f'Bearer {neuf}'}).status_code == 204
    for j in (vieux, neuf):
        assert client.get('/api/carte/geometrie', headers={'Authorization': f'Bearer {j}'}).status_code == 401


def test_mot_de_passe_hache_en_argon2(etat):
    creer(etat, 'ana', 'ANALYSTE')
    assert comptes.hachage_de(etat.base, 'ana').startswith('$argon2id$')


@pytest.mark.parametrize('identifiant, role, mdp, message', [
    ('ana', 'ANALYSTE', 'court', '12 caractères'),
    ('ana', 'ROI', MDP, 'rôle'),
    ('', 'ANALYSTE', MDP, 'identifiant'),
])
def test_creation_de_compte_verifiee(etat, identifiant, role, mdp, message):
    with pytest.raises(ValueError, match=message):
        comptes.creer(etat.base, identifiant, role, mdp)


def test_compte_en_double_refuse(etat):
    creer(etat, 'ana', 'ANALYSTE')
    with pytest.raises(ValueError, match='existe déjà'):
        creer(etat, 'ana', 'ADMIN')


def lignes_journal(etat):
    from sqlalchemy import select

    from app.base import Journal
    with etat.base() as s:
        return [(j.utilisateur, j.role, j.action) for j in s.scalars(select(Journal).order_by(Journal.id))]


def test_connexions_journalisees_sans_recopier_un_identifiant_inconnu(client, etat):
    creer(etat, 'ana', 'ANALYSTE')
    connecter(client, 'ZZ123456', 'faux')
    for _ in range(5):
        connecter(client, 'ana', 'faux')
    comptes.deverrouiller(etat.base, 'ana')
    connecter(client, 'ana')
    client.post('/api/auth/deconnexion')
    assert lignes_journal(etat) == [('inconnu', '', 'echec_connexion')] + \
        [('ana', 'ANALYSTE', 'echec_connexion')] * 4 + [('ana', 'ANALYSTE', 'verrouillage'),
                                                         ('ana', 'ANALYSTE', 'connexion'),
                                                         ('ana', 'ANALYSTE', 'deconnexion')]


@pytest.mark.parametrize('existe, bon, actif, verrouille, echecs, attendu', [
    (False, False, True, False, 0, ('echec_connexion', 0, False)),
    (True, True, True, False, 3, ('connexion', 0, False)),
    (True, True, False, False, 0, ('echec_connexion', 0, False)),        # désactivé, bon mot de passe
    (True, True, True, True, 5, ('echec_connexion', 5, True)),           # verrouillé, bon mot de passe
    (True, False, True, False, 3, ('echec_connexion', 4, False)),
    (True, False, True, False, 4, ('verrouillage', 5, True)),
    (True, False, True, True, 5, ('echec_connexion', 5, True)),          # déjà verrouillé : on ne compte plus
])
def test_decision_de_connexion(existe, bon, actif, verrouille, echecs, attendu):
    from app.auth import decider
    assert decider(existe, bon, actif, verrouille, echecs, echecs_max=5) == attendu
