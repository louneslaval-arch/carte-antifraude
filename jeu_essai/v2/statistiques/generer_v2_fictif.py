#!/usr/bin/env python3
"""Jeu d'essai du module de statistiques (couche 7) : 600 dossiers fictifs de l'antifraude v2, au format de
`GET /api/dossiers/:ref` (le dossier modèle vient de `generer_dossiers.py`, donc des types de Kamal), dont chaque
attribut est fixé par un plan explicite. La vérité attendue (`pipeline/tests/attendu_statistiques.json`) est comptée
ici, sur le plan lui-même, jamais par le code testé.

Cas couverts : PP et PM ; les trois produits ; les catégories A à D et une catégorie E de 3 dossiers (secret primaire
et secondaire) ; chaque verdict et des dossiers sans verdict ; revenu vérifié de quatre sources (bulletin, attestation,
pension, relevé) et sans source ; revenu déclaré absent ou présent ; dates de naissance hors bornes ; villes connues,
mal écrites, en graphie courte, inconnues ; relevés avec et sans opérations lues ; montants écrits en texte ; sociétés
à associé unique ; contrôles en anomalie, non exécutables et non applicables.

Tout est fictif : CIN et références en « ZZ », RIB et ICE en « 999 », noms tirés de syllabes.

Usage : generer_v2_fictif.py [--base BASE.sqlite] [--attendu FICHIER.json] [--graine N]
  --base     construit la base (couches c0 à c5) à partir des dossiers, pour stats_dossiers.py
  --attendu  écrit la vérité attendue
Sortie console : comptages seulement.
"""
import argparse
import datetime
import json
import os
import random
import sqlite3
import statistics
import sys
import uuid

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path[:0] = [RACINE, os.path.dirname(ICI)]

GRAINE = 20261117
N_DOSSIERS = 600
DEBUT = datetime.date(2026, 10, 13)                  # 28 jours de réception : du 13/10/2026 au 09/11/2026
ATTENDU = os.path.join(RACINE, 'pipeline', 'tests', 'attendu_statistiques.json')   # seul chemin .json admis
BASE_ESSAI = os.path.join(RACINE, 'jeu_essai', 'sortie', 'statistiques_essai.sqlite')
T0 = '2026-11-13T10:00:00.000Z'

PRODUITS = ('DISPO', 'AUTO_CLASSIQUE', 'LOA')
CSP_PP = ('SALARIE_PRIVE', 'FONCTIONNAIRE', 'MILITAIRE', 'EMPLOYE_COMMUNE', 'RETRAITE_PUBLIC', 'PROFESSION_LIBERALE')
CATEGORIE_E = (5, 6, 7)                              # catégorie de 3 dossiers : secret primaire puis secondaire
SOURCES_REVENU = ('bulletin', 'attestation', 'pension', 'releve', 'aucun')
# ville saisie, et ville attendue (canonique) ; l'ordre de priorité est domiciliation, CIN, relevé
VILLES = (('CASABLANCA', None, None, 'CASABLANCA'),          # (domiciliation, CIN, relevé, attendue)
          (None, 'Rabat', None, 'RABAT'),
          (None, '12 RUE EXEMPLE MARRAKCH', None, 'MARRAKECH'),
          (None, None, '7 AVENUE EXEMPLE TANGER', 'TANGER'),
          (None, 'ZOUKAVILLE', None, None),
          ('FES', 'AGADIR', None, 'FES'),
          (None, 'CASA', None, 'CASABLANCA'))
REGION = {'CASABLANCA': 'Casablanca-Settat', 'RABAT': 'Rabat-Salé-Kénitra', 'MARRAKECH': 'Marrakech-Safi',
          'TANGER': 'Tanger-Tétouan-Al Hoceïma', 'FES': 'Fès-Meknès',
          'TIZNIT': 'Souss-Massa'}
BANQUES = (('BANQUE TAZOULA', 'BANQUE TAZOULA'), ('BQ TAZOULA', 'BANQUE TAZOULA'), ('CREDIT ZIMOUKA', 'CREDIT ZIMOUKA'))
CONTROLES = (('IDT-01', 'IDENTITE', 'Cohérence de la CIN'), ('EMP-01', 'EMPLOI_REVENUS', 'Employeur déclaré'),
             ('BNQ-01', 'BANCAIRE', 'Relevé du compte'), ('AUT-01', 'AUTOMOBILE', 'Facture du véhicule'),
             ('PMP-01', 'PM_PRO', 'Registre de la société'), ('BLG-01', 'BLACKLIST_GEO', 'Liste noire'))
VERDICTS = ['CONFORME'] * 10 + ['OK_ALERTES_MINEURES'] * 4 + ['SUSPECT'] * 4 + ['TRES_SUSPECT', None]
NOMS = ('ZELMOU', 'BAKRITA', 'TOUZANI', 'RAMIKOU', 'FILALOU', 'DOUKARI', 'SOUFIMA', 'KHAROUBI')
PRENOMS = ('AZIZ', 'NADIRA', 'SALOUM', 'ZINEBA', 'HAMIDOU', 'RIMAH')


def _date(j):
    return DEBUT + datetime.timedelta(days=j % 28)


def _iso(d):
    return d.strftime('%Y-%m-%dT09:00:00.000Z')


def _fr(d):
    return d.strftime('%d/%m/%Y')


def _montant_texte(v, k):
    """Le même montant, sous les formes rencontrées : nombre, « 30 000,00 », « 1.250,50 DH »."""
    entier, cent = int(v), round((v - int(v)) * 100)
    return (v, f'{entier:,}'.replace(',', ' ') + f',{cent:02d}', f'{entier:,}'.replace(',', '.') + f',{cent:02d} DH')[k % 3]


def plan(graine=GRAINE, n=N_DOSSIERS):
    """Une ligne par dossier : tout ce que la vérité compte, décidé ici."""
    rnd = random.Random(graine)
    lignes = []
    for i in range(n):
        pm = i % 10 == 9
        recu = _date(i)
        verdict = VERDICTS[i % 20]
        p = dict(i=i, ref=f'ZZ26S{i:04d}', type_personne='PM' if pm else 'PP', produit=PRODUITS[i % 3],
                 categorie='E' if i in CATEGORIE_E else 'ABCD'[(i // 3) % 4],
                 csp='SOCIETE' if pm else CSP_PP[i % len(CSP_PP)],
                 mode_paiement='PRELEVEMENT_SOURCE' if i % 2 else 'PRELEVEMENT_BANCAIRE',
                 verdict=verdict, statut='EN_ATTENTE_DONNEES' if verdict is None else 'COMPLETE',
                 recu=recu, semaine='%d-S%02d' % recu.isocalendar()[:2], actif=True,
                 alertes_majeures=1 if verdict == 'SUSPECT' else 0, alertes_critiques=1 if verdict == 'TRES_SUSPECT' else 0)
        p['juge_suspect'] = None if verdict is None else int(verdict in ('SUSPECT', 'TRES_SUSPECT'))
        # identité (PP) : âge révolu fixé, quelques naissances hors bornes
        if not pm:
            age = 10 if i % 97 == 0 else 95 if i % 101 == 0 else 20 + (i * 7) % 60
            p['naissance'] = (recu.replace(year=recu.year - age) - datetime.timedelta(days=rnd.randint(0, 300)))
            p['age'] = age if 18 <= age <= 90 else None
            p['sexe_saisi'] = ('M', 'F', 'masculin', 'F')[i % 4]
            p['sexe'] = 'H' if i % 2 == 0 else 'F'
            p['nationalite'] = 'FRANCAISE' if i in (11, 22, 33) else 'MAROCAINE'
        # revenu vérifié
        source = 'aucun' if pm else SOURCES_REVENU[i % 5]
        montant = float(3000 + (i * 37) % 25 * 1000) + (0.5 if i % 4 == 0 else 0.0)
        if source == 'bulletin' and i % 89 == 0:
            montant = 200.0                                       # hors bornes : non renseigné
        p.update(source_saisie=source, montant=montant)
        p['revenu'] = None if source == 'aucun' or not 500 <= montant <= 500000 else montant
        p['source_revenu'] = source if p['revenu'] is not None else 'aucun'
        p['revenu_declare'] = (montant * (1.0, 1.3, 0.7)[(i // 3) % 3]) if i % 3 == 0 and not pm else None
        # relevé : opérations lues pour 2 dossiers sur 5
        p['lignes_lues'] = i % 5 in (0, 1)
        p['banque'] = BANQUES[i % 3]
        p['ville_saisie'] = VILLES[i % len(VILLES)]
        if i % 50 == 1:
            p['ville_saisie'] = (None, 'TIZNIT', None, 'TIZNIT')          # moins de 30 dossiers : « autres villes »
        dom, _cin, rel, attendue = p['ville_saisie']
        # une société n'a pas de CIN : sa ville vient de la quittance, sinon du relevé
        p['ville'] = (dom or ('TANGER' if rel else None)) if pm else attendue
        # véhicule (AUTO et LOA)
        if p['produit'] != 'DISPO':
            p['prix'] = float(80000 + (i * 13) % 50 * 10000)
            p['etat'] = ('NEUF', 'OCCASION', 'Occasion')[(i // 3) % 3]
            p['avance'] = round(p['prix'] * 0.2, 2)
        # société (PM)
        if pm:
            p['creation'] = recu.replace(year=recu.year - (i // 10) % 12) - datetime.timedelta(days=30)
            p['associes'] = 1 if i % 20 == 9 else 2
            p['capital'] = (10000.0, 100000.0, 5000.0)[(i // 10) % 3]
        # contrôles du dernier calcul
        p['controles'] = controles(i, p)
        lignes.append(p)
    return lignes


def controles(i, p):
    """(controlId, famille, libellé, applicable, résultat, criticité, manquants)."""
    v = p['verdict']
    sortie = []
    for cid, famille, libelle in CONTROLES:
        applicable = not ((cid == 'AUT-01' and p['produit'] == 'DISPO') or (cid == 'PMP-01' and p['type_personne'] == 'PP'))
        resultat, criticite, manquants = 'CONFORME', None, []
        if not applicable:
            resultat = 'NON_APPLICABLE'
        elif v is None:
            resultat, manquants = 'NON_EXECUTABLE', ['BULLETIN_DE_PAIE'] if cid == 'EMP-01' else ['RELEVE_BANCAIRE']
        elif cid == 'EMP-01' and v == 'SUSPECT' and i % 20 in (14, 15):
            resultat, criticite = 'ANOMALIE', 'MAJEURE'                    # seule anomalie majeure : décisif
        elif cid == 'BNQ-01' and v in ('SUSPECT', 'TRES_SUSPECT') and i % 20 in (16, 17, 18):
            resultat, criticite = 'ANOMALIE', 'CRITIQUE'
        elif cid == 'IDT-01' and v == 'OK_ALERTES_MINEURES':
            resultat, criticite = 'ANOMALIE', 'MINEURE'
        elif cid == 'BLG-01' and i % 7 == 0:
            resultat, manquants = 'NON_EXECUTABLE', ['ville']
        sortie.append((cid, famille, libelle, applicable, resultat, criticite, manquants))
    return sortie


# ---- dossiers au format de la v2 --------------------------------------------------------------------------------------

def modele(graine=GRAINE):
    import generer_dossiers as gd
    return gd.generer(n_dossiers=gd.MINIMUM_DOSSIERS, n_societes=300, graine=graine).dossiers[0]


def _piece(base, type_, k, champs, source='AMONT'):
    return dict(base, type=type_, upstreamPieceId=f'eqdom_{type_}_{k}', fields=champs, source=source,
                extractionStatus='OK')


def dossier(m, p):
    i, ref = p['i'], p['ref']
    d = json.loads(json.dumps(m))
    nom, prenom = NOMS[i % len(NOMS)], PRENOMS[i % len(PRENOMS)]
    cin = f'ZZ7{i:05d}'
    recu = _iso(p['recu'])
    ident = str(uuid.uuid5(uuid.NAMESPACE_OID, f'stats-{i}'))
    analyse_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f'stats-analyse-{i}'))
    controles_v2 = [dict(id=str(uuid.uuid5(uuid.NAMESPACE_OID, f'stats-{i}-{cid}')), controlId=cid,
                         applicable=app, applicabilityReason='Fictif.', outcome=res, criticality=crit,
                         escalade=None, explanation='Contrôle fictif.', details=None, missing=manq, source='MOTEUR',
                         computedAt=recu, label=lib, family=fam, numeroMetier=cid, previousOutcome=None)
                    for cid, fam, lib, app, res, crit, manq in p['controles']]
    analyse = dict(id=analyse_id, matrixVersion='V1.0', engineVersion='2.8.0', trigger='INTAKE', status=p['statut'],
                   verdict=p['verdict'], provisional=False, startedAt=recu, endedAt=recu, error=None,
                   controls=controles_v2)
    d.update(ref=ref, id=ident, personType=p['type_personne'], csp=p['csp'], productType=p['produit'],
             paymentMode=p['mode_paiement'], clientName=f'{nom} {prenom}', category=p['categorie'],
             analysisStatus=p['statut'], verdict=p['verdict'], verdictProvisional=False,
             alertsMinor=1 if p['verdict'] == 'OK_ALERTES_MINEURES' else 0, alertsMajor=p['alertes_majeures'],
             alertsCritical=p['alertes_critiques'], businessReceivedAt=recu, resultsReceivedAt=recu, createdAt=recu,
             updatedAt=recu, analyses=[{k: v for k, v in analyse.items() if k != 'controls'}],
             latestAnalysis=analyse, reanalyses=[], synthese=None)
    declare = p['revenu_declare']
    d['businessData'] = dict(d['businessData'], dossier_ref=ref, person_type=p['type_personne'], csp=p['csp'],
                             product_type=p['produit'], payment_mode=p['mode_paiement'],
                             civil=dict(full_name=f'{nom} {prenom}', cin=cin, address=None),
                             declared=dict(employer='VAB', monthly_income=None if declare is None else
                                           _montant_texte(round(declare, 2), i), pension_organism=None))
    base = m['pieces'][0]
    dom, ville_cin, ville_releve, _ = p['ville_saisie']
    pieces: list = []
    if p['type_personne'] == 'PP':
        cin_champs = dict(nom=nom, prenom=prenom, cin=cin, date_naissance=_fr(p['naissance']), sexe=p['sexe_saisi'],
                          nationalite=p['nationalite'])
        if ville_cin and ville_cin.startswith('12 RUE'):
            cin_champs['adresse'] = ville_cin
        elif ville_cin:
            cin_champs['ville_residence'] = ville_cin
        pieces.append(_piece(base, 'CIN', 0, cin_champs, source='REANALYSE' if i % 25 == 0 else 'AMONT'))
        src, mt = p['source_saisie'], p['montant']
        if src == 'bulletin':
            pieces.append(_piece(base, 'BULLETIN_DE_PAIE', 0, dict(
                nom=nom, prenom=prenom, remuneration=dict(salaire_net=_montant_texte(mt, i)), mois_paie='09/2026',
                date_embauche=_fr(p['recu'].replace(year=p['recu'].year - (i % 12))),
                situation_familiale=('MARIE', 'CELIBATAIRE')[i % 2], nombre_enfants=str(i % 4))))
        if src in ('bulletin', 'attestation'):
            att = dict(nom=nom, prenom=prenom, type_contrat=('CDI', 'cdd', 'INTERIM')[i % 3],
                       date_embauche=_fr(p['recu'].replace(year=p['recu'].year - (i % 12))))
            if src == 'attestation':
                att['salaire_net'] = _montant_texte(mt, i)
            pieces.append(_piece(base, 'ATTESTATION_TRAVAIL_SALAIRE', 0, att))
        if src == 'pension':
            pieces.append(_piece(base, 'ATTESTATION_PENSION', 0, dict(nom=nom, prenom=prenom,
                                                                     montant_pension_net=_montant_texte(mt, i))))
    else:
        pieces.append(_piece(base, 'REGISTRE_COMMERCE', 0, dict(denomination_sociale=f'{nom} NEGOCE SARL',
                                                               date_creation=_fr(p['creation']))))
        associes = [dict(nom_complet=f'{NOMS[(i + a) % len(NOMS)]} {PRENOMS[a]}', cin=f'ZZ8{i:04d}{a}')
                    for a in range(p['associes'])]
        pieces.append(_piece(base, 'STATUTS', 0, dict(denomination_sociale=f'{nom} NEGOCE SARL',
                                                     capital_social=_montant_texte(p['capital'], i), associes=associes)))
    if dom:
        pieces.append(_piece(base, 'DOMICILIATION', 0, dict(nom=nom, prenom=prenom, ville=dom)))
    mois = [dict(mois=mo, annee=2026, solde_ouverture=1000.0, solde_cloture=1200.0, total_credit=9000.0,
                 total_debit=8800.0, **({'operations': [dict(date_operation=f'05/{mo:02d}', libelle='VIREMENT RECU',
                                                             debit=None, credit=9000.0)]} if p['lignes_lues'] else {}))
            for mo in (8, 9)]
    releve = dict(titulaire_compte=f'{nom} {prenom}', rib='999' + f'{i:021d}', banque=p['banque'][0], mois=mois)
    if ville_releve:
        releve['adresse'] = ville_releve
    if p['type_personne'] == 'PP' and p['source_saisie'] == 'releve':
        releve['montant_salaire'] = {f'{mo:02d}/2026': p['montant'] for mo in (8, 9)}
    pieces.append(_piece(base, 'RELEVE_BANCAIRE', 0, releve))
    if p['produit'] != 'DISPO':
        pieces.append(_piece(base, 'FACTURE_PROFORMA_VEHICULE', 0, dict(
            etat_vehicule=p['etat'], prix_ttc=_montant_texte(p['prix'], i), montant_avance=p['avance'],
            marque_vehicule='MARQUE ZOUBA', vendeur={'raison_sociale': 'CONCESSION ZILAKO'})))
    d['pieces'] = pieces
    return d


def dossiers(graine=GRAINE, n=N_DOSSIERS):
    m = modele(graine)
    return [dossier(m, p) for p in plan(graine, n)]


# ---- vérité attendue, comptée sur le plan --------------------------------------------------------------------------

def _case(indicateur, valeur, numerateur=None, denominateur=None, dimension1='', valeur1='', masque=0):
    return dict(indicateur=indicateur, filtre_produit='tous', filtre_categorie='toutes', dimension1=dimension1,
                valeur1=valeur1, numerateur=numerateur, denominateur=denominateur, valeur=valeur, masque=masque)


def verite(lignes):
    n = len(lignes)
    jug = [p for p in lignes if p['juge_suspect'] is not None]
    k_susp = sum(p['juge_suspect'] for p in jug)
    cases = [_case('nb_dossiers', n, None, n)]
    for tp in ('PP', 'PM'):
        c = sum(p['type_personne'] == tp for p in lignes)
        cases.append(_case('nb_dossiers', c, None, c, 'type_personne', tp))
    par_cat = {cat: sum(p['categorie'] == cat for p in lignes) for cat in 'ABCDE'}
    assert par_cat['E'] == len(CATEGORIE_E) < 5
    secondaire = min((c, cat) for cat, c in par_cat.items() if cat != 'E')[1]   # la plus petite case restante
    for cat, c in par_cat.items():
        cache = cat in ('E', secondaire)
        cases.append(_case('nb_dossiers', None if cache else c, None, None if cache else c, 'categorie', cat,
                           masque=int(cache)))
    cases.append(_case('taux_juge_suspect', k_susp / len(jug), k_susp, len(jug)))
    for prod in PRODUITS:
        sel = [p for p in jug if p['produit'] == prod]
        k = sum(p['juge_suspect'] for p in sel)
        cases.append(_case('taux_juge_suspect', k / len(sel), k, len(sel), 'produit', prod))
    tres = sum(p['verdict'] == 'TRES_SUSPECT' for p in jug)
    cases.append(_case('taux_tres_suspect', tres / len(jug), tres, len(jug)))
    pp = [p for p in lignes if p['type_personne'] == 'PP']               # le revenu ne concerne que les PP
    for src in SOURCES_REVENU:
        c = sum(p['source_revenu'] == src for p in pp)
        cases.append(_case('part_source_revenu', c / len(pp), c, len(pp), 'source_revenu', src))
    ages = [p['age'] for p in lignes if p.get('age') is not None]
    cases.append(_case('mediane_age', statistics.median(ages), None, len(ages)))
    revenus = [p['revenu'] for p in lignes if p['revenu'] is not None]
    cases.append(_case('mediane_revenu_verifie', statistics.median(revenus), None, len(revenus)))
    prix = [p['prix'] for p in lignes if 'prix' in p]
    cases.append(_case('mediane_prix_vehicule', statistics.median(prix), None, len(prix)))
    releves_lus = sum(p['lignes_lues'] for p in lignes)
    cases.append(_case('taux_releve_relu', releves_lus / n, releves_lus, n))
    for cid in ('EMP-01', 'BNQ-01', 'AUT-01'):
        app = [c for p in lignes for c in p['controles'] if c[0] == cid and c[3] and c[4] != 'NON_APPLICABLE']
        k = sum(c[4] == 'ANOMALIE' for c in app)
        fam = next(c[1] for c in CONTROLES if c[0] == cid)
        cases.append(dict(_case('taux_anomalie_controle', k / len(app), k, len(app), 'famille', fam),
                          dimension2='controle', valeur2=cid))
    suspects = [p for p in lignes if p['juge_suspect'] == 1]
    decisif = sum(1 for p in suspects if [c[0] for c in p['controles']
                                          if c[4] == 'ANOMALIE' and c[5] in ('MAJEURE', 'CRITIQUE')] == ['EMP-01'])
    cases.append(dict(_case('controle_decisif', decisif / len(suspects), decisif, len(suspects), 'famille',
                            'EMPLOI_REVENUS'), dimension2='controle', valeur2='EMP-01'))
    for v, nom in ((None, 'ville inconnue'), ('CASABLANCA', 'CASABLANCA')):
        c = sum(p['ville'] == v for p in lignes)
        cases.append(_case('nb_dossiers', c, None, c, 'ville', nom))
    for region in sorted(set(REGION.values())):
        c = sum(REGION.get(p['ville']) == region for p in lignes)
        cases.append(_case('nb_dossiers', c, None, c, 'region', region))
    for sexe in ('H', 'F'):
        c = sum(p.get('sexe') == sexe for p in lignes)
        cases.append(_case('nb_dossiers', c, None, c, 'sexe', sexe))
    for c in cases:
        c.setdefault('dimension2', '')
        c.setdefault('valeur2', '')
    return dict(graine=GRAINE, dossiers=n, periode_debut=DEBUT.isoformat(),
                periode_fin=(DEBUT + datetime.timedelta(days=27)).isoformat(), cases=cases)


def construire_base(chemin, liste):
    """Base neuve : dossiers reçus (c0), puis toutes les couches, comme construire.py."""
    from pipeline import migrer
    from pipeline.couches import COUCHES
    from pipeline.couches import c0_brut as c0
    if os.path.exists(chemin):
        os.remove(chemin)
    cx = sqlite3.connect(chemin)
    migrer.appliquer(cx)
    passage = c0.ouvrir_passage(cx, 'essai-statistiques', 'lot', T0)
    for d in liste:
        c0.recevoir(cx, passage, d, actif=True, maintenant=T0)
    for couche in COUCHES[1:]:
        couche.construire_tout(cx)
    cx.commit()
    return cx


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--base', nargs='?', const=BASE_ESSAI)
    a.add_argument('--attendu', nargs='?', const=ATTENDU)
    a.add_argument('--graine', type=int, default=GRAINE)
    o = a.parse_args(argv)
    lignes = plan(o.graine)
    if o.attendu:
        with open(o.attendu, 'w', encoding='utf-8') as f:
            json.dump(verite(lignes), f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
        print(f'vérité : {len(verite(lignes)["cases"])} cases')
    if o.base:
        os.makedirs(os.path.dirname(os.path.abspath(o.base)), exist_ok=True)
        construire_base(o.base, dossiers(o.graine)).close()
        print(f'base : {len(lignes)} dossiers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
