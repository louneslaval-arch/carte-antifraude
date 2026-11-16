"""Tests de la couche 1 (étape E) : chaque valeur d'une pièce devient une ligne normalisée, avec son origine.
Un test par piège (T01 à T13), flux = lot, invariants."""

import json
import os
import random
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import verifier  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402
from pipeline.couches import c1_faits as c1  # noqa: E402
from pipeline.normalisation import cles  # noqa: E402

T0 = '2026-11-13T10:00:00.000Z'
TABLES = ('c1_piece', 'c1_fait', 'c1_releve_mois', 'c1_releve_operation', 'c1_mention_personne', 'c1_mention_societe',
          'c1_identifiant_brut')


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture(scope='module')
def base(jeu, tmp_path_factory):
    """Base où tout le jeu est reçu (c0), puis la couche 1 construite en lot."""
    chemin = str(tmp_path_factory.mktemp('c1') / 'base.sqlite')
    cx = sqlite3.connect(chemin)
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for e in jeu.chronologie:
        c0.recevoir(cx, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
    c1.construire_tout(cx)
    yield cx, chemin
    cx.close()


@pytest.fixture
def cx(base):
    return base[0]


def ref_de(jeu, code, n=0, **notes):
    return [v['ref'] for v in jeu.verite if (code in v['scenarios'] or code in v['pieges'])
            and all(v['notes'].get(k) == x for k, x in notes.items())][n]


def base_de(tmp_path, *dossiers, construire=True):
    """Base neuve où ces dossiers sont reçus (c0), puis c1 construite en lot."""
    cx = sqlite3.connect(str(tmp_path / f'base_{len(os.listdir(tmp_path))}.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for d in dossiers:
        c0.recevoir(cx, passage, d, maintenant=T0)
    if construire:
        c1.construire_tout(cx)
    return cx


def avec_piece(jeu, type_piece, champs, relectures=None):
    """Copie du premier dossier fictif dont la première pièce est remplacée."""
    d = json.loads(json.dumps(jeu.dossiers[0]))
    d['pieces'][0]['type'], d['pieces'][0]['fields'] = type_piece, champs
    if relectures is not None:
        d['reanalyses'] = relectures
    return d, d['pieces'][0]['upstreamPieceId']


def au_dessus(cx):
    """Construit les couches au-dessus de c1 : les invariants se vérifient sur une base entièrement construite."""
    from pipeline.couches import COUCHES
    for couche in COUCHES[2:]:
        couche.construire_tout(cx)
    cx.commit()


def lignes(cx, sql, *p):
    return cx.execute(sql, p).fetchall()


def faits(cx, ref, type_piece, cle=None):
    sql = 'SELECT cle_brute, cle, valeur, nombre, date, origine, statut FROM c1_fait WHERE ref = ? AND type = ?'
    return lignes(cx, sql + (' AND cle_brute = ?' if cle else ''), *([ref, type_piece] + ([cle] if cle else [])))


def contenu(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM {t}').fetchall(), key=repr) for t in TABLES}


# ---- généralités ---------------------------------------------------------------------------------------------------

def test_chaque_piece_du_miroir_a_sa_ligne_et_sa_version(cx, jeu):
    assert cx.execute('SELECT count(*) FROM c1_piece').fetchone()[0] == sum(len(d['pieces']) for d in jeu.dossiers)
    d = jeu.dossiers[0]
    assert {v for (v,) in lignes(cx, 'SELECT version FROM c1_piece WHERE ref = ?', d['ref'])} == {d['updatedAt']}


def test_reference_des_cles_semee_et_versionnee(cx):
    assert set(lignes(cx, 'SELECT type_piece, cle_brute, cle_moteur FROM ref_cle_canonique')) == \
        set(cles.lignes_de_reference())
    assert {v for (v,) in lignes(cx, 'SELECT version FROM ref_cle_canonique')} == {cles.VERSION}


def test_toute_cle_est_connue_ou_figure_au_rapport_des_cles_inconnues(cx):
    for type_piece, cle_brute, connue in lignes(cx, 'SELECT DISTINCT type, cle_brute, cle_connue FROM c1_fait'):
        assert bool(connue) == c1.cle_connue(type_piece, cle_brute), (type_piece, cle_brute)
    inconnues = cx.execute('SELECT coalesce(sum(nombre), 0) FROM c1_cle_inconnue').fetchone()[0]
    assert inconnues == cx.execute('SELECT count(*) FROM c1_fait WHERE cle_connue = 0').fetchone()[0]


def inventaire():
    import csv
    with open(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv'), encoding='utf-8') as f:
        return {(r['type'], r['key']) for r in csv.DictReader(f)}


def test_inventaire_de_kamal_chaque_cle_a_une_cle_canonique_dans_la_reference(cx):
    reference = {(t, c): m for t, c, m in lignes(cx, 'SELECT type_piece, cle_brute, cle_moteur FROM ref_cle_canonique')}
    for type_piece, cle in inventaire():
        assert c1.cle_connue(type_piece, cle), (type_piece, cle)
        assert reference[(type_piece, cle)] == cles.canon(type_piece, cle)


def test_cle_hors_de_l_inventaire_inconnue_et_au_rapport(cx, jeu, tmp_path):
    assert not c1.cle_connue('CIN', 'cle_jamais_vue') and not c1.cle_connue('CIN', 'cle_jamais_vue.sous_cle[01/2026]')
    assert c1.cle_connue('ATTESTATION_CNSS', 'assure.nom_complet')       # sous-clé d'un objet de l'inventaire
    connu = inventaire()
    for type_piece, cle_brute, _ in lignes(cx, 'SELECT * FROM c1_cle_inconnue'):
        assert (type_piece, cle_brute.split('[')[0].split('.')[0]) not in connu
    total, inconnus = lignes(cx, 'SELECT count(*), sum(1 - cle_connue) FROM c1_fait')[0]
    assert inconnus < total / 20                                         # le rapport reste lisible
    d = json.loads(json.dumps(jeu.dossiers[0]))
    d['pieces'][0]['fields']['cle_jamais_vue'] = 'x'
    autre = base_de(tmp_path, d)
    assert lignes(autre, "SELECT cle_brute, nombre FROM c1_cle_inconnue WHERE cle_brute = 'cle_jamais_vue'") == \
        [('cle_jamais_vue', 1)]


# ---- pièges --------------------------------------------------------------------------------------------------------

def test_T01_operations_datees_avec_l_annee_du_mois_du_releve(cx, jeu):
    ref = ref_de(jeu, 'T01')                                # relevé à cheval sur décembre et janvier
    ops = lignes(cx, 'SELECT mois, annee, date_operation, date_valeur, nature, debit, credit, libelle_norm '
                     'FROM c1_releve_operation WHERE ref = ? ORDER BY rang_mois, rang', ref)
    assert len(ops) == 6 and {o[4] for o in ops} == {'lue'}
    assert [o[2] for o in ops if o[0] == 12] == ['2025-12-05', '2025-12-28']
    assert [o[2] for o in ops if o[0] == 1] == ['2026-01-05', '2026-01-28']
    assert ops[0][6] == 9000.0 and ops[1][5] == 1500.0 and ops[0][7].startswith('VIREMENT RECU DE ')
    assert lignes(cx, 'SELECT nb_operations_lues FROM c1_releve_mois WHERE ref = ?', ref) == [(2,), (2,), (2,)]


def test_T02_releve_non_relu_agregats_mensuels_sans_operation(cx, jeu):
    ref = ref_de(jeu, 'T02')
    assert lignes(cx, 'SELECT count(*) FROM c1_releve_operation WHERE ref = ?', ref) == [(0,)]
    mois = lignes(cx, 'SELECT mois, annee, salaire_detecte, total_credit, nb_operations_lues FROM c1_releve_mois '
                      'WHERE ref = ? ORDER BY rang', ref)
    assert [m[:2] for m in mois] == [(7, 2026), (8, 2026), (9, 2026)]
    assert all(isinstance(m[2], float) and m[3] == 9000.0 and m[4] == 0 for m in mois)
    assert len(faits(cx, ref, 'RELEVE_BANCAIRE', 'montant_salaire[07/2026]')) == 1


def test_operation_sans_date_est_reconstituee_jamais_lue(cx, jeu, tmp_path):
    d = json.loads(json.dumps(next(x for x in jeu.dossiers if x['ref'] == ref_de(jeu, 'T01'))))
    releve = next(p for p in d['pieces'] if p['type'] == 'RELEVE_BANCAIRE')
    releve['fields']['mois'][0]['operations'].append(dict(date_operation=None, date_valeur=None, libelle='SALAIRE',
                                                           debit=None, credit=9000.0))
    autre = sqlite3.connect(str(tmp_path / 'b.sqlite'))
    migrer.appliquer(autre)
    c0.recevoir(autre, c0.ouvrir_passage(autre, 'essai', 'lot', T0), d, maintenant=T0)
    c1.traiter(autre, d['ref'])
    assert dict(autre.execute('SELECT nature, count(*) FROM c1_releve_operation GROUP BY nature')) == \
        {'lue': 6, 'reconstituee_amont': 1}
    assert autre.execute('SELECT nb_operations_lues FROM c1_releve_mois ORDER BY rang').fetchone() == (2,)


def test_T03_cin_multiple_une_mention_par_carte(cx, jeu):
    ref = ref_de(jeu, 'T03')
    mentions = lignes(cx, "SELECT rang, cin FROM c1_mention_personne WHERE ref = ? AND role = 'titulaire_cin' "
                          'ORDER BY rang', ref)
    assert len(mentions) == 2 and all(c and c.startswith('ZZ') for _, c in mentions) and mentions[0][1] != mentions[1][1]


def test_T04_cle_plate_et_objet_imbrique_ne_font_qu_un_fait(cx, jeu):
    ref = ref_de(jeu, 'T04')
    for type_piece, cle in (('FACTURE_PROFORMA_VEHICULE', 'vehicule.marque'), ('FACTURE_PROFORMA_VEHICULE', 'prix.prix_total_ttc'),
                            ('ATTESTATION_TRAVAIL_SALAIRE', 'employeur.raison_sociale'),
                            ('BULLETIN_DE_PAIE', 'remuneration.salaire_net')):
        assert len(faits(cx, ref, type_piece, cle)) == 1, cle
    assert faits(cx, ref, 'FACTURE_PROFORMA_VEHICULE', 'vehicule.marque')[0][1] == 'marque_vehicule'


def test_T05_cles_inventees_et_champs_de_cin_hors_cin_ecartes(cx, jeu):
    ref = ref_de(jeu, 'T05')
    assert faits(cx, ref, 'BULLETIN_DE_PAIE', 'remeration.salaire_net')[0][6] == 'cle_inventee'
    assert faits(cx, ref, 'ATTESTATION_TRAVAIL_SALAIRE', 'revelation.salaire_brut')[0][6] == 'cle_inventee'
    for type_piece in ('ATTESTATION_RIB', 'DOMICILIATION', 'CARTE_PROFESSIONNELLE'):
        assert faits(cx, ref, type_piece, 'filiation_complete')[0][6] == 'champ_cin_hors_cin'
        assert faits(cx, ref, type_piece, 'cin')[0][6] == 'champ_cin_hors_cin'
        assert lignes(cx, "SELECT count(*) FROM c1_identifiant_brut i JOIN c1_piece p ON p.ref = i.ref AND "
                          "p.upstream_piece_id = i.upstream_piece_id WHERE i.ref = ? AND p.type = ? AND i.type = 'CIN'",
                      ref, type_piece) == [(0,)]
        assert lignes(cx, 'SELECT count(*) FROM c1_mention_personne WHERE ref = ? AND type_piece = ? AND cin IS NOT NULL',
                      ref, type_piece) == [(0,)]
    assert faits(cx, ref, 'CIN', 'cin')[0][6] == 'normal'
    retenus = lignes(cx, 'SELECT type, cle_brute FROM c1_fait_retenu WHERE ref = ?', ref)
    assert retenus and not any(c.startswith(('remeration.', 'revelation.')) or c == 'filiation_complete'
                               or (c == 'cin' and t != 'CIN') for t, c in retenus)


def test_T06_montants_en_texte_et_en_nombre_deviennent_des_nombres(cx, jeu):
    ref = ref_de(jeu, 'T06')
    dh = faits(cx, ref, 'ATTESTATION_TRAVAIL_SALAIRE', 'salaire_net')[0]
    assert dh[2].endswith(' DH') and isinstance(dh[3], float) and dh[3] > 1000
    texte = faits(cx, ref, 'ATTESTATION_TRAVAIL_SALAIRE', 'salaire_net_mensuel')[0]
    assert ',' in texte[2] and isinstance(texte[3], float)
    assert isinstance(faits(cx, ref, 'BULLETIN_DE_PAIE', 'salaire_net')[0][3], float)
    assert isinstance(faits(cx, ref, 'RELEVE_BANCAIRE', 'total_mouvements_debit')[0][3], float)
    assert isinstance(faits(cx, ref, 'RELEVE_BANCAIRE', 'total_mouvements_credit[07/2026]')[0][3], float)


def test_T07_date_complete_lue_date_sans_annee_laissee_vide(cx, jeu):
    ref = ref_de(jeu, 'T07')
    assert faits(cx, ref, 'ATTESTATION_TRAVAIL_SALAIRE', 'date_embauche')[0][4] == '2019-09-01'
    sans_annee = faits(cx, ref, 'ATTESTATION_TRAVAIL_SALAIRE', 'date_attestation')[0]
    assert sans_annee[2] == '12/03' and sans_annee[4] is None


def test_T08_trois_vocabulaires_une_seule_cle_canonique(cx, jeu):
    for n in range(3):
        ref = ref_de(jeu, 'T08', n)
        retenus = dict(lignes(cx, "SELECT cle, valeur FROM c1_fait_retenu WHERE ref = ? AND type = 'REGISTRE_COMMERCE'",
                              ref))
        assert retenus['denomination_sociale'] and retenus['ville_tribunal'] and retenus['ice'].startswith('999')
        assert 'nom_societe' not in retenus and 'numero_ice' not in retenus
        societe = lignes(cx, "SELECT nom, rc, tribunal, ice FROM c1_mention_societe WHERE ref = ? AND role = 'societe' "
                             "AND type_piece = 'REGISTRE_COMMERCE'", ref)
        assert len(societe) == 1 and all(societe[0])
        assert lignes(cx, "SELECT count(*) FROM c1_societe_personne WHERE ref = ? AND role IN ('gerant', 'dirigeant')",
                      ref)[0][0] >= 1
        assert lignes(cx, "SELECT cle FROM c1_fait WHERE ref = ? AND cle_brute = 'Numéro de chassis'", ref) == \
            [('numero_chassis',)]


def test_T09_raison_sociale_titulaire_sur_un_releve_societe_ailleurs(cx, jeu):
    ref = ref_de(jeu, 'T09')
    assert faits(cx, ref, 'RELEVE_BANCAIRE', 'raison_sociale')[0][1] == 'titulaire_compte'
    autres = lignes(cx, "SELECT DISTINCT cle FROM c1_fait WHERE cle_brute = 'raison_sociale' "
                        "AND type NOT IN ('RELEVE_BANCAIRE', 'ATTESTATION_RIB')")
    assert autres == [('raison_sociale',)]


def test_T10_origine_amont_relue_ciblee_ou_fusion(cx, jeu):
    ref = ref_de(jeu, 'T10')
    d = next(x for x in jeu.dossiers if x['ref'] == ref)
    relue = next(p for p in d['pieces'] if p['source'] == 'REANALYSE')
    ciblees = set(next(r for r in d['reanalyses'] if r['pieceId'] == relue['upstreamPieceId'])['result']['apres'])
    origines = dict(lignes(cx, 'SELECT cle_brute, origine FROM c1_fait WHERE ref = ? AND upstream_piece_id = ?',
                           ref, relue['upstreamPieceId']))
    racine = lambda c: c.split('[')[0].split('.')[0]      # noqa: E731
    assert {o for c, o in origines.items() if racine(c) in ciblees} == {'relue_ciblee'}
    assert {o for c, o in origines.items() if racine(c) not in ciblees} <= {'fusion'}
    assert {o for (o,) in lignes(cx, "SELECT origine FROM c1_fait f JOIN c1_piece p USING (ref, upstream_piece_id) "
                                     "WHERE p.source = 'AMONT'")} == {'amont'}
    assert lignes(cx, 'SELECT nb_champs_relus FROM c1_piece WHERE ref = ? AND upstream_piece_id = ?', ref,
                  relue['upstreamPieceId']) == [(len(ciblees),)]


def test_T11_contexte_amont_partiel_sans_plantage(cx, jeu):
    for n in range(4):
        assert lignes(cx, 'SELECT count(*) FROM c1_piece WHERE ref = ?', ref_de(jeu, 'T11', n))[0][0] >= 2


def test_T12_valeurs_gabarits_hors_des_identites(cx, jeu):
    ref = ref_de(jeu, 'T12')
    assert faits(cx, ref, 'CIN', 'cin')[0][6] == 'gabarit'
    assert lignes(cx, "SELECT cin FROM c1_mention_personne WHERE ref = ? AND role = 'titulaire_cin'", ref) == [(None,)]
    assert lignes(cx, "SELECT count(*) FROM c1_identifiant_brut WHERE ref = ? AND type = 'CIN'", ref) == [(0,)]
    assert not lignes(cx, "SELECT 1 FROM c1_fait_retenu WHERE ref = ? AND type = 'CIN' AND cle = 'cin'", ref)
    n, gabarits = lignes(cx, "SELECT count(*), sum(CASE statut WHEN 'gabarit' THEN 1 ELSE 0 END) FROM "
                             "c1_mention_personne WHERE nom_norm IN ('DOE JOHN', 'JOHN DOE')")[0]
    assert n > 0 and n == gabarits                              # le nom gabarit, dans un ordre ou dans l'autre
    assert lignes(cx, "SELECT count(*) FROM c1_mention_personne WHERE statut = 'gabarit'") == [(n,)]


def test_T13_piece_en_echec_d_extraction_gardee_avec_son_statut(cx, jeu):
    ref = ref_de(jeu, 'T13')
    assert {s for (s,) in lignes(cx, 'SELECT extraction_status FROM c1_piece WHERE ref = ?', ref)} == \
        {'OK', 'PARTIAL', 'FAILED'}


# ---- mentions et identifiants --------------------------------------------------------------------------------------

def test_mentions_et_identifiants_d_un_dossier_salarie(cx, jeu):
    v = next(v for v in jeu.verite if 'S04' in v['scenarios'])
    ref = v['ref']
    demandeur, employeur = v['identites']
    roles = dict(lignes(cx, 'SELECT role, cin FROM c1_mention_personne WHERE ref = ? AND rang = 0', ref))
    assert roles['titulaire_cin'] == roles['employe'] == demandeur['cin']
    assert lignes(cx, "SELECT DISTINCT ice FROM c1_mention_societe WHERE ref = ? AND role = 'employeur'", ref) == \
        [(employeur['ice'],)]
    identifiants = {t: {x for (x,) in lignes(cx, 'SELECT valeur FROM c1_identifiant_brut WHERE ref = ? AND type = ?',
                                             ref, t)} for t in ('CIN', 'RIB', 'ICE', 'CNSS', 'AFFILIATION_CNSS')}
    assert identifiants['CIN'] == {demandeur['cin']} and identifiants['ICE'] == {employeur['ice']}
    assert len(identifiants['RIB']) == 1 and all(x.startswith('999') for t in ('RIB', 'CNSS', 'AFFILIATION_CNSS')
                                                 for x in identifiants[t])


def test_titulaire_du_compte_mentionne_sur_le_releve_et_l_attestation_de_rib(cx, jeu):
    ref = next(v['ref'] for v in jeu.verite if 'S04' in v['scenarios'])
    attendu = {(upi, nom) for upi, nom in lignes(
        cx, "SELECT upstream_piece_id, valeur FROM c1_fait WHERE ref = ? AND type IN ('RELEVE_BANCAIRE', "
            "'ATTESTATION_RIB') AND cle_brute = 'titulaire_compte' AND valeur IS NOT NULL", ref)}
    mentions = set(lignes(cx, "SELECT upstream_piece_id, nom_complet FROM c1_mention_personne WHERE ref = ? "
                              "AND role = 'titulaire_compte'", ref))
    assert attendu and mentions == attendu
    assert lignes(cx, "SELECT count(*) FROM c1_mention_personne WHERE role = 'titulaire_compte' AND "
                      "type_piece NOT IN ('RELEVE_BANCAIRE', 'ATTESTATION_RIB')") == [(0,)]


def test_titulaire_de_la_quittance_mentionne_sur_la_domiciliation(cx):
    n, m = lignes(cx, "SELECT count(*), count(nom_complet) FROM c1_mention_personne WHERE role = "
                      "'titulaire_quittance' AND type_piece = 'DOMICILIATION'")[0]
    assert n > 0 and n == m


def test_chassis_sans_ponctuation(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'CARTE_GRISE', {'Numéro de chassis': 'zz-fictif essai.0003'})
    cx = base_de(tmp_path, d)
    assert lignes(cx, "SELECT valeur FROM c1_identifiant_brut WHERE upstream_piece_id = ? AND type = 'CHASSIS'", upi) == \
        [('ZZFICTIFESSAI0003',)]


def test_chassis_et_rc_normalises(cx, jeu):
    refs = [v['ref'] for v in jeu.verite if 'S18' in v['scenarios']]
    chassis = {lignes(cx, "SELECT valeur FROM c1_identifiant_brut WHERE ref = ? AND type = 'CHASSIS'", r)[0][0]
               for r in refs}
    assert chassis == {'ZZFICTIFDOUBLE001'}
    ref = next(v['ref'] for v in jeu.verite if 'S02' in v['scenarios'])
    rc = lignes(cx, "SELECT valeur FROM c1_identifiant_brut WHERE ref = ? AND type = 'RC'", ref)
    assert len(rc) == 1 and rc[0][0].count('|') == 1


# ---- flux = lot ----------------------------------------------------------------------------------------------------

def test_traiter_chaque_dossier_dans_un_ordre_au_hasard_egale_le_lot(base, jeu):
    cx, _ = base
    en_lot = contenu(cx)
    refs = [d['ref'] for d in jeu.dossiers]
    random.Random(11).shuffle(refs)
    for t in TABLES:
        cx.execute(f'DELETE FROM {t}')
    for ref in refs:
        c1.traiter(cx, ref)
    assert contenu(cx) == en_lot
    c1.traiter(cx, refs[0])                                 # retraiter ne change rien
    assert contenu(cx) == en_lot
    c1.construire_tout(cx)
    assert contenu(cx) == en_lot


def test_flux_version_par_version_egale_le_lot(jeu, tmp_path):
    flux = base_de(tmp_path, construire=False)
    passage = c0.ouvrir_passage(flux, 'essai', 'scrutation', T0)
    for e in jeu.chronologie:
        c0.recevoir(flux, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
        c1.traiter(flux, e['ref'])
    lot = base_de(tmp_path, construire=False)
    passage = c0.ouvrir_passage(lot, 'essai', 'lot', T0)
    for e in jeu.chronologie:
        c0.recevoir(lot, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
    c1.construire_tout(lot)
    assert contenu(flux) == contenu(lot)
    assert lignes(flux, 'SELECT * FROM ref_cle_canonique ORDER BY 1, 2') == \
        lignes(lot, 'SELECT * FROM ref_cle_canonique ORDER BY 1, 2') != []


def test_dossier_sorti_du_miroir_n_a_plus_de_faits(jeu, tmp_path):
    cx = sqlite3.connect(str(tmp_path / 'b.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    ref = next(v['ref'] for v in jeu.verite if v['notes'].get('evenement') == 'retrait de pièce')
    avant, apres = [e['dossier'] for e in jeu.chronologie if e['ref'] == ref]
    c0.recevoir(cx, passage, avant, maintenant=T0)
    c1.traiter(cx, ref)
    n = cx.execute('SELECT count(*) FROM c1_piece').fetchone()[0]
    c0.recevoir(cx, passage, apres, maintenant=T0)          # la nouvelle version perd une pièce
    c1.traiter(cx, ref)
    assert cx.execute('SELECT count(*) FROM c1_piece').fetchone()[0] == n - 1
    retiree = (set(p['upstreamPieceId'] for p in avant['pieces']) - set(p['upstreamPieceId'] for p in apres['pieces'])).pop()
    assert cx.execute('SELECT count(*) FROM c1_fait WHERE upstream_piece_id = ?', (retiree,)).fetchone()[0] == 0
    cx.execute('DELETE FROM "Piece"'); cx.execute('DELETE FROM "Analysis"'); cx.execute('DELETE FROM "Dossier"')
    c1.traiter(cx, ref)
    assert {t: cx.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES} == dict.fromkeys(TABLES, 0)


def test_pieces_au_contenu_inattendu_ne_plantent_pas(jeu, tmp_path):
    cx = sqlite3.connect(str(tmp_path / 'b.sqlite'))
    migrer.appliquer(cx)
    d = json.loads(json.dumps(jeu.dossiers[0]))
    d['pieces'][0]['fields'] = {'cartes': 'texte', 'mois': [3, None], 'gerants': [None, 'x'], 'employeur': 7,
                                'nom': {'a': {'b': [1, {'c': 2}]}}, 'cin': 123456}
    d['pieces'][1]['fields'] = {'mois': [{'mois': 'x', 'annee': 'y', 'operations': [None, {'date_operation': 5}]}]}
    d['pieces'][1]['type'] = 'RELEVE_BANCAIRE'
    c0.recevoir(cx, c0.ouvrir_passage(cx, 'essai', 'lot', T0), d, maintenant=T0)
    c1.traiter(cx, d['ref'])
    assert cx.execute('SELECT count(*) FROM c1_piece').fetchone()[0] == len(d['pieces'])


def test_entier_demesure_dans_un_releve_ne_fait_pas_tomber_le_lot(jeu, tmp_path):
    cx = sqlite3.connect(str(tmp_path / 'b.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    d = json.loads(json.dumps(jeu.dossiers[0]))
    d['pieces'][0]['type'] = 'RELEVE_BANCAIRE'
    d['pieces'][0]['fields'] = {'mois': [{'mois': 10 ** 30, 'annee': 2 ** 70, 'operations': [{'libelle': 'x'}]}]}
    c0.recevoir(cx, passage, d, maintenant=T0)
    c0.recevoir(cx, passage, jeu.dossiers[1], maintenant=T0)
    c1.construire_tout(cx)
    assert cx.execute('SELECT count(DISTINCT ref) FROM c1_piece').fetchone()[0] == 2
    assert cx.execute('SELECT annee, mois FROM c1_releve_mois WHERE ref = ? AND upstream_piece_id = ?',
                      (d['ref'], d['pieces'][0]['upstreamPieceId'])).fetchall() == [(None, None)]


def test_relectures_mal_formees_et_champs_deja_decodes_ne_plantent_pas(jeu, tmp_path):
    d = json.loads(json.dumps(next(d for d in jeu.dossiers if len(d['reanalyses']) >= 1 and d['pieces'])))
    modele = d['reanalyses'][0]
    d['reanalyses'] = [dict(modele, result=resultat, status='DONE', pieceId=d['pieces'][0]['upstreamPieceId'])
                       for resultat in ('texte', {'apres': ['liste']}, {'apres': 'texte'}, ['liste'], None)]
    cx = base_de(tmp_path, d)
    assert lignes(cx, 'SELECT count(*) FROM c1_piece')[0][0] == len(d['pieces'])
    assert lignes(cx, 'SELECT sum(nb_champs_relus) FROM c1_piece') == [(0,)]
    assert c1._json({'a': 1}) == {'a': 1} and c1._json([1]) == [1] and c1._json('{') is None


def test_operation_lue_a_date_illisible_reste_lue_avec_son_texte(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'RELEVE_BANCAIRE', {'mois': [
        {'annee': 2025, 'mois': 2, 'operations': [{'date_operation': '31/02', 'libelle': 'a'},
                                                  {'date_operation': '05/02/25', 'libelle': 'b'}]},
        {'mois': 3, 'operations': [{'date_operation': '05/03', 'libelle': 'c'}]}]})
    cx = base_de(tmp_path, d)
    assert lignes(cx, 'SELECT nature, date_operation, date_operation_brute FROM c1_releve_operation WHERE '
                      'upstream_piece_id = ? ORDER BY rang_mois, rang', upi) == \
        [('lue', None, '31/02'), ('lue', None, '05/02/25'), ('lue', None, '05/03')]
    assert lignes(cx, 'SELECT sum(nb_operations_lues) FROM c1_releve_mois WHERE upstream_piece_id = ?', upi) == [(3,)]
    au_dessus(cx)
    chemin = cx.execute('PRAGMA database_list').fetchone()[2]
    assert verifier.verifier(chemin) == 0


def test_date_a_cheval_sur_la_fin_d_annee_prend_l_annee_voisine(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'RELEVE_BANCAIRE', {'mois': [
        {'annee': 2025, 'mois': 12, 'operations': [{'date_operation': '31/12', 'date_valeur': '02/01'}]},
        {'annee': 2026, 'mois': 1, 'operations': [{'date_operation': '31/12', 'date_valeur': '02/01'},
                                                  {'date_operation': '15/01/2026', 'date_valeur': '16/01'}]}]})
    cx = base_de(tmp_path, d)
    assert lignes(cx, 'SELECT date_operation, date_valeur FROM c1_releve_operation WHERE upstream_piece_id = ? '
                      'ORDER BY rang_mois, rang', upi) == \
        [('2025-12-31', '2026-01-02'), ('2025-12-31', '2026-01-02'), ('2026-01-15', '2026-01-16')]


@pytest.mark.parametrize('cle', ['titulaire_compte', 'nom_prenom', 'raison_sociale'])
@pytest.mark.parametrize('type_piece', ['RELEVE_BANCAIRE', 'ATTESTATION_RIB'])
def test_titulaire_du_compte_lu_sous_chacune_de_ses_cles(jeu, tmp_path, type_piece, cle):
    d, upi = avec_piece(jeu, type_piece, {cle: 'Zelmou Bakrita', 'rib': '999' + '0' * 21, 'banque': 'Banque Tazoula'})
    cx = base_de(tmp_path, d)
    assert lignes(cx, "SELECT nom_complet FROM c1_mention_personne WHERE upstream_piece_id = ? AND role = "
                      "'titulaire_compte'", upi) == [('Zelmou Bakrita',)]
    assert lignes(cx, "SELECT porteur FROM c1_identifiant_brut WHERE upstream_piece_id = ? AND type = 'RIB'", upi) == \
        [('Zelmou Bakrita',)]
    assert lignes(cx, "SELECT nom FROM c1_mention_societe WHERE upstream_piece_id = ? AND role = 'banque'", upi) == \
        [('Banque Tazoula',)]


def test_adresse_du_releve_portee_par_la_mention_du_titulaire(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'RELEVE_BANCAIRE', {'titulaire_compte': 'Zelmou Bakrita', 'adresse': '9 RUE ZIRMAK'})
    cx = base_de(tmp_path, d)
    assert lignes(cx, "SELECT adresse FROM c1_mention_personne WHERE upstream_piece_id = ? AND role = "
                      "'titulaire_compte'", upi) == [('9 RUE ZIRMAK',)]


def test_identifiants_recus_en_nombre_gardes(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'BULLETIN_DE_PAIE', {'nom': 'Zelmou', 'numero_affiliation': 9991234,
                                                  'employeur': {'raison_sociale': 'Tazoula Sarl', 'ice': 999000000000001}})
    cx = base_de(tmp_path, d)
    assert dict(lignes(cx, 'SELECT type, valeur FROM c1_identifiant_brut WHERE upstream_piece_id = ?', upi)) == \
        {'AFFILIATION_CNSS': '9991234', 'ICE': '999000000000001'}


def test_liste_d_objets_hors_des_listes_connues_comptee_jamais_perdue_en_silence(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'REGISTRE_COMMERCE', {'denomination_sociale': 'Tazoula Sarl', 'saisies': [{'a': 1}],
                                                   'signataires': [{'nom': 'x'}], 'gerants': [{'nom': 'y'}], 'vide': []})
    cx = base_de(tmp_path, d)
    assert lignes(cx, 'SELECT nb_listes_ignorees FROM c1_piece WHERE upstream_piece_id = ?', upi) == [(2,)]
    assert lignes(cx, 'SELECT sum(nb_listes_ignorees) FROM c1_piece WHERE upstream_piece_id <> ?', upi) == [(0,)]


def test_reference_des_cles_presente_apres_un_traitement_au_fil_de_l_eau(jeu, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers[0], construire=False)
    c1.traiter(cx, jeu.dossiers[0]['ref'])
    assert lignes(cx, 'SELECT count(*) FROM ref_cle_canonique')[0][0] == len(cles.lignes_de_reference())


def test_valeur_retenue_departagee_de_facon_stable(jeu, tmp_path):
    d, upi = avec_piece(jeu, 'FACTURE_PROFORMA_VEHICULE', {'vehicule.marque': 'DACIA', 'vehicule': {'marque': 'Dacia'}})
    cx = base_de(tmp_path, d)
    assert lignes(cx, "SELECT valeur FROM c1_fait_retenu WHERE upstream_piece_id = ? AND cle = 'marque_vehicule'",
                  upi) == [('DACIA',)]


# ---- invariants ----------------------------------------------------------------------------------------------------

def test_invariants_de_c1_verts_puis_rouges_si_on_les_viole(base, capsys):
    cx, chemin = base
    au_dessus(cx)
    assert verifier.verifier(chemin) == 0
    cx.execute("INSERT INTO c1_fait VALUES ('ZZ26R9999', 'eqdom_CIN', 'CIN', 'nom', 'nom', 'x', NULL, NULL, NULL, "
               "'amont', 'normal', 1)")
    cx.commit()
    assert verifier.verifier(chemin) == 1
    assert 'c1_fait_sans_piece : 1' in capsys.readouterr().out
    cx.execute("DELETE FROM c1_fait WHERE ref = 'ZZ26R9999'")
    cx.commit()


@pytest.mark.parametrize('nom, viol', [
    ('c1_operation_lue_sans_date', "UPDATE c1_releve_operation SET date_operation_brute = NULL, date_operation = NULL "
                                   "WHERE nature = 'lue'"),
    ('c1_releve_mois_montant_non_numerique', "UPDATE c1_releve_mois SET solde_cloture = 'douze'"),
    ('c1_cle_connue_hors_reference', "UPDATE c1_fait SET cle_brute = 'cle_jamais_vue' WHERE cle_brute = 'nom'"),
    ('c1_piece_absente_du_miroir', 'DELETE FROM "Piece"'),
    ('c1_piece_du_miroir_non_traitee', ' ; '.join(f'DELETE FROM {t} WHERE ref = (SELECT min(ref) FROM c1_piece)'
                                                  for t in reversed(TABLES))),
    ('c1_piece_d_une_autre_version', "UPDATE c1_piece SET version = '2020-01-01T00:00:00.000Z'"),
    ('c1_mention_ou_identifiant_sans_piece', "UPDATE c1_releve_mois SET upstream_piece_id = 'absente'"),
])
def test_chaque_invariant_de_c1_devient_rouge_quand_on_le_viole(jeu, tmp_path, capsys, nom, viol):
    releve_lu = next(d for d in jeu.dossiers if d['ref'] == ref_de(jeu, 'T01'))
    cx = base_de(tmp_path, releve_lu, *[d for d in jeu.dossiers[:12] if d is not releve_lu])
    au_dessus(cx)
    chemin = cx.execute('PRAGMA database_list').fetchone()[2]
    assert verifier.verifier(chemin) == 0
    cx.executescript(viol)
    cx.commit()
    assert verifier.verifier(chemin) == 1
    sortie = capsys.readouterr().out
    assert f'ÉCART  {nom} : ' in sortie and 'ZZ' not in sortie


def test_la_couche_suit_c0_dans_l_ordre_des_couches():
    from pipeline.couches import COUCHES
    assert [c.nom for c in COUCHES[:2]] == ['c0', 'c1']
