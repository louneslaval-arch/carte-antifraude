#!/usr/bin/env python3
"""Export du graphe AF global depuis PostgreSQL, sans pagination.

Sorties : geometrie.json (sans identités), identites.json (SENSIBLE),
statistiques.json, manifeste.json. Les identifiants sont aléatoires à chaque
export. Ceci n'est pas la publication historique du registre RC.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import tempfile

import psycopg
from psycopg.rows import dict_row
try:
    from pipeline.geo_maroc import VILLES, contour, monde
except ModuleNotFoundError:
    from geo_maroc import VILLES, contour, monde


def ville_connue(valeur):
    """Ne publier que les codes de villes présents dans le référentiel géographique."""
    if not isinstance(valeur, str):
        return None
    code = valeur.strip().upper()
    return code if code in VILLES else None


def construire(identites, relations, liens_bl):
    """Transforme toutes les lignes AF en couches géométrie et identités."""
    ref = {}
    noeuds, noms, aretes, details = [], [], [], []
    for i in identites:
        k = ('af', str(i['identite_id']))
        if k in ref:
            raise ValueError('identité AF dupliquée')
        idx = len(noeuds)
        ref[k] = idx
        t = 'societe' if i['type_identite'] in ('PM', 'societe') else 'personne'
        noeuds.append({'id': secrets.token_urlsafe(15), 't': t, 'bl': 0,
                       'v': ville_connue(i.get('ville_code'))})
        noms.append({'id': noeuds[idx]['id'], 'nom': i['nom'], 'type': t, 'liste_noire': False})

    dedup = set()
    for r in relations:
        a = ref.get(('af', str(r['pp_identite_id'])))
        b = ref.get(('af', str(r['pm_identite_id'])))
        if a is None or b is None or a == b:
            continue
        details.append({'de': noeuds[a]['id'], 'vers': noeuds[b]['id'],
                        'type': 'relation', 'role': r['role']})
        k = (a, b, str(r['role'] or 'relation'))
        if k not in dedup:
            dedup.add(k)
            # Le rôle brut reste hors couche géométrique : sa valeur peut être libre.
            aretes.append({'a': a, 'b': b, 'type': 'relation'})

    non_rattaches = 0
    for l in liens_bl:
        a = ref.get(('af', str(l['identite_id'])))
        if a is None and l.get('dossier_ref'):
            dossier_ref = str(l['dossier_ref'])
            dossier_key = ('dossier', dossier_ref)
            if dossier_key not in ref:
                ref[dossier_key] = len(noeuds)
                noeuds.append({'id': secrets.token_urlsafe(15), 't': 'dossier', 'bl': 0, 'v': None})
                noms.append({'id': noeuds[-1]['id'], 'nom': dossier_ref,
                             'type': 'dossier', 'liste_noire': False})
            a = ref[dossier_key]
        key = ('bl', str(l['entite_id']))
        if key not in ref:
            ref[key] = len(noeuds)
            t = 'societe' if l['type_entite'] in ('PM', 'societe') else 'personne'
            noeuds.append({'id': secrets.token_urlsafe(15), 't': t, 'bl': 1,
                           'v': ville_connue(l.get('ville_code'))})
            noms.append({'id': noeuds[-1]['id'], 'nom': l['nom_affiche'], 'type': t, 'liste_noire': True})
        b = ref[key]
        if a is None:
            non_rattaches += 1
            details.append({'de': None, 'vers': noeuds[b]['id'], 'type': 'liste_noire',
                            'role': l['regle'], 'niveau': l['niveau'], 'sans_rattachement': True})
            continue
        details.append({'de': noeuds[a]['id'], 'vers': noeuds[b]['id'],
                        'type': 'liste_noire', 'role': l['regle'], 'niveau': l['niveau']})
        k = (a, b, 'liste_noire', str(l['regle'] or ''), str(l['niveau'] or ''))
        if k not in dedup:
            dedup.add(k)
            aretes.append({'a': a, 'b': b, 'type': 'liste_noire'})

    # Layout déterministe en grille par composantes, sans noms ni IDs de source.
    parents = list(range(len(noeuds)))
    def find(x):
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x
    for a in aretes:
        x, y = find(a['a']), find(a['b'])
        if x != y:
            parents[y] = x
    composants = defaultdict(list)
    for i in range(len(noeuds)):
        composants[find(i)].append(i)
    groups = sorted(composants.values(), key=lambda g: (-len(g), min(g)))
    degrees = Counter()
    for a in aretes:
        degrees[a['a']] += 1
        degrees[a['b']] += 1
    group_index = {}
    xstart, ystart, row_height = 0.0, 0.0, 0.0
    for numero, group in enumerate(groups):
        width = max(110.0, math.ceil(math.sqrt(len(group))) * 34.0)
        height = max(110.0, math.ceil(len(group) / max(1, math.ceil(math.sqrt(len(group))))) * 34.0)
        if xstart + width > 2000 and xstart > 0:
            xstart = 0.0; ystart += row_height + 70; row_height = 0.0
        cols = max(1, math.ceil(math.sqrt(len(group))))
        for pos, node_index in enumerate(group):
            n = noeuds[node_index]
            n.update({'x': round(xstart + (pos % cols) * 34, 2),
                      'y': round(ystart + (pos // cols) * 34, 2),
                      'c': numero, 'deg': degrees[node_index]})
            group_index[node_index] = numero
        xstart += width + 70; row_height = max(row_height, height)

    villes = {nom: [round(x, 2), round(y, 2)] for nom, (lat, lon) in VILLES.items()
              for x, y in [monde(lat, lon)]}
    return ({'format': 1, 'type': 'graphe_af_postgresql', 'noeuds': noeuds,
             'aretes': aretes, 'reseaux': [len(g) for g in groups],
             'reseaux_bl': sorted({group_index[i] for i, n in enumerate(noeuds) if n['bl']}),
             'villes': villes, 'regions': contour()},
            {'format': 1, 'noeuds': noms, 'liens': details,
             'liens_liste_noire_sans_rattachement': non_rattaches})


def extraire(url):
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=8) as cx:
        cx.execute('SET TRANSACTION READ ONLY')
        cx.execute("SET LOCAL statement_timeout = '120000ms'")
        identites = cx.execute('SELECT identite_id, type_identite, nom, ville_code FROM af_identite ORDER BY identite_id').fetchall()
        relations = cx.execute('SELECT relation_id, pp_identite_id, pm_identite_id, role FROM af_relation ORDER BY relation_id').fetchall()
        liens_bl = cx.execute('''
            SELECT l.lien_id, l.identite_id, l.dossier_ref, l.regle, l.niveau,
                   b.entite_id, b.nom_affiche, b.type_entite, b.ville_code
            FROM af_lien l JOIN bl_entite b
              ON l.cible = 'bl_entite' AND l.cible_id = b.entite_id::text
            ORDER BY l.lien_id
        ''').fetchall()
    return identites, relations, liens_bl


def publier(url, sortie):
    sortie = Path(sortie).resolve()
    if sortie.exists() or sortie.is_symlink():
        raise ValueError('Le dossier de sortie existe déjà : utiliser un nouveau chemin')
    if not sortie.parent.is_dir():
        raise ValueError('Le dossier parent doit déjà exister')
    lignes = extraire(url)
    geo, identites = construire(*lignes)
    stats = {'identites_af': len(lignes[0]), 'relations_af': len(lignes[1]),
             'liens_bl_source': len(lignes[2]), 'noeuds': len(geo['noeuds']),
             'aretes': len(geo['aretes']), 'noeuds_bl': sum(n['bl'] for n in geo['noeuds']),
             'reseaux': len(geo['reseaux']),
             'liens_bl_sans_rattachement': identites['liens_liste_noire_sans_rattachement'],
             'liens_detailles': len(identites['liens'])}
    previous_umask = os.umask(0o077)
    try:
        tmp = Path(tempfile.mkdtemp(prefix='.graph-pg-', dir=sortie.parent))
        try:
            def write(name, value):
                p = tmp / name
                with p.open('x', encoding='utf-8') as f:
                    json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
                return hashlib.sha256(p.read_bytes()).hexdigest()
            checksums = {'geometrie.json': write('geometrie.json', geo),
                         'identites.json': write('identites.json', identites),
                         'statistiques.json': write('statistiques.json', stats)}
            write('manifeste.json', {'format': 1, 'type': 'graphe_af_postgresql',
                  'date_publication': datetime.now(timezone.utc).isoformat(),
                  'donnees_reelles': True, 'empreintes': checksums})
            os.rename(tmp, sortie)
        except BaseException:
            # Aucun effacement d'une publication existante ; nettoyer seulement
            # notre propre dossier provisoire identifié.
            import shutil
            shutil.rmtree(tmp)
            raise
    finally:
        os.umask(previous_umask)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sortie', required=True, help='Nouveau dossier de sortie')
    a = ap.parse_args()
    url = os.environ.get('AF_DATABASE_URL')
    if not url:
        ap.error('AF_DATABASE_URL doit être définie')
    print(json.dumps(publier(url, a.sortie), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
