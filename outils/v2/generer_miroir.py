#!/usr/bin/env python3
"""Génère le miroir de la base de la v2 de Kamal (couche 0) depuis `schema.prisma` : jamais écrit à la main.

Une table par modèle, aux noms de tables et de colonnes que PostgreSQL voit dans la base de la v2 (après `@map` et
`@@map`), entre guillemets ; mêmes clés primaires, unicités, clés étrangères et index ; énumérations en texte avec un
contrôle des valeurs ; valeurs par défaut littérales reprises (celles que Prisma calcule, `uuid()`, `now()`,
`@updatedAt`, ne le sont pas : le miroir reçoit des valeurs déjà posées par la v2).

Deux dialectes :
  sqlite      String, DateTime, Json et listes en TEXT ; Boolean en INTEGER contrôlé (0, 1) ; Float en REAL ;
  postgresql  TEXT, TIMESTAMP(3), JSONB, TEXT[], BOOLEAN, DOUBLE PRECISION, DATE pour `@db.Date`.

Fichiers écrits : `schema/010_miroir_v2.sql` (SQLite, appliqué par `pipeline/migrer.py`) et
`schema/postgresql/010_miroir_v2.sql` (appliqué à l'étape L). Une migration appliquée ne se modifie plus : si
`schema.prisma` change, `--verifier` échoue et la différence s'écrit dans une migration suivante, relue.

Usage : generer_miroir.py --ecrire | --verifier  [--schema FICHIER]
"""
import argparse
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import lire_prisma  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(ICI))
SCHEMA_DEFAUT = os.path.join(RACINE, 'import', 'kamal_structure', 'schema', 'schema.prisma')
SORTIES = {'sqlite': os.path.join(RACINE, 'schema', '010_miroir_v2.sql'),
           'postgresql': os.path.join(RACINE, 'schema', 'postgresql', '010_miroir_v2.sql')}
TYPES = {
    'sqlite': {'String': 'TEXT', 'Boolean': 'INTEGER', 'Int': 'INTEGER', 'BigInt': 'INTEGER', 'Float': 'REAL',
               'Decimal': 'TEXT', 'DateTime': 'TEXT', 'Json': 'TEXT', 'Bytes': 'BLOB'},
    'postgresql': {'String': 'TEXT', 'Boolean': 'BOOLEAN', 'Int': 'INTEGER', 'BigInt': 'BIGINT',
                   'Float': 'DOUBLE PRECISION', 'Decimal': 'DECIMAL', 'DateTime': 'TIMESTAMP(3)', 'Json': 'JSONB',
                   'Bytes': 'BYTEA'},
}


def _q(nom):
    return '"' + nom.replace('"', '""') + '"'


def _texte(valeur):
    return "'" + valeur.replace("'", "''") + "'"


def _type(c, dialecte):
    if c.enum:
        base = 'TEXT'
    elif c.type_natif == 'Date' and dialecte == 'postgresql':
        base = 'DATE'
    else:
        base = TYPES[dialecte][c.type]
    if c.liste:
        return 'TEXT[]' if dialecte == 'postgresql' else 'TEXT'      # SQLite : liste rangée en texte JSON
    return base


def _defaut(c, schema, dialecte):
    """Valeur par défaut littérale, ou None si Prisma la calcule (uuid(), now()) ou s'il n'y en a pas."""
    d = c.defaut
    if d is None or d.endswith(')'):
        return None
    if c.type == 'Boolean':
        return d if dialecte == 'postgresql' else {'true': '1', 'false': '0'}[d]
    if c.enum:
        return _texte(d)
    if d.startswith('"'):
        return _texte(d[1:-1])
    return d


def _colonne(c, schema, dialecte, modele):
    morceaux = [_q(c.colonne), _type(c, dialecte)]
    if not c.facultatif:
        morceaux.append('NOT NULL')
    defaut = _defaut(c, schema, dialecte)
    if defaut is not None:
        morceaux.append('DEFAULT ' + defaut)
    if modele.cle_primaire == [c.nom]:
        morceaux.append('PRIMARY KEY')
    if c.unique:
        morceaux.append('UNIQUE')
    if c.enum and not c.liste:
        valeurs = ', '.join(_texte(v.nom_base) for v in schema.enums[c.type].valeurs)
        morceaux.append(f'CHECK ({_q(c.colonne)} IN ({valeurs}))')
    if c.type == 'Boolean' and dialecte == 'sqlite':
        morceaux.append(f'CHECK ({_q(c.colonne)} IN (0, 1))')
    return '    ' + ' '.join(morceaux)


def _ordre(schema):
    """Modèles dans l'ordre où une table référencée est créée avant celle qui la référence."""
    faits, ordre = set(), []

    def visiter(m):
        if m.nom in faits:
            return
        faits.add(m.nom)
        for c in m.champs:
            if c.relation and c.relation_champs and c.type != m.nom:
                visiter(schema.modeles[c.type])
        ordre.append(m)
    for m in schema.modeles.values():
        visiter(m)
    return ordre


def sql(texte_prisma, dialecte):
    if dialecte not in TYPES:
        raise ValueError(f'dialecte inconnu : {dialecte}')
    schema = lire_prisma.lire(texte_prisma)
    lignes = ['-- Miroir de la base de la v2 de Kamal (couche 0), dialecte ' + dialecte + '.',
              '-- FICHIER GÉNÉRÉ par outils/v2/generer_miroir.py depuis schema.prisma : ne pas le modifier à la main.',
              '']
    for m in _ordre(schema):
        colonne_de = {c.nom: c.colonne for c in m.champs}
        corps = [_colonne(c, schema, dialecte, m) for c in m.colonnes()]
        if len(m.cle_primaire) > 1:
            corps.append('    PRIMARY KEY (' + ', '.join(_q(colonne_de[n]) for n in m.cle_primaire) + ')')
        for unicite in m.uniques:
            corps.append('    UNIQUE (' + ', '.join(_q(colonne_de[n]) for n in unicite) + ')')
        for c in m.champs:
            if c.relation and c.relation_champs:
                cible = schema.modeles[c.type]
                cible_de = {x.nom: x.colonne for x in cible.champs}
                suite = f' ON DELETE {c.relation_suppression.upper()}' if c.relation_suppression else ''
                corps.append('    FOREIGN KEY (' + ', '.join(_q(colonne_de[n]) for n in c.relation_champs) + ') REFERENCES '
                             + _q(cible.table) + ' (' + ', '.join(_q(cible_de[n]) for n in c.relation_references) + ')'
                             + suite)
        lignes += [f'CREATE TABLE {_q(m.table)} (', ',\n'.join(corps), ');']
        for index in m.index:
            nom = f'{m.table}_{"_".join(colonne_de[n] for n in index)}_idx'
            lignes.append(f'CREATE INDEX {_q(nom)} ON {_q(m.table)} (' + ', '.join(_q(colonne_de[n]) for n in index) + ');')
        lignes.append('')
    return '\n'.join(lignes)


def a_jour(schema=SCHEMA_DEFAUT):
    with open(schema, encoding='utf-8') as f:
        texte = f.read()
    for dialecte, chemin in SORTIES.items():
        if not os.path.exists(chemin):
            return False
        with open(chemin, encoding='utf-8') as f:
            if f.read() != sql(texte, dialecte):
                return False
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ecrire', action='store_true')
    mode.add_argument('--verifier', action='store_true')
    p.add_argument('--schema', default=SCHEMA_DEFAUT)
    a = p.parse_args(argv)
    if a.verifier:
        ok = a_jour(a.schema)
        print('miroir à jour' if ok else 'miroir périmé : écrire une nouvelle migration', file=sys.stderr)
        return 0 if ok else 1
    with open(a.schema, encoding='utf-8') as f:
        texte = f.read()
    for dialecte, chemin in SORTIES.items():
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, 'w', encoding='utf-8') as f:
            f.write(sql(texte, dialecte))
    print('miroir écrit : 2 migrations')
    return 0


if __name__ == '__main__':
    sys.exit(main())
