"""Stop : refuse de conclure si garde_donnees.py --arbre trouve un constat. Ne bloque pas une seconde fois
(stop_hook_active) : le crochet git reste la barrière."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import RACINE, bloquer, lire_entree  # noqa: E402


def main():
    entree = lire_entree()
    if entree.get('stop_hook_active'):
        sys.exit(0)
    python = os.path.join(RACINE, '.venv', 'bin', 'python')
    garde = os.path.join(RACINE, 'outils', 'garde', 'garde_donnees.py')
    r = subprocess.run([python if os.path.exists(python) else sys.executable, garde, '--arbre'],
                       capture_output=True, text=True, cwd=RACINE)
    if r.returncode == 1:
        bloquer('La garde des données trouve des constats dans les fichiers modifiés ou non suivis :\n'
                + r.stdout[-3000:] + 'Corriger avant de conclure (valeurs fictives ou marque fictif-volontaire).')
    sys.exit(0)


if __name__ == '__main__':
    main()
