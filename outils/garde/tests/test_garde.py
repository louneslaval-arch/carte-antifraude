"""Tests de la garde des données. Toute chaîne de forme réelle est construite par concaténation,
pour que ce fichier passe lui-même la garde."""

import os
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'garde'))
import garde_donnees  # noqa: E402
import motifs  # noqa: E402

MARQUE = 'fictif-' + 'volontaire'

# Formes réelles, construites par morceaux
CIN_REEL = 'AB' + '123456'
CIN_FICTIF = 'ZZ' + '123456'
REF_DOSSIER = 'A' + '26' + 'B' + '1234'
RIB_REEL = '011' + ' 780 ' + '0000123456789012' + ' 34'
RIB_FICTIF = '999' + ' 780 ' + '0000123456789012' + ' 34'
ICE_REEL = '001' + '525354000099'
ICE_FICTIF = '999' + '525354000099'
TEL_REEL = '06' + '12 34 56 78'
TEL_REEL_INTER = '+212' + ' 6' + '12345678'
TEL_FICTIF = '06' + '00000042'
TEL_FICTIF_HORS_PLAGE = '06' + '00000142'
MEL_REEL = 'ali' + '@' + 'exemple.ma'
MEL_FICTIF = 'ali' + '@' + 'exemple.invalid'
ARABE = ''.join(chr(c) for c in (0x0645, 0x062D, 0x0645, 0x062F))
MUTATION = "b'" + 'X' * 4 + "'"
MUTATION_CHAINE = '"' + 'X' * 2 + 'quoi' + 'X' * 2 + '"'


def motifs_de(texte, chemin='src/module.py'):
    return [m for _, m in motifs.analyser(texte, chemin, racine=RACINE)]


@pytest.mark.parametrize('texte, motif', [
    ('cin = "' + CIN_REEL + '"', 'cin'),
    ('ref = ' + REF_DOSSIER, 'reference_dossier'),
    ('rib ' + RIB_REEL, 'rib'),
    ('ice ' + ICE_REEL, 'ice'),
    ('tel ' + TEL_REEL, 'telephone'),
    ('tel ' + TEL_REEL_INTER, 'telephone'),
    ('tel ' + TEL_FICTIF_HORS_PLAGE, 'telephone'),
    ('mel ' + MEL_REEL, 'courriel'),
    ('nom ' + ARABE, 'ecriture_arabe'),
    ('iter(f, ' + MUTATION + ')', 'trace_mutation'),
    ('x = ' + MUTATION_CHAINE, 'trace_mutation'),
])
def test_forme_reelle_refusee(texte, motif):
    assert motif in motifs_de(texte)


@pytest.mark.parametrize('texte', [
    'cin = "' + CIN_FICTIF + '"',
    'rib ' + RIB_FICTIF,
    'ice ' + ICE_FICTIF,
    'tel ' + TEL_FICTIF,
    'mel ' + MEL_FICTIF,
    'mel ali@exemple.test',
    "iter(f, b'')",
    'aucune donnée ici, R01 et AF20, SHA256, UTF8',
])
def test_forme_fictive_acceptee(texte):
    assert motifs_de(texte) == []


def test_la_marque_exempte_la_ligne():
    texte = 'cin = "' + CIN_REEL + '"  # ' + MARQUE
    assert motifs_de(texte) == []


def test_la_marque_n_exempte_que_sa_ligne():
    texte = 'a = 1  # ' + MARQUE + '\ncin = "' + CIN_REEL + '"'
    assert motifs.analyser(texte, 'src/module.py', racine=RACINE) == [(2, 'cin')]


def test_ecriture_arabe_admise_dans_un_fichier_autorise():
    assert motifs_de('nom ' + ARABE, 'jeu_essai/generer.py') == []
    assert motifs_de('nom ' + ARABE, 'pipeline/normalisation/noms.py') == []


def test_constat_rend_numero_de_ligne_et_motif_seulement():
    texte = 'rien\ncin ' + CIN_REEL + '\n'
    constats = motifs.analyser(texte, 'src/module.py', racine=RACINE)
    assert constats == [(2, 'cin')]
    for ligne, motif in constats:
        assert isinstance(ligne, int) and isinstance(motif, str)


@pytest.mark.parametrize('chemin', [
    'base.sqlite', 'sortie/export.xlsx', 'donnees.csv', 'a/b.json', 'piece.pdf', 'scan.jpg',
    '.env', 'deploiement/.env.prod', 'cle.pem', 'serveur.key', 'x.parquet', 'y.jsonl', 'z.db',
    'import/kamal_structure/api/dossier.ts', 'reference/v2/api/reponse.md', './.env',
])
def test_fichier_refuse(chemin):
    assert motifs.fichier_refuse(chemin, racine=RACINE)


@pytest.mark.parametrize('chemin', [
    'jeu_essai/donnees/inscrits.csv', 'pipeline/tests/attendu_kit.json',
    'api/app/schemas/carte.json', '.claude/settings.json', '.claude/skills/x/config.json',
    'deploiement/.env.exemple', 'api/app/graphe.py', 'docs/plan.md',
])
def test_fichier_autorise(chemin):
    assert not motifs.fichier_refuse(chemin, racine=RACINE)


def test_ligne_de_commande_sans_valeur_dans_la_sortie(tmp_path, capsys):
    (tmp_path / 'module.py').write_text('a = 1\ncin = "' + CIN_REEL + '"\nmel = "' + MEL_REEL + '"\n')
    code = garde_donnees.main(['--fichiers', 'module.py'], racine=str(tmp_path))
    sortie = capsys.readouterr()
    texte = sortie.out + sortie.err
    assert code == 1
    assert 'module.py:2: cin' in texte
    assert 'module.py:3: courriel' in texte
    assert CIN_REEL not in texte and MEL_REEL not in texte


def test_ligne_de_commande_fichier_propre(tmp_path, capsys):
    (tmp_path / 'module.py').write_text('cin = "' + CIN_FICTIF + '"\n')
    assert garde_donnees.main(['--fichiers', 'module.py'], racine=str(tmp_path)) == 0


def test_ligne_de_commande_fichier_refuse_sans_lire_son_contenu(tmp_path, capsys):
    (tmp_path / 'export.xlsx').write_bytes(b'\x00\x01' + CIN_REEL.encode())
    code = garde_donnees.main(['--fichiers', 'export.xlsx'], racine=str(tmp_path))
    texte = capsys.readouterr().out
    assert code == 1
    assert 'export.xlsx: fichier_refuse' in texte
    assert ': cin' not in texte


def test_ligne_de_commande_refuse_un_chemin_hors_du_depot(tmp_path, capsys):
    dedans = tmp_path / 'depot'
    dedans.mkdir()
    (tmp_path / 'dehors.txt').write_text('rien\n')
    code = garde_donnees.main(['--fichiers', str(tmp_path / 'dehors.txt')], racine=str(dedans))
    assert code == 2


def _git(depot, *args):
    subprocess.run(['git', '-C', str(depot), *args], check=True, capture_output=True)


def test_index_et_arbre(tmp_path, capsys):
    depot = tmp_path / 'depot'
    depot.mkdir()
    _git(depot, 'init', '-q')
    (depot / 'propre.py').write_text('a = 1\n')
    (depot / 'sale.py').write_text('cin = "' + CIN_REEL + '"\n')
    _git(depot, 'add', 'propre.py')
    assert garde_donnees.main(['--index'], racine=str(depot)) == 0
    assert garde_donnees.main(['--arbre'], racine=str(depot)) == 1
    assert 'sale.py:1: cin' in capsys.readouterr().out
    _git(depot, 'add', 'sale.py')
    (depot / 'sale.py').write_text('a = 2\n')  # l'index garde la version sale
    assert garde_donnees.main(['--index'], racine=str(depot)) == 1


def test_dossiers_ignores(tmp_path, capsys):
    (tmp_path / '.verif').mkdir()
    (tmp_path / '.verif' / 'm.py').write_text('cin = "' + CIN_REEL + '"\n')
    assert garde_donnees.main(['--fichiers', '.verif/m.py'], racine=str(tmp_path)) == 0


def test_dossier_ignore_mais_indexe_est_controle(tmp_path, capsys):
    # un fichier d'un dossier ignoré qui entre quand même dans l'index va être enregistré : il est contrôlé
    depot = tmp_path / 'depot'
    depot.mkdir()
    _git(depot, 'init', '-q')
    (depot / '.verif').mkdir()
    (depot / '.verif' / 'm.py').write_text('cin = "' + CIN_REEL + '"\n')
    _git(depot, 'add', '-' + 'f', '.verif/m.py')
    assert garde_donnees.main(['--index'], racine=str(depot)) == 1
    assert '.verif/m.py:1: cin' in capsys.readouterr().out


@pytest.mark.parametrize('codage', ['utf-16', 'utf-16-le', 'utf-16-be'])
def test_texte_en_utf16_avec_marque_est_lu(tmp_path, capsys, codage):
    bom = {'utf-16': b'', 'utf-16-le': b'\xff\xfe', 'utf-16-be': b'\xfe\xff'}[codage]
    (tmp_path / 'notes.txt').write_bytes(bom + ('cin = "' + CIN_REEL + '"\n').encode(codage))
    assert garde_donnees.main(['--fichiers', 'notes.txt'], racine=str(tmp_path)) == 1
    assert 'notes.txt:1: cin' in capsys.readouterr().out
