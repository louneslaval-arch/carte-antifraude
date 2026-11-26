"""Lecture seule du graphe antifraude PostgreSQL, avec limites explicites.

Le statut 'liste_noire' qualifie l'entité cible, pas la culpabilité du client.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os

import psycopg
from psycopg.rows import dict_row


def _opaque(prefix: str, value: object, secret: str) -> str:
    digest = hmac.new(secret.encode(), str(value).encode(), hashlib.sha256).hexdigest()[:20]
    return f"{prefix}:{digest}"


class CarteGlobalePG:
    def __init__(self, url: str, secret: str):
        if not url:
            raise ValueError("URL PostgreSQL manquante")
        if len(secret) < 32:
            raise ValueError("AF_GRAPH_SECRET doit contenir au moins 32 caractères")
        self.url, self.secret = url, secret

    @contextmanager
    def connexion(self):
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=8) as cx:
            with cx.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = '15000ms'")
            yield cx

    def resume(self):
        with self.connexion() as cx:
            lignes = cx.execute("""
                SELECT
                  (SELECT count(*) FROM af_identite) AS identites,
                  (SELECT count(*) FROM af_relation) AS relations,
                  (SELECT count(*) FROM af_lien WHERE cible = 'bl_entite') AS liens_liste_noire,
                  (SELECT count(*) FROM bl_entite) AS entites_liste_noire
            """).fetchone()
        return dict(lignes)

    def graphe(self, limite_identites: int = 150, debut: int = 0):
        """Une fenêtre stable d'identités et les arêtes internes + cibles LN.

        Les liens hors fenêtre ne sont pas artificiellement présentés comme complets.
        """
        if not 1 <= limite_identites <= 500 or not 0 <= debut <= 1_000_000:
            raise ValueError("Limites de pagination invalides")
        with self.connexion() as cx:
            identites = cx.execute("""
                SELECT identite_id, type_identite, nom
                FROM af_identite ORDER BY identite_id LIMIT %s OFFSET %s
            """, (limite_identites, debut)).fetchall()
            ids = [x['identite_id'] for x in identites]
            if not ids:
                return {'noeuds': [], 'liens': [], 'pagination': {'debut': debut, 'taille': 0,
                        'suite_possible': False}, 'partiel': True}

            relations = cx.execute("""
                SELECT relation_id, pp_identite_id, pm_identite_id, role
                FROM af_relation
                WHERE pp_identite_id = ANY(%s) AND pm_identite_id = ANY(%s)
                ORDER BY relation_id LIMIT 3000
            """, (ids, ids)).fetchall()
            noirs = cx.execute("""
                SELECT l.lien_id, l.identite_id, l.regle, l.niveau,
                       b.entite_id, b.nom_affiche, b.type_entite
                FROM af_lien l JOIN bl_entite b
                  ON l.cible = 'bl_entite' AND l.cible_id = b.entite_id::text
                WHERE l.identite_id = ANY(%s)
                ORDER BY l.lien_id LIMIT 3000
            """, (ids,)).fetchall()

        noeuds = {}
        liens = []
        for i in identites:
            k = _opaque('i', i['identite_id'], self.secret)
            noeuds[k] = {'id': k, 'type': 'societe' if i['type_identite'] in ('PM', 'societe')
                         else 'personne', 'nom': i['nom'] or 'Identité sans nom',
                         'inscrit': False}
        for r in relations:
            liens.append({'de': _opaque('i', r['pp_identite_id'], self.secret),
                          'vers': _opaque('i', r['pm_identite_id'], self.secret),
                          'code': r['role'] or 'relation', 'nature': 'relation'})
        for l in noirs:
            k = _opaque('bl', l['entite_id'], self.secret)
            noeuds[k] = {'id': k, 'type': 'societe' if l['type_entite'] in ('PM', 'societe')
                         else 'personne', 'nom': l['nom_affiche'] or 'Entité liste noire',
                         'inscrit': True}
            liens.append({'de': _opaque('i', l['identite_id'], self.secret), 'vers': k,
                          'code': l['regle'] or 'liste_noire', 'niveau': l['niveau'],
                          'nature': 'liste_noire'})
        return {'noeuds': list(noeuds.values()), 'liens': liens,
                'pagination': {'debut': debut, 'taille': len(identites),
                               'suite_possible': len(identites) == limite_identites},
                'partiel': True,
                'avertissement': 'Liens indicatifs : une correspondance ne prouve pas une fraude.'}


def depuis_environnement():
    return CarteGlobalePG(os.environ.get('AF_DATABASE_URL', ''),
                          os.environ.get('AF_GRAPH_SECRET', ''))
