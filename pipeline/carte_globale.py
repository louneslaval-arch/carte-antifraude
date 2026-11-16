#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
carte_globale.py — tout le registre relié, sur un seul écran, avec la liste noire par-dessus.

  python3 carte_globale.py --base bl_rc.sqlite --html Carte_globale_liste_noire.html

Ce qui est dessiné :
  - toute personne du registre présente dans au moins deux sociétés (même CIN, ou même nom + même ville avec les
    garde-fous de chaines_dessin.py), et ces sociétés : ce sont les seuls liens qui relient des sociétés entre elles ;
  - les sociétés associées d'une autre société (participations) ;
  - les inscrits de la liste noire retrouvés au registre, reliés à la personne ou à la société du registre, et toutes
    les personnes de ces sociétés, même celles qui n'ont qu'une société.
  Les personnes qui n'ont qu'une société et aucun lien avec la liste noire ne sont pas dessinées (elles n'apportent
  aucun lien) ; leur nombre figure dans la fiche de la société.

La disposition est calculée ici, réseau par réseau (networkx) ; la page ne charge rien depuis internet.
Filtre « liste noire » : ne garde que les réseaux qui contiennent un élément de la liste noire.
"""
import argparse
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict

import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chaines_dessin as cd  # noqa: E402
import construire_base as cb  # noqa: E402
import geo_maroc as gm  # noqa: E402
import translitteration as tl  # noqa: E402


def construire(base):
    con = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    soc, lignes, par_soc, mentions, participations = cd.charger(con)
    locales = cd.personnes_locales(lignes, par_soc)
    local_de = {p: lid for lid, pids in locales.items() for p in pids}
    etats = cd.etats_roles(lignes, locales, mentions)
    groupes, individu_de, voisins, freq = cd.individus(lignes, locales, soc, etats)
    ent, lien_pers, lien_soc, variantes, dossiers, taille = cd.inscrits(con)
    nb_pers = {sid: len({local_de[p] for p in pids if p in local_de}) for sid, pids in par_soc.items()}

    t0 = time.time()
    # individus et sociétés reliés à la liste noire
    ind_bl = defaultdict(set)              # individu → inscrits (personnes) rattachés, avec le meilleur lien
    lien_ind = {}                          # (inscrit, individu) → (règle, statut, poids, local)
    for pid, liens in lien_pers.items():
        if pid not in local_de:
            continue
        lid = local_de[pid]
        ind = individu_de[lid]
        for eid, regle, statut, poids, conf in liens:
            if ent[eid]['type'] != 'PP':
                continue
            ind_bl[ind].add(eid)
            k = (eid, ind)
            if k not in lien_ind or poids > lien_ind[k][2]:
                lien_ind[k] = (regle, statut, poids, lid)
    soc_bl, soc_emp = defaultdict(set), defaultdict(set)
    for sid, liens in lien_soc.items():
        for eid, regle, statut, poids, nature in liens:
            (soc_emp if nature in ('emploi', 'adresse') else soc_bl)[sid].add(eid)

    # sélection : individus présents dans ≥ 2 sociétés, ou reliés à la liste noire ; sociétés touchées, inscrites,
    # employeurs déclarés, ou associées d'une autre ; toutes les personnes des sociétés reliées à la liste noire
    sids_de = {ind: {lignes[l]['sid'] for l in lids} for ind, lids in groupes.items()}
    inds = {ind for ind, s in sids_de.items() if len(s) >= 2} | set(ind_bl)
    socs = {sid for ind in inds for sid in sids_de[ind]} | set(soc_bl) | set(soc_emp)
    for a, bs in participations.items():
        socs.add(a)
        socs |= bs
    socs_bl = set(soc_bl) | set(soc_emp) | {sid for ind in ind_bl for sid in sids_de[ind]}
    for sid in socs_bl:
        for p in par_soc.get(sid, ()):
            if p in local_de:
                inds.add(individu_de[local_de[p]])
    socs = {s for s in socs if s in soc}

    noeuds, aretes = {}, {}
    for sid in socs:
        s = soc[sid]
        bl = []
        if soc_bl.get(sid):
            bl.append('société inscrite : ' + ', '.join(sorted(ent[e]['nom'] or ent[e]['cle'] for e in soc_bl[sid])))
        if soc_emp.get(sid):
            noms = sorted(ent[e]['nom'] or ent[e]['cle'] for e in soc_emp[sid])
            bl.append('employeur déclaré de ' + ', '.join(noms[:4]) + (f' (+{len(noms) - 4})' if len(noms) > 4 else ''))
        noeuds[f'S{sid}'] = dict(t='societe', nom=cd.nom_soc(s), rc=s['rc'], trib=s['trib'], ville=s['ville'] or s['trib'],
                                 dern=s['dern'], url=s.get('url'), diss=s['diss'], np=nb_pers.get(sid, 0),
                                 bl=' ; '.join(bl))
    ville_soc = {sid: (soc[sid]['ville'] or soc[sid]['trib']) for sid in socs}     # ville du siège, sinon du tribunal
    for ind in inds:
        lids = groupes[ind]
        noms = Counter()
        for l in lids:
            for p in locales[l]:
                noms[lignes[p]['nom']] += 1
        aff = sorted(noms, key=lambda n: (cb.est_arabe(n), -noms[n]))
        bl = ''
        if ind_bl.get(ind):
            bl = 'inscrit : ' + ', '.join(sorted(ent[e]['nom'] or ent[e]['cle'] for e in ind_bl[ind]))
        cin = next((lignes[p]['cin'] for l in lids for p in locales[l] if lignes[p]['cin']), None)
        villes = Counter(ville_soc[s] for s in sids_de[ind] if s in socs and ville_soc.get(s))
        noeuds[f'I{ind}'] = dict(t='personne', nom=' / '.join(aff[:2]), ns=len(sids_de[ind]), cin=cin, bl=bl,
                                 ville=villes.most_common(1)[0][0] if villes else None)
        for l in lids:
            sid = lignes[l]['sid']
            if sid not in socs:
                continue
            e = etats[l]
            ka = (f'I{ind}', f'S{sid}')
            style = '' if e['actuel'] else 'ancien'
            if e['fiab'] < 1:
                style = (style + ' melange').strip()
            aretes[ka] = dict(a=ka[0], b=ka[1], lib=e['lib'], force=round(e['poids'] * e['fiab'] * (soc[sid]['rar'] or 1), 4),
                              style=style)
    for a, bs in participations.items():
        for b in bs:
            if a in socs and b in socs and (f'S{b}', f'S{a}') not in aretes:
                aretes[(f'S{a}', f'S{b}')] = dict(a=f'S{a}', b=f'S{b}', lib='société associée', force=0.5, style='')
    # inscrits (personnes) → individu du registre
    for (eid, ind), (regle, statut, poids, lid) in lien_ind.items():
        e = ent[eid]
        k = 'B:' + e['cle']
        certain = statut in ('alerte', 'confirme')
        n = noeuds.setdefault(k, dict(t='inscrit', nom=e['nom'] or f"(sans nom, CIN {e['cin']})" if e['cin'] else e['nom'] or e['cle'],
                                      cin=e['cin'], listes=e['listes'], motifs=e['motifs'], certain=False, bl='inscrit',
                                      ville=None, _villes=Counter(), _vbl=e['ville']))
        n['certain'] = n['certain'] or certain
        v = noeuds[f'I{ind}'].get('ville')
        if v:
            n['_villes'][v] += 1
        aretes[(k, f'I{ind}')] = dict(a=k, b=f'I{ind}', lib=f"rapprochement {regle} ({'certain' if certain else 'probable'}, poids {poids:.2f})",
                                      force=round(poids, 4), style='certain' if certain else 'rap')
    # ville d'un inscrit : celle de la personne du registre à laquelle il est relié, sinon celle saisie dans la liste noire
    for n in noeuds.values():
        if n['t'] == 'inscrit':
            n['ville'] = n['_villes'].most_common(1)[0][0] if n['_villes'] else n['_vbl']
            del n['_villes'], n['_vbl']
    for n in noeuds.values():
        if n['t'] != 'inscrit':
            n['o'] = 'r'                                   # origine : registre (annonces légales)
    if con.execute("SELECT 1 FROM sqlite_master WHERE name = 'af_identite'").fetchone():
        ajouter_dossiers(con, noeuds, aretes, soc, local_de, individu_de, ent, nb_pers)
    # écriture latine des noms arabes (dictionnaire appris dans la base, règles sinon), affichable à la demande
    tr = tl.charger(con)
    nb_lat = 0
    for n in noeuds.values():
        lat = ' / '.join(x for x in (tr.nom(v) or '' for v in (n['nom'] or '').split(' / ')) if x)
        if lat:
            n['lat'] = lat
            nb_lat += 1
    print(f'  translittération : {nb_lat} nœuds avec un nom arabe ({len(tr.dico)} mots appris)', flush=True)
    print(f'  carte : {len(noeuds)} nœuds ({sum(1 for n in noeuds.values() if n["t"] == "societe")} sociétés, '
          f'{sum(1 for n in noeuds.values() if n["t"] == "personne")} personnes, '
          f'{sum(1 for n in noeuds.values() if n["t"] == "inscrit")} inscrits), {len(aretes)} arêtes '
          f'({time.time() - t0:.0f} s)', flush=True)
    return noeuds, aretes


def ajouter_dossiers(con, noeuds, aretes, soc, local_de, individu_de, ent, nb_pers):
    """Ajoute les personnes et les sociétés des dossiers de l'antifraude (tables af_*). Origine de chaque nœud :
    'r' registre seul, 'd' dossiers seuls, 'rd' les deux (société retrouvée par RC + tribunal, personne par CIN ou
    par son nom dans la même société)."""
    t0 = time.time()
    ident = {r[0]: r for r in con.execute(
        'SELECT identite_id, type_identite, nom, cin_norm, rc_num, tribunal_code, ville_code, nb_dossiers, niveau_cle FROM af_identite')}
    dossiers = defaultdict(list)
    for iid, ref, verdict in con.execute("""SELECT DISTINCT di.identite_id, d.ref, coalesce(d.verdict, 'sans verdict') FROM af_dossier_identite di
                                           JOIN af_dossier d ON d.ref = di.dossier_ref ORDER BY d.recu_le"""):
        dossiers[iid].append(f'{ref} ({verdict.lower().replace("_", " ")})')
    vers_soc, vers_pers = {}, {}
    for iid, cible, cid in con.execute("""SELECT identite_id, cible, cible_id FROM af_lien
                                         WHERE regle IN ('AF03', 'AF03b', 'AF04', 'AF05') AND niveau IN ('certain', 'probable')"""):
        cid = int(cid)
        if cible == 'rc_societe' and cid in soc:
            vers_soc.setdefault(iid, cid)
        elif cible == 'rc_personne' and cid in local_de:
            vers_pers.setdefault(iid, set()).add(individu_de[local_de[cid]])
    bl_de = defaultdict(list)
    for iid, eid, regle, niveau in con.execute("SELECT identite_id, cible_id, regle, niveau FROM af_lien WHERE cible = 'bl_entite' AND regle IN ('AF01', 'AF02', 'AF02b', 'AF02c')"):
        bl_de[iid].append((int(eid), regle, niveau))

    def info(iid):
        d = dossiers.get(iid, [])
        return dict(nd=len(d), dos=', '.join(d[:8]) + (f' (+{len(d) - 8})' if len(d) > 8 else ''))

    cle_soc, cle_pers = {}, {}

    def noeud_soc(iid):
        if iid in cle_soc:
            return cle_soc[iid]
        _i, _t, nom, _c, rc, trib, vil, _n, _niv = ident[iid]
        sid = vers_soc.get(iid)
        if sid is not None:
            k = f'S{sid}'
            if k not in noeuds:
                x = soc[sid]
                noeuds[k] = dict(t='societe', nom=cd.nom_soc(x), rc=x['rc'], trib=x['trib'], ville=x['ville'] or x['trib'], dern=x['dern'],
                                 url=x.get('url'), diss=x['diss'], np=nb_pers.get(sid, 0), bl='')
            noeuds[k]['o'] = 'rd'
            if noeuds[k]['nom'].startswith('(dénomination non lue') and nom:
                noeuds[k]['nom'] = nom
        else:
            k = f'A{iid}'
            noeuds[k] = dict(t='societe', nom=nom or '(société sans nom)', rc=rc, trib=trib, ville=vil or trib, np=0, bl='', o='d')
        noeuds[k].update(info(iid))
        for eid, regle, niveau in bl_de.get(iid, []):
            if eid in ent and ent[eid]['type'] == 'PM':
                txt = 'société inscrite : ' + (ent[eid]['nom'] or ent[eid]['cle']) + f' ({regle}, {niveau})'
                if (ent[eid]['nom'] or ent[eid]['cle']) not in (noeuds[k].get('bl') or ''):
                    noeuds[k]['bl'] = ' ; '.join(x for x in (noeuds[k].get('bl'), txt) if x)
        cle_soc[iid] = k
        return k

    def noeud_pers(iid):
        if iid in cle_pers:
            return cle_pers[iid]
        _i, _t, nom, cin, _rc, _trib, vil, _n, _niv = ident[iid]
        cles = [f'I{ind}' for ind in sorted(vers_pers.get(iid, ())) if f'I{ind}' in noeuds]
        if cles:
            for k in cles:
                noeuds[k]['o'] = 'rd'
                noeuds[k]['cin'] = noeuds[k].get('cin') or cin
                noeuds[k].update(info(iid))
            cle_pers[iid] = cles
            return cles
        k = f'P{iid}'
        noeuds[k] = dict(t='personne', nom=nom or f'(sans nom, CIN {cin})', ns=0, cin=cin, bl='', ville=vil,
                         o='rd' if vers_pers.get(iid) else 'd', **info(iid))
        cle_pers[iid] = [k]
        return [k]

    ROLES = {'gerant': ('gérant', 0.7), 'associe': ('associé', 0.5), 'dirigeant': ('dirigeant', 0.7), 'signataire': ('signataire', 0.3)}
    nb = 0
    for pp, pm, role, qualite, parts, ref in con.execute("""SELECT pp_identite_id, pm_identite_id, role, qualite, parts, dossier_ref FROM af_relation
            WHERE role IN ('gerant', 'associe', 'dirigeant', 'signataire') ORDER BY CASE role WHEN 'gerant' THEN 0 WHEN 'dirigeant' THEN 1 ELSE 2 END"""):
        if ident[pp][8] != 'fort' or ident[pm][8] != 'fort':
            continue                                   # sans CIN ou sans RC + tribunal : pas d'identité sûre, pas de nœud
        ks, lib_role = noeud_soc(pm), ROLES[role]
        for kp in noeud_pers(pp):
            ka = (kp, ks)
            lib = f'{lib_role[0]}' + (f' ({parts} parts)' if parts and role == 'associe' else '') + f' d\'après le dossier {ref}'
            if ka in aretes:
                if 'dossier' not in aretes[ka]['lib']:
                    aretes[ka]['lib'] += f' · confirmé par le dossier {ref}'
                    aretes[ka]['style'] = (aretes[ka]['style'] + ' dossier').strip()
            else:
                aretes[ka] = dict(a=kp, b=ks, lib=lib, force=lib_role[1], style='dossier')
                nb += 1
    # personnes des dossiers qui sont inscrites (même CIN) : nœud de l'inscrit relié par un trait certain
    for iid, liens in bl_de.items():
        if ident[iid][1] != 'PP' or iid not in cle_pers:
            continue
        for eid, regle, niveau in liens:
            if eid not in ent:
                continue
            e = ent[eid]
            kb = 'B:' + e['cle']
            noeuds.setdefault(kb, dict(t='inscrit', nom=e['nom'] or f"(sans nom, CIN {e['cin']})", cin=e['cin'], listes=e['listes'],
                                       motifs=e['motifs'], certain=True, bl='inscrit', ville=ident[iid][6] or e['ville']))
            noeuds[kb]['certain'] = True
            for kp in cle_pers[iid]:
                noeuds[kp]['bl'] = noeuds[kp].get('bl') or ('inscrit : ' + (e['nom'] or e['cle']))
                aretes.setdefault((kb, kp), dict(a=kb, b=kp, lib=f'rapprochement {regle} (certain, même CIN, dossier)', force=1.0, style='certain'))
    nb_soc = Counter(a for (a, b) in aretes if a.startswith('P'))
    for k, n in noeuds.items():
        if k.startswith('P'):
            n['ns'] = nb_soc.get(k, 0)
    c = Counter(n.get('o') for n in noeuds.values() if n['t'] != 'inscrit')
    print(f"  dossiers : {c['d']} nœuds venus des dossiers seuls, {c['rd']} communs au registre et aux dossiers, {c['r']} du registre seul ; "
          f'{nb} liens ajoutés ({time.time() - t0:.0f} s)', flush=True)


def disposer(noeuds, aretes):
    t0 = time.time()
    g = nx.Graph()
    g.add_nodes_from(noeuds)
    for (u, v), a in aretes.items():
        g.add_edge(u, v, weight=0.5 + a['force'])
    # réseaux qui contiennent un élément de la liste noire d'abord, puis par taille
    comps = sorted(nx.connected_components(g),
                   key=lambda c: (not any(noeuds[k].get('bl') for k in c), -len(c), min(c)))
    boites = []
    for c in comps:
        n = len(c)
        if n == 1:
            boites.append((16.0, {next(iter(c)): (0.0, 0.0)}, c))
            continue
        sg = g.subgraph(c)
        if n <= 3:
            p = nx.circular_layout(sg)
        else:
            p = nx.spring_layout(sg, k=2.0 / math.sqrt(n), iterations=60 if n > 300 else 150, seed=7, weight='weight')
        xs, ys = [q[0] for q in p.values()], [q[1] for q in p.values()]
        cx, cy = sum(xs) / n, sum(ys) / n
        scale = 34 * math.sqrt(n) if n > 3 else 28
        p = {k_: ((q[0] - cx) * scale, (q[1] - cy) * scale) for k_, q in p.items()}
        r = max(math.hypot(x, y) for x, y in p.values()) + 26
        boites.append((r, p, c))
    # rangement en lignes, du plus gros au plus petit : d'abord le bloc des réseaux de la liste noire, compact en
    # haut à gauche, puis le reste du registre en dessous, dans un rectangle de proportion écran
    pos = {}

    def ranger(bloc, y0, largeur_max):
        x, y, hauteur_ligne = 0.0, y0, 0.0
        for r, p, c in bloc:
            d = 2 * r + 20
            if x + d > largeur_max and x > 0:
                x, y, hauteur_ligne = 0.0, y + hauteur_ligne, 0.0
            for k_, (px, py) in p.items():
                pos[k_] = (round(x + r + px, 1), round(y + r + py, 1))
            x += d
            hauteur_ligne = max(hauteur_ligne, d)
        return y + hauteur_ligne
    bl = [b for b in boites if any(noeuds[k].get('bl') for k in b[2])]
    autres = [b for b in boites if not any(noeuds[k].get('bl') for k in b[2])]
    aire_bl = sum((2 * r + 20) ** 2 for r, _, _ in bl)
    aire = sum((2 * r + 20) ** 2 for r, _, _ in autres)
    fin_bl = ranger(bl, 0.0, math.sqrt(aire_bl * 1.6)) if bl else 0.0
    ranger(autres, fin_bl + 120, math.sqrt(aire * 1.7))
    print(f'  disposition : {len(comps)} réseaux, le plus grand {len(comps[0])} nœuds ({time.time() - t0:.0f} s)', flush=True)
    comp_de = {}
    for i, (_r, _p, c) in enumerate(boites):
        for k_ in c:
            comp_de[k_] = i
    return pos, comp_de, [len(c) for c in comps]


def disposer_maroc(noeuds, pos, comp_de):
    """Deuxième disposition : chaque nœud à sa ville sur la carte du Maroc. Dans le disque d'une ville, les nœuds
    d'un même réseau restent groupés (leur dessin de réseau, réduit) ; les blocs sont rangés en tournesol, les plus
    gros au centre. Les nœuds sans ville connue vont dans une zone à droite de la carte."""
    t0 = time.time()
    par_ville = defaultdict(lambda: defaultdict(list))        # ville → réseau → nœuds
    for k, n in noeuds.items():
        v = n.get('ville') if n.get('ville') in gm.VILLES else None
        par_ville[v or '__cote__'][comp_de[k]].append(k)
    disques = {}
    for v, grp in par_ville.items():
        n = sum(len(x) for x in grp.values())
        if v == '__cote__':
            continue
        x, y = gm.monde(*gm.VILLES[v])
        disques[v] = [x, y, gm.rayon_ville(n)]
    gm.ecarter(disques)
    # zone « sans ville » : à droite de la carte (à l'est de la frontière), hauteur de Rabat
    nb_cote = sum(len(x) for x in par_ville.get('__cote__', {}).values())
    r_cote = max(60.0, min(160.0, 3.0 * nb_cote ** 0.4))
    disques['__cote__'] = [gm.monde(33.0, -1.0)[0] + 70 + r_cote, gm.monde(33.0, -1.0)[1], r_cote]
    mpos = {}
    for v, grp in par_ville.items():
        cx, cy, rv = disques[v]
        blocs = sorted(grp.values(), key=len, reverse=True)
        aires = [len(b) for b in blocs]
        echelle = rv * math.sqrt(0.72 / max(1, sum(aires)))        # rayon d'un bloc = échelle × √n
        for (bx, by), b in zip(gm.tournesol(aires, rv), blocs):
            if len(b) == 1:
                mpos[b[0]] = (round(cx + bx, 1), round(cy + by, 1))
                continue
            rb = echelle * math.sqrt(len(b))
            xs = [pos[k][0] for k in b]; ys = [pos[k][1] for k in b]
            mx, my = sum(xs) / len(b), sum(ys) / len(b)
            etendue = max(math.hypot(x - mx, y - my) for x, y in zip(xs, ys)) or 1.0
            f = rb * 0.9 / etendue
            for k, x, y in zip(b, xs, ys):
                mpos[k] = (round(cx + bx + (x - mx) * f, 1), round(cy + by + (y - my) * f, 1))
    villes = [dict(code=v, nom=v.title(), x=round(d[0], 1), y=round(d[1], 1), r=round(d[2], 1),
                   n=sum(len(x) for x in par_ville[v].values()),
                   bl=sum(1 for grp in par_ville[v].values() for k in grp if noeuds[k].get('bl')),
                   lat=gm.VILLES[v][0], lon=gm.VILLES[v][1]) for v, d in disques.items() if v != '__cote__']
    cote = dict(x=round(disques['__cote__'][0], 1), y=round(disques['__cote__'][1], 1), r=round(r_cote, 1), n=nb_cote)
    print(f'  carte du Maroc : {len(villes)} villes, {nb_cote} nœuds sans ville ({time.time() - t0:.0f} s)', flush=True)
    return mpos, villes, cote


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default='bl_rc.sqlite')
    ap.add_argument('--html', default='Carte_globale_liste_noire.html')
    ap.add_argument('--json', help='Écrire aussi les données en JSON')
    a = ap.parse_args()
    t0 = time.time()
    noeuds, aretes = construire(a.base)
    pos, comp_de, tailles = disposer(noeuds, aretes)
    mpos, villes, cote = disposer_maroc(noeuds, pos, comp_de)
    degre = Counter()
    for u, v in aretes:
        degre[u] += 1
        degre[v] += 1
    # réseaux qui contiennent un élément de la liste noire
    comp_bl = {comp_de[k] for k, n in noeuds.items() if n.get('bl')}
    ids = list(noeuds)
    index = {k: i for i, k in enumerate(ids)}
    sortie = dict(
        noeuds=[dict(id=k, x=pos[k][0], y=pos[k][1], mx=mpos[k][0], my=mpos[k][1], deg=degre[k], c=comp_de[k], **noeuds[k]) for k in ids],
        aretes=[dict(a=index[x['a']], b=index[x['b']], lib=x['lib'], force=x['force'], style=x['style'])
                for x in aretes.values()],
        reseaux=tailles, reseaux_bl=sorted(comp_bl),
        geo=dict(villes=villes, cote=cote, regions=gm.contour(), echelle=[gm.ECHELLE_X, gm.ECHELLE_Y]),
        construction=time.strftime('%d/%m/%Y'),
    )
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(sortie, f, ensure_ascii=False)
    modele = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carte_globale_modele.html')
    with open(modele, encoding='utf-8') as f:
        page = f.read()
    with open(a.html, 'w', encoding='utf-8') as f:
        f.write(page.replace('/*__DONNEES__*/null', json.dumps(sortie, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')))
    print(f'  Carte : {a.html} ({os.path.getsize(a.html) / 1e6:.1f} Mo) · terminé en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
