#!/bin/sh
# Essai de l'étape E sur les deux dossiers réels de l'échantillon. À lancer par Lounès, dans l'app Terminal du Mac,
# depuis le dossier des données réelles (jamais depuis Claude Code, jamais depuis le dépôt) :
#
#     cd <dossier des données réelles> && ~/carte-antifraude/outils/essai_reel_e.sh <dossier1.json> <dossier2.json>
#
# Chaque fichier est le JSON d'un dossier de la v2 (réponse de GET /api/dossiers/<ref>). N'affiche que des comptages ;
# le détail d'une erreur éventuelle va dans un fichier du dossier courant, à ne pas coller.
set -u

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DEPOT/.venv/bin/python"
DATE="$(date +%Y-%m-%d)"
BASE="essai_E_$DATE.sqlite"

case "$(pwd)/" in
    "$DEPOT"/*) echo "refusé : lancer depuis le dossier des données réelles, pas depuis le dépôt"; exit 9 ;;
esac
[ "$#" -ge 1 ] || { echo "usage : essai_reel_e.sh <dossier1.json> <dossier2.json>"; exit 8; }
rm -f "$BASE" "$BASE-wal" "$BASE-shm"

echo "Chiffres à rapporter (rien d'autre) :"
"$PY" "$DEPOT/outils/comptages_e.py" --base "$BASE" "$@" 2> "essai_E_${DATE}_erreurs.txt" | sed \
    -e 's/^\(valeurs : .*\)$/\1 (attendu 182)/' \
    -e 's/^\(valeurs retenues : .*\)$/\1 (attendu 160)/' \
    -e 's/^\(opérations lues : .*\)$/\1 (attendu 252)/' \
    -e 's/^\(opérations reconstituées : .*\)$/\1 (attendu 2)/' \
    -e 's/^\(mentions de personnes (rôles du 11\/11) : .*\)$/\1 (attendu 9)/'
