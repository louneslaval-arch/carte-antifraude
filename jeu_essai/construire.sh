#!/usr/bin/env bash
# Construit une base et une publication à partir de données entièrement fictives.
#
# Usage : jeu_essai/construire.sh [taille] [dossier_de_sortie]
#   taille : kit    le petit jeu d'essai du kit (9 inscrits, cas particuliers connus) — par défaut
#            petit  ~400 sociétés générées       (quelques secondes)
#            moyen  ~8 000 sociétés générées     (~15 s)
#            grand  ~60 000 sociétés générées    (~2 min ; pour mesurer les temps de chargement)
#   sortie : par défaut jeu_essai/sortie/<taille>
#
# Ne jamais pointer ce script vers des données réelles.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
RACINE="$(cd "$ICI/.." && pwd)"
PIPELINE="$RACINE/pipeline"
TAILLE="${1:-kit}"
SORTIE="${2:-$ICI/sortie/$TAILLE}"
PYTHON="${PYTHON:-python3}"

rm -rf "$SORTIE"
mkdir -p "$SORTIE/publication"

if [ "$TAILLE" = "kit" ]; then
    DONNEES="$ICI/donnees"
    LN="$DONNEES/liste_noire_fictive.csv"
else
    echo "0/4 Génération des données fictives ($TAILLE)"
    DONNEES="$SORTIE/donnees"
    "$PYTHON" "$ICI/generer.py" --echelle "$TAILLE" --sortie "$DONNEES"
    LN="$DONNEES/liste_noire.csv"
fi

echo "1/4 Construction de la base"
"$PYTHON" "$PIPELINE/construire_base.py" --liste-noire "$LN" \
    --rc-annonces "$DONNEES/rc_annonces.csv" --rc-personnes "$DONNEES/rc_personnes.csv" \
    --base "$SORTIE/essai.sqlite" > "$SORTIE/bilan.txt"

echo "2/4 Chaînes du dessin (Excel, carte autonome, JSON)"
"$PYTHON" "$PIPELINE/chaines_dessin.py" --base "$SORTIE/essai.sqlite" \
    --excel "$SORTIE/chaines.xlsx" --html "$SORTIE/carte_chaines.html" \
    --json "$SORTIE/chaines.json" > /dev/null

echo "3/4 Rapport de croisement"
"$PYTHON" "$PIPELINE/rapport_croisement.py" --base "$SORTIE/essai.sqlite" \
    --sortie "$SORTIE/croisement.xlsx" > /dev/null

# carte_globale.py n'est pas dans le kit reçu : étape sautée tant qu'il manque.
if [ -f "$PIPELINE/carte_globale.py" ]; then
    "$PYTHON" "$PIPELINE/carte_globale.py" --base "$SORTIE/essai.sqlite" --json "$SORTIE/globale.json"
else
    echo "    (carte_globale.py absent du kit : carte globale non produite)"
fi

if [ -f "$PIPELINE/publier_carte.py" ]; then
    echo "4/4 Publication (couche 1 géométrie, couche 2 identités, manifeste)"
    "$PYTHON" "$PIPELINE/publier_carte.py" --base "$SORTIE/essai.sqlite" \
        --chaines "$SORTIE/chaines.json" --sortie "$SORTIE/publication"
else
    echo "4/4 Publication : publier_carte.py arrive à l'étape 2"
fi

echo "Terminé : $SORTIE"
