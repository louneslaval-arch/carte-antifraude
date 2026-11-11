"""Stop : refuse de conclure si garde_donnees.py --arbre trouve un constat. Ne bloque pas une seconde fois
(stop_hook_active) : le crochet git reste la barrière."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _commun import RACINE, bloquer, lire_entree  # noqa: E402
except Exception as e:  # garde introuvable : bloquer plutôt que laisser conclure en silence
    print(f'La garde des données n\'a pas pu se charger ({type(e).__name__}) : vérifier avant de conclure.',
          file=sys.stderr)
    sys.exit(2)


def main():
    entree = lire_entree()
    if entree.get('stop_hook_active'):
        sys.exit(0)
    python = os.path.join(RACINE, '.venv', 'bin', 'python')
    garde = os.path.join(RACINE, 'outils', 'garde', 'garde_donnees.py')
    try:
        r = subprocess.run([python if os.path.exists(python) else sys.executable, garde, '--arbre'],
                           capture_output=True, text=True, cwd=RACINE)
    except OSError:
        bloquer('La garde des données n\'a pas pu tourner (dépôt introuvable) : vérifier avant de conclure.')
    if r.returncode == 1:
        bloquer('La garde des données trouve des constats dans les fichiers modifiés ou non suivis :\n'
                + r.stdout[-3000:] + 'Corriger avant de conclure (valeurs fictives ou marque fictif-volontaire).')
    if r.returncode != 0:
        # erreur de la garde (git, chemin) : ne jamais conclure en silence ; seul le type d'erreur est montré
        bloquer(f'La garde des données a échoué (code {r.returncode}) : vérifier avant de conclure.')
    sys.exit(0)


if __name__ == '__main__':
    main()
