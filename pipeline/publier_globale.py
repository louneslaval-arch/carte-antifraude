#!/usr/bin/env python3
"""Publication de la carte globale (sortie de « carte_globale.py --json ») en deux couches, sur le modèle de
publier_carte.py, dont elle reprend les briques (indices opaques, schéma des identités, empreintes, bascule).

  geometrie.json     couche 1 : la carte sans rien qui identifie. Par nœud : positions (vue réseau et vue Maroc),
                     type, réseau, degré, ville, appartenance à la liste noire (0 ou 1), origine, nombre de sociétés
                     d'une personne, départ certain d'un inscrit. Par arête : indices, force, style, libellé de rôle
                     sans date. Contour du Maroc et disques des villes. Indices tirés au hasard à chaque publication.
  identites.sqlite   couche 2 : tables de publier_carte (noeud, identite, lien, annonce, chaine, recherche) et
                     `fiche_globale` (texte de la liste noire, personnes citées, dossiers).
  statistiques.json  comptages sans identité.
  manifeste.json     format 1, type « globale », marque « fictif », empreintes.

Usage :
  python3 publier_globale.py --globale globale.json --sortie publication_globale/2026-11-17

La disposition et les rapprochements ne sont pas touchés : ce script ne fait que redistribuer ce que
carte_globale.py a calculé.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publier_carte as pc  # noqa: E402

TYPES = ('societe', 'personne', 'inscrit')
# Styles d'arête de carte_globale.py (rôle actuel ou terminé, annonce mélangée, confirmé ou lu dans un dossier,
# rapprochements) ; un style nouveau ne doit jamais se perdre en silence. Les numéros existants ne changent jamais.
STYLES = ('', 'rap', 'certain', 'ancien', 'ancien rap', 'ancien certain', 'pont', 'ancien pont', 'dossier',
          'melange', 'ancien melange', 'ancien dossier', 'melange dossier', 'ancien melange dossier')
CHAMPS_COUCHE1 = {'x', 'y', 'mx', 'my', 'deg', 'c', 't', 'ville', 'bl', 'o', 'ns', 'certain'}
ORIGINES = ('r', 'd', 'rd')
# Libellés sans identité admis en couche 1, en plus des rôles de publier_carte (sans leur date)
RAPPROCHEMENT_RE = re.compile(r'^rapprochement (R|AF)\d{2}[a-z]? \((certain|probable)(, même CIN, dossier)?'
                              r'(, poids \d\.\d{2})?\)$')
LIBELLES_FIXES = {'société associée'}

SCHEMA_GLOBALE = """
CREATE TABLE fiche_globale (indice INTEGER PRIMARY KEY REFERENCES noeud, liste_noire TEXT, personnes INTEGER,
                            nb_dossiers INTEGER, dossiers TEXT);
"""


def libelle_couche1(lib):
    """Rôle sans date (« gérant (06/2025) » → « gérant »), rapprochement ou lien fixe ; sinon rien."""
    if not lib:
        return ''
    if lib in LIBELLES_FIXES or RAPPROCHEMENT_RE.match(lib):
        return lib
    return pc.role_couche1(lib)


def _compact(valeur):
    return re.sub(r'\s+', '', str(valeur)).upper()


def construire(globale):
    """(indices, couche 1, lignes de la couche 2) en mémoire, à partir de la sortie de carte_globale.py."""
    noeuds = globale['noeuds']
    for n in noeuds:
        if n['t'] not in TYPES:
            raise ValueError('type de nœud inconnu de la carte globale')
        if n.get('o', 'r') not in ORIGINES:
            raise ValueError("origine de nœud inconnue de la carte globale")
    for a in globale['aretes']:
        if a['style'] not in STYLES:
            raise ValueError("style d'arête inconnu : ajouter à STYLES")
    idx = pc.Indices({n['id']: TYPES.index(n['t']) for n in noeuds})
    ref_de_pos = [n['id'] for n in noeuds]                   # position dans globale.json → identifiant interne
    par_ref = {n['id']: n for n in noeuds}

    def couche1(n):
        c = {k: n[k] for k in ('x', 'y', 'mx', 'my', 'deg', 'c', 't')}
        c['bl'] = 1 if n.get('bl') else 0
        for k in ('ville', 'o', 'ns'):
            if n.get(k) is not None:
                c[k] = n[k]
        if n['t'] == 'inscrit':
            c['certain'] = 1 if n.get('certain') else 0
        return c

    geo = dict(
        format=pc.FORMAT, type='globale', construction=dict(date=pc.horodatage()), date_carte=globale['construction'],
        noeuds=[couche1(par_ref[r]) for r in idx.ref_de],
        aretes=[dict(a=idx[ref_de_pos[a['a']]], b=idx[ref_de_pos[a['b']]], force=a['force'], style=a['style'],
                     lib=libelle_couche1(a['lib'])) for a in globale['aretes']],
        reseaux=globale['reseaux'], reseaux_bl=globale['reseaux_bl'], geo=globale['geo'])
    identite = [(i, n.get('nom'), n.get('lat'), n.get('cin'), n.get('rc'), n.get('trib'), n.get('ville'), n.get('dern'),
                 n.get('url'), 1 if n.get('diss') else 0, n.get('listes'), n.get('motifs'), 1 if n.get('certain') else 0)
                for i, n in ((i, par_ref[r]) for i, r in enumerate(idx.ref_de))]
    fiches = [(i, n.get('bl') or None, n.get('np'), n.get('nd'), n.get('dos'))
              for i, n in ((i, par_ref[r]) for i, r in enumerate(idx.ref_de))]
    liens = [(idx[ref_de_pos[a['a']]], idx[ref_de_pos[a['b']]], a['lib'], STYLES.index(a['style']), None, a['force'])
             for a in globale['aretes']]
    recherche = []
    for i, nom, lat, cin, rc, *_ in identite:
        recherche += [(i, 'nom', v.upper()) for v in (nom, lat) if v]
        recherche += [(i, champ, _compact(v)) for champ, v in (('cin', cin), ('rc', rc)) if v]
    return idx, geo, dict(identite=identite, fiches=fiches, liens=liens, recherche=recherche)


def ecrire_identites(chemin, idx, couche2):
    out = sqlite3.connect(chemin)
    out.executescript(pc.SCHEMA_IDENTITES + SCHEMA_GLOBALE)
    out.executemany('INSERT INTO noeud VALUES (?, ?, ?)', [(i, TYPES[idx.type_de[r]], r) for i, r in enumerate(idx.ref_de)])
    out.executemany('INSERT INTO identite VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', couche2['identite'])
    out.executemany('INSERT INTO fiche_globale VALUES (?,?,?,?,?)', couche2['fiches'])
    out.executemany('INSERT INTO lien VALUES (?,?,?,?,?,?)', couche2['liens'])
    out.executemany('INSERT INTO recherche VALUES (?,?,?)', couche2['recherche'])
    out.commit()
    out.execute('VACUUM')
    out.close()
    os.chmod(chemin, 0o640)


def statistiques(geo):
    """Comptages sans identité : nœuds par type, arêtes, réseaux."""
    return dict(noeuds=dict(Counter(n['t'] for n in geo['noeuds'])), aretes=len(geo['aretes']),
                reseaux=len(geo['reseaux']), reseaux_liste_noire=len(geo['reseaux_bl']))


def manifeste(dossier, geo, cins):
    fichiers = {f: pc.empreinte(os.path.join(dossier, f)) for f in pc.FICHIERS}
    m = dict(format=pc.FORMAT, type='globale', date_publication=pc.horodatage(), noeuds=len(geo['noeuds']),
             inscrits=sum(1 for n in geo['noeuds'] if n['t'] == 'inscrit'), fictif=pc.est_fictif(cins),
             fichiers=fichiers,
             empreinte=hashlib.sha256(''.join(fichiers[f] for f in sorted(fichiers)).encode()).hexdigest())
    with open(os.path.join(dossier, 'manifeste.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    return m


def publier(chemin_globale, dossier):
    """Écrit la publication dans un dossier provisoire voisin, manifeste en dernier, puis bascule : un arrêt en cours
    de route laisse la publication précédente intacte."""
    with open(chemin_globale, encoding='utf-8') as f:
        globale = json.load(f)
    idx, geo, couche2 = construire(globale)                  # refuse avant d'écrire quoi que ce soit
    dossier = os.path.abspath(dossier)
    os.makedirs(os.path.dirname(dossier), exist_ok=True)
    provisoire = tempfile.mkdtemp(prefix='.' + os.path.basename(dossier) + '-', dir=os.path.dirname(dossier))
    try:
        with open(os.path.join(provisoire, 'geometrie.json'), 'w', encoding='utf-8') as f:
            json.dump(geo, f, ensure_ascii=False, separators=(',', ':'))
        ecrire_identites(os.path.join(provisoire, 'identites.sqlite'), idx, couche2)
        with open(os.path.join(provisoire, 'statistiques.json'), 'w', encoding='utf-8') as f:
            json.dump(statistiques(geo), f, ensure_ascii=False)
        m = manifeste(provisoire, geo, [n['cin'] for n in globale['noeuds'] if n.get('cin')])
        os.chmod(provisoire, 0o750)
        pc.basculer(provisoire, dossier)
        return m
    finally:
        shutil.rmtree(provisoire, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--globale', required=True, help='Sortie de carte_globale.py --json')
    ap.add_argument('--sortie', required=True, help='Dossier de publication à écrire')
    a = ap.parse_args()
    m = publier(a.globale, a.sortie)
    taille = os.path.getsize(os.path.join(a.sortie, 'geometrie.json'))
    print(f"  carte globale publiée : {m['noeuds']} nœuds, {m['inscrits']} inscrits, géométrie {taille / 1e6:.2f} Mo, "
          f"{'fictive' if m['fictif'] else 'DONNÉES RÉELLES'}")
    print(f"  empreinte : {m['empreinte'][:16]}…")


if __name__ == '__main__':
    sys.exit(main())
