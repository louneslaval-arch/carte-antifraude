"""Tests du générateur de dossiers v2 fictifs (étape C.2) : forme exacte des types de Kamal, pièges T01 à T15,
scénarios S01 à S24, vérité attendue, graine fixe, garde verte sur tout ce qui est généré."""

import collections
import csv
import json
import math
import os
import sys

import pytest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2'), os.path.join(RACINE, 'outils', 'garde'),
                os.path.join(RACINE, 'outils', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import motifs  # noqa: E402
from pipeline import modeles_v2  # noqa: E402

GRAINE = 20261113
N = 400
PIEGES = ['T%02d' % i for i in range(1, 16)]
SCENARIOS = ['S%02d' % i for i in range(1, 25)]


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=N, n_societes=300, graine=GRAINE)


@pytest.fixture(scope='module')
def inventaire():
    inv = collections.defaultdict(dict)
    with open(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            inv[(r['type'], r['source'])][r['key']] = (int(r['n']), int(r['non_null']))
    return inv


def refs(jeu, code):
    """Références des dossiers qui portent le scénario ou le piège `code`."""
    return [v['ref'] for v in jeu.verite if code in v['scenarios'] or code in v['pieges']]


def dossier(jeu, ref):
    return next(d for d in jeu.dossiers if d['ref'] == ref)


def pieces(d, type_):
    return [p for p in d['pieces'] if p['type'] == type_]


def champ(d, type_, cle):
    return next((p['fields'][cle] for p in pieces(d, type_) if p['fields'].get(cle) is not None), None)


# ---- forme ---------------------------------------------------------------------------------------------------------

def test_nombre_de_dossiers_et_references_fictives_uniques(jeu):
    assert len(jeu.dossiers) == N
    references = [d['ref'] for d in jeu.dossiers]
    assert len(set(references)) == N and all(r.startswith('ZZ') for r in references)


def test_chaque_dossier_est_valide_au_regard_des_types_de_kamal(jeu):
    for d in jeu.dossiers:
        modeles_v2.DossierDetail.model_validate(d)


def test_chaque_version_de_la_chronologie_est_valide(jeu):
    assert len(jeu.chronologie) >= N
    instants = [e['instant'] for e in jeu.chronologie]
    assert instants == sorted(instants)
    for e in jeu.chronologie:
        modeles_v2.DossierDetail.model_validate(e['dossier'])


def test_liste_au_format_de_la_v2(jeu):
    liste = modeles_v2.DossiersResponse.model_validate(jeu.liste)
    assert liste.total == len(jeu.liste['items']) == sum(1 for d in jeu.dossiers if jeu.meta[d['ref']]['actif'])
    assert sum(jeu.liste['counts']['status'].values()) == liste.total


def test_deux_generations_de_meme_graine_sont_identiques(jeu):
    autre = gd.generer(n_dossiers=N, n_societes=300, graine=GRAINE)
    assert json.dumps(autre.dossiers, ensure_ascii=False, sort_keys=True) == \
        json.dumps(jeu.dossiers, ensure_ascii=False, sort_keys=True)
    assert autre.verite == jeu.verite and autre.monde.bl == jeu.monde.bl


def test_une_autre_graine_donne_d_autres_dossiers(jeu):
    autre = gd.generer(n_dossiers=N, n_societes=300, graine=GRAINE + 1)
    assert [d['clientName'] for d in autre.dossiers] != [d['clientName'] for d in jeu.dossiers]


def test_garde_verte_sur_tout_ce_qui_est_genere(jeu):
    # la liste noire vient de jeu_essai/generer.py, qui y met exprès des saisies abîmées (« RC… », CIN masqué)
    for nom, objet in (('dossiers', jeu.dossiers), ('verite', jeu.verite), ('liste', jeu.liste),
                       ('chronologie', jeu.chronologie)):
        texte = json.dumps(objet, ensure_ascii=False, indent=0, default=str)
        constats = motifs.analyser(texte, f'jeu_essai/sortie/v2/{nom}.json', racine=RACINE)
        assert constats == [], f'{nom} : {sorted({m for _, m in constats})}'


def test_trop_peu_de_dossiers_pour_les_scenarios_refuse():
    with pytest.raises(ValueError):
        gd.generer(n_dossiers=50, n_societes=300, graine=GRAINE)


def test_structure_de_kamal_absente_arrete_la_generation(tmp_path):
    with pytest.raises(gd.PrealableManquant):
        gd.generer(n_dossiers=N, n_societes=300, graine=GRAINE, structure=str(tmp_path))


# ---- pièces et clés ------------------------------------------------------------------------------------------------

def test_les_quatorze_types_de_pieces_de_la_v2(jeu):
    import lire_types_ts
    with open(os.path.join(STRUCTURE, 'types', 'engine-core_types.ts'), encoding='utf-8') as f:
        attendus = set(lire_types_ts.lire(f.read()).enumerations['PieceType'])
    vus = {p['type'] for d in jeu.dossiers for p in d['pieces']}
    assert vus == attendus and len(attendus) == 14


def test_cles_de_fields_tirees_de_l_inventaire_de_kamal(jeu, inventaire):
    for d in jeu.dossiers:
        for p in d['pieces']:
            permis = set(gd.CLES_LISTES_README.get(p['type'], ()))
            permis |= set(inventaire.get((p['type'], 'AMONT'), ()))
            if p['source'] == 'REANALYSE':
                permis |= set(inventaire.get((p['type'], 'REANALYSE'), ()))
            inconnues = set(p['fields']) - permis
            assert not inconnues, f"{d['ref']} {p['type']} {p['source']} : {sorted(inconnues)}"


def test_repartition_des_cles_suit_l_inventaire(jeu, inventaire):
    cin = [p for d in jeu.dossiers for p in d['pieces'] if p['type'] == 'CIN' and p['source'] == 'AMONT']
    assert len(cin) > 150
    inv = inventaire[('CIN', 'AMONT')]
    n_max = max(n for n, _ in inv.values())
    for cle, (n, _) in inv.items():
        frequence = sum(1 for p in cin if cle in p['fields']) / len(cin)
        assert abs(frequence - n / n_max) < 0.2, f'{cle} : {frequence:.2f} pour {n / n_max:.2f} dans l\'inventaire'


def test_enumerations_de_kamal(jeu):
    with open(os.path.join(STRUCTURE, 'reference', 'business-data.schema.json'), encoding='utf-8') as f:
        proprietes = next(iter(json.load(f)['definitions'].values()))['properties']
    for d in jeu.dossiers:
        assert d['csp'] in proprietes['csp']['enum'] + [None]
        assert d['productType'] in proprietes['product_type']['enum'] + [None]
        assert d['paymentMode'] in proprietes['payment_mode']['enum'] + [None]
        for p in d['pieces']:
            assert p['source'] in ('AMONT', 'REANALYSE') and p['extractionStatus'] in ('OK', 'PARTIAL', 'FAILED')


# ---- pièges --------------------------------------------------------------------------------------------------------

def test_chaque_piege_est_present_au_moins_une_fois(jeu):
    for t in PIEGES:
        assert refs(jeu, t), f'piège {t} absent'


def test_T01_releve_relu_sans_annee_a_cheval_sur_decembre_et_janvier(jeu):
    trouve = False
    for ref in refs(jeu, 'T01'):
        releve = pieces(dossier(jeu, ref), 'RELEVE_BANCAIRE')[0]
        assert releve['source'] == 'REANALYSE'
        mois = releve['fields']['mois']
        for m in mois:
            for op in m['operations']:
                assert set(op) == {'date_operation', 'date_valeur', 'libelle', 'debit', 'credit'}
                assert len(op['date_operation']) == 5  # jj/mm, sans année
        if {12, 1} <= {m['mois'] for m in mois}:
            trouve = True
    assert trouve


def test_T02_releve_non_relu_en_agregats_mensuels(jeu):
    for ref in refs(jeu, 'T02'):
        releve = pieces(dossier(jeu, ref), 'RELEVE_BANCAIRE')[0]
        assert releve['source'] == 'AMONT' and not any(m.get('operations') for m in releve['fields'].get('mois') or [])
        assert isinstance(releve['fields']['total_mouvements_credit'], (dict, str))


def test_T03_cin_multiple(jeu):
    for ref in refs(jeu, 'T03'):
        assert len(champ(dossier(jeu, ref), 'CIN', 'cartes')) >= 2


def test_T04_cles_en_double_plate_et_imbriquee(jeu):
    doubles = set()
    for ref in refs(jeu, 'T04'):
        for p in dossier(jeu, ref)['pieces']:
            for plate in p['fields']:
                objet, _, cle = plate.partition('.')
                if cle and isinstance(p['fields'].get(objet), dict) and cle in p['fields'][objet]:
                    doubles.add(plate)
    assert {'vehicule.marque', 'prix.prix_total_ttc', 'employeur.raison_sociale', 'remuneration.salaire_net'} <= doubles


def test_T05_cles_inventees_et_champs_de_cin_hors_cin(jeu):
    cles = {(p['type'], c) for ref in refs(jeu, 'T05') for p in dossier(jeu, ref)['pieces'] for c in p['fields']}
    assert ('BULLETIN_DE_PAIE', 'remeration.salaire_net') in cles
    assert ('ATTESTATION_TRAVAIL_SALAIRE', 'revelation.salaire_brut') in cles
    for type_ in ('ATTESTATION_RIB', 'DOMICILIATION', 'CARTE_PROFESSIONNELLE'):
        assert (type_, 'filiation_complete') in cles and (type_, 'date_expiration') in cles


def test_T06_montants_en_texte_et_en_nombre(jeu):
    valeurs = [v for ref in refs(jeu, 'T06') for p in dossier(jeu, ref)['pieces'] for c, v in p['fields'].items()
               if 'salaire' in c or 'montant' in c or 'total' in c]
    textes = [v for v in valeurs if isinstance(v, str)]
    assert any(' DH' in v for v in textes) and any(',' in v and ' ' in v for v in textes)
    assert any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valeurs)
    assert any(isinstance(v, dict) for v in valeurs)


def test_T07_dates_avec_et_sans_annee(jeu):
    dates = [v for ref in refs(jeu, 'T07') for p in dossier(jeu, ref)['pieces'] for c, v in p['fields'].items()
             if c.startswith('date') and isinstance(v, str)]
    assert any(len(v) == 10 for v in dates) and any(len(v) == 5 for v in dates)


def test_T08_trois_vocabulaires(jeu):
    amont, moteur, les_deux = False, False, False
    for ref in refs(jeu, 'T08'):
        d = dossier(jeu, ref)
        for p in pieces(d, 'REGISTRE_COMMERCE'):
            a, m = 'nom_societe' in p['fields'], 'denomination_sociale' in p['fields']
            amont, moteur, les_deux = amont or (a and not m), moteur or (m and not a), les_deux or (a and m)
        if pieces(d, 'CARTE_GRISE'):
            assert 'Numéro de chassis' in pieces(d, 'CARTE_GRISE')[0]['fields']
    assert amont and moteur and les_deux


def test_T09_raison_sociale_titulaire_sur_un_releve(jeu):
    for ref in refs(jeu, 'T09'):
        d = dossier(jeu, ref)
        assert champ(d, 'RELEVE_BANCAIRE', 'raison_sociale') == d['clientName']


def test_T10_relecture_avec_avant_et_apres(jeu):
    for ref in refs(jeu, 'T10'):
        d = dossier(jeu, ref)
        assert any(p['source'] == 'REANALYSE' for p in d['pieces'])
        faites = [r for r in d['reanalyses'] if r['status'] == 'DONE']
        assert faites and all(set(r['result']) == {'avant', 'apres'} for r in faites)
        ids = {p['upstreamPieceId'] for p in d['pieces']}
        assert all(r['pieceId'] in ids for r in faites)


def test_T11_contexte_amont_partiel(jeu):
    vus = set()
    for ref in refs(jeu, 'T11'):
        bd = dossier(jeu, ref)['businessData']
        if dossier(jeu, ref)['personType'] == 'PM' and not bd['civil']['cin']:
            vus.add('cin vide pour une PM')
        if bd['declared']['employer'] is None and bd['declared']['monthly_income'] is None:
            vus.add('declared vide')
        if bd['declared']['employer'] == 'VAB':
            vus.add('VAB')
        if dossier(jeu, ref)['csp'] == 'RETRAITE_INDETERMINE':
            vus.add('retraité indistinct')
    assert vus == {'cin vide pour une PM', 'declared vide', 'VAB', 'retraité indistinct'}


def test_T12_valeurs_gabarits(jeu):
    for ref in refs(jeu, 'T12'):
        d = dossier(jeu, ref)
        assert champ(d, 'CIN', 'nom') + ' ' + champ(d, 'CIN', 'prenom') in ('DOE JOHN', 'JOHN DOE')


def test_T13_trois_statuts_d_extraction(jeu):
    statuts = {p['extractionStatus'] for ref in refs(jeu, 'T13') for p in dossier(jeu, ref)['pieces']}
    assert statuts == {'OK', 'PARTIAL', 'FAILED'}


def test_T14_analyse_non_terminee_et_dossier_archive(jeu):
    r = refs(jeu, 'T14')
    assert any(dossier(jeu, x)['analysisStatus'] in ('EN_COURS', 'EN_ATTENTE_DONNEES') and
               dossier(jeu, x)['latestAnalysis'] is None for x in r)
    assert any(not jeu.meta[x]['actif'] for x in r)


def test_T15_agence_et_canal_vides(jeu):
    for ref in refs(jeu, 'T15'):
        assert dossier(jeu, ref)['agence'] is None and dossier(jeu, ref)['canal'] is None


# ---- scénarios -----------------------------------------------------------------------------------------------------

def test_chaque_scenario_a_sa_verite(jeu):
    for s in SCENARIOS:
        entrees = [v for v in jeu.verite if s in v['scenarios']]
        assert entrees, f'scénario {s} absent'
        for v in entrees:
            assert {'ref', 'scenarios', 'pieges', 'identites', 'mentions', 'liens', 'niveau', 'force', 'chemin',
                    'incoherences', 'notes', 'controle'} <= set(v)
            assert v['controle'] is True
    assert {v['ref'] for v in jeu.verite} == {d['ref'] for d in jeu.dossiers}


def verite(jeu, scenario, **filtre):
    return [v for v in jeu.verite if scenario in v['scenarios'] and all(v.get(k) == x for k, x in filtre.items())]


def cins_inscrits(jeu):
    return {l['cin'].replace(' ', '') for l in jeu.monde.bl if l['cin']}


def test_S01_demandeur_inscrit_par_son_cin(jeu):
    v = verite(jeu, 'S01')[0]
    assert v['niveau'] == 'critique' and v['chemin'] == [] and v['liens'] == []
    assert champ(dossier(jeu, v['ref']), 'CIN', 'cin') in cins_inscrits(jeu)


def test_S02_societe_du_dossier_inscrite_par_rc_et_tribunal(jeu):
    v = verite(jeu, 'S02')[0]
    d = dossier(jeu, v['ref'])
    rc = champ(d, 'REGISTRE_COMMERCE', 'numero_analytique')
    assert v['niveau'] == 'critique' and d['personType'] == 'PM'
    assert any(l['regist_com'] == rc and l['regist_tribune'] for l in jeu.monde.bl)


def test_S03_employeur_inscrit_par_son_ice(jeu):
    v = verite(jeu, 'S03')[0]
    ice = champ(dossier(jeu, v['ref']), 'ATTESTATION_TRAVAIL_SALAIRE', 'employeur')['ice']
    assert v['niveau'] == 'critique' and ice.startswith('999') and any(l['ice'] == ice for l in jeu.monde.bl)


def test_S04_employeur_dont_le_gerant_est_inscrit(jeu):
    v = verite(jeu, 'S04')[0]
    assert v['niveau'] == 'majeure' and v['force'] == pytest.approx(0.7) and len(v['chemin']) == 1
    assert v['liens'][0]['nature'] == 'gérant'


def test_S05_meme_rib_qu_un_inscrit(jeu):
    v = verite(jeu, 'S05', niveau='majeure')[0]
    assert v['force'] == pytest.approx(0.9) and v['liens'][0]['nature'] == 'même RIB'
    rib = champ(dossier(jeu, v['ref']), 'RELEVE_BANCAIRE', 'rib')
    porteurs = [d for d in jeu.dossiers if champ(d, 'RELEVE_BANCAIRE', 'rib') == rib]
    assert len(porteurs) == 2 and any(champ(d, 'CIN', 'cin') in cins_inscrits(jeu) for d in porteurs)


def test_S06_rib_porte_par_cinq_personnes_dont_un_inscrit(jeu):
    v = verite(jeu, 'S06', niveau='majeure')[0]
    assert v['force'] == pytest.approx(0.9 * math.sqrt(2 / 5), abs=1e-4)
    rib = champ(dossier(jeu, v['ref']), 'RELEVE_BANCAIRE', 'rib')
    assert len({champ(d, 'CIN', 'cin') for d in jeu.dossiers if champ(d, 'RELEVE_BANCAIRE', 'rib') == rib}) == 5


def societes_de(jeu, cin):
    p = next(p for p in jeu.monde.personnes if p['cin'] == cin)
    return [s for s in jeu.monde.societes if any(pid == p['id'] for pid, _, _ in s['personnes'])]


def test_S07_gerant_de_huit_societes_donne_une_majeure(jeu):
    v = verite(jeu, 'S07')[0]
    assert v['niveau'] == 'majeure' and v['force'] == pytest.approx(0.245) and len(v['chemin']) == 2
    assert len(societes_de(jeu, v['notes']['cin_du_pont'])) == 8


def test_S08_liquidateur_de_quarante_societes_affiche_sans_alerte(jeu):
    v = verite(jeu, 'S08')[0]
    assert v['niveau'] == 'affiché' and v['force'] == pytest.approx(0.5 * math.sqrt(2 / 40) * 0.5, abs=1e-4)
    assert len(societes_de(jeu, v['notes']['cin_du_pont'])) == 40


def test_S09_et_S10_longueur_du_chemin(jeu):
    v9, v10 = verite(jeu, 'S09')[0], verite(jeu, 'S10')[0]
    assert len(v9['chemin']) == 3 and v9['niveau'] == 'mineure'
    assert len(v10['chemin']) == 4 and v10['niveau'] == 'hors alerte'


def test_S11_et_S12_homonymies(jeu):
    v11, v12 = verite(jeu, 'S11')[0], verite(jeu, 'S12')[0]
    assert v11['niveau'] == 'mineure' and 'homonymie à lever' in v11['notes']['mention']
    assert v11['notes']['si_meme_personne'] == 'majeure' and v11['notes']['si_homonyme_ecarte'] is None
    d12 = dossier(jeu, v12['ref'])
    assert v12['niveau'] == 'mineure' and 'ice' not in (champ(d12, 'ATTESTATION_TRAVAIL_SALAIRE', 'employeur') or {})


def test_S13_et_S14_foyer(jeu):
    v13, v14 = verite(jeu, 'S13', niveau='mineure')[0], verite(jeu, 'S14', niveau='majeure')[0]
    assert v13['force'] == pytest.approx(0.1) and v13['notes']['mention'] == 'même foyer qu\'un inscrit'
    assert v14['force'] == pytest.approx(0.9)


def test_S15_inscription_qui_designe_une_victime(jeu):
    assert verite(jeu, 'S15', niveau='critique')
    assert any(v['notes'].get('provisoire') for v in verite(jeu, 'S15') if v['niveau'] != 'critique')


def test_S16_les_deux_ordres_d_arrivee(jeu):
    ordres = {v['notes']['ordre'] for v in verite(jeu, 'S16') if 'ordre' in v['notes']}
    assert ordres == {'inscrit d\'abord', 'inscrit ensuite'}


def test_S17_relecture_qui_change_le_cin_retire_les_aretes(jeu):
    v = verite(jeu, 'S17')[0]
    versions = [e['dossier'] for e in jeu.chronologie if e['ref'] == v['ref']]
    assert len(versions) == 2
    avant, apres = (champ(x, 'CIN', 'cin') for x in versions)
    assert avant in cins_inscrits(jeu) and apres not in cins_inscrits(jeu) and v['niveau'] is None
    assert v['notes']['niveau_avant_relecture'] == 'critique'


def test_S18_meme_chassis_dans_deux_dossiers(jeu):
    vs = verite(jeu, 'S18')
    chassis = {champ(dossier(jeu, v['ref']), 'CARTE_GRISE', 'Numéro de chassis') for v in vs}
    assert len(vs) == 2 and len(chassis) == 1
    assert all(v['incoherences'] == ['double financement'] and v['liens'] == [] for v in vs)


def test_S19_meme_rib_dans_trois_dossiers_en_moins_de_trente_jours(jeu):
    vs = verite(jeu, 'S19')
    dates = sorted(dossier(jeu, v['ref'])['createdAt'][:10] for v in vs)
    assert len(vs) == 3 and all('dossiers en rafale' in v['notes']['signaux'] for v in vs)
    import datetime
    assert (datetime.date.fromisoformat(dates[-1]) - datetime.date.fromisoformat(dates[0])).days < 30


def test_S20_employeur_declare_dans_plus_de_deux_cents_dossiers(jeu):
    vs = verite(jeu, 'S20')
    assert len(vs) > 200 and all(v['notes']['propagation'] == 'nuit' for v in vs)
    ices = {champ(dossier(jeu, v['ref']), 'ATTESTATION_TRAVAIL_SALAIRE', 'employeur')['ice'] for v in vs}
    assert len(ices) == 1


def test_S21_a_S24(jeu):
    v21 = verite(jeu, 'S21')[0]
    assert dossier(jeu, v21['ref'])['latestAnalysis'] is None and v21['niveau'] is None
    assert not jeu.meta[verite(jeu, 'S22')[0]['ref']]['actif']
    v23 = next(v for v in verite(jeu, 'S23') if 'apres_levee' in v['notes'])   # l'autre est le dossier de l'inscrit
    assert len([e for e in jeu.chronologie if e['ref'] == v23['ref']]) == 2 and v23['notes']['apres_levee'] == 'rouvre'
    v24 = verite(jeu, 'S24', niveau=None)[0]
    assert v24['notes']['mention'] == 'même point de vente qu\'un inscrit, hors score'


# ---- ligne de commande ---------------------------------------------------------------------------------------------

def test_ligne_de_commande_ecrit_les_fichiers_et_n_affiche_que_des_comptages(tmp_path):
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'jeu_essai', 'v2', 'generer_dossiers.py'),
                        '--sortie', str(tmp_path), '--dossiers', str(N), '--societes', '300'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for nom in ('liste_noire.csv', 'rc_annonces.csv', 'rc_personnes.csv', 'dossiers.json', 'liste.json',
                'chronologie.json', 'verite_v2.json'):
        assert (tmp_path / nom).exists(), nom
    assert 'ZZ' not in r.stdout


def test_identifiants_numeriques_et_plaques_marques_fictifs(jeu):
    for d in jeu.dossiers:
        for p in d['pieces']:
            f = p['fields']
            for cle in ('numero_pension', 'numero_cnss', 'numero_affiliation'):
                if f.get(cle):
                    assert str(f[cle]).startswith('999'), cle
            if f.get('Immatriculation'):
                assert 'FICTIF' in f['Immatriculation']


def test_erreur_de_generation_sans_valeur_dans_la_console(monkeypatch, capsys, tmp_path):
    def casse(*a, **k):
        raise ValueError('ligne ZZ900001 illisible')
    monkeypatch.setattr(gd, 'generer', casse)
    assert gd.main(['--sortie', str(tmp_path)]) == 2
    sortie = capsys.readouterr()
    assert 'ZZ900001' not in sortie.out + sortie.err
