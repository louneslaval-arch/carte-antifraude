"""API EQDOM : graphe et indicateurs de vigilance (lecture seule PostgreSQL).

Démarrer : uvicorn api_graphe_eqdom:app --host 127.0.0.1 --port 8000
Documentation : http://127.0.0.1:8000/docs

Les indicateurs ne constituent pas une décision de fraude automatisée.
Ne pas exposer publiquement cette API sans authentification/contrôle d'accès.
"""

from collections import Counter
from contextlib import contextmanager
import os

from fastapi import FastAPI, HTTPException, Query
import psycopg
from psycopg.rows import dict_row


app = FastAPI(title="EQDOM - Graphe antifraude", version="0.1.0")


@contextmanager
def database():
    url = os.getenv("AF_DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="AF_DATABASE_URL absente")
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=8) as con:
            with con.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
            yield con
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Connexion PostgreSQL indisponible") from exc


def fetch(cur, query, params=()):
    cur.execute(query, params)
    return cur.fetchall()


def label_for(i):
    return i["nom"] or f"Identité {i['identite_id']}"


def vigilance(links):
    """Indicateur explicable, non score de probabilité ni verdict de fraude."""
    levels = Counter(str(l["niveau"] or "") for l in links)
    direct = sum(1 for l in links if l["cible"] == "bl_entite" and
                 l["niveau"] == "certain")
    if direct:
        band, reason = "elevee", "Au moins une correspondance directe certaine à la blacklist"
    elif any(l["cible"] == "bl_entite" and l["niveau"] == "probable" for l in links):
        band, reason = "a_examiner", "Correspondance probable avec la blacklist"
    elif links:
        band, reason = "information", "Liens de registre ou indices à examiner"
    else:
        band, reason = "aucun_lien_detecte", "Aucun lien enregistré pour les identités du dossier"
    return {
        "niveau_vigilance": band,
        "motif": reason,
        "nb_liens": len(links),
        "repartition_niveaux": dict(levels),
        "avertissement": "Indicateur technique non validé métier : ne préjuge pas d'une fraude",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dossiers/{dossier_ref}/graphe")
def graphe_dossier(
    dossier_ref: str,
    max_liens: int = Query(default=500, ge=1, le=2000),
):
    # Les identités appartiennent au dossier à travers af_dossier_identite.
    with database() as con:
        with con.cursor() as cur:
            dossiers = fetch(cur, "SELECT ref,lot,verdict,statut_analyse FROM af_dossier WHERE ref=%s", (dossier_ref,))
            if not dossiers:
                raise HTTPException(404, detail="Dossier inconnu")
            identities = fetch(cur, """SELECT DISTINCT i.identite_id,i.type_identite,i.nom,
                i.cle,i.niveau_cle FROM af_identite i
                JOIN af_dossier_identite di ON di.identite_id=i.identite_id
                WHERE di.dossier_ref=%s ORDER BY i.identite_id""", (dossier_ref,))
            ident_ids = [i["identite_id"] for i in identities]
            # Une requête avec ANY() évite les N+1 lectures.
            relations = fetch(cur, """SELECT relation_id,pp_identite_id,pm_identite_id,
                role,qualite,parts,dossier_ref FROM af_relation
                WHERE dossier_ref=%s AND pp_identite_id=ANY(%s)
                  AND pm_identite_id=ANY(%s) ORDER BY relation_id LIMIT %s""",
                (dossier_ref,ident_ids,ident_ids,max_liens))
            links = fetch(cur, """SELECT lien_id,regle,niveau,identite_id,dossier_ref,
                cible,cible_id,cle_type,detail FROM af_lien
                WHERE identite_id=ANY(%s) OR (dossier_ref=%s AND identite_id IS NULL)
                ORDER BY lien_id LIMIT %s""", (ident_ids,dossier_ref,max_liens))

    nodes = {}
    edges = {}
    def node(k,typ,text,**data):
        if k not in nodes:
            nodes[k] = {"id":k,"type":typ,"label":text,**data}

    def edge(k,source,target,typ,**data):
        edges[k] = {"id":k,"source":source,"target":target,"type":typ,**data}

    dossier_node = f"dossier:{dossier_ref}"
    node(dossier_node,"dossier",dossier_ref)
    for i in identities:
        k = f"identite:{i['identite_id']}"
        node(k,"personne" if i["type_identite"] == "PP" else "societe",label_for(i),
             identite_id=i["identite_id"],niveau_cle=i["niveau_cle"])
        edge(f"mention:{dossier_ref}:{i['identite_id']}",dossier_node,k,"apparait_dans")
    for r in relations:
        source,target = f"identite:{r['pp_identite_id']}",f"identite:{r['pm_identite_id']}"
        edge(f"relation:{r['relation_id']}",source,target,"relation",role=r["role"],
             qualite=r["qualite"],parts=r["parts"])
    for l in links:
        source = f"identite:{l['identite_id']}" if l["identite_id"] is not None else dossier_node
        target = f"{l['cible']}:{l['cible_id']}"
        node(target,l["cible"],str(l["cible_id"]))
        edge(f"lien:{l['lien_id']}",source,target,"antifraude",regle=l["regle"],
             niveau=l["niveau"],cle_type=l["cle_type"],detail=l["detail"])
    return {
        "dossier": dossiers[0],
        "graphe": {"nodes":list(nodes.values()),"edges":list(edges.values())},
        "vigilance":vigilance(links),
        "limite_liens":max_liens,
        "troncature_possible":len(links)>=max_liens or len(relations)>=max_liens,
    }


@app.get("/api/dossiers/{dossier_ref}/risque")
def risque_dossier(dossier_ref: str):
    # Réutilise le même calcul pour ne pas diverger entre écran et API.
    result = graphe_dossier(dossier_ref)
    return {"dossier_ref":dossier_ref,**result["vigilance"]}


@app.get("/api/dossiers/{dossier_ref}/liens")
def liens_dossier(dossier_ref: str):
    with database() as con:
        with con.cursor() as cur:
            if not fetch(cur,"SELECT ref FROM af_dossier WHERE ref=%s",(dossier_ref,)):
                raise HTTPException(404,detail="Dossier inconnu")
            links = fetch(cur,"""SELECT l.lien_id,l.regle,l.niveau,l.identite_id,
                l.dossier_ref,l.cible,l.cible_id,l.cle_type,l.detail
                FROM af_lien l WHERE l.identite_id IN (
                    SELECT identite_id FROM af_dossier_identite WHERE dossier_ref=%s)
                OR (l.dossier_ref=%s AND l.identite_id IS NULL)
                ORDER BY l.lien_id LIMIT 2000""",(dossier_ref,dossier_ref))
    return {"dossier_ref":dossier_ref,"liens":links,"total_retourne":len(links)}
