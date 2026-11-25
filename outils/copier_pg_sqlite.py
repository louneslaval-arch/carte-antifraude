#!/usr/bin/env python3
"""Copie la base PostgreSQL de la carte (tables du kit : bl_*, rc_*, af_*, cle, noeud, arete…) dans un fichier SQLite.

Les scripts du kit (`carte_globale.py`, `chaines_dessin.py`, `publier_carte.py`, `publier_globale.py`) lisent une base
SQLite construite par `construire_base.py` et `charger_antifraude.py` ; quand cette base vit dans PostgreSQL, ce script
en fait une copie aux mêmes noms de tables et de colonnes, avec les index simples, sans rien transformer d'autre que
la forme des valeurs (booléens en 0 et 1, dates en texte, JSON en texte).

- Lecture seule (`default_transaction_read_only`), par lots, curseur côté serveur.
- Copie écrite dans un fichier `.partiel`, renommé à la fin : une coupure ne laisse pas de base à moitié faite.
- Console : nom de chaque table et nombre de lignes, rien d'autre. Une erreur ne cite que son type.
- Données réelles : lancé par Lounès seulement, avec CARTE_DONNEES_REELLES=1, copie rangée hors du dépôt.

Usage : CARTE_SOURCE_PG='host=… dbname=… user=…' python outils/copier_pg_sqlite.py --sortie CHEMIN [--schema public]
(mot de passe dans ~/.pgpass).
"""
import argparse
import datetime
import decimal
import json
import os
import re
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ENTIERS = {'smallint', 'integer', 'bigint', 'boolean'}
_REELS = {'real', 'double precision', 'numeric', 'decimal'}


def type_sqlite(type_pg):
    t = type_pg.lower()
    if t in _ENTIERS:
        return 'INTEGER'
    if t in _REELS:
        return 'REAL'
    if t == 'bytea':
        return 'BLOB'
    return 'TEXT'


def valeur(v):
    """Valeur de PostgreSQL mise à la forme que les scripts du kit lisaient dans SQLite."""
    if v is None or isinstance(v, (str, int, float)) and not isinstance(v, bool):
        return v
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime.datetime):
        return v.isoformat(sep=' ')
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    if isinstance(v, (memoryview, bytearray)):
        return bytes(v)
    return str(v)


def _q(nom):
    return '"' + nom.replace('"', '""') + '"'


def structure(source, schema='public'):
    """Tables du schéma et leurs colonnes, dans l'ordre : {table: [(colonne, type), …]}."""
    tables = {}
    for table, colonne, genre in source.execute(
            'SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c '
            'JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name '
            "WHERE c.table_schema = %s AND t.table_type = 'BASE TABLE' ORDER BY c.table_name, c.ordinal_position",
            (schema,)).fetchall():
        tables.setdefault(table, []).append((colonne, genre))
    return tables


def index_simples(source, schema='public'):
    """Index sur des colonnes nommées (sans expression) : [(nom, table, [colonnes], unique)]."""
    trouves = []
    for nom, table, definition in source.execute(
            'SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname = %s ORDER BY 1', (schema,)):
        m = re.search(r'USING btree \(([^()]+)\)\s*$', definition)
        if not m:
            continue
        colonnes = [c.strip().strip('"') for c in m.group(1).split(',')]
        if all(re.fullmatch(r'\w+', c) for c in colonnes):
            trouves.append((nom, table, colonnes, definition.startswith('CREATE UNIQUE')))
    return trouves


def _lignes(source, texte, lot):
    if isinstance(source, sqlite3.Connection):
        curseur = source.execute(texte)
    else:
        curseur = source.cursor(name='copie_carte')          # curseur côté serveur : la table n'est pas chargée d'un coup
        curseur.execute(texte)
    try:
        while True:
            paquet = curseur.fetchmany(lot)
            if not paquet:
                return
            yield paquet
    finally:
        curseur.close()


def copier(source, sortie, tables, index=(), lot=20000, afficher=False):
    """Copie chaque table de `tables` ({table: [(colonne, type_pg)]}) dans le fichier SQLite `sortie`."""
    partiel = sortie + '.partiel'
    if os.path.exists(partiel):
        os.remove(partiel)
    comptes = {}
    cible = sqlite3.connect(partiel)
    try:
        cible.execute('PRAGMA journal_mode = OFF')
        cible.execute('PRAGMA synchronous = OFF')
        for table, colonnes in tables.items():
            cible.execute(f'CREATE TABLE {_q(table)} ('
                          + ', '.join(f'{_q(c)} {type_sqlite(t)}' for c, t in colonnes) + ')')
            noms = ', '.join(_q(c) for c, _ in colonnes)
            insertion = f'INSERT INTO {_q(table)} ({noms}) VALUES ({", ".join("?" * len(colonnes))})'
            n = 0
            for paquet in _lignes(source, f'SELECT {noms} FROM {_q(table)}', lot):
                cible.executemany(insertion, [tuple(valeur(v) for v in ligne) for ligne in paquet])
                n += len(paquet)
            cible.commit()
            comptes[table] = n
            if afficher:
                print(f'  {table} : {n} lignes', flush=True)
        faits = 0
        for nom, table, colonnes, unique in index:
            if table in tables:
                cible.execute(f'CREATE {"UNIQUE " if unique else ""}INDEX {_q(nom)} ON {_q(table)} '
                              f'({", ".join(_q(c) for c in colonnes)})')
                faits += 1
        cible.commit()
        if afficher and index:
            print(f'  index recréés : {faits}', flush=True)
        cible.close()
        os.replace(partiel, sortie)
    except BaseException:
        cible.close()
        if os.path.exists(partiel):
            os.remove(partiel)
        raise
    return comptes


def _dans_le_depot(chemin):
    return os.path.realpath(chemin).startswith(os.path.realpath(RACINE) + os.sep)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--sortie', required=True, help='fichier SQLite à écrire, hors du dépôt')
    ap.add_argument('--schema', default='public')
    a = ap.parse_args(argv)
    adresse = os.environ.get('CARTE_SOURCE_PG')
    if not adresse:
        print('arrêt : variable absente : CARTE_SOURCE_PG', file=sys.stderr)
        return 2
    if _dans_le_depot(a.sortie):
        print('arrêt : la copie se range hors du dépôt (par exemple dans ~/antifraude-donnees)', file=sys.stderr)
        return 2
    if os.environ.get('CARTE_DONNEES_REELLES') != '1':
        print('arrêt : données réelles : la commande doit commencer par CARTE_DONNEES_REELLES=1', file=sys.stderr)
        return 2
    try:
        import psycopg
        source = psycopg.connect(adresse, options='-c default_transaction_read_only=on', connect_timeout=15)
        source.read_only = True
    except Exception as e:                            # noqa: BLE001  le message d'origine peut citer l'adresse
        print(f'arrêt : connexion à la base impossible ({type(e).__name__})', file=sys.stderr)
        return 1
    try:
        tables = structure(source, a.schema)
        print(f'tables trouvées : {len(tables)}', flush=True)
        comptes = copier(source, a.sortie, tables, index=index_simples(source, a.schema), afficher=True)
    except Exception as e:                            # noqa: BLE001  jamais de contenu ni d'adresse dans la sortie
        print(f'arrêt : copie interrompue ({type(e).__name__})', file=sys.stderr)
        return 1
    finally:
        source.close()
    print(f'copie terminée : {len(comptes)} tables, {sum(comptes.values())} lignes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
