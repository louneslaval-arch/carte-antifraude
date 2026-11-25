"""Test local du pipeline C0-C5 avec deux dossiers entièrement fictifs.

Usage : python test_relations_postgresql.py
Base cible : eqdom_pipeline_test (PostgreSQL local, port 55432).
"""

import getpass

import psycopg

from pipeline.couches import (
    c0_brut_postgresql as c0,
    c1_faits_postgresql as c1,
    c2_identites_postgresql as c2,
    c3_dossier_postgresql as c3,
    c5_graphe_postgresql as c5,
)


def dossier(reference, titulaire, numero):
    instant = '2026-11-19T14:00:00Z'
    return {
        'id': reference,
        'ref': reference,
        'createdAt': instant,
        'updatedAt': instant,
        'analysisStatus': 'COMPLETE',
        'verdict': 'CONFORME',
        'verdictProvisional': False,
        'alertsMinor': 0,
        'alertsMajor': 0,
        'alertsCritical': 0,
        'commentaireAlerte': False,
        'pieces': [{
            'upstreamPieceId': f'RELEVE_TEST_{numero}',
            'type': 'RELEVE_BANCAIRE',
            'source': 'AMONT',
            'extractionStatus': 'COMPLETE',
            'fields': {
                'titulaire_compte': titulaire,
                'rib': '999999999999999999999999',
                'banque': 'BANQUE EXEMPLE',
            },
        }],
    }


def main():
    mot_de_passe = getpass.getpass('Mot de passe PostgreSQL local: ')
    with psycopg.connect(
        host='127.0.0.1', port=55432, dbname='eqdom_pipeline_test',
        user='postgres', password=mot_de_passe,
    ) as cx:
        passage = c0.ouvrir_passage(cx, 'test_relations_fictives', 'lot')
        references = ('TEST_RIB_A_001', 'TEST_RIB_B_001')
        for indice, (reference, nom) in enumerate(zip(
            references, ('ALPHA EXEMPLE', 'BETA EXEMPLE'),
        ), start=1):
            c0.recevoir(cx, passage, dossier(reference, nom, indice))
        c0.fermer_passage(cx, passage, 2, 2)

        for reference in references:
            c1.traiter(cx, reference)
            c2.traiter(cx, reference)
            c3.traiter(cx, reference)
            c5.traiter(cx, reference)

        result = cx.execute(
            "SELECT COUNT(*), COUNT(DISTINCT de), COUNT(DISTINCT vers) "
            "FROM c5_arete WHERE code = 'RIB' AND ref = ANY(%s)",
            (list(references),),
        ).fetchone()
        aretes, titulaires, ribs = result
        print(f'Aretes RIB: {aretes}; fiches distinctes: {titulaires}; noeuds RIB: {ribs}')
        if (aretes, titulaires, ribs) != (2, 2, 1):
            raise AssertionError('Les deux dossiers ne sont pas relies au meme RIB.')
        print('TEST RELATIONS OK')


if __name__ == '__main__':
    main()
