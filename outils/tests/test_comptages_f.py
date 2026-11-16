"""Tests du script de comptage de l'étape F (sortie : comptages seulement, aucun groupe de moins de 5)."""
import os
import re
import sqlite3
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
SCRIPT = os.path.join(RACINE, 'outils', 'comptages_f.py')
sys.path[:0] = [os.path.join(RACINE, 'jeu_essai', 'v2'), os.path.join(RACINE, 'outils')]

import generer_dossiers as gd  # noqa: E402

GARDE_FOU = 'CARTE_DONNEES_' + 'REELLES'       # jamais écrit en entier hors de la commande destinée à Lounès


@pytest.fixture(scope='module')
def kit(tmp_path_factory):
    d = tmp_path_factory.mktemp('kit')
    g = gd.generer(n_dossiers=300, n_societes=300, graine=20261113).monde
    gd.ecrire_csv(str(d / 'liste_noire.csv'), g.bl, gd.COLONNES_BL)
    gd.ecrire_csv(str(d / 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    gd.ecrire_csv(str(d / 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'construire_base.py'),
                        '--liste-noire', str(d / 'liste_noire.csv'), '--rc-annonces', str(d / 'rc_annonces.csv'),
                        '--rc-personnes', str(d / 'rc_personnes.csv'), '--base', str(d / 'socle.sqlite')],
                       capture_output=True, text=True)
    assert r.returncode == 0
    return str(d / 'socle.sqlite')


def lancer(*args, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)


def nombre(sortie, libelle):  # un total masqué (« < 5 ») lève une erreur : le jeu est assez grand
    return int(re.search(rf'^{re.escape(libelle)} : (\d+)', sortie, re.M).group(1))


def test_comptages_egaux_au_contenu_de_la_base_et_aucune_valeur(kit, tmp_path):
    base = str(tmp_path / 'essai.sqlite')
    r = lancer('--base-kit', kit, '--base', base)
    assert r.returncode == 0, r.stderr
    cx, source = sqlite3.connect(base), sqlite3.connect(kit)
    un = lambda c, sql: c.execute(sql).fetchone()[0]  # noqa: E731
    assert nombre(r.stdout, 'inscrits du kit') == un(source, 'SELECT count(*) FROM bl_entite') == \
        nombre(r.stdout, 'inscrits rangés') == un(cx, 'SELECT count(*) FROM ref_liste_noire')
    assert nombre(r.stdout, 'fiches de personnes') == un(cx, 'SELECT count(*) FROM c2_personne')
    assert nombre(r.stdout, 'fiches de sociétés') == un(cx, 'SELECT count(*) FROM c2_societe')
    assert nombre(r.stdout, 'rapprochements du kit repris') == un(source, 'SELECT count(*) FROM correspondance_retenue')
    assert nombre(r.stdout, 'invariants en écart') == 0
    noms = [n for (n,) in source.execute('SELECT nom_affiche FROM bl_entite WHERE nom_affiche IS NOT NULL')]
    assert 'ZZ' not in r.stdout + r.stderr and not any(n in r.stdout for n in noms)


def valeurs(sortie):
    return re.findall(r'^ *([^:\n]+) : (.+)$', sortie, re.M)


def test_aucun_chiffre_de_un_a_quatre_ni_dans_les_totaux_ni_dans_les_groupes(kit, tmp_path):
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'essai.sqlite'))
    affiches = [v for libelle, v in valeurs(r.stdout) if libelle != 'invariants en écart']
    assert affiches and all(v == '< 5' or int(v) == 0 or int(v) >= 5 for v in affiches)
    import comptages_f
    assert [comptages_f._affiche(n) for n in (0, 1, 4, 5, 86)] == [0, '< 5', '< 5', 5, 86]
    assert comptages_f._groupes([('R01', 9, 9), ('R02', 7, 3), ('R03', 6, 6), ('libellé libre', 2, 2)]) == \
        [('R01', 9), ('R03', 6), (comptages_f.AUTRES, 9)]
    assert comptages_f._groupes([('R01', 9, 9), ('R03', 6, 6), ('R04', 2, 1)]) == [('R01', 9), (comptages_f.AUTRES, 8)]


def test_groupe_masque_impossible_a_retrouver_par_soustraction(kit, tmp_path):
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'essai.sqlite'))
    blocs = re.findall(r'^([^\n:]+) :\n((?:  .+\n)+)', r.stdout, re.M)
    assert len(blocs) == 2
    for titre, corps in blocs:
        lignes = re.findall(r'^  (.+) : (.+)$', corps, re.M)
        assert all(v != '< 5' for _, v in lignes), titre           # les petits groupes sont réunis, pas masqués un à un
        assert all(re.fullmatch(r'[A-Za-z0-9_]{1,24}|autres \(sous le seuil\)', nom) for nom, _ in lignes)
    cx = sqlite3.connect(str(tmp_path / 'essai.sqlite'))
    regles = dict(re.findall(r'^  (.+) : (\d+)$', blocs[0][1], re.M))
    assert sum(map(int, regles.values())) == cx.execute('SELECT count(*) FROM c2_mention').fetchone()[0]
    assert int(regles['autres (sous le seuil)']) >= 5


def test_seuil_sur_les_inscrits_distincts_pas_sur_les_lignes(kit, tmp_path):
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'essai.sqlite'))
    cx = sqlite3.connect(str(tmp_path / 'essai.sqlite'))
    distincts = dict(cx.execute('SELECT regle, count(DISTINCT fiche_a) FROM c2_correspondance GROUP BY 1'))
    bloc = r.stdout.split('rapprochements entre fiches par règle :')[1]
    affichees = dict(re.findall(r'^  ([A-Za-z0-9_]+) : (\d+)$', bloc, re.M))
    assert affichees and all(distincts[regle] >= 5 for regle in affichees)
    assert any(n < 5 for n in distincts.values())                   # le jeu a bien des règles sous le seuil


def test_libelle_de_regle_libre_jamais_affiche(kit, tmp_path):
    import shutil
    copie = str(tmp_path / 'kit.sqlite')
    shutil.copy(kit, copie)
    con = sqlite3.connect(copie)
    con.execute("UPDATE correspondance_retenue SET regle = 'ZELMOU BAKRITA de Kenitra' WHERE regle = 'R07'")
    con.commit()
    con.close()
    r = lancer('--base-kit', copie, '--base', str(tmp_path / 'essai.sqlite'))
    assert r.returncode == 0 and 'ZELMOU' not in r.stdout + r.stderr


def test_kit_non_fictif_refuse_sans_le_garde_fou_accepte_avec(kit, tmp_path, monkeypatch, capsys):
    import shutil
    import comptages_f
    copie = str(tmp_path / 'kit.sqlite')
    shutil.copy(kit, copie)
    con = sqlite3.connect(copie)
    con.execute("UPDATE bl_entite SET cin = ? WHERE entite_id = (SELECT min(entite_id) FROM bl_entite WHERE cin IS NOT NULL)",
                ('AB' + '100001',))
    con.commit()
    con.close()
    monkeypatch.delenv(comptages_f.GARDE_FOU, raising=False)
    assert comptages_f.main(['--base-kit', copie, '--base', str(tmp_path / 'a.sqlite')]) == 2
    sortie = capsys.readouterr()
    assert not os.path.exists(tmp_path / 'a.sqlite') and 'AB1' not in sortie.out + sortie.err
    monkeypatch.setenv(comptages_f.GARDE_FOU, '1')
    assert comptages_f.main(['--base-kit', copie, '--base', str(tmp_path / 'a.sqlite')]) == 0


def test_echec_classe_seulement_et_base_refusee(kit, tmp_path, monkeypatch, capsys):
    import comptages_f
    monkeypatch.setattr(comptages_f.c2_identites, 'charger_socle',
                        lambda cx, chemin: (_ for _ in ()).throw(ValueError('ZZ-SECRET')))
    assert comptages_f.main(['--base-kit', kit, '--base', str(tmp_path / 'a.sqlite')]) == 3
    sortie = capsys.readouterr()
    assert sortie.out.strip().splitlines()[-1] == 'échec : ValueError' and 'ZZ' not in sortie.out + sortie.err
    assert comptages_f.main(['--base-kit', kit, '--base', str(tmp_path / 'a.sqlite')]) == 2      # la base existe déjà
    r = lancer('--base-kit', kit, '--base', str(tmp_path / 'b.sqlite'), '--ZZ-secret')
    assert r.returncode == 2 and 'ZZ' not in r.stdout + r.stderr


def test_base_dans_le_depot_refusee_quand_les_donnees_sont_reelles(kit):
    base = os.path.join(RACINE, 'jeu_essai', 'sortie', 'jamais_creee_f.sqlite')
    r = lancer('--base-kit', kit, '--base', base, env=dict(os.environ, **{GARDE_FOU: '1'}))
    assert r.returncode == 2 and not os.path.exists(base)


def test_script_shell_affiche_les_comptages_et_refuse_le_depot(kit, tmp_path):
    shell = os.path.join(RACINE, 'outils', 'essai_reel_f.sh')
    r = subprocess.run(['sh', shell, kit], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0 and 'invariants en écart : 0' in r.stdout and 'ZZ' not in r.stdout + r.stderr
    assert subprocess.run(['sh', shell, kit], capture_output=True, cwd=os.path.join(RACINE, 'docs')).returncode == 9
    assert subprocess.run(['sh', shell, 'absente.sqlite'], capture_output=True, cwd=str(tmp_path)).returncode == 8


def test_invariant_en_ecart_nomme_sans_comptage(kit, tmp_path, monkeypatch, capsys):
    import comptages_f
    charger = comptages_f.c2_identites.charger_socle

    def charger_puis_abimer(cx, chemin):
        charger(cx, chemin)
        cx.execute("INSERT INTO c2_perimetre (mention) VALUES ('m_absente')")
        cx.commit()
    monkeypatch.setattr(comptages_f.c2_identites, 'charger_socle', charger_puis_abimer)
    assert comptages_f.main(['--base-kit', kit, '--base', str(tmp_path / 'a.sqlite')]) == 1
    sortie = capsys.readouterr().out
    assert 'invariants en écart : 1' in sortie and 'premier invariant en écart : c2_perimetre_non_vide' in sortie
