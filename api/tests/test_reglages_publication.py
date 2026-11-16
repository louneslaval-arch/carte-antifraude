"""Réglages lus une fois à l'entrée ; publication vérifiée avant d'être servie."""

import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import ReglageInvalide, lire_reglages
from app.graphe import PublicationRefusee, charger
from app.main import creer_app


def test_reglages_par_defaut(env):
    r = lire_reglages(env)
    assert r.duree_jeton_s == 8 * 3600 and r.quota_fiches == 2000 and r.debit == '60/minute'
    assert r.donnees_reelles is False and r.cookie_securise is True


@pytest.mark.parametrize('cle', [None, '', 'trop-courte'])
def test_cle_jwt_absente_ou_courte_refusee(env, cle):
    env = dict(env)
    if cle is None:
        del env['CARTE_CLE_JWT']
    else:
        env['CARTE_CLE_JWT'] = cle
    with pytest.raises(ReglageInvalide, match='CARTE_CLE_JWT'):
        lire_reglages(env)


def test_entier_invalide_refuse(env):
    with pytest.raises(ReglageInvalide, match='CARTE_QUOTA_FICHES'):
        lire_reglages(dict(env, CARTE_QUOTA_FICHES='beaucoup'))


def test_publication_fictive_chargee(publication):
    p = charger(publication, donnees_reelles=False)
    assert p.manifeste['fictif'] is True and p.noeuds == p.manifeste['noeuds'] == len(p.geometrie['noeuds']['t'])
    assert p.etag == '"' + p.manifeste['empreinte'] + '"'


def test_publication_reelle_refusee_sans_autorisation(publication_reelle):
    with pytest.raises(PublicationRefusee, match='CARTE_DONNEES_REELLES'):
        charger(publication_reelle, donnees_reelles=False)
    assert charger(publication_reelle, donnees_reelles=True).manifeste['fictif'] is False


def test_fichier_altere_refuse(publication, tmp_path):
    copie = str(tmp_path / 'pub')
    shutil.copytree(publication, copie)
    with open(os.path.join(copie, 'geometrie.json'), 'a', encoding='utf-8') as f:
        f.write(' ')
    with pytest.raises(PublicationRefusee, match='geometrie.json'):
        charger(copie, donnees_reelles=False)


def test_manifeste_absent_refuse(tmp_path):
    with pytest.raises(PublicationRefusee, match='manifeste'):
        charger(str(tmp_path), donnees_reelles=False)


def test_format_inconnu_refuse(publication, tmp_path):
    copie = str(tmp_path / 'pub')
    shutil.copytree(publication, copie)
    chemin = os.path.join(copie, 'manifeste.json')
    m = json.load(open(chemin, encoding='utf-8'))
    m['format'] = 99
    json.dump(m, open(chemin, 'w', encoding='utf-8'))
    with pytest.raises(PublicationRefusee, match='format'):
        charger(copie, donnees_reelles=False)


def test_sante_publique(env):
    with TestClient(creer_app(lire_reglages(env)), base_url='https://testserver') as c:
        r = c.get('/api/sante')
    m = json.load(open(os.path.join(env['CARTE_PUBLICATION'], 'manifeste.json'), encoding='utf-8'))
    assert r.status_code == 200
    assert r.json() == dict(etat='ok', version=r.json()['version'], date_publication=m['date_publication'],
                            noeuds=m['noeuds'], fictif=True)


def test_sante_sans_publication(env):
    env = {k: v for k, v in env.items() if k != 'CARTE_PUBLICATION'}
    with TestClient(creer_app(lire_reglages(env)), base_url='https://testserver') as c:
        r = c.get('/api/sante')
    assert r.status_code == 503 and r.json()['etat'] == 'sans_publication'


def test_demarrage_refuse_une_publication_reelle_non_autorisee(env, publication_reelle):
    with pytest.raises(PublicationRefusee):
        creer_app(lire_reglages(dict(env, CARTE_PUBLICATION=publication_reelle)))
