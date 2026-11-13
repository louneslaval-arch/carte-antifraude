#!/bin/sh
# Essai de référence de l'étape A sur les données réelles. À lancer par Lounès, dans l'app Terminal du Mac,
# depuis le dossier des données réelles (jamais depuis Claude Code, jamais depuis le dépôt) :
#
#     cd <dossier des données réelles> && ~/carte-antifraude/outils/essai_reel_a.sh
#
# N'affiche que des comptages. Toute la sortie des scripts du kit (bilans, erreurs) va dans des fichiers du dossier
# courant ; en cas d'échec, seul le numéro de l'étape est affiché.
set -u

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DEPOT/.venv/bin/python"
P="$DEPOT/pipeline"
DATE="$(date +%Y-%m-%d)"

# Fichiers d'entrée (dans le dossier courant) : à adapter si les noms changent.
LISTE_NOIRE="${LISTE_NOIRE:-Liste_noir_03_08_2026.xlsx}"
ANNONCES="${ANNONCES:-annonces-legales-2026-10-26.csv}"
PERSONNES="${PERSONNES:-personnes-annonces-legales-2026-10-26.csv}"
EXPORT="${EXPORT:-antifraude_export_complet_2026-11-10}"

case "$(pwd)/" in
    "$DEPOT"/*) echo "refusé : lancer depuis le dossier des données réelles, pas depuis le dépôt"; exit 9 ;;
esac
for f in "$LISTE_NOIRE" "$ANNONCES" "$PERSONNES" "$EXPORT"; do
    [ -e "$f" ] || { echo "fichier d'entrée absent (voir les noms en tête du script)"; exit 8; }
done

# L'archive de l'export contient souvent son propre dossier : chercher 1_donnees_prod un niveau plus bas si besoin
# (sans lot trouvé, charger_antifraude.py du kit s'arrête sur une AttributeError).
if [ ! -d "$EXPORT/1_donnees_prod" ] && [ ! -d "$EXPORT/2_donnees_preprod" ]; then
    INTERIEUR="$(ls -d "$EXPORT"/*/1_donnees_prod "$EXPORT"/*/2_donnees_preprod 2>/dev/null | head -1)"
    [ -n "$INTERIEUR" ] || { echo "export : ni 1_donnees_prod ni 2_donnees_preprod trouvé"; exit 7; }
    EXPORT="$(dirname "$INTERIEUR")"
fi

BASE="bl_rc_$DATE.sqlite"
etape() {  # etape <numéro> <fichier de sortie> <commande…>
    n="$1"; sortie="$2"; shift 2
    printf 'étape %s… ' "$n"
    if "$@" > "$sortie" 2>&1; then echo "faite"; else echo "ÉCHEC (détail dans $sortie, à ne pas coller)"; exit "$n"; fi
}

etape 1 "essai_A_${DATE}_nettoyage.txt"     "$PY" "$P/nettoyer_liste_noire.py" --entree "$LISTE_NOIRE" --sortie Liste_noire_nettoyee.xlsx
etape 2 "essai_A_${DATE}_construction.txt"  "$PY" "$P/construire_base.py" --liste-noire Liste_noire_nettoyee.xlsx --rc-kamal "$ANNONCES" --rc-kamal-personnes "$PERSONNES" --base "$BASE"
etape 3 "essai_A_${DATE}_antifraude.txt"    "$PY" "$P/charger_antifraude.py" --base "$BASE" --export "$EXPORT"
etape 4 "essai_A_${DATE}_chaines.txt"       "$PY" "$P/chaines_dessin.py" --base "$BASE" --excel "Chaines_$DATE.xlsx" --html "Carte_reseaux_$DATE.html" --json "carte_$DATE.json"
etape 5 "essai_A_${DATE}_globale.txt"       "$PY" "$P/carte_globale.py" --base "$BASE" --html "Carte_globale_$DATE.html" --json "globale_$DATE.json"
cp "$BASE" bl_rc_reference_2026-11-11.sqlite

echo
echo "Chiffres à rapporter (rien d'autre) :"
printf '1. inscrits reliés : %s (attendu 122)\n' \
    "$(grep 'Inscrits reliés au registre' "essai_A_${DATE}_construction.txt" | head -1 | grep -oE '[0-9]+[[:space:]]*$' | tr -d '[:space:]')"
"$PY" "$DEPOT/outils/comptages_a.py" --globale "globale_$DATE.json" | sed 's/^réseaux/2. réseaux/; s/^plus grand/3. plus grand/' \
    | sed 's/$/ (attendu : 16 300 réseaux ; 17 nœuds)/'
printf '4. chemins de retour : %s (attendu 301)\n' \
    "$(grep -oE 'dont [0-9]+ reliés à la liste noire' "essai_A_${DATE}_chaines.txt" | head -1 | grep -oE '[0-9]+')"
