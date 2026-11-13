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
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

FORMAT = 1
# Types de nœud (couche 1, champ t)
T_SOCIETE, T_PERSONNE, T_INSCRIT_PP, T_INSCRIT_PM = 0, 1, 2, 3
NOMS_TYPES = ['societe', 'personne', 'inscrit_personne', 'inscrit_societe']
# Rôle simple, rapprochement inscrit ↔ registre, passage d'une société à l'autre ; puis les styles du kit du 11/11 :
# rapprochement certain, rôle terminé (« ancien »), et leurs combinaisons. Les numéros existants ne changent jamais.
STYLES = ['', 'rap', 'pont', 'certain', 'ancien', 'ancien rap', 'ancien certain', 'ancien pont']
FICHIERS = ('geometrie.json', 'identites.sqlite', 'statistiques.json')   # tous portés par le manifeste
PREFIXE_FICTIF = 'ZZ'                 # tous les CIN du jeu d'essai et du générateur

from chaines_dessin import ROLES_FR  # noqa: E402  (même dossier que ce script)

# Libellés de rôle admis dans la couche 1 : le vocabulaire de chaines_dessin.role_txt, part détenue comprise.
# Tout autre libellé (rôle brut inattendu) ne va que dans la couche 2.
_ROLES = sorted(set(ROLES_FR.values()) | {'associée de'})          # ordre indifférent : expression ancrée
ROLE_PERMIS_RE = re.compile('^(' + '|'.join(map(re.escape, _ROLES)) + r')( \(\d+(\.\d+)? %\))?$')


# Rôles datés du kit du 11/11 : « gérant (06/2025) », « ancien associé (cédé 02/2025) », « associé 50 % (01/2023) »,
# plusieurs rôles séparés par une virgule, suffixe « · annonce mélangée ». La couche 1 garde le rôle et la part, jamais
# la date (une date d'annonce, croisée avec le registre public, désignerait la société).
_DATE_ROLE_RE = re.compile(r'\s*\((?:cédé |remplacé |autre gérant nommé )?\d{2}/\d{4}\)')
_PART_NUE_RE = re.compile(r'^(.*?) (\d+(?:\.\d+)?) %$')


def _role_simple(partie):
    if partie != partie.strip():  # espace parasite : libellé inattendu, il reste en couche 2
        return None
    partie = _DATE_ROLE_RE.sub('', partie)
    m = _PART_NUE_RE.match(partie)  # « associé 50 % » → « associé (50 %) »
    if m:
        partie = f'{m.group(1)} ({m.group(2)} %)'
    return partie if ROLE_PERMIS_RE.match(partie) else None


def role_couche1(lib):
    if not lib:
        return ''
    lib = lib.split(' · ', 1)[0]
    parties = [_role_simple(p) for p in lib.split(', ')]
    return ', '.join(parties) if all(parties) else ''


class Indices:
    """Table figée identifiant interne ↔ indice opaque, construite d'un coup par `figer`.

    Les identifiants sont numérotés dans un ordre aléatoire : l'indice ne dit rien de l'ordre alphabétique, du RC,
    ni de l'ordre de construction de la base.
    """

    def __init__(self, types):
        refs = list(types)
        random.SystemRandom().shuffle(refs)
        self.ref_de = tuple(refs)
        self.type_de = dict(types)
        self.indice_de = {r: k for k, r in enumerate(refs)}

    def __getitem__(self, ref):
        return self.indice_de[ref]

    def __len__(self):
        return len(self.ref_de)

    def types(self):
        return [self.type_de[r] for r in self.ref_de]


def societe_racine(con):
    """Société du registre dessinée au centre de la carte d'une société inscrite.

    Reprend la règle de chaines_dessin.calculer : liens d'identité retenus (ni faibles ni écartés), et la plus petite
    societe_id. Le résultat est vérifié dans `ref_noeud` contre le RC et le tribunal affichés.
    """
    return dict(con.execute(
        """SELECT bl_entite_id, MIN(rc_objet_id) FROM correspondance
           WHERE rc_objet = 'rc_societe' AND nature NOT IN ('emploi', 'adresse')
             AND statut NOT IN ('faible', 'ecarte') GROUP BY bl_entite_id"""))


def ref_noeud(cle, noeud, inscrit, contexte):
    """Identifiant interne et type d'un nœud de chaines.json (« R », « S123 », « I45 »)."""
    if cle == 'R' and inscrit['type'] == 'PP':
        return inscrit['ref'], T_INSCRIT_PP
    if cle == 'R':
        sid = contexte['racine_pm'][inscrit['eid']]
        if contexte['soc'][sid] != (noeud.get('rc'), noeud.get('trib')):
            raise SystemExit('Société racine introuvable pour une société inscrite : '
                             'la règle de chaines_dessin a changé, à revoir.')
        return f'S:{sid}', T_SOCIETE
    if cle[:1] == 'S':
        return f'S:{int(cle[1:])}', T_SOCIETE
    if cle[:1] == 'I':
        return f'I:{int(cle[1:])}', T_PERSONNE
    raise SystemExit(f'Clé de nœud inattendue dans chaines.json : {cle!r}')


def lire_entrees(con, chaines):
    """Relie chaque entrée de chaines.json à son entité inscrite, et chaque nœud à un identifiant interne."""
    entite_de_cle = {cle: (eid, typ) for eid, cle, typ in
                     con.execute('SELECT entite_id, cle_entite, type_entite FROM bl_entite')}
    contexte = dict(racine_pm=societe_racine(con), soc={sid: (rc, trib) for sid, rc, trib in con.execute(
        'SELECT societe_id, rc_num, tribunal_code FROM rc_societe')})
    types, entrees = {}, []
    for x in chaines:
        typ, cle = x['id'].split(':', 1)
        eid, typ_base = entite_de_cle[cle]
        if typ != typ_base:
            raise SystemExit('Type d\'inscrit incohérent entre chaines.json et la base.')
        inscrit = dict(eid=eid, type=typ, ref=f'E:{eid}')
        types.setdefault(inscrit['ref'], T_INSCRIT_PP if typ == 'PP' else T_INSCRIT_PM)
        refs = {}
        for k, n in x['noeuds'].items():
            refs[k], t = ref_noeud(k, n, inscrit, contexte)
            types.setdefault(refs[k], t)
        entrees.append((x, inscrit, refs))
    return Indices(types), entrees


def composantes(n, aretes):
    """Numéro de réseau (composante connexe) de chaque nœud."""
    parent = list(range(n))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in aretes:
        parent[racine(a)] = racine(b)
    num = {}
    return [num.setdefault(racine(i), len(num)) for i in range(n)]


# ---- une carte d'inscrit : sa part de couche 1 et sa chaîne complète (couche 2) --------------------------------
def style_de(arete):
    if arete['style'] not in STYLES:  # un style nouveau du kit ne doit jamais se perdre en silence
        raise ValueError('style d\'arête inconnu : ajouter à STYLES')
    return STYLES.index(arete['style'])


def carte_couche1(x, ind, certain):
    """Structure de la carte d'un inscrit, sans identité ; `ind` traduit une clé de nœud en indice."""
    return dict(
        type=x['type'], compte=x['compte'], alerte=bool(x['alerte']),
        certain=certain,
        noeuds=[[ind(k), nd.get('d', 0), 1 if nd.get('bl') else 0, 1 if nd.get('diss') else 0]
                for k, nd in x['noeuds'].items()],
        aretes=[[ind(a['a']), ind(a['b']), role_couche1(a['lib']), style_de(a), a['fiab'], a['force']]
                for a in x['aretes']],
        chaines=[[c['distance'], c['fiab'], c['force'], 1 if c['bl'] else 0] for c in x['chaines']])


def chaine_complete(x, ind, i_inscrit):
    """Entrée de donnees_carte telle quelle, clés de nœud remplacées par les indices."""
    return dict(x, id=i_inscrit, racine=ind('R'),
                noeuds={str(ind(k)): nd for k, nd in x['noeuds'].items()},
                aretes=[dict(a, a=ind(a['a']), b=ind(a['b'])) for a in x['aretes']])


def cartes(con, idx, entrees):
    """Pour chaque inscrit : (indice, carte de la couche 1, chaîne complète, indice de chaque clé de nœud)."""
    certain = {eid for (eid,) in con.execute(
        "SELECT DISTINCT bl_entite_id FROM correspondance_retenue WHERE niveau = 'certain'")}
    sortie = []
    for x, inscrit, refs in entrees:
        indices = {k: idx[r] for k, r in refs.items()}
        i_inscrit = idx[inscrit['ref']]
        c1 = dict(i=i_inscrit, **carte_couche1(x, indices.__getitem__, inscrit['eid'] in certain))
        sortie.append((i_inscrit, c1, chaine_complete(x, indices.__getitem__, i_inscrit), indices))
    return sortie


# ---- fusion des cartes : un nœud ou une arête vu dans plusieurs cartes ------------------------------------------
def fusionner_noeuds(idx, entrees, liste_cartes):
    """Indicateur liste noire (vrai s'il l'est dans une carte), ville et fiche (la première vue l'emporte)."""
    bl = [1 if t in (T_INSCRIT_PP, T_INSCRIT_PM) else 0 for t in idx.types()]
    ville, identite = [None] * len(idx), {}
    for (x, _inscrit, _refs), (_i, _c1, _ch, indices) in zip(entrees, liste_cartes):
        for k, nd in x['noeuds'].items():
            i = indices[k]
            bl[i] = bl[i] or (1 if nd.get('bl') else 0)
            ville[i] = ville[i] or nd.get('ville')
            identite.setdefault(i, dict(nom=nd.get('nom'), rc=nd.get('rc'), tribunal=nd.get('trib'),
                                        ville=nd.get('ville'), derniere=nd.get('dern'), url=nd.get('url'),
                                        dissoute=nd.get('diss')))
    return bl, ville, identite


def fusionner_liens(entrees, liste_cartes):
    """Arête non orientée → la plus forte vue, toutes cartes confondues."""
    liens = {}
    for (x, _inscrit, _refs), (_i, _c1, _ch, indices) in zip(entrees, liste_cartes):
        for a in x['aretes']:
            ia, ib = indices[a['a']], indices[a['b']]
            cle = (min(ia, ib), max(ia, ib))
            if cle not in liens or a['force'] > liens[cle]['force']:
                liens[cle] = dict(libelle=a['lib'], style=style_de(a), fiab=a['fiab'], force=a['force'])
    return liens


def villes_inscrits(con, idx, ville):
    """Le nœud racine d'une personne inscrite ne porte pas de ville : on prend celle de la liste noire."""
    for eid, v in con.execute('SELECT entite_id, ville_code FROM bl_entite WHERE ville_code IS NOT NULL'):
        i = idx.indice_de.get(f'E:{eid}')
        if i is not None and not ville[i]:
            ville[i] = v
    return ville


def reseaux(c):
    """Taille de chaque réseau, dans l'ordre des numéros."""
    taille = Counter(c)
    return [taille[k] for k in range(len(taille))]


def degres(n, liens):
    deg = [0] * n
    for a, b in liens:
        deg[a] += 1
        deg[b] += 1
    return deg


def colonnes_aretes(liens):
    """Arêtes en tableaux parallèles (a, b, style, force)."""
    paires = list(liens)
    return dict(a=[a for a, _ in paires], b=[b for _, b in paires],
                style=[liens[p]['style'] for p in paires], force=[liens[p]['force'] for p in paires])


def numeros_reseau(n, liens, liste_cartes):
    """Réseau de chaque nœud ; l'entité inscrite PM, non dessinée, suit sa société racine."""
    attaches = [(i, ch['racine']) for i, _c1, ch, _ind in liste_cartes if ch['racine'] != i]
    return composantes(n, list(liens) + attaches)


def colonne_ville(ville):
    """Liste des villes et, pour chaque nœud, le rang de la sienne (−1 : inconnue)."""
    villes = sorted({v for v in ville if v})
    rang = {v: k for k, v in enumerate(villes)}
    return villes, [rang.get(v, -1) for v in ville]


def geometrie(idx, bl, ville, liens, liste_cartes):
    """Couche 1 complète."""
    n = len(idx)
    c = numeros_reseau(n, liens, liste_cartes)
    villes, rang_ville = colonne_ville(ville)
    return dict(
        format=FORMAT, construction=dict(date=horodatage()), types=NOMS_TYPES, styles=STYLES, villes=villes,
        noeuds=dict(t=idx.types(), bl=bl, c=c, deg=degres(n, liens), ville=rang_ville),
        aretes=colonnes_aretes(liens), reseaux=reseaux(c),
        reseaux_bl=sorted({c[i] for i in range(n) if bl[i]}),
        inscrits=[c1 for _i, c1, _ch, _ind in liste_cartes])


def construire(con, chaines):
    """Les deux couches, en mémoire."""
    idx, entrees = lire_entrees(con, chaines)
    liste_cartes = cartes(con, idx, entrees)
    bl, ville, identite = fusionner_noeuds(idx, entrees, liste_cartes)
    liens = fusionner_liens(entrees, liste_cartes)
    geo = geometrie(idx, bl, villes_inscrits(con, idx, ville), liens, liste_cartes)
    couche2 = dict(identite=identite, liens=liens, certains={i for i, c1, _ch, _ind in liste_cartes if c1['certain']},
                   chaines=[(i, ch) for i, _c1, ch, _ind in liste_cartes])
    return idx, geo, couche2


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


# ---- couche 2 : lignes à écrire (fonctions pures) puis écriture -------------------------------------------------
def lignes_identite(idx, identite, inscrits, certains):
    """Une fiche par nœud ; pour un inscrit, les champs de la liste noire priment."""
    lignes = []
    for i, r in enumerate(idx.ref_de):
        v = dict(identite.get(i, {}))
        if r in inscrits:
            nom, cin, rc, trib, ville, listes, motifs = inscrits[r]
            v.update(nom=nom, cin=cin, listes=listes, motifs=motifs, rc=rc or v.get('rc'),
                     tribunal=trib or v.get('tribunal'), ville=ville or v.get('ville'))
        lignes.append((i, v.get('nom'), None, v.get('cin'), v.get('rc'), v.get('tribunal'), v.get('ville'),
                       v.get('derniere'), v.get('url'), v.get('dissoute'), v.get('listes'), v.get('motifs'),
                       1 if i in certains else 0))
    return lignes


def lignes_recherche(lignes):
    """Formes cherchables de chaque fiche : nom, CIN, RC, en majuscules."""
    return [(i, champ, str(valeur).upper())
            for i, nom, _lat, cin, rc, *_ in lignes
            for champ, valeur in (('nom', nom), ('cin', cin), ('rc', rc)) if valeur]


def lignes_annonce(con, idx):
    """Annonces des sociétés présentes sur la carte, dans l'ordre des dates."""
    indice_de_sid = {int(r[2:]): i for i, r in enumerate(idx.ref_de) if r.startswith('S:')}
    return [(indice_de_sid[sid], date, typ, url) for sid, date, typ, url in con.execute(
        'SELECT societe_id, date_publication, type_acte, url FROM rc_annonce WHERE societe_id IS NOT NULL '
        'ORDER BY societe_id, date_publication') if sid in indice_de_sid]


def ecrire_identites(chemin, con, idx, couche2):
    inscrits = {f'E:{r[0]}': r[1:] for r in con.execute(
        'SELECT entite_id, nom_affiche, cin, rc_num, tribunal_code, ville_code, types_liste, motifs FROM bl_entite')}
    fiches = lignes_identite(idx, couche2['identite'], inscrits, couche2['certains'])
    out = sqlite3.connect(chemin)
    out.executescript(SCHEMA_IDENTITES)
    out.executemany('INSERT INTO noeud VALUES (?, ?, ?)',
                    [(i, NOMS_TYPES[idx.type_de[r]], r) for i, r in enumerate(idx.ref_de)])
    out.executemany('INSERT INTO identite VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', fiches)
    out.executemany('INSERT INTO lien VALUES (?,?,?,?,?,?)', [(a, b, l['libelle'], l['style'], l['fiab'], l['force'])
                                                              for (a, b), l in couche2['liens'].items()])
    out.executemany('INSERT INTO annonce VALUES (?,?,?,?)', lignes_annonce(con, idx))
    out.executemany('INSERT INTO chaine VALUES (?, ?)',
                    [(i, json.dumps(ch, ensure_ascii=False)) for i, ch in couche2['chaines']])
    out.executemany('INSERT INTO recherche VALUES (?,?,?)', lignes_recherche(fiches))
    out.commit()
    out.execute('VACUUM')
    out.close()
    os.chmod(chemin, 0o640)


def statistiques(con):
    """Agrégats sans identité : correspondances retenues par règle et niveau, et par statut."""
    regles = [dict(regle=r, niveau=n, correspondances=c, inscrits=i) for r, n, c, i in con.execute(
        """SELECT regle, niveau, COUNT(*), COUNT(DISTINCT bl_entite_id) FROM correspondance_retenue
           GROUP BY regle, niveau ORDER BY regle, niveau""")]
    statuts = dict(con.execute('SELECT statut, COUNT(*) FROM correspondance_retenue GROUP BY statut'))
    return dict(regles=regles, statuts=statuts)


def horodatage():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def est_fictif(cins):
    """Vrai seulement si chaque CIN porte le préfixe réservé : une seule exception suffit à le refuser."""
    return bool(cins) and all(c.upper().startswith(PREFIXE_FICTIF) for c in cins)


def manifeste(con, dossier, n):
    pp, pm = (con.execute('SELECT COUNT(*) FROM bl_entite WHERE type_entite = ?', (t,)).fetchone()[0]
              for t in ('PP', 'PM'))
    fichiers = {f: empreinte(os.path.join(dossier, f)) for f in FICHIERS}
    m = dict(format=FORMAT, date_publication=horodatage(), noeuds=n, inscrits_personnes=pp, inscrits_societes=pm,
             fictif=est_fictif([c for (c,) in con.execute('SELECT cin FROM bl_entite WHERE cin IS NOT NULL')]),
             fichiers=fichiers,
             empreinte=hashlib.sha256(''.join(fichiers[f] for f in sorted(fichiers)).encode()).hexdigest())
    with open(os.path.join(dossier, 'manifeste.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    return m


def basculer(provisoire, dossier):
    """Remplace `dossier` par `provisoire` : l'ancien n'est retiré qu'une fois le nouveau complet."""
    ancien = provisoire + '.ancien'
    if os.path.exists(dossier):
        os.rename(dossier, ancien)
    os.rename(provisoire, dossier)
    shutil.rmtree(ancien, ignore_errors=True)


def publier(base, chemin_chaines, dossier):
    """Écrit la publication dans un dossier provisoire voisin, manifeste en dernier, puis bascule.

    Un arrêt en cours de route laisse la publication précédente intacte ; relancer donne le même état.
    """
    dossier = os.path.abspath(dossier)
    os.makedirs(os.path.dirname(dossier), exist_ok=True)
    provisoire = tempfile.mkdtemp(prefix='.' + os.path.basename(dossier) + '-', dir=os.path.dirname(dossier))
    con = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    try:
        with open(chemin_chaines, encoding='utf-8') as f:
            idx, geo, couche2 = construire(con, json.load(f))
        with open(os.path.join(provisoire, 'geometrie.json'), 'w', encoding='utf-8') as f:
            json.dump(geo, f, ensure_ascii=False, separators=(',', ':'))
        ecrire_identites(os.path.join(provisoire, 'identites.sqlite'), con, idx, couche2)
        with open(os.path.join(provisoire, 'statistiques.json'), 'w', encoding='utf-8') as f:
            json.dump(statistiques(con), f, ensure_ascii=False)
        m = manifeste(con, provisoire, len(idx))
        os.chmod(provisoire, 0o750)
        basculer(provisoire, dossier)
        return m
    finally:
        con.close()
        shutil.rmtree(provisoire, ignore_errors=True)


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
