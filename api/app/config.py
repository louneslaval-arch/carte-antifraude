"""Réglages de l'interface, lus une seule fois depuis l'environnement et vérifiés à l'entrée.

Aucun secret dans le dépôt : la clé de signature, l'adresse de la base du journal et la clé publique Tandem
viennent des variables d'environnement du serveur.
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional


class ReglageInvalide(Exception):
    pass


@dataclass(frozen=True)
class Reglages:
    cle_jwt: str
    base_url: str                                # base du journal, des comptes et des révocations
    publication: Optional[str]                   # dossier « publication/courant »
    donnees_reelles: bool = False                # CARTE_DONNEES_REELLES=1, posé seulement sur le serveur
    duree_jeton_s: int = 8 * 3600
    renouveler_apres_s: int = 15 * 60            # un jeton plus vieux est renouvelé à la requête suivante
    echecs_max: int = 5                          # échecs de connexion avant verrouillage du compte
    quota_etiquettes: int = 20_000               # indices distincts nommés par heure et par utilisateur
    quota_fiches: int = 2_000                    # fiches complètes (nœud, chaînes) par heure et par utilisateur
    debit: str = '60/minute'                     # toutes routes, par utilisateur
    debit_connexion: str = '10/minute'           # par adresse
    journal_jours: int = 365                     # conservation du journal d'audit
    origine: Optional[str] = None                # seule origine admise par CORS (vide : aucune)
    cookie_securise: bool = True


def _entier(env, nom, defaut):
    brut = env.get(nom)
    if brut in (None, ''):
        return defaut
    try:
        valeur = int(brut)
    except ValueError:
        raise ReglageInvalide(f'{nom} doit être un entier') from None
    if valeur <= 0:
        raise ReglageInvalide(f'{nom} doit être positif')
    return valeur


def lire_reglages(env: Mapping[str, str] = os.environ) -> Reglages:
    cle = env.get('CARTE_CLE_JWT') or ''
    if len(cle) < 32:
        raise ReglageInvalide('CARTE_CLE_JWT absente ou trop courte (32 caractères au moins)')
    base_url = env.get('CARTE_BASE_URL')
    if not base_url:
        raise ReglageInvalide('CARTE_BASE_URL absente')
    return Reglages(
        cle_jwt=cle, base_url=base_url, publication=env.get('CARTE_PUBLICATION') or None,
        donnees_reelles=env.get('CARTE_DONNEES_REELLES') == '1',
        duree_jeton_s=_entier(env, 'CARTE_DUREE_JETON_S', 8 * 3600),
        quota_etiquettes=_entier(env, 'CARTE_QUOTA_ETIQUETTES', 20_000),
        quota_fiches=_entier(env, 'CARTE_QUOTA_FICHES', 2_000),
        debit=env.get('CARTE_DEBIT') or '60/minute',
        debit_connexion=env.get('CARTE_DEBIT_CONNEXION') or '10/minute',
        journal_jours=_entier(env, 'CARTE_JOURNAL_JOURS', 365),
        origine=env.get('CARTE_ORIGINE') or None,
        cookie_securise=env.get('CARTE_COOKIE_NON_SECURISE') != '1')
