"""Garde des données : refuse les formes réelles et les fichiers interdits.

Usage :
    garde_donnees.py --index          fichiers indexés (contenu de l'index) ; utilisé par le crochet git
    garde_donnees.py --arbre          fichiers modifiés et non suivis, hors ignorés
    garde_donnees.py --tout           fichiers suivis
    garde_donnees.py --fichiers f...  fichiers donnés (dans le dépôt seulement)

Affiche « chemin:ligne: motif », jamais la valeur. Sort en 1 s'il y a un constat, 0 sinon, 2 sur erreur d'usage.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motifs  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOSSIERS_IGNORES = ('.verif', '.venv', 'mutants')


def _ignore(rel):
    return rel.split('/', 1)[0] in DOSSIERS_IGNORES


def _git(racine, *args):
    r = subprocess.run(['git', '-C', racine, *args], capture_output=True, check=True)
    return r.stdout


def _liste_git(racine, *args):
    return [c for c in _git(racine, *args, '-z').decode('utf-8').split('\0') if c]


def _controler(rel, lire_octets):
    """Constats d'un fichier : nom d'abord ; contenu seulement s'il n'est ni refusé ni binaire."""
    if motifs.fichier_refuse(rel):
        return [f'{rel}: fichier_refuse']
    octets = lire_octets()
    if octets is None or b'\0' in octets[:8192]:
        return []
    texte = octets.decode('utf-8', errors='replace')
    return [f'{rel}:{ligne}: {motif}' for ligne, motif in motifs.analyser(texte, rel)]


def _lire_fichier(chemin):
    def lire():
        try:
            with open(chemin, 'rb') as f:
                return f.read()
        except (FileNotFoundError, IsADirectoryError):
            return None
    return lire


def main(argv=None, racine=None):
    racine = os.path.realpath(racine or RACINE)
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parseur.add_mutually_exclusive_group(required=True)
    mode.add_argument('--index', action='store_true')
    mode.add_argument('--arbre', action='store_true')
    mode.add_argument('--tout', action='store_true')
    mode.add_argument('--fichiers', nargs='+')
    args = parseur.parse_args(argv)

    a_controler = []  # (chemin relatif, fonction qui lit les octets)
    if args.fichiers:
        for f in args.fichiers:
            chemin = os.path.realpath(f if os.path.isabs(f) else os.path.join(racine, f))
            if os.path.commonpath([chemin, racine]) != racine:
                print('erreur : chemin hors du dépôt refusé', file=sys.stderr)
                return 2
            a_controler.append((os.path.relpath(chemin, racine).replace(os.sep, '/'), _lire_fichier(chemin)))
    elif args.index:
        for rel in _liste_git(racine, 'diff', '--cached', '--name-only', '--diff-filter=ACMR'):
            a_controler.append((rel, lambda rel=rel: _git(racine, 'show', f':{rel}')))
    else:
        if args.arbre:
            noms = _liste_git(racine, 'ls-files', '-m', '-o', '--exclude-standard')
        else:
            noms = _liste_git(racine, 'ls-files')
        for rel in dict.fromkeys(noms):
            chemin = os.path.join(racine, rel)
            if os.path.isfile(chemin):
                a_controler.append((rel, _lire_fichier(chemin)))

    constats = []
    for rel, lire in a_controler:
        if not _ignore(rel):
            constats.extend(_controler(rel, lire))
    for c in constats:
        print(c)
    print(f'garde : {len(a_controler)} fichier(s), {len(constats)} constat(s)', file=sys.stderr)
    return 1 if constats else 0


if __name__ == '__main__':
    sys.exit(main())
