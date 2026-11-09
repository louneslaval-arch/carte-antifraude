#!/usr/bin/env python3
"""Paires de fonctions qui se ressemblent, classées par rang de ressemblance (0 à 1).

Usage : outils/dryer.py fichier.py [...] [--seuil 0.8]
Chaque fonction est réduite à sa suite de jetons, noms et littéraux remplacés par leur catégorie : deux fonctions
qui ne diffèrent que par les noms ou les constantes obtiennent un rang proche de 1. Les fonctions de moins de
4 instructions sont ignorées. Code de sortie 1 si une paire atteint le seuil.
"""
import argparse
import ast
import difflib
import io
import itertools
import keyword
import sys
import textwrap
import tokenize


def jetons(source):
    sortie = []
    for t in tokenize.generate_tokens(io.StringIO(source).readline):
        if t.type == tokenize.NAME:
            sortie.append(t.string if keyword.iskeyword(t.string) else 'NOM')
        elif t.type in (tokenize.STRING, tokenize.NUMBER):
            sortie.append('LIT')
        elif t.type == tokenize.OP:
            sortie.append(t.string)
    return sortie


def fonctions(chemin):
    with open(chemin, encoding='utf-8') as f:
        source = f.read()
    lignes = source.splitlines()
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            corps = n.body[1:] if ast.get_docstring(n) else n.body
            if sum(1 for _ in ast.walk(ast.Module(body=corps, type_ignores=[])) if isinstance(_, ast.stmt)) < 4:
                continue
            texte = '\n'.join(lignes[corps[0].lineno - 1:n.end_lineno])
            yield f'{chemin}:{n.lineno} {n.name}', jetons(textwrap.dedent(texte))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('fichiers', nargs='+')
    ap.add_argument('--seuil', type=float, default=0.8)
    a = ap.parse_args()
    toutes = [f for chemin in a.fichiers for f in fonctions(chemin)]
    paires = []
    for (na, ja), (nb, jb) in itertools.combinations(toutes, 2):
        rang = difflib.SequenceMatcher(None, ja, jb, autojunk=False).ratio()
        paires.append((round(rang, 2), na, nb))
    paires.sort(reverse=True)
    print(f'{len(toutes)} fonctions comparées ; les 10 paires les plus proches :')
    for rang, na, nb in paires[:10]:
        print(f'  {rang:.2f}  {na}  ↔  {nb}' + ('   ← au-dessus du seuil' if rang >= a.seuil else ''))
    return 1 if paires and paires[0][0] >= a.seuil else 0


if __name__ == '__main__':
    sys.exit(main())
