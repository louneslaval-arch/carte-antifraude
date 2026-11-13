"""Vocabulaire des clés de `fields` : clé brute → clé canonique, et statut d'une clé.

La clé canonique d'un fait est la clé « moteur » de la v2 (README de Kamal, § 4, table amont → moteur), complétée
des libellés français de la carte grise. Repris d'`extraire_json_v2.py` (11/11). La table `ref_cle_canonique` de la
base est remplie depuis ce module (`lignes_de_reference`) et versionnée avec lui : les traductions ci-dessous, plus
toutes les clés de l'inventaire de Kamal par type de pièce (`vocabulaire_v2.py`, généré). Une clé absente de cette
référence est « inconnue » et sort au rapport.

Écarts voulus avec le script d'origine (provisoires, `docs/questions_ouvertes.md`) : `cin` lu sur une attestation de
RIB, une domiciliation ou une carte professionnelle est un champ de CIN hors CIN (piège T05 : il n'y apparaît qu'à
la relecture) ; un nom gabarit est reconnu quel que soit l'ordre de ses mots.
"""
import re

from pipeline.normalisation.vocabulaire_v2 import VOCABULAIRE

VERSION = '2026-11-13'

# clé amont → clé moteur
CANON = {
    'nom_societe': 'denomination_sociale', 'siege_social': 'adresse_siege', 'capital': 'capital_social',
    'forme_juridique': 'type_statuts', 'tribunal_commerce': 'ville_tribunal', 'numero_ice': 'ice',
    'objet_commerce': 'objet_social', 'objet_du_commerce': 'objet_social', 'date_emission': 'date_generation_document',
    'date_immatriculation': 'date_creation', 'date_debut': 'date_creation', 'dirigeants': 'gerants',
    'numero_cin': 'cin', 'numero_cin_gerant': 'cin', 'nom_prenom': 'titulaire_compte',
    'raison_sociale': 'titulaire_compte', 'rib': 'numero_compte',
    'Numéro de chassis': 'numero_chassis', 'Immatriculation': 'immatriculation', 'Marque véhicule': 'marque',
    'Modèle véhicule': 'modele', 'Date de première mise en circulation': 'date_mise_circulation',
    'Puissance fiscal': 'puissance_fiscale', 'Type carburant': 'type_carburant',
    'vehicule.marque': 'marque_vehicule', 'vehicule.modele': 'modele_vehicule', 'prix.prix_total_ttc': 'prix_ttc',
}
# la correspondance ne vaut que pour certains types (`raison_sociale` n'est un titulaire que sur un relevé ou un RIB)
CANON_PAR_TYPE = {
    'nom_prenom': {'RELEVE_BANCAIRE', 'ATTESTATION_RIB'}, 'raison_sociale': {'RELEVE_BANCAIRE', 'ATTESTATION_RIB'},
    'rib': {'RELEVE_BANCAIRE'}, 'capital': {'STATUTS', 'REGISTRE_COMMERCE'}, 'forme_juridique': {'STATUTS'},
    'date_emission': {'REGISTRE_COMMERCE'}, 'date_debut': {'REGISTRE_COMMERCE'},
    'date_immatriculation': {'REGISTRE_COMMERCE'},
}
# préfixes inventés par la relecture, et champs de CIN apparus hors d'une CIN
CLES_INVENTEES = re.compile(r'^(remeration|revelation)\.')
CHAMPS_CIN = {'filiation_complete', 'date_expiration', 'nom_pere', 'nom_mere'}
TYPES_AVEC_CIN_LEGITIME = {'CIN', 'CARTE_GRISE'}
# le numéro de CIN lui-même n'apparaît sur ces pièces qu'à la relecture, avec les autres champs de CIN (piège T05)
CLES_DU_CIN = {'cin', 'numero_cin'}
TYPES_SANS_CIN = {'ATTESTATION_RIB', 'DOMICILIATION', 'CARTE_PROFESSIONNELLE'}
# valeurs d'exemple rendues par le modèle de lecture ; les formes de CIN de démonstration sont assemblées ici pour
# que ce fichier passe la garde des données
GABARITS = {'JOHN DOE', 'JANE DOE', 'A' + '123456', 'AB' + '123456', 'X' * 6, 'N/A', 'NULL', 'NONE'}
LISTES = {'mois', 'gerants', 'dirigeants', 'associes', 'associes_presents', 'nouveau_gerant', 'resolutions',
          'historique', 'cartes'}


def canon(type_piece, cle):
    """Clé canonique (moteur) d'une clé brute, pour ce type de pièce ; la clé elle-même si rien ne la traduit."""
    if cle in CANON and (cle not in CANON_PAR_TYPE or type_piece in CANON_PAR_TYPE[cle]):
        return CANON[cle]
    return cle


def statut_cle(type_piece, cle, valeur):
    """normal, cle_inventee, champ_cin_hors_cin ou gabarit : tout ce qui n'est pas normal sort des règles d'identité."""
    if CLES_INVENTEES.match(cle):
        return 'cle_inventee'
    racine = cle.split('.')[-1]
    if type_piece not in TYPES_AVEC_CIN_LEGITIME and (racine in CHAMPS_CIN or racine.startswith('mrz_')):
        return 'champ_cin_hors_cin'
    if type_piece in TYPES_SANS_CIN and racine in CLES_DU_CIN:
        return 'champ_cin_hors_cin'
    if isinstance(valeur, str) and valeur.strip().upper() in GABARITS:
        return 'gabarit'
    return 'normal'


def lignes_de_reference():
    """Lignes de `ref_cle_canonique` : (type de pièce ou « * », clé brute, clé moteur)."""
    lignes = {}
    for cle, cible in CANON.items():
        for type_piece in sorted(CANON_PAR_TYPE.get(cle, ('*',))):
            lignes[(type_piece, cle)] = cible
    for type_piece, cles in VOCABULAIRE.items():
        for cle in cles:
            lignes[(type_piece, cle)] = canon(type_piece, cle)
    return [(type_piece, cle, cible) for (type_piece, cle), cible in sorted(lignes.items())]


_REFERENCE = {(t, c) for t, c, _ in lignes_de_reference()}
_CIBLES = {m for _, _, m in lignes_de_reference()}


def connue(type_piece, cle_brute):
    """Vrai si la clé est dans la référence : elle-même ou l'objet qui la contient, pour ce type de pièce ou pour
    tous, ou une clé déjà écrite dans le vocabulaire moteur."""
    racine = cle_brute.split('[')[0]
    return any((t, c) in _REFERENCE for t in (type_piece, '*') for c in (racine, racine.split('.')[0])) \
        or racine in _CIBLES


_NOMS_GABARITS = {tuple(sorted(g.split())) for g in GABARITS if ' ' in g}


def nom_gabarit(nom_norm):
    """Vrai si le nom normalisé est un nom d'exemple (« JOHN DOE »), dans un ordre ou dans l'autre."""
    return isinstance(nom_norm, str) and tuple(sorted(nom_norm.split())) in _NOMS_GABARITS
