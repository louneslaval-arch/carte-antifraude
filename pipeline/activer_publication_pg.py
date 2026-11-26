"""Activation et retour arrière des publications PostgreSQL."""

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "publications_pg"
VERSIONS = DOSSIER / "versions"

COURANTE = DOSSIER / "courante"
PRECEDENTE = DOSSIER / "precedente"


def verifier(publication):
    if not publication.is_dir():
        raise RuntimeError("Publication introuvable")

    environnement = os.environ.copy()
    environnement["AF_GRAPH_PUBLICATION"] = str(publication)
    environnement["PYTHONPATH"] = str(RACINE)

    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from api.app.publication_pg import "
                "depuis_environnement; "
                "p=depuis_environnement(); "
                "assert p.stats['noeuds'] > 0; "
                "print('Publication valide :', p.stats['noeuds'], 'noeuds')"
            ),
        ],
        cwd=RACINE,
        env=environnement,
        check=True,
    )


def remplacer_lien(lien, cible):
    """Remplace un lien symbolique par renommage atomique."""
    temporaire = lien.with_name(
        lien.name + ".tmp-" + uuid.uuid4().hex
    )

    try:
        temporaire.symlink_to(cible, target_is_directory=True)
        os.replace(temporaire, lien)
    finally:
        temporaire.unlink(missing_ok=True)


def activer(cible):
    cible = cible.resolve(strict=True)

    # Protection contre une activation hors des versions connues.
    if not cible.is_relative_to(VERSIONS.resolve()):
        raise RuntimeError("La publication doit être dans versions/")

    if not COURANTE.is_symlink():
        raise RuntimeError("Le lien courante est absent ou invalide")

    ancienne = COURANTE.resolve(strict=True)

    if cible == ancienne:
        print("Cette version est déjà active")
        return

    verifier(cible)

    # On conserve l'ancienne version avant de changer.
    remplacer_lien(PRECEDENTE, ancienne)
    remplacer_lien(COURANTE, cible)

    print("ACTIVATION REUSSIE")
    print("Version active :", COURANTE.resolve())
    print("Version précédente :", PRECEDENTE.resolve())


def retour_arriere():
    if not PRECEDENTE.is_symlink():
        raise RuntimeError("Aucune version précédente")

    if not COURANTE.is_symlink():
        raise RuntimeError("Version courante absente")

    ancienne = PRECEDENTE.resolve(strict=True)
    actuelle = COURANTE.resolve(strict=True)

    verifier(ancienne)

    remplacer_lien(COURANTE, ancienne)
    remplacer_lien(PRECEDENTE, actuelle)

    print("RETOUR ARRIERE REUSSI")
    print("Version active :", COURANTE.resolve())


def main():
    parser = argparse.ArgumentParser()
    groupe = parser.add_mutually_exclusive_group(required=True)

    groupe.add_argument("--version", type=Path)
    groupe.add_argument(
        "--rollback",
        action="store_true"
    )

    args = parser.parse_args()

    if args.rollback:
        retour_arriere()
    else:
        activer(args.version)


if __name__ == "__main__":
    main()
