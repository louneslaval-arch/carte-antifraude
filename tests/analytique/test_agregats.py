"""Agrégats de la couche 7 (`c7_agregat`) : cases de la vérité du jeu d'essai, fourchette de Wilson, parts qui font
100 %, reconstruction identique. Tout est fictif."""
from collections import defaultdict

import pytest

from .commun import CALCULE_LE, SANS_KAMAL, lignes_agregat
from pipeline.analytique import agregats
from pipeline.analytique.indicateurs import FILTRES_CATEGORIE, FILTRES_PRODUIT, NOMS


@pytest.mark.parametrize('k, n, bas, haut', [
    (0, 5, 0.0, 0.434492), (5, 5, 0.565508, 1.0), (1, 1, 0.206543, 1.0), (50, 1000, 0.038130, 0.065314),
    (500, 1000, 0.469069, 0.530931)])
def test_fourchette_de_wilson_contre_des_valeurs_de_reference(k, n, bas, haut):
    b, h = agregats.wilson(k, n)
    assert b == pytest.approx(bas, abs=2e-6) and h == pytest.approx(haut, abs=2e-6)


def test_wilson_sans_effectif_rend_rien():
    assert agregats.wilson(0, 0) == (None, None)


def test_mediane_sans_minimum_ni_maximum_publies():
    assert agregats.mediane([3.0, 1.0, 2.0]) == 2.0
    assert agregats.mediane([1.0, 2.0, 3.0, 10.0]) == 2.5
    assert agregats.mediane([]) is None


def _cle(r):
    return (r['indicateur'], r['filtre_produit'], r['filtre_categorie'], r['dimension1'], r['valeur1'],
            r['dimension2'], r['valeur2'])


@SANS_KAMAL
def test_cases_de_la_verite_du_jeu_d_essai(base_stats, attendu):
    table = {_cle(r): r for r in lignes_agregat(base_stats)}
    assert len(attendu['cases']) >= 30
    for c in attendu['cases']:
        r = table.get(_cle(c))
        assert r is not None, c
        assert r['masque'] == c['masque'], (c, r)
        for champ in ('numerateur', 'denominateur'):
            if c[champ] is not None:
                assert r[champ] == c[champ], (champ, c, r)
        if c['valeur'] is None:
            assert r['valeur'] is None, (c, r)
        else:
            assert r['valeur'] == pytest.approx(c['valeur'], abs=1e-6), (c, r)       # vérité à 6 décimales
    assert {(r['periode_debut'], r['periode_fin']) for r in table.values()} == {
        (attendu['periode_debut'], attendu['periode_fin'])}


@SANS_KAMAL
def test_chaque_tranche_de_filtre_a_son_ensemble(base_stats):
    tranches = {(r['filtre_produit'], r['filtre_categorie']) for r in lignes_agregat(base_stats)
                if r['indicateur'] == 'nb_dossiers' and not r['dimension1']}
    assert tranches == {(p, c) for p in FILTRES_PRODUIT for c in FILTRES_CATEGORIE}


@SANS_KAMAL
def test_tous_les_indicateurs_du_dictionnaire_sont_calcules(base_stats):
    assert {r['indicateur'] for r in lignes_agregat(base_stats)} == set(NOMS)
    assert base_stats.execute('SELECT count(*) FROM c7_indicateur').fetchone()[0] == len(NOMS)


@SANS_KAMAL
def test_taux_avec_fourchette_qui_encadre_la_valeur(base_stats):
    for r in lignes_agregat(base_stats):
        if r['indicateur'].startswith('taux_') and not r['masque']:
            assert r['valeur'] == pytest.approx(r['numerateur'] / r['denominateur'])
            assert r['borne_basse'] <= r['valeur'] <= r['borne_haute'], r


@SANS_KAMAL
def test_parts_d_une_repartition_sans_case_masquee_font_cent_pour_cent(base_stats):
    groupes = defaultdict(list)
    for r in lignes_agregat(base_stats):
        if r['indicateur'].startswith('part_') and not r['dimension2']:
            groupes[(r['indicateur'], r['filtre_produit'], r['filtre_categorie'], r['dimension1'])].append(r)
    complets = [g for g in groupes.values() if not any(r['masque'] for r in g)]
    assert complets
    for g in complets:
        assert sum(r['valeur'] for r in g) == pytest.approx(1.0), g[0]


@SANS_KAMAL
def test_ville_sous_trente_dossiers_regroupee_en_autres_villes(base_stats):
    villes = {r['valeur1'] for r in lignes_agregat(base_stats) if r['dimension1'] == 'ville'}
    assert 'autres villes' in villes and 'CASABLANCA' in villes
    comptes = dict(base_stats.execute(
        "SELECT ville, count(*) FROM c7_variable_dossier WHERE ville IS NOT NULL GROUP BY ville").fetchall())
    for ville in villes - {'autres villes', 'ville inconnue'}:
        assert comptes[ville] >= 30, ville


@SANS_KAMAL
def test_deux_constructions_donnent_la_meme_table(base_stats):
    avant = sorted(map(repr, lignes_agregat(base_stats)))
    agregats.construire(base_stats, calcule_le=CALCULE_LE)
    assert sorted(map(repr, lignes_agregat(base_stats))) == avant


@SANS_KAMAL
def test_periode_restreint_les_dossiers(base_stats, jeu_stats):
    n = agregats.construire(base_stats, periode_debut='2026-10-13', periode_fin='2026-10-19',
                            calcule_le=CALCULE_LE)['dossiers']
    attendu = sum(1 for p in jeu_stats.plan() if p['actif'] and p['recu'].isoformat() <= '2026-10-19')
    assert n == attendu
    agregats.construire(base_stats, calcule_le=CALCULE_LE)


@SANS_KAMAL
def test_noms_de_societes_seulement_sur_option(base_stats):
    sans = {r['dimension1'] for r in lignes_agregat(base_stats)}
    assert not sans & {'banque', 'employeur', 'concessionnaire'}
    agregats.construire(base_stats, avec_noms_societes=True, calcule_le=CALCULE_LE)
    avec = [r for r in lignes_agregat(base_stats) if r['dimension1'] in ('banque', 'concessionnaire')]
    assert avec and all(r['masque'] or (r['numerateur'] or r['denominateur'] or 0) >= 5 for r in avec)
    agregats.construire(base_stats, calcule_le=CALCULE_LE)


@SANS_KAMAL
def test_societe_de_moins_de_cinq_dossiers_jamais_nommee_meme_masquee(base_stats):
    agregats.construire(base_stats, avec_noms_societes=True, calcule_le=CALCULE_LE)
    comptes = {}
    for dim in ('banque', 'employeur', 'concessionnaire'):
        for v, n in base_stats.execute(f'SELECT {dim}, count(*) FROM c7_variable_dossier WHERE {dim} IS NOT NULL '
                                       f'GROUP BY {dim}'):
            comptes[(dim, v)] = n
    for r in lignes_agregat(base_stats):
        for d, v in ((r['dimension1'], r['valeur1']), (r['dimension2'], r['valeur2'])):
            if d in ('banque', 'employeur', 'concessionnaire') and v not in ('autres sociétés', 'non renseigné'):
                assert comptes[(d, v)] >= 5, r
    agregats.construire(base_stats, calcule_le=CALCULE_LE)


def test_societe_rare_regroupee_par_le_lecteur():
    lignes = [dict(banque='BANQUE RARE', employeur=None, concessionnaire=None)] + \
             [dict(banque='BANQUE COURANTE', employeur=None, concessionnaire=None)] * 5
    val = agregats.lecteur({}, agregats.societes_retenues(lignes))
    assert val(lignes[0], 'banque') == 'autres sociétés' and val(lignes[1], 'banque') == 'BANQUE COURANTE'


@SANS_KAMAL
def test_verite_figee_egale_a_une_nouvelle_generation(jeu_stats, attendu):
    """Graine fixe : la vérité versionnée est celle que le générateur produit, jamais retouchée à la main."""
    import json
    assert json.loads(json.dumps(jeu_stats.verite(jeu_stats.plan()), default=str)) == attendu
    assert json.dumps(jeu_stats.dossiers(), sort_keys=True) == json.dumps(jeu_stats.dossiers(), sort_keys=True)


@SANS_KAMAL
def test_employeur_rare_ou_sans_forme_sociale_jamais_nomme(base_stats, jeu_stats):
    agregats.construire(base_stats, avec_noms_societes=True, calcule_le=CALCULE_LE)
    valeurs = {r['valeur1'] for r in lignes_agregat(base_stats)} | {r['valeur2'] for r in lignes_agregat(base_stats)}
    assert jeu_stats.EMPLOYEUR_COURANT in valeurs and jeu_stats.CONCESSION_COURANTE in valeurs
    for nom in (jeu_stats.EMPLOYEUR_RARE, jeu_stats.EMPLOYEUR_PERSONNE, jeu_stats.CONCESSION_RARE):
        assert nom not in valeurs, nom
    agregats.construire(base_stats, calcule_le=CALCULE_LE)


def test_forme_sociale_reconnue():
    assert agregats.est_societe('ZOUKAFA NEGOCE SARL') and agregats.est_societe('Ste Zoukafa')
    assert not agregats.est_societe('KAZEX ZOULORIZ') and not agregats.est_societe('SALAMA')


@SANS_KAMAL
def test_mediane_seulement_sur_dix_valeurs_et_arrondie(base_stats):
    from pipeline.analytique.indicateurs import SEUIL_MEDIANE
    vues = 0
    for r in lignes_agregat(base_stats):
        if r['indicateur'].startswith('mediane_') and not r['masque']:
            vues += 1
            assert r['denominateur'] >= SEUIL_MEDIANE, r
            pas = {'mediane_revenu_verifie': 100, 'mediane_prix_vehicule': 1000, 'mediane_age': 1}[r['indicateur']]
            assert r['valeur'] % pas == 0, r
    assert vues


def test_region_d_une_seule_petite_ville_regroupee():
    lignes = [dict(ville='TIZNIT', region='Souss-Massa')] * 12 + [dict(ville='RABAT', region='Rabat-Salé-Kénitra')] * 40
    villes = {'TIZNIT': 'autres villes', 'RABAT': 'RABAT'}
    assert agregats.regions_isolees(lignes, villes) == {'Souss-Massa'}


def test_aucun_module_servi_ne_lit_la_table_de_travail():
    import pathlib
    from .commun import RACINE
    for f in list(pathlib.Path(RACINE, 'api').rglob('*.py')) + list(pathlib.Path(RACINE, 'front').glob('*')):
        if f.is_file():
            assert 'c7_variable_dossier' not in f.read_text(encoding='utf-8', errors='ignore'), f
