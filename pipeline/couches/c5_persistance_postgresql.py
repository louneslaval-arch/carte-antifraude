from psycopg.types.json import Jsonb
from pipeline.couches.c5_graphe_postgresql import chemins
import hashlib
from collections import defaultdict

def enregistrer_chemins(cx, ref):
    """Calcule et enregistre les chemins C5 d'un dossier."""

    resultats = chemins(cx, ref)

    with cx.transaction():
        cx.execute(
            "DELETE FROM c5_chemin WHERE ref = %s",
            (ref,)
        )

        for chemin in resultats:
            cx.execute(
                """
                INSERT INTO c5_chemin (
                    ref, cible, longueur, force, niveau,
                    homonymie, foyer, etapes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ref,
                    chemin["cible"],
                    chemin["longueur"],
                    chemin["force"],
                    chemin["niveau"],
                    chemin["homonymie"],
                    chemin["foyer"],
                    Jsonb(chemin["etapes"]),
                )
            )

    return len(resultats)


def reconstruire_reseau(cx):
    """Reconstruit les composantes et les mesures du graphe C5."""

    aretes = cx.execute(
        'SELECT de, vers FROM c5_arete'
    ).fetchall()

    noeuds = {
        n for (n,) in cx.execute(
            'SELECT noeud FROM c5_compteur'
        ).fetchall()
    }

    voisins = defaultdict(set)
    parent = {}

    def trouver(x):
        parent.setdefault(x, x)

        if parent[x] != x:
            parent[x] = trouver(parent[x])

        return parent[x]

    def unir(a, b):
        ra, rb = trouver(a), trouver(b)

        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for a, b in aretes:
        noeuds.update((a, b))
        voisins[a].add(b)
        voisins[b].add(a)
        unir(a, b)

    composantes = defaultdict(list)

    for noeud in sorted(noeuds):
        composantes[trouver(noeud)].append(noeud)

    chemins_par_cible = dict(
        cx.execute(
            'SELECT cible, COUNT(*) FROM c5_chemin GROUP BY cible'
        ).fetchall()
    )

    lignes_composantes = []
    lignes_mesures = []

    for membres in composantes.values():
        identifiant = hashlib.sha256(
            '|'.join(membres).encode('utf-8')
        ).hexdigest()[:24]

        composante_id = f'c5_comp_{identifiant}'
        taille = len(membres)

        for noeud in membres:
            lignes_composantes.append(
                (composante_id, noeud)
            )

            lignes_mesures.append((
                noeud,
                len(voisins[noeud]),
                taille,
                chemins_par_cible.get(noeud, 0)
            ))

    with cx.transaction():
        with cx.cursor() as cur:
            cur.execute('DELETE FROM c5_composante')
            cur.execute('DELETE FROM c5_mesure')

            cur.executemany(
                '''
                INSERT INTO c5_composante(composante_id, noeud)
                VALUES (%s, %s)
                ''',
                lignes_composantes
            )

            cur.executemany(
                '''
                INSERT INTO c5_mesure(
                    noeud, degre, taille_composante,
                    nb_chemins_liste_noire
                )
                VALUES (%s, %s, %s, %s)
                ''',
                lignes_mesures
            )
    return {
        'noeuds': len(noeuds),
        'composantes': len(composantes),
        'mesures': len(lignes_mesures)
    }