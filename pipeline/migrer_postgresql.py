"""Migrations SQL PostgreSQL, idempotentes et transactionnelles (psycopg 3).

Conserver ``pipeline/migrer.py`` pour les bases SQLite existantes.
Passer explicitement le dossier contenant l'ensemble des migrations PostgreSQL.
"""

import datetime
import hashlib
import os
import re

NOM = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class ErreurMigration(RuntimeError):
    pass


def lister(dossier):
    fichiers = []
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith(".sql"):
            continue
        match = NOM.fullmatch(nom)
        if match is None:
            raise ErreurMigration(f"nom de migration non conforme : {nom}")
        fichiers.append((int(match.group(1)), nom))
    numeros = [numero for numero, _ in fichiers]
    if len(numeros) != len(set(numeros)):
        raise ErreurMigration("deux migrations portent le même numéro")
    return fichiers


def _empreinte(texte):
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def appliquer(connexion, dossier):
    """Appliquer les migrations PostgreSQL manquantes avec une connexion psycopg 3.

    Chaque migration et sa trace sont validées ensemble. Une erreur annule
    uniquement la migration courante et interrompt la suite.
    """
    if not connexion.autocommit:
        raise ErreurMigration("utiliser une connexion psycopg avec autocommit=True")
    fichiers = lister(dossier)
    with connexion.cursor() as curseur:
        curseur.execute("SELECT to_regclass('schema_version')")
        table_existe = curseur.fetchone()[0] is not None
        if table_existe:
            curseur.execute("SELECT numero, empreinte FROM schema_version")
            deja = dict(curseur.fetchall())
        else:
            deja = {}
            if not fichiers or fichiers[0][0] != 0:
                raise ErreurMigration("migration 000_schema_version.sql manquante")

    appliquees = []
    for numero, nom in fichiers:
        with open(os.path.join(dossier, nom), encoding="utf-8") as fichier:
            texte = fichier.read()
        empreinte = _empreinte(texte)
        if numero in deja:
            if deja[numero] != empreinte:
                raise ErreurMigration(
                    f"migration {nom} modifiée après application : créer une nouvelle migration"
                )
            continue

        quand = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        try:
            with connexion.transaction():
                with connexion.cursor() as curseur:
                    curseur.execute(texte)
                    curseur.execute(
                        "INSERT INTO schema_version (numero, nom, empreinte, applique_le) "
                        "VALUES (%s, %s, %s, %s)",
                        (numero, nom, empreinte, quand),
                    )
        except Exception as exc:
            raise ErreurMigration(f"migration {nom} en échec : {exc}") from exc
        appliquees.append(nom)
    return appliquees
