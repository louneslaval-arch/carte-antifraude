"""Extrait les fichiers fournis par le document de lancement, sans rien retaper.

Chaque fichier est encadré dans le document par deux lignes seules :
    <!-- FICHIER: chemin/relatif -->
    ...
    <!-- FIN FICHIER -->
Si le contenu est entouré d'une clôture de code (``` ou ````), elle est retirée.
Un fichier existant n'est jamais écrasé.

Usage :
    .venv/bin/python outils/extraire_lancement.py [--document CHEMIN] [--sauf CHEMIN]... [--seulement CHEMIN]...
"""
import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
OUVERTURE = re.compile(r"^<!-- FICHIER: (?P<chemin>\S+) -->$")
FERMETURE = "<!-- FIN FICHIER -->"
CLOTURE = re.compile(r"^(?P<marque>`{3,}|~{3,})[\w-]*$")


def document_par_defaut():
    for candidat in (RACINE / "LANCEMENT_construction_temps_reel.md",
                     RACINE / "docs" / "LANCEMENT_construction_temps_reel.md"):
        if candidat.exists():
            return candidat
    return RACINE / "LANCEMENT_construction_temps_reel.md"


def retirer_cloture(lignes):
    """Retire la clôture de code qui entoure tout le bloc, s'il y en a une."""
    debut, fin = 0, len(lignes)
    while debut < fin and not lignes[debut].strip():
        debut += 1
    while fin > debut and not lignes[fin - 1].strip():
        fin -= 1
    if fin - debut >= 2:
        ouverture = CLOTURE.match(lignes[debut].rstrip())
        if ouverture and lignes[fin - 1].rstrip() == ouverture.group("marque"):
            return lignes[debut + 1:fin - 1]
    return lignes[debut:fin]


def lire_blocs(texte):
    """Rend la liste (chemin, contenu) des blocs du document, dans l'ordre."""
    blocs, courant, lignes = [], None, []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if courant is None:
            m = OUVERTURE.match(ligne)
            if m:
                courant, lignes = m.group("chemin"), []
            elif ligne == FERMETURE:
                raise ValueError(f"ligne {numero} : fermeture sans ouverture")
        elif ligne == FERMETURE:
            contenu = "\n".join(retirer_cloture(lignes)) + "\n"
            blocs.append((courant, contenu))
            courant = None
        elif OUVERTURE.match(ligne):
            raise ValueError(f"ligne {numero} : ouverture dans un bloc non fermé ({courant})")
        else:
            lignes.append(ligne)
    if courant is not None:
        raise ValueError(f"bloc non fermé : {courant}")
    return blocs


def chemin_sur(chemin):
    p = Path(chemin)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"chemin refusé (hors du dépôt) : {chemin}")
    return RACINE / p


def main(argv=None):
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--document", type=Path, default=None)
    parseur.add_argument("--sauf", action="append", default=[])
    parseur.add_argument("--seulement", action="append", default=[])
    parseur.add_argument("--lister", action="store_true", help="lister les blocs sans rien écrire")
    args = parseur.parse_args(argv)

    document = args.document or document_par_defaut()
    blocs = lire_blocs(document.read_text(encoding="utf-8"))
    chemins = [c for c, _ in blocs]
    if len(set(chemins)) != len(chemins):
        print("erreur : un même chemin apparaît deux fois", file=sys.stderr)
        return 1
    for demande in args.sauf + args.seulement:
        if demande not in chemins:
            print(f"erreur : aucun bloc pour {demande}", file=sys.stderr)
            return 1

    retenus = [(c, t) for c, t in blocs
               if c not in args.sauf and (not args.seulement or c in args.seulement)]
    if args.lister:
        for c, t in retenus:
            print(f"{c} ({len(t.splitlines())} lignes)")
        return 0

    existants = [c for c, _ in retenus if chemin_sur(c).exists()]
    if existants:
        for c in existants:
            print(f"refusé, existe déjà : {c}", file=sys.stderr)
        return 1
    for c, t in retenus:
        cible = chemin_sur(c)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(t, encoding="utf-8")
        print(f"écrit : {c} ({len(t.splitlines())} lignes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
