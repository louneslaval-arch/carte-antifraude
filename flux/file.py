"""File de travail du collecteur (`flux_travail`) : les dossiers à aller chercher dans la v2.

États (`.claude/rules/flux.md`) : `en_attente` → `en_cours` → `fait` ; `erreur` → nouvelle tentative à intervalle
croissant ; `bloque` après 5 échecs, ou si la v2 répond que le dossier n'existe pas : le travail reste visible dans
l'administration et se débloque à la main, il n'est jamais effacé. Une même version annoncée deux fois (deux
scrutations, ou une scrutation et une notification) ne fait qu'un travail ; une version plus récente fait sauter
l'ancienne encore en attente. Aucune donnée de dossier ici : références, états, codes d'erreur sans valeur.
"""
import datetime
import uuid

FORMAT = '%Y-%m-%dT%H:%M:%S.000Z'
DELAI_INITIAL_S, DELAI_MAX_S = 60, 3600
ECHECS_MAX = 5


def _iso(t):
    return t.strftime(FORMAT)


def delai(essais, initial=DELAI_INITIAL_S, maximum=DELAI_MAX_S):
    """Délai avant la tentative suivante : double à chaque échec, plafonné."""
    return min(initial * 2 ** max(essais - 1, 0), maximum)


def annoncer(cx, source, ref, updated_at, actif, maintenant):
    """Ajoute un travail pour cette version si elle n'est pas déjà annoncée. Rend vrai si le travail est nouveau."""
    avant = cx.total_changes
    cx.execute('INSERT INTO flux_travail (id, source, ref, updated_at, actif, recu_le) VALUES (?, ?, ?, ?, ?, ?) '
               'ON CONFLICT (source, ref, updated_at) DO NOTHING',
               (str(uuid.uuid4()), source, ref, updated_at, int(actif), _iso(maintenant)))
    nouveau = cx.total_changes > avant
    if nouveau:                                           # la version plus ancienne encore à faire n'a plus d'objet
        cx.execute("UPDATE flux_travail SET etat = 'fait', code_erreur = 'remplace', prochaine_tentative = NULL "
                   "WHERE source = ? AND ref = ? AND updated_at < ? AND etat IN ('en_attente', 'erreur')",
                   (source, ref, updated_at))
    return nouveau


def a_prendre(cx, source, maintenant):
    """Travaux à faire maintenant : (id, ref, actif), les plus anciens d'abord."""
    return cx.execute(
        "SELECT id, ref, actif FROM flux_travail WHERE source = ? AND etat IN ('en_attente', 'erreur') "
        'AND (prochaine_tentative IS NULL OR prochaine_tentative <= ?) ORDER BY recu_le, ref',
        (source, _iso(maintenant))).fetchall()


def reussir(cx, travail, empreinte, duree_ms, code=None):
    cx.execute("UPDATE flux_travail SET etat = 'fait', empreinte = ?, duree_ms = ?, code_erreur = ?, "
               'prochaine_tentative = NULL WHERE id = ?', (empreinte, duree_ms, code, travail))


def echouer(cx, travail, code, maintenant):
    essais = cx.execute('SELECT essais FROM flux_travail WHERE id = ?', (travail,)).fetchone()[0] + 1
    if essais >= ECHECS_MAX:
        cx.execute("UPDATE flux_travail SET etat = 'bloque', essais = ?, code_erreur = ?, prochaine_tentative = NULL "
                   'WHERE id = ?', (essais, code, travail))
        return
    prochaine = maintenant + datetime.timedelta(seconds=delai(essais))
    cx.execute("UPDATE flux_travail SET etat = 'erreur', essais = ?, code_erreur = ?, prochaine_tentative = ? "
               'WHERE id = ?', (essais, code, _iso(prochaine), travail))


def bloquer(cx, travail, code):
    cx.execute("UPDATE flux_travail SET etat = 'bloque', code_erreur = ?, prochaine_tentative = NULL WHERE id = ?",
               (code, travail))


def debloquer(cx, source, ref):
    """Remet en attente les travaux bloqués d'un dossier (geste d'administration)."""
    cx.execute("UPDATE flux_travail SET etat = 'en_attente', essais = 0, prochaine_tentative = NULL "
               "WHERE source = ? AND ref = ? AND etat = 'bloque'", (source, ref))
    cx.commit()


def etat(cx):
    """Nombre de travaux par état : comptages seulement."""
    return dict(cx.execute('SELECT etat, count(*) FROM flux_travail GROUP BY etat').fetchall())
