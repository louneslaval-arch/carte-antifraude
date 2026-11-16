"""Tests de la couche 5 (étape H) : le graphe (rôles, identifiants partagés, homonymies) et la recherche des chemins
vers la liste noire, avec la force (barème n°23, coût de taille n°21, fiabilité) et le niveau. Tout est fictif."""

import json
import math
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
from pipeline import migrer  # noqa: E402
from pipeline.couches import COUCHES  # noqa: E402
from pipeline.couches import c0_brut as c0  # noqa: E402
from pipeline.couches import c2_identites as c2  # noqa: E402
from pipeline.couches import c5_graphe as c5  # noqa: E402

T0 = '2026-11-13T10:00:00.000Z'
TABLES = ('c5_arete', 'c5_compteur', 'c5_cle_adresse')
APRES_C2 = [c for c in COUCHES if c.nom not in ('c0', 'c1', 'c2')]


# ---- montage -------------------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


@pytest.fixture(scope='module')
def socle(jeu, tmp_path_factory):
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


def base_de(tmp_path, dossiers=(), socle=None, meta=None):
    """Base neuve : dossiers reçus (c0), c1 et c2 en lot, socle chargé, puis les couches du dessus."""
    cx = sqlite3.connect(str(tmp_path / f'base_{len(os.listdir(tmp_path))}.sqlite'))
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai', 'lot', T0)
    for d in dossiers:
        c0.recevoir(cx, passage, d, actif=meta[d['ref']]['actif'] if meta else True, maintenant=T0)
    for couche in COUCHES[1:3]:
        couche.construire_tout(cx)
    if socle:
        c2.charger_socle(cx, socle)
    for couche in APRES_C2:
        couche.construire_tout(cx)
    return cx


@pytest.fixture(scope='module')
def base(jeu, socle, tmp_path_factory):
    cx = base_de(tmp_path_factory.mktemp('c5'), jeu.dossiers, socle, jeu.meta)
    yield cx
    cx.close()


@pytest.fixture
def cx(base):
    return base


def lignes(cx, sql, *p):
    return cx.execute(sql, p).fetchall()


def contenu(cx):
    return {t: sorted(cx.execute(f'SELECT * FROM {t}').fetchall(), key=repr) for t in TABLES}


def meilleur(cx, ref):
    chemins = c5.chemins(cx, ref)
    return chemins[0] if chemins else None


def dossier(jeu, n, *pieces, **entete):
    d = json.loads(json.dumps(jeu.dossiers[0]))
    modele = d['pieces'][0]
    d.update(ref=f'ZZ26T{n:04d}', id=str(uuid.uuid5(uuid.NAMESPACE_OID, f'essai-c5-{n}')), analyses=[],
             latestAnalysis=None, reanalyses=[])
    d['businessData'] = dict(d['businessData'], dossier_ref=d['ref'],
                             civil=dict(full_name='ZELMOU BAKRITA', cin=f'ZZ1{n:05d}', address=None),
                             declared=dict(employer=None, monthly_income=None, pension_organism=None))
    d.update(entete)
    d['pieces'] = [dict(modele, type=t, upstreamPieceId=f'eqdom_{t}_{k}', fields=f) for k, (t, f) in enumerate(pieces)]
    return d


# ---- coût de taille et niveaux -------------------------------------------------------------------------------------

@pytest.mark.parametrize('n, attendu', [(1, 1.0), (2, 1.0), (3, 0.82), (5, 0.63), (8, 0.50), (40, 0.22), (500, 0.06)])
def test_table_des_couts(n, attendu):
    assert round(c5.cout(n), 2) == attendu


def test_exemples_de_reference_et_niveaux(cx):
    p = c5.parametres(cx)
    assert round(0.7 * c5.cout(8) * 0.7, 3) == 0.245 and c5.niveau(p, 2, 0.245) == 'majeure'
    assert round(0.5 * c5.cout(40) * 0.5, 4) == 0.0559 and c5.niveau(p, 2, 0.0559) == 'affiche'
    assert [c5.niveau(p, 0, 1.0), c5.niveau(p, 1, 0.19), c5.niveau(p, 3, 0.9), c5.niveau(p, 3, 0.07),
            c5.niveau(p, 4, 0.9), c5.niveau(p, 2, 0.04), c5.niveau(p, 0, 0.5, plafond='mineure'),
            c5.niveau(p, 1, 0.9, plafond='mineure')] == \
        ['critique', 'mineure', 'mineure', 'affiche', 'hors_alerte', None, 'mineure', 'mineure']


def test_parametres_et_bareme_lus_dans_c6_version_parametres(cx):
    noms = {n for (n,) in lignes(cx, "SELECT nom FROM parametre WHERE nom LIKE 'c5_%'")}
    assert {'c5_seuil_majeure', 'c5_seuil_mineure', 'c5_seuil_affichage', 'c5_longueur_alerte',
            'c5_longueur_recherche', 'c5_poids_gerant', 'c5_poids_liquidateur', 'c5_poids_employe',
            'c5_poids_meme_rib', 'c5_poids_meme_logement', 'c5_poids_foyer', 'c5_fiabilite_homonymie'} <= noms
    assert lignes(cx, "SELECT valeur, provisoire FROM parametre WHERE nom = 'c5_seuil_majeure'") == [(0.2, 1)]


# ---- scénarios du générateur ---------------------------------------------------------------------------------------

def attendus(jeu, codes):
    return [v for v in jeu.verite if set(v['scenarios']) & set(codes) and v['chemin']]


@pytest.mark.parametrize('code', ['S04', 'S05', 'S06', 'S07', 'S08', 'S09', 'S10', 'S13', 'S14', 'S15', 'S16', 'S20'])
def test_scenario_force_longueur_et_niveau_attendus(cx, jeu, code):
    p = c5.parametres(cx)
    cas = attendus(jeu, [code])
    assert cas
    for v in cas:
        m = meilleur(cx, v['ref'])
        assert m is not None, v['ref']
        assert m['longueur'] == len(v['chemin']), (v['ref'], m)
        assert math.isclose(m['force'], v['force'], abs_tol=0.002), (v['ref'], m)
        attendu = v['niveau'] if v['niveau'] not in ('calcul', None) else c5.niveau(p, len(v['chemin']), v['force'])
        attendu = {'affiché': 'affiche', 'hors alerte': 'hors_alerte'}.get(attendu, attendu)
        if code == 'S13':
            attendu = 'mineure'                         # même foyer qu'un inscrit : jamais plus que mineure
        assert m['niveau'] == attendu, (v['ref'], m)


def test_S01_a_S03_zero_lien_critique(cx, jeu):
    for v in jeu.verite:
        if set(v['scenarios']) & {'S01', 'S02', 'S03'}:
            m = meilleur(cx, v['ref'])
            assert m and m['longueur'] == 0 and m['niveau'] == 'critique' and m['force'] == 1.0, v['ref']


def test_S11_homonymie_a_un_bout_plafonnee_a_mineure_puis_levee(cx, jeu):
    ref = attendus(jeu, ['S11'])[0]['ref']
    m = meilleur(cx, ref)
    assert m['niveau'] == 'mineure' and m['homonymie'] and m['longueur'] == 1
    homonymie = next(e for e in m['etapes'] if e['type'] == 'homonymie')
    c2.decider(cx, homonymie['de'], homonymie['vers'], 'meme_personne', analyste='essai')
    m = meilleur(cx, ref)
    assert m['niveau'] == 'majeure' and not m['homonymie']
    c2.decider(cx, homonymie['de'], homonymie['vers'], 'homonyme_ecarte', analyste='essai')
    assert all(not any(e['type'] == 'homonymie' and {e['de'], e['vers']} == {homonymie['de'], homonymie['vers']}
                       for e in ch['etapes']) for ch in c5.chemins(cx, ref))


def test_S12_employeur_reconnu_par_son_seul_nom_mineure_au_plus(cx, jeu):
    ref = next(v['ref'] for v in jeu.verite if 'S12' in v['scenarios'])
    m = meilleur(cx, ref)
    assert m and m['homonymie'] and m['longueur'] == 0 and m['niveau'] == 'mineure'


def test_S18_meme_chassis_n_est_pas_un_lien(cx, jeu):
    a, b = [v['ref'] for v in jeu.verite if 'S18' in v['scenarios']]
    assert lignes(cx, "SELECT count(*) FROM c5_arete WHERE code = 'CHASSIS'") == [(0,)]
    assert all(e['code'] != 'CHASSIS' for r in (a, b) for ch in c5.chemins(cx, r) for e in ch['etapes'])


def test_dossier_sans_lien_aucun_chemin(cx, jeu):
    sans = [v['ref'] for v in jeu.verite if not v['scenarios'] and not v['pieges']][:20]
    assert sans and all(c5.chemins(cx, r) == [] for r in sans)


def test_chemin_detaille_sans_aucune_valeur_d_identite(cx, jeu):
    import re
    assert [e['code'] for e in meilleur(cx, attendus(jeu, ['S07'])[0]['ref'])['etapes']] == ['gerant', 'gerant']
    k = c5.Contexte(cx)
    valeurs = {v for (v,) in lignes(cx, 'SELECT valeur FROM c1_identifiant_brut UNION SELECT cle FROM c5_cle_adresse')}
    fiche = re.compile(r'(pp|pm)_[0-9a-f]{16}')
    vus = {'role': 0, 'identifiant': 0, 'homonymie': 0}
    for d in jeu.dossiers:
        for ch in c5.chemins(cx, d['ref'], k):
            assert set(ch) == {'cible', 'longueur', 'force', 'niveau', 'homonymie', 'foyer', 'etapes'}
            assert fiche.fullmatch(ch['cible'])
            for e in ch['etapes']:
                assert set(e) == {'type', 'code', 'de', 'vers'} and fiche.fullmatch(e['de']) and fiche.fullmatch(e['vers'])
                vus[e['type']] += 1
            texte = json.dumps(ch, ensure_ascii=False)
            assert 'ZZ' not in texte and not any(x in texte for x in ('RIB:', 'LOGEMENT:', 'SIEGE:'))
            assert not any(v in texte for v in valeurs if v and len(v) >= 6)
    assert all(vus.values())                                # des chemins par rôle, par identifiant et par homonymie


def test_cles_d_arete_et_noeuds_d_identifiant_sans_valeur_en_clair(cx):
    valeurs = {v for (v,) in lignes(cx, "SELECT valeur FROM c1_identifiant_brut WHERE type = 'RIB'")}
    adresses = {v for (v,) in lignes(cx, 'SELECT cle FROM c5_cle_adresse')}
    for cle, vers in lignes(cx, "SELECT cle, vers FROM c5_arete WHERE type = 'identifiant'"):
        assert not any(v in cle or v in vers for v in valeurs | adresses)
    assert not any(v in n for (n,) in lignes(cx, 'SELECT noeud FROM c5_compteur') for v in valeurs | adresses)


# ---- petit graphe fait à la main -----------------------------------------------------------------------------------

def test_quatre_liens_trouves_mais_hors_alerte_et_borne_de_recherche_parametree(cx, jeu):
    ref = attendus(jeu, ['S10'])[0]['ref']
    assert meilleur(cx, ref)['niveau'] == 'hors_alerte'
    cx.execute("INSERT INTO c6_version_parametres (version, nom, valeur, provisoire) VALUES ('2099-01-01', "
               "'c5_longueur_recherche', 3, 1)")
    try:
        assert c5.chemins(cx, ref) == []
    finally:
        cx.execute("DELETE FROM c6_version_parametres WHERE version = '2099-01-01'")


def test_cout_lu_dans_le_compteur_au_moment_du_calcul(jeu, socle, tmp_path):
    v = attendus(jeu, ['S05'])
    inscrit = next(x['ref'] for x in jeu.verite if 'S05' in x['scenarios'] and not x['chemin'])
    lie = v[0]['ref']
    dossiers = [d for d in jeu.dossiers if d['ref'] in (inscrit, lie)]
    rib = next(p['fields']['rib'] for d in dossiers for p in d['pieces'] if p['type'] == 'RELEVE_BANCAIRE')
    autres = [dossier(jeu, n, ('CIN', {'nom': 'TAGHRIZ', 'prenom': f'NADOUL{chr(64 + n)}', 'cin': f'ZZ1{n:05d}'}),
                      ('RELEVE_BANCAIRE', {'titulaire_compte': f'TAGHRIZ NADOUL{chr(64 + n)}', 'rib': rib}))
              for n in (1, 2, 3)]
    cx = base_de(tmp_path, dossiers, socle)
    assert math.isclose(meilleur(cx, lie)['force'], 0.9, abs_tol=1e-6)
    passage = c0.ouvrir_passage(cx, 'essai', 'scrutation', T0)
    for d in autres:                                     # trois porteurs de plus : n = 5
        c0.recevoir(cx, passage, d, maintenant=T0)
        for couche in COUCHES[1:]:
            couche.traiter(cx, d['ref'])
    assert math.isclose(meilleur(cx, lie)['force'], 0.9 * math.sqrt(2 / 5), abs_tol=1e-6)
    assert lignes(cx, "SELECT n FROM c5_compteur WHERE noeud = ?", c5.noeud_identifiant('RIB', rib)) == [(5,)]


def test_foyer_meme_nom_meme_logement_poids_reduit_et_plafond(jeu, tmp_path):
    kit_inscrit = None
    adresse = '12 Avenue Tazoula, Appartement 3, Casablanca'
    a = dossier(jeu, 1, ('CIN', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': 'ZZ100001', 'adresse': adresse}),
                ('DOMICILIATION', {'titulaire': 'ZELMOU BAKRITA', 'adresse': adresse}))
    b = dossier(jeu, 2, ('CIN', {'nom': 'ZELMOU', 'prenom': 'NADOUL', 'cin': 'ZZ100002', 'adresse': adresse}),
                ('DOMICILIATION', {'titulaire': 'ZELMOU NADOUL', 'adresse': adresse}))
    c = dossier(jeu, 3, ('CIN', {'nom': 'TAGHRIZ', 'prenom': 'LOUMIZA', 'cin': 'ZZ100003', 'adresse': adresse}),
                ('DOMICILIATION', {'titulaire': 'TAGHRIZ LOUMIZA', 'adresse': adresse}))
    cx = base_de(tmp_path, [a, b, c], kit_inscrit)
    cx.execute("UPDATE c2_personne SET inscrit = 1 WHERE cin = 'ZZ100001'")
    foyer, voisin = meilleur(cx, 'ZZ26T0002'), meilleur(cx, 'ZZ26T0003')
    assert foyer['foyer'] and voisin and not voisin['foyer']
    assert math.isclose(foyer['force'], 0.1 * c5.cout(3), abs_tol=1e-6) and foyer['niveau'] == 'mineure'
    assert math.isclose(voisin['force'], 0.5 * c5.cout(3), abs_tol=1e-6) and voisin['niveau'] == 'majeure'


class GrapheFait(c5.Contexte):
    """Petit graphe fait à la main : {nœud: [(voisin, type, code, poids)]}, tailles et inscrits donnés."""

    def __init__(self, cx, aretes, tailles, inscrits):
        self.cx, self.p, self.inscrits, self._t = cx, c5.parametres(cx), set(inscrits), tailles
        self._a = {}
        for a, b, type_, code, poids in aretes:
            for x, y in ((a, b), (b, a)):
                self._a.setdefault(x, []).append((y, type_, code, poids))

    def n(self, noeud):
        return self._t.get(noeud, 1)

    def liens(self, u):
        sortie = []
        for voisin, type_, code, poids in sorted(self._a.get(u, ())):
            homonymie = type_ == 'homonymie'
            sortie.append((voisin, 0 if homonymie else 1, poids, dict(type=type_, code=code, de=u, vers=voisin),
                           'mineure' if homonymie else None, False, None))
        return sortie


def pp(n):
    return f'pp_{n:016x}'


def test_homonymie_au_milieu_n_agit_que_sur_la_force(cx):
    # départ –gérant– A ≈ B (homonymie) –gérant– inscrit : 2 liens, 0,7 × 0,9 × 0,7 = 0,441, majeure
    k = GrapheFait(cx, [(pp(1), pp(2), 'role', 'gerant', 0.7), (pp(2), pp(3), 'homonymie', 'R07', 0.9),
                        (pp(3), pp(4), 'role', 'gerant', 0.7)], {}, [pp(4)])
    (m,) = c5.chercher(k, [pp(1)])
    assert (m['longueur'], round(m['force'], 3), m['niveau'], m['homonymie']) == (2, 0.441, 'majeure', False)


def test_homonymie_au_bout_plafonne_et_ne_coute_pas_la_taille_du_presume_inscrit(cx):
    # départ –gérant– A (8 sociétés) ≈ inscrit : A est l'inscrit présumé, un bout : pas de coût de taille
    k = GrapheFait(cx, [(pp(1), pp(2), 'role', 'gerant', 0.7), (pp(2), pp(3), 'homonymie', 'R07', 0.5)],
                   {pp(2): 8}, [pp(3)])
    (m,) = c5.chercher(k, [pp(1)])
    assert (m['longueur'], round(m['force'], 3), m['niveau'], m['homonymie']) == (1, 0.35, 'mineure', True)
    # le départ lui-même rapproché d'une fiche du registre : celle-ci vaut le départ, sans coût
    k = GrapheFait(cx, [(pp(1), pp(2), 'homonymie', 'AF07', 0.5), (pp(2), pp(3), 'role', 'gerant', 0.7)],
                   {pp(2): 8}, [pp(3)])
    (m,) = c5.chercher(k, [pp(1)])
    assert (m['longueur'], round(m['force'], 3), m['niveau'], m['homonymie']) == (1, 0.35, 'mineure', True)


def test_cout_jamais_aux_deux_bouts_mais_au_milieu(cx):
    k = GrapheFait(cx, [(pp(1), pp(2), 'role', 'gerant', 0.7), (pp(2), pp(3), 'role', 'gerant', 0.7)],
                   {pp(1): 40, pp(2): 8, pp(3): 500}, [pp(3)])
    (m,) = c5.chercher(k, [pp(1)])
    assert round(m['force'], 3) == 0.245


def test_role_sans_poids_au_bareme_vaut_le_poids_inconnu(cx):
    assert c5.poids_role(c5.parametres(cx), 'role_jamais_vu') == c5.parametres(cx)['c5_poids_inconnu']


# ---- flux = lot, propriétés, invariants ----------------------------------------------------------------------------

def test_flux_dans_un_ordre_au_hasard_egale_le_lot(jeu, socle, tmp_path):
    lot = base_de(tmp_path, jeu.dossiers, socle, jeu.meta)
    flux = base_de(tmp_path, [], socle)
    dossiers = list(jeu.dossiers)
    random.Random(9).shuffle(dossiers)
    passage = c0.ouvrir_passage(flux, 'essai', 'scrutation', T0)
    for d in dossiers:
        c0.recevoir(flux, passage, d, actif=jeu.meta[d['ref']]['actif'], maintenant=T0)
        for couche in COUCHES[1:]:
            couche.traiter(flux, d['ref'])
    a, b = contenu(flux), contenu(lot)
    for t in TABLES:
        assert a[t] == b[t], t
    for ref in [d['ref'] for d in jeu.dossiers]:
        assert c5.chemins(flux, ref) == c5.chemins(lot, ref), ref


def test_flux_version_par_version_egale_le_lot(jeu, socle, tmp_path):
    flux = base_de(tmp_path, [], socle)
    lot = base_de(tmp_path, [], socle)
    for cx_, au_fil in ((flux, True), (lot, False)):
        passage = c0.ouvrir_passage(cx_, 'essai', 'scrutation', T0)
        for e in jeu.chronologie:
            c0.recevoir(cx_, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
            for couche in COUCHES[1:] if au_fil else ():
                couche.traiter(cx_, e['ref'])
    for couche in COUCHES[1:]:
        couche.construire_tout(lot)
    a, b = contenu(flux), contenu(lot)
    for t in TABLES:
        assert a[t] == b[t], t


def test_ajouter_puis_retirer_un_dossier_rend_le_graphe_identique(jeu, socle, tmp_path):
    cx = base_de(tmp_path, jeu.dossiers, socle, jeu.meta)
    avant = contenu(cx)
    d = dossier(jeu, 9, ('CIN', {'nom': 'ZELMOU', 'prenom': 'BAKRITA', 'cin': 'ZZ100009'}),
                ('RELEVE_BANCAIRE', {'titulaire_compte': 'ZELMOU BAKRITA', 'rib': jeu.dossiers[0]['pieces'][-1]
                                     ['fields'].get('rib', '999' + '7' * 21)}),
                ('ATTESTATION_TRAVAIL_SALAIRE', {'nom': 'ZELMOU', 'prenom': 'BAKRITA',
                                                 'employeur': {'raison_sociale': 'TAZOULA SARL', 'ice': '999000000000015'}}))
    c0.recevoir(cx, c0.ouvrir_passage(cx, 'essai', 'scrutation', T0), d, maintenant=T0)
    for couche in COUCHES[1:]:
        couche.traiter(cx, d['ref'])
    assert contenu(cx) != avant
    cx.execute('DELETE FROM "Piece" WHERE "dossierId" = ?', (d['id'],))
    cx.execute('DELETE FROM "Dossier" WHERE ref = ?', (d['ref'],))
    for couche in COUCHES[1:]:
        couche.traiter(cx, d['ref'])
    assert contenu(cx) == avant


@pytest.mark.parametrize('nom, viol', [
    ('c5_arete_mention_absente', "UPDATE c5_arete SET mention = 'm_absente' WHERE rowid = (SELECT min(rowid) FROM c5_arete)"),
    ('c5_arete_fiche_perimee', "UPDATE c5_arete SET de = 'pp_absente' WHERE rowid = (SELECT min(rowid) FROM c5_arete)"),
    ('c5_compteur_faux', "UPDATE c5_compteur SET n = n + 1 WHERE rowid = (SELECT min(rowid) FROM c5_compteur)"),
    ('c5_mention_sans_arete', "DELETE FROM c5_arete WHERE type = 'role' AND rowid = (SELECT min(rowid) FROM c5_arete "
                              "WHERE type = 'role')"),
])
def test_chaque_invariant_de_c5_devient_rouge_quand_on_le_viole(jeu, socle, tmp_path, capsys, nom, viol):
    cx = base_de(tmp_path, jeu.dossiers[:40], socle, jeu.meta)
    cx.commit()
    chemin = cx.execute('PRAGMA database_list').fetchone()[2]
    assert verifier.verifier(chemin) == 0
    cx.executescript(viol)
    cx.commit()
    assert verifier.verifier(chemin) == 1
    sortie = capsys.readouterr().out
    assert f'ÉCART  {nom} : ' in sortie and 'ZZ' not in sortie


def test_la_couche_suit_c3_dans_l_ordre_des_couches():
    assert [c.nom for c in COUCHES[:5]] == ['c0', 'c1', 'c2', 'c3', 'c5']
