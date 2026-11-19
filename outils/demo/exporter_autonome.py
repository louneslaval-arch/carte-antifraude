#!/usr/bin/env python3
"""Démonstration autonome : les pages de la plateforme (portail, base client, fiches, dossiers, carte antifraude) avec
les réponses de l'API calculées à l'avance, dans un dossier qu'on ouvre sans serveur ni connexion (index.html).

Les réponses sont demandées à l'API elle-même (même code, mêmes masquages), lancée en mémoire sur la base de
démonstration et la carte globale du même jeu, toutes deux fictives ; une base ou une carte non fictive est refusée,
comme par l'API. Chaque fiche, dossier et réseau a son fichier de données, chargé à la demande par `demo.js`.

Usage : exporter_autonome.py --sortie DOSSIER [--zip FICHIER.zip] [--base BASE] [--carte DOSSIER] [--clients N]
Sortie console : comptages seulement.
"""
import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import zipfile

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(RACINE, 'api'), RACINE]
DEMO = os.path.join(RACINE, 'jeu_essai', 'demo')
FRONT = os.path.join(RACINE, 'front')
PAGES = ('index.html', 'base.html', 'fiche.html', 'dossier.html', 'carte.html', 'reseau.html')
SCRIPT_COMMUN = '<script src="commun.js" defer></script>'


def base_livree(d):
    chemin = os.path.join(d, 'base_demo.sqlite')
    with gzip.open(os.path.join(DEMO, 'base_demo.sqlite.gz'), 'rb') as source, open(chemin, 'wb') as cible:
        shutil.copyfileobj(source, cible)
    return chemin


def carte_livree(d):
    chemin = os.path.join(d, 'carte')
    os.makedirs(chemin)
    with tarfile.open(os.path.join(DEMO, 'carte_globale_demo.tar.gz')) as t:
        t.extractall(chemin, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
    return chemin


class Ecrivain:
    """Fichiers de données : `donnees/<clé>.js` contient « Demo.recevoir(clé, réponse) »."""

    def __init__(self, sortie):
        self.sortie, self.nombre = sortie, 0

    def ecrire(self, cle, valeur):
        chemin = os.path.join(self.sortie, 'donnees', cle + '.js')
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, 'w', encoding='utf-8') as f:
            f.write(f'Demo.recevoir({json.dumps(cle)}, {json.dumps(valeur, ensure_ascii=False, separators=(",", ":"))});\n')
        self.nombre += 1


def indices_cites(objet, cles=('indice',)):
    """Indices de fiche cités dans une réponse (liens vers d'autres fiches)."""
    if isinstance(objet, dict):
        for k, v in objet.items():
            if k in cles and isinstance(v, int):
                yield v
            else:
                yield from indices_cites(v, cles)
    elif isinstance(objet, list):
        for v in objet:
            yield from indices_cites(v, cles)


def exporter(sortie, base, carte, limite=None):
    from fastapi.testclient import TestClient

    from app import comptes
    from app.config import lire_reglages
    from app.main import creer_app
    if os.path.exists(sortie):
        shutil.rmtree(sortie)
    os.makedirs(sortie)
    ecr = Ecrivain(sortie)
    with tempfile.TemporaryDirectory() as t:
        env = {'CARTE_CLE_JWT': 'demo-autonome-' + 'x' * 40, 'CARTE_BASE_URL': f'sqlite:///{t}/journal.db',
               'CARTE_BASE_CLIENT': base, 'CARTE_PUBLICATION_GLOBALE': carte, 'CARTE_COOKIE_NON_SECURISE': '1',
               'CARTE_QUOTA_FICHES': '1000000', 'CARTE_QUOTA_ETIQUETTES': '10000000', 'CARTE_DEBIT': '1000000/minute'}
        app = creer_app(lire_reglages(env))
        with TestClient(app, base_url='https://testserver') as c:
            comptes.creer(app.state.etat.base, 'export', 'ANALYSTE', 'export-demo-autonome')
            assert c.post('/api/auth/connexion', json={'identifiant': 'export', 'mot_de_passe': 'export-demo-autonome'}).status_code == 200

            def lire(chemin):
                r = c.get(chemin)
                return r.json() if r.status_code == 200 else None
            ecr.ecrire('resume', lire('/api/base/resume'))
            items, page = [], 1
            while True:
                r = c.post('/api/base/clients', json={'page': page, 'taille': 200}).json()
                items += r['items']
                if page * 200 >= r['total']:
                    break
                page += 1
            items = items[:limite] if limite else items
            fiches, dossiers, cites = set(), set(), set()
            for x in items:
                f = lire(f'/api/base/clients/{x["indice"]}')
                ecr.ecrire(f'fiche/{x["indice"]}', f)
                fiches.add(x['indice'])
                dossiers.update(d['indice'] for d in f['dossiers'])
                cites.update(indices_cites(f))
                reseau = lire(f'/api/base/reseau/{x["indice"]}')
                ecr.ecrire(f'reseau/{x["indice"]}', reseau)
                cites.update(n['id'] for n in reseau['noeuds'] if isinstance(n['id'], int))
                position = lire(f'/api/base/carte/{x["indice"]}')
                x['carte'] = position['indice'] if position else None
            ecr.ecrire('clients', {'items': items})
            for i in sorted(dossiers):
                d = lire(f'/api/base/dossiers/{i}')
                ecr.ecrire(f'dossier/{i}', d)
                cites.update(p['indice'] for p in d['parties'] if p.get('indice'))
            for i in sorted(cites - fiches - dossiers):         # fiches citées par les clients (un pas), sans les dossiers
                f = lire(f'/api/base/clients/{i}')
                if f is not None:
                    ecr.ecrire(f'fiche/{i}', f)
                    fiches.add(i)
            geo = lire('/api/carte/globale')
            ecr.ecrire('carte/geometrie', geo)
            n = len(geo['noeuds'])
            noms = {}
            for k in range(0, n, 400):
                noms.update(c.post('/api/carte/globale/noms', json={'indices': list(range(k, min(n, k + 400)))}).json())
            ecr.ecrire('carte/noms', noms)
            ecr.ecrire('carte/fiches', {str(i): lire(f'/api/carte/globale/noeud/{i}') for i in range(n)})
        con = sqlite3.connect(f'file:{os.path.join(carte, "identites.sqlite")}?mode=ro', uri=True)
        ecr.ecrire('carte/recherche', dict(
            lignes=con.execute('SELECT indice, champ, valeur FROM recherche ORDER BY indice').fetchall(),
            types={str(i): t for i, t in con.execute('SELECT indice, type FROM noeud')},
            noms={str(i): nom for i, nom in con.execute('SELECT indice, nom FROM identite')}))
        con.close()
    pages(sortie)
    stats = statistiques(sortie, base)
    return dict(clients=len(items), fiches=len(fiches), dossiers=len(dossiers), noeuds_carte=n, fichiers=ecr.nombre, cases_statistiques=stats)


STATS_ACTIF = ("{ id: 'stats', nom: 'Statistiques client', etat: 'a_venir',",
               "{ id: 'stats', nom: 'Statistiques client', etat: 'actif', lien: 'statistiques.html',")


def statistiques(sortie, base):
    """Page des statistiques (couche 7), calculée sur le jeu d'essai des statistiques (600 dossiers fictifs qui
    couvrent tous les verdicts et tous les cas ; la base de démonstration n'a presque que des verdicts conformes), avec
    un lien vers le portail et la mention de démonstration. Rend le nombre de cases."""
    sys.path[:0] = [os.path.join(RACINE, 'jeu_essai', 'v2'), os.path.join(RACINE, 'jeu_essai', 'v2', 'statistiques')]
    import generer_v2_fictif
    from pipeline.analytique import agregats, page_statistiques
    with tempfile.TemporaryDirectory() as t:
        cx = generer_v2_fictif.construire_base(os.path.join(t, 'stats.sqlite'), generer_v2_fictif.dossiers())
        try:
            comptes = agregats.construire(cx)
            chemin = os.path.join(sortie, 'statistiques.html')
            page_statistiques.generer(cx, chemin)
        finally:
            cx.close()
    with open(chemin, encoding='utf-8') as f:
        html = f.read()
    for avant, apres in (("document.getElementById('pastille').textContent = 'données agrégées';",
                          "document.getElementById('pastille').textContent = 'démonstration · données fictives';"),
                         ('<div class="app">', '<div class="app">\n  <p data-style="margin:0 0 14px;font-size:13px">'
                          '<a href="index.html" data-style="color:inherit">← Portail</a></p>')):
        if html.count(avant) != 1:
            raise SystemExit('statistiques.html : repère introuvable')
        html = html.replace(avant, apres)
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(html)
    return comptes['cases']


def pages(sortie):
    """Pages, styles et scripts du front ; `demo.js` chargé juste après commun.js dans chaque page."""
    for nom in os.listdir(FRONT):
        if nom.endswith(('.css', '.js')):
            shutil.copy(os.path.join(FRONT, nom), os.path.join(sortie, nom))
    for nom in PAGES:
        with open(os.path.join(FRONT, nom), encoding='utf-8') as f:
            html = f.read()
        if html.count(SCRIPT_COMMUN) != 1:
            raise SystemExit(f'{nom} : commun.js introuvable, demo.js ne trouve pas sa place')
        html = html.replace(SCRIPT_COMMUN, SCRIPT_COMMUN + '\n<script src="demo.js" defer></script>')
        with open(os.path.join(sortie, nom), 'w', encoding='utf-8') as f:
            f.write(html)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demo_autonome.js'), os.path.join(sortie, 'demo.js'))
    # le module de statistiques existe dans la démonstration : sa bulle du portail devient active et mène à sa page
    chemin = os.path.join(sortie, 'contenu.js')
    with open(chemin, encoding='utf-8') as f:
        contenu = f.read()
    if contenu.count(STATS_ACTIF[0]) != 1:
        raise SystemExit('contenu.js : module de statistiques introuvable')
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(contenu.replace(*STATS_ACTIF))
    with open(os.path.join(sortie, 'LISEZ-MOI.txt'), 'w', encoding='utf-8') as f:
        f.write('EQDOM · Plateforme clients : démonstration autonome\n\n'
                'Ouvrir index.html dans un navigateur (Chrome, Edge, Safari ou Firefox). Aucun serveur ni connexion à '
                'internet n\'est nécessaire.\n\nToutes les données sont fictives : noms inventés, CIN en « ZZ », '
                'numéros en « 999 ». Aucune personne ni aucune société réelle.\n')


def zipper(dossier, archive):
    racine = os.path.basename(os.path.normpath(dossier))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for d, _sous, noms in os.walk(dossier):
            for nom in sorted(noms):
                chemin = os.path.join(d, nom)
                z.write(chemin, os.path.join(racine, os.path.relpath(chemin, dossier)))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--sortie', required=True)
    p.add_argument('--zip')
    p.add_argument('--base', help='base de démonstration (par défaut : la base livrée)')
    p.add_argument('--carte', help='carte globale publiée (par défaut : celle livrée)')
    p.add_argument('--clients', type=int, help='seulement les N premiers clients (essais)')
    a = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as t:
        comptes = exporter(a.sortie, a.base or base_livree(t), a.carte or carte_livree(t), a.clients)
    print(' ; '.join(f'{k} : {v}' for k, v in comptes.items()))
    if a.zip:
        zipper(a.sortie, a.zip)
        print(f'archive : {os.path.getsize(a.zip) // 1024} Ko')
    return 0


if __name__ == '__main__':
    sys.exit(main())
