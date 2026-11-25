import re
import unicodedata


def normaliser_nom(valeur):
    if not isinstance(valeur, str):
        return ""

    texte = unicodedata.normalize("NFKD", valeur.upper())
    texte = "".join(
        c for c in texte
        if not unicodedata.combining(c)
    )

    return " ".join(
        re.findall(r"[A-Z0-9]+", texte)
    )


def rechercher_contrepartie(nom, personnes_liste_noire):
    """
    Recherche des noms identiques après normalisation.
    Ne confirme jamais une identité sur le seul nom.
    """

    nom_normalise = normaliser_nom(nom)

    if not nom_normalise:
        return []

    correspondances = []

    for personne in personnes_liste_noire:
        nom_liste = normaliser_nom(personne.get("nom"))

        if nom_normalise == nom_liste:
            correspondances.append({
                "regle": "AF11",
                "nom_contrepartie": nom,
                "identifiant_liste_noire": personne.get("id"),
                "statut": "a_verifier",
                "motif": "Correspondance exacte du nom normalise",
            })

    return correspondances
def reconstruire_af11(cx):
    """Recherche les contreparties présentes sur liste noire."""

    personnes = [
        {"id": identifiant, "nom": nom}
        for identifiant, nom in cx.execute(
            """
            SELECT identifiant, nom
            FROM c2_personne
            WHERE inscrit = 1
              AND nom IS NOT NULL
            """
        ).fetchall()
    ]

    operations = cx.execute(
        """
        SELECT ref, upstream_piece_id, rang_mois,
               rang, contrepartie
        FROM c3_operation
        WHERE contrepartie IS NOT NULL
        """
    ).fetchall()

    candidats = []

    for ref, piece, mois, rang, nom in operations:
        correspondances = rechercher_contrepartie(
            nom, personnes
        )

        for correspondance in correspondances:
            candidats.append((
                ref,
                piece,
                mois,
                rang,
                correspondance["identifiant_liste_noire"],
                correspondance["motif"]
            ))

    with cx.transaction():
        with cx.cursor() as cur:
            cur.execute("DELETE FROM c6_af11_candidat")

            if candidats:
                cur.executemany(
                    """
                    INSERT INTO c6_af11_candidat (
                        ref, upstream_piece_id, rang_mois,
                        rang, identifiant_inscrit, motif
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    candidats
                )

    return len(candidats)