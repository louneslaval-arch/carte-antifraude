"""Import de fichiers JSON antifraude dans le pipeline PostgreSQL local.

Simulation (aucune écriture) : python ingester_json_postgresql.py chemin.json
Import : python ingester_json_postgresql.py chemin.json --appliquer
Un dossier peut aussi être fourni : ses fichiers *.json sont traités par ordre alphabétique.
"""

import argparse
import getpass
import json
import os
import re
from pathlib import Path
from zipfile import ZipFile

import psycopg

from pipeline.couches import (
    c0_brut_postgresql as c0,
    c1_faits_postgresql as c1,
    c2_identites_postgresql as c2,
    c3_dossier_postgresql as c3,
    c5_graphe_postgresql as c5,
    c6_regles_postgresql as c6,
    c7_relations_complementaires as c7,
)
from pipeline.couches.af11_contreparties import reconstruire_af11

from pipeline.couches.c5_persistance_postgresql import (
    enregistrer_chemins,
    reconstruire_reseau,
)
def relations_c7(dossier):
    """Relations attestées facultatives, jamais inférées des noms ou pièces.

    Absence de la clé : ne pas toucher aux relations C7 déjà enregistrées.
    Liste vide explicite : supprimer les anciennes relations lors de l'import.
    """
    if 'relationsComplementaires' not in dossier:
        return None
    elements = dossier['relationsComplementaires']
    if not isinstance(elements, list):
        raise ValueError('relationsComplementaires doit être une liste')
    for element in elements:
        c7.preparer(element)
    return elements


def fichiers_json(chemin):
    if chemin.is_file():
        if chemin.suffix.lower() not in ('.json', '.zip'):
            raise ValueError('Le fichier doit avoir l’extension .json ou .zip')
        return [chemin]
    if chemin.is_dir():
        fichiers = sorted(p for p in chemin.glob('*.json') if p.is_file())
        if not fichiers:
            raise ValueError('Aucun fichier .json dans le dossier')
        return fichiers
    raise FileNotFoundError('Chemin JSON introuvable')


def lire_fichier(fichier):
    """Pour les ZIP plateforme, ne retenir que les dossiers complets GET /api/dossiers/{ref}."""
    if fichier.suffix.lower() == '.zip':
        with ZipFile(fichier) as archive:
            noms = sorted(n for n in archive.namelist()
                          if re.search(r'/api/GET_api_dossiers_[^/]+\.json$', n)
                          and not n.endswith(('_liste.json', '_monitoring.json'))
                          and '_controls_' not in n)
            if not noms:
                raise ValueError('Aucun dossier complet /api/dossiers/{ref} trouvé dans le ZIP')
            return [(f'{fichier.name}:{nom.split("/")[-1]}',
                     extraire_dossiers(json.loads(archive.read(nom).decode('utf-8-sig')))) for nom in noms]
    with fichier.open(encoding='utf-8-sig') as flux:
        return [(fichier.name, extraire_dossiers(json.load(flux)))]


def extraire_dossiers(document):
    """Accepte un dossier, une liste, ou un objet contenant `dossiers`."""
    if isinstance(document, list):
        dossiers = document
    elif isinstance(document, dict) and isinstance(document.get('dossiers'), list):
        dossiers = document['dossiers']
    elif isinstance(document, dict):
        dossiers = [document]
    else:
        raise ValueError('Structure JSON non reconnue')
    for dossier in dossiers:
        if not isinstance(dossier, dict) or not all(dossier.get(c) for c in ('id', 'ref', 'updatedAt')):
            raise ValueError('Dossier sans id, ref ou updatedAt')
    return dossiers


def main():
    parser = argparse.ArgumentParser(description='Ingestion des JSON antifraude vers PostgreSQL local')
    parser.add_argument('chemin', type=Path, help='Fichier .json ou dossier de fichiers .json')
    parser.add_argument('--appliquer', action='store_true', help='Écrit dans la base PostgreSQL')
    args = parser.parse_args()

    fichiers = fichiers_json(args.chemin)
    lots = [lot for fichier in fichiers for lot in lire_fichier(fichier)]

    total = sum(len(dossiers) for _, dossiers in lots)
    # Vérifier aussi les rôles déclarés pendant la simulation, avant toute écriture.
    relations = [relations_c7(dossier) for _, dossiers in lots for dossier in dossiers]
    declarations = sum(len(elements) for elements in relations if elements is not None)
    print(f'JSON valides : {len(lots)} fichier(s), {total} dossier(s)')
    print(f'Relations C7 explicitement déclarées : {declarations}')
    if not args.appliquer:
        print('SIMULATION OK — aucune écriture. Ajouter --appliquer pour importer.')
        return

    # On limite volontairement cet importeur initial à la base locale de recette.
    dsn = os.getenv('CARTE_BASE_CLIENT')
    if dsn:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
        if (info.get('dbname') != 'eqdom_pipeline_test'
                or info.get('host') not in ('127.0.0.1', 'localhost')
                or str(info.get('port', '')) != '55432'):
            raise ValueError('Seule la base locale eqdom_pipeline_test est autorisée pour cet importeur')
        connexion = psycopg.connect(dsn)
    else:
        connexion = psycopg.connect(
            host='127.0.0.1', port=55432, dbname='eqdom_pipeline_test', user='postgres',
            password=getpass.getpass('Mot de passe PostgreSQL local : '),
        )

    with connexion as cx:
        passage = c0.ouvrir_passage(cx, 'json_antifraude_local', 'lot')
        nouvelles = 0
        erreurs = 0
        for fichier, dossiers in lots:
            for dossier in dossiers:
                ref = dossier['ref']
                try:
                    if c0.recevoir(cx, passage, dossier):
                        nouvelles += 1
                    for couche in (c1, c2, c3):
                        couche.traiter(cx, ref)
                    elements = relations_c7(dossier)
                    if elements is not None:
                        c7.traiter(cx, ref, elements)
                    c5.traiter(cx, ref)
                except Exception as exc:
                    cx.rollback()
                    erreurs += 1
                    print(f'Échec de traitement : {type(exc).__name__} ({fichier})')
        c0.fermer_passage(cx, passage, total, nouvelles)

        # Recalculer les chemins de tous les dossiers
        references = [
            ligne[0]
            for ligne in cx.execute(
                'SELECT ref FROM c3_dossier ORDER BY ref'
            ).fetchall()
        ]

        total_chemins = 0

        for ref in references:
            total_chemins += enregistrer_chemins(cx, ref)

        # Actualiser les composantes et les mesures C5
        statistiques = reconstruire_reseau(cx)

        print(f'C5 : {total_chemins} chemins enregistrés')
        print(f'C5 : {statistiques}')

        # Recalculer les alertes C6
        c6.reconstruire_tout(cx)
        candidats_af11 = reconstruire_af11(cx)
        print(f'AF11 : {candidats_af11} correspondance(s) à vérifier')
    print(f'Import terminé : {total} reçu(s), {nouvelles} nouvelle(s) version(s), {erreurs} échec(s)')
    if erreurs:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
