#!/usr/bin/env bash
# Premier déploiement ou nouvelle publication du graphe AF sur l'instance EQDOM.
set -Eeuo pipefail
umask 077

RACINE=/home/ubuntu/carte-antifraude
RUNTIME=/home/ubuntu/carte-runtime
VERSIONS="$RACINE/publications_pg/versions"
COURANTE="$RACINE/publications_pg/courante"
PY="$RACINE/.venv-backend/bin/python"
DEMARRAGE="$RUNTIME/demarrer.sh"

cd "$RACINE"
test -f /home/ubuntu/.antifraude_db_env
test -x "$PY"
test -f "$DEMARRAGE"
test -f "$RUNTIME/jwt.key"
grep -q '^exec /home/ubuntu/carte-antifraude/' "$DEMARRAGE" || {
  echo 'Script de démarrage inattendu : aucune modification effectuée' >&2
  exit 1
}

set -a
# shellcheck disable=SC1091
source /home/ubuntu/.antifraude_db_env
set +a
: "${AF_DATABASE_URL:?Connexion PostgreSQL absente}"

mkdir -p "$RACINE/publications_pg" "$VERSIONS" "$RUNTIME/exports_pg"
chmod 700 "$RACINE/publications_pg" "$VERSIONS" "$RUNTIME/exports_pg"
VERSION="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EXPORT="$RUNTIME/exports_pg/$VERSION"
DESTINATION="$VERSIONS/$VERSION"

echo '1/5 Export PostgreSQL (données privées, permissions restrictives)…'
"$PY" pipeline/exporter_graphe_postgresql.py --sortie "$EXPORT"

echo '2/5 Séparation géométrie / identités sensibles…'
"$PY" pipeline/publier_graphe_pg.py --source "$EXPORT" --sortie "$DESTINATION"

echo '3/5 Contrôle de la publication AVANT activation…'
AF_GRAPH_PUBLICATION="$DESTINATION" "$PY" -c \
  'from api.app.publication_pg import depuis_environnement; p=depuis_environnement(); assert p.stats["noeuds"]>0; print("Publication valide :", p.stats["noeuds"], "noeuds")'

echo '4/5 Activation de la version…'
if [ -L "$COURANTE" ]; then
  "$PY" pipeline/activer_publication_pg.py --version "$DESTINATION"
elif [ ! -e "$COURANTE" ]; then
  # Le script d'activation historique exige une version existante.
  ln -s "versions/$VERSION" "$COURANTE"
else
  echo 'Publication courante non symbolique : arrêt de sécurité' >&2
  exit 1
fi

if ! grep -q '^export AF_GRAPH_PUBLICATION=' "$DEMARRAGE"; then
  sed -i '/^exec \/home\/ubuntu\/carte-antifraude\//i export AF_GRAPH_PUBLICATION="/home/ubuntu/carte-antifraude/publications_pg/courante"' "$DEMARRAGE"
fi
bash -n "$DEMARRAGE"

echo '5/5 Redémarrage du seul service Carte Antifraude…'
sudo systemctl restart carte-antifraude
sudo systemctl is-active --quiet carte-antifraude || {
  sudo journalctl -u carte-antifraude -n 25 --no-pager
  exit 1
}
curl --fail --silent --show-error http://127.0.0.1:8720/api/sante
echo
echo 'Page du graphe PostgreSQL : http://127.0.0.1:8720/carte-pg.html (via tunnel SSH)'
