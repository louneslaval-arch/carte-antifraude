"""Vue 360° : le mur de tuiles montre les données lues dans les documents (pièces, registre, liste noire), chacune avec
sa source et un ton de couleur, selon la liste de Lounès (19/11/2026). Fonction pure sur une fiche construite à la
main. Fictif."""
import copy
import os
import sys

import pytest

from conftest import RACINE

sys.path.insert(0, os.path.join(RACINE, 'api'))
from app import vue360  # noqa: E402

TONS = {'bon', 'attention', 'critique', 'neutre'}


def _piece(type_piece, **faits):
    return dict(type=type_piece, faits=[dict(cle=k.replace('__', '.'), valeur=v) for k, v in faits.items()], mois=[])


def _mois(annee, mois, credit, debit, echeances, salaire):
    return dict(annee=annee, mois=mois, total_credit=credit, total_debit=debit, echeances_credits=echeances,
                solde_cloture=1000, solde_ouverture=0, salaire_detecte=salaire, nb_operations_lues=10)


def fiche_salarie():
    releve = _piece('RELEVE_BANCAIRE', type_titulaire='PP', banque='BANQUE EXEMPLE')
    releve['mois'] = [_mois(2026, 7, 9000, 8500, 3000, 7900), _mois(2026, 8, 9000, 8800, 3200, 8000)]
    return dict(
        identite=dict(type='personne', nom='ZALOU KAMI', cin='ZZ123456', date_naissance='1980-03-10',
                      adresse='12 RUE EXEMPLE RABAT', inscrit=False),
        vue360=dict(profil='salarie', retraite=False, csp='SALARIE_PRIVE',
                    aussi=[dict(indice=7, nom='SOCIETE AUSSI SARL', role='associé')],
                    revenus=dict(declare=10000, pieces={'BULLETIN_DE_PAIE': 10000, 'ATTESTATION_TRAVAIL_SALAIRE': 10000,
                                                        'RELEVE_BANCAIRE': 8000}, ecart=0.2),
                    controles=[dict(famille='Revenus et employeur', anomalies=1, controles=[
                        dict(controle='EMP-05', libelle='Date d’embauche et historique CNSS', resultat='ANOMALIE',
                             criticite='MAJEURE', dossier=1)])],
                    entite=dict(employeur_clients=12)),
        dossiers=[dict(indice=1, demandeur=True, recu='2026-09-15T10:00:00.000Z', produit='DISPO', verdict='CONFORME')],
        chemins=[dict(niveau='majeure', force=0.3, longueur=2, homonymie=False, foyer=False,
                      inscrit=dict(indice=9, nom='INSCRIT EXEMPLE'), etapes=[])],
        incoherences=[dict(type='rib_autre_dossier', libelle='Même RIB', gravite='incoherence', dossier=1)],
        alias=[dict(nom='ZALOU KAMI', ecriture='latin', nombre=3), dict(nom='ZALOU KAMY', ecriture='latin', nombre=1)],
        adresses=[dict(adresse='12 RUE EXEMPLE RABAT', source='v2', role='titulaire de la CIN')],
        identifiants=[dict(type='CIN', valeur='ZZ123456', dossier=1), dict(type='CNSS', valeur='999123456', dossier=1)],
        societes=[dict(indice=5, nom='EMPLOYEUR EXEMPLE SARL', role='salarié', source='v2', inscrit=False)],
        personnes=[], registre=[], liste_noire=[],
        comptes=[dict(rib='••• 0001', banque='BANQUE EXEMPLE', titulaire='ZALOU KAMI')],
        charges=[dict(nature='credit_source', montant=1500, annee=2026, mois=8, dossier=1)],
        vehicules=[],
        donnees=[dict(dossier=1, demandeur=True, controles=[],
                      contexte=[dict(libelle='Employeur déclaré', valeur='VAB')],
                      pieces=[_piece('BULLETIN_DE_PAIE', employeur__raison_sociale='EMPLOYEUR EXEMPLE SARL',
                                     date_embauche='01/06/2019', salaire_net='10 000,00'),
                              _piece('CIN', date_expiration='31/01/2026', lieu_naissance='RABAT'),
                              releve])])


def fiche_entrepreneur():
    f = fiche_salarie()
    f['vue360'].update(profil='entrepreneur', csp='PROFESSION_LIBERALE', aussi=[])
    f['societes'] = [dict(indice=5, nom='CABINET EXEMPLE SARL', role='gérant', source='registre', inscrit=False),
                     dict(indice=6, nom='ANCIENNE EXEMPLE SARL', role='gérant sortant', source='registre', inscrit=False)]
    f['registre'] = [dict(societe='CABINET EXEMPLE SARL', role='associé', parts='60', adresse=None)]
    f['donnees'][0]['pieces'] += [_piece('CARTE_PROFESSIONNELLE', profession='MEDECIN', date_validite='31/12/2027',
                                         numero_inscription='999777'),
                                  _piece('REGISTRE_COMMERCE', date_creation='15/03/2015')]
    return f


def fiche_societe():
    f = fiche_salarie()
    f['identite'] = dict(type='societe', nom='SOCIETE EXEMPLE SARL', rc='9991234', tribunal='RABAT',
                         ice='999000000000001', adresse='5 AV EXEMPLE RABAT', inscrit=False)
    f['vue360'].update(profil='pm', csp='SOCIETE', aussi=[], entite=dict(siege_partage=14, soeurs=['SOEUR A SARL',
                                                                                                     'SOEUR B SARL']))
    f['personnes'] = [dict(indice=3, nom='GERANT EXEMPLE', role='gérant', source='registre', inscrit=True),
                      dict(indice=3, nom='GERANT EXEMPLE', role='associé', source='registre', inscrit=True)]
    f['vue360']['controles'] = [dict(famille='Relevés bancaires', anomalies=1, controles=[
        dict(controle='BNQ-10', libelle='Flux aller-retour', resultat='ANOMALIE', criticite='MAJEURE', dossier=1)])]
    f['donnees'][0]['pieces'] = [_piece('REGISTRE_COMMERCE', forme_juridique='SARL', capital='100 000,00',
                                        date_immatriculation='02/02/2020'),
                                 f['donnees'][0]['pieces'][2]]
    return f


def _toutes(groupes):
    return [t for g in groupes for t in g['tuiles']]


def _tuile(groupes, libelle):
    for t in _toutes(groupes):
        if t['libelle'] == libelle:
            return t
    raise KeyError(libelle)


def _libelles(groupes):
    return {t['libelle'] for t in _toutes(groupes)}


def _groupes(groupes):
    return {g['groupe']: g for g in groupes}


@pytest.mark.parametrize('fabrique', [fiche_salarie, fiche_entrepreneur, fiche_societe])
def test_un_mur_epure_et_bien_forme(fabrique):
    """Épuré (Lounès, 19/11/2026) : une vingtaine de tuiles au plus, aucune tuile vide hors « À venir », aucun
    groupe vide, rien de ce que l'en-tête montre déjà."""
    groupes = vue360.tuiles(fabrique())
    toutes = _toutes(groupes)
    assert 10 <= len(toutes) <= 24
    assert all({'libelle', 'valeur', 'format', 'ton', 'source'} <= set(t) and t['ton'] in TONS for t in toutes)
    assert len({t['libelle'] for t in toutes}) == len(toutes)
    assert all(g['tuiles'] for g in groupes)
    assert all(t['valeur'] is not None for g in groupes if g['groupe'] != 'À venir' for t in g['tuiles'])
    assert not {'Nom', 'CIN', 'Date de naissance', 'Adresse retenue', 'RC', 'ICE', 'Siège'} & _libelles(groupes)


def test_a_venir_regroupe_les_sources_non_branchees():
    g = _groupes(vue360.tuiles(fiche_salarie()))['À venir']['tuiles']
    assert {t['libelle'] for t in g} == {'Historique EQDOM', 'Recouvrement', 'Salaire versé par un autre'}
    assert all(t['valeur'] is None and t['ton'] == 'neutre' and t['detail'] for t in g)
    pm = _groupes(vue360.tuiles(fiche_societe()))['À venir']['tuiles']
    assert 'Chiffre d’affaires déclaré' in {t['libelle'] for t in pm}


def test_identite_seulement_ce_qui_alerte():
    g = vue360.tuiles(fiche_salarie())
    exp = _tuile(g, 'Expiration de la CIN')
    assert exp['valeur'] == '2026-01-31' and exp['ton'] == 'critique'


def test_revenus_ecart_et_endettement_du_salarie():
    g = vue360.tuiles(fiche_salarie())
    assert _tuile(g, 'Bulletin de paie')['valeur'] == 10000
    assert _tuile(g, 'Salaire retrouvé sur les relevés')['valeur'] == 8000
    assert _tuile(g, 'Écart entre pièces')['ton'] == 'attention'
    t = _tuile(g, 'Taux d’endettement')
    # (échéances du relevé 3 200 + crédit prélevé à la source 1 500) / revenu vérifié 10 000
    assert t['valeur'] == pytest.approx(0.47) and t['ton'] == 'attention'


def test_employeur_compte_et_bandeau_du_salarie():
    g = vue360.tuiles(fiche_salarie())
    emp = _tuile(g, 'Employeur')
    assert emp['valeur'] == 'EMPLOYEUR EXEMPLE SARL' and emp['source'] == 'bulletin de paie'
    assert _tuile(g, 'Date d’embauche')['valeur'] == '2019-06-01'
    assert _tuile(g, 'Clients EQDOM qui le déclarent')['valeur'] == 12
    assert _tuile(g, 'Compte')['valeur'] == '••• 0001 · BANQUE EXEMPLE'
    assert _tuile(g, 'N° CNSS')['valeur'] == '999123456'
    assert _tuile(g, 'Aussi associé de')['valeur'] == 'SOCIETE AUSSI SARL'


def test_liste_noire_et_chemin():
    f = fiche_salarie()
    g = vue360.tuiles(f)
    assert _tuile(g, 'Liste noire')['ton'] == 'bon'
    assert _tuile(g, 'Meilleur chemin') == dict(_tuile(g, 'Meilleur chemin'), valeur='majeure · force 0,30',
                                                ton='attention')
    assert _tuile(g, 'Inscrit atteint')['valeur'] == 'INSCRIT EXEMPLE'
    f['identite']['inscrit'] = True
    f['liste_noire'] = [dict(label='ZALOU KAMI', typeListe='INDESIRABLE', motif='FAUX DOCUMENTS', statut='actif',
                             premiere_saisie='2020-07-20', type_fraude=None, nb_inscriptions=1)]
    g = vue360.tuiles(f)
    ln = _tuile(g, 'Liste noire')
    assert ln['ton'] == 'critique' and ln['valeur'] == 'INDESIRABLE' and 'FAUX DOCUMENTS' in ln['detail']


def test_incoherences_et_controles_seulement_s_ils_alertent():
    g = vue360.tuiles(fiche_salarie())
    assert _tuile(g, 'Même RIB dans le dossier d’un autre')['ton'] == 'critique'
    assert 'Même châssis ailleurs' not in _libelles(g)
    ctl = _tuile(g, 'Revenus et employeur')
    assert ctl['valeur'] == '1 anomalie' and 'EMP-05' in ctl['detail']
    f = fiche_salarie()
    f['incoherences'], f['vue360']['controles'] = [], [dict(famille='Identité', anomalies=0, controles=[
        dict(controle='IDT-01', resultat='CONFORME', criticite='CRITIQUE', dossier=1)])]
    g = vue360.tuiles(f)
    assert _tuile(g, 'Incohérences')['ton'] == 'bon' and _tuile(g, 'Contrôles')['valeur'] == 'tous conformes'


def test_historique_des_dossiers_trois_au_plus():
    f = fiche_salarie()
    f['dossiers'] = [dict(indice=k, demandeur=True, recu=f'2026-0{k}-01T10:00:00.000Z', produit='DISPO',
                          verdict='CONFORME') for k in range(1, 6)]
    f['vehicules'] = [dict(type_piece='FACTURE_PROFORMA_VEHICULE', marque='MARQUE EXEMPLE', modele='MODELE X',
                           etat='neuf', prix=150000)]
    h = _groupes(vue360.tuiles(f))['Historique des dossiers']['tuiles']
    dossiers = [t for t in h if t['libelle'].startswith('Dossier du')]
    assert len(dossiers) == 3 and dossiers[0]['libelle'] == 'Dossier du 1 mai 2026'
    v = _tuile(vue360.tuiles(f), 'Véhicule')
    assert v['valeur'] == 'MARQUE EXEMPLE MODELE X' and '150' in v['detail']


def test_entrepreneur_societes_et_carte_pro():
    g = vue360.tuiles(fiche_entrepreneur())
    assert _tuile(g, 'CABINET EXEMPLE SARL')['valeur'] == 'gérant · associé 60 %'
    assert _tuile(g, 'ANCIENNE EXEMPLE SARL')['ton'] == 'attention'
    assert _tuile(g, 'Profession')['valeur'] == 'MEDECIN'
    assert _tuile(g, 'Carte professionnelle valide jusqu’au')['ton'] == 'bon'
    assert _tuile(g, 'Activité depuis')['valeur'] == '2015-03-15'
    assert _tuile(g, 'Type de compte')['valeur'] == 'personnel'
    assert 'Employeur' not in _libelles(g)


def test_societe_identite_legale_dirigeants_flux_reseau():
    g = vue360.tuiles(fiche_societe())
    assert _tuile(g, 'Forme juridique')['valeur'] == 'SARL'
    assert _tuile(g, 'Capital')['valeur'] == 100000
    assert _tuile(g, 'Immatriculée le')['valeur'] == '2020-02-02'
    assert _tuile(g, 'Sociétés au même siège')['valeur'] == 14
    gerant = _tuile(g, 'GERANT EXEMPLE')
    assert gerant['valeur'] == 'gérant, associé' and gerant['ton'] == 'critique'
    assert _tuile(g, 'Crédits par mois')['valeur'] == 9000
    assert _tuile(g, 'Sociétés sœurs')['valeur'] == 'SOEUR A SARL, SOEUR B SARL'
    assert _tuile(g, 'Relevés bancaires')['valeur'] == '1 anomalie'
    assert 'Bulletin de paie' not in _libelles(g)


def test_un_retraite_n_a_que_sa_pension():
    f = fiche_salarie()
    f['vue360']['retraite'] = True
    f['donnees'][0]['pieces'].append(_piece('ATTESTATION_PENSION', nom_organisme_retraite='CAISSE EXEMPLE'))
    g = vue360.tuiles(f)
    assert _tuile(g, 'Organisme de pension')['valeur'] == 'CAISSE EXEMPLE'
    assert not {'Employeur', 'Salaire versé par un autre', 'Clients EQDOM qui le déclarent'} & _libelles(g)


def test_une_fiche_vide_ne_casse_rien():
    f = fiche_salarie()
    for cle in ('dossiers', 'chemins', 'incoherences', 'alias', 'adresses', 'identifiants', 'societes', 'comptes',
                'donnees', 'charges'):
        f[cle] = []
    f['vue360'].update(revenus=dict(declare=None, pieces={}, ecart=None), controles=[], entite={}, aussi=[])
    groupes = vue360.tuiles(f)
    assert _toutes(groupes) and all(g['tuiles'] for g in groupes)


def test_la_fonction_ne_modifie_pas_la_fiche():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        avant = copy.deepcopy(f)
        vue360.tuiles(f)
        assert f == avant
