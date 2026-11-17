"""Dictionnaire des indicateurs de la couche 7 (version 1) et listes fermées des découpages.

Le verdict est celui de l'antifraude : « jugé suspect par l'antifraude », jamais une fraude constatée (seules la liste
noire et la cellule fraude disent qui est fraudeur). Ce module fait foi ; `c7_indicateur` en est la copie.
"""
VERSION = '1'
SEUIL = 5                    # aucune valeur publiée sur moins de 5 dossiers (règle absolue n°6)
SEUIL_VILLE = 30             # une ville n'est un découpage qu'à partir de 30 dossiers ; sinon « autres villes »
NON_RENSEIGNE = 'non renseigné'

# Critères autorisés pour découper un taux de verdict ou de contrôle (constante unique, relue par les tests).
DIMENSIONS_TAUX = ('semaine', 'type_personne', 'csp', 'produit', 'mode_paiement', 'categorie', 'region', 'ville',
                   'tranche_age', 'tranche_revenu', 'source_revenu', 'ecart_revenu', 'anciennete_emploi',
                   'type_contrat', 'situation_familiale', 'banque', 'vehicule_etat', 'tranche_prix_vehicule',
                   'age_societe', 'associe_unique', 'capital_tranche', 'releve_lignes_lues')
# Répartition simple des demandeurs seulement : jamais croisés avec un verdict, un contrôle ou une autre dimension.
DIMENSIONS_REPARTITION_SEULE = ('sexe', 'nationalite')
# Autres répartitions simples (profils, qualité), jamais des taux.
DIMENSIONS_REPARTITION = ('source_ville', 'personnes_a_charge', 'marque_vehicule', 'tranche_apport',
                          'statut_analyse')
# Noms de sociétés : derrière `--avec-noms-societes` (à valider avec la conformité), 5 dossiers au moins chacune.
DIMENSIONS_SOCIETES = ('banque', 'employeur', 'concessionnaire')
# Croisements deux à deux autorisés (liste fermée : pas de cube, qui multiplierait les cases sous le seuil).
CROISEMENTS = (('produit', 'categorie'), ('csp', 'tranche_revenu'), ('region', 'produit'),
               ('tranche_age', 'produit'), ('type_personne', 'produit'), ('semaine', 'produit'))

FILTRES_PRODUIT = ('tous', 'DISPO', 'AUTO_CLASSIQUE', 'LOA')
FILTRES_CATEGORIE = ('toutes', 'A', 'B', 'C', 'D', 'E')

# Indicateurs de verdict ou de contrôle : jamais découpés par DIMENSIONS_REPARTITION_SEULE (annexe C).
INDICATEURS_VERDICT_CONTROLE = ('taux_juge_suspect', 'taux_tres_suspect', 'part_verdict',
                                'nb_moyen_alertes_majeures_critiques', 'taux_anomalie_controle',
                                'taux_non_executable_controle', 'controle_decisif')

C3, MIROIR, C1 = 'c3_dossier', 'miroir v2 (AnalysisControl)', 'c1 (pièces, faits retenus)'
INDICATEURS = (
    ('nb_dossiers', 'Nombre de dossiers', 'Dossiers reçus sur la période (dernière version).', 'comptage', C3,
     'dossiers'),
    ('part_dossiers', 'Répartition des dossiers', 'Part des dossiers de la répartition qui tombent dans la case.',
     'dossiers de la case / dossiers de la répartition', C3, '%'),
    ('taux_juge_suspect', "Dossiers jugés suspects par l'antifraude",
     "Verdict SUSPECT ou TRES_SUSPECT de l'antifraude, parmi les dossiers qui ont un verdict. Un signal, pas une "
     'fraude constatée.', 'juge_suspect = 1 / juge_suspect non nul', C3, '%'),
    ('taux_tres_suspect', "Dossiers jugés très suspects par l'antifraude",
     'Verdict TRES_SUSPECT parmi les dossiers qui ont un verdict.', 'verdict TRES_SUSPECT / dossiers avec verdict',
     C3, '%'),
    ('part_verdict', 'Répartition des verdicts', "Part de chaque verdict de l'antifraude.",
     'dossiers du verdict / dossiers avec verdict', C3, '%'),
    ('nb_moyen_alertes_majeures_critiques', 'Alertes majeures et critiques par dossier',
     'Moyenne du nombre d’alertes majeures et critiques.', 'moyenne', C3, 'alertes'),
    ('taux_anomalie_controle', "Anomalies d'un contrôle",
     'Part des dossiers où le contrôle est en anomalie, parmi ceux où il est applicable.',
     'ANOMALIE / (applicable et résultat ≠ NON_APPLICABLE), par contrôle', MIROIR, '%'),
    ('taux_non_executable_controle', 'Contrôle non exécutable',
     'Part des dossiers où le contrôle n’a pas pu s’exécuter, parmi ceux où il est applicable.',
     'NON_EXECUTABLE / applicable, par contrôle', MIROIR, '%'),
    ('elements_manquants', 'Ce qui manque aux contrôles non exécutables',
     'Nombre de fois où chaque élément manque à un contrôle non exécutable.', 'comptage des éléments manquants',
     MIROIR, 'occurrences'),
    ('controle_decisif', 'Contrôle décisif',
     'Part des dossiers jugés suspects où ce contrôle est la seule anomalie majeure ou critique.',
     'dossiers jugés suspects où le contrôle est la seule anomalie MAJEURE ou CRITIQUE / dossiers jugés suspects',
     MIROIR, '%'),
    ('mediane_revenu_verifie', 'Revenu vérifié médian',
     'Revenu mensuel lu sur les pièces : bulletin le plus récent, attestation de travail, pension, médiane du '
     'salaire repéré sur le relevé.', 'médiane', 'c3_revenu', 'dirhams par mois'),
    ('part_source_revenu', 'Source du revenu vérifié', 'Pièce d’où vient le revenu vérifié.', 'répartition',
     'c3_revenu', '%'),
    ('mediane_age', 'Âge médian', 'Âge révolu à la réception, depuis la date de naissance de la CIN.', 'médiane',
     C1, 'ans'),
    ('mediane_prix_vehicule', 'Prix médian du véhicule', 'Prix TTC de la facture proforma (AUTO et LOA).',
     'médiane', 'c3_vehicule', 'dirhams'),
    ('taux_releve_relu', "Relevés avec lignes d'opérations lues",
     'Part des dossiers avec relevé dont au moins un mois porte des opérations lues.',
     'releve_lignes_lues = 1 / dossiers avec relevé', C1, '%'),
    ('taux_relecture_piece', 'Pièces relues', 'Part des pièces relues (source REANALYSE ou champs relus).',
     'pièces relues / pièces, par type', C1, '%'),
    ('part_statut_extraction', 'Statut d’extraction des pièces', 'Répartition des statuts d’extraction.',
     'répartition, par type de pièce', C1, '%'),
    ('taux_remplissage', 'Variable renseignée',
     'Part des dossiers concernés pour lesquels la variable a pu être calculée.',
     'dossiers où la variable n’est pas NULL / dossiers concernés, par variable', 'c7_variable_dossier', '%'),
    ('part_statut_analyse', "Statut de l'analyse", 'Répartition des statuts de l’analyse.', 'répartition', C3, '%'),
)
NOMS = tuple(i[0] for i in INDICATEURS)


def ecrire(cx):
    """Recopie le dictionnaire dans `c7_indicateur`."""
    cx.execute('DELETE FROM c7_indicateur')
    cx.executemany('INSERT INTO c7_indicateur (nom, libelle, definition, formule, source, unite, version) '
                   'VALUES (?, ?, ?, ?, ?, ?, ?)', [(*i, VERSION) for i in INDICATEURS])
