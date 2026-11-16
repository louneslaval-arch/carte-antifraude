#!/usr/bin/env bash
# Démonstration locale : base client fictive (jeu_essai/demo/base_demo.sqlite) et pages, sur http://127.0.0.1:8720.
# Deux comptes de démonstration, recréés à chaque lancement : analyste-demo (ANALYSTE) et direction-demo (DIRECTION),
# mots de passe ci-dessous. Jamais sur des données réelles : l'API refuse une base dont un CIN n'est pas fictif.
# Usage : api/lancer_demo.sh [port]      (base absente : outils/demo/construire_demo.py --sortie jeu_essai/demo/base_demo.sqlite)
set -euo pipefail
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8720}"
TEMP="${TMPDIR:-/tmp}/carte-demo"
BASE="$RACINE/jeu_essai/demo/base_demo.sqlite"
PY="$RACINE/.venv/bin/python"
if [ ! -f "$BASE" ] && [ -f "$BASE.gz" ]; then gunzip -k "$BASE.gz"; fi    # la base livrée dans le dépôt est compressée
[ -f "$BASE" ] || { echo "base de démonstration absente : $PY outils/demo/construire_demo.py --sortie jeu_essai/demo/base_demo.sqlite"; exit 2; }
rm -rf "$TEMP" && mkdir -p "$TEMP"
export CARTE_CLE_JWT="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
export CARTE_BASE_URL="sqlite:///$TEMP/journal.db"
export CARTE_BASE_CLIENT="$BASE"
export CARTE_FRONT="$RACINE/front"
export CARTE_COOKIE_NON_SECURISE=1          # http local uniquement
export CARTE_DEBIT="600/minute"
"$PY" - <<'PYTHON'
import os, sys
sys.path.insert(0, os.path.join(os.environ['CARTE_FRONT'], '..', 'api'))
from app.base import ouvrir
from app import comptes
base = ouvrir(os.environ['CARTE_BASE_URL'])
for identifiant, role in (('analyste-demo', 'ANALYSTE'), ('direction-demo', 'DIRECTION')):
    comptes.creer(base, identifiant, role, f'{identifiant}-2026')
PYTHON
echo "Démonstration : http://127.0.0.1:$PORT/  ·  comptes analyste-demo / analyste-demo-2026, direction-demo / direction-demo-2026"
exec "$PY" -m uvicorn --app-dir "$RACINE/api" app.serveur:app --host 127.0.0.1 --port "$PORT"
