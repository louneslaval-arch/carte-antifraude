"""Vocabulaire des clés de `fields` : clé brute → clé canonique, et statut d'une clé.

La clé canonique d'un fait est la clé « moteur » de la v2 (README de Kamal, § 4, table amont → moteur), complétée
des libellés français de la carte grise. Repris d'`extraire_json_v2.py` (11/11), sans changement de règle. La table
`ref_cle_canonique` de la base est remplie depuis ce module (`lignes_de_reference`) et versionnée avec lui.
"""
import re

VERSION = '2026-11-11'

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
    if isinstance(valeur, str) and valeur.strip().upper() in GABARITS:
        return 'gabarit'
    return 'normal'


def lignes_de_reference():
    """Lignes de `ref_cle_canonique` : (type de pièce ou « * », clé brute, clé moteur)."""
    lignes = []
    for cle, cible in CANON.items():
        if cle in CANON_PAR_TYPE:
            lignes += [(type_piece, cle, cible) for type_piece in sorted(CANON_PAR_TYPE[cle])]
        else:
            lignes.append(('*', cle, cible))
    return lignes
