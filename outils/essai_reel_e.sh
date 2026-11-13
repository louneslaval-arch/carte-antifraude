#!/bin/sh
# Essai de l'étape E sur les deux dossiers réels de l'échantillon. À lancer par Lounès, dans l'app Terminal du Mac,
# depuis le dossier des données réelles (jamais depuis Claude Code, jamais depuis le dépôt), avec le garde-fou des
# données réelles posé dans la commande elle-même (voir le skill essai-donnees-reelles) :
#
#     cd <dossier des données réelles> && <garde-fou>=1 ~/carte-antifraude/outils/essai_reel_e.sh <d1.json> <d2.json>
#
# Chaque fichier est le JSON d'un dossier de la v2 (réponse de GET /api/dossiers/<ref>). N'affiche que des comptages.
# La base et le fichier d'erreurs restent dans le dossier courant : ne jamais les coller, les supprimer après l'essai.
set -u

DEPOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PY="$DEPOT/.venv/bin/python"
DATE="$(date +%Y-%m-%d)"
BASE="essai_E_$DATE.sqlite"
SORTIE="essai_E_${DATE}_comptages.txt"
ERREURS="essai_E_${DATE}_erreurs.txt"

case "$(pwd -P)/" in
    "$DEPOT"/*) echo "refusé : lancer depuis le dossier des données réelles, pas depuis le dépôt"; exit 9 ;;
esac
[ "$#" -ge 1 ] || { echo "usage : essai_reel_e.sh <dossier1.json> <dossier2.json>"; exit 8; }
rm -f "$BASE" "$BASE-wal" "$BASE-shm"

"$PY" "$DEPOT/outils/comptages_e.py" --base "$BASE" -- "$@" > "$SORTIE" 2> "$ERREURS"
CODE=$?
echo "Chiffres à rapporter (rien d'autre) :"
sed -e 's/^\(valeurs : .*\)$/\1 (attendu 182)/' \
    -e 's/^\(valeurs retenues : .*\)$/\1 (attendu 160)/' \
    -e 's/^\(opérations lues : .*\)$/\1 (attendu 252)/' \
    -e 's/^\(opérations reconstituées : .*\)$/\1 (attendu 2)/' \
    -e 's/^\(mentions de personnes (rôles du 11\/11) : .*\)$/\1 (attendu 9)/' "$SORTIE"
if [ "$CODE" -ne 0 ]; then
    echo "essai incomplet (code $CODE) : rapporter ce code et les lignes ci-dessus ; ne pas coller le fichier d'erreurs"
fi
exit "$CODE"
