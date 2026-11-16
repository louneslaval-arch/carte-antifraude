"""Couches de la base, dans l'ordre (c0 à c6). Chaque couche expose construire_tout(connexion) et
traiter(connexion, ref), qui appellent les mêmes fonctions. Elles s'ajoutent ici étape par étape (D : c0, E : c1…)."""

from pipeline.couches import c0_brut, c1_faits, c2_identites, c3_dossier, c5_graphe

COUCHES = [c0_brut, c1_faits, c2_identites, c3_dossier, c5_graphe]
