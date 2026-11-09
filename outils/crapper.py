#!/usr/bin/env python3
"""Score CRAP de chaque fonction : complexité² × (1 − couverture)³ + complexité.

Usage : outils/crapper.py fichier.py [...]
Lit .coverage (produit par « coverage run -m pytest » puis « coverage combine »).
Complexité cyclomatique : radon. Couverture : instructions exécutables de la fonction, exécutées ou non.
Code de sortie 1 si une fonction atteint le seuil (10).
"""
import os
import sys

import coverage
from radon.complexity import cc_visit

SEUIL = 10


def scores(chemin, cov):
    _f, instructions, _exclues, manquantes, _texte = cov.analysis2(chemin)
    manquantes = set(manquantes)
    with open(chemin, encoding='utf-8') as f:
        source = f.read()
    for fn in cc_visit(source):
        if hasattr(fn, 'methods'):
            continue                                      # une classe : radon liste déjà ses méthodes à part
        utiles = {l for l in instructions if fn.lineno < l <= fn.endline}
        part = 1 - len(utiles & manquantes) / len(utiles) if utiles else 1.0
        c = fn.complexity
        yield round(c * c * (1 - part) ** 3 + c, 1), c, round(part * 100), f'{os.path.relpath(chemin)}:{fn.lineno} {fn.name}'


def main(fichiers):
    cov = coverage.Coverage()
    cov.load()
    tout = sorted((s for f in fichiers for s in scores(os.path.abspath(f), cov)), reverse=True)
    print(f"{'CRAP':>6} {'compl':>5} {'couv%':>5}  fonction")
    for s, c, p, nom in tout:
        print(f'{s:6} {c:5} {p:5}  {nom}' + ('   ← au-dessus du seuil' if s >= SEUIL else ''))
    return 1 if any(s >= SEUIL for s, *_ in tout) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
