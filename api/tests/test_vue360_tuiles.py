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


@pytest.mark.parametrize('fabrique', [fiche_salarie, fiche_entrepreneur, fiche_societe])
def test_tuiles_bien_formees_avec_leur_source(fabrique):
    toutes = _toutes(vue360.tuiles(fabrique()))
    assert 25 <= len(toutes) <= 60
    assert all({'libelle', 'valeur', 'format', 'ton', 'source'} <= set(t) and t['ton'] in TONS for t in toutes)
    assert len({t['libelle'] for t in toutes}) == len(toutes)


def test_historique_eqdom_recouvrement_pour_tous_et_endettement_du_salarie():
    """En rouge sur la liste de Lounès, à garder (19/11/2026) : historique des dossiers, historique EQDOM,
    recouvrement, taux d'endettement."""
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        groupes = {g['groupe']: g for g in vue360.tuiles(fabrique())}
        assert {'Historique des dossiers', 'Historique EQDOM', 'Recouvrement'} <= set(groupes)
        eqdom = groupes['Historique EQDOM']['tuiles']
        assert {t['libelle'] for t in eqdom} >= {'Contrats EQDOM', 'Impayés', 'Classe BAM'}
        assert all(t['valeur'] is None and 'historique sur 36 mois' in t['detail'] for t in eqdom)
        assert all(t['valeur'] is None for t in groupes['Recouvrement']['tuiles'])
    g = vue360.tuiles(fiche_salarie())
    t = _tuile(g, 'Taux d’endettement')
    # charges du mois (échéances du relevé 3 200 + crédit prélevé à la source 1 500) / revenu vérifié 10 000
    assert t['valeur'] == pytest.approx(0.47) and t['format'] == 'pourcent' and t['ton'] == 'attention'
    assert 'Taux d’endettement' not in _libelles(vue360.tuiles(fiche_societe()))


def test_historique_des_dossiers_produit_date_role_verdict_vehicule():
    f = fiche_salarie()
    f['vehicules'] = [dict(type_piece='FACTURE_PROFORMA_VEHICULE', marque='MARQUE EXEMPLE', modele='MODELE X',
                           etat='neuf', prix=150000)]
    g = vue360.tuiles(f)
    d = _tuile(g, 'Dossier du 15 sept. 2026')
    assert d['valeur'] == 'DISPO · demandeur' and d['ton'] == 'bon' and 'CONFORME' in d['detail']
    v = _tuile(g, 'Véhicule')
    assert v['valeur'] == 'MARQUE EXEMPLE MODELE X' and _tuile(g, 'Prix du véhicule')['valeur'] == 150000


def test_identite_lue_dans_les_pieces():
    g = vue360.tuiles(fiche_salarie())
    assert _tuile(g, 'CIN')['valeur'] == 'ZZ123456'
    assert _tuile(g, 'Lieu de naissance') == dict(_tuile(g, 'Lieu de naissance'), valeur='RABAT', source='CIN')
    exp = _tuile(g, 'Expiration de la CIN')
    assert exp['valeur'] == '2026-01-31' and exp['ton'] == 'critique'          # expirée au dernier dossier
    assert 'ZALOU KAMY' in _tuile(g, 'Graphies')['valeur']


def test_revenus_piece_par_piece_et_ecart():
    g = vue360.tuiles(fiche_salarie())
    assert _tuile(g, 'Bulletin de paie') == dict(_tuile(g, 'Bulletin de paie'), valeur=10000, format='montant')
    assert _tuile(g, 'Salaire retrouvé sur les relevés')['valeur'] == 8000
    assert _tuile(g, 'Revenu déclaré')['source'] == 'déclaration'
    assert _tuile(g, 'Écart entre pièces')['ton'] == 'attention'               # 20 % > 15 %


def test_employeur_charges_comptes_identifiants_du_salarie():
    g = vue360.tuiles(fiche_salarie())
    emp = _tuile(g, 'Employeur sur le bulletin')
    assert emp['valeur'] == 'EMPLOYEUR EXEMPLE SARL' and emp['source'] == 'bulletin de paie'
    assert _tuile(g, 'Employeur déclaré au dossier')['valeur'] == 'VAB'
    assert _tuile(g, 'Clients EQDOM qui le déclarent')['valeur'] == 12
    assert _tuile(g, 'Date d’embauche')['valeur'] == '2019-06-01'
    assert _tuile(g, 'Contrôle EMP-05')['ton'] == 'attention'
    assert _tuile(g, 'Crédit prélevé à la source')['valeur'] == 1500
    assert _tuile(g, 'Échéances de crédit sur les relevés')['valeur'] == 3200
    assert _tuile(g, 'RIB')['valeur'] == '••• 0001'
    assert _tuile(g, 'N° CNSS')['valeur'] == '999123456'
    assert _tuile(g, 'Aussi associé de')['valeur'] == 'SOCIETE AUSSI SARL'
    nd = _tuile(g, 'Salaire versé par un autre')
    assert nd['valeur'] is None and nd['ton'] == 'neutre' and 'Tandem' in nd['detail']


def test_liste_noire_et_chemins():
    f = fiche_salarie()
    g = vue360.tuiles(f)
    assert _tuile(g, 'Liste noire')['ton'] == 'bon'
    best = _tuile(g, 'Meilleur chemin')
    assert best['valeur'] == 'majeure · force 0,30' and best['ton'] == 'attention'
    assert _tuile(g, 'Inscrit atteint')['valeur'] == 'INSCRIT EXEMPLE'
    assert _tuile(g, 'Même RIB dans le dossier d’un autre')['ton'] == 'critique'
    f['identite']['inscrit'] = True
    f['liste_noire'] = [dict(label='ZALOU KAMI', typeListe='INDESIRABLE', motif='FAUX DOCUMENTS', statut='actif',
                             premiere_saisie='2020-07-20', type_fraude=None, nb_inscriptions=1)]
    g = vue360.tuiles(f)
    assert _tuile(g, 'Liste noire')['ton'] == 'critique'
    assert _tuile(g, 'Type de liste')['valeur'] == 'INDESIRABLE' and _tuile(g, 'Motif')['valeur'] == 'FAUX DOCUMENTS'
    assert _tuile(g, 'Inscrit depuis')['valeur'] == '2020-07-20'


def test_controles_par_famille():
    t = _tuile(vue360.tuiles(fiche_salarie()), 'Revenus et employeur')
    assert t['valeur'] == '1 anomalie' and t['ton'] == 'attention' and 'EMP-05' in t['detail']


def test_entrepreneur_societes_carte_pro_anciennete():
    g = vue360.tuiles(fiche_entrepreneur())
    assert _tuile(g, 'CABINET EXEMPLE SARL')['valeur'] == 'gérant · associé 60 %'
    assert _tuile(g, 'ANCIENNE EXEMPLE SARL')['ton'] == 'attention'          # rôle terminé
    assert _tuile(g, 'Profession')['valeur'] == 'MEDECIN'
    assert _tuile(g, 'Carte professionnelle valide jusqu’au') == dict(
        _tuile(g, 'Carte professionnelle valide jusqu’au'), valeur='2027-12-31', ton='bon')
    assert _tuile(g, 'Activité depuis')['valeur'] == '2015-03-15'
    assert _tuile(g, 'Type de compte')['valeur'] == 'personnel'
    assert 'Employeur sur le bulletin' not in _libelles(g)


def test_societe_identite_legale_dirigeants_flux_et_reseau():
    g = vue360.tuiles(fiche_societe())
    assert _tuile(g, 'RC')['valeur'] == '9991234 · RABAT'
    assert _tuile(g, 'Forme juridique')['valeur'] == 'SARL'
    assert _tuile(g, 'Capital')['valeur'] == 100000
    assert _tuile(g, 'Immatriculée le')['valeur'] == '2020-02-02'
    gerant = _tuile(g, 'GERANT EXEMPLE')
    assert gerant['valeur'] == 'gérant, associé' and gerant['ton'] == 'critique'   # inscrit, une seule tuile
    assert _tuile(g, 'Crédits par mois')['valeur'] == 9000
    assert _tuile(g, 'BNQ-10 · Flux aller-retour')['ton'] == 'attention'
    assert _tuile(g, 'Sociétés au même siège')['valeur'] == 14
    assert _tuile(g, 'Sociétés sœurs')['valeur'] == 'SOEUR A SARL, SOEUR B SARL'
    assert 'Bulletin de paie' not in _libelles(g)


def test_une_fiche_vide_ne_casse_rien():
    f = fiche_salarie()
    for cle in ('dossiers', 'chemins', 'incoherences', 'alias', 'adresses', 'identifiants', 'societes', 'comptes',
                'donnees', 'charges'):
        f[cle] = []
    f['vue360'].update(revenus=dict(declare=None, pieces={}, ecart=None), controles=[], entite={}, aussi=[])
    toutes = _toutes(vue360.tuiles(f))
    assert toutes and all(t['ton'] in TONS for t in toutes)


def test_la_fonction_ne_modifie_pas_la_fiche():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        avant = copy.deepcopy(f)
        vue360.tuiles(f)
        assert f == avant


def test_un_retraite_n_a_ni_employeur_ni_salaire_verse_par_un_autre():
    f = fiche_salarie()
    f['vue360']['retraite'] = True
    f['donnees'][0]['pieces'].append(_piece('ATTESTATION_PENSION', nom_organisme_retraite='CAISSE EXEMPLE'))
    g = vue360.tuiles(f)
    assert _tuile(g, 'Organisme de pension')['valeur'] == 'CAISSE EXEMPLE'
    assert not {'Employeur relié', 'Salaire versé par un autre', 'Employeur sur le bulletin'} & _libelles(g)
