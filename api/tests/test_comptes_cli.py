"""Ligne de commande d'administration des comptes."""

import pytest
from conftest import CLE, MDP

from app import comptes
from app.base import ouvrir


@pytest.fixture
def cli(monkeypatch, tmp_path):
    url = f'sqlite:///{tmp_path}/c.db'
    monkeypatch.setenv('CARTE_CLE_JWT', CLE)
    monkeypatch.setenv('CARTE_BASE_URL', url)
    monkeypatch.setattr(comptes.getpass, 'getpass', lambda _invite: MDP)
    return ouvrir(url)


def test_creer_puis_lister(cli, capsys):
    assert comptes.main(['creer', 'ana', 'ANALYSTE']) == 0
    assert comptes.main(['creer', 'adm', 'ADMIN']) == 0
    assert comptes.main(['lister']) == 0
    assert capsys.readouterr().out.splitlines() == ['adm\tADMIN\tTrue\tFalse', 'ana\tANALYSTE\tTrue\tFalse']
    assert comptes.hachage_de(cli, 'ana').startswith('$argon2id$')


def test_desactiver_et_deverrouiller(cli, capsys):
    comptes.main(['creer', 'ana', 'ANALYSTE'])
    assert comptes.main(['desactiver', 'ana']) == 0
    with cli.begin() as s:
        from app.base import Utilisateur
        s.query(Utilisateur).filter_by(identifiant='ana').update({'verrouille': True, 'echecs': 5})
    assert comptes.main(['deverrouiller', 'ana']) == 0
    comptes.main(['lister'])
    assert capsys.readouterr().out.splitlines() == ['ana\tANALYSTE\tFalse\tFalse']


def test_refus_explique_et_code_1(cli, capsys):
    assert comptes.main(['deverrouiller', 'personne']) == 1
    assert capsys.readouterr().err == 'Refusé : compte personne introuvable\n'
    comptes.main(['creer', 'ana', 'ANALYSTE'])
    assert comptes.main(['creer', 'ana', 'ANALYSTE']) == 1
    assert 'existe déjà' in capsys.readouterr().err


def test_role_inconnu_refuse_par_la_ligne_de_commande(cli):
    with pytest.raises(SystemExit) as e:
        comptes.main(['creer', 'ana', 'ROI'])
    assert e.value.code == 2


def test_le_mot_de_passe_n_est_jamais_un_argument(cli):
    with pytest.raises(SystemExit):
        comptes.main(['creer', 'ana', 'ANALYSTE', MDP])
