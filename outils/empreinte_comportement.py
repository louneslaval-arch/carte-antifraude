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




def forme_canonique(dossier):
    """Publication ramenée à une forme indépendante du tirage des indices (indice → identifiant interne)."""
    con = sqlite3.connect(os.path.join(dossier, 'identites.sqlite'))
    ref = dict(con.execute('SELECT indice, ref_id FROM noeud'))
    with open(os.path.join(dossier, 'geometrie.json'), encoding='utf-8') as f:
        g = json.load(f)
    n = g['noeuds']
    groupes = {}
    for i, c in enumerate(n['c']):
        groupes.setdefault(c, []).append(ref[i])
    tables = {}
    for t in ('identite', 'lien', 'annonce', 'recherche', 'chaine'):
        lignes = []
        for r in con.execute(f'SELECT * FROM {t}'):
            r = list(r)
            if t == 'lien':
                r[0:2] = sorted((ref[r[0]], ref[r[1]]))      # arête non orientée
            else:
                r[0] = ref[r[0]]
            if t == 'chaine':
                r[1] = canon_chaine(json.loads(r[1]), ref)
            lignes.append(json.dumps(r, ensure_ascii=False, default=str, sort_keys=True))
        tables[t] = sorted(lignes)
    with open(os.path.join(dossier, 'manifeste.json'), encoding='utf-8') as f:
        m = json.load(f)
    return dict(
        format=g['format'], types=g['types'], styles=g['styles'], villes=g['villes'],
        noeuds=sorted([ref[i], n['t'][i], n['bl'][i], n['deg'][i], n['ville'][i]] for i in range(len(ref))),
        partition=sorted(sorted(v) for v in groupes.values()),
        aretes=sorted([*sorted((ref[a], ref[b])), s, f] for a, b, s, f in zip(
            g['aretes']['a'], g['aretes']['b'], g['aretes']['style'], g['aretes']['force'])),
        inscrits=[dict(p, i=ref[p['i']], noeuds=sorted([ref[i], *r] for i, *r in p['noeuds']),
                       aretes=sorted([ref[a], ref[b], *r] for a, b, *r in p['aretes'])) for p in g['inscrits']],
        reseaux=sorted(g['reseaux']), nb_reseaux_bl=len(g['reseaux_bl']),
        tables=tables,
        manifeste={k: m[k] for k in ('format', 'noeuds', 'inscrits_personnes', 'inscrits_societes', 'fictif')})


def canon_chaine(ch, ref):
    return dict(ch, id=ref[ch['id']], racine=ref[ch['racine']],
                noeuds={ref[int(k)]: v for k, v in ch['noeuds'].items()},
                aretes=sorted((dict(a, a=ref[a['a']], b=ref[a['b']]) for a in ch['aretes']),
                              key=lambda a: json.dumps(a, sort_keys=True, ensure_ascii=False)))


def empreinte_publication(base, chaines):
    with tempfile.TemporaryDirectory() as d:
        pc.publier(base, chaines, os.path.join(d, 'pub'))
        forme = forme_canonique(os.path.join(d, 'pub'))
        return hashlib.sha256(json.dumps(forme, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


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
