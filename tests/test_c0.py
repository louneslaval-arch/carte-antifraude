"""Tests de la couche 0 (étape D) : versions brutes gardées telles quelles, miroir de la v2 projeté de la dernière
version, rien perdu, rien doublé, flux = lot."""

import copy
import json
import os
import sqlite3
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
from pipeline import migrer, modeles_v2  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402

T0 = '2026-11-13T10:00:00.000Z'
TABLES_MIROIR = ('Dossier', 'Piece', 'Analysis', 'AnalysisControl', 'Reanalysis')


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture
def cx(tmp_path):
    connexion = sqlite3.connect(str(tmp_path / 'base.sqlite'))
    connexion.execute('PRAGMA foreign_keys = ON')
    migrer.appliquer(connexion)
    yield connexion
    connexion.close()


@pytest.fixture
def passage(cx):
    return c0.ouvrir_passage(cx, 'essai', 'lot', T0)


def compte(cx, table):
    return cx.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]


def miroir(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM "{t}"').fetchall(), key=repr) for t in TABLES_MIROIR}


def ref_de(jeu, code):
    return next(v['ref'] for v in jeu.verite if code in v['scenarios'] or code in v['pieges'])


def versions(jeu, ref):
    return [e['dossier'] for e in jeu.chronologie if e['ref'] == ref]


# ---- versions brutes -----------------------------------------------------------------------------------------------

def test_version_gardee_telle_quelle_avec_son_empreinte(cx, passage, jeu):
    d = jeu.dossiers[0]
    assert c0.recevoir(cx, passage, d, maintenant=T0) is True
    ref, empreinte, updated_at, texte, actif = cx.execute(
        'SELECT ref, empreinte, updated_at, json, actif FROM c0_dossier_brut').fetchone()
    assert json.loads(texte) == d and ref == d['ref'] and updated_at == d['updatedAt'] and actif == 1
    assert empreinte == c0.empreinte(d) and len(empreinte) == 64


def test_empreinte_independante_de_l_ordre_des_cles(jeu):
    d = jeu.dossiers[0]
    assert c0.empreinte(dict(reversed(list(d.items())))) == c0.empreinte(d)
    assert c0.empreinte(dict(d, clientName='AUTRE')) != c0.empreinte(d)


def test_deux_passages_identiques_n_ajoutent_aucune_ligne(cx, passage, jeu):
    for d in jeu.dossiers[:30]:
        c0.recevoir(cx, passage, d, maintenant=T0)
    avant = {t: compte(cx, t) for t in TABLES_MIROIR + ('c0_dossier_brut',)}
    second = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    assert [c0.recevoir(cx, second, d, maintenant=T0) for d in jeu.dossiers[:30]] == [False] * 30
    assert {t: compte(cx, t) for t in avant} == avant


def test_dossier_modifie_ajoute_une_version_l_ancienne_reste_intacte(cx, passage, jeu):
    avant, apres = versions(jeu, ref_de(jeu, 'S17'))
    c0.recevoir(cx, passage, avant, maintenant=T0)
    premiere = cx.execute('SELECT empreinte, json FROM c0_dossier_brut').fetchone()
    assert c0.recevoir(cx, passage, apres, maintenant=T0) is True
    lignes = cx.execute('SELECT empreinte, json FROM c0_dossier_brut ORDER BY updated_at').fetchall()
    assert len(lignes) == 2 and lignes[0] == premiere and json.loads(lignes[1][1]) == apres


def test_passage_compte_les_dossiers_et_les_versions_nouvelles(cx, passage, jeu):
    nouvelles = sum(c0.recevoir(cx, passage, d, maintenant=T0) for d in jeu.dossiers[:5])
    c0.fermer_passage(cx, passage, dossiers=5, versions_nouvelles=nouvelles, maintenant=T0)
    assert cx.execute('SELECT dossiers, versions_nouvelles, termine_le FROM c0_export').fetchone() == (5, 5, T0)


def test_dossier_sans_reference_ou_sans_date_refuse_sans_citer_son_contenu(cx, passage, jeu):
    casse = dict(jeu.dossiers[0], ref=None)
    with pytest.raises(c0.DossierIllisible) as erreur:
        c0.recevoir(cx, passage, casse, maintenant=T0)
    assert jeu.dossiers[0]['clientName'] not in str(erreur.value)


# ---- miroir --------------------------------------------------------------------------------------------------------

def test_miroir_montre_la_derniere_version(cx, passage, jeu):
    avant, apres = versions(jeu, ref_de(jeu, 'S17'))
    c0.recevoir(cx, passage, avant, maintenant=T0)
    c0.recevoir(cx, passage, apres, maintenant=T0)
    assert compte(cx, 'Dossier') == 1
    assert cx.execute('SELECT "updatedAt" FROM "Dossier"').fetchone()[0] == apres['updatedAt']
    cin = next(p for p in apres['pieces'] if p['type'] == 'CIN')['fields']['cin']
    champs = json.loads(cx.execute('SELECT fields FROM "Piece" WHERE type = \'CIN\'').fetchone()[0])
    assert champs['cin'] == cin
    assert compte(cx, 'Analysis') == len(apres['analyses']) == 2


def test_version_ancienne_recue_apres_coup_ne_remplace_pas_le_miroir(cx, passage, jeu):
    avant, apres = versions(jeu, ref_de(jeu, 'S17'))
    c0.recevoir(cx, passage, apres, maintenant=T0)
    c0.recevoir(cx, passage, avant, maintenant=T0)
    assert cx.execute('SELECT "updatedAt" FROM "Dossier"').fetchone()[0] == apres['updatedAt']
    assert compte(cx, 'c0_dossier_brut') == 2


def test_projection_champ_par_champ(cx, passage, jeu):
    d = next(x for x in jeu.dossiers if x['latestAnalysis'] and x['reanalyses'])
    c0.recevoir(cx, passage, d, maintenant=T0)
    cx.row_factory = sqlite3.Row
    ligne = cx.execute('SELECT * FROM "Dossier"').fetchone()
    for cle in ('id', 'ref', 'personType', 'csp', 'productType', 'paymentMode', 'clientName', 'agence', 'canal',
                'category', 'categoryRule', 'analysisStatus', 'verdict', 'matrixVersion', 'createdAt', 'updatedAt'):
        assert ligne[cle] == d[cle], cle
    assert json.loads(ligne['businessData']) == d['businessData'] and ligne['actif'] == 1
    pieces = cx.execute('SELECT * FROM "Piece"').fetchall()
    assert {p['upstreamPieceId'] for p in pieces} == {p['upstreamPieceId'] for p in d['pieces']}
    assert all(p['dossierId'] == d['id'] for p in pieces)
    controles = cx.execute('SELECT * FROM "AnalysisControl"').fetchall()
    assert {c['controlId'] for c in controles} == {c['controlId'] for c in d['latestAnalysis']['controls']}
    assert all(c['analysisId'] == d['latestAnalysis']['id'] and json.loads(c['missing']) == [] for c in controles)
    relectures = cx.execute('SELECT * FROM "Reanalysis"').fetchall()
    assert len(relectures) == len(d['reanalyses'])
    assert json.loads(relectures[0]['requestedFields']) == d['reanalyses'][0]['requestedFields']
    cx.row_factory = None


def test_piece_retiree_par_une_nouvelle_version_quitte_le_miroir(cx, passage, jeu):
    ref = next(v['ref'] for v in jeu.verite if v['notes'].get('evenement') == 'retrait de pièce')
    avant, apres = versions(jeu, ref)
    c0.recevoir(cx, passage, avant, maintenant=T0)
    assert compte(cx, 'Piece') == len(avant['pieces'])
    c0.recevoir(cx, passage, apres, maintenant=T0)
    assert compte(cx, 'Piece') == len(apres['pieces']) == len(avant['pieces']) - 1


def test_analyse_non_terminee_stockee_en_cours(cx, passage, jeu):
    d = next(x for x in jeu.dossiers if x['ref'] == ref_de(jeu, 'S21'))
    c0.recevoir(cx, passage, d, maintenant=T0)
    assert cx.execute('SELECT "analysisStatus" FROM "Dossier"').fetchone()[0] == 'EN_COURS'
    assert compte(cx, 'Analysis') == 0 and compte(cx, 'AnalysisControl') == 0


def test_dossier_archive_repris_et_marque(cx, passage, jeu):
    d = next(x for x in jeu.dossiers if x['ref'] == ref_de(jeu, 'S22'))
    c0.recevoir(cx, passage, d, actif=False, maintenant=T0)
    assert cx.execute('SELECT actif FROM c0_dossier_brut').fetchone()[0] == 0
    assert cx.execute('SELECT actif FROM "Dossier"').fetchone()[0] == 0
    c0.recevoir(cx, passage, d, actif=True, maintenant=T0)                 # réactivé, sans nouvelle version
    assert compte(cx, 'c0_dossier_brut') == 1 and cx.execute('SELECT actif FROM "Dossier"').fetchone()[0] == 1


def test_valeur_d_enumeration_inconnue_refusee_par_le_miroir_la_version_brute_reste(cx, passage, jeu):
    d = dict(copy.deepcopy(jeu.dossiers[0]), verdict='VERDICT_INCONNU')
    with pytest.raises(c0.MiroirRefuse):
        c0.recevoir(cx, passage, d, maintenant=T0)
    assert compte(cx, 'c0_dossier_brut') == 1 and compte(cx, 'Dossier') == 0


# ---- flux = lot ----------------------------------------------------------------------------------------------------

def test_reconstruire_tout_donne_le_meme_miroir_que_le_fil_de_l_eau(cx, passage, jeu):
    for e in jeu.chronologie[:120] + [x for x in jeu.chronologie if x['version'] > 1]:
        c0.recevoir(cx, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
    au_fil_de_l_eau = miroir(cx)
    c0.construire_tout(cx)
    assert miroir(cx) == au_fil_de_l_eau
    for t in TABLES_MIROIR:
        cx.execute(f'DELETE FROM "{t}"')
    c0.construire_tout(cx)
    assert miroir(cx) == au_fil_de_l_eau
    une = jeu.chronologie[0]['ref']
    c0.traiter(cx, une)
    assert miroir(cx) == au_fil_de_l_eau


# ---- place de chaque champ de DossierDetail ------------------------------------------------------------------------

def champs_de(modele, prefixe=''):
    for nom, c in modele.model_fields.items():
        yield prefixe + (c.alias or nom)


def test_chaque_champ_de_dossier_detail_a_sa_place_declaree(cx):
    attendus = set(champs_de(modeles_v2.DossierDetail))
    for objet, modele in (('pieces[].', modeles_v2.Piece), ('analyses[].', modeles_v2.AnalysisSummary),
                          ('reanalyses[].', modeles_v2.ReanalysisInfo), ('latestAnalysis.', modeles_v2.LatestAnalysis),
                          ('latestAnalysis.controls[].', modeles_v2.AnalysisControl)):
        attendus |= set(champs_de(modele, objet))
    assert set(c0.PLACES) == attendus
    for chemin, place in c0.PLACES.items():
        if place == c0.BRUT:
            continue
        table, colonne = place
        assert colonne in {r[1] for r in cx.execute(f'PRAGMA table_info("{table}")')}, chemin


def test_la_couche_est_declaree_dans_l_ordre_des_couches():
    from pipeline.couches import COUCHES
    assert COUCHES[0] is c0 and c0.nom == 'c0'
