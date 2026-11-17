"""Page autonome des statistiques des dossiers : un seul fichier HTML, hors ligne, sans ressource externe, avec les
cases de `c7_agregat` qu'elle affiche, insérées en JSON. Une case masquée n'y est qu'une clé (dimension et valeur),
sans aucun nombre : la page la dessine grisée et hachurée, « < 5 ». Les filtres choisissent une tranche précalculée ;
le navigateur ne recalcule rien.
"""
from __future__ import annotations

import json
import os
from typing import Any

from pipeline.analytique import indicateurs as ind

# Gabarit à côté des autres modèles de page (`pipeline/*_modele.html`, seuls fichiers .html admis par .gitignore).
MODELE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'statistiques_modele.html')
MARQUE = '/*DONNEES*/'
# Ce que la page affiche : indicateur → découpages (dimension1, dimension2) ; None = tous.
PAGE: dict[str, Any] = {
    'nb_dossiers': {('', '')},
    'part_dossiers': {(d, '') for d in ind.DIMENSIONS_TAUX + ind.DIMENSIONS_REPARTITION_SEULE
                      + ind.DIMENSIONS_REPARTITION + ind.DIMENSIONS_SOCIETES},
    'part_verdict': None, 'part_statut_analyse': None, 'part_statut_extraction': None,
    'taux_juge_suspect': {('', '')} | {(d, '') for d in ind.DIMENSIONS_TAUX},
    'taux_tres_suspect': {('', '')}, 'nb_moyen_alertes_majeures_critiques': {('', '')},
    'taux_anomalie_controle': None, 'taux_non_executable_controle': None, 'controle_decisif': None,
    'elements_manquants': None,
    'mediane_revenu_verifie': {('', '')}, 'mediane_age': {('', '')}, 'mediane_prix_vehicule': {('', '')},
    'taux_releve_relu': {('', '')}, 'taux_relecture_piece': None, 'taux_remplissage': None,
}


def _arrondi(v: Any) -> Any:
    return round(v, 4) if isinstance(v, float) else v


def donnees(cx: Any) -> dict[str, Any]:
    """Données de la page : en-tête, dictionnaire, cases (non masquées avec leurs nombres, masquées en clé seule)."""
    noms_ind = [r for r in cx.execute('SELECT nom, libelle, definition, unite FROM c7_indicateur ORDER BY nom')]
    index_ind = {r[0]: k for k, r in enumerate(noms_ind)}
    textes: list[str] = []
    index_texte: dict[str, int] = {}

    def t(v: str) -> int:
        if v not in index_texte:
            index_texte[v] = len(textes)
            textes.append(v)
        return index_texte[v]
    cases = []
    entete = None
    for (i, p, c, d1, v1, d2, v2, n, d, x, b, h, m, debut, fin, version, le) in cx.execute(
            'SELECT indicateur, filtre_produit, filtre_categorie, dimension1, valeur1, dimension2, valeur2, numerateur, '
            'denominateur, valeur, borne_basse, borne_haute, masque, periode_debut, periode_fin, version, calcule_le '
            'FROM c7_agregat ORDER BY indicateur, filtre_produit, filtre_categorie, dimension1, valeur1, dimension2, '
            'valeur2'):
        permis = PAGE.get(i, set())
        if permis is not None and (d1, d2) not in permis:
            continue
        if i == 'nb_dossiers' and p == 'tous' and c == 'toutes' and not d1:
            entete = dict(periode_debut=debut, periode_fin=fin, version=version, calcule_le=le, dossiers=x)
        case: dict[str, Any] = dict(i=index_ind[i], p=ind.FILTRES_PRODUIT.index(p), c=ind.FILTRES_CATEGORIE.index(c))
        if d1:
            case.update(d1=t(d1), v1=t(v1))
        if d2:
            case.update(d2=t(d2), v2=t(v2))
        if m:
            case['m'] = 1
        else:
            for cle, val in (('n', n), ('d', d), ('x', x), ('b', b), ('h', h)):
                if val is not None:
                    case[cle] = _arrondi(val)
        cases.append(case)
    return dict(entete=entete or {}, filtres=dict(produit=ind.FILTRES_PRODUIT, categorie=ind.FILTRES_CATEGORIE),
                indicateurs=[dict(nom=r[0], libelle=r[1], definition=r[2], unite=r[3]) for r in noms_ind],
                textes=textes, cases=cases)


def generer(cx: Any, chemin: str) -> int:
    """Écrit la page ; rend sa taille en octets."""
    with open(MODELE, encoding='utf-8') as f:
        modele = f.read()
    texte = json.dumps(donnees(cx), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = modele.replace(MARQUE, texte)
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(page)
    return len(page.encode('utf-8'))
