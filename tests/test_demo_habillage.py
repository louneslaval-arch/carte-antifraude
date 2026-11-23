"""Habillage marocain de la démonstration (outils/demo/habillage_maroc.py, Lounès, 23/11/2026 : « fake data
marocaine ») : les valeurs génériques du générateur (« RUE EXEMPLE », « BANQUE EXEMPLE », « FICTIF FONCTION ») deviennent
des valeurs vraisemblables et les relevés deviennent cohérents avec le salaire. Les identifiants restent fictifs (ZZ,
999) et les pièges du jeu d'essai sont gardés. Seulement pour la démonstration, jamais pour les tests du pipeline."""
import copy
import json
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'outils', 'demo'), os.path.join(RACINE, 'jeu_essai', 'v2')]
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure', 'reference', 'champs_par_type_prod.csv')
pytestmark = pytest.mark.skipif(not os.path.exists(STRUCTURE), reason='structure de Kamal absente')

from pipeline.normalisation.valeurs import montant  # noqa: E402

GENERIQUES = ('RUE EXEMPLE', 'AVENUE EXEMPLE', 'BANQUE EXEMPLE', 'CAISSE EXEMPLE', 'FICTIF FONCTION',
              'FICTIF SITUATION FAMILIALE', 'PROFESSION FICTIVE', 'MARQUE FICTIVE', 'MODELE FICTIF')


@pytest.fixture(scope='module')
def jeu():
    import generer_dossiers as gd
    return gd.generer(n_dossiers=300, n_societes=300, graine=20261119)


@pytest.fixture(scope='module')
def habille(jeu):
    import habillage_maroc as hm
    h = hm.Habillage()
    return [h.dossier(copy.deepcopy(e['dossier'])) for e in jeu.chronologie], h


def _releves(d):
    return [p['fields'] for p in d['pieces'] if p['type'] == 'RELEVE_BANCAIRE']


def test_plus_aucune_valeur_generique(habille):
    dossiers, _ = habille
    texte = json.dumps(dossiers, ensure_ascii=False)
    for g in GENERIQUES:
        assert g not in texte, g
    assert 'BANQUE ' in texte or 'CRÉDIT ' in texte


def test_les_identifiants_restent_fictifs_et_inchanges(jeu, habille):
    dossiers, _ = habille
    for e, d in zip(jeu.chronologie, dossiers):
        avant, apres = e['dossier'], d
        assert avant['ref'] == apres['ref'] and avant['businessData']['civil']['cin'] == apres['businessData']['civil']['cin']
        for p0, p1 in zip(avant['pieces'], apres['pieces']):
            for cle in ('cin', 'numero_cin', 'rib', 'ice', 'numero_ice', 'numero_cnss', 'numero_analytique'):
                assert p0['fields'].get(cle) == p1['fields'].get(cle), cle


def test_une_meme_adresse_donne_toujours_la_meme_et_deux_adresses_restent_distinctes(jeu):
    import habillage_maroc as hm
    h = hm.Habillage()
    a, b = '12 RUE EXEMPLE CASABLANCA', '13 RUE EXEMPLE CASABLANCA'
    assert h.texte(a) == h.texte(a) and h.texte(a) != h.texte(b)
    assert h.texte(a).endswith(', CASABLANCA') and 'EXEMPLE' not in h.texte(a)
    sorties = {h.texte(f'{n} RUE EXEMPLE RABAT') for n in range(1, 2000)}
    assert len(sorties) == 1999, 'aucune adresse partagée par hasard (pas de faux foyer)'
    assert hm.Habillage().texte(a) == h.texte(a), 'déterministe d’une construction à l’autre'


def test_les_releves_sont_coherents_avec_le_salaire(habille):
    dossiers, _ = habille
    vus = 0
    for d in dossiers:
        decl = montant((d['businessData'].get('declared') or {}).get('monthly_income'))
        for r in _releves(d):
            mois = r.get('mois') or []
            for k, m in enumerate(mois):
                assert abs(m['solde_ouverture'] + m['total_credit'] - m['total_debit'] - m['solde_cloture']) < 0.02
                if k:
                    assert m['solde_ouverture'] == mois[k - 1]['solde_cloture']
            if not decl or not isinstance(r.get('montant_salaire'), dict):
                continue
            vus += 1
            salaires = list(r['montant_salaire'].values())
            assert all(0.55 * decl <= s <= decl * 1.001 for s in salaires), (d['ref'], decl, salaires)
            if isinstance(r.get('montant_echeances_credits'), dict):
                ech = set(r['montant_echeances_credits'].values())
                assert len(ech) == 1 and max(ech) <= 0.62 * decl, 'échéances constantes, jamais au-delà de 62 %'
    assert vus > 100


def test_les_pieges_du_jeu_sont_gardes(jeu, habille):
    dossiers, _ = habille
    for e, d in zip(jeu.chronologie, dossiers):
        for p0, p1 in zip(e['dossier']['pieces'], d['pieces']):
            if p0['type'] != 'RELEVE_BANCAIRE':
                continue
            for cle in ('total_mouvements_debit', 'total_mouvements_credit', 'montant_salaire'):
                if cle in p0['fields'] and not isinstance(p0['fields'][cle], dict):
                    assert p1['fields'][cle] == p0['fields'][cle], 'une valeur piège (texte) n’est pas réécrite'


def test_le_socle_prend_les_memes_adresses(jeu):
    import habillage_maroc as hm
    h = hm.Habillage()
    ligne = dict(jeu.monde.annonces[0])
    siege = ligne['siege']
    assert h.ligne(ligne)['siege'] == h.texte(siege) and 'EXEMPLE' not in h.ligne(dict(ligne))['siege']
    assert h.ligne(ligne)['url'].endswith('.invalid/annonce/' + ligne['annonce_id'])
