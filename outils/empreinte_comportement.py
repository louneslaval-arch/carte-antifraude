#!/usr/bin/env python3
"""Empreinte du comportement de la publication et du générateur, pour prouver qu'un remaniement ne change rien.

Les indices étant tirés au hasard, la publication est ramenée à une forme canonique (chaque indice remplacé par
l'identifiant interne qu'il désigne) avant d'être hachée. Usage : outils/empreinte_comportement.py base chaines.json
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, 'pipeline'))
import publier_carte as pc  # noqa: E402




def empreinte_publication(base, chaines):
    with tempfile.TemporaryDirectory() as d:
        pc.publier(base, chaines, d)
        con = sqlite3.connect(os.path.join(d, 'identites.sqlite'))
        ref = dict(con.execute('SELECT indice, ref_id FROM noeud'))
        g = json.load(open(os.path.join(d, 'geometrie.json'), encoding='utf-8'))
        g['construction'] = None
        n = g['noeuds']
        noeuds = sorted((ref[i], n['t'][i], n['bl'][i], n['deg'][i], n['ville'][i]) for i in range(len(ref)))
        # réseau : même partition, numéros quelconques
        groupes = {}
        for i, c in enumerate(n['c']):
            groupes.setdefault(c, []).append(ref[i])
        partition = sorted(sorted(v) for v in groupes.values())
        aretes = sorted((*sorted((ref[a], ref[b])), s, f) for a, b, s, f in zip(g['aretes']['a'], g['aretes']['b'],
                                                                    g['aretes']['style'], g['aretes']['force']))
        inscrits = [(ref[p['i']], p['type'], p['compte'], p['alerte'], p['certain'],
                     sorted((ref[i], d_, b, x) for i, d_, b, x in p['noeuds']),
                     sorted((ref[a], ref[b], l, s, fi, fo) for a, b, l, s, fi, fo in p['aretes']), p['chaines'])
                    for p in g['inscrits']]
        tables = {}
        for t, req in [('identite', 'SELECT * FROM identite'), ('lien', 'SELECT * FROM lien'),
                       ('annonce', 'SELECT * FROM annonce'), ('recherche', 'SELECT * FROM recherche')]:
            lignes = []
            for r in con.execute(req):
                r = list(r)
                if t == 'lien':
                    r[0:2] = sorted((ref[r[0]], ref[r[1]]))      # arête non orientée
                else:
                    r[0] = ref[r[0]]
                lignes.append(json.dumps(r, ensure_ascii=False, default=str))
            tables[t] = sorted(lignes)
        m = json.load(open(os.path.join(d, 'manifeste.json')))
        tout = dict(villes=g['villes'], noeuds=noeuds, partition=partition, aretes=aretes, inscrits=inscrits,
                    tables=tables, reseaux=sorted(g['reseaux']), nb_reseaux_bl=len(g['reseaux_bl']),
                    manifeste={k: m[k] for k in ('noeuds', 'inscrits_personnes', 'inscrits_societes', 'fictif')})
        return hashlib.sha256(json.dumps(tout, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def empreinte_generateur():
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, os.path.join(RACINE, 'jeu_essai', 'generer.py'), '--echelle', 'petit',
                        '--sortie', d], check=True, capture_output=True)
        h = hashlib.sha256()
        for f in sorted(os.listdir(d)):
            h.update(open(os.path.join(d, f), 'rb').read())
        return h.hexdigest()


if __name__ == '__main__':
    print('publication', empreinte_publication(sys.argv[1], sys.argv[2]))
    print('generateur ', empreinte_generateur())
