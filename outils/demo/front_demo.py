#!/usr/bin/env python3
"""Pages de la démonstration locale (`api/lancer_demo.sh`) : copie de `front/` dans un dossier temporaire, plus la page
des statistiques (couche 7, jeu d'essai fictif des statistiques) et la bulle « Statistiques client » du portail rendue
active. `front/` n'est pas modifié ; la plateforme n'a pas de route de statistiques (décision du 17/11) : la page est un
fichier statique, de chiffres agrégés seulement.

Usage : front_demo.py DOSSIER        Sortie console : comptages seulement.
"""
import os
import shutil
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path.insert(0, ICI)


def separer(page):
    """La plateforme refuse styles et scripts écrits dans la page (`default-src 'self'`) : la feuille de style et le
    script de la page autonome passent dans des fichiers voisins ; les données JSON, non exécutées, restent."""
    with open(page, encoding='utf-8') as f:
        html = f.read()
    base = os.path.splitext(page)[0]
    debut, fin = html.index('<style>'), html.index('</style>') + len('</style>')
    with open(base + '.css', 'w', encoding='utf-8') as f:
        f.write(html[debut + len('<style>'):fin - len('</style>')])
    html = html[:debut] + '<link rel="stylesheet" href="statistiques.css">' + html[fin:]
    debut = html.index("<script>\n'use strict';")
    fin = html.index('</script>', debut) + len('</script>')
    with open(base + '.js', 'w', encoding='utf-8') as f:
        f.write(html[debut + len('<script>'):fin - len('</script>')])
    html = html[:debut] + '<script src="statistiques.js" defer></script>' + html[fin:]
    with open(page, 'w', encoding='utf-8') as f:
        f.write(html)


def construire(dossier):
    import exporter_autonome as ex
    if os.path.exists(dossier):
        shutil.rmtree(dossier)
    shutil.copytree(os.path.join(RACINE, 'front'), dossier)
    cases = ex.statistiques(dossier, None)
    if cases is not None:                      # sans la structure de Kamal : pas de page, bulle « à venir »
        separer(os.path.join(dossier, 'statistiques.html'))
        ex.activer_statistiques(dossier)
    return cases


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.splitlines()[-2].strip(), file=sys.stderr)
        return 2
    cases = construire(argv[0])
    print(f'pages de démonstration : statistiques, {cases} cases' if cases is not None
          else 'pages de démonstration : sans statistiques (structure de Kamal absente)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
