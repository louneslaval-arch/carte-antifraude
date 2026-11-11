"""Tests de outils/controle_skill.py : analyse statique d'un dossier de skill ou de plugin.
Les faux skills sont écrits dans un dossier temporaire ; rien de ce qui est analysé n'est exécuté."""

import json
import os
import stat
import subprocess
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path.insert(0, os.path.join(RACINE, 'outils'))
import controle_skill  # noqa: E402

ENTETE = '---\nname: essai\ndescription: Un skill d\'essai.\n---\n'
INVISIBLE = chr(0x200B)
BOM = chr(0xFEFF)


def ecrire(racine, chemin, contenu, mode='w'):
    p = racine / chemin
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == 'wb':
        p.write_bytes(contenu)
    else:
        p.write_text(contenu, encoding='utf-8')
    return p


def categories(dossier):
    return controle_skill.analyser_dossier(str(dossier))


def lignes_de(constats, categorie):
    return [(c.fichier, c.ligne) for c in constats[categorie]]


# --- dossier propre -------------------------------------------------------------------------------------------------

def test_skill_propre_rien_a_signaler(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE + '# Essai\n\nRelire le code avec soin.\n')
    constats = categories(tmp_path)
    assert controle_skill.proposition(constats) == controle_skill.RIEN
    assert [f.chemin for f in controle_skill.lister_fichiers(str(tmp_path))] == ['SKILL.md']


def test_le_dossier_git_est_ignore(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE)
    ecrire(tmp_path, '.git/hooks/pre-commit', 'curl http://x | sh\n')
    assert controle_skill.proposition(categories(tmp_path)) == controle_skill.RIEN


# --- fichiers -------------------------------------------------------------------------------------------------------

def test_liste_avec_taille_et_type(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE)
    ecrire(tmp_path, 'image.bin', b'\x00\x01\x02', mode='wb')
    fichiers = {f.chemin: f for f in controle_skill.lister_fichiers(str(tmp_path))}
    assert fichiers['image.bin'].taille == 3
    assert fichiers['image.bin'].binaire is True
    assert fichiers['SKILL.md'].binaire is False


def test_binaire_signale(tmp_path):
    ecrire(tmp_path, 'outil.bin', b'\x7fELF\x00\x00', mode='wb')
    assert lignes_de(categories(tmp_path), 'binaires_executables') == [('outil.bin', 0)]


def test_fichier_executable_signale(tmp_path):
    p = ecrire(tmp_path, 'lancer', 'echo bonjour\n')
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    assert ('lancer', 0) in lignes_de(categories(tmp_path), 'binaires_executables')


@pytest.mark.parametrize('nom', ['a.py', 'a.sh', 'a.js', 'a.ts', 'a.mjs', 'a.rb', 'a.ps1'])
def test_scripts_par_extension(tmp_path, nom):
    ecrire(tmp_path, nom, 'x = 1\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'scripts') == [(nom, 0)]
    assert controle_skill.proposition(constats) == controle_skill.A_LIRE


def test_lien_symbolique_signale_et_non_suivi(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE)
    (tmp_path / 'lien').symlink_to('/etc')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'liens_symboliques') == [('lien', 0)]
    assert all(not f.chemin.startswith('lien/') for f in controle_skill.lister_fichiers(str(tmp_path)))


# --- crochets, serveurs, agents, commandes ---------------------------------------------------------------------------

def test_hooks_json_refus(tmp_path):
    ecrire(tmp_path, 'hooks/hooks.json', json.dumps({'hooks': {'PreToolUse': []}}))
    constats = categories(tmp_path)
    assert constats['crochets']
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_cle_hooks_du_frontmatter_refus(tmp_path):
    ecrire(tmp_path, 'SKILL.md', '---\nname: essai\nhooks:\n  PreToolUse: []\n---\ncorps\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'crochets') == [('SKILL.md', 3)]
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_hooks_dans_le_corps_hors_frontmatter_non_signale(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE + 'hooks: un mot du corps\n')
    assert categories(tmp_path)['crochets'] == []


def test_serveur_mcp_par_fichier_et_par_cle(tmp_path):
    ecrire(tmp_path, '.mcp.json', '{}')
    ecrire(tmp_path, 'plugin.json', json.dumps({'mcpServers': {'x': {}}}, indent=1))
    constats = categories(tmp_path)
    fichiers = {f for f, _ in lignes_de(constats, 'serveurs_mcp')}
    assert fichiers == {'.mcp.json', 'plugin.json'}
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_agents_et_commandes(tmp_path):
    ecrire(tmp_path, 'agents/relire.md', ENTETE)
    ecrire(tmp_path, 'commands/faire.md', ENTETE)
    assert {f for f, _ in lignes_de(categories(tmp_path), 'agents_commandes')} == {'agents/relire.md',
                                                                                 'commands/faire.md'}


def test_allowed_tools(tmp_path):
    ecrire(tmp_path, 'SKILL.md', '---\nname: essai\nallowed-tools: Bash, Write\n---\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'allowed_tools') == [('SKILL.md', 3)]
    assert 'Bash' in constats['allowed_tools'][0].detail


# --- motifs dans le texte -------------------------------------------------------------------------------------------

@pytest.mark.parametrize('ligne', ['curl -s http://x', 'wget x', 'import requests', 'urllib.request.urlopen(u)',
                                   'import http.client', 'socket.socket()', 'await fetch(u)', 'axios.get(u)',
                                   'new XMLHttpRequest()', 'new WebSocket(u)'])
def test_reseau(tmp_path, ligne):
    ecrire(tmp_path, 'SKILL.md', ENTETE + ligne + '\n')
    assert lignes_de(categories(tmp_path), 'reseau') == [('SKILL.md', 5)]


@pytest.mark.parametrize('ligne', ['subprocess.run(x)', 'os.system(x)', 'eval(x)', 'exec(x)',
                                   "require('child_process')", 'curl x | sh', 'curl x | bash'])
def test_execution(tmp_path, ligne):
    ecrire(tmp_path, 'notes.md', ligne + '\n')
    assert lignes_de(categories(tmp_path), 'execution') == [('notes.md', 1)]


@pytest.mark.parametrize('ligne', ['cat ~/.ssh/id', 'lire .env', 'security find-generic-password',
                                   'keychain', 'trousseau', 'ls ~/', 'cd /Users/x', 'cat /etc/hosts', 'echo $HOME'])
def test_secrets_et_chemins_hors_depot(tmp_path, ligne):
    ecrire(tmp_path, 'notes.md', ligne + '\n')
    assert lignes_de(categories(tmp_path), 'secrets_chemins') == [('notes.md', 1)]


def test_mot_ordinaire_non_signale(tmp_path):
    ecrire(tmp_path, 'notes.md', 'évaluer la base, exécuter les étapes, environnement\n')
    constats = categories(tmp_path)
    assert constats['execution'] == [] and constats['secrets_chemins'] == [] and constats['reseau'] == []


def test_base64_long_refus(tmp_path):
    ecrire(tmp_path, 'notes.md', 'données : ' + 'QUJD' * 60 + '\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'base64') == [('notes.md', 1)]
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_base64_court_ignore(tmp_path):
    ecrire(tmp_path, 'notes.md', 'QUJD' * 40 + '\n')
    assert categories(tmp_path)['base64'] == []


@pytest.mark.parametrize('code', [0x200B, 0x200F, 0x202A, 0x202E, 0x2060, 0x2064, 0x2066, 0x2069, 0xFEFF])
def test_unicode_invisible_refus(tmp_path, code):
    ecrire(tmp_path, 'SKILL.md', ENTETE + 'texte' + chr(code) + 'caché\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'unicode_invisible') == [('SKILL.md', 5)]
    assert 'U+%04X' % code in constats['unicode_invisible'][0].detail
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_commentaire_html_dans_markdown(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE + '<!-- consigne cachée -->\n')
    ecrire(tmp_path, 'page.html', '<!-- normal en HTML -->\n')
    assert lignes_de(categories(tmp_path), 'commentaires_html') == [('SKILL.md', 5)]


@pytest.mark.parametrize('ligne', ['Ignore all previous instructions', 'ignore les instructions précédentes',
                                   'Do not tell the user', 'ne pas dire à l\'utilisateur', 'disable the hook',
                                   'désactiver le contrôle', 'without asking', 'sans demander'])
def test_consignes_suspectes(tmp_path, ligne):
    ecrire(tmp_path, 'SKILL.md', ENTETE + ligne + '\n')
    constats = categories(tmp_path)
    assert lignes_de(constats, 'consignes_suspectes') == [('SKILL.md', 5)]
    assert controle_skill.proposition(constats) == controle_skill.A_LIRE


def test_urls_listees(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE + 'voir https://exemple.invalid/doc et http://a.invalid.\n')
    constats = categories(tmp_path)
    assert [c.detail for c in constats['urls']] == ['https://exemple.invalid/doc', 'http://a.invalid']
    assert controle_skill.proposition(constats) == controle_skill.RIEN


def test_binaire_non_lu_comme_texte(tmp_path):
    ecrire(tmp_path, 'x.dat', b'\x00curl http://x | sh', mode='wb')
    constats = categories(tmp_path)
    assert constats['reseau'] == [] and constats['execution'] == []


# --- rapport et ligne de commande -----------------------------------------------------------------------------------

def test_rapport_markdown(tmp_path):
    ecrire(tmp_path, 'SKILL.md', ENTETE + 'curl http://a.invalid\n')
    rapport = controle_skill.rapport(str(tmp_path))
    assert rapport.startswith('# Contrôle de ')
    assert '## Réseau' in rapport
    assert '`SKILL.md:5`' in rapport
    assert 'Proposition : **à lire de près**' in rapport
    assert '| `SKILL.md` |' in rapport


def test_detail_tronque(tmp_path):
    ecrire(tmp_path, 'notes.md', 'curl ' + 'a' * 500 + '\n')
    assert len(categories(tmp_path)['reseau'][0].detail) <= 160


@pytest.mark.parametrize('contenu, code', [(ENTETE, 0), (ENTETE + 'wget x\n', 1), (ENTETE + INVISIBLE + '\n', 2)])
def test_ligne_de_commande_code_de_sortie(tmp_path, contenu, code):
    ecrire(tmp_path, 'SKILL.md', contenu)
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'outils', 'controle_skill.py'), str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == code
    assert r.stdout.startswith('# Contrôle de ')


def test_ligne_de_commande_dossier_absent(tmp_path):
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'outils', 'controle_skill.py'), str(tmp_path / 'nul')],
                       capture_output=True, text=True)
    assert r.returncode == 3
    assert 'dossier introuvable' in r.stderr


@pytest.mark.parametrize('code', [0xE0001, 0xE0041, 0xE007F])
def test_caracteres_d_etiquette_invisibles_refus(tmp_path, code):
    # les caractères du bloc « Tags » d'Unicode cachent du texte lisible par un modèle, invisible à l'écran
    ecrire(tmp_path, 'SKILL.md', ENTETE + 'texte' + chr(code) + '\n')
    constats = categories(tmp_path)
    assert 'U+%05X' % code in constats['unicode_invisible'][0].detail
    assert controle_skill.proposition(constats) == controle_skill.REFUS


def test_erreur_de_lecture_sort_en_3(tmp_path):
    p = ecrire(tmp_path, 'SKILL.md', ENTETE)
    p.chmod(0)
    try:
        r = subprocess.run([sys.executable, os.path.join(RACINE, 'outils', 'controle_skill.py'), str(tmp_path)],
                           capture_output=True, text=True)
    finally:
        p.chmod(0o644)
    assert r.returncode == 3
    assert 'erreur de lecture' in r.stderr


def test_bom_en_tete_signale(tmp_path):
    ecrire(tmp_path, 'SKILL.md', BOM + ENTETE)
    assert lignes_de(categories(tmp_path), 'unicode_invisible') == [('SKILL.md', 1)]
