#!/usr/bin/env python3
"""Publication de la carte globale (sortie de carte_globale.py --json) en deux couches, sur le modèle de
publier_carte.py."""

CHAMPS_COUCHE1 = {'x', 'y', 'mx', 'my', 'deg', 'c', 't', 'ville', 'bl', 'o', 'ns', 'certain'}


def publier(chemin_globale, dossier):
    raise NotImplementedError
