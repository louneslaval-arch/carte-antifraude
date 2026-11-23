"""Vue 360° pensée pour la direction (Lounès, 23/11/2026 : « que les dirigeants puissent tout comprendre d'un client,
sans inventer de données qu'on n'aura pas ») : au centre, qui est le client, ses signaux et l'essentiel chiffré ; autour,
trois zones qui répondent chacune à une question (qui est-ce ? peut-il rembourser ? que s'est-il passé ?) ; les sources
pas encore branchées passent en pied de page. Fonction pure sur une fiche construite à la main. Fictif."""
import os
import sys

from conftest import RACINE
from test_vue360_tuiles import fiche_entrepreneur, fiche_salarie, fiche_societe

sys.path.insert(0, os.path.join(RACINE, 'api'))
from app import vue360  # noqa: E402

ZONES = ('qui', 'capacite', 'historique')


def _etoile(f):
    return vue360.etoile(f, vue360.presentation(f))


def _branche(e, cle):
    return next((b for b in e['branches'] if b['cle'] == cle), None)


def _valeur(b, libelle):
    return next((x['valeur'] for x in b['lignes'] if x['libelle'] == libelle), None)


def _signal(e, cle):
    return next(s for s in e['signaux'] if s['cle'] == cle)


def test_le_centre_dit_qui_en_quelques_faits():
    f = fiche_salarie()
    f['donnees'][0]['contexte'] += [dict(libelle='Client connu', valeur=0), dict(libelle='Agence', valeur='AG07'),
                                    dict(libelle='Ville de l\'agence', valeur='RABAT')]
    assert _etoile(f)['centre']['faits'] == ['46 ans', 'nouveau client', 'agence AG07 · RABAT',
                                             'première demande le 15 sept. 2026']


def test_trois_signaux_factuels_au_centre():
    e = _etoile(fiche_salarie())
    assert [s['cle'] for s in e['signaux']] == ['liste_noire', 'reseau', 'controles']
    assert _signal(e, 'liste_noire')['valeur'] == 'Non inscrit' and _signal(e, 'liste_noire')['ton'] == 'bon'
    reseau = _signal(e, 'reseau')
    assert reseau['valeur'] == 'À 2 liens d’une personne inscrite' and reseau['ton'] == 'attention'
    assert 'INSCRIT EXEMPLE' in reseau['detail']
    assert _signal(e, 'controles')['valeur'] == '1 anomalie sur 1 contrôle'


def test_un_client_sans_lien_ni_anomalie_est_dit_en_clair():
    f = fiche_salarie()
    f['chemins'] = []
    f['vue360']['controles'][0].update(anomalies=0)
    f['vue360']['controles'][0]['controles'][0]['resultat'] = 'CONFORME'
    e = _etoile(f)
    assert _signal(e, 'reseau') == dict(cle='reseau', libelle='Réseau', valeur='Aucune personne inscrite à moins de 4 liens',
                                        ton='bon', detail=None)
    assert _signal(e, 'controles')['valeur'] == '1 contrôle sur 1 conforme' and _signal(e, 'controles')['ton'] == 'bon'


def test_l_inscrit_est_dit_inscrit():
    f = fiche_salarie()
    f['identite']['inscrit'] = True
    assert _signal(_etoile(f), 'liste_noire')['ton'] == 'critique'


def test_un_inscrit_n_est_pas_sa_propre_personne_inscrite_la_plus_proche():
    f = fiche_salarie()
    f['indice'], f['identite']['inscrit'] = 9, True
    f['chemins'][0].update(longueur=0, niveau='critique')
    e = _etoile(f)
    assert _signal(e, 'reseau')['valeur'] == 'Une identité du dossier est inscrite' and _signal(e, 'reseau')['detail'] is None
    assert _valeur(_branche(e, 'liste_noire'), 'Personne inscrite la plus proche') is None


def test_l_essentiel_du_salarie_repond_a_peut_il_rembourser():
    ess = _etoile(fiche_salarie())['essentiel']
    chiffres = {c['libelle']: c for c in ess['chiffres']}
    assert list(chiffres) == ['Revenu vérifié', 'Taux d’endettement', 'Reste après crédits', 'Ancienneté chez l’employeur']
    assert chiffres['Revenu vérifié']['valeur'] == 10000
    assert chiffres['Taux d’endettement']['valeur'] == 0.47 and chiffres['Taux d’endettement']['ton'] == 'attention'
    assert chiffres['Reste après crédits']['valeur'] == 5300        # 10 000 − 3 200 d'échéances − 1 500 à la source
    assert chiffres['Ancienneté chez l’employeur']['valeur'] == 7
    assert 'Endettement élevé (47 % du revenu)' in ess['vigilance']
    assert 'CIN expirée à la date du dernier dossier' in ess['vigilance']
    assert 'Emploi stable : 7 ans chez le même employeur' in ess['forts']


def test_l_essentiel_de_la_societe():
    chiffres = [c['libelle'] for c in _etoile(fiche_societe())['essentiel']['chiffres']]
    assert chiffres == ['Crédits mensuels', 'Échéances de crédit par mois', 'Ancienneté de la société', 'Capital']


def test_chaque_plaque_est_rangee_dans_une_zone_et_dans_l_ordre():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        e = _etoile(fabrique())
        zones = [b['zone'] for b in e['branches']]
        assert set(zones) <= set(ZONES) and zones == sorted(zones, key=ZONES.index), fabrique.__name__
        assert [b['cle'] for b in e['branches'] if b['zone'] == 'historique'][-2:] == ['liste_noire', 'controles']
    cles = [b['cle'] for b in _etoile(fiche_salarie())['branches']]
    assert cles == ['identite', 'emploi', 'societes', 'revenus', 'credits', 'banque', 'demandes', 'liste_noire', 'controles']
    cles = [b['cle'] for b in _etoile(fiche_societe())['branches']]
    assert cles == ['legal', 'activite', 'siege', 'dirigeants', 'groupe', 'flux', 'demandes', 'liste_noire', 'controles']


def test_les_revenus_en_barres_sans_repetition():
    b = _branche(_etoile(fiche_salarie()), 'revenus')
    assert b['visuel'] == dict(type='barres', items=[
        dict(libelle='Déclaré', valeur=10000), dict(libelle='Bulletin de paie', valeur=10000),
        dict(libelle='Attestation de salaire', valeur=10000), dict(libelle='Relevés (dernier mois)', valeur=8000)])
    assert [x['libelle'] for x in b['lignes']] == ['Écart entre pièces']


def test_les_credits_en_jauge_avec_le_repere_provisoire():
    b = _branche(_etoile(fiche_salarie()), 'credits')
    assert b['titre'] == 'Crédits en cours'
    assert b['visuel'] == dict(type='jauge', libelle='Taux d’endettement', valeur=0.47, repere=0.4, ton='attention',
                               note='repère de 40 % provisoire, à valider par la direction des risques')
    assert _valeur(b, 'Échéances repérées sur les relevés') == 3200
    assert _valeur(b, 'Crédit prélevé à la source') == 1500
    assert _valeur(b, 'Reste après crédits') == 5300


def test_les_releves_mois_par_mois():
    b = _branche(_etoile(fiche_salarie()), 'banque')
    assert b['visuel'] == dict(type='tableau', colonnes=['juil. 2026', 'août 2026'], lignes=[
        dict(libelle='Salaire reçu', valeurs=[7900, 8000]), dict(libelle='Échéances de crédit', valeurs=[3000, 3200]),
        dict(libelle='Solde en fin de mois', valeurs=[1000, 1000])])
    assert _valeur(b, 'RIB') == '••• 0001 · BANQUE EXEMPLE'
    assert _valeur(b, 'Banque') is None and _valeur(b, 'Comptes lus') is None, 'déjà dans le RIB ; un seul compte'
    pm = _branche(_etoile(fiche_societe()), 'flux')['visuel']
    assert [x['libelle'] for x in pm['lignes']] == ['Crédits', 'Débits', 'Échéances de crédit', 'Solde en fin de mois']


def test_le_chemin_vers_l_inscrit_est_explique():
    f = fiche_salarie()
    f['chemins'][0].update(longueur=1, etapes=[dict(type='identifiant', code='RIB', de=dict(indice=1, nom='ZALOU KAMI'),
                                                    vers=dict(indice=9, nom='INSCRIT EXEMPLE', inscrit=True))])
    e = _etoile(f)
    assert _signal(e, 'reseau')['detail'] == 'même RIB que INSCRIT EXEMPLE, sur la liste noire'
    b = _branche(e, 'liste_noire')
    assert b['visuel'] == dict(type='chemin', etapes=[dict(de='ZALOU KAMI', lien='même RIB', vers='INSCRIT EXEMPLE',
                                                           inscrit=True, fiche='fiche.html?i=9')])
    assert not any(x['libelle'] in ('Meilleur chemin', 'Inscrit atteint') for x in b['lignes']), 'plus de jargon'


def test_les_controles_tous_conformes_tiennent_en_une_ligne():
    f = fiche_salarie()
    f['vue360']['controles'] = [dict(famille=n, anomalies=0, controles=[dict(controle=c, libelle='x', resultat='CONFORME')])
                                for n, c in (('Identité', 'IDT-01'), ('Relevés bancaires', 'BNQ-01'))]
    lignes = _branche(_etoile(f), 'controles')['lignes']
    assert lignes == [dict(libelle='Contrôles de la v2', valeur='2 sur 2 conformes', format='texte', lien=None, ton='bon',
                           detail='Identité, Relevés bancaires')]


def test_les_sources_a_venir_passent_en_pied_et_eqdom_au_centre():
    e = _etoile(fiche_salarie())
    assert [x['libelle'] for x in e['a_venir']] == ['Historique EQDOM', 'Recouvrement', 'Salaire versé par un autre']
    assert all(x['valeur'] != 'à venir' for b in e['branches'] for x in b['lignes'])
    assert _branche(e, 'eqdom') is None


def test_identite_avec_la_situation_familiale_lue_sur_les_pieces():
    f = fiche_salarie()
    f['donnees'][0]['pieces'][0]['faits'] += [dict(cle='situation_familiale', valeur='MARIÉ(E)'),
                                              dict(cle='nombre_enfants', valeur='2')]
    assert _valeur(_branche(_etoile(f), 'identite'), 'Situation familiale') == 'MARIÉ(E) · 2 enfants'


def test_l_emploi_sans_detail_inutile():
    b = _branche(_etoile(fiche_salarie()), 'emploi')
    anciennete = next(x for x in b['lignes'] if x['libelle'] == 'Ancienneté')
    assert anciennete['valeur'] == 7 and anciennete['detail'] == 'depuis le 1 juin 2019'
    assert _valeur(b, 'Date d’embauche') is None
    assert _valeur(b, 'Clients EQDOM chez cet employeur') == 12, 'gardé : plus d’un client chez cet employeur'


def test_la_carte_professionnelle_expiree_est_un_point_de_vigilance():
    f = fiche_entrepreneur()
    f['donnees'][0]['pieces'][-2]['faits'][1]['valeur'] = '31/12/2025'
    assert 'Carte professionnelle expirée à la date du dernier dossier' in _etoile(f)['essentiel']['vigilance']
    assert 'Carte professionnelle expirée à la date du dernier dossier' not in _etoile(fiche_entrepreneur())['essentiel']['vigilance']
