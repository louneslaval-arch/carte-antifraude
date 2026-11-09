#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chaines_dessin.py — chaînes du dessin du 22/10/2026, sur les vraies données :

    PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3

    PM n°1 est à 1 arête de l'inscrit, PP n°2 à 2, PM n°2 à 3, PP n°3 à 4.
    Une société associée d'une autre (participation) relie aussi deux sociétés en une arête.

Une personne du registre n'a pas d'identifiant (l'export ne porte quasiment pas de CIN). On la reconnaît ainsi :
  - dans une même société : même nom (ordre des mots indifférent), ou même nom écrit en latin et en arabe
    (mêmes consonnes, mêmes voyelles longues, mêmes coupures entre les mots) ;
  - d'une société à l'autre : même CIN, ou même nom + même ville du siège quand ce nom figure dans 5 sociétés au
    plus. Un nom plus courant ne sert jamais de pont : deux « MOHAMED ALAMI » ne sont pas la même personne.

Chaque chaîne porte :
  - fiabilité : rapprochement inscrit ↔ registre × passages d'une société à l'autre (1 pour un CIN,
    0,8 × n^-0,5 pour un même nom + même ville, n = nombre de sociétés qui portent ce nom) ;
  - force : fiabilité × poids des rôles (gérant 0,7, associé 0,3 à 0,7 selon les parts…) × rareté de la taille
    de la société, comme dans la carte.

  python3 chaines_dessin.py --base bl_rc.sqlite --excel Chaines_liste_noire_RC.xlsx --html Carte_chaines.html
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import construire_base as cb  # noqa: E402

ROLES_FR = {'gerant': 'gérant', 'administrateur': 'administrateur', 'associe': 'associé', 'liquidateur': 'liquidateur',
            'gerant_sortant': 'ancien gérant', 'associe_sortant': 'ancien associé', 'cessionnaire': 'cessionnaire',
            'cedant': 'cédant', 'representant': 'représentant', 'inconnu': 'cité'}
MOTS_DEPOSANT = {'CABINET', 'FIDUCIAIRE', 'FIDUCIARE', 'COMPTA', 'COMPTABLE', 'COMPTABILITE', 'DOMICILIATION',
                 'JURIC', 'JURIDIQUE', 'AVOCAT', 'NOTAIRE', 'MAITRE'}
PONT_MAX = 5            # un nom présent dans plus de 5 sociétés ne relie jamais deux sociétés
PERSONNES_MAX = 25      # société trop grande (SA, coopérative) : on ne passe pas par ses membres
SOCIETES_MAX = 15       # personne présente dans trop de sociétés (fiduciaire, liquidateur de métier) : pas de passage
PROFONDEUR = 4
CHEMINS_PAR_CIBLE = 5


# ---- identité des personnes du registre ---------------------------------------------------------------------
def cle_personne(nom):
    """Nom sans ordre des mots : article retiré, graphies ramenées (ال / لا, ة / ه, prénoms usuels)."""
    if not nom:
        return None
    toks = []
    if cb.est_arabe(nom):
        for m in cb.latin_maj(nom).split():
            if not cb.est_arabe(m):
                continue
            if m.startswith('ال') and len(m) > 3 and m not in cb.NON_ARTICLE_AR:
                m = m[2:]
            m = cb.ar_simple(m).replace('ا', '').replace('ء', '')
            if len(m) >= 2:
                toks.append(m)
    else:
        toks = [cb.article_colle(m) or m for m in cb.mots_nom_latin(nom)]
    return ' '.join(sorted(toks)) if len(toks) >= 2 else None


def _jetons_arabes(nom):
    sortie = []
    for m in cb.latin_maj(nom).split():
        if not cb.est_arabe(m):
            continue
        feminin = m.endswith('ة')
        if m.startswith('ال') and len(m) > 3 and m not in cb.NON_ARTICLE_AR:
            m = m[2:]
        m = cb.ar_simple(m)
        if len(m) >= 2:
            sortie.append((m, feminin))
    return sortie


def _mots_proches(x, y):
    """Deux mots d'un nom : identiques ; ou mêmes lettres à des lettres sœurs près (اصيل / اسيل, ص / س) ; ou une lettre
    d'écart sur un mot long (زغلول / زغلو, جاموس / دجاموس). Sinon les mots courts doivent être identiques :
    سعيد ≠ سعد, حسن ≠ حسين, عمر ≠ عمار."""
    if x == y:
        return True
    if len(x) == len(y) and all(a == b or (a in cb._SQ_AR and cb._SQ_AR.get(a) == cb._SQ_AR.get(b))
                                for a, b in zip(x, y)):
        return True
    return min(len(x), len(y)) >= 4 and max(len(x), len(y)) >= 5 and cb._ratio(x, y) >= 0.85


def arabes_proches(a, b):
    """Deux graphies arabes du même nom : même nombre de mots, au moins un mot identique, les autres proches,
    pas d'écart masculin / féminin (سعيد / سعيدة)."""
    ta, tb = _jetons_arabes(a), _jetons_arabes(b)
    if len(ta) < 2 or len(ta) != len(tb):
        return False
    restants, identique = list(tb), False
    for x, fx in ta:
        k = max(range(len(restants)), key=lambda i: (restants[i][0] == x, cb._ratio(x, restants[i][0])))
        y, fy = restants.pop(k)
        if fx != fy or not _mots_proches(x, y):
            return False
        identique |= x == y
    return identique


def latins_proches(a, b):
    """Deux graphies latines du même nom : même nombre de mots, chacun très proche (sans SAID / SAIDA)."""
    ma, mb = cb.mots_nom_latin(a), cb.mots_nom_latin(b)
    if len(ma) < 2 or len(ma) != len(mb):
        return False
    return all(any(_mots_proches(x, y) and not cb._formes_distinctes(x, y) for y in mb) for x in ma)


class Unions:
    def __init__(self):
        self.p = {}

    def racine(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def unir(self, a, b):
        ra, rb = self.racine(a), self.racine(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def charger(con):
    t0 = time.time()
    soc = {}
    for sid, den, rc, trib, ville, prem, dern, diss, nbp, rar in con.execute(
            """SELECT societe_id, denomination, rc_num, tribunal_code, ville_code, premiere_publication,
                      derniere_publication, dissoute, nb_personnes, rarete_taille FROM rc_societe"""):
        soc[sid] = dict(den=den, rc=rc, trib=trib, ville=ville, prem=prem, dern=dern, diss=diss, nbp=nbp or 0,
                        rar=rar or 1.0)
    for sid, url, date in con.execute("""SELECT societe_id, url, date_publication FROM rc_annonce
                                         WHERE url IS NOT NULL ORDER BY date_publication"""):
        if sid in soc:
            soc[sid]['url'] = url                   # la plus récente l'emporte
    # nom affiché qui est celui du cabinet ou du domiciliataire qui a déposé l'annonce (« CABINET X 286 BD … »)
    for sid, titre in con.execute("""SELECT DISTINCT societe_id, titre FROM rc_annonce WHERE titre IS NOT NULL"""):
        s = soc.get(sid)
        if s and s['den'] and not s.get('deposant') and set(cb.latin_maj(s['den']).split()) & MOTS_DEPOSANT:
            a, b = cb.cle_rs(s['den']) or '', cb.cle_rs(titre) or ''
            if a and b and (a == b or cb._ratio(a, b) >= 0.8 or a in b or b in a):
                s['deposant'] = True
    lignes = {}
    par_soc = defaultdict(list)
    ecartees = 0
    for pid, sid, typ, nom, ecr, cin, role, roles, poids, pct, sortant, fiab, prem, dern in con.execute(
            """SELECT personne_id, societe_id, type_personne, nom_complet, ecriture, cin_norm, role, roles, poids_role,
                      pct, sortant, fiabilite, premiere_mention, derniere_mention
               FROM rc_personne WHERE type_personne = 'PP' AND nom_complet IS NOT NULL"""):
        mots = cb.mots_nom_nettoyes(nom)
        if cb.motif_rejet_nom(mots):                           # bout de phrase lu comme un nom (listes à jour)
            ecartees += 1
            continue
        if not cb.est_arabe(nom) or len(mots) < len(nom.split()):
            nom = ' '.join(mots) if cb.est_arabe(nom) else nom      # « عيسى الروزي الف » → « عيسى الروزي »
        lignes[pid] = dict(sid=sid, nom=nom, ecr=ecr, cin=cin, role=role, roles=roles, poids=poids or 0.3, pct=pct,
                           sortant=sortant, fiab=fiab or 1.0, prem=prem, dern=dern, cle=cle_personne(nom))
        par_soc[sid].append(pid)
    participations = defaultdict(set)          # société associée d'une autre : arête société – société
    for sid, cible in con.execute("""SELECT p.societe_id, r.societe_id FROM rc_participation r
                                     JOIN rc_personne p ON p.personne_id = r.personne_id"""):
        if sid != cible:
            participations[sid].add(cible)
            participations[cible].add(sid)
    print(f'  registre : {len(soc)} sociétés, {len(lignes)} personnes citées, {ecartees} noms écartés '
          f'({time.time() - t0:.0f} s)', flush=True)
    return soc, lignes, par_soc, participations


def personnes_locales(lignes, par_soc):
    """Dans chaque société : lignes qui désignent la même personne (même nom sans ordre, ou latin ↔ arabe)."""
    t0 = time.time()
    u = Unions()
    fusions = Counter()
    for sid, pids in par_soc.items():
        if len(pids) < 2:
            continue
        par_cle = defaultdict(list)
        for p in pids:
            if lignes[p]['cle']:
                par_cle[lignes[p]['cle']].append(p)
        for groupe in par_cle.values():
            for p in groupe[1:]:
                u.unir(groupe[0], p)
                fusions['même nom'] += 1
        lat = [p for p in pids if lignes[p]['ecr'] == 'latin']
        ar = [p for p in pids if lignes[p]['ecr'] == 'arabe']
        for a in ar:
            for b in lat:
                if u.racine(a) != u.racine(b) and cb.profils_compatibles(lignes[b]['nom'], lignes[a]['nom']):
                    u.unir(a, b)
                    fusions['latin ↔ arabe'] += 1
        for i, a in enumerate(lat):
            for b in lat[i + 1:]:
                if u.racine(a) != u.racine(b) and latins_proches(lignes[a]['nom'], lignes[b]['nom']):
                    u.unir(a, b)
                    fusions['variante latine'] += 1
        for i, a in enumerate(ar):
            for b in ar[i + 1:]:
                if u.racine(a) != u.racine(b) and arabes_proches(lignes[a]['nom'], lignes[b]['nom']):
                    u.unir(a, b)
                    fusions['variante arabe'] += 1
    locales = defaultdict(list)
    for pid in lignes:
        locales[u.racine(pid)].append(pid)
    print(f"  personnes par société : {len(lignes)} lignes → {len(locales)} personnes "
          f"({', '.join(f'{k} {v}' for k, v in fusions.items())}) ({time.time() - t0:.0f} s)", flush=True)
    return locales           # id local (plus petit personne_id) → lignes


def individus(lignes, locales, soc):
    """D'une société à l'autre : même CIN, ou même nom + même ville quand le nom est rare (≤ PONT_MAX sociétés)."""
    t0 = time.time()
    freq = defaultdict(set)
    for pid, l in lignes.items():
        if l['cle']:
            freq[l['cle']].add(l['sid'])
    freq = {k: len(v) for k, v in freq.items()}
    u = Unions()
    ponts = defaultdict(list)              # (cle, ville) ou CIN → personnes locales
    for lid, pids in locales.items():
        u.racine(lid)
        ville = soc[lignes[lid]['sid']]['ville']
        for p in pids:
            l = lignes[p]
            if l['cin']:
                ponts[('CIN', l['cin'])].append(lid)
            if l['cle'] and ville and freq.get(l['cle'], 0) <= PONT_MAX:
                ponts[('NOM', l['cle'], ville)].append(lid)
    voisins = defaultdict(dict)           # pont direct entre deux personnes locales : (poids, motif)
    for k, lids in ponts.items():
        lids = sorted(set(lids))
        if len(lids) < 2:
            continue
        if k[0] == 'CIN':
            poids, motif = 1.0, f'même CIN {k[1]}'
        else:
            n = freq[k[1]]
            poids, motif = 0.8 * n ** -0.5, f'même nom + même ville ({k[2]}), nom présent dans {n} sociétés'
        for a in lids:
            for b in lids:
                if a != b and poids > voisins[a].get(b, (0, ''))[0]:
                    voisins[a][b] = (poids, motif)
        for b in lids[1:]:
            u.unir(lids[0], b)
    groupes = defaultdict(list)
    for lid in locales:
        groupes[u.racine(lid)].append(lid)
    tailles = Counter(min(len(g), 6) for g in groupes.values())
    repartition = ', '.join(('6+' if k == 6 else str(k)) + f':{v}' for k, v in sorted(tailles.items()))
    print(f'  individus : {len(locales)} personnes → {len(groupes)} individus ; présents dans 1, 2, 3… sociétés : '
          f'{repartition} ({time.time() - t0:.0f} s)', flush=True)
    individu_de = {lid: g for g, lids in groupes.items() for lid in lids}
    return groupes, individu_de, voisins, freq


def meilleur_pont(voisins, depart, arrivee, membres):
    """Passage d'une personne locale à une autre du même individu : produit des ponts sur le meilleur chemin."""
    if depart == arrivee:
        return 1.0, []
    meilleur = {depart: (1.0, [])}
    file = deque([depart])
    while file:
        x = file.popleft()
        px, mx = meilleur[x]
        for y, (p, m) in voisins.get(x, {}).items():
            if y in membres and px * p > meilleur.get(y, (0, None))[0]:
                meilleur[y] = (px * p, mx + [m])
                file.append(y)
    return meilleur.get(arrivee, (0.0, ['pas de pont']))


# ---- inscrits et drapeaux -------------------------------------------------------------------------------------
def inscrits(con):
    ent = {}
    for r in con.execute("""SELECT entite_id, cle_entite, type_entite, nom_affiche, cin, ville_code, employeur,
                                   types_liste, types_fraude, motifs, nb_inscriptions, derniere_saisie
                            FROM bl_entite"""):
        ent[r[0]] = dict(zip(('id', 'cle', 'type', 'nom', 'cin', 'ville', 'employeur', 'listes', 'fraudes', 'motifs',
                              'nb', 'saisie'), r))
    variantes = defaultdict(list)      # nom + prénom de l'inscrit, dans les deux ordres
    for eid, nom, prenom in con.execute('SELECT entite_id, nom, prenom FROM bl_inscription'):
        for v in ([f'{nom} {prenom}', f'{prenom} {nom}'] if nom and prenom else [nom or prenom]):
            if v and v not in variantes[eid]:
                variantes[eid].append(v)
    lien_pers = defaultdict(list)      # personne_id → [(entité, règle, statut, poids)]
    lien_soc = defaultdict(list)       # societe_id → [(entité, règle, statut, poids, nature)]
    for eid, objet, oid, regle, statut, poids, nature, conf in con.execute(
            """SELECT bl_entite_id, rc_objet, rc_objet_id, regle, statut, poids, nature, confirmation
               FROM correspondance WHERE statut NOT IN ('faible', 'ecarte')"""):
        if objet == 'rc_personne':
            lien_pers[oid].append((eid, regle, statut, poids, conf))
        else:
            lien_soc[oid].append((eid, regle, statut, poids, nature))
    return ent, lien_pers, lien_soc, variantes


# ---- parcours -------------------------------------------------------------------------------------------------
def parcourir(eid, ctx, depart_lignes=None, depart_socs=None):
    """Chemins les plus courts (≤ PROFONDEUR arêtes) depuis un inscrit.
    - personne inscrite : depart_lignes {personne_id: (règle, statut, poids, confirmation)} ; la 1re arête mène à ses
      sociétés (PM n°1 du dessin) ;
    - société inscrite : depart_socs {societe_id: (règle, statut, poids, confirmation)} ; la société du registre est le
      point de départ (distance 0), la 1re arête mène à ses dirigeants et associés.
    Renvoie {noeud: (distance, [chemins])} ; un chemin = liste d'étapes (pour une société inscrite, la 1re étape est
    le point de départ lui-même)."""
    lignes, locales, individu_de, groupes, voisins, soc, par_soc, participations = (
        ctx['lignes'], ctx['locales'], ctx['individu_de'], ctx['groupes'], ctx['voisins'], ctx['soc'],
        ctx['par_soc'], ctx['participations'])
    local_de = ctx['local_de']
    dist, resultats, frontiere = {}, defaultdict(list), []
    ind_depart, cache_soi = set(), {}
    soi_ar, soi_lat = set(), set()

    def est_soi(lid):
        """L'inscrit lui-même sous une autre graphie (« جاموس » / « دجاموس ») ne revient pas en PP n°2 ou n°3."""
        if not depart_lignes:
            return False
        if lid not in cache_soi:
            r = False
            for p in locales[lid]:
                n = lignes[p]['nom']
                if lignes[p]['ecr'] == 'arabe':
                    r = (any(arabes_proches(n, x) for x in soi_ar)
                         or any(cb.profils_compatibles(v, n) for v in ctx['variantes'].get(eid, [])))
                else:
                    r = any(latins_proches(n, x) for x in soi_lat)
                if r:
                    break
            cache_soi[lid] = r
        return cache_soi[lid]

    if depart_lignes:
        locaux_directs = {}
        for pid, m in depart_lignes.items():
            lid = local_de[pid]
            if lid not in locaux_directs or m[2] > locaux_directs[lid][2]:
                locaux_directs[lid] = m
        ind_depart = {individu_de[lid] for lid in locaux_directs}
        soi = [lignes[p] for ind in ind_depart for lid in groupes[ind] for p in locales[lid]]
        soi_ar = {l['nom'] for l in soi if l['ecr'] == 'arabe'}
        soi_lat = {l['nom'] for l in soi if l['ecr'] != 'arabe'} | set(ctx['variantes'].get(eid, []))
        # 1re arête : sociétés de l'inscrit (rapprochement direct, ou même individu par CIN / nom + ville)
        for ind in ind_depart:
            membres = set(groupes[ind])
            for lid in groupes[ind]:
                sid = lignes[lid]['sid']
                best = None
                for d, (regle, statut, poids, conf) in locaux_directs.items():
                    if d not in membres:
                        continue
                    pp, motifs = meilleur_pont(voisins, d, lid, membres)
                    if best is None or poids * pp > best[0]:
                        best = (poids * pp, regle, statut, poids, conf, motifs, d)
                if best is None:
                    continue
                l = ligne_role(lignes, locales[lid])
                etape = dict(type='S', sid=sid, role=l['role'], roles=l['roles'], pct=l['pct'], local=lid,
                             fiab=best[0], force=best[0] * arete(l, soc[sid]), regle=best[1], statut=best[2],
                             rapprochement=best[3], confirmation=best[4], pont=best[5],
                             nom_registre=lignes[best[6]]['nom'])
                ajouter(('S', sid), [etape], 1, dist, resultats, frontiere)
        premiere = 2
    else:
        for sid, (regle, statut, poids, conf) in depart_socs.items():
            etape = dict(type='S', sid=sid, role='depart', roles='', pct=None, local=None, fiab=poids, force=poids,
                         regle=regle, statut=statut, rapprochement=poids, confirmation=conf, pont=[],
                         nom_registre=soc[sid]['den'])
            ajouter(('S', sid), [etape], 0, dist, resultats, frontiere)
        premiere = 1
    # arêtes suivantes : largeur d'abord, chemins les plus courts seulement
    for profondeur in range(premiere, PROFONDEUR + 1):
        suivante = []
        for noeud, chemin in frontiere:
            dernier = chemin[-1]
            if noeud[0] == 'S':
                sid = noeud[1]
                if soc[sid]['nbp'] > PERSONNES_MAX:
                    continue
                for lid in sorted({local_de[p] for p in par_soc.get(sid, ())}):
                    ind = individu_de[lid]
                    if ind in ind_depart or est_soi(lid):
                        continue
                    n2 = ('I', ind)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    l = ligne_role(lignes, locales[lid])
                    etape = dict(type='I', ind=ind, local=lid, nom=nom_affiche(lignes, locales[lid]), role=l['role'],
                                 roles=l['roles'], pct=l['pct'], sid_depuis=sid,
                                 fiab=dernier['fiab'], force=dernier['force'] * arete(l, soc[sid]))
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
                for cible in sorted(participations.get(sid, ())):
                    n2 = ('S', cible)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    etape = dict(type='S', sid=cible, role='participation', roles='société associée', pct=None,
                                 local=None, fiab=dernier['fiab'], force=dernier['force'] * 0.5, pont=[])
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
            else:
                ind = noeud[1]
                membres = set(groupes[ind])
                if len(membres) > SOCIETES_MAX:
                    continue
                for lid in groupes[ind]:
                    if lid == dernier['local']:
                        continue
                    sid = lignes[lid]['sid']
                    n2 = ('S', sid)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    pp, motifs = meilleur_pont(voisins, dernier['local'], lid, membres)
                    l = ligne_role(lignes, locales[lid])
                    etape = dict(type='S', sid=sid, role=l['role'], roles=l['roles'], pct=l['pct'], local=lid,
                                 fiab=dernier['fiab'] * pp, force=dernier['force'] * pp * arete(l, soc[sid]),
                                 pont=motifs)
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
        frontiere = suivante
    sortie = {}
    for n, chemins in resultats.items():
        if dist[n] == 0:
            continue
        vus, garde = set(), []
        for ch in sorted(chemins, key=lambda c: -c[-1]['force']):
            signature = tuple((e['type'], e.get('sid') or e.get('ind'), e['role']) for e in ch)
            if signature not in vus:
                vus.add(signature)
                garde.append(ch)
        sortie[n] = (dist[n], garde[:CHEMINS_PAR_CIBLE])
    return sortie


def ajouter(noeud, chemin, profondeur, dist, resultats, suivante):
    if noeud not in dist:
        dist[noeud] = profondeur
        suivante.append((noeud, chemin))
    if dist[noeud] == profondeur:
        resultats[noeud].append(chemin)


def ligne_role(lignes, pids):
    """Ligne la plus forte d'une personne locale (rôle le plus lourd)."""
    return max((lignes[p] for p in pids), key=lambda l: l['poids'])


def nom_affiche(lignes, pids):
    noms = sorted({lignes[p]['nom'] for p in pids}, key=lambda n: (cb.est_arabe(n), n))
    return ' / '.join(noms[:2])


def arete(l, s):
    return (l['poids'] or 0.3) * (s['rar'] or 1.0) * (l['fiab'] or 1.0)


# ---- programme ------------------------------------------------------------------------------------------------
def calculer(base):
    con = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    soc, lignes, par_soc, participations = charger(con)
    locales = personnes_locales(lignes, par_soc)
    local_de = {p: lid for lid, pids in locales.items() for p in pids}
    groupes, individu_de, voisins, freq = individus(lignes, locales, soc)
    ent, lien_pers, lien_soc, variantes = inscrits(con)
    ctx = dict(lignes=lignes, locales=locales, local_de=local_de, individu_de=individu_de, groupes=groupes,
               voisins=voisins, soc=soc, par_soc=par_soc, participations=participations, variantes=variantes)
    # drapeaux : individus et sociétés reliés à la liste noire
    inscrits_ind = defaultdict(set)
    for pid, liens in lien_pers.items():
        if pid in local_de:
            for eid, *_ in liens:
                inscrits_ind[individu_de[local_de[pid]]].add(eid)
    inscrits_soc, employeur_de = defaultdict(set), defaultdict(set)
    departs_soc = defaultdict(dict)
    for sid, liens in lien_soc.items():
        for eid, regle, statut, poids, nature in liens:
            if nature in ('emploi', 'adresse'):
                employeur_de[sid].add(eid)
                continue
            inscrits_soc[sid].add(eid)
            if ent[eid]['type'] == 'PM' and (sid not in departs_soc[eid] or poids > departs_soc[eid][sid][2]):
                departs_soc[eid][sid] = (regle, statut, poids, None)
    # départs : inscrits personnes rapprochées d'une personne du registre, sociétés inscrites retrouvées
    departs = defaultdict(dict)
    for pid, liens in lien_pers.items():
        if pid not in lignes:
            continue
        for eid, regle, statut, poids, conf in liens:
            if ent[eid]['type'] == 'PP' and (pid not in departs[eid] or poids > departs[eid][pid][2]):
                departs[eid][pid] = (regle, statut, poids, conf)
    t0 = time.time()
    res = {eid: ('PP', parcourir(eid, ctx, depart_lignes=d)) for eid, d in departs.items()}
    res.update({eid: ('PM', parcourir(eid, ctx, depart_socs=d)) for eid, d in departs_soc.items()})
    print(f'  départs parcourus : {len(departs)} personnes inscrites, {len(departs_soc)} sociétés inscrites '
          f'({time.time() - t0:.0f} s)', flush=True)
    return dict(con=con, soc=soc, lignes=lignes, locales=locales, groupes=groupes, ent=ent, res=res,
                inscrits_ind=inscrits_ind, inscrits_soc=inscrits_soc, employeur_de=employeur_de, freq=freq,
                departs_soc=departs_soc)


def drapeau_soc(d, sid, eid):
    x = []
    autres = d['inscrits_soc'].get(sid, set()) - {eid}
    if autres:
        cle = cb.cle_rs(d['soc'][sid]['den'] or '') or ''
        noms = sorted(d['ent'][e]['nom'] for e in autres)
        if all(cle and cb._ratio(cle, cb.cle_rs(n) or '') >= 0.8 for n in noms):
            x.append('société inscrite')
        else:
            x.append('société inscrite : ' + ', '.join(noms))
    emp = d['employeur_de'].get(sid, set()) - {eid}
    if emp:
        noms = sorted(d['ent'][e]['nom'] for e in emp)
        x.append('employeur déclaré de ' + ', '.join(noms[:5]) + (f' (+{len(noms) - 5})' if len(noms) > 5 else ''))
    return ' ; '.join(x)


def drapeau_ind(d, ind, eid, nom=None):
    autres = d['inscrits_ind'].get(ind, set()) - {eid}
    if not autres:
        return ''
    noms = sorted(d['ent'][e]['nom'] for e in autres)
    if nom and not cb.est_arabe(nom) and all(cle_personne(n) == cle_personne(nom) for n in noms):
        return 'inscrit'                         # même nom écrit pareil : inutile de le répéter
    return 'inscrit : ' + ', '.join(noms)


def role_txt(e):
    if e['role'] == 'participation':
        return 'associée de'
    r = ROLES_FR.get(e['role'], e['role'] or '')
    if e.get('pct') is not None and e['role'] in ('associe', 'associe_sortant', 'cessionnaire'):
        r += f" ({e['pct']:g} %)"
    return r


def nom_soc(s):
    if not s['den']:
        return '(dénomination non lue)'
    return s['den'] + (' (nom du déposant de l\'annonce ?)' if s.get('deposant') else '')


def isole(nom, oui):
    """Nom arabe isolé du texte latin qui l'entoure (sinon le navigateur réordonne la ligne)."""
    return f'\u2068{nom}\u2069' if oui and cb.est_arabe(nom) else nom


def decrire(d, eid, typ, ch, isoler=False):
    """Étapes d'un chemin, prêtes à afficher : [(arête, noeud)] + texte compact + éléments de liste noire touchés."""
    etapes = ch if typ == 'PP' else ch[1:]
    e = d['ent'][eid]
    if typ == 'PP':
        texte = [f"{e['nom']} (inscrit)"]
    else:
        s0 = d['soc'][ch[0]['sid']]
        texte = [f"{isole(nom_soc(s0), isoler)} [société inscrite, RC {s0['rc'] or '?'} {s0['trib'] or ''}]".replace(' ]', ']')]
    sortie, alertes = [], []
    for k, et in enumerate(etapes, start=1):
        if et['type'] == 'S':
            s = d['soc'][et['sid']]
            noeud = dict(type='société', nom=nom_soc(s), rc=s['rc'], trib=s['trib'], ville=s['ville'], dern=s['dern'],
                         url=s.get('url'), bl=drapeau_soc(d, et['sid'], eid))
            lib = role_txt(et)
            texte.append(f"–{lib}– {isole(noeud['nom'], isoler)}" + (f" [RC {s['rc']}]" if s['rc'] else ''))
        else:
            noeud = dict(type='personne', nom=et['nom'], bl=drapeau_ind(d, et['ind'], eid, et['nom']))
            lib = role_txt(et)
            texte.append(f"–{lib}– {isole(et['nom'], isoler)}")
        if noeud['bl']:
            alertes.append(f"{isole(noeud['nom'], isoler)} ({noeud['bl']})")
            texte[-1] += ' ⚑'
        pont = ' → '.join(et.get('pont') or [])
        sortie.append((lib, pont, noeud))
    return sortie, ' '.join(texte), ' | '.join(alertes)


def lignes_chaines(d):
    """Une ligne par chemin le plus court vers une cible à 1, 2, 3 ou 4 arêtes."""
    sortie = []
    for eid, (typ, noeuds) in d['res'].items():
        e = d['ent'][eid]
        for (_t, _i), (dist_, chemins) in noeuds.items():
            for ch in chemins:
                etapes, texte, alertes = decrire(d, eid, typ, ch)
                l = dict(depart=typ, inscrit=e['nom'], cle_inscrit=e['cle'], cin_inscrit=e['cin'], listes=e['listes'],
                         motifs=e['motifs'], distance=dist_, fiabilite=round(ch[-1]['fiab'], 4),
                         force=round(ch[-1]['force'], 5), chaine=texte, alerte_liste_noire=alertes,
                         nb_liste_noire=alertes.count(' | ') + 1 if alertes else 0)
                l['rapprochement'] = f"{ch[0]['regle']} ({ch[0]['statut']}, poids {ch[0]['rapprochement']:.2f})"
                l['nom_registre'] = ch[0]['nom_registre']
                for k, (lib, pont, n) in enumerate(etapes, start=1):
                    l[f'a{k}'], l[f'a{k}_pont'] = lib, pont
                    l[f'n{k}_type'], l[f'n{k}'] = n['type'], n['nom']
                    if n['type'] == 'société':
                        l[f'n{k}_rc'] = f"{n['rc'] or '?'} {n['trib'] or ''}".strip()
                        l[f'n{k}_ville'], l[f'n{k}_derniere_annonce'], l[f'n{k}_url'] = n['ville'], n['dern'], n['url']
                    l[f'n{k}_liste_noire'] = n['bl']
                sortie.append(l)
    return sortie


def ecrire_excel(d, chemin):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    lignes = lignes_chaines(d)
    wb = Workbook()
    wb.remove(wb.active)
    entete, rouge = PatternFill('solid', fgColor='14212B'), PatternFill('solid', fgColor='FCE4E4')

    def feuille(titre, colonnes, rangees, note, largeurs):
        ws = wb.create_sheet(titre)
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color='4A5866')
        for j, (c, lib) in enumerate(colonnes, start=1):
            x = ws.cell(row=3, column=j, value=lib)
            x.font, x.fill = Font(bold=True, color='FFFFFF'), entete
            x.alignment = Alignment(wrap_text=True, vertical='center')
            ws.column_dimensions[get_column_letter(j)].width = largeurs.get(c, 20)
        for i, r in enumerate(rangees, start=4):
            for j, (c, _) in enumerate(colonnes, start=1):
                ws.cell(row=i, column=j, value=r.get(c))
            if r.get('alerte_liste_noire'):
                for j in range(1, len(colonnes) + 1):
                    ws.cell(row=i, column=j).fill = rouge
        ws.freeze_panes = 'B4'
        ws.row_dimensions[3].height = 32
        if rangees:
            ws.auto_filter.ref = f'A3:{get_column_letter(len(colonnes))}{3 + len(rangees)}'

    larg = {'inscrit': 28, 'chaine': 110, 'alerte_liste_noire': 50, 'rapprochement': 24, 'nom_registre': 26}
    for k in range(1, 5):
        larg.update({f'n{k}': 32, f'a{k}_pont': 34, f'n{k}_liste_noire': 34, f'n{k}_url': 30})
    base = [('inscrit', 'Inscrit (point de départ)'), ('cin_inscrit', 'CIN inscrit'), ('listes', 'Listes'),
            ('rapprochement', 'Rapprochement liste noire ↔ registre'), ('nom_registre', 'Nom au registre'),
            ('distance', 'Arêtes'), ('fiabilite', 'Fiabilité'), ('force', 'Force'),
            ('alerte_liste_noire', 'Autres éléments de la liste noire sur le chemin'), ('chaine', 'Chaîne')]

    def detail(k, dessin):
        c = []
        for i in range(1, k + 1):
            c += [(f'a{i}', f'Arête {i}'), (f'a{i}_pont', f'Arête {i} : même personne d\'une société à l\'autre'),
                  (f'n{i}', f'Nœud {i} ({dessin[i]})'), (f'n{i}_type', f'Nœud {i} : type'), (f'n{i}_rc', f'Nœud {i} : RC'),
                  (f'n{i}_ville', f'Nœud {i} : ville'), (f'n{i}_derniere_annonce', f'Nœud {i} : dernière annonce'),
                  (f'n{i}_liste_noire', f'Nœud {i} : liste noire'), (f'n{i}_url', f'Nœud {i} : annonce')]
        return c

    dessin_pp = {1: 'PM n°1', 2: 'PP n°2', 3: 'PM n°2', 4: 'PP n°3'}
    dessin_pm = {1: 'personne', 2: 'société', 3: 'personne', 4: 'société'}
    tri = lambda r: (-r['nb_liste_noire'], -r['fiabilite'], -r['force'], r['inscrit'])
    pp = [r for r in lignes if r['depart'] == 'PP']
    pm = [r for r in lignes if r['depart'] == 'PM']
    boucles = sorted((r for r in lignes if r['alerte_liste_noire']), key=lambda r: (r['depart'], ) + tri(r))
    nb = lambda l, k: sum(1 for r in l if r['distance'] == k)
    ins = lambda l, k: len({r['cle_inscrit'] for r in l if r['distance'] == k})
    ws = wb.create_sheet('Synthèse')
    texte = [
        'Réseaux liste noire × registre du commerce — chaînes du dessin du 22/10/2026',
        'PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3',
        '',
        f"Personnes inscrites retrouvées au registre (point de départ) : {len({r['cle_inscrit'] for r in pp})}",
        f"   1 arête  : {nb(pp, 1)} chemins (PM n°1), {ins(pp, 1)} inscrits",
        f"   2 arêtes : {nb(pp, 2)} chemins (PP n°2 ou société associée), {ins(pp, 2)} inscrits",
        f"   3 arêtes : {nb(pp, 3)} chemins (PM n°2), {ins(pp, 3)} inscrits",
        f"   4 arêtes : {nb(pp, 4)} chemins (PP n°3), {ins(pp, 4)} inscrits",
        f"Sociétés inscrites retrouvées au registre (point de départ) : {len({r['cle_inscrit'] for r in pm})}",
        f"   1 à 4 arêtes : {nb(pm, 1)} / {nb(pm, 2)} / {nb(pm, 3)} / {nb(pm, 4)} chemins",
        f"Chemins qui reviennent vers un autre élément de la liste noire (feuille « Reliés à la liste noire », en rouge) : "
        f"{len(boucles)}, au départ de {len({r['cle_inscrit'] for r in boucles})} inscrits",
        '',
        'Lecture',
        '- Chaque ligne est un chemin le plus court vers une société ou une personne (au plus 5 par cible).',
        '- ⚑ dans la chaîne : élément aussi présent dans la liste noire (autre inscrit, société inscrite, employeur déclaré).',
        '- Rapprochement liste noire ↔ registre : nom + élément qui confirme, à valider par un analyste (pas de CIN dans '
        'l\'export).',
        '- Même personne d\'une société à l\'autre : même CIN, ou même nom + même ville quand ce nom figure dans 5 sociétés '
        'au plus. Un nom courant ne relie jamais deux sociétés.',
        '- Fiabilité = rapprochement × passages (1 pour un CIN, 0,8 × n^-0,5 pour nom + ville). Force = fiabilité × '
        'poids des rôles × taille des sociétés.',
    ]
    for i, t in enumerate(texte, start=1):
        ws.cell(row=i, column=1, value=t).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    ws.column_dimensions['A'].width = 140
    feuille('Reliés à la liste noire', [('depart', 'Départ')] + base + detail(4, dessin_pp), boucles,
            f'{len(boucles)} chemins qui touchent un autre élément de la liste noire, du plus chargé au moins chargé '
            '(départ PP = personne inscrite, PM = société inscrite ; nœuds selon le départ)', larg)
    for k, titre in ((4, 'Personnes · 4 arêtes'), (3, 'Personnes · 3 arêtes'), (2, 'Personnes · 2 arêtes'),
                     (1, 'Personnes · 1 arête')):
        rang = sorted((r for r in pp if r['distance'] == k), key=tri)
        feuille(titre, base + detail(k, dessin_pp), rang,
                f'{len(rang)} chemins au départ d\'une personne inscrite · en rouge : un autre élément de la liste noire', larg)
    feuille('Sociétés inscrites', base + detail(4, dessin_pm), sorted(pm, key=lambda r: (r['distance'],) + tri(r)),
            f'{len(pm)} chemins au départ d\'une société inscrite retrouvée au registre (1 à 4 arêtes)', larg)
    wb.save(chemin)
    print(f'  Excel : {chemin} ({len(lignes)} chemins, dont {len(boucles)} reliés à la liste noire)', flush=True)
    return lignes


def donnees_carte(d):
    """Sous-graphe de chaque inscrit (chemins les plus courts) pour la page."""
    sortie = []
    for eid, (typ, noeuds) in d['res'].items():
        e = d['ent'][eid]
        if not noeuds:
            continue
        n_out, a_out, vus_a, chaines = {}, [], {}, []
        if typ == 'PP':
            n_out['R'] = dict(t='PP', nom=e['nom'], d=0, sous='CIN ' + e['cin'] if e['cin'] else 'inscrit', bl='')
        else:
            sids = sorted(d['departs_soc'][eid])
            s0 = d['soc'][sids[0]]
            n_out['R'] = dict(t='PM', nom=nom_soc(s0), d=0, rc=s0['rc'], trib=s0['trib'], ville=s0['ville'],
                              dern=s0['dern'], url=s0.get('url'), bl='société inscrite : ' + e['nom'])
        compte = Counter()
        for (_t, _i), (dist_, chemins) in noeuds.items():
            compte[dist_] += 1
            for ch in chemins:
                etapes, texte, alertes = decrire(d, eid, typ, ch, isoler=True)
                chaines.append(dict(texte=texte, distance=dist_, fiab=round(ch[-1]['fiab'], 4),
                                    force=round(ch[-1]['force'], 5), bl=alertes))
                prec = 'R'
                bruts = ch if typ == 'PP' else ch[1:]
                if typ == 'PM' and len(d['departs_soc'][eid]) > 1 and ch[0]['sid'] != sorted(d['departs_soc'][eid])[0]:
                    s0 = d['soc'][ch[0]['sid']]
                    n_out.setdefault(f"S{ch[0]['sid']}", dict(t='PM', nom=nom_soc(s0), d=0, rc=s0['rc'], trib=s0['trib'],
                                                              ville=s0['ville'], dern=s0['dern'], url=s0.get('url'),
                                                              bl='société inscrite : ' + e['nom']))
                    prec = f"S{ch[0]['sid']}"
                for k, ((lib, pont, n), et) in enumerate(zip(etapes, bruts), start=1):
                    if et['type'] == 'S':
                        cle = f"S{et['sid']}"
                        n_out.setdefault(cle, dict(t='PM', nom=n['nom'], d=k, rc=n['rc'], trib=n['trib'], ville=n['ville'],
                                                   dern=n['dern'], url=n['url'], bl=n['bl'],
                                                   diss=d['soc'][et['sid']]['diss']))
                    else:
                        cle = f"I{et['ind']}"
                        n_out.setdefault(cle, dict(t='PP', nom=n['nom'], d=k, sous=lib, bl=n['bl']))
                    style = ''
                    if typ == 'PP' and k == 1:
                        style = 'rap'
                        pont = (f"rapprochement {et['regle']} ({et['statut']}, poids {et['rapprochement']:.2f}) avec "
                                f"« {et['nom_registre']} »" + (f' ; puis {pont}' if pont else ''))
                    elif pont:
                        style = 'pont'
                    ka = (prec, cle)
                    if ka not in vus_a or et['force'] > vus_a[ka]['force']:
                        a = dict(a=prec, b=cle, lib=lib, pont=pont, fiab=round(et['fiab'], 4),
                                 force=round(et['force'], 5), style=style)
                        if ka in vus_a:
                            a_out[a_out.index(vus_a[ka])] = a
                        else:
                            a_out.append(a)
                        vus_a[ka] = a
                    prec = cle
        chaines.sort(key=lambda c: (not c['bl'], c['distance'], -c['force']))
        sortie.append(dict(id=f"{typ}:{e['cle']}", nom=e['nom'], type=typ, cin=e['cin'], listes=e['listes'],
                           motifs=e['motifs'], compte={str(k): compte[k] for k in (1, 2, 3, 4)},
                           alerte=any(c['bl'] for c in chaines), noeuds=n_out, aretes=a_out, chaines=chaines))
    sortie.sort(key=lambda x: (x['type'], not x['alerte'], -x['compte']['4'], -x['compte']['3'], x['nom']))
    return sortie


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default='bl_rc.sqlite')
    ap.add_argument('--excel', default='Chaines_liste_noire_RC.xlsx')
    ap.add_argument('--html', default='Carte_chaines.html')
    ap.add_argument('--json', help='Écrire aussi les données de la carte en JSON')
    a = ap.parse_args()
    t0 = time.time()
    d = calculer(a.base)
    ecrire_excel(d, a.excel)
    carte = donnees_carte(d)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(carte, f, ensure_ascii=False)
    if a.html:
        modele = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carte_chaines_modele.html')
        with open(modele, encoding='utf-8') as f:
            page = f.read()
        donnees = json.dumps(carte, ensure_ascii=False).replace('</', '<\\/')
        with open(a.html, 'w', encoding='utf-8') as f:
            f.write(page.replace('/*__DONNEES__*/[]', donnees))
        print(f'  Carte : {a.html}', flush=True)
    print(f'Terminé en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
