"""SessionStart : rappel des règles et de l'état, en moins de 30 lignes. Ne bloque jamais."""
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.realpath(os.environ.get('CLAUDE_PROJECT_DIR') or os.path.dirname(os.path.dirname(ICI)))

REGLES = [
    '1. Données réelles : jamais (ni lire, ni ouvrir, ni lancer) ; essais réels lancés par Lounès.',
    '2. Seulement du fictif : ZZ, 999, @exemple.invalid ; forme réelle voulue = concaténation ou fictif-volontaire.',
    '3. Aucune donnée personnelle dans URL, journaux, erreurs, événements, sortie Tandem, console.',
    '4. Rien vers l\'extérieur ; aucun serveur MCP ; aucune dépendance nouvelle sans accord.',
    '5. Fraudeur = liste noire ou fraude confirmée ; le score ordonne, ne refuse jamais.',
    '6. Ni sexe ni nationalité dans un taux ; aucun chiffre sous 5 clients.',
    '7. Garde-fous intouchables ; mutation seulement dans testeur-mutation.',
]


def git(*args):
    try:
        r = subprocess.run(['git', '-C', RACINE, *args], capture_output=True, text=True, timeout=10)
        return r.stdout.rstrip()
    except (OSError, subprocess.SubprocessError):
        return ''


def derniere_entree_journal(max_lignes=8):
    chemin = os.path.join(RACINE, 'docs', 'journal_etapes.md')
    try:
        with open(chemin, encoding='utf-8') as f:
            lignes = f.read().splitlines()
    except OSError:
        return []
    debuts = [i for i, l in enumerate(lignes) if l.startswith('## ')]
    if not debuts:
        return []
    return [l for l in lignes[debuts[-1]:] if l.strip()][:max_lignes]


def etape_1_faite():
    chemin = os.path.join(RACINE, 'docs', 'plan_construction.md')
    try:
        with open(chemin, encoding='utf-8') as f:
            for l in f:
                m = re.match(r'\|\s*1\s*\|.*\|\s*([^|]+?)\s*\|\s*$', l)
                if m:
                    return m.group(1).lower().startswith('fait')
    except OSError:
        pass
    return False


def main():
    sortie = ['Carte antifraude EQDOM — règles absolues (CLAUDE.md) :', *REGLES]
    sortie.append(f'Branche : {git("branch", "--show-current") or "?"}')
    etat = git('status', '--short').splitlines()
    if etat:
        sortie.append('git status --short :')
        sortie.extend(etat[:15 if len(etat) <= 15 else 14])
        if len(etat) > 15:
            sortie.append(f'… et {len(etat) - 14} autres')
    sortie.extend(derniere_entree_journal(30 - len(sortie) - 2))
    if not etape_1_faite():
        sortie.append('Étape 1 non terminée : reprendre LANCEMENT_construction_temps_reel.md § 4 au point indiqué.')
    print('\n'.join(sortie[:30]))
    sys.exit(0)


if __name__ == '__main__':
    main()
