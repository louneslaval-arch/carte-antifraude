"""Vue 360° : présentation du client pour la direction (Lounès, 19/11/2026) : est-ce un bon client, demande-t-il
souvent des prêts ; peu d'informations, aucune de fraude dans la présentation (une petite partie à part, en bas).
Fonction pure sur une fiche construite à la main. Fictif."""
import os
import sys

import pytest

from conftest import RACINE
from test_vue360_tuiles import _piece, fiche_entrepreneur, fiche_salarie, fiche_societe

sys.path.insert(0, os.path.join(RACINE, 'api'))
from app import vue360  # noqa: E402

MOTS_DE_FRAUDE = ('fraude', 'liste noire', 'inscrit', 'anomalie', 'suspect', 'homonymie', 'incohérence')


def _chiffre(p, libelle):
    return next(c for c in p['chiffres'] if c['libelle'] == libelle)


def _demandes(f, dates):
    f['dossiers'] = [dict(indice=k + 1, demandeur=True, recu=f'{d}T10:00:00.000Z', produit='DISPO', verdict='CONFORME')
                     for k, d in enumerate(dates)]
    return f


def test_chiffres_cles_du_salarie():
    p = vue360.presentation(fiche_salarie())
    assert [c['libelle'] for c in p['chiffres']] == ['Revenu mensuel vérifié', 'Taux d’endettement',
                                                     'Ancienneté chez l’employeur', 'Demandes de prêt',
                                                     'Client connu d’EQDOM']
    assert _chiffre(p, 'Revenu mensuel vérifié')['valeur'] == 10000
    assert _chiffre(p, 'Taux d’endettement')['valeur'] == pytest.approx(0.47)
    assert _chiffre(p, 'Ancienneté chez l’employeur')['valeur'] == 7          # juin 2019 → sept. 2026, en années
    assert _chiffre(p, 'Demandes de prêt')['valeur'] == 1


def test_chiffres_cles_de_l_entrepreneur_et_de_la_societe():
    e = vue360.presentation(fiche_entrepreneur())
    assert [c['libelle'] for c in e['chiffres']][:2] == ['Revenu mensuel sur les relevés', 'Activité depuis']
    assert _chiffre(e, 'Activité depuis')['valeur'] == 11                    # mars 2015 → sept. 2026
    s = vue360.presentation(fiche_societe())
    assert [c['libelle'] for c in s['chiffres']] == ['Crédits mensuels', 'Ancienneté de la société', 'Capital',
                                                     'Demandes de prêt', 'Client connu d’EQDOM']
    assert _chiffre(s, 'Capital')['valeur'] == 100000 and _chiffre(s, 'Ancienneté de la société')['valeur'] == 6


def test_client_connu_d_eqdom_lu_dans_la_declaration():
    f = fiche_salarie()
    f['donnees'][0]['contexte'].append(dict(libelle='Client connu', valeur='1'))
    assert _chiffre(vue360.presentation(f), 'Client connu d’EQDOM')['valeur'] == 'oui'
    f['donnees'][0]['contexte'][-1]['valeur'] = '0'
    assert _chiffre(vue360.presentation(f), 'Client connu d’EQDOM')['valeur'] == 'non'


def test_demandes_dans_l_ordre_et_leur_rythme():
    p = vue360.presentation(_demandes(fiche_salarie(), ['2026-09-01', '2026-04-15', '2026-07-01']))
    assert [d['date'] for d in p['demandes']] == ['2026-04-15', '2026-07-01', '2026-09-01']
    assert p['demandes'][0] == dict(p['demandes'][0], produit='DISPO', verdict='CONFORME', indice=2)
    assert p['rythme'] == '3 demandes en 5 mois'
    assert any('rapprochées' in v for v in p['vigilance'])
    assert vue360.presentation(fiche_salarie())['rythme'] == '1 demande, le 15 sept. 2026'


def test_points_forts_et_de_vigilance_en_clair_sans_vocabulaire_de_fraude():
    f = fiche_salarie()
    f['vue360']['revenus']['ecart'] = 0.05
    f['charges'], f['donnees'][0]['pieces'][2]['mois'] = [], [dict(f['donnees'][0]['pieces'][2]['mois'][0],
                                                                  echeances_credits=1500)]
    p = vue360.presentation(f)
    assert any('Revenus concordants' in x for x in p['forts'])
    assert any('Endettement maîtrisé' in x for x in p['forts'])
    assert any('Emploi stable' in x for x in p['forts'])
    p = vue360.presentation(fiche_salarie())                                 # écart 20 %, endettement 47 %
    assert any('Revenus divergents' in x for x in p['vigilance'])
    assert any('Endettement élevé' in x for x in p['vigilance'])
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        f['identite']['inscrit'] = True
        p = vue360.presentation(f)
        texte = ' '.join(p['forts'] + p['vigilance'] + [c['libelle'] for c in p['chiffres']]).lower()
        assert not any(m in texte for m in MOTS_DE_FRAUDE), fabrique.__name__


def test_la_fraude_tient_dans_une_petite_partie_a_part():
    f = fiche_salarie()
    p = vue360.presentation(f)
    assert p['antifraude'] == dict(liste_noire=False, lien='majeure', alertes=2)   # 1 incohérence + 1 anomalie
    f['identite']['inscrit'], f['chemins'], f['incoherences'] = True, [], []
    f['vue360']['controles'] = []
    assert vue360.presentation(f)['antifraude'] == dict(liste_noire=True, lien=None, alertes=0)


def test_remboursements_annonces_a_venir():
    assert 'historique sur 36 mois' in vue360.presentation(fiche_salarie())['remboursements']


def test_retraite_et_fiche_vide():
    f = fiche_salarie()
    f['vue360']['retraite'] = True
    f['vue360']['revenus']['pieces'] = {'ATTESTATION_PENSION': 6000}
    f['donnees'][0]['pieces'].append(_piece('ATTESTATION_PENSION', nom_organisme_retraite='CAISSE EXEMPLE'))
    p = vue360.presentation(f)
    assert p['chiffres'][0] == dict(p['chiffres'][0], libelle='Pension mensuelle', valeur=6000)
    assert 'Ancienneté chez l’employeur' not in [c['libelle'] for c in p['chiffres']]
    for cle in ('dossiers', 'chemins', 'incoherences', 'societes', 'comptes', 'donnees', 'charges'):
        f[cle] = []
    f['vue360'].update(revenus=dict(declare=None, pieces={}, ecart=None), controles=[], entite={})
    p = vue360.presentation(f)
    assert p['demandes'] == [] and p['rythme'] == 'aucune demande en propre'


# ---- portrait de l'entité (Lounès, 20/11/2026 : « pour les PM, le nom des associés et gérants… ») ----------------------
def _fait(p, libelle):
    return next((x['valeur'] for x in p['portrait']['faits'] if x['libelle'] == libelle), None)


def test_portrait_d_une_societe_gerants_associes_et_parts():
    f = fiche_societe()
    f['personnes'] = [dict(indice=4, nom='ASSOCIE EXEMPLE', role='associé', source='registre', inscrit=False, parts=40),
                      dict(indice=3, nom='GERANT EXEMPLE', role='gérant', source='registre', inscrit=True, parts=None),
                      dict(indice=3, nom='GERANT EXEMPLE', role='associé', source='registre', inscrit=True, parts=60)]
    f['donnees'][0]['pieces'][0]['faits'] += [dict(cle='objet_social', valeur='NEGOCE DE MATERIAUX'),
                                               dict(cle='tribunal_commerce', valeur='RABAT')]
    p = vue360.presentation(f)['portrait']
    assert p['titre'] == 'Gérants et associés'
    # les parts sont des parts sociales (un nombre), le pourcentage se calcule sur le total des associés lus
    assert p['personnes'] == [dict(nom='GERANT EXEMPLE', roles=['gérant', 'associé'], parts=60, pourcentage=60.0, indice=3),
                              dict(nom='ASSOCIE EXEMPLE', roles=['associé'], parts=40, pourcentage=40.0, indice=4)]
    assert _fait(vue360.presentation(f), 'Activité') == 'NEGOCE DE MATERIAUX'
    assert _fait(vue360.presentation(f), 'Forme et capital') == 'SARL · 100 000 DH'
    assert p['groupe'] == ['SOEUR A SARL', 'SOEUR B SARL']
    assert all('inscrit' not in x for x in p['personnes']), 'aucune donnée de fraude dans le portrait'


def test_portrait_d_un_entrepreneur_ses_societes():
    p = vue360.presentation(fiche_entrepreneur())['portrait']
    assert p['titre'] == 'Ses sociétés'
    cabinet = next(x for x in p['personnes'] if x['nom'] == 'CABINET EXEMPLE SARL')
    assert cabinet == dict(nom='CABINET EXEMPLE SARL', roles=['gérant'], parts=60, pourcentage=None, indice=5,
                           termine=False)
    assert next(x for x in p['personnes'] if x['nom'] == 'ANCIENNE EXEMPLE SARL')['termine'] is True
    assert _fait(vue360.presentation(fiche_entrepreneur()), 'Profession') == 'MEDECIN'


def test_portrait_d_un_salarie_emploi_en_clair():
    f = fiche_salarie()
    f['donnees'][0]['pieces'][0]['faits'] += [dict(cle='fonction', valeur='COMPTABLE'),
                                               dict(cle='type_contrat', valeur='CDI')]
    p = vue360.presentation(f)
    assert _fait(p, 'Employeur') == 'EMPLOYEUR EXEMPLE SARL'
    assert _fait(p, 'Fonction') == 'COMPTABLE' and _fait(p, 'Contrat') == 'CDI'
    assert p['portrait']['personnes'] == []


def test_parts_sociales_jamais_lues_comme_un_pourcentage():
    f = fiche_societe()
    f['personnes'] = [dict(indice=1, nom='A EXEMPLE', role='associé', parts=500), dict(indice=2, nom='B EXEMPLE',
                                                                                     role='associé', parts=1500)]
    q = vue360.presentation(f)['portrait']['personnes']
    assert [(x['parts'], x['pourcentage']) for x in q] == [(1500, 75.0), (500, 25.0)]
