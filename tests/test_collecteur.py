"""Tests du collecteur en scrutation et de sa file (étape D.4), branchés sur le serveur v2 fictif :
rien perdu, rien doublé, reprises à intervalle croissant, journaux sans contenu de dossier."""

import datetime
import logging
import os
import sqlite3
import sys

import httpx
import pytest
from starlette.testclient import TestClient

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURE = os.path.join(RACINE, 'import', 'kamal_structure')
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(STRUCTURE, 'reference', 'champs_par_type_prod.csv')),
                                reason='structure de Kamal absente')

import generer_dossiers as gd  # noqa: E402
import serveur_v2  # noqa: E402
from flux import collecteur, file  # noqa: E402
from pipeline import migrer  # noqa: E402

FIN = datetime.datetime(2027, 1, 1)
COMPTE, SECRET = 'analyste@exemple.invalid', 'mot-de-passe-fictif'


@pytest.fixture(scope='module')
def jeu():
    return gd.generer(n_dossiers=320, n_societes=300, graine=20261113)


class Client:
    """Client du serveur fictif qui compte les appels et peut simuler une panne ou modifier une réponse."""

    def __init__(self, appli):
        self.vrai = TestClient(appli)
        self.appels = []
        self.parametres = []
        self.panne = None             # None, 'reseau', ou un code HTTP
        self.panne_detail = set()     # références dont le détail répond 503
        self.modifier_detail = None
        self.refuser_jeton_une_fois = False

    def _appel(self, methode, url, **k):
        self.appels.append((methode, url.split('?')[0]))
        self.parametres.append(k.get('params') or {})
        if self.panne == 'reseau':
            raise httpx.ConnectError('connexion refusée')
        if self.panne:
            return httpx.Response(self.panne, json={'error': 'indisponible'})
        if self.refuser_jeton_une_fois and 'login' not in url:
            self.refuser_jeton_une_fois = False
            return httpx.Response(401, json={'error': 'unauthorized'})
        if methode == 'GET' and url.rsplit('/', 1)[-1] in self.panne_detail:
            return httpx.Response(503, json={'error': 'indisponible'})
        r = getattr(self.vrai, methode.lower())(url, **k)
        if self.modifier_detail and methode == 'GET' and url.startswith('/api/dossiers/') and r.status_code == 200:
            return httpx.Response(200, json=self.modifier_detail(r.json()))
        return r

    def get(self, url, **k):
        return self._appel('GET', url, **k)

    def post(self, url, **k):
        return self._appel('POST', url, **k)

    def compte(self, methode, fin):
        return sum(1 for m, u in self.appels if m == methode and u.endswith(fin))

    def details(self):
        return sum(1 for m, u in self.appels if m == 'GET' and u.startswith('/api/dossiers/'))


@pytest.fixture
def monde(jeu, tmp_path):
    def fabriquer(tri='createdAt'):
        appli = serveur_v2.creer_application(jeu, secret='x', tri=tri)
        appli.state.horloge.regler(FIN)
        client = Client(appli)
        cx = sqlite3.connect(str(tmp_path / f'base_{tri}.sqlite'))
        cx.execute('PRAGMA foreign_keys = ON')
        migrer.appliquer(cx)
        heure = [datetime.datetime(2026, 11, 13, 9, 0, 0)]
        c = collecteur.Collecteur(cx, client, compte=COMPTE, secret=SECRET, horloge=lambda: heure[0])
        return appli, client, cx, c, heure
    return fabriquer


def un(cx, sql, *p):
    return cx.execute(sql, p).fetchone()[0]


def avancer(heure, **duree):
    heure[0] += datetime.timedelta(**duree)


# ---- scénario complet ----------------------------------------------------------------------------------------------

def test_scenario_complet_sans_perte_ni_doublon(monde, jeu):
    _, client, cx, c, heure = monde()
    bilan = c.passer()
    assert bilan['versions_nouvelles'] == len(jeu.dossiers) == un(cx, 'SELECT count(*) FROM c0_dossier_brut')
    assert un(cx, 'SELECT count(DISTINCT ref) FROM c0_dossier_brut') == len(jeu.dossiers)
    assert un(cx, 'SELECT count(*) FROM "Dossier"') == len(jeu.dossiers)
    assert un(cx, "SELECT count(*) FROM flux_travail WHERE etat <> 'fait'") == 0
    details = client.details()
    avancer(heure, minutes=10)
    bilan = c.passer()
    assert bilan['versions_nouvelles'] == 0 and client.details() == details      # rien de changé : aucun détail relu
    assert un(cx, 'SELECT count(*) FROM c0_dossier_brut') == len(jeu.dossiers)
    assert un(cx, 'SELECT count(*) FROM c0_export') == 2


def test_dossier_archive_repris_et_marque_analyse_en_cours_stockee(monde, jeu):
    _, _, cx, c, _ = monde()
    c.passer()
    archives = {r for r, m in jeu.meta.items() if not m['actif']}
    assert {r[0] for r in cx.execute('SELECT ref FROM "Dossier" WHERE actif = 0')} == archives and archives
    en_cours = {d['ref'] for d in jeu.dossiers if d['analysisStatus'] == 'EN_COURS'}
    assert {r[0] for r in cx.execute('SELECT ref FROM "Dossier" WHERE "analysisStatus" = \'EN_COURS\'')} == en_cours


def test_au_fil_de_l_eau_chaque_version_est_gardee(monde, jeu):
    appli, _, cx, c, heure = monde()
    ref = next(v['ref'] for v in jeu.verite if 'S17' in v['scenarios'])
    instants = [datetime.datetime.strptime(e['instant'], serveur_v2.FORMAT) for e in jeu.chronologie if e['ref'] == ref]
    for instant in (instants[0], instants[1], FIN):
        appli.state.horloge.regler(instant)
        avancer(heure, minutes=10)
        c.passer()
    assert un(cx, 'SELECT count(*) FROM c0_dossier_brut WHERE ref = ?', ref) == 2
    assert un(cx, 'SELECT count(*) FROM "Dossier" WHERE ref = ?', ref) == 1
    assert un(cx, 'SELECT count(DISTINCT ref) FROM c0_dossier_brut') == len(jeu.dossiers)
    assert un(cx, 'SELECT count(*) FROM (SELECT ref, empreinte FROM c0_dossier_brut GROUP BY ref, empreinte '
                  'HAVING count(*) > 1)') == 0


# ---- pannes --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('panne', ['reseau', 503])
def test_serveur_coupe_nouvelles_tentatives_a_intervalle_croissant_aucune_perte(monde, jeu, panne):
    _, client, cx, c, heure = monde()
    client.panne = panne
    delais = []
    for _ in range(3):
        bilan = c.passer()
        assert bilan['echec'] and bilan['versions_nouvelles'] == 0
        prochaine = datetime.datetime.strptime(un(cx, 'SELECT prochaine_scrutation FROM flux_curseur'), collecteur.FORMAT)
        delais.append((prochaine - heure[0]).total_seconds())
        assert c.passer().get('saute')                       # trop tôt : aucun appel
        heure[0] = prochaine
    assert delais[0] < delais[1] < delais[2] and un(cx, 'SELECT echecs FROM flux_curseur') == 3
    client.panne = None
    assert c.passer()['versions_nouvelles'] == len(jeu.dossiers)
    assert un(cx, 'SELECT echecs FROM flux_curseur') == 0


def test_detail_en_echec_reessaye_plus_tard_les_autres_passent(monde, jeu):
    _, client, cx, c, heure = monde()
    ref = jeu.dossiers[3]['ref']
    client.panne_detail = {ref}
    assert c.passer()['versions_nouvelles'] == len(jeu.dossiers) - 1
    etat, essais, code = cx.execute('SELECT etat, essais, code_erreur FROM flux_travail WHERE ref = ?', (ref,)).fetchone()
    assert (etat, essais, code) == ('erreur', 1, 'http_503')
    client.panne_detail = set()
    avancer(heure, seconds=30)
    assert c.passer()['versions_nouvelles'] == 0             # trop tôt pour ce dossier
    avancer(heure, minutes=10)
    assert c.passer()['versions_nouvelles'] == 1
    assert un(cx, 'SELECT count(DISTINCT ref) FROM c0_dossier_brut') == len(jeu.dossiers)


def test_jeton_refuse_nouvelle_connexion(monde, jeu):
    _, client, _, c, heure = monde()
    c.passer()
    avancer(heure, minutes=10)
    client.refuser_jeton_une_fois = True
    assert not c.passer().get('echec') and client.compte('POST', '/api/auth/login') == 2


def test_compte_refuse_est_un_echec_sans_boucle(monde):
    _, client, _, _, heure = monde()
    cx = sqlite3.connect(':memory:')
    migrer.appliquer(cx)
    c = collecteur.Collecteur(cx, client, compte=COMPTE, secret='faux', horloge=lambda: heure[0])
    assert c.passer()['echec'] == 'connexion_refusee' and client.compte('POST', '/api/auth/login') == 1


# ---- liste triée ou non --------------------------------------------------------------------------------------------

def test_liste_non_triee_relecture_complete_toutes_les_cinq_minutes(monde, jeu):
    _, client, cx, c, heure = monde(tri='createdAt')         # tri par création : pas un tri par mise à jour
    c.passer()
    assert un(cx, 'SELECT liste_triee FROM flux_source') == 0
    listes = client.compte('GET', '/api/dossiers')
    avancer(heure, minutes=2)
    assert c.passer().get('liste') == 'attente' and client.compte('GET', '/api/dossiers') == listes
    avancer(heure, minutes=4)
    c.passer()
    assert client.compte('GET', '/api/dossiers') == 2 * listes


def test_liste_triee_par_mise_a_jour_une_page_suffit(monde, jeu):
    _, client, cx, c, heure = monde(tri='updatedAt')
    c.passer()
    assert un(cx, 'SELECT liste_triee FROM flux_source') == 1
    complet = client.compte('GET', '/api/dossiers')
    avancer(heure, minutes=2)
    bilan = c.passer()
    assert bilan['versions_nouvelles'] == 0
    assert client.compte('GET', '/api/dossiers') - complet < complet      # pas de relecture complète


# ---- tolérance et discrétion ---------------------------------------------------------------------------------------

def test_champ_inconnu_tolere_et_compte(monde, jeu):
    _, client, cx, c, _ = monde()
    client.modifier_detail = lambda d: dict(d, actif=True)            # le README de Kamal cite ce champ, ses types non
    bilan = c.passer()
    assert bilan['versions_nouvelles'] == len(jeu.dossiers) == bilan['hors_modele']
    assert un(cx, 'SELECT count(*) FROM "Dossier"') == len(jeu.dossiers)


def test_journaux_techniques_sans_contenu_de_dossier(monde, jeu, caplog):
    _, client, _, c, heure = monde()
    client.panne_detail = {jeu.dossiers[0]['ref']}
    with caplog.at_level(logging.DEBUG):
        c.passer()
        avancer(heure, minutes=10)
        c.passer()
    texte = caplog.text
    assert texte and 'ZZ' not in texte
    for d in jeu.dossiers[:50]:
        assert d['clientName'] not in texte


def test_etat_de_la_file_en_comptages(monde, jeu):
    _, client, cx, c, _ = monde()
    client.panne_detail = {jeu.dossiers[0]['ref']}
    c.passer()
    assert file.etat(cx) == {'fait': len(jeu.dossiers) - 1, 'erreur': 1}


# ---- états de la file (règles du temps réel) -----------------------------------------------------------------------

def test_travail_bloque_apres_cinq_echecs_visible_et_jamais_efface(monde, jeu):
    _, client, cx, c, heure = monde()
    ref = jeu.dossiers[3]['ref']
    client.panne_detail = {ref}
    for _ in range(5):
        c.passer()
        avancer(heure, hours=2)
    etat, essais = cx.execute('SELECT etat, essais FROM flux_travail WHERE ref = ?', (ref,)).fetchone()
    assert (etat, essais) == ('bloque', 5)
    details = client.details()
    c.passer()
    assert client.details() == details and file.etat(cx)['bloque'] == 1      # plus retenté, toujours visible
    file.debloquer(cx, 'v2', ref)
    client.panne_detail = set()
    avancer(heure, hours=2)
    assert c.passer()['versions_nouvelles'] == 1


def test_version_plus_recente_fait_sauter_l_ancienne_encore_en_attente(monde):
    _, _, cx, c, heure = monde()
    assert file.annoncer(cx, 'v2', 'ZZ26R9001', '2026-09-01T08:00:00.000Z', True, heure[0])
    assert file.annoncer(cx, 'v2', 'ZZ26R9001', '2026-09-02T08:00:00.000Z', True, heure[0])
    assert not file.annoncer(cx, 'v2', 'ZZ26R9001', '2026-09-02T08:00:00.000Z', True, heure[0])   # déjà annoncée
    etats = dict(cx.execute('SELECT updated_at, etat || \':\' || coalesce(code_erreur, \'\') FROM flux_travail'))
    assert etats == {'2026-09-01T08:00:00.000Z': 'fait:remplace', '2026-09-02T08:00:00.000Z': 'en_attente:'}
    assert [r[1] for r in file.a_prendre(cx, 'v2', heure[0])] == ['ZZ26R9001']


def test_dossier_inconnu_de_la_v2_est_bloque_sans_nouvelle_tentative(monde):
    _, client, cx, c, heure = monde()
    c.passer()
    file.annoncer(cx, 'v2', 'ZZ26R9002', '2026-09-01T08:00:00.000Z', True, heure[0])
    cx.commit()
    avancer(heure, minutes=10)
    c.passer()
    assert cx.execute("SELECT etat, code_erreur FROM flux_travail WHERE ref = 'ZZ26R9002'").fetchone() == \
        ('bloque', 'dossier_inconnu')


def test_invariants_verts_apres_un_scenario_complet_et_rouges_si_le_miroir_derive(monde, jeu, tmp_path, capsys):
    import verifier
    appli, _, cx, c, heure = monde()
    for instant in (datetime.datetime(2026, 9, 3), FIN):
        appli.state.horloge.regler(instant)
        avancer(heure, minutes=10)
        c.passer()
    from pipeline.couches import COUCHES
    for couche in COUCHES[1:]:                    # le traiteur (étape ultérieure) le fera au fil de l'eau
        couche.construire_tout(cx)
    base = str(tmp_path / 'base_createdAt.sqlite')
    assert verifier.verifier(base) == 0
    cx.execute('UPDATE "Dossier" SET "updatedAt" = \'2020-01-01T00:00:00.000Z\' WHERE ref = ?', (jeu.dossiers[0]['ref'],))
    cx.commit()
    assert verifier.verifier(base) == 1
    sortie = capsys.readouterr().out
    assert 'c0_miroir_pas_la_derniere_version : 1' in sortie and 'ZZ' not in sortie


# ---- défauts relevés par les relectures ----------------------------------------------------------------------------

def instant(e):
    return datetime.datetime.strptime(e['instant'], serveur_v2.FORMAT)


def test_dossier_modifie_loin_dans_une_liste_crue_triee_n_est_jamais_perdu(monde, jeu):
    appli, _, cx, c, heure = monde(tri='createdAt')
    relectures = [e for e in jeu.chronologie if e['version'] > 1]
    premier = min(instant(e) for e in relectures) - datetime.timedelta(seconds=1)
    appli.state.horloge.regler(premier)
    c.passer()                                    # aucun dossier modifié : la liste par création a l'air triée
    assert un(cx, 'SELECT liste_triee FROM flux_source') == 1
    deja_la = {e['ref'] for e in jeu.chronologie if e['version'] == 1 and instant(e) <= premier}
    appli.state.horloge.regler(FIN)               # des dossiers anciens sont relus, loin dans la liste
    for _ in range(4):
        avancer(heure, minutes=2)
        c.passer()
    relus = {e['ref'] for e in relectures} & deja_la
    assert relus                                  # des dossiers vus au premier passage, modifiés ensuite
    for ref in relus:
        assert un(cx, 'SELECT count(*) FROM c0_dossier_brut WHERE ref = ?', ref) >= 2
    assert un(cx, 'SELECT liste_triee FROM flux_source') == 0
    assert un(cx, 'SELECT count(DISTINCT ref) FROM c0_dossier_brut') == len(jeu.dossiers)


def test_relecture_complete_au_moins_toutes_les_cinq_minutes_meme_si_la_liste_est_triee(monde, jeu):
    _, client, cx, c, heure = monde(tri='updatedAt')
    c.passer()
    complet = client.compte('GET', '/api/dossiers')
    avancer(heure, minutes=6)
    c.passer()
    assert client.compte('GET', '/api/dossiers') == 2 * complet


def test_la_liste_avec_archives_est_lue_avant_celle_des_actifs(monde):
    _, client, _, c, _ = monde()
    c.passer()
    listes = [p for (m, u), p in zip(client.appels, client.parametres) if u == '/api/dossiers']
    assert listes[0].get('archives') == 'true' and 'archives' not in listes[-1]


def test_dossier_ecarte_annonce_par_notification_reste_ecarte(monde, jeu):
    _, _, cx, c, heure = monde()
    archive = next(d for d in jeu.dossiers if not jeu.meta[d['ref']]['actif'])
    file.annoncer(cx, 'v2', archive['ref'], archive['updatedAt'], None, heure[0])     # état « écarté » inconnu
    cx.commit()
    c.passer()
    assert un(cx, 'SELECT actif FROM "Dossier" WHERE ref = ?', archive['ref']) == 0


def test_version_refusee_par_le_miroir_bloque_le_travail_et_reste_visible(monde, jeu):
    _, client, cx, c, _ = monde()
    cible = jeu.dossiers[5]['ref']
    client.modifier_detail = lambda d: dict(d, verdict='VERDICT_INCONNU') if d['ref'] == cible else d
    bilan = c.passer()
    assert bilan['miroir_refuse'] == 1
    assert cx.execute('SELECT etat, code_erreur FROM flux_travail WHERE ref = ?', (cible,)).fetchone() == \
        ('bloque', 'miroir_refuse')
    assert un(cx, 'SELECT count(*) FROM c0_dossier_brut WHERE ref = ?', cible) == 1     # la version brute est gardée
    assert un(cx, 'SELECT count(*) FROM "Dossier" WHERE ref = ?', cible) == 0


@pytest.mark.parametrize('adresse, admise', [
    ('https://v2.exemple.invalid', True), ('http://127.0.0.1:8720', True), ('http://localhost:8720', True),
    ('http://v2.exemple.invalid', False),                         # en clair vers une autre machine
    ('https://compte:secret@v2.exemple.invalid', False),          # identifiants dans l'adresse
    ('ftp://v2.exemple.invalid', False), ('v2.exemple.invalid', False), ('', False)])
def test_adresse_de_la_v2(adresse, admise):
    assert collecteur.adresse_admise(adresse) is admise


def test_reference_encodee_dans_l_adresse_du_detail(monde):
    _, client, cx, c, heure = monde()
    c.passer()
    file.annoncer(cx, 'v2', 'ZZ/../x?y#z', '2026-09-01T08:00:00.000Z', True, heure[0])
    cx.commit()
    avancer(heure, minutes=10)
    c.passer()
    assert client.appels[-1][1] == '/api/dossiers/ZZ%2F..%2Fx%3Fy%23z'
