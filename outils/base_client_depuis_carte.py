#!/usr/bin/env python3
"""Base client (couches c0 à c5) construite depuis la base de la carte (tables af_*, bl_*, rc_* du kit).

La base de la carte garde, pour chaque dossier de l'antifraude, ce que le kit en a extrait (`charger_antifraude.py`) :
le contexte du dossier (`af_dossier`), les personnes, sociétés et comptes lus dans chaque pièce (`af_personne`,
`af_societe`, `af_compte`, avec `piece_type` et `piece_id`). Ce script remet chaque dossier sous la forme de
`DossierDetail` de la v2 : une pièce par `piece_id`, ses champs sous les clés de production que le kit avait lues
(`nom`, `cin`, `denomination_sociale`, `numero_rc`, `employeur.raison_sociale`, `gerants[]`…), le contexte en
`businessData`. Les dossiers passent par `c0_brut.recevoir`, puis toutes les couches se construisent, avec la liste
noire et le registre recopiés de la même base (`--socle`) : la base client et la vue 360° s'en servent telles quelles.

Ce que la base de la carte ne garde pas ne se reconstitue pas : salaires et soldes mois par mois, opérations des
relevés, contrôles un par un, véhicules. Les valeurs hors des énumérations de Kamal sont laissées vides.

Usage, par Lounès seulement (garde-fou des données réelles, base rangée hors du dépôt) :
  python outils/base_client_depuis_carte.py --carte CARTE_KIT.sqlite --base BASE_CLIENT.sqlite
"""
import argparse
import os
import sqlite3
import sys
from collections import defaultdict

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

ENUMS = {
    'personType': {'PP', 'PM'},
    'category': {'A', 'B', 'C', 'D', 'E', 'NON_CLASSIFIABLE'},
    'analysisStatus': {'EN_ATTENTE_DONNEES', 'EN_COURS', 'COMPLETE', 'INCOMPLETE', 'EN_ERREUR'},
    'verdict': {'CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT'},
}
DATE_DEFAUT = '2026-01-01'
EMPLOI = ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_CNSS')
DIRIGEANTS = {'gerant', 'associe', 'dirigeant', 'signataire', 'representant'}


def _enum(champ, v):
    return v if v in ENUMS[champ] else None


def _horodatage(jour):
    jour = (jour or DATE_DEFAUT)[:10]
    return f'{jour}T00:00:00.000Z'


def _sans_vides(d):
    return {k: v for k, v in d.items() if v not in (None, '')}


def _lignes(cx, sql, *p):
    cur = cx.execute(sql, p)
    noms = [c[0] for c in cur.description]
    return [dict(zip(noms, r)) for r in cur]


def _personne_simple(p):
    return _sans_vides(dict(nom=p['nom'], prenom=p['prenom'], nom_complet=p['nom_complet'], cin=p['cin_brut'],
                            numero_cin=p['cin_brut'], date_naissance=p['date_naissance'], adresse=p['adresse']))


def _dirigeant(p):
    return _sans_vides(dict(nom_complet=p['nom_complet'] or ' '.join(filter(None, (p['nom'], p['prenom']))) or None,
                            nom=p['nom'], prenom=p['prenom'], cin=p['cin_brut'], numero_cin=p['cin_brut'],
                            qualite=p['qualite'] or p['role'], parts_sociales=p['parts'], adresse=p['adresse'],
                            date_naissance=p['date_naissance'], nationalite=p['nationalite']))


def champs_piece(type_piece, personnes, societes, comptes):
    """Champs d'une pièce, sous les clés de production que `charger_antifraude.py` avait lues."""
    f = {}
    pers = [p for p in personnes if p['role'] not in DIRIGEANTS] or personnes
    p = pers[0] if pers else None
    s = societes[0] if societes else None
    if type_piece == 'CIN' and p:
        f = _sans_vides(dict(nom=p['nom'], prenom=p['prenom'], cin=p['cin_brut'], id_document_recto=p['cin_brut'],
                             date_naissance=p['date_naissance'], lieu_naissance=p['lieu_naissance'], adresse=p['adresse'],
                             nom_pere=p['nom_pere'], nom_mere=p['nom_mere'], nationalite=p['nationalite'],
                             document_identite='CIN'))
    elif type_piece in EMPLOI:
        emp = next((x for x in societes if x['role'] == 'employeur'), s)
        if emp:
            f['employeur'] = _sans_vides(dict(raison_sociale=emp['denomination'], ice=emp['ice'], adresse=emp['adresse']))
        if p:
            f.update(_sans_vides(dict(nom=p['nom'], prenom=p['prenom'], numero_cin=p['cin_brut'],
                                      date_naissance=p['date_naissance'], adresse_employe=p['adresse'],
                                      fonction=p['qualite'])))
            f['employe'] = _sans_vides(dict(nom_complet=p['nom_complet'], cin=p['cin_brut']))
    elif type_piece == 'ATTESTATION_PENSION' and p:
        f = _sans_vides(dict(nom=p['nom'], prenom=p['prenom'], numero_cin=p['cin_brut'], date_naissance=p['date_naissance'],
                             adresse=p['adresse']))
        f['pensionne'] = _sans_vides(dict(nom_complet=p['nom_complet'], cin=p['cin_brut']))
    elif type_piece == 'CARTE_PROFESSIONNELLE' and p:
        f = _sans_vides(dict(nom=p['nom'], prenom=p['prenom'], nom_complet=p['nom_complet'], numero_cin=p['cin_brut'],
                             profession=p['qualite']))
    elif type_piece == 'CARTE_GRISE' and p:
        f = _sans_vides(dict(nom=p['nom'], prenom=p['prenom'], cin=p['cin_brut'], adresse=p['adresse']))
    elif type_piece == 'FACTURE_PROFORMA_VEHICULE' and s:
        f = {'vendeur': _sans_vides(dict(raison_sociale=s['denomination']))}
    elif type_piece in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB') and comptes:
        c = comptes[0]
        f = _sans_vides(dict(rib=c['rib'], numero_compte=c['rib'] if type_piece == 'RELEVE_BANCAIRE' else None,
                             banque=c['banque'], titulaire_compte=c['titulaire'], type_titulaire=c['type_titulaire']))
    else:                                                   # registre, statuts, procès-verbal, pièce de société
        if s:
            f = _sans_vides(dict(denomination_sociale=s['denomination'], numero_rc=s['rc_brut'] or s['rc_num'],
                                 ville_tribunal=s['tribunal_code'], ice=s['ice'], forme_juridique=s['forme_juridique'],
                                 adresse_siege=s['adresse'], date_creation=s['date_creation'],
                                 capital_social=s['capital'], objet_social=s['objet'], origine_fond=s['origine_fonds']))
        dirigeants = [x for x in personnes if x['role'] in DIRIGEANTS]
        gerants = [_dirigeant(x) for x in dirigeants if x['role'] in ('gerant', 'dirigeant', 'representant')]
        associes = [_dirigeant(x) for x in dirigeants if x['role'] in ('associe', 'signataire')]
        if gerants:
            f['gerants'] = gerants
        if associes:
            f['associes'] = associes
        if not f and p:
            f = _personne_simple(p)
    return f


def dossiers(cx):
    """Chaque dossier de la base de la carte, sous la forme de `DossierDetail`."""
    par_piece = defaultdict(lambda: dict(personnes=[], societes=[], comptes=[]))
    types = {}
    for genre, table in (('personnes', 'af_personne'), ('societes', 'af_societe'), ('comptes', 'af_compte')):
        for ligne in _lignes(cx, f'SELECT * FROM {table} WHERE piece_id IS NOT NULL ORDER BY 1'):
            cle = (ligne['dossier_ref'], ligne['piece_id'])
            par_piece[cle][genre].append(ligne)
            types.setdefault(cle, ligne['piece_type'] or 'AUTRE')
    pieces = defaultdict(list)
    for (ref, piece_id), contenu in sorted(par_piece.items()):
        type_piece = types[(ref, piece_id)]
        if type_piece == 'CONTEXTE':
            continue
        champs = champs_piece(type_piece, contenu['personnes'], contenu['societes'], contenu['comptes'])
        if champs:
            pieces[ref].append(dict(upstreamPieceId=str(piece_id), type=type_piece, extractionStatus='OK',
                                    pdfPath=None, fields=champs, source='AMONT'))
    for d in _lignes(cx, 'SELECT * FROM af_dossier ORDER BY ref'):
        quand = _horodatage(d['recu_le'])
        affaire = _sans_vides(dict(
            dossier_ref=d['ref'], person_type=_enum('personType', d['type_personne']), csp=d['csp'],
            product_type=d['produit'], payment_mode=d['mode_paiement'],
            civil=_sans_vides(dict(full_name=d['client_nom'], cin=d['client_cin'], address=d['client_adresse'])),
            declared=_sans_vides(dict(employer=d['employeur_declare'], monthly_income=d['revenu_declare'],
                                      pension_organism=d['organisme_pension'])),
            known_client=None if d['client_connu'] is None else bool(d['client_connu'])))
        yield dict(
            id=d['ref'], ref=d['ref'], actif=bool(d['actif'] if d['actif'] is not None else 1),
            personType=_enum('personType', d['type_personne']), csp=d['csp'], productType=d['produit'],
            paymentMode=d['mode_paiement'], clientName=d['client_nom'], agence=None, canal=None,
            businessData=affaire, category=_enum('category', d['categorie']), categoryRule=None, categoryReason=None,
            analysisStatus=_enum('analysisStatus', d['statut_analyse']) or 'COMPLETE',
            verdict=_enum('verdict', d['verdict']), verdictProvisional=False,
            alertsMinor=d['alertes_mineures'] or 0, alertsMajor=d['alertes_majeures'] or 0,
            alertsCritical=d['alertes_critiques'] or 0, commentaireScore=None, commentaireAlerte=False,
            matrixVersion=None, businessReceivedAt=quand, resultsReceivedAt=None, createdAt=quand, updatedAt=quand,
            pieces=pieces.get(d['ref'], []), analyses=[], latestAnalysis=None, reanalyses=[], synthese=None)


def construire(carte, base, maintenant=None):
    """Reçoit chaque dossier dans la couche 0 de `base`, puis construit toutes les couches avec le socle de `carte`."""
    from pipeline import migrer
    from pipeline.couches import COUCHES, c0_brut as c0, c2_identites
    import construire as construction
    source = sqlite3.connect(f'file:{carte}?mode=ro', uri=True)
    bilan = dict(dossiers=0, pieces=0, miroir_refuse=0)
    cx = sqlite3.connect(base)
    try:
        migrer.appliquer(cx)
        passage = c0.ouvrir_passage(cx, 'base de la carte', 'lot', maintenant)
        for d in dossiers(source):
            actif = d.pop('actif')
            bilan['dossiers'] += 1
            bilan['pieces'] += len(d['pieces'])
            try:
                c0.recevoir(cx, passage, d, actif=actif, maintenant=maintenant)
            except c0.MiroirRefuse:
                bilan['miroir_refuse'] += 1
        c0.fermer_passage(cx, passage, bilan['dossiers'], bilan['dossiers'] - bilan['miroir_refuse'], maintenant)
    finally:
        cx.close()
        source.close()
    construction.construire(base, couches=COUCHES, depuis='c1', socle=carte)
    assert c2_identites                               # le socle est chargé par construire() (liste noire, registre)
    return bilan


def _dans_le_depot(chemin):
    return os.path.realpath(chemin).startswith(os.path.realpath(RACINE) + os.sep)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--carte', required=True, help='copie SQLite de la base de la carte (copier_pg_sqlite.py)')
    ap.add_argument('--base', required=True, help='base client à écrire, hors du dépôt')
    a = ap.parse_args(argv)
    if _dans_le_depot(a.base):
        print('arrêt : la base client se range hors du dépôt (par exemple dans ~/antifraude-donnees)', file=sys.stderr)
        return 2
    if os.environ.get('CARTE_DONNEES_REELLES') != '1':
        print('arrêt : données réelles : la commande doit commencer par CARTE_DONNEES_REELLES=1', file=sys.stderr)
        return 2
    if not os.path.exists(a.carte):
        print('arrêt : base de la carte introuvable', file=sys.stderr)
        return 2
    if os.path.exists(a.base):
        os.remove(a.base)                             # reconstruite en entier, sans état caché
    print('lecture des dossiers et construction des couches (plusieurs minutes)…', flush=True)
    try:
        bilan = construire(a.carte, a.base)
    except Exception as e:                            # noqa: BLE001  jamais de contenu dans la sortie
        print(f'arrêt : construction interrompue ({type(e).__name__})', file=sys.stderr)
        return 1
    print(' ; '.join(f'{k} : {v}' for k, v in bilan.items()))
    cx = sqlite3.connect(f'file:{a.base}?mode=ro', uri=True)
    try:
        for table in ('c1_piece', 'c2_personne', 'c2_societe', 'c3_dossier', 'c3_demandeur', 'c5_arete'):
            print(f'  {table} : {cx.execute(f"SELECT count(*) FROM {table}").fetchone()[0]}')
    finally:
        cx.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
