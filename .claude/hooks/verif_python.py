"""PostToolUse, Edit/Write : un fichier .py doit compiler (et passer ruff E9,F63,F7,F82 si ruff est dans le .venv)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import RACINE, bloquer, lire_entree  # noqa: E402


def main():
    entree = lire_entree()
    chemin = (entree.get('tool_input') or {}).get('file_path') or ''
    if not chemin.endswith('.py') or not os.path.isfile(chemin):
        sys.exit(0)
    try:
        with open(chemin, 'rb') as f:
            compile(f.read(), chemin, 'exec')
    except (SyntaxError, ValueError) as e:
        bloquer(f'Le fichier ne compile pas : {os.path.basename(chemin)} : {type(e).__name__}, ligne '
                f'{getattr(e, "lineno", "?")}.')
    ruff = os.path.join(RACINE, '.venv', 'bin', 'ruff')
    if os.path.exists(ruff):
        r = subprocess.run([ruff, 'check', '--select', 'E9,F63,F7,F82', '--quiet', chemin],
                           capture_output=True, text=True)
        if r.returncode != 0:
            bloquer('ruff (E9, F63, F7, F82) :\n' + r.stdout[-2000:])
    sys.exit(0)


if __name__ == '__main__':
    main()
