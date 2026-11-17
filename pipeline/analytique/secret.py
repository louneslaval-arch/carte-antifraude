"""Secret statistique de la couche 7, isolé et testé à part.

Primaire : une case dont l'effectif est sous le seuil (5 dossiers) est masquée. Secondaire : quand une seule case
d'une répartition est masquée, la plus petite case restante l'est aussi, pour que la valeur masquée ne se retrouve pas
par différence avec le total. Un tableau croisé est protégé ligne par ligne et colonne par colonne, jusqu'à ce que
plus rien ne change. Une égalité d'effectif se départage par la valeur de la case : le résultat ne dépend pas de
l'ordre des cases.

Une case est un dictionnaire qui porte `effectif` (et `valeur1`, `valeur2`) ; ces fonctions y posent `masque` (0 ou 1)
et `motif` ('moins de 5', 'secret secondaire' ou None).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from pipeline.analytique.indicateurs import SEUIL

PRIMAIRE, SECONDAIRE = 'moins de 5', 'secret secondaire'
Case = dict[str, Any]


def primaire(cases: Iterable[Case], seuil: int = SEUIL) -> None:
    for c in cases:
        petit = c['effectif'] is None or c['effectif'] < seuil
        c['masque'], c['motif'] = (1, PRIMAIRE) if petit else (0, None)


def secondaire(cases: list[Case]) -> bool:
    """Une seule case masquée dans la répartition : masque la plus petite restante. Rend vrai si une case change."""
    if len(cases) < 2 or sum(c['masque'] for c in cases) != 1:
        return False
    restantes = [c for c in cases if not c['masque']]
    cible = min(restantes, key=lambda c: (c['effectif'], str(c.get('valeur1', '')), str(c.get('valeur2', ''))))
    cible['masque'], cible['motif'] = 1, SECONDAIRE
    return True


def masquer_repartition(cases: list[Case], seuil: int = SEUIL) -> None:
    primaire(cases, seuil)
    secondaire(cases)


def masquer_tableau(cases: list[Case], seuil: int = SEUIL) -> None:
    """Tableau croisé (valeur1 × valeur2) : chaque ligne et chaque colonne est une répartition."""
    primaire(cases, seuil)
    lignes: dict[Any, list[Case]] = defaultdict(list)
    colonnes: dict[Any, list[Case]] = defaultdict(list)
    for c in cases:
        lignes[c.get('valeur1')].append(c)
        colonnes[c.get('valeur2')].append(c)
    change = True
    while change:
        change = False
        for groupe in list(lignes.values()) + list(colonnes.values()):
            change |= secondaire(groupe)
