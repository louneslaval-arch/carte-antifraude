#!/usr/bin/env python3
"""Lecteur direct de la base PostgreSQL de l'antifraude (étape L, décision n°12) : lecture seule, sans transformation.

Les tables de Kamal `Dossier`, `Piece`, `Analysis`, `AnalysisControl` et `Reanalysis` sont lues par lots ; chaque
dossier est remis sous la forme de `DossierDetail` (types de la v2) et passe par `c0_brut.recevoir`, comme une
réponse du collecteur : versions brutes, miroir, couches au-dessus, flux = lot, tout reste inchangé.

- Seule mise en forme : les valeurs de PostgreSQL prennent la forme de l'API (dates en texte ISO à la milliseconde en
  temps universel, booléens, JSON et listes décodés). Les identifiants de Kamal (`Piece.id`, `Reanalysis.id`) et les
  dates des pièces sont repris tels quels : rien n'est dérivé.
- La « dernière analyse » est la plus récente (`startedAt`, puis `id`) ; elle porte ses contrôles.
- `Reanalysis.pieceId` est repris tel quel (questions ouvertes : identifiant amont ou `Piece.id` ?).
- Connexion en lecture seule ; l'adresse vient de `CARTE_SOURCE_PG` et n'apparaît jamais dans une sortie. Console :
  comptages seulement, jamais une référence ni un contenu de dossier.

Usage : CARTE_SOURCE_PG='host=… dbname=… user=…' python -m flux.lecteur_direct --base CHEMIN [--depuis DATE]
(mot de passe dans ~/.pgpass ou PGPASSWORD, jamais dans le dépôt).
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402

# Colonnes dont la forme diffère entre PostgreSQL, SQLite et l'API ; un test les compare à schema.prisma.
TYPES = {
    'booleen': {('Dossier', 'actif'), ('Dossier', 'verdictProvisional'), ('Dossier', 'commentaireAlerte'),
                ('Analysis', 'provisional'), ('AnalysisControl', 'applicable')},
    'json': {('Dossier', 'businessData'), ('Piece', 'fields'), ('AnalysisControl', 'details'),
             ('Reanalysis', 'result')},
    'liste': {('AnalysisControl', 'missing'), ('Reanalysis', 'requestedFields')},
    'date': {('Dossier', 'businessReceivedAt'), ('Dossier', 'resultsReceivedAt'), ('Dossier', 'createdAt'),
             ('Dossier', 'updatedAt'), ('Piece', 'createdAt'), ('Piece', 'updatedAt'), ('Analysis', 'startedAt'),
             ('Analysis', 'endedAt'), ('AnalysisControl', 'computedAt'), ('Reanalysis', 'createdAt'),
             ('Reanalysis', 'completedAt')},
}
_SORTES = {cle: sorte for sorte, cles in TYPES.items() for cle in cles}

COLONNES = {
    'Dossier': ('actif',) + c0._DOSSIER,
    'Piece': ('id', 'dossierId', 'createdAt', 'updatedAt') + c0._PIECE,
    'Analysis': ('dossierId',) + c0._ANALYSE,
    'AnalysisControl': ('analysisId', 'dossierId') + c0._CONTROLE,
    'Reanalysis': ('id', 'dossierId') + c0._RELECTURE,
}
_ORDRE = {'Piece': ('upstreamPieceId',), 'Analysis': ('startedAt', 'id'), 'AnalysisControl': ('controlId', 'id'),
          'Reanalysis': ('createdAt', 'id')}


def sorte(table, colonne):
    return _SORTES.get((table, colonne))


def valeur(v, genre):
    """Valeur lue (PostgreSQL ou SQLite) mise à la forme de l'API de la v2."""
    if v is None or genre is None:
        return v
    if genre == 'date':
        if isinstance(v, datetime.datetime):
            if v.tzinfo is not None:
                v = v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return f'{v:%Y-%m-%dT%H:%M:%S}.{v.microsecond // 1000:03d}Z'
        return v
    if genre == 'booleen':
        return bool(v)
    if isinstance(v, (str, bytes)):                  # JSON et listes : texte dans SQLite, déjà décodés par psycopg
        return json.loads(v)
    return v


def _marque(source):
    return '?' if isinstance(source, sqlite3.Connection) else '%s'


def _lignes(source, table, condition='', parametres=()):
    colonnes = COLONNES[table]
    ordre = ', '.join(f'"{c}"' for c in _ORDRE.get(table, ()))
    texte = (f'SELECT {", ".join(chr(34) + c + chr(34) for c in colonnes)} FROM "{table}"'
             + (f' WHERE {condition}' if condition else '') + (f' ORDER BY {ordre}' if ordre else ''))
    for ligne in source.execute(texte, tuple(parametres)).fetchall():
        yield {c: valeur(v, sorte(table, c)) for c, v in zip(colonnes, ligne)}


def _par_dossier(source, table, identifiants):
    condition = f'"dossierId" IN ({", ".join([_marque(source)] * len(identifiants))})'
    groupes = {i: [] for i in identifiants}
    for ligne in _lignes(source, table, condition, identifiants):
        groupes[ligne.pop('dossierId')].append(ligne)
    return groupes


def _detail(dossier, pieces, analyses, controles, relectures):
    d = dict(dossier)
    d['pieces'] = pieces
    d['analyses'] = [dict(a) for a in analyses]
    derniere = analyses[-1] if analyses else None
    d['latestAnalysis'] = (dict(derniere, controls=[{k: v for k, v in c.items() if k != 'analysisId'}
                                                     for c in controles if c['analysisId'] == derniere['id']])
                           if derniere else None)
    d['reanalyses'] = relectures
    return d


def dossiers(source, depuis=None, lot=500):
    """Chaque dossier de la base, sous la forme de `DossierDetail`, par ordre de référence."""
    condition, parametres = ('"updatedAt" >= ' + _marque(source), (depuis,)) if depuis else ('', ())
    texte = 'SELECT "id" FROM "Dossier"' + (f' WHERE {condition}' if condition else '') + ' ORDER BY "ref"'
    tous = [r[0] for r in source.execute(texte, parametres).fetchall()]
    for k in range(0, len(tous), lot):
        identifiants = tous[k:k + lot]
        condition = f'"id" IN ({", ".join([_marque(source)] * len(identifiants))})'
        lus = {ligne['id']: ligne for ligne in _lignes(source, 'Dossier', condition, identifiants)}
        enfants = {t: _par_dossier(source, t, identifiants)
                   for t in ('Piece', 'Analysis', 'AnalysisControl', 'Reanalysis')}
        for i in identifiants:
            if i in lus:
                yield _detail(lus[i], enfants['Piece'][i], enfants['Analysis'][i], enfants['AnalysisControl'][i],
                              enfants['Reanalysis'][i])


def lire(source, cx, passage, depuis=None, maintenant=None, lot=500):
    """Lit la base de l'antifraude et passe chaque dossier à la couche 0. Rend des comptages."""
    bilan = dict(dossiers=0, versions_nouvelles=0, miroir_refuse=0, illisibles=0)
    for detail in dossiers(source, depuis=depuis, lot=lot):
        bilan['dossiers'] += 1
        actif = detail.pop('actif', True)
        try:
            if c0.recevoir(cx, passage, detail, actif=bool(actif), maintenant=maintenant):
                bilan['versions_nouvelles'] += 1
        except c0.MiroirRefuse:
            bilan['miroir_refuse'] += 1
        except c0.DossierIllisible:
            bilan['illisibles'] += 1
    return bilan


def _connecter(adresse):
    import psycopg
    cx = psycopg.connect(adresse, options='-c default_transaction_read_only=on', connect_timeout=15)
    cx.read_only = True
    return cx


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', required=True, help='base de la carte (SQLite) à remplir')
    ap.add_argument('--depuis', help='seulement les dossiers mis à jour depuis cette date (ISO)')
    a = ap.parse_args(argv)
    adresse = os.environ.get('CARTE_SOURCE_PG')
    if not adresse:
        print('arrêt : variable absente : CARTE_SOURCE_PG', file=sys.stderr)
        return 2
    try:
        source = _connecter(adresse)
    except Exception as e:                            # noqa: BLE001  le message peut citer l'adresse : son type seul
        print(f'arrêt : connexion à la base de l’antifraude impossible ({type(e).__name__})', file=sys.stderr)
        return 1
    cx = sqlite3.connect(a.base)
    try:
        cx.execute('PRAGMA journal_mode = WAL')
        cx.execute('PRAGMA foreign_keys = ON')
        migrer.appliquer(cx)
        passage = c0.ouvrir_passage(cx, 'base antifraude', 'lecture_directe')
        try:
            bilan = lire(source, cx, passage, depuis=a.depuis)
        except Exception as e:                        # noqa: BLE001  jamais de contenu ni d'adresse dans la sortie
            print(f'arrêt : lecture interrompue ({type(e).__name__})', file=sys.stderr)
            return 1
        c0.fermer_passage(cx, passage, bilan['dossiers'], bilan['versions_nouvelles'])
    finally:
        cx.close()
        source.close()
    print(' ; '.join(f'{k} : {v}' for k, v in bilan.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
