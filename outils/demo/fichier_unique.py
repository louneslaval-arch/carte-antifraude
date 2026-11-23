#!/usr/bin/env python3
"""Démonstration en un seul fichier HTML : portail, base client, vue 360° et dossiers, sur une base fictive légère
(une centaine de clients par défaut, choisis parmi 300 dossiers générés : le générateur en exige 300 pour
porter tous ses scénarios), sans serveur ni fichier voisin. On l'ouvre d'un double-clic.

Les réponses sont demandées à l'API elle-même (même code, mêmes masquages), lancée en mémoire sur une base construite
par `construire_demo.py` ; elles sont jointes à la page en JSON. Un petit routeur affiche chaque page selon l'adresse
(`#base`, `#fiche?i=…`) ; la carte, le réseau et les statistiques ne sont pas dans ce fichier : leurs liens le disent.

Usage : fichier_unique.py --sortie FICHIER.html [--clients 100] [--dossiers 300] [--societes 400]
Sortie console : comptages seulement.
"""
import argparse
import json
import os
import re
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path[:0] = [ICI, os.path.join(RACINE, 'api'), RACINE]
FRONT = os.path.join(RACINE, 'front')
PAGES = {'index': ('portail.js',), 'base': ('base.js',), 'fiche': ('fiche.js',), 'dossier': ('dossier.js',)}
STYLES = ('commun.css', 'portail.css')
NAVIGATION = re.compile(r'location\.href\s*=(?!=)\s*')
QUOTAS = {'salarie': 0.6, 'entrepreneur': 0.2, 'pm': 0.2}   # part des clients retenus par profil


def _lire(nom):
    with open(os.path.join(FRONT, nom), encoding='utf-8') as f:
        return f.read()


def _fin_expression(js, i):
    """Fin de l'expression qui commence en `i` : avant le premier `;`, `,` ou fermant non apparié, hors chaînes."""
    profondeur, chaine = 0, None
    while i < len(js):
        c = js[i]
        if chaine:
            if c == '\\':
                i += 1
            elif c == chaine:
                chaine = None
        elif c in '\'"`':
            chaine = c
        elif c in '([{':
            profondeur += 1
        elif c in ')]}':
            if profondeur == 0:
                return i
            profondeur -= 1
        elif c in ';,\n' and profondeur == 0:
            return i
        i += 1
    return i


def _router(js):
    """Toute navigation passe par le routeur du fichier : `location.href = X` devient `Commun.aller(X)`, que
    l'affectation soit une instruction ou au milieu d'une expression."""
    morceaux, debut = [], 0
    for m in NAVIGATION.finditer(js):
        if m.start() < debut:
            continue
        fin = _fin_expression(js, m.end())
        morceaux += [js[debut:m.start()], f'Commun.aller({js[m.end():fin].strip()})']
        debut = fin
    return ''.join(morceaux) + js[debut:]


PROFONDEUR_CITEES = 2


def collecter(base, n_clients=100):
    """Réponses de l'API sur la base : résumé, liste des clients retenus, fiche de chaque client, fiches citées (un
    pas) et dossiers. {clé: réponse}, aux clés de `demo_autonome.js`. Clients retenus : les plus graves d'abord (ordre
    de la liste), dans la limite de la part de chaque profil (`QUOTAS`), complétés dans l'ordre s'il en manque."""
    from fastapi.testclient import TestClient

    from app import comptes
    from app.config import lire_reglages
    from app.main import creer_app
    from exporter_autonome import indices_cites
    donnees = {}
    with tempfile.TemporaryDirectory() as t:
        env = {'CARTE_CLE_JWT': 'demo-fichier-unique-' + 'x' * 40, 'CARTE_BASE_URL': f'sqlite:///{t}/journal.db',
               'CARTE_BASE_CLIENT': base, 'CARTE_COOKIE_NON_SECURISE': '1', 'CARTE_QUOTA_FICHES': '1000000',
               'CARTE_QUOTA_ETIQUETTES': '10000000', 'CARTE_DEBIT': '1000000/minute'}
        app = creer_app(lire_reglages(env))
        with TestClient(app, base_url='https://testserver') as c:
            comptes.creer(app.state.etat.base, 'export', 'ANALYSTE', 'export-fichier-unique')
            assert c.post('/api/auth/connexion', json={'identifiant': 'export',
                                                       'mot_de_passe': 'export-fichier-unique'}).status_code == 200

            def lire(chemin):
                r = c.get(chemin)
                return r.json() if r.status_code == 200 else None
            donnees['resume'] = lire('/api/base/resume')
            items, page = [], 1
            while True:
                r = c.post('/api/base/clients', json={'page': page, 'taille': 200}).json()
                items += r['items']
                if page * 200 >= r['total']:
                    break
                page += 1
            quotas = {p: round(n_clients * part) for p, part in QUOTAS.items()}
            lues, retenus, reste = {}, [], []
            for x in items:
                f = lues[x['indice']] = lire(f'/api/base/clients/{x["indice"]}')
                if not any(d['demandeur'] for d in f['dossiers']):
                    continue
                profil = f['vue360']['profil']
                if quotas.get(profil, 0) > 0:
                    quotas[profil] -= 1
                    retenus.append(x)
                else:
                    reste.append(x)
                if len(retenus) >= n_clients:
                    break
            retenus += reste[:n_clients - len(retenus)]
            items = retenus
            donnees['clients'] = {'items': items}
            fiches, dossiers, cites = set(), set(), set()
            for x in items:
                f = lues[x['indice']]
                donnees[f'fiche/{x["indice"]}'] = f
                fiches.add(x['indice'])
                dossiers.update(d['indice'] for d in f['dossiers'])
                cites.update(indices_cites(f))
            for i in sorted(dossiers):
                d = lire(f'/api/base/dossiers/{i}')
                donnees[f'dossier/{i}'] = d
                cites.update(p['indice'] for p in d['parties'] if p.get('indice'))
            for _ in range(PROFONDEUR_CITEES):   # fiches citées, puis celles qu'elles citent : la vue en étoile se déplie
                suivantes = set()
                for i in sorted(cites - fiches - dossiers):
                    f = lire(f'/api/base/clients/{i}')
                    if f is not None:
                        donnees[f'fiche/{i}'] = f
                        fiches.add(i)
                        suivantes.update(indices_cites(f))
                cites = suivantes
    resumer(donnees, items, dossiers)
    return donnees, dict(clients=len(items), fiches=len(fiches), dossiers=len(dossiers))


def resumer(donnees, items, dossiers):
    """Chiffres du portail et de la base recalculés sur les clients retenus (et non sur toute la base générée), avec
    les mêmes règles que l'API : jamais un chiffre de 1 à 4, masquage secondaire des répartitions. Les inscrits restent
    ceux de la liste noire."""
    from app.base_client import compte, masquer_groupe
    produits = {}
    for i in dossiers:
        p = ((donnees.get(f'dossier/{i}') or {}).get('entete') or {}).get('produit')
        if p:
            produits[p] = produits.get(p, 0) + 1
    if not produits:                                  # repli : produits portés par la liste des clients
        for x in items:
            for p in x.get('produits') or []:
                produits[p] = produits.get(p, 0) + 1
    r = donnees['resume']
    r.update(clients=compte(len(items)), dossiers=compte(len(dossiers)), produits=masquer_groupe(
        [dict(valeur=v, nombre=compte(n)) for v, n in sorted(produits.items(), key=lambda x: -x[1])]))


def _corps(nom):
    """(classe du <body>, titre, contenu du <body>) d'une page du front."""
    html = _lire(f'{nom}.html')
    corps = re.search(r'<body([^>]*)>(.*)</body>', html, re.S)
    titre = re.search(r'<title>(.*?)</title>', html, re.S)
    classe = re.search(r'class="([^"]*)"', corps.group(1))
    return (classe.group(1) if classe else ''), titre.group(1).strip(), corps.group(2)


def assembler(donnees):
    """Le fichier : styles, gabarits des quatre pages, données jointes, scripts (commun, routeur, contenu, pages)."""
    styles = '\n'.join(_lire(n) for n in STYLES)
    gabarits, pages_js = [], []
    for nom, scripts in PAGES.items():
        classe, titre, corps = _corps(nom)
        gabarits.append(f'<template id="page-{nom}" data-classe="{classe}" data-titre="{titre}">{corps}</template>')
        code = '\n'.join(_router(_lire(s)) for s in scripts)
        pages_js.append(f'PAGES_DEMO[{json.dumps(nom)}] = function () {{\n{code}\n}};')
    with open(os.path.join(ICI, 'fichier_unique.js'), encoding='utf-8') as f:
        routeur = f.read()
    json_donnees = json.dumps(donnees, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    scripts = [_router(_lire('commun.js')), routeur, _lire('contenu.js'), 'const PAGES_DEMO = {};', *pages_js,
               'DemoUnique.demarrer();']
    return ('<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>EQDOM · Plateforme clients · démonstration</title>\n'
            f'<style>\n{styles}\n</style>\n</head>\n<body>\n'
            + '\n'.join(gabarits)
            + f'\n<script type="application/json" id="donnees">{json_donnees}</script>\n'
            + '\n'.join(f'<script>\n{s}\n</script>' for s in scripts)
            + '\n</body>\n</html>\n')


def construire(sortie, n_clients=100, n_dossiers=300, n_societes=400, graine=20261119):
    import construire_demo
    with tempfile.TemporaryDirectory() as t:
        base = os.path.join(t, 'base_legere.sqlite')
        construire_demo.construire(base, n_dossiers=n_dossiers, n_societes=n_societes, graine=graine)
        donnees, comptes = collecter(base, n_clients)
    html = assembler(donnees)
    with open(sortie, 'w', encoding='utf-8') as f:
        f.write(html)
    comptes['taille_ko'] = len(html.encode('utf-8')) // 1024
    return comptes


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--sortie', required=True)
    p.add_argument('--clients', type=int, default=100)
    p.add_argument('--dossiers', type=int, default=300)
    p.add_argument('--societes', type=int, default=400)
    a = p.parse_args(argv)
    comptes = construire(a.sortie, a.clients, a.dossiers, a.societes)
    print(' ; '.join(f'{k} : {v}' for k, v in comptes.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
