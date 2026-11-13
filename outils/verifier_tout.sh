#!/bin/sh
# Vérification complète (étape B) : garde, ruff (E9, F), mypy, pytest, jeu d'essai, construire + verifier,
# carte de correspondance à jour. S'arrête au premier échec. Sans dépôt distant, ce script et le crochet git
# tiennent lieu d'intégration continue (questions ouvertes n°10).
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python

etape() { printf '\n== %s\n' "$1"; }

etape "garde des données"
$PY outils/garde/garde_donnees.py --tout

etape "ruff (E9, F)"
if [ ! -x .venv/bin/ruff ]; then echo "ruff absent : .venv/bin/python -m pip install -r requirements-dev.txt"; exit 1; fi
.venv/bin/ruff check --select E9,F .

etape "mypy (normalisation, lecteurs de structure)"
if [ ! -x .venv/bin/mypy ]; then echo "mypy absent : .venv/bin/python -m pip install -r requirements-dev.txt"; exit 1; fi
.venv/bin/mypy --ignore-missing-imports --explicit-package-bases pipeline/normalisation outils/v2

etape "tests"
$PY -m pytest -q

etape "jeu d'essai du kit"
jeu_essai/construire.sh kit > /dev/null

etape "construire + verifier (base vide)"
BASE="${TMPDIR:-/tmp}/verifier_tout_$$.sqlite"
rm -f "$BASE"
CARTE_BASE_ESSAI="$BASE" $PY construire.py --jeu-essai
$PY verifier.py --base "$BASE"
rm -f "$BASE"

etape "1 000 dossiers v2 fictifs sur le grand registre, tous valides"
V2="${TMPDIR:-/tmp}/verifier_tout_v2_$$"
$PY jeu_essai/v2/generer_dossiers.py --sortie "$V2"
$PY - "$V2" <<'PYTHON'
import json, sys
sys.path.insert(0, '.')
from pipeline import modeles_v2
dossiers = json.load(open(sys.argv[1] + '/dossiers.json', encoding='utf-8'))
for d in dossiers:
    modeles_v2.DossierDetail.model_validate(d)
assert len(dossiers) == 1000
print(f'dossiers valides : {len(dossiers)}')
PYTHON
rm -rf "$V2"

etape "carte de correspondance, modèles d'échange et miroir à jour"
if [ -f reference/v2/schema/schema.prisma ]; then
    $PY outils/v2/carte_correspondance.py --verifier --structure reference/v2
    $PY outils/v2/generer_modeles.py --verifier --types reference/v2/types
    $PY outils/v2/generer_miroir.py --verifier --schema reference/v2/schema/schema.prisma
elif [ -f import/kamal_structure/schema/schema.prisma ]; then
    $PY outils/v2/carte_correspondance.py --verifier
    $PY outils/v2/generer_modeles.py --verifier
    $PY outils/v2/generer_miroir.py --verifier
else
    echo "structure de Kamal absente (reference/v2/ et import/kamal_structure/) : carte non vérifiée"
    exit 1
fi

printf '\nvérification complète : vert\n'
