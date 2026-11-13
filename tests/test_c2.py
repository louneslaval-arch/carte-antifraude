"""Tests de la couche 2 (étape F) : une fiche maître par personne et par société, qui réunit la liste noire, le
registre du commerce (socle construit par le kit) et les dossiers de la v2. Tout est fictif."""

import csv
import json
import os
import random
import sqlite3
import subprocess
import sys
import uuid

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import verifier  # noqa: E402
from pipeline import construire_base as cb  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402
from pipeline.couches import c1_faits as c1  # noqa: E402
from pipeline.couches import c2_identites as c2  # noqa: E402

T0 = '2026-11-13T10:00:00.000Z'
TABLES = ('c2_mention', 'c2_personne', 'c2_societe', 'c2_correspondance_mention', 'c2_identifiant_attribue',
          'ref_liste_noire')
VUES = ('c2_correspondance', 'c2_alias', 'c2_adresse', 'c2_role', 'c2_identifiant', 'c2_employeur')


# ---- montage -------------------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture(scope='module')
def socle(jeu, tmp_path_factory):
    """Base du kit (liste noire et registre fictifs du monde des dossiers), construite par `construire_base.py`."""
    d = tmp_path_factory.mktemp('socle')
    g = jeu.monde
    gd.ecrire_csv(str(d / 'liste_noire.csv'), g.bl, gd.COLONNES_BL)
    gd.ecrire_csv(str(d / 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    gd.ecrire_csv(str(d / 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    r = subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'construire_base.py'),
                        '--liste-noire', str(d / 'liste_noire.csv'), '--rc-annonces', str(d / 'rc_annonces.csv'),
                        '--rc-personnes', str(d / 'rc_personnes.csv'), '--base', str(d / 'socle.sqlite')],
                       capture_output=True, text=True)
    assert r.returncode == 0
    return str(d / 'socle.sqlite')


def base_de(tmp_path, dossiers=(), socle=None, construire=True):
    """Base neuve : dossiers reçus (c0), c1 en lot, socle chargé, c2 en lot."""
    cx = sqlite3.connect(str(tmp_path / f'base_{len(os.listdir(tmp_path))}.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for d in dossiers:
        c0.recevoir(cx, passage, d, maintenant=T0)
    c1.construire_tout(cx)
    if socle:
        c2.charger_socle(cx, socle)
    if construire:
        c2.construire_tout(cx)
    return cx


@pytest.fixture(scope='module')
def base(jeu, socle, tmp_path_factory):
    cx = base_de(tmp_path_factory.mktemp('c2'), jeu.dossiers, socle)
    yield cx
    cx.close()


@pytest.fixture
def cx(base):
    return base


def lignes(cx, sql, *p):
    return cx.execute(sql, p).fetchall()


def un(cx, sql, *p):
    return cx.execute(sql, p).fetchone()[0]


def contenu(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM {t}').fetchall(), key=repr) for t in TABLES + VUES}


def dossier(jeu, n, *pieces):
    """Dossier fictif minimal : une pièce par couple (type, champs)."""
    d = json.loads(json.dumps(jeu.dossiers[0]))
    modele = d['pieces'][0]
    d.update(ref=f'ZZ26T{n:04d}', id=str(uuid.uuid5(uuid.NAMESPACE_OID, f'essai-c2-{n}')), analyses=[],
             latestAnalysis=None, reanalyses=[])
    d['pieces'] = [dict(modele, type=t, upstreamPieceId=f'eqdom_{t}_{k}', fields=f) for k, (t, f) in enumerate(pieces)]
    return d


def cin_de(nom, prenom, cin):
    return ('CIN', {'nom': nom, 'prenom': prenom, 'cin': cin})


def mini_socle(tmp_path, entites=(), societes=(), personnes=(), correspondances=(), decisions=()):
    """Petite base au schéma du kit, remplie à la main."""
    chemin = str(tmp_path / f'socle_{len(os.listdir(tmp_path))}.sqlite')
    con = sqlite3.connect(chemin)
    with open(os.path.join(RACINE, 'pipeline', 'schema_bl_rc.sql'), encoding='utf-8') as f:
        con.executescript(f.read())
    con.execute('PRAGMA foreign_keys = OFF')              # les référentiels du kit (rôles, villes) restent vides ici
    for table, rangs in (('bl_entite', entites), ('rc_societe', societes), ('rc_personne', personnes),
                         ('correspondance_retenue', correspondances), ('decision_analyste', decisions)):
        for r in rangs:
            con.execute(f'INSERT INTO {table} ({", ".join(r)}) VALUES ({", ".join("?" * len(r))})', list(r.values()))
    con.commit()
    con.close()
    return chemin


def fiche(cx, **criteres):
    sql = ' AND '.join(f'{c} = ?' for c in criteres)
    return {f for (f,) in lignes(cx, f'SELECT fiche FROM c2_mention WHERE {sql}', *criteres.values())}


# ---- liste noire dans la structure de Kamal ------------------------------------------------------------------------

def test_liste_noire_rangee_dans_la_structure_de_blacklistentry_sans_perte(cx, socle):
    kit = sqlite3.connect(socle)
    entites = kit.execute('SELECT cle_entite, type_entite, nom_affiche, cin, rc_num, tribunal_code, ice, statut, '
                          'types_liste, motifs, adresse, date_naissance FROM bl_entite ORDER BY cle_entite').fetchall()
    rangees = lignes(cx, 'SELECT cle_entite, personne, label, cin, rc, tribunal, ice, statut, "typeListe", motif, '
                         'adresse, date_naissance FROM ref_liste_noire ORDER BY cle_entite')
    assert rangees == entites and len(entites) > 50
    colonnes = {c[1] for c in lignes(cx, 'PRAGMA table_info(ref_liste_noire)')}
    assert {'id', 'kind', 'label', 'normalized', 'city', 'active', 'createdAt', 'personne', 'nom', 'prenom',
            'raisonSociale', 'cin', 'rc', 'typeListe', 'motif', 'source'} <= colonnes
    assert {k for (k,) in lignes(cx, 'SELECT DISTINCT kind FROM ref_liste_noire')} <= \
        {'CLIENT', 'EMPLOYEUR', 'GERANT', 'BENEFICIAIRE', 'TIERS_BANCAIRE', 'ZONE'}
    assert lignes(cx, "SELECT count(*) FROM ref_liste_noire WHERE (active = 1) <> (statut = 'actif')") == [(0,)]


def test_chaque_objet_du_socle_et_chaque_mention_de_c1_a_sa_mention(cx, socle):
    kit = sqlite3.connect(socle)
    for source, tables in (('liste_noire', ('bl_entite',)), ('registre', ('rc_societe', 'rc_personne'))):
        attendu = sum(kit.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables)
        assert un(cx, 'SELECT count(*) FROM c2_mention WHERE source = ?', source) == attendu
    assert un(cx, "SELECT count(*) FROM c2_mention WHERE source = 'v2' AND type_fiche = 'PP'") == \
        un(cx, 'SELECT count(*) FROM c1_mention_personne')
    assert un(cx, "SELECT count(*) FROM c2_mention WHERE source = 'v2' AND type_fiche = 'PM'") == \
        un(cx, "SELECT count(*) FROM c1_mention_societe WHERE role <> 'banque'")


# ---- rattachement par clé forte ------------------------------------------------------------------------------------

def test_meme_cin_dans_la_liste_noire_et_dans_un_dossier_une_seule_fiche_inscrite(cx, jeu):
    v = next(v for v in jeu.verite if 'S01' in v['scenarios'])
    cin = v['identites'][0]['cin']
    fiches = fiche(cx, cin=cin)
    assert len(fiches) == 1
    sources = {s for (s,) in lignes(cx, 'SELECT DISTINCT source FROM c2_mention WHERE fiche = ?', *fiches)}
    assert {'liste_noire', 'v2'} <= sources
    assert lignes(cx, 'SELECT inscrit, cin FROM c2_personne WHERE identifiant = ?', *fiches) == [(1, cin)]
    assert lignes(cx, "SELECT DISTINCT regle FROM c2_mention WHERE cin = ?", cin) == [('CIN',)]


def test_societe_d_un_dossier_rattachee_au_registre_par_rc_et_tribunal_ou_par_ice(cx):
    par_rc = lignes(cx, "SELECT v.fiche, r.fiche FROM c2_mention v JOIN c2_mention r ON r.rc_cle = v.rc_cle AND "
                        "r.source = 'registre' WHERE v.source = 'v2' AND v.rc_cle IS NOT NULL")
    par_ice = lignes(cx, "SELECT v.fiche, r.fiche FROM c2_mention v JOIN c2_mention r ON r.ice = v.ice AND "
                         "r.source = 'registre' WHERE v.source = 'v2' AND v.ice IS NOT NULL")
    assert par_rc and par_ice and all(a == b for a, b in par_rc + par_ice)
    assert un(cx, "SELECT count(*) FROM c2_societe WHERE inscrit = 1") > 0


def test_mention_sans_cle_forte_fiche_propre_au_dossier(jeu, tmp_path):
    a = dossier(jeu, 1, ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'employeur': 'TAZOULA SARL'}))
    b = dossier(jeu, 2, ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'employeur': 'TAZOULA SARL'}))
    cx = base_de(tmp_path, [a, b])
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 2 and un(cx, 'SELECT count(*) FROM c2_societe') == 2
    assert {r for (r,) in lignes(cx, 'SELECT DISTINCT regle FROM c2_mention')} == {'propre'}
    assert un(cx, "SELECT count(*) FROM c2_role WHERE role = 'employe'") == 2


def test_meme_personne_en_latin_et_en_arabe(jeu, tmp_path):
    p = next(p for p in jeu.monde.personnes if p['nom'][1] and p['prenom'][1])
    latin, arabe = f"{p['nom'][0]} {p['prenom'][0]}", f"{p['prenom'][1]} {p['nom'][1]}"
    kit = mini_socle(tmp_path, societes=[dict(societe_id=1, cle_societe='RC:70001@KENITRA', denomination='TAZOULA SARL',
                                              rc_num='70001', tribunal_code='KENITRA')],
                     personnes=[dict(personne_id=1, cle_stable='RC:70001@KENITRA|CIN:ZZ100001', societe_id=1,
                                     type_personne='PP', nom_complet=arabe, ecriture='arabe', cin='ZZ100001',
                                     cin_norm='ZZ100001', cin_statut='valide', role='gerant')])
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(p['nom'][0], p['prenom'][0], 'ZZ100001'))], kit)
    assert len(fiche(cx, cin='ZZ100001')) == 1 and un(cx, 'SELECT count(*) FROM c2_personne') == 1
    assert sorted(lignes(cx, "SELECT ecriture, alias FROM c2_alias WHERE fiche LIKE 'pp_%'")) == \
        [('arabe', arabe), ('latin', latin)]
    assert lignes(cx, 'SELECT nom FROM c2_personne') == [(latin,)]          # le nom affiché est en écriture latine


def test_homonymes_a_cin_differents_deux_fiches_sans_rapprochement(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001')),
                            dossier(jeu, 2, cin_de('ZELMOU', 'BAKRITA', 'ZZ100002'))])
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 2
    assert un(cx, 'SELECT count(*) FROM c2_correspondance') == 0


def test_cin_a_lettre_parasite_rapproche_jamais_fusionne(cx, socle):
    kit = sqlite3.connect(socle)
    n = kit.execute("SELECT count(*) FROM correspondance_retenue WHERE regle = 'R01v'").fetchone()[0]
    paires = lignes(cx, "SELECT fiche_a, fiche_b, niveau, statut, nb_mentions FROM c2_correspondance WHERE regle = 'R01v'")
    assert n > 0 and sum(p[4] for p in paires) == n       # une personne citée dans deux sociétés : une seule fiche
    assert all(a != b and niveau == 'probable' and statut == 'homonymie' for a, b, niveau, statut, _ in paires)


def test_societe_sous_deux_denominations_une_seule_fiche(jeu, tmp_path):
    rc = lambda nom: ('REGISTRE_COMMERCE', {'denomination_sociale': nom, 'numero_analytique': '70001',  # noqa: E731
                                            'ville_tribunal': 'Tribunal de commerce de Kénitra'})
    cx = base_de(tmp_path, [dossier(jeu, 1, rc('TAZOULA SARL')), dossier(jeu, 2, rc('ZIRMAK NEGOCE SARL'))])
    assert lignes(cx, 'SELECT rc, tribunal FROM c2_societe') == [('70001', 'KENITRA')]
    assert un(cx, 'SELECT count(DISTINCT alias) FROM c2_alias') == 2
    assert lignes(cx, 'SELECT DISTINCT regle FROM c2_mention') == [('RC_TRIB',)]


def test_cin_partage_par_deux_noms_incompatibles_pas_de_fusion_signalement(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001')),
                            dossier(jeu, 2, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001')),
                            dossier(jeu, 3, cin_de('TAGHRIZ', 'MILOUDA', 'ZZ100001'))])
    assert sorted(lignes(cx, 'SELECT nom, cin, nb_mentions FROM c2_personne')) == \
        [('TAGHRIZ MILOUDA', 'ZZ100001', 1), ('ZELMOU BAKRITA', 'ZZ100001', 2)]
    assert lignes(cx, 'SELECT regle, niveau, statut FROM c2_correspondance') == [('CIN_PARTAGE', 'a_verifier', 'alerte')]
    cx.commit()
    assert verifier.verifier(cx.execute('PRAGMA database_list').fetchone()[2]) == 0


def test_cin_partage_entre_deux_ecritures_jamais_separe_faute_de_preuve(jeu, tmp_path):
    p, q = [x for x in jeu.monde.personnes if x['nom'][1] and x['prenom'][1]][:2]
    assert p['nom'][0] != q['nom'][0]
    kit = mini_socle(tmp_path, societes=[dict(societe_id=1, cle_societe='RC:70001@KENITRA', denomination='TAZOULA SARL',
                                              rc_num='70001', tribunal_code='KENITRA')],
                     personnes=[dict(personne_id=1, cle_stable='RC:70001@KENITRA|CIN:ZZ100001', societe_id=1,
                                     type_personne='PP', nom_complet=f"{q['prenom'][1]} {q['nom'][1]}",
                                     ecriture='arabe', cin='ZZ100001', cin_norm='ZZ100001', cin_statut='valide',
                                     role='gerant')])
    cx = base_de(tmp_path, [dossier(jeu, 1, cin_de(p['nom'][0], p['prenom'][0], 'ZZ100001'))], kit)
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 1 and un(cx, 'SELECT count(*) FROM c2_correspondance') == 0


def test_mention_sans_cin_rattachee_a_la_cin_du_meme_dossier_par_le_nom(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001'),
                ('RELEVE_BANCAIRE', {'titulaire_compte': 'BAKRITA ZELMOU', 'rib': '999' + '0' * 21}),
                ('ATTESTATION_RIB', {'titulaire_compte': 'TAGHRIZ MILOUDA', 'rib': '999' + '1' * 21}))
    cx = base_de(tmp_path, [d])
    assert sorted(lignes(cx, 'SELECT role, regle FROM c2_mention ORDER BY role')) == \
        [('titulaire_cin', 'CIN'), ('titulaire_compte', 'nom_dans_dossier'), ('titulaire_compte', 'propre')]
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 2
    assert sorted(lignes(cx, "SELECT p.nom, i.valeur FROM c2_identifiant i JOIN c2_personne p ON p.identifiant = "
                             "i.fiche WHERE i.type = 'RIB'")) == \
        [('TAGHRIZ MILOUDA', '999' + '1' * 21), ('ZELMOU BAKRITA', '999' + '0' * 21)]


def test_gerant_d_un_dossier_retrouve_au_registre_dans_la_meme_societe_le_dossier_apporte_le_cin(jeu, tmp_path):
    kit = mini_socle(tmp_path, societes=[dict(societe_id=1, cle_societe='RC:70001@KENITRA', denomination='TAZOULA SARL',
                                              rc_num='70001', tribunal_code='KENITRA')],
                     personnes=[dict(personne_id=k, cle_stable=f'RC:70001@KENITRA|N:{nom}', societe_id=1,
                                     type_personne='PP', nom_complet=nom, ecriture='latin', cin_statut='absent',
                                     role='gerant') for k, nom in enumerate(('ZELMOU BAKRITA', 'TAGHRIZ MILOUDA'), 1)])
    d = dossier(jeu, 1, ('REGISTRE_COMMERCE', {'denomination_sociale': 'TAZOULA', 'numero_analytique': '70001',
                                               'ville_tribunal': 'KENITRA',
                                               'gerants': [{'nom_complet': 'BAKRITA ZELMOU', 'cin': 'ZZ100001'}]}))
    cx = base_de(tmp_path, [d], kit)
    assert sorted(lignes(cx, "SELECT nom, regle, cin_effectif FROM c2_mention WHERE source = 'registre' AND "
                             "type_fiche = 'PP'")) == \
        [('TAGHRIZ MILOUDA', 'propre', None), ('ZELMOU BAKRITA', 'AF05', 'ZZ100001')]
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 2 and un(cx, 'SELECT count(*) FROM c2_societe') == 1
    assert lignes(cx, "SELECT count(DISTINCT fiche), count(DISTINCT societe) FROM c2_role WHERE role = 'gerant'") == \
        [(2, 1)]
    cx.execute('DELETE FROM "Piece"'); cx.execute('DELETE FROM "Dossier"')         # le dossier sort du miroir
    c1.traiter(cx, d['ref'])
    c2.traiter(cx, d['ref'])
    assert sorted(lignes(cx, "SELECT nom, regle, cin_effectif FROM c2_mention")) == \
        [('TAGHRIZ MILOUDA', 'propre', None), ('TAZOULA SARL', 'RC_TRIB', None), ('ZELMOU BAKRITA', 'propre', None)]
    assert un(cx, 'SELECT count(*) FROM c2_personne') == 2 and un(cx, 'SELECT count(*) FROM c2_personne WHERE cin IS NOT NULL') == 0


def test_mention_gabarit_sans_fiche(cx):
    n, sans = lignes(cx, "SELECT count(*), sum(CASE WHEN fiche IS NULL THEN 1 ELSE 0 END) FROM c2_mention WHERE "
                         "statut = 'gabarit'")[0]
    assert n > 0 and n == sans
    assert lignes(cx, "SELECT DISTINCT regle FROM c2_mention WHERE statut = 'gabarit'") == [('gabarit',)]


def test_banque_d_un_releve_n_est_pas_une_fiche(jeu, tmp_path):
    cx = base_de(tmp_path, [dossier(jeu, 1, ('RELEVE_BANCAIRE', {'titulaire_compte': 'ZELMOU BAKRITA',
                                                                 'banque': 'BANQUE TAZOULA'}))])
    assert un(cx, 'SELECT count(*) FROM c2_societe') == 0 and un(cx, 'SELECT count(*) FROM c2_personne') == 1


# ---- rapprochements et décisions -----------------------------------------------------------------------------------

def test_correspondances_du_kit_reprises_telles_quelles(cx, socle):
    kit = sqlite3.connect(socle)
    attendu = sorted(kit.execute('SELECT regle, niveau, statut, count(*) FROM correspondance_retenue GROUP BY 1, 2, 3'))
    assert sorted(lignes(cx, "SELECT regle, niveau, statut, count(*) FROM c2_correspondance_mention WHERE source = "
                             "'kit' GROUP BY 1, 2, 3")) == attendu


def test_aucun_rapprochement_certain_d_identite_entre_deux_fiches(cx):
    assert un(cx, "SELECT count(*) FROM c2_correspondance WHERE niveau = 'certain' AND nature = 'identite'") == 0
    assert un(cx, "SELECT count(*) FROM c2_correspondance WHERE fiche_a = fiche_b") == 0
    assert un(cx, "SELECT count(*) FROM c2_correspondance WHERE statut = 'homonymie'") > 0


def test_regles_sur_le_perimetre_d_un_dossier_inscrit_sans_cin_et_societe_inscrite_sans_rc(jeu, tmp_path):
    kit = mini_socle(tmp_path, entites=[
        dict(entite_id=1, cle_entite='P#1', type_entite='PP', nom_affiche='ZELMOU BAKRITA', statut='actif'),
        dict(entite_id=2, cle_entite='M#2', type_entite='PM', nom_affiche='TAZOULA NEGOCE SARL', statut='actif'),
        dict(entite_id=3, cle_entite='M:70001@?:ZIRMAK', type_entite='PM', nom_affiche='ZIRMAK SARL', rc_num='70001',
             statut='actif')])
    d = dossier(jeu, 1, ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'BAKRITA', 'prenom': 'ZELMOU',
                                                         'employeur': 'Sté TAZOULA NEGOCE'}),
                ('REGISTRE_COMMERCE', {'denomination_sociale': 'ZIRMAK', 'numero_analytique': '70001',
                                       'ville_tribunal': 'KENITRA'}))
    cx = base_de(tmp_path, [d], kit)
    assert sorted(lignes(cx, 'SELECT regle, niveau, statut, source FROM c2_correspondance')) == \
        [('AF01n', 'a_verifier', 'homonymie', 'v2'), ('AF02b', 'probable', 'homonymie', 'v2'),
         ('AF07', 'a_verifier', 'homonymie', 'v2')]
    assert un(cx, 'SELECT count(*) FROM c2_personne WHERE inscrit = 1') == 1          # la fiche du dossier ne l'est pas
    assert lignes(cx, 'SELECT count(*) FROM perimetre') == [(0,)]


def test_decision_homonyme_ecarte_survit_aux_reconstructions(jeu, socle, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers[:40], socle)
    a, b = lignes(cx, "SELECT fiche_a, fiche_b FROM c2_correspondance WHERE statut = 'homonymie' ORDER BY 1, 2")[0]
    avant = un(cx, "SELECT count(*) FROM c2_correspondance WHERE statut = 'homonymie'")
    c2.decider(cx, a, b, 'homonyme_ecarte', analyste='essai', justification='test')
    etat = lambda: lignes(cx, 'SELECT DISTINCT statut FROM c2_correspondance WHERE fiche_a = ? AND fiche_b = ?', a, b)  # noqa: E731
    assert etat() == [('ecarte',)]
    c2.construire_tout(cx)
    assert etat() == [('ecarte',)]
    c2.charger_socle(cx, socle)
    c2.construire_tout(cx)
    assert etat() == [('ecarte',)]
    assert un(cx, "SELECT count(*) FROM c2_correspondance WHERE statut = 'homonymie'") < avant
    with pytest.raises(ValueError):
        c2.decider(cx, a, b, 'autre_chose')


def test_decisions_du_kit_reprises(jeu, tmp_path):
    kit = mini_socle(tmp_path, entites=[dict(entite_id=1, cle_entite='P#1', type_entite='PP',
                                             nom_affiche='ZELMOU BAKRITA', statut='actif')],
                     societes=[dict(societe_id=1, cle_societe='RC:70001@KENITRA', denomination='TAZOULA SARL',
                                    rc_num='70001', tribunal_code='KENITRA')],
                     personnes=[dict(personne_id=1, cle_stable='RC:70001@KENITRA|N:ZELMOUBAKRITA', societe_id=1,
                                     type_personne='PP', nom_complet='ZELMOU BAKRITA', ecriture='latin',
                                     cin_statut='absent', role='gerant')],
                     correspondances=[dict(bl_entite_id=1, rc_objet='rc_personne', rc_objet_id=1, societe_id=1,
                                           nature='identite', regle='R07', niveau='probable', statut='homonymie')],
                     decisions=[dict(cle_bl='P#1', rc_objet='rc_personne', cle_rc='RC:70001@KENITRA|N:ZELMOUBAKRITA',
                                     decision='homonyme_ecarte', analyste='essai')])
    cx = base_de(tmp_path, [], kit)
    assert lignes(cx, 'SELECT regle, statut FROM c2_correspondance') == [('R07', 'ecarte')]


# ---- stabilité, flux = lot -----------------------------------------------------------------------------------------

def test_identifiants_stables_d_une_construction_a_l_autre(jeu, socle, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers[:60], socle)
    avant = contenu(cx)
    c2.construire_tout(cx)
    assert contenu(cx) == avant
    c2.charger_socle(cx, socle)
    c2.construire_tout(cx)
    assert contenu(cx) == avant
    autre = base_de(tmp_path, list(reversed(jeu.dossiers[:60])), socle)
    assert contenu(autre) == avant
    assert all(i.startswith(('pp_', 'pm_')) and 'ZZ' not in i for (i,) in lignes(cx, 'SELECT identifiant FROM c2_personne '
                                                                                  'UNION SELECT identifiant FROM c2_societe'))


def test_traiter_chaque_dossier_dans_un_ordre_au_hasard_egale_le_lot(jeu, socle, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers, socle)
    en_lot = contenu(cx)
    refs = [d['ref'] for d in jeu.dossiers]
    random.Random(7).shuffle(refs)
    for ref in refs[:80]:
        c2.traiter(cx, ref)
    assert contenu(cx) == en_lot


def test_flux_version_par_version_egale_le_lot(jeu, socle, tmp_path):
    flux = base_de(tmp_path, [], socle)
    passage = c0.ouvrir_passage(flux, 'essai', 'scrutation', T0)
    for e in jeu.chronologie:
        c0.recevoir(flux, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
        c1.traiter(flux, e['ref'])
        c2.traiter(flux, e['ref'])
    lot = base_de(tmp_path, [], socle, construire=False)
    passage = c0.ouvrir_passage(lot, 'essai', 'lot', T0)
    for e in jeu.chronologie:
        c0.recevoir(lot, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
    c1.construire_tout(lot)
    c2.construire_tout(lot)
    a, b = contenu(flux), contenu(lot)
    for t in TABLES + VUES:
        if t != 'c2_identifiant_attribue':
            assert a[t] == b[t], t
    # un identifiant attribué le reste : le flux garde ceux des versions passées, le lot n'a que ceux d'aujourd'hui
    assert set(b['c2_identifiant_attribue']) < set(a['c2_identifiant_attribue'])


def test_dossier_sorti_du_miroir_ses_fiches_propres_disparaissent(jeu, tmp_path):
    d = dossier(jeu, 1, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001'),
                ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'employeur': 'TAZOULA SARL'}))
    cx = base_de(tmp_path, [d, dossier(jeu, 2, cin_de('ZELMOU', 'BAKRITA', 'ZZ100001'))])
    assert lignes(cx, 'SELECT nb_mentions FROM c2_personne') == [(3,)] and un(cx, 'SELECT count(*) FROM c2_societe') == 1
    cx.execute('DELETE FROM "Piece" WHERE "dossierId" = ?', (d['id'],))
    cx.execute('DELETE FROM "Dossier" WHERE ref = ?', (d['ref'],))
    c1.traiter(cx, d['ref'])
    c2.traiter(cx, d['ref'])
    assert lignes(cx, 'SELECT nb_mentions FROM c2_personne') == [(1,)] and un(cx, 'SELECT count(*) FROM c2_societe') == 0
    assert un(cx, 'SELECT count(*) FROM c2_identifiant_attribue') == 2          # un identifiant attribué reste attribué


def test_sans_socle_la_couche_se_construit(jeu, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers[:20])
    assert un(cx, 'SELECT count(*) FROM c2_personne') > 0 and un(cx, 'SELECT count(*) FROM ref_liste_noire') == 0


# ---- survie des attributs, employeurs ------------------------------------------------------------------------------

def test_adresse_qui_fait_foi_releve_avant_cin(jeu, tmp_path):
    d = dossier(jeu, 1, ('CIN', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': 'ZZ100001', 'adresse': '1 RUE TAZOULA'}),
                ('RELEVE_BANCAIRE', {'titulaire_compte': 'ZELMOU BAKRITA', 'adresse': '9 RUE ZIRMAK'}))
    cx = base_de(tmp_path, [d])
    assert lignes(cx, 'SELECT adresse, date_naissance FROM c2_personne') == [('9 RUE ZIRMAK', None)]
    assert un(cx, 'SELECT count(*) FROM c2_adresse') == 2
    assert un(cx, "SELECT count(*) FROM ref_regle_survie WHERE attribut = 'adresse'") >= 3


def test_employeurs_selon_le_referentiel_de_kamal_ice_et_graphies(jeu, tmp_path):
    emploi = lambda nom: ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA',  # noqa: E731
                                                          'employeur': {'raison_sociale': nom, 'ice': '999000000000015'}})
    cx = base_de(tmp_path, [dossier(jeu, 1, emploi('TAZOULA SARL')), dossier(jeu, 2, emploi('TAZOULA SARL')),
                            dossier(jeu, 3, emploi('STE TAZOULA'))])
    assert lignes(cx, 'SELECT ice, nom, vus FROM c2_employeur ORDER BY nom') == \
        [('999000000000015', 'STE TAZOULA', 1), ('999000000000015', 'TAZOULA SARL', 2)]
    assert un(cx, 'SELECT count(*) FROM c2_societe') == 1
    assert lignes(cx, 'SELECT DISTINCT regle FROM c2_mention WHERE type_fiche = ?', 'PM') == [('ICE',)]


# ---- invariants, ordre des couches ---------------------------------------------------------------------------------

@pytest.mark.parametrize('nom, viol', [
    ('c2_mention_de_c1_absente', "DELETE FROM c2_mention WHERE id = (SELECT min(id) FROM c2_mention WHERE source = 'v2')"),
    ('c2_mention_v2_sans_c1', 'DELETE FROM c1_mention_societe ; DELETE FROM c1_mention_personne'),
    ('c2_rapprochement_certain_non_fusionne', "UPDATE c2_correspondance_mention SET niveau = 'certain', nature = "
                                              "'identite' WHERE regle = 'R07'"),
    ('c2_inscrit_sans_mention', "UPDATE c2_mention SET cle_origine = 'x:' || cle_origine WHERE source = 'liste_noire'"),
    ('c2_perimetre_non_vide', "INSERT INTO c2_perimetre (mention) VALUES ('m_absente')"),
    ('c2_mention_sans_fiche_en_base', "DELETE FROM c2_personne WHERE identifiant = (SELECT min(identifiant) FROM c2_personne)"),
    ('c2_fiche_sans_mention', "INSERT INTO c2_societe (identifiant, cle_naturelle, inscrit, nb_mentions) VALUES "
                              "('pm_absente', 'V2:absente', 0, 1)"),
    ('c2_fiche_a_plusieurs_cin', "UPDATE c2_mention SET cin = 'ZZ999999' WHERE id = (SELECT min(id) FROM c2_mention "
                                 "WHERE cin IS NOT NULL AND fiche IN (SELECT fiche FROM c2_mention WHERE cin IS NOT "
                                 "NULL GROUP BY fiche HAVING count(*) > 1))"),
    ('c2_identifiant_non_attribue', "DELETE FROM c2_identifiant_attribue"),
])
def test_chaque_invariant_de_c2_devient_rouge_quand_on_le_viole(jeu, socle, tmp_path, capsys, nom, viol):
    cx = base_de(tmp_path, jeu.dossiers[:60], socle)
    cx.commit()
    chemin = cx.execute('PRAGMA database_list').fetchone()[2]
    assert verifier.verifier(chemin) == 0
    cx.executescript(viol)
    cx.commit()
    assert verifier.verifier(chemin) == 1
    sortie = capsys.readouterr().out
    assert f'ÉCART  {nom} : ' in sortie and 'ZZ' not in sortie


def test_la_couche_suit_c1_dans_l_ordre_des_couches():
    from pipeline.couches import COUCHES
    assert [c.nom for c in COUCHES[:3]] == ['c0', 'c1', 'c2']
    assert csv and cb                                                       # modules du kit importables
