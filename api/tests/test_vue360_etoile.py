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
    c = _etoile(fiche_salarie())['centre']
    assert (c['figure'], c['nom'], c['profil']) == ('personne', 'ZALOU KAMI', 'Personne physique · salariée')
    assert _etoile(fiche_entrepreneur())['centre']['profil'] == 'Personne physique · entrepreneur'
    s = _etoile(fiche_societe())['centre']
    assert s['figure'] == 'maison' and s['nom'] == 'SOCIETE EXEMPLE SARL' and s['profil'] == 'Personne morale'


def _connu(f):
    f['donnees'][0]['contexte'].append(dict(libelle='Client connu', valeur='1'))
    return f


def test_branches_du_salarie_dans_l_ordre():
    e = _etoile(_connu(fiche_salarie()))
    assert [b['cle'] for b in e['branches']] == ['identite', 'emploi', 'societes', 'revenus', 'credits', 'banque',
                                                 'demandes', 'liste_noire', 'controles']
    assert _valeur(_branche(e, 'identite'), 'CIN') == 'ZZ123456'
    assert _valeur(_branche(e, 'identite'), 'Adresse') == '12 RUE EXEMPLE RABAT'
    assert _valeur(_branche(e, 'emploi'), 'Employeur') == 'EMPLOYEUR EXEMPLE SARL'
    assert _valeur(_branche(e, 'emploi'), 'Ancienneté') == 7
    assert _branche(e, 'revenus')['visuel']['items'][1] == dict(libelle='Bulletin de paie', valeur=10000)
    assert _valeur(_branche(e, 'banque'), 'RIB') == '••• 0001 · BANQUE EXEMPLE'
    assert 'client EQDOM' in e['centre']['faits']
    societe = _branche(e, 'societes')['lignes'][0]
    assert societe == dict(libelle='associé', valeur='SOCIETE AUSSI SARL', format='texte', lien='fiche.html?i=7')


def test_un_salarie_sans_societe_n_a_pas_de_branche_vide():
    f = fiche_salarie()
    f['vue360']['aussi'], f['comptes'], f['charges'] = [], [], []
    f['donnees'][0]['pieces'] = [p for p in f['donnees'][0]['pieces'] if p['type'] != 'RELEVE_BANCAIRE']
    cles = [b['cle'] for b in _etoile(f)['branches']]
    assert 'societes' not in cles and 'banque' not in cles
    assert all(b['lignes'] for b in _etoile(f)['branches'])


def test_branches_de_l_entrepreneur():
    e = _etoile(fiche_entrepreneur())
    assert [b['cle'] for b in e['branches']][:3] == ['identite', 'activite', 'societes']
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
    assert [b['cle'] for b in e['branches']] == ['legal', 'activite', 'siege', 'dirigeants', 'groupe', 'flux',
                                                 'demandes', 'liste_noire', 'controles']
    assert _valeur(_branche(e, 'legal'), 'RC') == '9991234 · RABAT'
    assert _valeur(_branche(e, 'legal'), 'ICE') == '999000000000001'
    assert _valeur(_branche(e, 'legal'), 'Capital') == 100000
    gerant = _branche(e, 'dirigeants')['lignes'][0]
    assert gerant == dict(libelle='gérant, associé · 60 %', valeur='GERANT EXEMPLE', format='texte', lien='fiche.html?i=3')
    assert [x['valeur'] for x in _branche(e, 'groupe')['lignes']] == ['SOEUR A SARL', 'SOEUR B SARL']
    assert _valeur(_branche(e, 'siege'), 'Adresse') == '5 AV EXEMPLE RABAT'
    libelles = [x['libelle'] for x in _toutes_les_lignes(e)]
    assert libelles.count('Forme juridique') == 1 and libelles.count('RC') == 1 and 'Crédits mensuels' not in libelles
    credits = next(c for c in e['essentiel']['chiffres'] if c['libelle'] == 'Crédits mensuels')
    assert credits['valeur'] == 9000                                      # moyenne des crédits des relevés


def test_les_demandes_menent_au_dossier_et_portent_le_rythme():
    b = _branche(_etoile(fiche_salarie()), 'demandes')
    assert b['resume'] == '1 demande, le 15 sept. 2026'
    assert b['lignes'][0] == dict(libelle='15 sept. 2026', valeur='Crédit disponible', format='texte',
                                  lien='dossier.html?i=1', ton='conforme')


ANTIFRAUDE = ('liste_noire', 'controles')


def test_la_fraude_reste_sur_ses_plaques():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        f['identite']['inscrit'] = True
        e = _etoile(f)
        autres = [b for b in e['branches'] if b['cle'] not in ANTIFRAUDE]
        texte = ' '.join(str(x.get(k)) for b in autres for x in b['lignes'] for k in ('libelle', 'valeur', 'detail'))
        texte += ' '.join(b['titre'] for b in autres)
        assert not any(m in texte.lower() for m in MOTS_DE_FRAUDE), fabrique.__name__
        assert [b['cle'] for b in e['branches']][-len(ANTIFRAUDE):] == list(ANTIFRAUDE), 'les plaques antifraude ferment l’étoile'
        assert _valeur(_branche(e, 'liste_noire'), 'Liste noire') == 'Inscrit'


# Dites autrement (Lounès, 23/11/2026, lecture par la direction) : le meilleur chemin et l'inscrit atteint dans le signal
# « Réseau » et la ligne « Personne inscrite la plus proche » ; la date d'embauche dans le détail de l'ancienneté ; les
# revenus des pièces en barres ; un seul client chez l'employeur n'est pas montré.
ABSORBEES = {'Meilleur chemin', 'Inscrit atteint', 'Date d’embauche', 'Salaire retrouvé sur les relevés',
             'Revenu retrouvé sur les relevés', 'Revenu déclaré', 'Clients EQDOM qui le déclarent'}


# ---- toutes les informations sur les plaques (Lounès, 23/11/2026 : « vraiment toutes les infos visibles ») --------
def _toutes_les_lignes(e):
    return [x for b in e['branches'] for x in b['lignes']]


def test_chaque_tuile_du_detail_est_sur_une_plaque():
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        e = _etoile(f)
        lignes = _toutes_les_lignes(e) + e['essentiel']['chiffres'] + e['signaux'] + e['a_venir']
        lignes += [i for b in e['branches'] if b.get('visuel', {}).get('type') == 'barres' for i in b['visuel']['items']]
        lignes += [b['visuel'] for b in e['branches'] if b.get('visuel', {}).get('type') == 'jauge']
        vus = {x['libelle'] for x in lignes} | {str(x.get('valeur')) for x in lignes} | {x['lien'] for x in lignes if x.get('lien')}
        vus |= ABSORBEES
        for g in vue360.tuiles(f):
            if g['groupe'] == 'Alertes':          # résumés : chaque incohérence et chaque famille ont leur ligne
                continue
            for t in g['tuiles']:
                liste = isinstance(t['valeur'], str) and all(n in vus for n in t['valeur'].split(', '))
                assert t['libelle'] in vus or liste or (t['valeur'] is not None and str(t['valeur']) in vus) \
                    or t.get('lien') in vus, (fabrique.__name__, t['libelle'])


def test_aucune_plaque_alertes_meme_avec_des_incoherences():
    """Lounès, 23/11/2026 : « retire-la partout ». Les incohérences restent dans les données brutes."""
    for fabrique in (fiche_salarie, fiche_entrepreneur, fiche_societe):
        f = fabrique()
        assert f['incoherences'] or fabrique is not fiche_salarie
        e = _etoile(f)
        assert _branche(e, 'alertes') is None, fabrique.__name__
        assert 'Alertes' not in [b['titre'] for b in e['branches']]


def test_les_lignes_venues_du_detail_gardent_ton_et_precision():
    e = _etoile(fiche_salarie())
    ecart = next(x for x in _branche(e, 'revenus')['lignes'] if x['libelle'] == 'Écart entre pièces')
    assert ecart['ton'] == 'attention' and ecart['detail'] == 'signalé au-delà de 15 %' and ecart['format'] == 'pourcent'
    famille = _branche(e, 'controles')['lignes'][0]
    assert famille['libelle'] == 'Revenus et employeur' and famille['valeur'] == '1 anomalie sur 1'
    assert 'EMP-05' in famille['detail'] and famille['ton'] == 'attention'


def test_identite_et_banque_portent_tout_ce_qui_est_lu():
    e = _etoile(fiche_salarie())
    identite = _branche(e, 'identite')
    assert _valeur(identite, 'N° CNSS') == '999123456'
    assert _valeur(identite, 'Autres écritures du nom') == 'ZALOU KAMY'
    assert _valeur(identite, 'Expiration de la CIN') == '2026-01-31'
    assert _valeur(_branche(e, 'banque'), 'RIB') == '••• 0001 · BANQUE EXEMPLE'
    assert _valeur(_branche(e, 'credits'), 'Crédit prélevé à la source') == 1500


def test_ce_qui_viendra_est_chez_eqdom():
    a_venir = next(x for x in _etoile(fiche_salarie())['a_venir'] if x['libelle'] == 'Historique EQDOM')
    assert 'classe BAM' in a_venir['detail']


def test_fiche_vide_garde_le_centre_et_la_branche_demandes():
    f = fiche_salarie()
    for cle in ('dossiers', 'chemins', 'incoherences', 'societes', 'comptes', 'donnees', 'charges', 'identifiants',
                'alias', 'adresses'):
        f[cle] = []
    f['identite'].update(cin=None, adresse=None, date_naissance=None)
    f['vue360'].update(aussi=[], revenus=dict(declare=None, pieces={}, ecart=None), controles=[], entite={})
    e = _etoile(f)
    assert e['centre']['figure'] == 'personne'
    assert [b['cle'] for b in e['branches']] == ['demandes', 'liste_noire']
    assert _branche(e, 'demandes')['resume'] == 'aucune demande en propre'
