"""Audit en lecture seule du rattachement C2/C3 dans PostgreSQL local.

Commande : python verifier_c2_c3_postgresql.py
N'affiche jamais de CIN, de nom, de référence ou d'identifiant individuel.
"""

import getpass
import psycopg


REQUETES = {
    "Dossiers C3": "SELECT COUNT(*) FROM c3_dossier",
    "Mentions personnelles C2": "SELECT COUNT(*) FROM c2_mention WHERE type_fiche = 'PP'",
    "Fiches personnes C2": "SELECT COUNT(*) FROM c2_personne",
    "Dossiers avec CIN déclaré": "SELECT COUNT(*) FROM c3_dossier WHERE civil_cin IS NOT NULL",
    "Dossiers avec CIN relié à une fiche": """
        SELECT COUNT(*) FROM c3_dossier d
        WHERE d.civil_cin IS NOT NULL AND EXISTS (
            SELECT 1 FROM c2_mention m
            WHERE m.ref = d.ref AND m.type_fiche = 'PP'
              AND m.cin_effectif = d.civil_cin AND m.fiche IS NOT NULL
        )
    """,
    "CIN avec plusieurs fiches (conflits possibles)": """
        SELECT COUNT(*) FROM (
            SELECT cin_effectif FROM c2_mention
            WHERE type_fiche = 'PP' AND cin_effectif IS NOT NULL
            GROUP BY cin_effectif HAVING COUNT(DISTINCT fiche) > 1
        ) x
    """,
    "Fiches présentes dans plusieurs dossiers": """
        SELECT COUNT(*) FROM (
            SELECT fiche FROM c2_mention
            WHERE source = 'v2' AND type_fiche = 'PP' AND fiche IS NOT NULL
            GROUP BY fiche HAVING COUNT(DISTINCT ref) > 1
        ) x
    """,
    "Mentions rattachées à une fiche inexistante": """
        SELECT COUNT(*) FROM c2_mention m
        WHERE m.type_fiche = 'PP' AND m.fiche IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM c2_personne p WHERE p.identifiant = m.fiche)
    """,
    "Homonymies à examiner": """
        SELECT COUNT(*) FROM c2_correspondance_mention
        WHERE statut = 'homonymie'
    """,
}


def main():
    password = getpass.getpass("Mot de passe PostgreSQL local : ")
    with psycopg.connect(
        host="127.0.0.1", port=55432, user="postgres",
        dbname="eqdom_pipeline_test", password=password,
        options="-c default_transaction_read_only=on",
    ) as cx:
        valeurs = {}
        for titre, requete in REQUETES.items():
            valeurs[titre] = cx.execute(requete).fetchone()[0]
            print(f"{titre} : {valeurs[titre]}")
        if valeurs["Mentions rattachées à une fiche inexistante"]:
            print("ALERTE : des mentions renvoient vers des fiches absentes.")
        else:
            print("Intégrité des références C2 : OK")
        print("Audit terminé — aucune donnée modifiée.")


if __name__ == "__main__":
    main()
