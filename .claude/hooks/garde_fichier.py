"""PreToolUse, Read/Edit/Write/NotebookEdit/Grep/Glob : refuse un chemin de données réelles, le dossier api/ du lot
de Kamal, et l'écriture d'un texte qui présente un motif de la garde. Ne recopie jamais la valeur trouvée."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import bloquer, lire_entree, motifs, relatif_au_depot, repere_present  # noqa: E402

CLES_CHEMIN = ('file_path', 'path', 'notebook_path', 'pattern')
CLES_TEXTE = ('content', 'new_string', 'new_source')


def main():
    entree = lire_entree()
    outil = entree.get('tool_name') or ''
    params = entree.get('tool_input') or {}

    chemins = [params[c] for c in CLES_CHEMIN if isinstance(params.get(c), str)]
    if outil == 'Grep':  # pour Grep, « pattern » est l'expression cherchée, pas un chemin
        chemins = [params[c] for c in ('path', 'glob') if isinstance(params.get(c), str)]
    for chemin in chemins:
        if repere_present(chemin):
            bloquer('Refusé : chemin de données réelles (.claude/hooks/chemins_interdits.txt).')

    cible = params.get('file_path') or params.get('notebook_path') or params.get('path') or ''
    rel = relatif_au_depot(cible) if cible else None
    if rel and motifs.dans_api_de_kamal(rel):
        bloquer('Refusé : le dossier api/ du lot de Kamal contient de vrais dossiers.')

    if outil in ('Write', 'Edit', 'NotebookEdit'):
        texte = '\n'.join(params[c] for c in CLES_TEXTE if isinstance(params.get(c), str))
        constats = motifs.analyser(texte, rel or os.path.basename(cible))
        if constats:
            liste = ', '.join(f'ligne {l} : {m}' for l, m in constats[:10])
            bloquer(f'Refusé : le texte écrit présente une forme réelle ({liste}). Utiliser des valeurs fictives '
                    '(ZZ, 999, @exemple.invalid), une construction par concaténation, ou la marque '
                    'fictif-volontaire pour un refus voulu.')
    sys.exit(0)


if __name__ == '__main__':
    main()
