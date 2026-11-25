"""Variables par dossier de la couche 7 (`c7_variable_dossier`) : fonctions pures sur des cas construits à la main,
puis chaque dossier du jeu d'essai comparé à son plan. Tout est fictif."""
import pytest

from .commun import SANS_KAMAL
from pipeline.analytique import variables as v
from pipeline.analytique.regions import REGION_DE_VILLE


# ---- âge et tranches ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('naissance, reference, attendu', [
    ('1990-11-17', '2026-11-17', 36),           # anniversaire le jour même : révolu
    ('1990-11-18', '2026-11-17', 35),           # la veille de l'anniversaire
    ('2008-11-17', '2026-11-17', 18),           # borne basse comprise
    ('2008-11-18', '2026-11-17', None),         # 17 ans : hors bornes
    ('1936-11-17', '2026-11-17', 90),           # borne haute comprise
    ('1935-11-16', '2026-11-17', None),         # 91 ans
    ('2000-02-29', '2026-02-28', 25),           # né un 29 février
    (None, '2026-11-17', None),
    ('1990-11-17', None, None),
])
def test_age_revolu_au_jour_pres_et_hors_bornes_mis_a_null(naissance, reference, attendu):
    assert v.age_revolu(naissance, reference) == attendu


@pytest.mark.parametrize('fonction, valeur, attendu', [
    ('tranche_age', 18, '18–25'), ('tranche_age', 25, '18–25'), ('tranche_age', 26, '26–35'),
    ('tranche_age', 65, '56–65'), ('tranche_age', 66, 'plus de 65'), ('tranche_age', None, None),
    ('tranche_revenu', 2999.99, 'moins de 3 000'), ('tranche_revenu', 3000, '3 000–4 999'),
    ('tranche_revenu', 4999.99, '3 000–4 999'), ('tranche_revenu', 12000, '12 000–19 999'),
    ('tranche_revenu', 20000, '20 000 et plus'),
    ('tranche_ecart', -0.21, 'plus de 20 % en dessous'), ('tranche_ecart', -0.2, '±20 %'),
    ('tranche_ecart', 0.2, '±20 %'), ('tranche_ecart', 0.2001, 'plus de 20 % au-dessus'),
    ('tranche_anciennete', 0.99, 'moins de 1 an'), ('tranche_anciennete', 1, '1–3 ans'),
    ('tranche_anciennete', 3, '3–5 ans'), ('tranche_anciennete', 10, 'plus de 10 ans'),
    ('tranche_prix', 99999, 'moins de 100 000'), ('tranche_prix', 100000, '100 000–199 999'),
    ('tranche_prix', 500000, '500 000 et plus'),
    ('tranche_age_societe', 0.5, 'moins de 1 an'), ('tranche_age_societe', 2, '2–5 ans'),
    ('tranche_age_societe', 10.5, 'plus de 10 ans'),
    ('tranche_capital', 9999, 'moins de 10 000'), ('tranche_capital', 10000, '10 000–99 999'),
    ('tranche_capital', 1000000, '1 million et plus'),
])
def test_tranches_aux_bornes(fonction, valeur, attendu):
    assert getattr(v, fonction)(valeur) == attendu


def test_semaine_iso_y_compris_a_cheval_sur_deux_annees():
    assert v.semaine_iso('2026-11-12') == '2026-S46'
    assert v.semaine_iso('2027-01-01') == '2026-S53'
    assert v.semaine_iso(None) is None


@pytest.mark.parametrize('saisi, attendu', [('M', 'H'), ('masculin', 'H'), ('Homme', 'H'), ('F', 'F'),
                                            ('FEMININ', 'F'), ('femme', 'F'), ('X', None), (None, None)])
def test_sexe_normalise_en_h_ou_f(saisi, attendu):
    assert v.normaliser_sexe(saisi) == attendu


@pytest.mark.parametrize('saisi, attendu', [('CDI', 'CDI'), ('cdd', 'CDD'), ('Contrat à durée indéterminée', 'CDI'),
                                            ('INTERIM', 'autre'), ('', None), (None, None)])
def test_type_de_contrat_normalise(saisi, attendu):
    assert v.normaliser_contrat(saisi) == attendu


@pytest.mark.parametrize('saisi, attendu', [('NEUF', 'neuf'), ('Occasion', 'occasion'), ('VO', 'occasion'),
                                            ('FICTIF', None), (None, None)])
def test_etat_du_vehicule_normalise(saisi, attendu):
    assert v.normaliser_etat(saisi) == attendu


def test_banque_rapprochee_de_ses_graphies():
    assert v.normaliser_banque('BQ TAZOULA') == v.normaliser_banque('Banque  Tazoula') == 'BANQUE TAZOULA'
    assert v.normaliser_banque(None) is None


# ---- revenu vérifié : ordre des sources ----------------------------------------------------------------------------

def test_revenu_bulletin_le_plus_recent_avant_attestation_pension_releve():
    r = v.choisir_revenu(bulletins=[('2026-08', 8000.0), ('2026-09', 8100.0)], attestations=[7000.0],
                         pensions=[6000.0], releves=[5000.0, 5200.0])
    assert r == (8100.0, 'bulletin')
    assert v.choisir_revenu(attestations=[7000.0], pensions=[6000.0]) == (7000.0, 'attestation')
    assert v.choisir_revenu(pensions=[6000.0], releves=[5000.0]) == (6000.0, 'pension')
    assert v.choisir_revenu(releves=[5000.0, 5400.0, 9000.0]) == (5400.0, 'releve')      # médiane des mois
    assert v.choisir_revenu() == (None, 'aucun')


def test_revenu_hors_bornes_ecarte_puis_source_suivante():
    assert v.choisir_revenu(bulletins=[('2026-09', 200.0)], attestations=[7000.0]) == (7000.0, 'attestation')
    assert v.choisir_revenu(bulletins=[('2026-09', 600000.0)]) == (None, 'aucun')


@pytest.mark.parametrize('saisi, attendu', [('30 000,00', 30000.0), ('1.250,50 DH', 1250.5), (8100, 8100.0)])
def test_montants_ecrits_en_texte_lus_par_la_normalisation_du_depot(saisi, attendu):
    assert v.choisir_revenu(attestations=[v.montant(saisi)]) == (attendu, 'attestation')


def test_ecart_de_revenu_seulement_si_les_deux_existent():
    assert v.ecart_relatif(8000.0, 10000.0) == pytest.approx(-0.2)
    assert v.ecart_relatif(None, 10000.0) is None and v.ecart_relatif(8000.0, None) is None
    assert v.ecart_relatif(8000.0, 0) is None


# ---- ville : ordre des sources et référentiel ----------------------------------------------------------------------

def test_ville_par_ordre_des_sources_et_graphies_du_referentiel():
    assert v.choisir_ville(domiciliation=['FES'], cin=['AGADIR'], releve=['TANGER']) == ('FES', 'quittance')
    assert v.choisir_ville(cin=['12 RUE EXEMPLE MARRAKCH']) == ('MARRAKECH', 'CIN')
    assert v.choisir_ville(cin=['CASA']) == ('CASABLANCA', 'CIN')
    assert v.choisir_ville(domiciliation=['ZOUKAVILLE'], releve=['7 AVENUE EXEMPLE TANGER']) == ('TANGER', 'relevé')
    assert v.choisir_ville(cin=['ZOUKAVILLE']) == (None, 'aucune')


def test_toutes_les_villes_du_referentiel_ont_une_des_douze_regions():
    from pipeline import construire_base
    villes = {c for c, *_ in construire_base.VILLES}
    assert villes <= set(REGION_DE_VILLE)
    assert len(set(REGION_DE_VILLE.values())) == 12


# ---- chaque dossier du jeu d'essai contre son plan ------------------------------------------------------------------

@SANS_KAMAL
def test_variables_du_jeu_d_essai_egales_au_plan(base_stats, plan_stats):
    cx = base_stats
    noms = [c[1] for c in cx.execute('PRAGMA table_info(c7_variable_dossier)')]
    lignes = {r[0]: dict(zip(noms, r)) for r in cx.execute('SELECT * FROM c7_variable_dossier')}
    actifs = {r: p for r, p in plan_stats.items() if p['actif']}
    assert set(lignes) == set(actifs) and len(actifs) < len(plan_stats)          # archivés écartés par défaut
    for ref, p in actifs.items():
        x = lignes[ref]
        assert (x['type_personne'], x['produit'], x['categorie'], x['semaine']) == \
               (p['type_personne'], p['produit'], p['categorie'], p['semaine']), ref
        assert x['verdict'] == (p['verdict'] or 'sans verdict') and x['juge_suspect'] == p['juge_suspect'], ref
        assert x['age'] == p.get('age'), ref
        assert x['sexe'] == p.get('sexe'), ref
        assert x['source_revenu'] == p['source_revenu'], ref
        assert (x['revenu_verifie'] is None and p['revenu'] is None) or x['revenu_verifie'] == pytest.approx(p['revenu'])
        assert x['ville'] == p['ville'] and x['region'] == REGION_DE_VILLE.get(p['ville']), ref
        assert x['releve_lignes_lues'] == int(p['lignes_lues']), ref
        assert x['vehicule_etat'] == (None if p['produit'] == 'DISPO' else p['etat'].lower()), ref
        assert x['associe_unique'] == (None if p['type_personne'] == 'PP' else int(p['associes'] == 1)), ref
        assert x['banque'] == p['banque'][1], ref


@SANS_KAMAL
def test_variable_incalculable_vaut_null_jamais_devinee(base_stats, plan_stats):
    pm = [r for r, p in plan_stats.items() if p['type_personne'] == 'PM' and p['actif']]
    for ref in pm:
        age, sexe, revenu = base_stats.execute('SELECT age, sexe, revenu_verifie FROM c7_variable_dossier WHERE ref = ?',
                                               (ref,)).fetchone()
        assert (age, sexe, revenu) == (None, None, None)


@SANS_KAMAL
def test_verdict_provisoire_ou_analyse_en_cours_compte_sans_verdict(base_stats, plan_stats):
    vus = set()
    for ref, p in plan_stats.items():
        if p['actif'] and (p['provisoire'] or p['statut'] == 'EN_COURS'):
            verdict, juge = base_stats.execute('SELECT verdict, juge_suspect FROM c7_variable_dossier WHERE ref = ?',
                                               (ref,)).fetchone()
            assert (verdict, juge) == ('sans verdict', None), ref
            vus.add(p['provisoire'])
    assert vus == {True, False}


@SANS_KAMAL
def test_age_et_sexe_lus_sur_la_cin_du_demandeur_pas_sur_celle_de_la_caution(base_stats, plan_stats):
    cautions = [r for r, p in plan_stats.items() if p['actif'] and p.get('caution')]
    assert cautions
    for ref in cautions:
        age, sexe = base_stats.execute('SELECT age, sexe FROM c7_variable_dossier WHERE ref = ?', (ref,)).fetchone()
        assert (age, sexe) == (plan_stats[ref]['age'], plan_stats[ref]['sexe']), ref


@SANS_KAMAL
def test_archives_seulement_sur_demande(base_stats, plan_stats):
    from pipeline.analytique import agregats
    from .commun import CALCULE_LE
    assert agregats.construire(base_stats, avec_archives=True, calcule_le=CALCULE_LE)['dossiers'] == len(plan_stats)
    assert base_stats.execute('SELECT count(*) FROM c7_variable_dossier WHERE actif = 0').fetchone()[0] > 0
    agregats.construire(base_stats, calcule_le=CALCULE_LE)
