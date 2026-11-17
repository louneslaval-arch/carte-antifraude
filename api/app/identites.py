"""Lecture de la couche 2 (identites.sqlite, en lecture seule). Ne journalise rien et ne lève rien qui contienne
une identité : les routes s'en chargent."""

import re
import sqlite3
from contextlib import closing

MAX_RESULTATS = 50
CIN_OU_RC = re.compile(r'[A-Z]{0,2}\d{3,}')


def _ouvrir(publication):
    return closing(sqlite3.connect(f'file:{publication.identites}?mode=ro', uri=True))


def noms(publication, indices):
    marques = ','.join('?' * len(indices))
    with _ouvrir(publication) as con:
        return {i: {'nom': nom, 'lat': lat} for i, nom, lat in con.execute(
            f'SELECT indice, nom, lat FROM identite WHERE indice IN ({marques})', list(indices))}


CHAMPS_FICHE = ('nom', 'lat', 'cin', 'rc', 'tribunal', 'ville', 'derniere', 'url', 'dissoute', 'listes',
                'motifs', 'certain')


def fiche(publication, indice):
    with _ouvrir(publication) as con:
        ligne = con.execute(f"SELECT n.type, {', '.join('i.' + c for c in CHAMPS_FICHE)} FROM noeud n "
                            'JOIN identite i USING (indice) WHERE indice = ?', (indice,)).fetchone()
        if ligne is None:
            return None
        f = dict(zip(('type',) + CHAMPS_FICHE, ligne), indice=indice, certain=bool(ligne[-1]))
        f['liens'] = [dict(indice=v, libelle=l, style=s, force=fo) for v, l, s, fo in con.execute(
            """SELECT indice_b, libelle, style, force FROM lien WHERE indice_a = ?
               UNION ALL SELECT indice_a, libelle, style, force FROM lien WHERE indice_b = ?
               ORDER BY 4 DESC""", (indice, indice))]
        f['annonces'] = [dict(date=d, type=t, url=u) for d, t, u in con.execute(
            'SELECT date, type, url FROM annonce WHERE indice = ? ORDER BY date', (indice,))]
    return f


def fiche_globale(publication, indice):
    """Fiche d'un nœud de la carte globale : la fiche commune et ce que seule la carte globale porte."""
    f = fiche(publication, indice)
    if f is None:
        return None
    with _ouvrir(publication) as con:
        ligne = con.execute('SELECT liste_noire, personnes, nb_dossiers, dossiers FROM fiche_globale WHERE indice = ?',
                            (indice,)).fetchone()
    f.update(zip(('liste_noire', 'personnes', 'nb_dossiers', 'dossiers'), ligne or (None,) * 4))
    return f


def indice_par_cle(publication, cle):
    """Indice du nœud qui porte ce CIN (personne du registre d'abord, puis inscrit) ou ce RC (société, du même
    tribunal d'abord), comparés sans espaces et en majuscules ; None s'il n'est pas sur la carte."""
    compact = re.sub(r'\s+', '', str(cle[1])).upper()
    with _ouvrir(publication) as con:
        if cle[0] == 'cin':                      # table de recherche : CIN déjà sans blancs, en majuscules, indexé
            r = con.execute("""SELECT r.indice FROM recherche r JOIN noeud n USING (indice)
                               WHERE r.champ = 'cin' AND r.valeur = ?
                               ORDER BY CASE n.type WHEN 'personne' THEN 0 WHEN 'inscrit' THEN 1 ELSE 2 END, r.indice
                               LIMIT 1""", (compact,)).fetchone()
            return r[0] if r else None
        # un numéro de RC n'est unique que dans son tribunal : même tribunal exigé ; sans tribunal, un seul candidat
        candidats = con.execute("""SELECT r.indice, i.tribunal FROM recherche r JOIN noeud n USING (indice)
                                     JOIN identite i USING (indice)
                                     WHERE n.type = 'societe' AND r.champ = 'rc' AND r.valeur = ?""",
                                (compact,)).fetchall()
    if cle[2]:
        retenus = sorted(i for i, t in candidats if t == cle[2])
    else:
        retenus = [i for i, _t in candidats] if len(candidats) == 1 else []
    return retenus[0] if retenus else None


def forme_recherche(q):
    """(champs, valeur, exacte) : un CIN ou un RC se cherche exactement, un nom par morceau."""
    nettoye = re.sub(r'\s+', ' ', q.strip().upper())
    compact = nettoye.replace(' ', '')
    if CIN_OU_RC.fullmatch(compact):
        return ('cin', 'rc'), compact, True
    return ('nom',), nettoye, False


def motif_like(valeur):
    """Motif LIKE « contient », les jokers de la saisie pris à la lettre (échappement par \\)."""
    return '%' + valeur.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def recherche(publication, q):
    champs, valeur, exacte = forme_recherche(q)
    condition = 'r.valeur = ?' if exacte else "r.valeur LIKE ? ESCAPE '\\'"
    motif = valeur if exacte else motif_like(valeur)
    with _ouvrir(publication) as con:
        return [dict(indice=i, type=t, nom=n) for i, t, n in con.execute(
            f"""SELECT DISTINCT r.indice, n.type, i.nom FROM recherche r JOIN noeud n USING (indice)
                JOIN identite i USING (indice)
                WHERE r.champ IN ({','.join('?' * len(champs))}) AND {condition}
                ORDER BY i.nom LIMIT {MAX_RESULTATS}""", (*champs, motif))]


def chaine(publication, indice):
    with _ouvrir(publication) as con:
        ligne = con.execute('SELECT donnees FROM chaine WHERE indice = ?', (indice,)).fetchone()
    return ligne[0] if ligne else None


def noms_inscrits(publication):
    with _ouvrir(publication) as con:
        return dict(con.execute('SELECT c.indice, i.nom FROM chaine c JOIN identite i USING (indice)'))
