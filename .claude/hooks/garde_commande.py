"""PreToolUse, Bash : refuse les commandes qui visent des données réelles ou contournent les garde-fous."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import RACINE, bloquer, lire_entree, repere_present  # noqa: E402

# « git », puis d'éventuelles options globales (-C dossier, -c clé=valeur, --git-dir=…), puis la sous-commande
GIT = r'\bgit\b(?:\s+(?:-[Cc]\s+\S+|--\S+))*\s+'
GIT_ADD_FORCE = re.compile(GIT + r'add\b[^;&|\n]*\s(?:--force\b|-[A-Za-z]*f[A-Za-z]*\b)')
# -n est la forme courte de --no-verify pour git commit, seule ou groupée (-anm)
GIT_COMMIT_SANS_CROCHET = re.compile(GIT + r'commit\b[^;&|\n]*\s-[A-Za-z]*n[A-Za-z]*\b')
# git ne distingue pas la casse des clés de configuration
HOOKS_PATH = re.compile(r'core\.hookspath', re.IGNORECASE)
MUTMUT = re.compile(r'\bmutmut\s+run\b')


def dans_le_depot_principal(cwd):
    cwd = os.path.realpath(cwd)
    if os.path.commonpath([cwd, RACINE]) != RACINE:
        return False
    copies = os.path.join(RACINE, '.claude', 'worktrees')
    return os.path.commonpath([cwd, copies]) != copies


def main():
    entree = lire_entree()
    commande = (entree.get('tool_input') or {}).get('command') or ''
    cwd = entree.get('cwd') or os.getcwd()

    repere = repere_present(commande)
    if repere:
        bloquer('Refusé : la commande vise un emplacement ou un réglage de données réelles '
                '(.claude/hooks/chemins_interdits.txt). Les essais réels, c\'est Lounès qui les lance.')
    if '--no-verify' in commande or GIT_COMMIT_SANS_CROCHET.search(commande):
        bloquer('Refusé : --no-verify (ou -n) contourne le crochet git (CLAUDE.md, règle 7).')
    if HOOKS_PATH.search(commande):
        bloquer('Refusé : core.hooksPath ne se change pas sans demande explicite de Lounès (règle 7).')
    if GIT_ADD_FORCE.search(commande):
        bloquer('Refusé : ajout forcé d\'un fichier ignoré (règle 7).')
    if MUTMUT.search(commande) and dans_le_depot_principal(cwd):
        bloquer('Refusé : mutmut modifie les fichiers en place ; il ne tourne que dans le sous-agent '
                'testeur-mutation, dans une copie de travail jetable.')
    sys.exit(0)


if __name__ == '__main__':
    main()
