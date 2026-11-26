"""Validation d'un export antifraude JSON/JSONL."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def valider_export(dossier):
    dossier = Path(dossier).resolve()

    if not dossier.is_dir():
        raise ValueError("Dossier d'export introuvable")

    fichiers = sorted(
        p for p in dossier.rglob("*")
        if p.is_file() and p.suffix.lower() in (".json", ".jsonl")
    )

    if not fichiers:
        raise ValueError("Aucun fichier JSON/JSONL")

    bilan = {
        "fichiers": 0,
        "enregistrements": 0,
        "empreintes": {},
    }

    for fichier in fichiers:
        empreinte = hashlib.sha256()

        with fichier.open("rb") as f:
            for bloc in iter(lambda: f.read(1024 * 1024), b""):
                empreinte.update(bloc)

        if fichier.suffix.lower() == ".json":
            with fichier.open(encoding="utf-8-sig") as f:
                contenu = json.load(f)

            nombre = len(contenu) if isinstance(contenu, list) else 1

        else:
            nombre = 0

            with fichier.open(encoding="utf-8-sig") as f:
                for numero, ligne in enumerate(f, start=1):
                    if not ligne.strip():
                        continue

                    try:
                        json.loads(ligne)
                    except json.JSONDecodeError as erreur:
                        raise ValueError(
                            f"JSON invalide : {fichier.name}, "
                            f"ligne {numero}"
                        ) from erreur

                    nombre += 1

        bilan["fichiers"] += 1
        bilan["enregistrements"] += nombre
        bilan["empreintes"][str(fichier.relative_to(dossier))] = (
            empreinte.hexdigest()
        )

    return bilan


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--export",
        required=True,
        help="Dossier contenant les exports AF",
    )

    args = parser.parse_args()

    resultat = valider_export(args.export)

    print("VALIDATION REUSSIE")
    print("Fichiers :", resultat["fichiers"])
    print("Enregistrements :", resultat["enregistrements"])
    print("Empreintes SHA-256 calculées")


if __name__ == "__main__":
    try:
        main()
    except Exception as erreur:
        print("VALIDATION ECHOUEE :", erreur, file=sys.stderr)
        sys.exit(1)
