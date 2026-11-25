#!/usr/bin/env python3
"""Enrichissement incrémental EQDOM sur PostgreSQL.

Par défaut : simulation transactionnelle intégrale puis ROLLBACK.
Écriture réelle : --apply --confirm-apply, après revue des résultats et sauvegarde.
Ne recharge PAS les données et ne recrée PAS le schéma historique SQLite.
"""

import argparse
from collections import Counter, defaultdict
import os

import psycopg
from psycopg.rows import dict_row


def val(value):
    return str(value).strip() if value is not None and str(value).strip() else None


def keypart(value):
    return val(value) or ""


def report(label, count):
    print(f"{label} : {count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Valider la transaction")
    parser.add_argument("--confirm-apply", action="store_true", help="Confirmation de l'écriture")
    args = parser.parse_args()
    if args.apply != args.confirm_apply:
        parser.error("L'écriture exige --apply ET --confirm-apply ensemble.")

    with psycopg.connect(os.environ["AF_DATABASE_URL"], row_factory=dict_row) as con:
        try:
            with con.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute("SET LOCAL statement_timeout = '180s'")
                # Gel du périmètre AVANT la première insertion.
                cur.execute("""CREATE TEMP TABLE dossiers_cibles ON COMMIT DROP AS
                    SELECT d.ref FROM af_dossier d
                    WHERE NOT EXISTS (SELECT 1 FROM af_dossier_identite di
                                      WHERE di.dossier_ref = d.ref)""")
                cur.execute("SELECT ref FROM dossiers_cibles ORDER BY ref")
                refs = {r["ref"] for r in cur.fetchall()}
                report("Dossiers figés", len(refs))
                if not refs:
                    con.rollback()
                    print("Rien à enrichir. Base inchangée.")
                    return

                # Les identifiants historiques n'ont pas de séquence : verrouillage nécessaire.
                cur.execute("""LOCK TABLE af_identite, af_personne, af_societe,
                    af_dossier_identite, af_relation IN SHARE ROW EXCLUSIVE MODE""")
                cur.execute("""SELECT p.* FROM af_personne p
                    JOIN dossiers_cibles d ON d.ref = p.dossier_ref
                    WHERE p.identite_id IS NULL ORDER BY p.af_personne_id""")
                personnes = cur.fetchall()
                cur.execute("""SELECT s.* FROM af_societe s
                    JOIN dossiers_cibles d ON d.ref = s.dossier_ref
                    WHERE s.identite_id IS NULL ORDER BY s.af_societe_id""")
                societes = cur.fetchall()
                cur.execute("SELECT * FROM af_identite")
                existantes = cur.fetchall()
                by_key = {i["cle"]: i for i in existantes}
                by_ice = defaultdict(set)
                for i in existantes:
                    if i["type_identite"] == "PM" and val(i["ice"]):
                        by_ice[val(i["ice"])].add(i["cle"])

                # CIN : ne jamais fusionner des noms normalisés divergents.
                cin_names = defaultdict(set)
                cin_in_dossier = defaultdict(lambda: defaultdict(set))
                for p in personnes:
                    cin, nom = val(p["cin_norm"]), val(p["cle_nom"])
                    if cin:
                        if nom:
                            cin_names[cin].add(nom)
                        if nom:
                            cin_in_dossier[p["dossier_ref"]][nom].add(cin)
                conflits_cin = {c for c, noms in cin_names.items() if len(noms) > 1}
                report("CIN divergents à vérifier", len(conflits_cin))

                # L'ICE peut résoudre un alias RC, à condition qu'il soit unique.
                ice_rc = defaultdict(set)
                for s in societes:
                    if val(s["ice"]) and val(s["rc_num"]) and val(s["tribunal_code"]):
                        ice_rc[val(s["ice"])].add(
                            "R:" + val(s["rc_num"]) + "@" + val(s["tribunal_code"])
                        )
                ice_ambigus = {ice for ice, keys in ice_rc.items() if len(keys) > 1}

                # Planifier toutes les affectations, sans encore modifier les lignes.
                affectations = {}  # (type, row_id) -> (cle, niveau)
                bloqués = Counter()
                for p in personnes:
                    ref, cin, nom = p["dossier_ref"], val(p["cin_norm"]), val(p["cle_nom"])
                    if cin:
                        if cin in conflits_cin:
                            bloqués["PP_CIN_DIVERGENT"] += 1
                            continue
                        cle, niveau = "C:" + cin, "fort"
                    else:
                        cands = cin_in_dossier[ref].get(nom, set()) if nom else set()
                        cands = {x for x in cands if x not in conflits_cin}
                        if len(cands) == 1:
                            cle, niveau = "C:" + next(iter(cands)), "fort"
                        elif len(cands) > 1:
                            bloqués["PP_SANS_CIN_AMBIGU"] += 1
                            continue
                        elif nom:
                            cle, niveau = f"N:{ref}:{nom}", "faible"
                        else:
                            bloqués["PP_SANS_NOM"] += 1
                            continue
                    affectations[("PP", p["af_personne_id"])] = (cle, niveau)

                # Les sociétés sont traitées en deux passes : fortes puis faibles.
                fortes_dossier = defaultdict(set)
                for s in societes:
                    ice, rc, trib = val(s["ice"]), val(s["rc_num"]), val(s["tribunal_code"])
                    role = val(s["role"])
                    if ice in ice_ambigus:
                        bloqués["PM_ICE_AMBIGU"] += 1
                        continue
                    if role not in ("employeur", "vendeur") and rc and trib:
                        cle = f"R:{rc}@{trib}"
                    elif ice:
                        cands = ice_rc.get(ice, set()) | by_ice.get(ice, set())
                        if len(cands) > 1:
                            bloqués["PM_ICE_CONTRADICTOIRE"] += 1
                            continue
                        cle = next(iter(cands)) if cands else "I:" + ice
                    else:
                        continue
                    affectations[("PM", s["af_societe_id"])] = (cle, "fort")
                    if role not in ("employeur", "vendeur"):
                        fortes_dossier[s["dossier_ref"]].add(cle)

                for s in societes:
                    sid, ref = s["af_societe_id"], s["dossier_ref"]
                    if ("PM", sid) in affectations or val(s["ice"]) in ice_ambigus:
                        continue
                    rc, trib, ice = val(s["rc_num"]), val(s["tribunal_code"]), val(s["ice"])
                    nom, role = val(s["cle_rs"]), val(s["role"])
                    if ice:
                        # Ne pas contourner un conflit ICE détecté lors de la première passe.
                        bloqués["PM_ICE_A_EXAMINER"] += 1
                        continue
                    if role in ("employeur", "vendeur") and nom:
                        cle, niveau = "E:" + nom, "faible"
                    elif not rc and nom and len(fortes_dossier[ref]) == 1:
                        # Réutilisation dans le même dossier SEULEMENT si le nom
                        # correspond à une mention forte de la même société.
                        strong_names = {
                            val(q["cle_rs"]) for q in societes
                            if q["dossier_ref"] == ref
                            and ("PM", q["af_societe_id"]) in affectations
                            and affectations[("PM", q["af_societe_id"])][1] == "fort"
                            and affectations[("PM", q["af_societe_id"])][0] in fortes_dossier[ref]
                        }
                        if nom in strong_names:
                            cle, niveau = next(iter(fortes_dossier[ref])), "fort"
                        else:
                            cle, niveau = f"D:{ref}:{nom}", "faible"
                    elif rc:
                        cle, niveau = f"R:{rc}@?:{keypart(nom)}", "faible"
                    elif nom:
                        cle, niveau = f"D:{ref}:{nom}", "faible"
                    else:
                        bloqués["PM_SANS_CLE"] += 1
                        continue
                    affectations[("PM", sid)] = (cle, niveau)

                # Construire les identités absentes avec les mêmes 17 colonnes
                # que le schéma historique, sans écraser les données existantes.
                source = {("PP", p["af_personne_id"]): p for p in personnes}
                source.update({("PM", s["af_societe_id"]): s for s in societes})
                groupes = defaultdict(list)
                for rowkey, (cle, niveau) in affectations.items():
                    groupes[cle].append((rowkey, niveau, source[rowkey]))
                # Les clés historiques sont globalement uniques ; éviter tout croisement PP/PM.
                for cle, group in groupes.items():
                    if cle in by_key and by_key[cle]["type_identite"] != group[0][0][0]:
                        raise RuntimeError("Clé d'identité de type incohérent : " + cle[:2])
                cur.execute("SELECT COALESCE(MAX(identite_id), 0) AS n FROM af_identite")
                next_id = cur.fetchone()["n"]
                nouvelles = 0
                for cle, group in sorted(groupes.items()):
                    if cle in by_key:
                        continue
                    next_id += 1
                    typ = group[0][0][0]
                    niveau = group[0][1]
                    rows = [r for _, _, r in group]
                    nom_field = "nom_complet" if typ == "PP" else "denomination"
                    nom = next((val(r[nom_field]) for r in rows if val(r[nom_field])), None)
                    refs_group = sorted({r["dossier_ref"] for r in rows})
                    roles = ", ".join(sorted({str(r["role"]) for r in rows if r["role"]}))
                    first = rows[0]
                    cur.execute("""INSERT INTO af_identite
                        (identite_id,type_identite,cle,niveau_cle,nom,autres_noms,
                         cin_norm,rc_num,tribunal_code,ice,date_naissance,ville_code,
                         adresse,nb_dossiers,roles,premier_dossier,dernier_dossier)
                        VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (next_id,typ,cle,niveau,nom,
                         val(first["cin_norm"]) if typ == "PP" else None,
                         val(first["rc_num"]) if typ == "PM" else None,
                         val(first["tribunal_code"]) if typ == "PM" else None,
                         val(first["ice"]) if typ == "PM" else None,
                         val(first["date_naissance"]) if typ == "PP" else None,
                         val(first["ville_code"]),val(first["adresse"]),
                         len(refs_group),roles,refs_group[0],refs_group[-1]))
                    by_key[cle] = {"identite_id": next_id, "cle": cle, "type_identite": typ}
                    nouvelles += 1
                report("Identités créées en test", nouvelles)

                pp_updates = pm_updates = 0
                for (typ, row_id), (cle, _) in affectations.items():
                    table, col = ("af_personne", "af_personne_id") if typ == "PP" else ("af_societe", "af_societe_id")
                    cur.execute(f"UPDATE {table} SET identite_id = %s WHERE {col} = %s AND identite_id IS NULL",
                                (by_key[cle]["identite_id"], row_id))
                    if typ == "PP":
                        pp_updates += cur.rowcount
                    else:
                        pm_updates += cur.rowcount
                report("Personnes rattachées en test", pp_updates)
                report("Sociétés rattachées en test", pm_updates)

                # Association dossier-identité : alimenter une seule fois
                # chaque couple (dossier, identité, rôle), sans mélanger les pièces.
                cur.execute("""INSERT INTO af_dossier_identite
                    (dossier_ref,identite_id,role,piece_types)
                    SELECT dossier_ref,identite_id,role,
                           STRING_AGG(DISTINCT piece_type, ', ')
                    FROM (
                        SELECT p.dossier_ref,p.identite_id,p.role,p.piece_type
                        FROM af_personne p JOIN dossiers_cibles d ON d.ref=p.dossier_ref
                        UNION ALL
                        SELECT s.dossier_ref,s.identite_id,s.role,s.piece_type
                        FROM af_societe s JOIN dossiers_cibles d ON d.ref=s.dossier_ref
                    ) x
                    WHERE identite_id IS NOT NULL AND role IS NOT NULL
                    GROUP BY dossier_ref,identite_id,role
                    ON CONFLICT (dossier_ref,identite_id,role) DO NOTHING""")
                report("Associations dossier-identité créées en test", cur.rowcount)

                # Relations PP -> PM, selon l'identifiant explicite de société
                # puis rôle de société cliente unique (règle historique).
                cur.execute("SELECT COALESCE(MAX(relation_id),0) AS n FROM af_relation")
                next_relation = cur.fetchone()["n"]
                cur.execute("""SELECT p.identite_id AS pp,s.identite_id AS pm,p.role,p.qualite,
                       p.parts,p.dossier_ref,p.piece_type,p.source
                    FROM af_personne p JOIN dossiers_cibles d ON d.ref=p.dossier_ref
                    JOIN af_societe s ON s.af_societe_id=p.societe_af_id
                    WHERE p.identite_id IS NOT NULL AND s.identite_id IS NOT NULL""")
                relations = cur.fetchall()
                cur.execute("""SELECT p.identite_id AS pp,s.identite_id AS pm,p.role,p.qualite,
                       p.parts,p.dossier_ref,p.piece_type,p.source
                    FROM af_personne p JOIN dossiers_cibles d ON d.ref=p.dossier_ref
                    JOIN af_societe s ON s.dossier_ref=p.dossier_ref
                    JOIN af_identite i ON i.identite_id=s.identite_id
                    WHERE p.societe_af_id IS NULL AND p.identite_id IS NOT NULL
                      AND p.role IN ('gerant','associe','dirigeant','signataire')
                      AND s.role IN ('societe_cliente','societe_du_client')
                      AND i.niveau_cle='fort'
                      AND (SELECT COUNT(DISTINCT s2.identite_id)
                           FROM af_societe s2 JOIN af_identite i2 ON i2.identite_id=s2.identite_id
                           WHERE s2.dossier_ref=p.dossier_ref
                             AND s2.role IN ('societe_cliente','societe_du_client')
                             AND i2.niveau_cle='fort')=1""")
                relations.extend(cur.fetchall())
                seen = set()
                relations_creees = 0
                for r in relations:
                    ident = (r["pp"],r["pm"],r["role"],r["dossier_ref"])
                    if ident in seen or not r["role"]:
                        continue
                    seen.add(ident)
                    cur.execute("""SELECT 1 FROM af_relation WHERE pp_identite_id=%s
                        AND pm_identite_id=%s AND role=%s AND dossier_ref=%s LIMIT 1""", ident)
                    if cur.fetchone():
                        continue
                    next_relation += 1
                    cur.execute("""INSERT INTO af_relation
                      (relation_id,pp_identite_id,pm_identite_id,role,qualite,parts,dossier_ref,piece_type,source)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (next_relation,r["pp"],r["pm"],r["role"],r["qualite"],
                       r["parts"],r["dossier_ref"],r["piece_type"],r["source"]))
                    relations_creees += 1
                report("Relations personne-société créées en test", relations_creees)

                # Contrôle de cohérence : aucune clé orpheline sur le périmètre.
                cur.execute("""SELECT COUNT(*) AS n FROM af_dossier_identite di
                    JOIN dossiers_cibles d ON d.ref=di.dossier_ref
                    LEFT JOIN af_identite i ON i.identite_id=di.identite_id
                    WHERE i.identite_id IS NULL""")
                if cur.fetchone()["n"]:
                    raise RuntimeError("Association dossier-identité orpheline")
                for motif, nombre in sorted(bloqués.items()):
                    report("À vérifier / non rattaché : " + motif, nombre)
                print("NOTE : liens antifraude AF01–AF20 non recalculés ici ; traitement séparé requis.")
                if args.apply:
                    con.commit()
                    print("COMMIT effectué : enrichissement enregistré.")
                else:
                    con.rollback()
                    print("ROLLBACK effectué : base inchangée.")
        except BaseException:
            con.rollback()
            raise


if __name__ == "__main__":
    main()
