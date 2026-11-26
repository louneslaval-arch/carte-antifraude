"""Actualisation contrôlée du graphe PostgreSQL."""

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def executer(*arguments):
    commande = [PYTHON, *map(str, arguments)]
    subprocess.run(
        commande,
        cwd=RACINE,
        check=True
    )


def main():
    if not os.environ.get("AF_DATABASE_URL"):
        raise RuntimeError("AF_DATABASE_URL non configurée")

    dossier_versions = RACINE / "publications_pg" / "versions"
    dossier_versions.mkdir(parents=True, exist_ok=True)

    version = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    with tempfile.TemporaryDirectory(prefix="eqdom_export_") as temporaire:
        extraction = Path(temporaire) / "extraction"
        publication = dossier_versions / version

        print("1/3 - Extraction PostgreSQL")

        executer(
            "pipeline/exporter_graphe_postgresql.py",
            "--sortie", extraction
        )

        print("2/3 - Préparation de la publication")

        executer(
            "pipeline/publier_graphe_pg.py",
            "--source", extraction,
            "--sortie", publication
        )

        print("3/3 - Vérification de la publication")

        environnement = os.environ.copy()
        environnement["AF_GRAPH_PUBLICATION"] = str(publication)
        environnement["PYTHONPATH"] = str(RACINE)

        subprocess.run(
            [
                PYTHON,
                "-c",
                (
                    "from api.app.publication_pg "
                    "import depuis_environnement; "
                    "p = depuis_environnement(); "
                    "print('Publication vérifiée'); "
                    "print('Statistiques:', p.stats)"
                )
            ],
            cwd=RACINE,
            env=environnement,
            check=True
        )

        print("4/4 - Activation de la publication")

        executer(
            "pipeline/activer_publication_pg.py",
            "--version",
            publication
        )

        print()
        print("SUCCÈS")
        print("Nouvelle version :", publication)
        print("Publication active :", RACINE / "publications_pg" / "courante")


if __name__ == "__main__":
    try:
        main()
    except Exception as erreur:
        print("ÉCHEC :", erreur, file=sys.stderr)
        sys.exit(1)
