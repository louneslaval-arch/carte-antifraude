#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comparer_bases.py — ce qui change entre deux constructions de la base (deux exports de Kamal).

  python3 comparer_bases.py --avant bl_rc_22-10.sqlite --apres bl_rc_26-10.sqlite [--json comparaison.json]

Compare : remplissage du registre (CIN, rôles, parts), correspondances par règle et par niveau, inscrits reliés,
et liste les inscrits nouvellement reliés ou passés de « probable » à « certain ».
"""
import argparse
import json
import sqlite3


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def chiffres(con):
    r = {}
    r['annonces'] = q(con, 'SELECT count(*) FROM rc_annonce')[0][0]
    r['societes'] = q(con, 'SELECT count(*) FROM rc_societe')[0][0]
    r['personnes'] = q(con, "SELECT count(*) FROM rc_personne WHERE type_personne = 'PP'")[0][0]
    r['personnes_cin'] = q(con, "SELECT count(*) FROM rc_personne WHERE type_personne = 'PP' AND cin_norm IS NOT NULL")[0][0]
    r['cin_distincts'] = q(con, 'SELECT count(DISTINCT cin_norm) FROM rc_personne WHERE cin_norm IS NOT NULL')[0][0]
    r['personnes_pct'] = q(con, "SELECT count(*) FROM rc_personne WHERE type_personne = 'PP' AND pct IS NOT NULL")[0][0]
    r['mentions'] = q(con, 'SELECT count(*) FROM rc_mention')[0][0]
    r['rejets'] = q(con, 'SELECT count(*) FROM rc_rejet')[0][0]
    r['cin_communs'] = q(con, """SELECT count(*) FROM (SELECT DISTINCT r.cin_norm FROM rc_personne r
        JOIN bl_inscription b ON b.cin_norm = r.cin_norm WHERE r.cin_norm IS NOT NULL)""")[0][0]
    r['par_regle'] = {k: (n, i) for k, n, i in q(con, """SELECT regle, count(*), count(DISTINCT bl_entite_id)
        FROM correspondance WHERE statut NOT IN ('faible', 'ecarte') GROUP BY regle""")}
    r['par_statut'] = dict(q(con, 'SELECT statut, count(*) FROM correspondance GROUP BY statut'))
    r['inscrits_relies'] = q(con, """SELECT count(DISTINCT bl_entite_id) FROM correspondance
        WHERE statut NOT IN ('faible', 'ecarte')""")[0][0]
    r['inscrits_certains'] = q(con, """SELECT count(DISTINCT bl_entite_id) FROM correspondance
        WHERE statut IN ('alerte', 'confirme')""")[0][0]
    r['pp_relies'] = q(con, """SELECT count(DISTINCT c.bl_entite_id) FROM correspondance c JOIN bl_entite e
        ON e.entite_id = c.bl_entite_id WHERE e.type_entite = 'PP' AND c.rc_objet = 'rc_personne'
        AND c.statut NOT IN ('faible', 'ecarte')""")[0][0]
    r['pp_certains'] = q(con, """SELECT count(DISTINCT c.bl_entite_id) FROM correspondance c JOIN bl_entite e
        ON e.entite_id = c.bl_entite_id WHERE e.type_entite = 'PP' AND c.statut IN ('alerte', 'confirme')""")[0][0]
    return r


def inscrits(con):
    """{clé entité: (nom, meilleur statut, règles, sociétés reliées)}"""
    out = {}
    for cle, nom, typ, statut, regles, socs in q(con, """
        SELECT e.cle_entite, e.nom_affiche, e.type_entite,
               min(CASE c.statut WHEN 'alerte' THEN 0 WHEN 'confirme' THEN 0 ELSE 1 END),
               group_concat(DISTINCT c.regle), group_concat(DISTINCT coalesce(s.rc_num || '@' || s.tribunal_code, s.denomination))
        FROM correspondance c JOIN bl_entite e ON e.entite_id = c.bl_entite_id
        LEFT JOIN rc_societe s ON s.societe_id = c.societe_id
        WHERE c.statut NOT IN ('faible', 'ecarte') GROUP BY e.cle_entite"""):
        out[cle] = (nom, typ, 'certain' if statut == 0 else 'probable', regles, set((socs or '').split(',')))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--avant', required=True)
    ap.add_argument('--apres', required=True)
    ap.add_argument('--json')
    a = ap.parse_args()
    c1 = sqlite3.connect(f'file:{a.avant}?mode=ro', uri=True)
    c2 = sqlite3.connect(f'file:{a.apres}?mode=ro', uri=True)
    r1, r2 = chiffres(c1), chiffres(c2)
    print('Indicateur                                   avant       après')
    for k in ('annonces', 'societes', 'personnes', 'personnes_cin', 'cin_distincts', 'cin_communs', 'personnes_pct',
              'mentions', 'rejets', 'inscrits_relies', 'inscrits_certains', 'pp_relies', 'pp_certains'):
        print(f'{k:40} {r1[k]:>10,} {r2[k]:>10,}'.replace(',', ' '))
    print('\nRègle        avant (liens / inscrits)   après')
    for k in sorted(set(r1['par_regle']) | set(r2['par_regle'])):
        x, y = r1['par_regle'].get(k, (0, 0)), r2['par_regle'].get(k, (0, 0))
        print(f'{k:8} {x[0]:>8} / {x[1]:<6}   {y[0]:>8} / {y[1]:<6}')
    print('\nStatut        avant   après')
    for k in sorted(set(r1['par_statut']) | set(r2['par_statut'])):
        print(f"{k:12} {r1['par_statut'].get(k, 0):>7} {r2['par_statut'].get(k, 0):>7}")
    i1, i2 = inscrits(c1), inscrits(c2)
    nouveaux = {k: v for k, v in i2.items() if k not in i1}
    perdus = {k: v for k, v in i1.items() if k not in i2}
    renforces = {k: v for k, v in i2.items() if k in i1 and i1[k][2] == 'probable' and v[2] == 'certain'}
    elargis = {k: v for k, v in i2.items() if k in i1 and v[4] - i1[k][4] and k not in renforces}
    print(f'\nInscrits reliés : {len(i1)} → {len(i2)} ; nouveaux {len(nouveaux)}, disparus {len(perdus)}, '
          f'passés de probable à certain {len(renforces)}, reliés à de nouvelles sociétés {len(elargis)}')
    for titre, grp in (('NOUVEAUX', nouveaux), ('PROBABLE → CERTAIN', renforces), ('DISPARUS', perdus)):
        print(f'\n--- {titre} ({len(grp)})')
        for k, (nom, typ, st, regles, socs) in sorted(grp.items(), key=lambda x: (x[1][1] or '', x[1][2], x[1][0] or ''))[:80]:
            print(f'  {typ} {st:8} {(nom or "?")[:34]:34} {(regles or ""):14} {", ".join(sorted(socs))[:70]}')
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(dict(avant=r1, apres=r2, nouveaux=list(nouveaux), perdus=list(perdus),
                           renforces=list(renforces), elargis=list(elargis)), f, ensure_ascii=False, default=list)


if __name__ == '__main__':
    main()
