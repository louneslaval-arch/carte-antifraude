"""Bilan de l'ingestion C0-C5, en lecture seule, sans afficher de données personnelles.

Usage : python valider_pipeline_json.py
Base : PostgreSQL local eqdom_pipeline_test, port 55432.
"""

import getpass

import psycopg


MESURES = (
    ("Dossiers JSON reçus (C0)", "SELECT COUNT(DISTINCT ref) FROM c0_dossier_brut"),
    ("Versions brutes conservées (C0)", "SELECT COUNT(*) FROM c0_dossier_brut"),
    ("Dossiers du miroir", 'SELECT COUNT(*) FROM "Dossier"'),
    ("Dossiers structurés (C3)", "SELECT COUNT(*) FROM c3_dossier"),
    ("Dossiers sans C3", """
        SELECT COUNT(*) FROM (SELECT DISTINCT ref FROM c0_dossier_brut) a
        WHERE NOT EXISTS (SELECT 1 FROM c3_dossier d WHERE d.ref = a.ref)
    """),
    ("Pièces extraites (C1)", "SELECT COUNT(*) FROM c1_piece"),
    ("Pièces sans champ relu (C1)", "SELECT COUNT(*) FROM c1_piece WHERE nb_champs_relus = 0"),
    ("Listes d'objets ignorées (C1)", "SELECT COALESCE(SUM(nb_listes_ignorees),0) FROM c1_piece"),
    ("Champs extraits (C1)", "SELECT COUNT(*) FROM c1_fait"),
    ("Champs non reconnus (C1)", "SELECT COUNT(*) FROM c1_fait WHERE cle_connue = 0"),
    ("Champs avec statut non normal (C1)", "SELECT COUNT(*) FROM c1_fait WHERE statut <> 'normal'"),
    ("Mentions personnes (C2)", "SELECT COUNT(*) FROM c2_mention WHERE type_fiche = 'PP'"),
    ("Mentions sociétés (C2)", "SELECT COUNT(*) FROM c2_mention WHERE type_fiche = 'PM'"),
    ("Fiches personnes (C2)", "SELECT COUNT(*) FROM c2_personne"),
    ("Fiches sociétés (C2)", "SELECT COUNT(*) FROM c2_societe"),
    ("Relations professionnelles (C5)", "SELECT COUNT(*) FROM c5_arete WHERE type = 'role'"),
    ("Identifiants partagés (C5)", "SELECT COUNT(*) FROM c5_arete WHERE type = 'identifiant'"),
)


def main():
    password = getpass.getpass("Mot de passe PostgreSQL local : ")
    with psycopg.connect(host='127.0.0.1', port=55432, dbname='eqdom_pipeline_test',
                         user='postgres', password=password,
                         options='-c default_transaction_read_only=on') as cx:
        valeurs = {}
        for titre, sql in MESURES:
            valeurs[titre] = cx.execute(sql).fetchone()[0]
            print(f'{titre} : {valeurs[titre]}')
    if valeurs['Dossiers sans C3']:
        print('À corriger : certains dossiers reçus ne sont pas structurés en C3.')
    if valeurs['Champs non reconnus (C1)'] or valeurs["Listes d'objets ignorées (C1)"]:
        print('À examiner : des champs ou listes n’ont pas été intégrés aux tables structurées.')
    print('Bilan terminé : aucune donnée modifiée.')


if __name__ == '__main__':
    main()
