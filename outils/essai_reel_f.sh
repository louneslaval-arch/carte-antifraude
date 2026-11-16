#!/bin/sh
# Essai de l'étape F sur la base réelle du kit (liste noire et registre). À lancer par Lounès, dans l'app Terminal du
# Mac, depuis le dossier des données réelles (jamais depuis Claude Code, jamais depuis le dépôt), avec le garde-fou
# des données réelles posé dans la commande elle-même :
#
#     cd <dossier des données réelles> && <garde-fou>=1 ~/carte-antifraude/outils/essai_reel_f.sh [base du kit]
#
# Base du kit par défaut : la référence de l'étape A (bl_rc_reference_2026-11-11.sqlite), ouverte en lecture seule.
# N'affiche que des comptages. La base et le fichier d'erreurs restent dans le dossier courant : ne jamais les
# coller ; les supprimer après l'essai.
set -u

DEPOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PY="$DEPOT/.venv/bin/python"
DATE="$(date +%Y-%m-%d)"
KIT="${1:-bl_rc_reference_2026-11-11.sqlite}"
BASE="essai_F_$DATE.sqlite"
SORTIE="essai_F_${DATE}_comptages.txt"
ERREURS="essai_F_${DATE}_erreurs.txt"

case "$(pwd -P)/" in
    "$DEPOT"/*) echo "refusé : lancer depuis le dossier des données réelles, pas depuis le dépôt"; exit 9 ;;
esac
[ -f "$KIT" ] || { echo "base du kit introuvable (la donner en argument)"; exit 8; }
rm -f "$BASE" "$BASE-wal" "$BASE-shm"

"$PY" "$DEPOT/outils/comptages_f.py" --base-kit "$KIT" --base "$BASE" > "$SORTIE" 2> "$ERREURS"
CODE=$?
echo "Chiffres à rapporter (rien d'autre) :"
cat "$SORTIE"
if [ "$CODE" -ne 0 ]; then
    echo "essai incomplet (code $CODE) : rapporter ce code et les lignes ci-dessus ; ne pas coller le fichier d'erreurs"
fi
exit "$CODE"
