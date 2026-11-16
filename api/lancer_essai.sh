#!/usr/bin/env bash
# Lance l'interface en local sur la publication fictive du kit (jamais sur des données réelles).
# Clé de signature tirée au hasard à chaque lancement ; base du journal dans un dossier temporaire.
# Usage : api/lancer_essai.sh [port]      (construire d'abord : jeu_essai/construire.sh kit)
set -euo pipefail
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8710}"
TEMP="${TMPDIR:-/tmp}/carte-essai"
mkdir -p "$TEMP"
export CARTE_CLE_JWT="$("$RACINE/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')"
export CARTE_BASE_URL="sqlite:///$TEMP/journal.db"
export CARTE_PUBLICATION="$RACINE/jeu_essai/sortie/kit/publication"
export CARTE_COOKIE_NON_SECURISE=1          # http local uniquement
exec "$RACINE/.venv/bin/python" -m uvicorn --app-dir "$RACINE/api" app.serveur:app --host 127.0.0.1 --port "$PORT"
