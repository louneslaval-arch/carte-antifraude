#!/usr/bin/env python3
"""Contrôle statique d'un dossier de skill ou de plugin avant installation (annexe H.1 du document de lancement).

N'exécute, n'importe et ne suit rien de ce qu'il analyse : il lit des octets, cherche des motifs et rend un rapport
Markdown par catégorie, avec fichier:ligne, puis une proposition : rien à signaler, à lire de près, refus.

Usage : outils/controle_skill.py <dossier>
Code de sortie : 0 rien à signaler, 1 à lire de près, 2 refus, 3 dossier introuvable ou illisible.
"""
import os
import re
import stat
import sys
from dataclasses import dataclass

RIEN = 'rien à signaler'
A_LIRE = 'à lire de près'
REFUS = 'refus'

EXTENSIONS_SCRIPT = ('.py', '.sh', '.js', '.ts', '.mjs', '.rb', '.ps1')
DOSSIERS_IGNORES = {'.git'}
LONGUEUR_DETAIL = 160

# (clé, titre, conséquence) ; l'ordre est celui du rapport
CATEGORIES = (
    ('crochets', 'Crochets', REFUS),
    ('serveurs_mcp', 'Serveurs MCP', REFUS),
    ('unicode_invisible', 'Unicode invisible', REFUS),
    ('base64', 'Chaînes en base64 de plus de 200 caractères', REFUS),
    ('binaires_executables', 'Fichiers binaires ou exécutables', A_LIRE),
    ('liens_symboliques', 'Liens symboliques (non suivis)', A_LIRE),
    ('scripts', 'Scripts', A_LIRE),
    ('agents_commandes', 'Agents et commandes', A_LIRE),
    ('allowed_tools', 'allowed-tools', A_LIRE),
    ('reseau', 'Réseau', A_LIRE),
    ('execution', 'Exécution', A_LIRE),
    ('secrets_chemins', 'Secrets et chemins hors du dépôt', A_LIRE),
    ('commentaires_html', 'Commentaires HTML dans le Markdown', A_LIRE),
    ('consignes_suspectes', 'Consignes suspectes', A_LIRE),
    ('urls', 'URL citées', RIEN),
)

MOTIFS_TEXTE = {
    'reseau': re.compile(r'\bcurl\b|\bwget\b|\brequests\b|\burllib\b|\bhttp\.client\b|\bsocket\b|\bfetch\(|'
                         r'\baxios\b|\bXMLHttpRequest\b|\bWebSocket\b'),
    'execution': re.compile(r'\bsubprocess\b|\bos\.system\b|(?<![\w.])eval\(|(?<![\w.])exec\(|\bchild_process\b|'
                            r'\|\s*(?:ba)?sh\b'),
    'secrets_chemins': re.compile(r'\.ssh\b|(?<![\w])\.env\b|\bkeychain\b|find-generic-password|'
                                  r'find-internet-password|\btrousseau\b|~/|/Users/|/etc/|\$HOME\b|\$\{HOME\}',
                                  re.IGNORECASE),
    'base64': re.compile(r'[A-Za-z0-9+/]{201,}={0,2}'),
    'consignes_suspectes': re.compile(
        r'\bignore\b.{0,30}\binstructions?\b|\bignorer?\b.{0,30}\b(?:instructions?|consignes?|règles?)\b|'
        r'\b(?:do not|don\'t|never)\s+(?:tell|mention|inform|reveal|show)\b|'
        r'\bne\s+(?:pas|jamais)\s+(?:dire|mentionner|signaler|informer|révéler|montrer)\b|'
        r'\bdisabl(?:e|ing)\b|\bdésactiv(?:er|ez|e)\b|'
        r'\bwithout\s+(?:asking|confirmation|permission|telling)\b|\bsans\s+(?:demander|confirmation|prévenir)\b',
        re.IGNORECASE),
}
URL = re.compile(r'https?://[^\s<>"\'`()\[\]]+')
# plages de l'annexe H.1, plus le bloc « Tags » (texte caché lisible par un modèle, invisible à l'écran)
INVISIBLES = re.compile('[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]')
ALLOWED_TOOLS = re.compile(r'^\s*allowed-tools\s*:', re.IGNORECASE)
CLE_HOOKS_FRONTMATTER = re.compile(r'^hooks\s*:')
CLE_HOOKS_JSON = re.compile(r'"hooks"\s*:')
CLE_MCP = re.compile(r'\bmcpServers\b')


@dataclass(frozen=True)
class Fichier:
    chemin: str
    taille: int
    binaire: bool
    executable: bool
    lien: bool


@dataclass(frozen=True)
class Constat:
    fichier: str
    ligne: int  # 0 : le fichier entier
    detail: str


def _tronquer(texte):
    texte = texte.strip()
    return texte if len(texte) <= LONGUEUR_DETAIL else texte[:LONGUEUR_DETAIL - 1] + '…'


def _est_binaire(octets):
    if b'\x00' in octets[:8192]:
        return True
    try:
        octets.decode('utf-8')
    except UnicodeDecodeError:
        return True
    return False


def lister_fichiers(dossier):
    """Fichiers du dossier, triés, sans suivre les liens symboliques ni entrer dans .git."""
    resultat = []
    for base, sous, noms in os.walk(dossier, followlinks=False):
        sous[:] = sorted(s for s in sous if s not in DOSSIERS_IGNORES)
        rel_base = os.path.relpath(base, dossier)
        # un lien symbolique vers un dossier apparaît dans « sous » : on le signale sans y entrer
        for s in list(sous):
            if os.path.islink(os.path.join(base, s)):
                sous.remove(s)
                resultat.append(Fichier(_rel(rel_base, s), 0, False, False, True))
        for nom in sorted(noms):
            chemin = os.path.join(base, nom)
            rel = _rel(rel_base, nom)
            infos = os.lstat(chemin)
            if stat.S_ISLNK(infos.st_mode):
                resultat.append(Fichier(rel, 0, False, False, True))
                continue
            with open(chemin, 'rb') as f:
                octets = f.read()
            resultat.append(Fichier(rel, infos.st_size, _est_binaire(octets),
                                    bool(infos.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)), False))
    return sorted(resultat, key=lambda f: f.chemin)


def _rel(base, nom):
    return nom if base == '.' else os.path.join(base, nom).replace(os.sep, '/')


def _bornes_frontmatter(lignes):
    """Numéros (1-indexés) des lignes du frontmatter YAML, s'il y en a un en tête."""
    if not lignes or lignes[0].lstrip('﻿').strip() != '---':
        return set()
    for i in range(1, len(lignes)):
        if lignes[i].strip() == '---':
            return set(range(2, i + 1))
    return set()


def analyser_dossier(dossier):
    constats = {cle: [] for cle, _, _ in CATEGORIES}
    for f in lister_fichiers(dossier):
        if f.lien:
            constats['liens_symboliques'].append(Constat(f.chemin, 0, 'lien symbolique'))
            continue
        nom = os.path.basename(f.chemin)
        parties = f.chemin.split('/')
        if f.binaire or f.executable:
            constats['binaires_executables'].append(
                Constat(f.chemin, 0, ('binaire' if f.binaire else '') + (' exécutable' if f.executable else '')))
        if nom.endswith(EXTENSIONS_SCRIPT):
            constats['scripts'].append(Constat(f.chemin, 0, 'script'))
        if nom == 'hooks.json':
            constats['crochets'].append(Constat(f.chemin, 0, 'définition de crochets'))
        if nom == '.mcp.json':
            constats['serveurs_mcp'].append(Constat(f.chemin, 0, 'définition de serveurs MCP'))
        if ('agents' in parties[:-1] or 'commands' in parties[:-1]) and nom.endswith('.md'):
            constats['agents_commandes'].append(Constat(f.chemin, 0, 'agent' if 'agents' in parties else 'commande'))
        if f.binaire:
            continue
        with open(os.path.join(dossier, f.chemin), encoding='utf-8') as fd:
            lignes = fd.read().split('\n')
        _analyser_texte(f.chemin, lignes, constats)
    return constats


def _analyser_texte(chemin, lignes, constats):
    markdown = chemin.endswith('.md')
    json_ = chemin.endswith('.json')
    entete = _bornes_frontmatter(lignes) if markdown else set()
    for n, ligne in enumerate(lignes, start=1):
        for m in INVISIBLES.finditer(ligne):
            constats['unicode_invisible'].append(Constat(chemin, n, 'U+%04X' % ord(m.group())))
        if n in entete and CLE_HOOKS_FRONTMATTER.match(ligne):
            constats['crochets'].append(Constat(chemin, n, 'clé hooks du frontmatter'))
        if json_ and CLE_HOOKS_JSON.search(ligne) and os.path.basename(chemin) != 'hooks.json':
            constats['crochets'].append(Constat(chemin, n, _tronquer(ligne)))
        if CLE_MCP.search(ligne):
            constats['serveurs_mcp'].append(Constat(chemin, n, _tronquer(ligne)))
        if ALLOWED_TOOLS.match(ligne):
            constats['allowed_tools'].append(Constat(chemin, n, _tronquer(ligne)))
        if markdown and '<!--' in ligne:
            constats['commentaires_html'].append(Constat(chemin, n, _tronquer(ligne)))
        for cle, motif in MOTIFS_TEXTE.items():
            if motif.search(ligne):
                constats[cle].append(Constat(chemin, n, _tronquer(ligne)))
        for m in URL.finditer(ligne):
            constats['urls'].append(Constat(chemin, n, m.group().rstrip('.,;:')))


def proposition(constats):
    resultat = RIEN
    for cle, _, consequence in CATEGORIES:
        if constats[cle] and consequence == REFUS:
            return REFUS
        if constats[cle] and consequence == A_LIRE:
            resultat = A_LIRE
    return resultat


def rapport(dossier, constats=None):
    fichiers = lister_fichiers(dossier)
    constats = analyser_dossier(dossier) if constats is None else constats
    prop = proposition(constats)
    sortie = [f'# Contrôle de `{dossier}`', '', f'Proposition : **{prop}**', '',
              f'## Fichiers ({len(fichiers)})', '', '| Fichier | Taille | Type |', '| --- | ---: | --- |']
    for f in fichiers:
        genre = 'lien' if f.lien else ('binaire' if f.binaire else 'texte') + (', exécutable' if f.executable else '')
        sortie.append(f'| `{f.chemin}` | {f.taille} | {genre} |')
    for cle, titre, consequence in CATEGORIES:
        liste = constats[cle]
        sortie += ['', f'## {titre} ({len(liste)})', '']
        if not liste:
            sortie.append('Rien.')
            continue
        if cle == 'urls':
            for url in sorted({c.detail for c in liste}):
                sortie.append(f'- {url}')
            continue
        for c in liste:
            lieu = f'`{c.fichier}:{c.ligne}`' if c.ligne else f'`{c.fichier}`'
            sortie.append(f'- {lieu} : {c.detail}')
    return '\n'.join(sortie) + '\n'


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage : controle_skill.py <dossier>', file=sys.stderr)
        return 3
    dossier = argv[0]
    if not os.path.isdir(dossier):
        print('dossier introuvable', file=sys.stderr)
        return 3
    try:
        constats = analyser_dossier(dossier)
        texte = rapport(dossier, constats)
    except (OSError, UnicodeDecodeError) as e:
        # un fichier illisible n'est pas « à lire de près » : le contrôle n'a pas eu lieu
        print(f'erreur de lecture ({type(e).__name__}) : contrôle impossible', file=sys.stderr)
        return 3
    sys.stdout.write(texte)
    return {RIEN: 0, A_LIRE: 1, REFUS: 2}[proposition(constats)]


if __name__ == '__main__':
    sys.exit(main())
