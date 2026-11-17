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
    publication: Optional[str] = None            # dossier « publication/courant »
    publication_globale: Optional[str] = None    # dossier de la carte globale publiée (publier_globale.py)
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
    flux_v2_secret: Optional[str] = None         # secret partagé de la notification de la v2 (route inactive sans lui)
    flux_base: Optional[str] = None              # base du temps réel où la notification met le dossier en file
    base_client: Optional[str] = None            # base des couches c0 à c5 (lecture seule) pour les pages
    front: Optional[str] = None                  # dossier des pages servies à la racine (aucune ressource externe)


def _texte(env, nom):
    return env.get(nom) or None


def _entier(env, nom):
    brut = env.get(nom)
    if brut in (None, ''):
        return None
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
    lus = dict(
        publication=_texte(env, 'CARTE_PUBLICATION'),
        publication_globale=_texte(env, 'CARTE_PUBLICATION_GLOBALE'),
        donnees_reelles=env.get('CARTE_DONNEES_REELLES') == '1',
        duree_jeton_s=_entier(env, 'CARTE_DUREE_JETON_S'),
        quota_etiquettes=_entier(env, 'CARTE_QUOTA_ETIQUETTES'),
        quota_fiches=_entier(env, 'CARTE_QUOTA_FICHES'),
        debit=_texte(env, 'CARTE_DEBIT'),
        debit_connexion=_texte(env, 'CARTE_DEBIT_CONNEXION'),
        journal_jours=_entier(env, 'CARTE_JOURNAL_JOURS'),
        origine=_texte(env, 'CARTE_ORIGINE'),
        cookie_securise=env.get('CARTE_COOKIE_NON_SECURISE') != '1',
        flux_v2_secret=_texte(env, 'CARTE_FLUX_V2_SECRET'),
        flux_base=_texte(env, 'CARTE_FLUX_BASE'),
        base_client=_texte(env, 'CARTE_BASE_CLIENT'),
        front=_texte(env, 'CARTE_FRONT'))
    if lus['flux_v2_secret'] and len(lus['flux_v2_secret']) < 32:
        raise ReglageInvalide('CARTE_FLUX_V2_SECRET trop court (32 caractères au moins)')
    # une variable absente garde la valeur par défaut de Reglages : chaque défaut n'est écrit qu'une fois
    return Reglages(cle_jwt=cle, base_url=base_url, **{k: v for k, v in lus.items() if v is not None})
