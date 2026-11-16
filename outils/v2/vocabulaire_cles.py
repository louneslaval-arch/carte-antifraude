#!/usr/bin/env python3
"""Vocabulaire des clés de `fields` par type de pièce, tiré de l'inventaire de Kamal (`champs_par_type_prod.csv`).

L'inventaire liste, par type de pièce et par source, les clés que la v2 produit vraiment. On n'en garde que les noms
de clés (aucune valeur, aucun comptage) dans `pipeline/normalisation/vocabulaire_v2.py`, lu par
`pipeline/normalisation/cles.py` pour remplir `ref_cle_canonique`. Généré, jamais écrit à la main ; un test échoue
si l'inventaire change sans régénération (dérive).

Usage : vocabulaire_cles.py --ecrire | --verifier [--structure DOSSIER] [--sortie FICHIER]
"""
import argparse
import csv
import hashlib
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCTURE_DEFAUT = os.path.join(RACINE, 'import', 'kamal_structure')
SORTIE_DEFAUT = os.path.join(RACINE, 'pipeline', 'normalisation', 'vocabulaire_v2.py')
INVENTAIRE = os.path.join('reference', 'champs_par_type_prod.csv')


def generer(structure):
    chemin = os.path.join(structure, INVENTAIRE)
    with open(chemin, 'rb') as f:
        brut = f.read()
    types = {}
    for ligne in csv.DictReader(brut.decode('utf-8').splitlines()):
        types.setdefault(ligne['type'], set()).add(ligne['key'])
    lignes = ['"""Clés de `fields` par type de pièce, d\'après l\'inventaire de Kamal. Généré par',
              '`outils/v2/vocabulaire_cles.py --ecrire` ; ne pas modifier à la main."""',
              f"SOURCE = '{INVENTAIRE.replace(os.sep, '/')}'", f"SHA256 = '{hashlib.sha256(brut).hexdigest()}'",
              'VOCABULAIRE = {']
    for type_piece, cles in sorted(types.items()):
        lignes.append(f'    {type_piece!r}: (')
        lignes += [f'        {c!r},' for c in sorted(cles)]
        lignes.append('    ),')
    return '\n'.join(lignes + ['}']) + '\n'


def a_jour(structure, sortie):
    return os.path.exists(sortie) and open(sortie, encoding='utf-8').read() == generer(structure)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ecrire', action='store_true')
    mode.add_argument('--verifier', action='store_true')
    p.add_argument('--structure', default=STRUCTURE_DEFAUT)
    p.add_argument('--sortie', default=SORTIE_DEFAUT)
    a = p.parse_args(argv)
    if a.ecrire:
        with open(a.sortie, 'w', encoding='utf-8') as f:
            f.write(generer(a.structure))
        print('vocabulaire des clés écrit')
        return 0
    ok = a_jour(a.structure, a.sortie)
    print('vocabulaire des clés à jour' if ok else 'vocabulaire des clés périmé', file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
