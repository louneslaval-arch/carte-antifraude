#!/usr/bin/env python3
"""Liens antifraude incrémentaux PostgreSQL EQDOM.

Règles incluses : AF01, AF02/02b/02n/02c, AF03/03b/03n, AF04,
AF05, AF07, AF09, AF11, AF20. Les rapprochements de noms sont
conservateurs et les résultats incertains restent « à vérifier ».

Simulation par défaut (ROLLBACK). Écriture : --apply --confirm-apply.
Ce script ne supprime jamais les liens existants.
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import os
import re
import sys
import unicodedata
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# Réutiliser la normalisation métier exacte du projet historique quand elle
# est disponible sur le PC (évite de reclassifier des sociétés par approximation).
_legacy_dir = Path(__file__).resolve().parents[1] / 'pipeline'
if not (_legacy_dir / 'construire_base.py').is_file():
    raise SystemExit('construire_base.py introuvable dans le dossier pipeline historique')
sys.path.insert(0, str(_legacy_dir))
import construire_base as cb


def cleaned(s):
    s = unicodedata.normalize("NFKD", str(s or "")).upper()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[A-Z0-9]+", s))


def compatible(a, b):
    x, y = cleaned(a), cleaned(b)
    return bool(x and y and (x == y or SequenceMatcher(None, x, y).ratio() >= .90))


def variants(i):
    return [x for x in [i.get("nom")] + (i.get("autres_noms") or "").split(" ; ") if x]


def societe_compatible(a, b):
    """Critères historiques rs_proches + sq_proches du moteur SQLite."""
    ka, kb = cb.cle_rs(a or ''), cb.cle_rs(b or '')
    if ka and kb:
        if ka == kb or cb._ratio(ka, kb) >= .8:
            return True
        ma, mb = set(ka.split()), set(kb.split())
        if ma and mb and (ma <= mb or mb <= ma):
            return True
    sa, sb = cb.squelette_rs(a or ''), cb.squelette_rs(b or '')
    return bool(sa and sb) and cb._ratio(sa, sb) >= .8


def nmatch(names, others, societe=False):
    matcher = societe_compatible if societe else compatible
    return any(matcher(a, b) for a in names for b in others if a and b)


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-apply", action="store_true")
    args = parser.parse_args()
    if args.apply != args.confirm_apply:
        parser.error("Écriture : utiliser --apply --confirm-apply ensemble")

    with psycopg.connect(os.environ["AF_DATABASE_URL"], row_factory=dict_row) as con:
        try:
            with con.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='5s'")
                cur.execute("SET LOCAL statement_timeout='240s'")
                cur.execute("LOCK TABLE af_lien IN SHARE ROW EXCLUSIVE MODE")

                # On cible les identités sans lien et celles récemment rattachées.
                # Le contrôle global idempotent permet aussi de récupérer un lien ancien manqué.
                ids = rows(cur, """SELECT identite_id,type_identite,cle,niveau_cle,
                    nom,autres_noms,cin_norm,rc_num,tribunal_code,ice,ville_code,roles
                    FROM af_identite""")
                bles = rows(cur, """SELECT entite_id,type_entite,nom_affiche,cin,
                    rc_num,tribunal_code,ice,ville_code,employeur FROM bl_entite""")
                inscr = rows(cur, """SELECT entite_id,nom,prenom,nom_ras,cin_norm,ice_norm
                    FROM bl_inscription""")
                rcs = rows(cur, """SELECT societe_id,denomination,autres_denominations,
                    rc_num,tribunal_code FROM rc_societe
                    WHERE rc_num IS NOT NULL AND tribunal_code IS NOT NULL""")
                rcp = rows(cur, """SELECT personne_id,societe_id,cin_norm,nom_complet,
                    nom_latin,ecriture FROM rc_personne WHERE type_personne='PP'""")
                rel = rows(cur, """SELECT pp_identite_id,pm_identite_id,role,dossier_ref
                    FROM af_relation WHERE role IN ('gerant','associe','dirigeant','signataire')""")

                iid = {r["identite_id"]: r for r in ids}
                blnames = defaultdict(set)
                for b in bles:
                    if b["nom_affiche"]:
                        blnames[b["entite_id"]].add(b["nom_affiche"])
                for b in inscr:
                    for name in ((b["nom"] or "") + " " + (b["prenom"] or ""), b["nom_ras"]):
                        if name and name.strip():
                            blnames[b["entite_id"]].add(name.strip())
                bl_cin = defaultdict(set)
                bl_rc = defaultdict(list)
                bl_ice = defaultdict(set)
                bl_rs = defaultdict(set)
                bl_emp = defaultdict(set)
                for b in bles:
                    eid = b["entite_id"]
                    if b["type_entite"] == "PP":
                        if b["cin"]:
                            bl_cin[cleaned(b["cin"]).replace(" ", "")].add(eid)
                        if b["employeur"]:
                            bl_emp[cleaned(b["employeur"])].add(eid)
                    else:
                        if b["rc_num"]:
                            bl_rc[b["rc_num"]].append(b)
                        if b["ice"]:
                            bl_ice[b["ice"]].add(eid)
                    for name in blnames[eid]:
                        if b["type_entite"] == "PM":
                            bl_rs[cleaned(name)].add(eid)
                for b in inscr:
                    if b["cin_norm"]:
                        bl_cin[b["cin_norm"]].add(b["entite_id"])
                    if b["ice_norm"]:
                        bl_ice[b["ice_norm"]].add(b["entite_id"])
                bl_has_cin = set().union(*bl_cin.values()) if bl_cin else set()

                rc_by_key = defaultdict(list)
                for r in rcs:
                    rc_by_key[(r["rc_num"],r["tribunal_code"])].append(r)
                rp_by_cin = defaultdict(list)
                rp_by_soc = defaultdict(list)
                for p in rcp:
                    if p["cin_norm"]:
                        rp_by_cin[p["cin_norm"]].append(p)
                    rp_by_soc[p["societe_id"]].append(p)

                # Une clé logique sans détail : cohérente avec le moteur historique.
                existing = rows(cur, """SELECT regle,identite_id,dossier_ref,cible,
                       cible_id,cle_valeur FROM af_lien""")
                seen = {(r["regle"],r["identite_id"],r["dossier_ref"],
                         r["cible"],r["cible_id"],r["cle_valeur"]) for r in existing}
                candidates = []

                def link(rule, level, identity, target, target_id,
                         ktype=None, kval=None, detail=None, dossier=None):
                    key = (rule,identity,dossier,target,str(target_id),kval)
                    if key in seen:
                        return
                    seen.add(key)
                    candidates.append((rule,level,identity,dossier,target,str(target_id),
                                       ktype,kval,str(detail)[:600] if detail else None))

                soc_reg = {
                    r["identite_id"]: int(r["cible_id"])
                    for r in rows(cur,"""SELECT identite_id,cible_id FROM af_lien
                        WHERE regle IN ('AF03','AF03b') AND cible='rc_societe'
                          AND identite_id IS NOT NULL AND cible_id ~ '^[0-9]+$'""")
                }
                for i in ids:
                    ii, typ, names = i["identite_id"], i["type_identite"], variants(i)
                    cin, rc, trib, ice = i["cin_norm"], i["rc_num"], i["tribunal_code"], i["ice"]
                    if typ == "PP":
                        if cin:
                            for eid in bl_cin.get(cin, ()):
                                link("AF01","certain",ii,"bl_entite",eid,"CIN",cin)
                            for p in rp_by_cin.get(cin, ()):
                                link("AF04","certain",ii,"rc_personne",p["personne_id"],
                                     "CIN",cin,f"société du registre n° {p['societe_id']}")
                        else:
                            for eid, bs in blnames.items():
                                if nmatch(names,bs) and eid not in bl_has_cin:
                                    link("AF01n","à vérifier",ii,"bl_entite",eid,"NOM",cleaned(i["nom"]),
                                         "correspondance de nom sans CIN")
                        continue
                    if rc and trib:
                        for b in bl_rc.get(rc, ()):
                            eid = b["entite_id"]
                            good = nmatch(names,blnames[eid],societe=True)
                            if b["tribunal_code"] == trib:
                                link("AF02" if good else "AF02n",
                                     "certain" if good else "à vérifier",ii,"bl_entite",eid,
                                     "RC_TRIB",f"{rc}@{trib}",None if good else "raison sociale différente")
                            elif not b["tribunal_code"] and good:
                                link("AF02b","probable",ii,"bl_entite",eid,"RC",rc)
                        for s in rc_by_key.get((rc,trib), ()):
                            names_rc = [s["denomination"]] + (s["autres_denominations"] or "").split(" | ")
                            if nmatch(names,names_rc,societe=True):
                                rule,level = "AF03","certain"
                                soc_reg[ii] = s["societe_id"]
                            elif not any(names_rc):
                                rule,level = "AF03b","probable"
                                soc_reg[ii] = s["societe_id"]
                            else:
                                rule,level = "AF03n","à vérifier"
                            link(rule,level,ii,"rc_societe",s["societe_id"],"RC_TRIB",f"{rc}@{trib}")
                    if ice:
                        for eid in bl_ice.get(ice, ()):
                            link("AF02c","certain",ii,"bl_entite",eid,"ICE",ice)
                    key = cleaned(i["nom"])
                    if key and len(key) >= 5:
                        if "employeur" in (i["roles"] or ""):
                            for eid in bl_rs.get(key, set()) | bl_emp.get(key, set()):
                                link("AF07","à vérifier",ii,"bl_entite",eid,"RS",key)
                        if any(x in (i["roles"] or "") for x in ("societe_cliente","societe_du_client")):
                            for eid in bl_rs.get(key, ()):
                                bs = next(b for b in bles if b["entite_id"] == eid)
                                if not bs["rc_num"] and (not bs["ville_code"] or not i["ville_code"] or bs["ville_code"] == i["ville_code"]):
                                    link("AF02d","à vérifier",ii,"bl_entite",eid,"RS",key)

                # AF05 : personne associée à une société rapprochée du registre.
                for r in rel:
                    pp, pm = iid.get(r["pp_identite_id"]), r["pm_identite_id"]
                    sid = soc_reg.get(pm)
                    if not pp or not pp["cin_norm"] or not sid:
                        continue
                    for p in rp_by_soc.get(sid, ()):
                        if not nmatch(variants(pp),[p["nom_complet"],p["nom_latin"]]):
                            continue
                        rcin = p["cin_norm"]
                        conflict = bool(rcin and rcin != pp["cin_norm"])
                        level = "à vérifier" if conflict else "certain"
                        link("AF05",level,pp["identite_id"],"rc_personne",p["personne_id"],
                             "CIN",pp["cin_norm"],"CIN différent au registre" if conflict else "CIN apporté ou confirmé",
                             r["dossier_ref"])

                # AF11 : tiers bancaire portant le même nom qu'un inscrit.
                tiers = rows(cur, """SELECT dossier_ref,tiers,cle,type_cle,nb_operations,
                    total_credit,total_debit FROM af_tiers WHERE cle IS NOT NULL""")
                for t in tiers:
                    key = cleaned(t["cle"])
                    if t["type_cle"] == "RS":
                        dests = bl_rs.get(key, ()) if len(key) >= 6 else ()
                        level = "indice"
                    elif t["type_cle"] == "NOM" and len(key.split()) >= 2:
                        dests = {e for e,names in blnames.items() if any(cleaned(n)==key for n in names)}
                        level = "indice faible" if len(key.split()) == 2 else "indice"
                    else:
                        continue
                    for eid in dests:
                        link("AF11",level,None,"bl_entite",eid,t["type_cle"],t["cle"],
                             f"tiers : {t['tiers']} / {t['nb_operations']} opération(s)",t["dossier_ref"])

                # AF09 : même RIB, clients forts différents et non directement liés.
                clients = defaultdict(set)
                for r in rows(cur, """SELECT di.dossier_ref,di.identite_id FROM af_dossier_identite di
                    JOIN af_identite i ON i.identite_id=di.identite_id
                    WHERE di.role IN ('demandeur','societe_cliente') AND i.niveau_cle='fort'"""):
                    clients[r["dossier_ref"]].add(r["identite_id"])
                ribs = defaultdict(set)
                for r in rows(cur,"SELECT rib,dossier_ref FROM af_compte WHERE rib IS NOT NULL"):
                    ribs[r["rib"]].add(r["dossier_ref"])
                direct = {(r["pp_identite_id"],r["pm_identite_id"]) for r in rel}
                for rib, refs in ribs.items():
                    if not (2 <= len(refs) <= 12):
                        continue
                    refs = sorted(refs)
                    for a in range(len(refs)):
                        for b in range(a+1,len(refs)):
                            aa,bb = clients[refs[a]], clients[refs[b]]
                            if not aa or not bb or aa & bb:
                                continue
                            if any((x,y) in direct or (y,x) in direct for x in aa for y in bb):
                                continue
                            if any(x in iid and y in iid and iid[x]["type_identite"]==iid[y]["type_identite"]=="PP"
                                   and nmatch(variants(iid[x]),variants(iid[y])) for x in aa for y in bb):
                                continue
                            identity = min(aa)
                            link("AF09","indice",identity,"af_dossier",refs[b],"RIB",rib,
                                 f"même RIB que le dossier {refs[a]}, clients distincts",refs[a])

                # AF20 : rapprochement au réseau de registre, si table chemin disponible.
                cur.execute("SELECT to_regclass('public.chemin') AS t")
                if cur.fetchone()["t"]:
                    anchors = defaultdict(set)
                    directs = defaultdict(set)
                    for row in existing:
                        if row["cible"]=="bl_entite" and row["identite_id"] is not None:
                            directs[row["identite_id"]].add(row["cible_id"])
                        if row["regle"] in ("AF03","AF03b","AF04","AF05"):
                            anchors[(row["cible"],row["cible_id"])].add(row["identite_id"])
                    for r in candidates:
                        if r[4]=="bl_entite" and r[2] is not None:
                            directs[r[2]].add(r[5])
                        if r[0] in ("AF03","AF03b","AF04","AF05") and r[1] in ("certain","probable"):
                            anchors[(r[4],r[5])].add(r[2])
                    best = {}
                    for path in rows(cur,"""SELECT bl_entite_id,cible_type,cible_id,
                        profondeur,force,trace FROM chemin
                        WHERE cible_type IN ('rc_societe','rc_personne')"""):
                        for ident in anchors.get((path["cible_type"],str(path["cible_id"])), ()):
                            if str(path["bl_entite_id"]) in directs.get(ident, ()):
                                continue
                            k = (ident,path["bl_entite_id"])
                            if k not in best or path["profondeur"] < best[k]["profondeur"]:
                                best[k] = path
                    for (ident,eid),p in best.items():
                        prof = p["profondeur"]
                        link("AF20",f"réseau à {prof} arête"+("s" if prof>1 else ""),
                             ident,"bl_entite",eid,"CHEMIN",f"{p['cible_type']}:{p['cible_id']}",p["trace"])

                counts = Counter(x[0] for x in candidates)
                print("=== NOUVEAUX LIENS (TRANSACTION) ===")
                for rule,count in sorted(counts.items()):
                    print(f"{rule}: {count}")
                print("TOTAL :",len(candidates))
                if args.apply and candidates:
                    cur.execute("SELECT COALESCE(MAX(lien_id),0) AS n FROM af_lien")
                    base = cur.fetchone()["n"]
                    for pos,r in enumerate(candidates,1):
                        cur.execute("""INSERT INTO af_lien
                           (lien_id,regle,niveau,identite_id,dossier_ref,cible,cible_id,
                            cle_type,cle_valeur,detail)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(base+pos,*r))
                    con.commit()
                    print("COMMIT effectué : nouveaux liens enregistrés.")
                elif args.apply:
                    con.rollback()
                    print("Aucun nouveau lien ; base inchangée.")
                else:
                    con.rollback()
                    print("SIMULATION : ROLLBACK, base inchangée.")
        except BaseException:
            con.rollback()
            raise


if __name__ == "__main__":
    main()
