"""Quotas d'identités, calculés depuis le journal (une seule source, valable avec plusieurs processus).

- étiquettes : indices distincts nommés en une heure (noms et résultats de recherche) ; un indice déjà servi
  dans l'heure n'est pas recompté ;
- fiches : fiches complètes et chaînes ouvertes en une heure.
Deux requêtes simultanées peuvent dépasser le plafond d'une requête : écart accepté.
"""

from fastapi import HTTPException

from . import journal

ETIQUETTES = ('noms', 'recherche')
FICHES = ('fiche', 'chaine')


def etiquettes(etat, session, indices):
    deja = journal.indices_servis(etat.base, session.utilisateur, ETIQUETTES)
    if len(deja | set(indices)) > etat.reglages.quota_etiquettes:
        raise HTTPException(429, 'Quota d\'étiquettes de l\'heure atteint')


def fiches(etat, session):
    if journal.nombre_actions(etat.base, session.utilisateur, FICHES) >= etat.reglages.quota_fiches:
        raise HTTPException(429, 'Quota de fiches de l\'heure atteint')
