"""Vue 360° en étoile (Lounès, 23/11/2026) : au centre un bonhomme (personne) ou une maison (société), autour ses
informations rangées en branches. Fonction pure sur une fiche construite à la main ; aucune donnée de fraude dans les
branches (l'antifraude reste une petite bande à part). Fictif."""
import os
import sys

from conftest import RACINE
from test_vue360_presentation import MOTS_DE_FRAUDE
from test_vue360_tuiles import fiche_entrepreneur, fiche_salarie, fiche_societe

sys.path.insert(0, os.path.join(RACINE, 'api'))
from app import vue360  # noqa: E402


def _etoile(f):
    return vue360.etoile(f, vue360.presentation(f))


def _branche(e, cle):
    return next((b for b in e['branches'] if b['cle'] == cle), None)


def _valeur(b, libelle):
    return next((x['valeur'] for x in b['lignes'] if x['libelle'] == libelle), None)


def test_le_centre_dit_bonhomme_ou_maison():
    assert _etoile(fiche_salarie())['centre'] == dict(figure='personne', nom='ZALOU KAMI',
                                                      profil='Personne physique · salariée')
    assert _etoile(fiche_entrepreneur())['centre']['profil'] == 'Personne physique · entrepreneur'
    s = _etoile(fiche_societe())['centre']
    assert s['figure'] == 'maison' and s['nom'] == 'SOCIETE EXEMPLE SARL' and s['profil'] == 'Personne morale'


def _connu(f):
    f['donnees'][0]['contexte'].append(dict(libelle='Client connu', valeur='1'))
    return f


def test_branches_du_salarie_dans_l_ordre():
    e = _etoile(_connu(fiche_salarie()))
    assert [b['cle'] for b in e['branches']] == ['identite', 'emploi', 'revenus', 'banque', 'societes', 'demandes',
                                                 'eqdom']
    assert _valeur(_branche(e, 'identite'), 'CIN') == 'ZZ123456'
    assert _valeur(_branche(e, 'identite'), 'Adresse') == '12 RUE EXEMPLE RABAT'
    assert _valeur(_branche(e, 'emploi'), 'Employeur') == 'EMPLOYEUR EXEMPLE SARL'
    assert _valeur(_branche(e, 'emploi'), 'Ancienneté') == 7
    assert _valeur(_branche(e, 'revenus'), 'Revenu mensuel vérifié') == 10000
    assert _valeur(_branche(e, 'banque'), 'Banque') == 'BANQUE EXEMPLE'
    assert _valeur(_branche(e, 'eqdom'), 'Client connu') == 'oui'
    societe = _branche(e, 'societes')['lignes'][0]
    assert societe == dict(libelle='associé', valeur='SOCIETE AUSSI SARL', format='texte', lien='fiche.html?i=7')


def test_un_salarie_sans_societe_n_a_pas_de_branche_vide():
    f = fiche_salarie()
    f['vue360']['aussi'], f['comptes'] = [], []
    f['donnees'][0]['pieces'] = [p for p in f['donnees'][0]['pieces'] if p['type'] != 'RELEVE_BANCAIRE']
    cles = [b['cle'] for b in _etoile(f)['branches']]
    assert 'societes' not in cles and 'banque' not in cles
    assert all(b['lignes'] for b in _etoile(f)['branches'])


def test_branches_de_l_entrepreneur():
    e = _etoile(fiche_entrepreneur())
    assert [b['cle'] for b in e['branches']][:3] == ['identite', 'activite', 'revenus']
    assert _valeur(_branche(e, 'activite'), 'Profession') == 'MEDECIN'
    assert _valeur(_branche(e, 'activite'), 'Activité depuis') == 11
    noms = [x['valeur'] for x in _branche(e, 'societes')['lignes']]
    assert noms == ['CABINET EXEMPLE SARL', 'ANCIENNE EXEMPLE SARL']
    assert _branche(e, 'societes')['lignes'][1]['libelle'] == 'gérant sortant · terminé'


def test_branches_de_la_societe_avec_gerants_et_parts():
    f = fiche_societe()
    f['personnes'] = [dict(indice=3, nom='GERANT EXEMPLE', role='gérant', parts=None),
                      dict(indice=3, nom='GERANT EXEMPLE', role='associé', parts=60),
                      dict(indice=4, nom='ASSOCIE EXEMPLE', role='associé', parts=40)]
    e = _etoile(_connu(f))
    assert [b['cle'] for b in e['branches']] == ['legal', 'activite', 'dirigeants', 'siege', 'groupe', 'flux',
                                                 'demandes', 'eqdom']
    assert _valeur(_branche(e, 'legal'), 'RC') == '9991234 · RABAT'
    assert _valeur(_branche(e, 'legal'), 'ICE') == '999000000000001'
    assert _valeur(_branche(e, 'legal'), 'Capital') == 100000
    gerant = _branche(e, 'dirigeants')['lignes'][0]
    assert gerant == dict(libelle='gérant, associé · 60 %', valeur='GERANT EXEMPLE', format='texte', lien='fiche.html?i=3')
    assert [x['valeur'] for x in _branche(e, 'groupe')['lignes']] == ['SOEUR A SARL', 'SOEUR B SARL']
    assert _valeur(_branche(e, 'siege'), 'Adresse') == '5 AV EXEMPLE RABAT'


def test_les_demandes_menent_au_dossier_et_portent_le_rythme():
    b = _branche(_etoile(fiche_salarie()), 'demandes')
    assert b['resume'] == '1 demande, le 15 sept. 2026'
    assert b['lignes'][0] == dict(libelle='15 sept. 2026', valeur='Crédit disponible', format='texte',
                                  lien='dossier.html?i=1', ton='conforme')


def test_aucune_donnee_de_fraude_dans_les_branches():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        f['identite']['inscrit'] = True
        e = _etoile(f)
        texte = ' '.join(str(x.get(k)) for b in e['branches'] for x in b['lignes'] for k in ('libelle', 'valeur'))
        texte += ' '.join(b['titre'] for b in e['branches'])
        assert not any(m in texte.lower() for m in MOTS_DE_FRAUDE), fabrique.__name__


def test_fiche_vide_garde_le_centre_et_la_branche_demandes():
    f = fiche_salarie()
    for cle in ('dossiers', 'chemins', 'incoherences', 'societes', 'comptes', 'donnees', 'charges', 'identifiants'):
        f[cle] = []
    f['identite'].update(cin=None, adresse=None, date_naissance=None)
    f['vue360'].update(aussi=[], revenus=dict(declare=None, pieces={}, ecart=None), controles=[], entite={})
    e = _etoile(f)
    assert e['centre']['figure'] == 'personne'
    assert [b['cle'] for b in e['branches']] == ['demandes']
    assert _branche(e, 'demandes')['resume'] == 'aucune demande en propre'
