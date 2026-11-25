"""C6 : matérialisation des signaux C3 et des chemins C5.

Le module n'invente pas de liens, de règles ni de fraude confirmée.
`reconstruire_tout` est recommandé après ingestion : les incohérences entre
dossiers peuvent changer lorsqu'un autre dossier est importé.
"""

import hashlib

from pipeline.couches import c5_graphe_postgresql as c5


LIBELLES = {
    'double_financement': 'Numéro de châssis présent dans plusieurs dossiers',
    'rib_autre_dossier': 'RIB utilisé dans le dossier d’une autre personne',
    'dossiers_en_rafale': 'Dépôts rapprochés avec un identifiant commun',
    'salaire_bulletin_releve': 'Écart entre salaire du bulletin et relevé',
    'adresse_cin_differente': 'Adresses incohérentes entre pièces',
    'employeur_absent_du_registre': 'Employeur non retrouvé au registre',
}


def _cle(*valeurs):
    return hashlib.sha256('|'.join('' if v is None else str(v) for v in valeurs).encode()).hexdigest()[:24]

def _af09_admissible(cx, ref, autre_ref):
    """AF09 : RIB partagé par 2 à 12 clients distincts."""

    if not autre_ref:
        return False

    ribs = cx.execute(
        """
        SELECT DISTINCT a.valeur
        FROM c3_cle_dossier a
        JOIN c3_cle_dossier b
          ON b.type = 'RIB'
         AND b.valeur = a.valeur
         AND b.ref = %s
        WHERE a.type = 'RIB'
          AND a.ref = %s
        """,
        (autre_ref, ref)
    ).fetchall()

    for (rib,) in ribs:
        nombre = cx.execute(
            """
            SELECT COUNT(DISTINCT d.fiche)
            FROM c3_cle_dossier c
            JOIN c3_demandeur d ON d.ref = c.ref
            WHERE c.type = 'RIB'
              AND c.valeur = %s
            """,
            (rib,)
        ).fetchone()[0]

        if 2 <= nombre <= 12:
            return True

    return False
def calculer(cx, ref, contexte=None):
    """Retourne des alertes sans PII ; aucune écriture ni classement frauduleux."""
    alertes = {}
    for ch in c5.chemins(cx, ref, contexte):
        code = 'inscrit_direct' if ch['longueur'] == 0 else 'lien_liste_noire'
        justification = ('Identité du dossier présente sur la liste noire' if ch['longueur'] == 0
                         else 'Chemin vers une identité inscrite sur la liste noire')
        if ch.get('homonymie'):
            justification += ' (homonymie à valider)'
        cle = _cle('graphe', ch['cible'], ch['longueur'])
        alertes[cle] = (ref, cle, code, 'lien_liste_noire', ch['niveau'], justification)

    for row in cx.execute(
        'SELECT type, gravite, upstream_piece_id_a, repere_a, ref_b, '
        'upstream_piece_id_b, repere_b FROM c3_incoherence WHERE ref = %s', (ref,)
    ):
        code, gravite, piece_a, repere_a, autre_ref, piece_b, repere_b = row
        if code == 'rib_autre_dossier':
            if not _af09_admissible(cx, ref, autre_ref):
                continue
        cle = _cle('incoherence', code, piece_a, repere_a, autre_ref, piece_b, repere_b)
        nature = 'incoherence' if gravite == 'incoherence' else 'signal'
        alertes[cle] = (ref, cle, code, nature, None, LIBELLES.get(code, 'Signal documentaire à examiner'))
    return list(alertes.values())


def _traiter(cx, ref, contexte=None):
    if not cx.execute('SELECT 1 FROM c3_dossier WHERE ref = %s', (ref,)).fetchone():
        raise ValueError('Dossier C3 introuvable')
    alertes = calculer(cx, ref, contexte)
    cx.execute('DELETE FROM c6_alerte WHERE ref = %s', (ref,))
    if alertes:
        with cx.cursor() as curseur:
            curseur.executemany(
                'INSERT INTO c6_alerte (ref, cle, code, nature, niveau, justification) '
                'VALUES (%s, %s, %s, %s, %s, %s)', alertes)
    return len(alertes)


def traiter(cx, ref):
    """Met à jour un dossier, commit uniquement après succès."""
    try:
        total = _traiter(cx, ref)
        cx.commit()
        return total
    except Exception:
        cx.rollback()
        raise


def reconstruire_tout(cx):
    """Recalcule tous les dossiers ; recommandé après un nouvel import JSON."""
    try:
        contexte = c5.Contexte(cx)
        refs = [r for (r,) in cx.execute('SELECT ref FROM c3_dossier ORDER BY ref')]
        for ref in refs:
            _traiter(cx, ref, contexte)
        cx.execute('DELETE FROM c6_alerte WHERE ref NOT IN (SELECT ref FROM c3_dossier)')
        cx.commit()
        return len(refs)
    except Exception:
        cx.rollback()
        raise
