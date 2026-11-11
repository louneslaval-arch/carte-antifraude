"""Fonctions communes aux crochets de Claude Code. Sans dépendance ; réutilise outils/garde/."""
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.realpath(os.environ.get('CLAUDE_PROJECT_DIR') or os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, 'outils', 'garde'))
import motifs  # noqa: E402


def lire_entree():
    try:
        return json.load(sys.stdin)
    except (ValueError, OSError):
        return {}


def reperes_interdits():
    chemin = os.path.join(ICI, 'chemins_interdits.txt')
    with open(chemin, encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith('#')]


def repere_present(texte):
    """Rend le premier repère interdit présent dans le texte (comparaison sensible à la casse), sinon None."""
    texte = os.path.expanduser(texte) + '\n' + texte
    for r in reperes_interdits():
        if r in texte:
            return r
    return None


def bloquer(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def relatif_au_depot(chemin):
    """Chemin relatif à la racine du dépôt si le chemin y est, sinon None."""
    absolu = os.path.realpath(os.path.expanduser(chemin) if os.path.isabs(os.path.expanduser(chemin))
                              else os.path.join(RACINE, chemin))
    if os.path.commonpath([absolu, RACINE]) != RACINE:
        return None
    return os.path.relpath(absolu, RACINE).replace(os.sep, '/')
