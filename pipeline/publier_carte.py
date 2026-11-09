#!/usr/bin/env python3
"""Publication de la carte en deux couches, à partir de la base construite et de la sortie de chaines_dessin.py.

  geometrie.json     couche 1 : ce qu'il faut pour dessiner, sans rien qui identifie une personne ou une société.
                     Les nœuds y sont désignés par un indice opaque (0 … N−1), tiré au hasard à chaque publication.
  identites.sqlite   couche 2 : table indice → identifiant interne, noms, CIN, RC, annonces, chaînes complètes.
                     Servie à la demande par l'interface, selon le rôle, et jamais copiée sur un poste.
  manifeste.json     date, nombre de nœuds, nombre d'inscrits, marque « fictif », empreintes SHA-256.

Usage :
  python3 publier_carte.py --base bl_rc.sqlite --chaines chaines.json --sortie publication/2026-11-09
  (chaines.json : sortie de « chaines_dessin.py --json » ; globale.json : sortie de « carte_globale.py --json »,
   pris en compte quand ce script sera fourni)

La logique de rapprochement n'est pas touchée : ce script ne fait que redistribuer ce que les scripts du kit
ont calculé.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

FORMAT = 1
# Types de nœud (couche 1, champ t)
T_SOCIETE, T_PERSONNE, T_INSCRIT_PP, T_INSCRIT_PM = 0, 1, 2, 3
NOMS_TYPES = ['societe', 'personne', 'inscrit_personne', 'inscrit_societe']
STYLES = ['', 'rap', 'pont']          # rôle simple, rapprochement inscrit ↔ registre, passage d'une société à l'autre
PREFIXE_FICTIF = 'ZZ'                 # tous les CIN du jeu d'essai et du générateur

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chaines_dessin import ROLES_FR  # noqa: E402

# Libellés de rôle admis dans la couche 1 : le vocabulaire de chaines_dessin.role_txt, part détenue comprise.
# Tout autre libellé (rôle brut inattendu) ne va que dans la couche 2.
_ROLES = sorted(set(ROLES_FR.values()) | {'associée de'}, key=len, reverse=True)
ROLE_PERMIS_RE = re.compile('^(' + '|'.join(map(re.escape, _ROLES)) + r')( \(\d+(\.\d+)? %\))?$')


def role_couche1(lib):
    return lib if lib and ROLE_PERMIS_RE.match(lib) else ''


class Indices:
    """Attribue à chaque identifiant interne un indice opaque.

    Les identifiants sont d'abord collectés, puis numérotés dans un ordre aléatoire : l'indice ne dit rien de
    l'ordre alphabétique, du RC, ni de l'ordre de construction de la base.
    """

    def __init__(self):
        self.type_de = {}

    def ajouter(self, ref, typ):
        if ref not in self.type_de:
            self.type_de[ref] = typ
        return ref

    def figer(self):
        refs = list(self.type_de)
        random.SystemRandom().shuffle(refs)
        self.ref_de = refs
        self.indice_de = {r: k for k, r in enumerate(refs)}

    def __getitem__(self, ref):
        return self.indice_de[ref]

    def __len__(self):
        return len(self.ref_de)


def societe_racine(con):
    """Société du registre dessinée au centre de la carte d'une société inscrite.

    Reprend la règle de chaines_dessin.calculer : liens d'identité retenus (ni faibles ni écartés), et la plus petite
    societe_id. Le résultat est vérifié plus bas contre le RC et le tribunal affichés.
    """
    sortie = {}
    for eid, sid in con.execute(
            """SELECT bl_entite_id, MIN(rc_objet_id) FROM correspondance
               WHERE rc_objet = 'rc_societe' AND nature NOT IN ('emploi', 'adresse')
                 AND statut NOT IN ('faible', 'ecarte') GROUP BY bl_entite_id"""):
        sortie[eid] = sid
    return sortie


def lire_entrees(con, chaines):
    """Associe chaque entrée de chaines.json à son entité inscrite et chaque nœud à un identifiant interne."""
    entite_de_cle = {cle: (eid, typ) for eid, cle, typ in
                     con.execute('SELECT entite_id, cle_entite, type_entite FROM bl_entite')}
    soc = {sid: (rc, trib) for sid, rc, trib in
           con.execute('SELECT societe_id, rc_num, tribunal_code FROM rc_societe')}
    racine_pm = societe_racine(con)
    idx = Indices()
    entrees = []
    for x in chaines:
        typ, cle = x['id'].split(':', 1)
        eid, typ_base = entite_de_cle[cle]
        assert typ == typ_base, f'type incohérent pour l\'entrée {len(entrees)}'
        ref_inscrit = idx.ajouter(f'E:{eid}', T_INSCRIT_PP if typ == 'PP' else T_INSCRIT_PM)
        refs = {}
        for k, n in x['noeuds'].items():
            if k == 'R':
                if typ == 'PP':
                    refs[k] = ref_inscrit
                    continue
                sid = racine_pm[eid]
                if soc[sid] != (n.get('rc'), n.get('trib')):
                    raise SystemExit(f'Société racine introuvable pour l\'entrée {len(entrees)} : '
                                     'la règle de chaines_dessin a changé, à revoir.')
                refs[k] = idx.ajouter(f'S:{sid}', T_SOCIETE)
            elif k.startswith('S'):
                refs[k] = idx.ajouter(f'S:{int(k[1:])}', T_SOCIETE)
            elif k.startswith('I'):
                refs[k] = idx.ajouter(f'I:{int(k[1:])}', T_PERSONNE)
            else:
                raise SystemExit(f'Clé de nœud inattendue dans chaines.json : {k!r}')
        entrees.append((x, eid, ref_inscrit, refs))
    idx.figer()
    return idx, entrees


def composantes(n, aretes):
    """Numéro de réseau (composante connexe) de chaque nœud."""
    parent = list(range(n))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in aretes:
        ra, rb = racine(a), racine(b)
        if ra != rb:
            parent[ra] = rb
    num, c = {}, []
    for i in range(n):
        c.append(num.setdefault(racine(i), len(num)))
    return c


def construire(con, chaines):
    idx, entrees = lire_entrees(con, chaines)
    n = len(idx)
    t = [idx.type_de[r] for r in idx.ref_de]
    bl = [1 if ti in (T_INSCRIT_PP, T_INSCRIT_PM) else 0 for ti in t]
    ville_txt = [None] * n
    identite = {}                         # indice → champs de la couche 2 (le premier vu l'emporte)
    liens = {}                            # (a, b) → arête la plus forte, toutes cartes confondues
    par_inscrit, chaines_completes = [], []
    certain = {eid for (eid,) in con.execute(
        "SELECT DISTINCT bl_entite_id FROM correspondance_retenue WHERE niveau = 'certain'")}

    for x, eid, ref_inscrit, refs in entrees:
        i_inscrit = idx[ref_inscrit]
        noeuds_c1 = []
        for k, nd in x['noeuds'].items():
            i = idx[refs[k]]
            a_bl = 1 if nd.get('bl') else 0
            bl[i] = bl[i] or a_bl
            if nd.get('ville'):
                ville_txt[i] = ville_txt[i] or nd['ville']
            identite.setdefault(i, dict(nom=nd.get('nom'), rc=nd.get('rc'), tribunal=nd.get('trib'),
                                        ville=nd.get('ville'), derniere=nd.get('dern'), url=nd.get('url'),
                                        dissoute=nd.get('diss')))
            noeuds_c1.append([i, nd.get('d', 0), a_bl, 1 if nd.get('diss') else 0])
        aretes_c1 = []
        for a in x['aretes']:
            ia, ib = idx[refs[a['a']]], idx[refs[a['b']]]
            style = STYLES.index(a['style']) if a['style'] in STYLES else 0
            aretes_c1.append([ia, ib, role_couche1(a['lib']), style, a['fiab'], a['force']])
            cle = (min(ia, ib), max(ia, ib))
            if cle not in liens or a['force'] > liens[cle]['force']:
                liens[cle] = dict(libelle=a['lib'], style=style, fiab=a['fiab'], force=a['force'])
        par_inscrit.append(dict(
            i=i_inscrit, type=x['type'], compte=x['compte'], alerte=bool(x['alerte']), certain=eid in certain,
            noeuds=noeuds_c1, aretes=aretes_c1,
            chaines=[[c['distance'], c['fiab'], c['force'], 1 if c['bl'] else 0] for c in x['chaines']]))
        # chaîne complète, au format de donnees_carte, clés remplacées par les indices (pour la couche 2)
        complet = dict(x)
        complet['id'] = i_inscrit
        complet['noeuds'] = {str(idx[refs[k]]): nd for k, nd in x['noeuds'].items()}
        complet['racine'] = idx[refs['R']]
        complet['aretes'] = [dict(a, a=idx[refs[a['a']]], b=idx[refs[a['b']]]) for a in x['aretes']]
        chaines_completes.append((i_inscrit, complet))

    # ville des inscrits (le nœud racine d'une personne inscrite n'en porte pas)
    for eid, ville in con.execute('SELECT entite_id, ville_code FROM bl_entite WHERE ville_code IS NOT NULL'):
        i = idx.indice_de.get(f'E:{eid}')
        if i is not None and not ville_txt[i]:
            ville_txt[i] = ville

    deg = [0] * n
    for a, b in liens:
        deg[a] += 1
        deg[b] += 1
    # l'entité inscrite PM n'est pas dessinée : elle est reliée à sa société racine pour le numéro de réseau
    attaches = [(i, int(c['racine'])) for i, c in chaines_completes if c['racine'] != i]
    c = composantes(n, list(liens) + attaches)
    taille = defaultdict(int)
    for ci in c:
        taille[ci] += 1
    reseaux_bl = sorted({c[i] for i in range(n) if bl[i]})
    villes = sorted({v for v in ville_txt if v})
    geometrie = dict(
        format=FORMAT,
        construction=dict(date=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')),
        types=NOMS_TYPES, styles=STYLES, villes=villes,
        noeuds=dict(t=t, bl=bl, c=c, deg=deg, ville=[villes.index(v) if v else -1 for v in ville_txt]),
        aretes=dict(a=[a for a, _ in liens], b=[b for _, b in liens],
                    style=[l['style'] for l in liens.values()], force=[l['force'] for l in liens.values()]),
        reseaux=[taille[k] for k in range(len(taille))], reseaux_bl=reseaux_bl,
        inscrits=par_inscrit)
    return idx, geometrie, identite, liens, chaines_completes


SCHEMA_IDENTITES = """
CREATE TABLE noeud (indice INTEGER PRIMARY KEY, type TEXT NOT NULL, ref_id TEXT NOT NULL UNIQUE);
CREATE TABLE identite (
    indice INTEGER PRIMARY KEY REFERENCES noeud, nom TEXT, lat TEXT, cin TEXT, rc TEXT, tribunal TEXT,
    ville TEXT, derniere TEXT, url TEXT, dissoute INTEGER, listes TEXT, motifs TEXT, certain INTEGER);
CREATE TABLE lien (indice_a INTEGER, indice_b INTEGER, libelle TEXT, style INTEGER, fiab REAL, force REAL,
                   PRIMARY KEY (indice_a, indice_b));
CREATE INDEX lien_b ON lien (indice_b);
CREATE TABLE annonce (indice INTEGER REFERENCES noeud, date TEXT, type TEXT, url TEXT);
CREATE INDEX annonce_indice ON annonce (indice);
CREATE TABLE chaine (indice INTEGER PRIMARY KEY REFERENCES noeud, donnees TEXT NOT NULL);
-- recherche : une ligne par forme cherchable (nom, CIN, RC), en majuscules
CREATE TABLE recherche (indice INTEGER REFERENCES noeud, champ TEXT, valeur TEXT);
CREATE INDEX recherche_valeur ON recherche (valeur);
"""


def ecrire_identites(chemin, con, idx, identite, liens, chaines_completes, certains):
    if os.path.exists(chemin):
        os.remove(chemin)
    out = sqlite3.connect(chemin)
    out.executescript(SCHEMA_IDENTITES)
    out.executemany('INSERT INTO noeud VALUES (?, ?, ?)',
                    [(i, NOMS_TYPES[idx.type_de[r]], r) for i, r in enumerate(idx.ref_de)])
    inscrits = {f'E:{r[0]}': r[1:] for r in con.execute(
        'SELECT entite_id, nom_affiche, cin, rc_num, tribunal_code, ville_code, types_liste, motifs FROM bl_entite')}
    lignes = []
    for i, r in enumerate(idx.ref_de):
        v = identite.get(i, {})
        if r in inscrits:
            nom, cin, rc, trib, ville, listes, motifs = inscrits[r]
            v = dict(v, nom=nom, cin=cin, rc=rc or v.get('rc'), tribunal=trib or v.get('tribunal'),
                     ville=ville or v.get('ville'), listes=listes, motifs=motifs)
        lignes.append((i, v.get('nom'), None, v.get('cin'), v.get('rc'), v.get('tribunal'), v.get('ville'),
                       v.get('derniere'), v.get('url'), v.get('dissoute'), v.get('listes'), v.get('motifs'),
                       1 if i in certains else 0))
    out.executemany('INSERT INTO identite VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', lignes)
    out.executemany('INSERT INTO lien VALUES (?,?,?,?,?,?)',
                    [(a, b, l['libelle'], l['style'], l['fiab'], l['force']) for (a, b), l in liens.items()])
    # annonces des sociétés présentes sur la carte
    sid_de = {int(r[2:]): i for i, r in enumerate(idx.ref_de) if r.startswith('S:')}
    for sid, date, typ, url in con.execute(
            'SELECT societe_id, date_publication, type_acte, url FROM rc_annonce WHERE societe_id IS NOT NULL '
            'ORDER BY societe_id, date_publication'):
        if sid in sid_de:
            out.execute('INSERT INTO annonce VALUES (?,?,?,?)', (sid_de[sid], date, typ, url))
    out.executemany('INSERT INTO chaine VALUES (?, ?)',
                    [(i, json.dumps(ch, ensure_ascii=False)) for i, ch in chaines_completes])
    rech = []
    for i, nom, _lat, cin, rc, *_ in lignes:
        if nom:
            rech.append((i, 'nom', nom.upper()))
        if cin:
            rech.append((i, 'cin', cin.upper()))
        if rc:
            rech.append((i, 'rc', str(rc).upper()))
    out.executemany('INSERT INTO recherche VALUES (?,?,?)', rech)
    out.commit()
    out.execute('VACUUM')
    out.close()
    os.chmod(chemin, 0o640)


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def manifeste(con, dossier, n):
    pp, pm = (con.execute(f"SELECT COUNT(*) FROM bl_entite WHERE type_entite = '{t}'").fetchone()[0]
              for t in ('PP', 'PM'))
    cins = [c for (c,) in con.execute('SELECT cin FROM bl_entite WHERE cin IS NOT NULL')]
    # « fictif » seulement si chaque CIN porte le préfixe réservé : une seule exception suffit à le refuser
    fictif = bool(cins) and all(c.upper().startswith(PREFIXE_FICTIF) for c in cins)
    fichiers = {f: empreinte(os.path.join(dossier, f)) for f in ('geometrie.json', 'identites.sqlite')}
    m = dict(format=FORMAT, date_publication=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
             noeuds=n, inscrits_personnes=pp, inscrits_societes=pm, fictif=fictif, fichiers=fichiers,
             empreinte=hashlib.sha256(''.join(fichiers[f] for f in sorted(fichiers)).encode()).hexdigest())
    with open(os.path.join(dossier, 'manifeste.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    return m


def publier(base, chemin_chaines, dossier):
    os.makedirs(dossier, exist_ok=True)
    con = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    with open(chemin_chaines, encoding='utf-8') as f:
        chaines = json.load(f)
    idx, geometrie, identite, liens, completes = construire(con, chaines)
    certains = {p['i'] for p in geometrie['inscrits'] if p['certain']}
    with open(os.path.join(dossier, 'geometrie.json'), 'w', encoding='utf-8') as f:
        json.dump(geometrie, f, ensure_ascii=False, separators=(',', ':'))
    ecrire_identites(os.path.join(dossier, 'identites.sqlite'), con, idx, identite, liens, completes, certains)
    m = manifeste(con, dossier, len(idx))
    con.close()
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True, help='Base SQLite construite par construire_base.py')
    ap.add_argument('--chaines', required=True, help='Sortie de chaines_dessin.py --json')
    ap.add_argument('--sortie', required=True, help='Dossier de publication à écrire')
    a = ap.parse_args()
    m = publier(a.base, a.chaines, a.sortie)
    taille = os.path.getsize(os.path.join(a.sortie, 'geometrie.json'))
    print(f"  publication : {m['noeuds']} nœuds, {m['inscrits_personnes']} personnes et "
          f"{m['inscrits_societes']} sociétés inscrites, géométrie {taille / 1e6:.2f} Mo, "
          f"{'fictive' if m['fictif'] else 'DONNÉES RÉELLES'}")
    print(f"  empreinte : {m['empreinte'][:16]}…")


if __name__ == '__main__':
    sys.exit(main())
