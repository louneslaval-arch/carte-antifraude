"""Six relations complémentaires, avec preuve explicite issue de Tandem.

Contrat d'entrée par dossier :
[{"code":"caution", "cin":"AB123456", "source_piece":"p1"},
 {"code":"signataire", "cin":"AB123456", "source_piece":"p2"},
 {"code":"cabinet_comptable", "ice":"123456789012345", "source_piece":"p3"},
 {"code":"meme_immeuble", "adresse":"12 rue exemple", "ville":"Casablanca",
  "source_piece":"p4"}]
Les valeurs confidentielles ne sont jamais enregistrées en clair dans c7_relation.
"""

import hashlib
import unicodedata

from pipeline import construire_base as cb
from pipeline.couches import c2_identites_postgresql as c2


PERSONNES = {'caution', 'coemprunteur', 'reference_personnelle', 'signataire'}
CODES = PERSONNES | {'cabinet_comptable', 'meme_immeuble'}


def _hash(*parts):
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def preparer(element):
    """Valide une relation sans consulter la base : (code, clé, type, preuve)."""
    if not isinstance(element, dict):
        raise ValueError('relation invalide')
    code = element.get('code')
    preuve = element.get('source_piece')
    if code not in CODES or not isinstance(preuve, str) or not preuve.strip():
        raise ValueError('code ou source_piece manquant')
    if code in PERSONNES:
        valeur = c2._cin(element.get('cin'))
        if not valeur:
            raise ValueError('CIN valide obligatoire : un nom ne prouve pas une identité')
        return code, _hash('CIN', valeur), 'PP', valeur, preuve
    if code == 'cabinet_comptable':
        valeur = c2._ice(element.get('ice'))
        if not valeur:
            raise ValueError('ICE valide obligatoire pour le cabinet')
        return code, _hash('ICE', valeur), 'PM', valeur, preuve
    adresse = element.get('adresse')
    ville = element.get('ville')
    if not isinstance(adresse, str) or not isinstance(ville, str):
        raise ValueError('Adresse et ville obligatoires')
    cle = cb.cle_adresse(adresse)
    ville_norm = ''.join(c for c in unicodedata.normalize('NFKD', ville.strip().upper())
                         if not unicodedata.combining(c))
    if not cle or not ville_norm:
        raise ValueError('Adresse insuffisamment précise')
    valeur = f'{cle}|{ville_norm}'
    return code, _hash('IMMEUBLE', valeur), 'IMMEUBLE', valeur, preuve


def _fiche_unique(cx, type_fiche, valeur):
    table, colonne = ('c2_personne', 'cin') if type_fiche == 'PP' else ('c2_societe', 'ice')
    lignes = cx.execute(f'SELECT identifiant FROM {table} WHERE {colonne} = %s LIMIT 2', (valeur,)).fetchall()
    return lignes[0][0] if len(lignes) == 1 else None


def traiter(cx, ref, elements):
    """Remplace les relations explicitement documentées du dossier, transactionnelle."""
    if not cx.execute('SELECT 1 FROM c3_dossier WHERE ref = %s', (ref,)).fetchone():
        raise ValueError('Dossier inconnu')
    valeurs = [preparer(e) for e in elements]
    try:
        cx.execute('DELETE FROM c7_relation WHERE ref = %s', (ref,))
        for code, cle, type_fiche, valeur, source in valeurs:
            fiche = _fiche_unique(cx, type_fiche, valeur) if type_fiche != 'IMMEUBLE' else None
            # Une personne ambiguë n'est jamais fusionnée ; un nœud partagé
            # reste utile pour lier des dossiers sans attribuer une identité.
            noeud = f'c7_{code}_{cle}'
            cx.execute('INSERT INTO c7_relation(ref,code,cle,fiche,noeud,source_piece) '
                       'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (ref,code,cle) DO NOTHING',
                       (ref, code, cle, fiche, noeud, source))
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    return len(valeurs)


def liens(cx, ref):
    """Relations vérifiées du dossier, avec poids versionnés ; n'invente aucun lien.

    Les personnes caution/co-emprunteur/référence sont reliées à la fiche
    demandeur uniquement lorsque leur CIN désigne une fiche unique.
    Les signataires, cabinets et immeubles créent un lien entre demandeurs
    seulement si deux dossiers ont une clé forte commune explicite.
    """
    demandeurs = {r for (r,) in cx.execute('SELECT fiche FROM c3_demandeur WHERE ref = %s', (ref,))}
    parametres = dict(cx.execute("SELECT nom,valeur FROM parametre WHERE nom LIKE 'c7_poids_%'").fetchall())
    resultat = set()
    for code, fiche, noeud in cx.execute('SELECT code,fiche,noeud FROM c7_relation WHERE ref = %s', (ref,)):
        poids = parametres.get('c7_poids_' + code)
        if poids is None:
            raise LookupError('Poids absent du référentiel')
        if code in ('caution', 'coemprunteur', 'reference_personnelle'):
            if fiche:
                for debut in demandeurs - {fiche}:
                    resultat.add((debut, fiche, code, poids))
        elif code in ('signataire', 'cabinet_comptable', 'meme_immeuble'):
            refs = {r for (r,) in cx.execute(
                'SELECT DISTINCT ref FROM c7_relation WHERE code = %s AND noeud = %s AND ref <> %s',
                (code, noeud, ref))}
            for autre_ref in refs:
                autres = {r for (r,) in cx.execute('SELECT fiche FROM c3_demandeur WHERE ref = %s', (autre_ref,))}
                for debut in demandeurs:
                    for fin in autres - {debut}:
                        resultat.add((debut, fin, code, poids))
    return [dict(de=a, vers=b, code=c, poids=p) for a, b, c, p in sorted(resultat)]
