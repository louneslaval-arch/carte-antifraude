"""Application idempotente des migrations numérotées `schema/NNN_<objet>.sql`.

Chaque migration s'applique dans une transaction avec sa ligne de `schema_version` : tout ou rien. Une migration déjà
appliquée dont le fichier a changé est refusée (aucune modification de table à la main ni de migration après coup).
"""
import datetime
import hashlib
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(RACINE, 'schema')
NOM = re.compile(r'^(\d{3})_[a-z0-9_]+\.sql$')


class ErreurMigration(RuntimeError):
    pass


def lister(dossier=SCHEMA):
    fichiers = []
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith('.sql'):
            continue
        m = NOM.match(nom)
        if not m:
            raise ErreurMigration(f'nom de migration non conforme : {nom} (attendu NNN_objet.sql)')
        fichiers.append((int(m.group(1)), nom))
    numeros = [n for n, _ in fichiers]
    if len(numeros) != len(set(numeros)):
        raise ErreurMigration('deux migrations portent le même numéro')
    return fichiers


def _empreinte(texte):
    return hashlib.sha256(texte.encode('utf-8')).hexdigest()


def appliquer(connexion, dossier=SCHEMA):
    """Applique les migrations manquantes, dans l'ordre ; rend la liste des fichiers appliqués."""
    deja = {}
    if connexion.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'").fetchone():
        deja = {n: e for n, e in connexion.execute('SELECT numero, empreinte FROM schema_version')}
    appliquees = []
    for numero, nom in lister(dossier):
        with open(os.path.join(dossier, nom), encoding='utf-8') as f:
            sql = f.read()
        empreinte = _empreinte(sql)
        if numero in deja:
            if deja[numero] != empreinte:
                raise ErreurMigration(f'migration {nom} modifiée après application : en écrire une nouvelle')
            continue
        quand = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        script = ('BEGIN;\n' + sql + '\n'
                  'INSERT INTO schema_version (numero, nom, empreinte, applique_le) '
                  f"VALUES ({numero}, '{nom}', '{empreinte}', '{quand}');\nCOMMIT;\n")
        try:
            connexion.executescript(script)
        except Exception as e:
            if connexion.in_transaction:
                connexion.execute('ROLLBACK')
            raise ErreurMigration(f'migration {nom} en échec ({type(e).__name__}) : rien n\'est appliqué') from None
        appliquees.append(nom)
    return appliquees
