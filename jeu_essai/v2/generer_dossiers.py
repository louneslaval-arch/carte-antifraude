#!/usr/bin/env python3
"""Générateur de dossiers fictifs de l'antifraude v2, au format exact des types de Kamal (étape C.2).

Produit, à partir d'une graine :
  - le registre et la liste noire fictifs de `jeu_essai/generer.py`, enrichis des structures dont les scénarios ont
    besoin (un gérant de 8 sociétés, un liquidateur de 40, des inscrits, des sociétés inscrites…) ;
  - des dossiers au format de `GET /api/dossiers/:ref` (`DossierDetail`), la liste au format de `GET /api/dossiers`,
    une chronologie (arrivées, relectures) et la vérité attendue (`verite_v2.json`).

Tout est fictif : CIN et références en « ZZ », RIB, ICE, n° CNSS et d'affiliation en « 999 », noms tirés de
syllabes. Les clés de `fields` viennent de l'inventaire de production de Kamal (`champs_par_type_prod.csv`), par type
de pièce et par source ; les listes d'objets, du README de Kamal (§ 4). Sans la structure de Kamal, rien n'est
généré (préalable manquant) : un dossier « à peu près au format » ferait passer des tests qui casseraient sur la v2.

Pièges T01 à T15 et scénarios S01 à S24 : `.claude/skills/jeu-essai-v2/references/pieges_scenarios.md`. Adaptations,
faute de champ chez Kamal (questions ouvertes) : S13 et S14, foyer par « même nom de famille et même logement »
(aucun champ « conjoint ») ; S24, par le point de vente `agency.code` (aucun champ « apporteur ») ; T12, CIN gabarit
« N/A » (la forme de démonstration réelle ne passe pas la garde : un test qui en a besoin la construit lui-même).
Les niveaux et forces attendus suivent les paramètres provisoires de `.claude/rules/score.md`.

Usage : generer_dossiers.py --sortie DOSSIER [--dossiers 1000] [--societes 61043] [--graine N]
Sortie console : comptages seulement.
"""
import argparse
import csv
import datetime
import json
import math
import os
import random
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai'), os.path.join(RACINE, 'pipeline')]
from construire_base import COLONNES_BL  # noqa: E402
from generer import PRENOMS, VILLES_UTILES, Generateur, ecrire_csv  # noqa: E402

GRAINE = 20261113
MINIMUM_DOSSIERS = 300
SEUIL_MAJEURE, SEUIL_MINEURE, SEUIL_AFFICHAGE = 0.20, 0.08, 0.05   # provisoires (score.md)

# Listes d'objets de `fields` décrites au README de Kamal (§ 4), absentes de l'inventaire à plat
CLES_LISTES_README = {
    'CIN': ('cartes',),
    'PV_ASSEMBLEE_GENERALE': ('associes_presents', 'nouveau_gerant', 'resolutions'),
}
# Identifiants de pièce côté EQDOM cités au README ; les autres suivent la même forme (provisoire)
ID_AMONT = {'CIN': 'eqdom_CIN', 'RELEVE_BANCAIRE': 'eqdom_releves_comptes', 'REGISTRE_COMMERCE': 'eqdom_RC',
            'STATUTS': 'eqdom_statut', 'FACTURE_PROFORMA_VEHICULE': 'eqdom_facture_proforma',
            'DOMICILIATION': 'eqdom_quittance_eau'}
# Vocabulaires du registre du commerce (README § 4, table amont → moteur)
RC_MOTEUR = {'denomination_sociale', 'adresse_siege', 'ville_tribunal', 'ice', 'capital_social', 'objet_social',
             'date_creation', 'date_generation_document', 'gerants'}
RC_AMONT = {'nom_societe', 'siege_social', 'tribunal_commerce', 'numero_ice', 'capital', 'objet_commerce',
            'date_immatriculation', 'date_debut', 'date_emission', 'dirigeants'}
CHAMPS_DE_CIN = ('filiation_complete', 'date_expiration', 'cin')
MONTANT_RE = re.compile(r'montant|salaire|prix|capital|solde|total|frais|somme|pension|base_cnss|commission')
DATE_RE = re.compile(r'^(ctrl_)?date|_date$|validite')


class PrealableManquant(RuntimeError):
    pass


def structure_kamal(chemin=None):
    candidats = [chemin] if chemin else [os.path.join(RACINE, 'reference', 'v2'),
                                         os.path.join(RACINE, 'import', 'kamal_structure')]
    for d in candidats:
        if os.path.exists(os.path.join(d, 'reference', 'champs_par_type_prod.csv')):
            return d
    raise PrealableManquant('structure de Kamal absente (reference/v2/ ou import/kamal_structure/)')


def charger_inventaire(structure):
    inventaire = {}
    with open(os.path.join(structure, 'reference', 'champs_par_type_prod.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            inventaire.setdefault((r['type'], r['source']), []).append(dict(
                key=r['key'], n=int(r['n']), non_null=int(r['non_null']), types=set(r['types_json'].split('|'))))
    return inventaire


def charger_enumerations(structure):
    with open(os.path.join(structure, 'reference', 'business-data.schema.json'), encoding='utf-8') as f:
        proprietes = next(iter(json.load(f)['definitions'].values()))['properties']
    return {k: proprietes[k]['enum'] for k in ('csp', 'product_type', 'payment_mode')}


def cout(n):
    """Coût de taille d'un nœud traversé (score.md, n°21)."""
    return 1.0 if n <= 2 else math.sqrt(2 / n)


def niveau_de(force, liens):
    """Niveau attendu sous les paramètres provisoires : plafond par la longueur, puis seuils de force."""
    if liens == 0:
        return 'critique'
    if liens >= 4:
        return 'hors alerte'
    if force >= SEUIL_MAJEURE:
        return 'majeure' if liens <= 2 else 'mineure'
    if force >= SEUIL_MINEURE:
        return 'mineure'
    return 'affiché' if force >= SEUIL_AFFICHAGE else None


# ---- registre et liste noire fictifs, avec les structures des scénarios ------------------------------------------

class Registre(Generateur):
    """Le générateur du registre fictif, plus des sociétés « figées » : une seule annonce de création, ICE publié."""

    def _annoncer(self, s, type_acte, quand, personnes):
        aid = super()._annoncer(s, type_acte, quand, personnes)
        if s.get('ice'):
            self.annonces[-1]['ice'] = s['ice']
        return aid

    def annonces_registre(self):
        toutes = self.societes
        self.societes = [s for s in toutes if not s.get('figee')]
        super().annonces_registre()
        self.societes = toutes
        for s in toutes:
            if s.get('figee'):
                self._annoncer(s, 'Création', s['creation'], s['personnes'])

    # -- briques des scénarios --
    def personne_scenario(self, cin=True, ville=None, comme=None):
        """Personne au nom de famille unique (aucun homonyme fortuit), hors du tirage des gérants."""
        ville = ville or VILLES_UTILES[0]
        p = dict(id=len(self.personnes), prenom=comme['prenom'] if comme else self.r.choice(PRENOMS),
                 nom=comme['nom'] if comme else self._nom_famille(), ville=ville,
                 cin=self._cin() if cin else None, societes=[], naissance=self._date(1950, 2000))
        self.personnes.append(p)
        return p

    def societe_scenario(self, personnes, ville=None):
        ville = ville or VILLES_UTILES[0]
        k = len(self.societes)
        mot = ''.join(self._syllabe()[0] for _ in range(3))
        rc = str(700_000 + k)
        s = dict(id=k, nom=f'{mot} {k} SCENARIO SARL', nom_ar=None, ville=ville, rc=rc,
                 personnes=[(p['id'], role, parts) for p, role, parts in personnes],
                 creation=self._date(2022, 2025), ecriture='lat', figee=True,
                 ice='999%012d' % (int(rc) * 1000 + k % 1000))
        s['nom_ar'] = s['nom']
        for p, _, _ in personnes:
            p['societes'].append(k)
        self.societes.append(s)
        return s

    def inscrire_pp(self, p, cin=True, **valeurs):
        return self._inscription(cli_phy_mor='PP', cin=p['cin'] if cin else '', nom=p['nom'][0],
                                 prenom=p['prenom'][0], **valeurs)

    def inscrire_pm(self, s, par):
        ville = s['ville'][1].upper()
        cles = {'rc': dict(regist_com=s['rc'], regist_tribune=ville), 'ice': dict(ice=s['ice']),
                'nom': dict(ville=ville)}[par]
        return self._inscription(cli_phy_mor='PM', nom_ras=s['nom'], **cles)


def construire_monde(n_societes, graine):
    """Registre, liste noire et structures des scénarios ; rend (registre, scènes)."""
    g = Registre(n_societes, graine)
    g.registre()
    g.liste_noire()
    sc = {}
    P, S = g.personne_scenario, g.societe_scenario
    sc['x1'] = P(); g.inscrire_pp(sc['x1'])
    sc['s2'] = S([(P(), 'gerant', None)]); g.inscrire_pm(sc['s2'], 'rc')
    sc['s3'] = S([(P(), 'gerant', None)]); g.inscrire_pm(sc['s3'], 'ice')
    sc['g4'] = P(); sc['e4'] = S([(sc['g4'], 'gerant', None)]); g.inscrire_pp(sc['g4'])
    for nom in ('x5', 'x6', 'x13', 'x14', 'x16a', 'x16b', 'x17', 'x24'):
        sc[nom] = P(); g.inscrire_pp(sc[nom])
    sc['p7'] = P(); sc['s7'] = [S([(sc['p7'], 'gerant', None)]) for _ in range(8)]
    g.inscrire_pm(sc['s7'][1], 'rc')
    sc['l8'] = P(); sc['s8'] = [S([(sc['l8'], 'liquidateur', None)]) for _ in range(40)]
    g.inscrire_pm(sc['s8'][1], 'rc')
    sc['g9'], sc['x9'] = P(), P()
    sc['e9'] = S([(sc['g9'], 'gerant', None)])
    sc['b9'] = S([(sc['g9'], 'gerant', None), (sc['x9'], 'gerant', None)]); g.inscrire_pp(sc['x9'])
    sc['g10'], sc['h10'] = P(), P()
    sc['e10'] = S([(sc['g10'], 'gerant', None)])
    sc['b10'] = S([(sc['g10'], 'gerant', None), (sc['h10'], 'associe', None)])
    sc['c10'] = S([(sc['h10'], 'gerant', None)]); g.inscrire_pm(sc['c10'], 'rc')
    sc['g11'] = P(cin=False); sc['e11'] = S([(sc['g11'], 'gerant', None)])
    g.inscrire_pp(sc['g11'], cin=False, ville=sc['g11']['ville'][1].upper())      # même nom, même ville, sans CIN
    sc['i12'] = S([(P(), 'gerant', None)]); g.inscrire_pm(sc['i12'], 'nom')
    sc['v15'] = P(); g.inscrire_pp(sc['v15'], motif='VICTIME USURPATION IDENTITE')
    sc['g20'] = P(); sc['e20'] = S([(sc['g20'], 'gerant', None)]); g.inscrire_pp(sc['g20'])
    sc['g23'] = P(); sc['e23'] = S([(sc['g23'], 'gerant', None)]); g.inscrire_pp(sc['g23'])
    g.annonces_registre()
    return g, sc


# ---- dossiers ----------------------------------------------------------------------------------------------------

class Jeu:
    def __init__(self, monde, dossiers, chronologie, verite, meta, liste):
        self.monde, self.dossiers, self.chronologie = monde, dossiers, chronologie
        self.verite, self.meta, self.liste = verite, meta, liste


class Fabrique:
    def __init__(self, monde, scenes, inventaire, enumerations, graine):
        self.g, self.sc, self.inventaire, self.enums = monde, scenes, inventaire, enumerations
        self.r = random.Random(graine * 7919 + 1)
        self.horloge = datetime.datetime(2026, 9, 1, 8, 0, 0)
        self.n_ref = self.n_id = self.n_rib = self.n_employeur = 0
        self.entrees = []          # (instant, ref, détail)
        self.verite, self.meta, self.finals = [], {}, {}
        self.employeurs = [self.employeur_hors_registre() for _ in range(25)]

    # -- identifiants et valeurs fictives --
    def uid(self):
        self.n_id += 1
        return '00000000-0000-4000-8000-%012d' % self.n_id

    def ref(self):
        self.n_ref += 1
        return 'ZZ26%s%04d' % ('RSTUVW'[self.n_ref // 10000], self.n_ref % 10000)

    def cin(self):
        while True:
            c = 'ZZ%06d' % self.r.randrange(1, 1_000_000)
            if c not in self.g.cins_pris:
                self.g.cins_pris.add(c)
                return c

    def rib(self):
        self.n_rib += 1
        return '999%021d' % self.n_rib

    def instant(self, minutes=37):
        self.horloge += datetime.timedelta(minutes=minutes)
        return self.horloge

    @staticmethod
    def iso(t):
        return t.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    def date_txt(self, debut=2015, fin=2026):
        j = datetime.date(debut, 1, 1) + datetime.timedelta(days=self.r.randrange(365 * (fin - debut) + 200))
        return j.strftime('%d/%m/%Y')

    def montant(self, types=frozenset({'string'}), forme=None):
        v = round(self.r.uniform(3000, 40000), 2)
        if forme is None:
            forme = 'nombre' if 'number' in types and ('string' not in types or self.r.random() < 0.5) else 'texte'
        if forme == 'nombre':
            return v
        texte = f'{v:,.2f}'
        if forme == 'dh':
            return texte.replace(',', ' ').replace('.', ',').replace(' ', '.') + ' DH'      # « 1.250,50 DH »
        return texte.replace(',', ' ').replace('.', ',')                                    # « 30 000,00 »

    def agregat(self):
        return {'%02d/2026' % m: round(self.r.uniform(2000, 30000), 2) for m in (7, 8, 9)}

    # -- identités --
    def individu(self, nom=None, adresse=None):
        ville = self.r.choice(VILLES_UTILES)[1].upper()
        return dict(prenom=self.r.choice(PRENOMS)[0], nom=nom or self.r.choice(self.g.familles)[0], cin=self.cin(),
                    naissance=self.date_txt(1955, 2000), ville=ville,
                    adresse=adresse or f'{self.r.randrange(1, 99)} RUE EXEMPLE {ville}')

    def du_registre(self, p):
        ville = p['ville'][1].upper()
        return dict(prenom=p['prenom'][0], nom=p['nom'][0], cin=p['cin'], ville=ville,
                    naissance=p['naissance'].strftime('%d/%m/%Y'), adresse=f'{1 + p["id"] % 90} RUE EXEMPLE {ville}')

    def employeur_hors_registre(self):
        self.n_employeur += 1
        ville = self.r.choice(VILLES_UTILES)[1].upper()
        mot = ''.join(self.g._syllabe()[0] for _ in range(3))
        return dict(nom=f'{mot} {self.n_employeur} EMPLOI SARL', ice='999%012d' % (500_000_000_000 + self.n_employeur),
                    adresse=f'{self.n_employeur} AVENUE EXEMPLE {ville}', ville=ville,
                    affiliation='999%07d' % self.n_employeur)

    def employeur_du_registre(self, s, avec_ice=True):
        ville = s['ville'][1].upper()
        return dict(nom=s['nom'], ice=s['ice'] if avec_ice else None, adresse=f'{1 + s["id"] % 90} RUE EXEMPLE {ville}',
                    ville=ville, affiliation='999%07d' % (1_000_000 + s['id']))

    def societe_du_registre(self, s):
        ville = s['ville'][1].upper()
        gerants = [self.du_registre(self.g.personnes[pid]) for pid, role, _ in s['personnes'] if role == 'gerant']
        return dict(nom=s['nom'], rc=s['rc'], tribunal=ville, ice=s['ice'], ville=ville,
                    adresse=f'{1 + s["id"] % 90} RUE EXEMPLE {ville}', gerants=gerants)

    def societe_hors_registre(self):
        e = self.employeur_hors_registre()
        gerant = self.individu()
        return dict(nom=e['nom'].replace('EMPLOI', 'NEGOCE'), rc=str(800_000 + self.n_employeur), tribunal=e['ville'],
                    ice=e['ice'], ville=e['ville'], adresse=e['adresse'], gerants=[gerant])

    # -- champs d'une pièce, d'après l'inventaire --
    def valeur(self, cle, types, sem):
        if cle in sem:
            return sem[cle]
        if types == {'null'}:
            return None
        if re.fullmatch(r'\d{2}/\d{4}', cle):
            return self.r.randrange(2000, 20000)
        if 'boolean' in types:
            return self.r.random() < 0.5
        if 'array' in types and 'string' not in types:
            return []
        if 'object' in types:
            return self.agregat() if 'string' in types else {}
        if cle.startswith('mois'):
            return '%02d/2026' % self.r.randrange(1, 10)
        if DATE_RE.search(cle):
            return self.date_txt()
        if MONTANT_RE.search(cle):
            return self.montant(types)
        if 'number' in types and 'string' not in types:
            return self.r.randrange(1, 9)
        if cle.startswith(('nombre', 'nbre', 'exemplaires')):
            return str(self.r.randrange(0, 4))
        return 'FICTIF ' + re.sub(r'[^A-Z ]', ' ', cle.upper()).strip()

    def champs(self, type_, source, sem, forcer=(), sans=()):
        inventaire = self.inventaire.get((type_, source), [])
        n_max = max((c['n'] for c in inventaire), default=1)
        champs = {}
        for c in inventaire:
            cle = c['key']
            if cle in sans:
                continue
            if cle not in forcer:
                if cle.startswith(('remeration.', 'revelation.')) or (type_ != 'CIN' and cle in CHAMPS_DE_CIN
                                                                     and type_ != 'CARTE_GRISE'):
                    continue                                   # clés des pièges T05 : seulement sur demande
                if self.r.random() >= c['n'] / n_max:
                    continue
                if self.r.random() >= c['non_null'] / max(c['n'], 1):
                    champs[cle] = None
                    continue
            champs[cle] = self.valeur(cle, c['types'], sem)
        return champs

    def piece(self, ref, type_, sem, source='AMONT', forcer=(), sans=(), statut='OK', rang=1):
        champs = self.champs(type_, 'AMONT', sem, forcer, sans)
        if source == 'REANALYSE':      # la relecture remplace la pièce : valeurs relues prioritaires, clés amont gardées
            champs.update(self.champs(type_, 'REANALYSE', sem, forcer, sans))
        identifiant = ID_AMONT.get(type_, 'eqdom_' + type_.lower()) + ('' if rang == 1 else f'_{rang}')
        return dict(upstreamPieceId=identifiant, type=type_, extractionStatus=statut,
                    pdfPath=f'af_{ref}_{type_}_{rang}.pdf', fields=champs, source=source)

    # -- sémantique des pièces : valeurs cohérentes avec les identités du dossier --
    @staticmethod
    def nom_complet(i):
        return f"{i['nom']} {i['prenom']}"

    def sem_cin(self, i):
        return dict(cin=i['cin'], id_document_recto=i['cin'], numero_cin=i['cin'], nom=i['nom'], prenom=i['prenom'],
                    date_naissance=i['naissance'], adresse=i['adresse'], ville_residence=i['ville'],
                    lieu_naissance=i['ville'], document_identite='CIN', mrz_document_number=i['cin'],
                    mrz_surname=i['nom'], mrz_name=i['prenom'])

    def sem_emploi(self, i, e, salaire):
        employeur = {'raison_sociale': e['nom'], 'adresse': e['adresse']}
        if e.get('ice'):
            employeur['ice'] = e['ice']        # prévu par le contrat Tandem (attestation : raison sociale, adresse, ICE)
        return {
            'nom': i['nom'], 'prenom': i['prenom'], 'numero_cin': i['cin'], 'date_naissance': i['naissance'],
            'employeur': employeur, 'raison_sociale': e['nom'], 'adresse_employeur': e['adresse'],
            'employeur.raison_sociale': e['nom'], 'employeur.nom': e['nom'], 'employeur.adresse': e['adresse'],
            'employe': {'nom_complet': self.nom_complet(i), 'cin': i['cin']},
            'employe.nom_complet': self.nom_complet(i), 'employe.cin': i['cin'],
            'salaire_net': salaire, 'salaire_net_mensuel': salaire, 'remuneration.salaire_net': salaire,
            'remuneration': {'salaire_brut': salaire, 'salaire_net': salaire, 'base_cnss': salaire},
            'numero_affiliation': e['affiliation'], 'numero_cnss': '999%06d' % self.r.randrange(1_000_000),
            'matricule': str(self.r.randrange(1000, 99999)), 'type_contrat': 'CDI', 'adresse_employe': i['adresse'],
            'employeur_actuel': e['nom'], 'assure': {'nom_complet': self.nom_complet(i)},
            'historique': [{'employeur': e['nom'], 'date_debut': self.date_txt(2015, 2020), 'date_fin': None,
                            'salaire_declare': salaire}],
        }

    def sem_releve(self, titulaire, rib, relu, mois=(7, 8, 9), tiers=None):
        liste = []
        for k, m in enumerate(mois):
            annee = 2025 if m >= 11 and 1 in mois else 2026
            entree = dict(mois=m, annee=annee, solde_ouverture=1000.0 + k, solde_cloture=1200.0 + k,
                          total_credit=9000.0, total_debit=8800.0)
            if relu:
                entree['operations'] = [
                    dict(date_operation='%02d/%02d' % (5, m), date_valeur='%02d/%02d' % (6, m),
                         libelle='VIREMENT RECU DE ' + (tiers or 'EMPLOYEUR FICTIF'), debit=None, credit=9000.0),
                    dict(date_operation='%02d/%02d' % (28, m), date_valeur='%02d/%02d' % (28, m),
                         libelle='PRELEVEMENT ECHEANCE CREDIT', debit=1500.0, credit=None)]
            liste.append(entree)
        return dict(titulaire_compte=titulaire, nom_prenom=titulaire, raison_sociale=titulaire, rib=rib,
                    numero_compte=rib, mois=liste, banque='BANQUE EXEMPLE', type_titulaire='PP',
                    total_mouvements_credit=self.agregat(), total_mouvements_debit=self.agregat(),
                    solde_fin_periode=self.agregat(), montant_salaire=self.agregat())

    def sem_societe(self, s):
        gerants = [dict(nom_complet=self.nom_complet(x), cin=x['cin'], qualite='gérant') for x in s['gerants']]
        dirigeants = [dict(type='PP', qualite='gérant', nom_gerant=x['nom'], prenom_gerant=x['prenom'],
                           numero_cin_gerant=x['cin'], date_naissance_gerant=x['naissance'],
                           adresse_gerant=x['adresse']) for x in s['gerants']]
        associes = [dict(nom_complet=self.nom_complet(x), cin=x['cin'], parts_sociales=500, nom=x['nom'],
                         prenom=x['prenom'], numero_cin=x['cin'], adresse=x['adresse']) for x in s['gerants']]
        return dict(nom_societe=s['nom'], denomination_sociale=s['nom'], siege_social=s['adresse'],
                    adresse_siege=s['adresse'], tribunal_commerce=s['tribunal'], ville_tribunal=s['tribunal'],
                    numero_analytique=s['rc'], numero_ice=s['ice'], ice=s['ice'], forme_juridique='SARL',
                    type_statuts='SARL', gerants=gerants, dirigeants=dirigeants, associes=associes, signataires=[],
                    adresse_principal_etablissement=s['adresse'])

    # -- un dossier --
    def controles(self, t):
        modele = (('IDT-01', 'IDENTITE', 'Cohérence de la CIN'), ('EMP-01', 'EMPLOI_REVENUS', 'Employeur déclaré'),
                  ('BNQ-01', 'BANCAIRE', 'Titulaire du compte'), ('BLG-02', 'BLACKLIST_GEO', 'Employeur en liste'))
        return [dict(id=self.uid(), controlId=cid, applicable=True, applicabilityReason=None, outcome='CONFORME',
                     criticality=None, escalade=None, explanation='Contrôle fictif.', details=None, missing=[],
                     source='MOTEUR', computedAt=self.iso(t), label=libelle, family=famille, numeroMetier=cid,
                     previousOutcome=None) for cid, famille, libelle in modele]

    def dossier(self, demandeur, csp='SALARIE_PRIVE', produit='DISPO', employeur=None, societe=None, rib=None,
                relu=(), mois=(7, 8, 9), chassis=None, agence='auto', statut='COMPLETE', actif=True, ref=None,
                quand=None, sem_en_plus=None, forcer_en_plus=None, vocabulaire=None, pieces_en_plus=(),
                cnss=False, domiciliation=None, rib_piece=None, declare='auto', statuts_pieces=None):
        """Construit un dossier et rend son détail ; `sem_en_plus[type]` et `forcer_en_plus[type]` servent aux pièges."""
        ref = ref or self.ref()
        t = quand or self.instant()
        sem_en_plus, forcer_en_plus = sem_en_plus or {}, forcer_en_plus or {}
        pm = societe is not None
        rib = rib or self.rib()
        salaire = self.montant()
        nom_client = societe['nom'] if pm else self.nom_complet(demandeur)
        if employeur is None and csp in ('SALARIE_PRIVE', 'FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE'):
            employeur = self.r.choice(self.employeurs)
        types = ['CIN']
        if pm:
            types += ['REGISTRE_COMMERCE', 'STATUTS'] + (['PV_ASSEMBLEE_GENERALE'] if self.r.random() < 0.3 else [])
        elif csp.startswith('RETRAITE'):
            types += ['ATTESTATION_PENSION']
        elif csp == 'PROFESSION_LIBERALE':
            types += ['CARTE_PROFESSIONNELLE']
        elif employeur:
            types += ['ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE'] + (['ATTESTATION_CNSS'] if cnss else [])
        types += ['RELEVE_BANCAIRE']
        if rib_piece if rib_piece is not None else self.r.random() < 0.4:
            types += ['ATTESTATION_RIB']
        if domiciliation if domiciliation is not None else self.r.random() < 0.4:
            types += ['DOMICILIATION']
        if produit != 'DISPO':
            types += ['FACTURE_PROFORMA_VEHICULE'] + (['CARTE_GRISE'] if chassis or self.r.random() < 0.4 else [])
        types += [x for x in pieces_en_plus if x not in types]

        pieces, mentions = [], []
        for k, type_ in enumerate(types):
            source = 'REANALYSE' if type_ in relu else 'AMONT'
            forcer, sans, sem = set(forcer_en_plus.get(type_, ())), set(), {}
            if type_ == 'CIN':
                sem, forcer = self.sem_cin(demandeur), forcer | {'cin', 'nom', 'prenom', 'date_naissance', 'adresse'}
                mentions.append(dict(piece=type_, role='demandeur' if not pm else 'gérant',
                                     nom_complet=self.nom_complet(demandeur), cin=demandeur['cin']))
            elif type_ in ('ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE', 'ATTESTATION_CNSS'):
                sem = self.sem_emploi(demandeur, employeur, salaire)
                forcer |= {'employeur', 'nom', 'prenom', 'numero_cin', 'raison_sociale', 'numero_affiliation'}
                mentions.append(dict(piece=type_, role='employeur', raison_sociale=employeur['nom'],
                                     ice=employeur.get('ice')))
            elif type_ == 'ATTESTATION_PENSION':
                sem = dict(nom=demandeur['nom'], prenom=demandeur['prenom'], numero_cin=demandeur['cin'],
                           adresse=demandeur['adresse'], date_naissance=demandeur['naissance'],
                           nom_organisme_retraite='CAISSE EXEMPLE', caisse='CAISSE EXEMPLE',
                           pensionne={'nom_complet': self.nom_complet(demandeur), 'cin': demandeur['cin']},
                           numero_pension='999%06d' % self.r.randrange(1_000_000), montant_pension_mensuel=salaire)
                forcer |= {'nom', 'prenom', 'numero_cin'}
            elif type_ == 'CARTE_PROFESSIONNELLE':
                sem = dict(nom=demandeur['nom'], prenom=demandeur['prenom'], numero_cin=demandeur['cin'],
                           nom_complet=self.nom_complet(demandeur), profession='PROFESSION FICTIVE')
                forcer |= {'nom', 'prenom', 'numero_cin'}
            elif type_ == 'RELEVE_BANCAIRE':
                sem = self.sem_releve(nom_client, rib, source == 'REANALYSE', mois, employeur and employeur['nom'])
                forcer |= {'rib', 'mois', 'titulaire_compte', 'raison_sociale', 'total_mouvements_credit'}
                mentions.append(dict(piece=type_, role='titulaire du compte', nom_complet=nom_client, rib=rib))
            elif type_ == 'ATTESTATION_RIB':
                sem = dict(rib=rib, titulaire_compte=nom_client, nom_prenom=nom_client, nom=demandeur['nom'],
                           prenom=demandeur['prenom'], banque='BANQUE EXEMPLE', raison_sociale=nom_client,
                           type_titulaire='PM' if pm else 'PP')
                forcer |= {'rib'}
            elif type_ == 'DOMICILIATION':
                sem = dict(nom=demandeur['nom'], prenom=demandeur['prenom'], numero_cin=demandeur['cin'],
                           adresse=demandeur['adresse'], adresse_complete=demandeur['adresse'], ville=demandeur['ville'],
                           titulaire=self.nom_complet(demandeur), raison_sociale='REGIE EXEMPLE')
                forcer |= {'adresse', 'nom', 'prenom'}
            elif type_ in ('REGISTRE_COMMERCE', 'STATUTS'):
                sem = self.sem_societe(societe)
                choix = vocabulaire or self.r.choice(('amont', 'moteur', 'les deux'))
                if type_ == 'REGISTRE_COMMERCE':
                    forcer |= {'numero_analytique'}
                    if choix == 'amont':
                        sans, forcer = RC_MOTEUR, forcer | {'nom_societe', 'tribunal_commerce', 'numero_ice', 'dirigeants'}
                    elif choix == 'moteur':
                        sans, forcer = RC_AMONT, forcer | {'denomination_sociale', 'ville_tribunal', 'ice', 'gerants'}
                    else:
                        forcer |= {'nom_societe', 'denomination_sociale', 'tribunal_commerce', 'ville_tribunal',
                                   'numero_ice', 'ice', 'gerants', 'dirigeants'}
                    mentions.append(dict(piece=type_, role='société', raison_sociale=societe['nom'], rc=societe['rc'],
                                         tribunal=societe['tribunal'], ice=societe['ice']))
                    mentions += [dict(piece=type_, role='gérant', nom_complet=self.nom_complet(x), cin=x['cin'])
                                 for x in societe['gerants']]
                else:
                    forcer |= {'gerants', 'associes', 'denomination_sociale'}
            elif type_ == 'FACTURE_PROFORMA_VEHICULE':
                sem = {'vehicule': {'marque': 'MARQUE FICTIVE', 'modele': 'MODELE FICTIF'},
                       'vehicule.marque': 'MARQUE FICTIVE', 'vehicule.modele': 'MODELE FICTIF',
                       'marque_vehicule': 'MARQUE FICTIVE', 'modele_vehicule': 'MODELE FICTIF',
                       'prix': {'prix_total_ttc': 185000.0}, 'prix.prix_total_ttc': 185000.0,
                       'vendeur': {'raison_sociale': 'CONCESSION EXEMPLE'}, 'nom_concessionnaire': 'CONCESSION EXEMPLE',
                       'acheteur': {'nom_complet': nom_client}, 'nom': demandeur['nom'], 'prenom': demandeur['prenom'],
                       'raison_sociale': 'CONCESSION EXEMPLE'}
            elif type_ == 'CARTE_GRISE':
                sem = {'Numéro de chassis': chassis or 'ZZFICTIF%09d' % self.r.randrange(10 ** 9),
                       'Marque véhicule': 'MARQUE FICTIVE', 'Modèle véhicule': 'MODELE FICTIF',
                       'Immatriculation': 'FICTIF-%05d' % self.r.randrange(100_000),
                       'Type carburant': 'DIESEL', 'Puissance fiscal': '8',
                       'nom': demandeur['nom'], 'prenom': demandeur['prenom']}
                forcer |= {'Numéro de chassis'}
            sem.update(sem_en_plus.get(type_, {}))
            statut_piece = (statuts_pieces or {}).get(k, 'OK')
            if type_ == 'PV_ASSEMBLEE_GENERALE':       # absent de l'inventaire : listes du README § 4
                qui = [dict(nom_complet=self.nom_complet(x), cin=x['cin']) for x in societe['gerants']]
                p = dict(upstreamPieceId='eqdom_pv_assemblee_generale', type=type_, extractionStatus=statut_piece,
                         pdfPath=f'af_{ref}_{type_}_1.pdf', source='AMONT',
                         fields=dict(associes_presents=qui, nouveau_gerant=qui[:1],
                                     resolutions=[dict(objet='Nomination du gérant', decision='adoptée')]))
            else:
                p = self.piece(ref, type_, sem, source, forcer, sans, statut_piece)
            pieces.append(p)

        fini = statut == 'COMPLETE'
        analyse = dict(id=self.uid(), matrixVersion='V1.0', engineVersion='2.8.0', trigger='INITIAL', status=statut,
                       verdict='CONFORME' if fini else None, provisional=False, startedAt=self.iso(t),
                       endedAt=self.iso(t + datetime.timedelta(minutes=2)) if fini else None, error=None)
        reanalyses = [dict(controlId='IDT-13', pieceId=p['upstreamPieceId'], requestedFields=sorted(p['fields'])[:3],
                           result=dict(avant={c: None for c in sorted(p['fields'])[:3]},
                                       apres={c: p['fields'][c] for c in sorted(p['fields'])[:3]}),
                           status='DONE', createdAt=self.iso(t), completedAt=self.iso(t))
                      for p in pieces if p['source'] == 'REANALYSE']
        if agence == 'auto':
            agence = dict(code='AG%02d' % self.r.randrange(1, 40), city=demandeur['ville'])
        if declare == 'auto':
            declare = dict(employer='VAB' if employeur else None, monthly_income=salaire if employeur else None,
                           pension_organism='CAISSE EXEMPLE' if csp.startswith('RETRAITE') else None)
        detail = dict(
            id=self.uid(), ref=ref, personType='PM' if pm else 'PP', csp=csp, productType=produit,
            paymentMode=self.r.choice(self.enums['payment_mode']), clientName=nom_client,
            agence=agence['city'] if agence else None,
            canal=self.r.choice(('PHYSIQUE', 'DIGITAL')) if agence else None,
            category=self.r.choice('ABCDE') if fini else None, categoryRule=self.r.randrange(1, 12) if fini else None,
            categoryReason='Règle fictive.' if fini else None, analysisStatus=statut,
            verdict='CONFORME' if fini else None, verdictProvisional=False, alertsMinor=0, alertsMajor=0,
            alertsCritical=0, commentaireScore=None, commentaireAlerte=False, matrixVersion='V1.0' if fini else None,
            businessReceivedAt=self.iso(t), resultsReceivedAt=self.iso(t), createdAt=self.iso(t), updatedAt=self.iso(t),
            businessData=dict(
                schema_version='1.0', dossier_ref=ref, person_type='PM' if pm else 'PP', csp=csp, product_type=produit,
                payment_mode='PRELEVEMENT_BANCAIRE',
                civil=dict(full_name=nom_client, cin='' if pm else demandeur['cin'], address=demandeur['adresse']),
                declared=declare, known_client=False, in_production=True,
                agency=agence or dict(code=None, city=None), sent_at=self.iso(t)),
            pieces=pieces, analyses=[analyse] if fini else [], reanalyses=reanalyses, synthese=None,
            latestAnalysis=dict(analyse, controls=self.controles(t)) if fini else None)
        self.entrees.append((t, ref, detail))
        self.finals[ref] = detail
        self.meta[ref] = dict(actif=actif)
        identites = [dict(role='société', type='PM', raison_sociale=societe['nom'], rc=societe['rc'], ice=societe['ice'])
                     if pm else dict(role='demandeur', type='PP', nom_complet=nom_client, cin=demandeur['cin'])]
        if employeur:
            identites.append(dict(role='employeur', type='PM', raison_sociale=employeur['nom'], ice=employeur.get('ice')))
        self._contexte = dict(ref=ref, identites=identites, mentions=mentions)
        return detail

    def nouvelle_version(self, ref, modifier, heures=2):
        """Version suivante d'un dossier (relecture, pièce ajoutée) : copie modifiée, datée plus tard."""
        detail = json.loads(json.dumps(self.finals[ref]))
        t = self.instant() + datetime.timedelta(hours=heures)
        modifier(detail)
        detail['updatedAt'] = self.iso(t)
        self.entrees.append((t, ref, detail))
        self.finals[ref] = detail
        return detail

    def noter(self, scenarios=(), pieges=(), liens=(), chemin=(), force=None, niveau='calcul', incoherences=(),
              controle=True, **notes):
        if niveau == 'calcul':
            niveau = niveau_de(force, len(chemin)) if force is not None else None
        self.verite.append(dict(self._contexte, scenarios=list(scenarios), pieges=list(pieges), liens=list(liens),
                                chemin=list(chemin), force=force, niveau=niveau, incoherences=list(incoherences),
                                notes=notes, controle=controle))

    # -- scénarios S01 à S24 --
    def scenarios(self):
        sc, R = self.sc, self.du_registre
        E = self.employeur_du_registre

        def lien(nature, a, b, poids):
            return dict(nature=nature, a=a, b=b, poids=poids)

        self.dossier(R(sc['x1']))
        self.noter(['S01'], force=1.0)
        self.dossier(self.societe_du_registre(sc['s2'])['gerants'][0], csp='SOCIETE',
                     societe=self.societe_du_registre(sc['s2']), vocabulaire='les deux')
        self.noter(['S02'], force=1.0)
        self.dossier(self.individu(), employeur=E(sc['s3']))
        self.noter(['S03'], force=1.0)
        self.dossier(self.individu(), employeur=E(sc['e4']))
        self.noter(['S04'], [], [lien('gérant', sc['e4']['ice'], sc['g4']['cin'], 0.7)], ['gérant'], 0.7)

        rib = self.rib()                                                   # S05 : 2 porteurs dont un inscrit
        self.dossier(R(sc['x5']), rib=rib); self.noter(['S05'], force=1.0)
        self.dossier(self.individu(), rib=rib)
        self.noter(['S05'], [], [lien('même RIB', rib, sc['x5']['cin'], 0.9)], ['même RIB'], 0.9)

        rib = self.rib()                                                   # S06 : 5 porteurs, 0,9 × √(2/5) ≈ 0,57
        self.dossier(R(sc['x6']), rib=rib); self.noter(['S06'], force=1.0)
        for _ in range(4):
            self.dossier(self.individu(), rib=rib)
            self.noter(['S06'], [], [lien('même RIB', rib, sc['x6']['cin'], 0.9)], ['même RIB'],
                       round(0.9 * cout(5), 5))

        self.dossier(self.individu(), employeur=E(sc['s7'][0]))           # S07 : 0,7 × coût(8) × 0,7 = 0,245
        self.noter(['S07'], [], [lien('gérant', sc['s7'][0]['ice'], sc['p7']['cin'], 0.7),
                                 lien('gérant', sc['p7']['cin'], sc['s7'][1]['ice'], 0.7)], ['gérant', 'gérant'],
                   round(0.7 * cout(8) * 0.7, 5), cin_du_pont=sc['p7']['cin'])
        self.dossier(self.individu(), employeur=E(sc['s8'][0]))           # S08 : 0,5 × √(2/40) × 0,5 ≈ 0,0559
        self.noter(['S08'], [], [lien('liquidateur', sc['s8'][0]['ice'], sc['l8']['cin'], 0.5),
                                 lien('liquidateur', sc['l8']['cin'], sc['s8'][1]['ice'], 0.5)],
                   ['liquidateur', 'liquidateur'], round(0.5 * cout(40) * 0.5, 5), cin_du_pont=sc['l8']['cin'])
        self.dossier(self.individu(), employeur=E(sc['e9']))              # S09 : 3 liens forts, plafond « mineure »
        self.noter(['S09'], [], [lien('gérant', sc['e9']['ice'], sc['g9']['cin'], 0.7),
                                 lien('gérant', sc['g9']['cin'], sc['b9']['ice'], 0.7),
                                 lien('gérant', sc['b9']['ice'], sc['x9']['cin'], 0.7)], ['gérant'] * 3,
                   round(0.7 ** 3, 5))
        self.dossier(self.individu(), employeur=E(sc['e10']))             # S10 : 4 liens, jamais d'alerte
        self.noter(['S10'], [], [lien('gérant', sc['e10']['ice'], sc['g10']['cin'], 0.7),
                                 lien('gérant', sc['g10']['cin'], sc['b10']['ice'], 0.7),
                                 lien('associé', sc['b10']['ice'], sc['h10']['cin'], 0.5),
                                 lien('gérant', sc['h10']['cin'], sc['c10']['ice'], 0.7)],
                   ['gérant', 'gérant', 'associé', 'gérant'], round(0.7 * 0.7 * 0.5 * 0.7, 5))
        self.dossier(self.individu(), employeur=E(sc['e11']))             # S11 : homonymie à un bout
        self.noter(['S11'], [], [lien('gérant', sc['e11']['ice'], 'nom et ville', 0.7)], ['gérant'], None, 'mineure',
                   mention='homonymie à lever', si_meme_personne='majeure', si_homonyme_ecarte=None)
        self.dossier(self.individu(), employeur=E(sc['i12'], avec_ice=False))   # S12 : employeur par son seul nom
        self.noter(['S12'], niveau='mineure', mention='homonymie à lever (employeur reconnu par son nom)')

        for s, x in (('S13', 'x13'), ('S14', 'x14')):                     # foyer : même nom, même logement
            inscrit, rib = R(sc[x]), self.rib()
            self.dossier(inscrit, rib=rib, domiciliation=True); self.noter([s], force=1.0)
            proche = self.individu(nom=inscrit['nom'], adresse=inscrit['adresse'])
            proche['ville'] = inscrit['ville']
            if s == 'S13':
                self.dossier(proche, domiciliation=True)
                self.noter([s], [], [lien('même logement', inscrit['adresse'], inscrit['cin'], 0.1)], ['même logement'],
                           0.1, mention='même foyer qu\'un inscrit')
            else:                                                          # argent au poids plein
                self.dossier(proche, rib=rib, domiciliation=True)
                self.noter([s], [], [lien('même RIB', rib, inscrit['cin'], 0.9)], ['même RIB'], 0.9,
                           mention='même foyer, même RIB')

        rib = self.rib()                                                   # S15 : inscription « victime »
        self.dossier(R(sc['v15']), rib=rib); self.noter(['S15'], force=1.0)
        self.dossier(self.individu(), rib=rib)
        self.noter(['S15'], [], [lien('même RIB', rib, sc['v15']['cin'], 0.9)], ['même RIB'], 0.9, provisoire=True,
                   regle='au-delà de 0 lien : selon le paramètre (provisoire : propage)')

        rib = self.rib()                                                   # S16 : les deux ordres d'arrivée
        self.dossier(R(sc['x16a']), rib=rib); self.noter(['S16'], force=1.0)
        self.dossier(self.individu(), rib=rib)
        self.noter(['S16'], [], [lien('même RIB', rib, sc['x16a']['cin'], 0.9)], ['même RIB'], 0.9,
                   ordre='inscrit d\'abord', attendu='relié à l\'arrivée')
        rib = self.rib()
        self.dossier(self.individu(), rib=rib)
        self.noter(['S16'], [], [lien('même RIB', rib, sc['x16b']['cin'], 0.9)], ['même RIB'], 0.9,
                   ordre='inscrit ensuite', attendu='nouvellement relié')
        self.dossier(R(sc['x16b']), rib=rib); self.noter(['S16'], force=1.0)

        lu_de_travers = dict(self.individu(), cin=sc['x17']['cin'])        # S17 : relecture qui change le CIN
        d = self.dossier(lu_de_travers)
        contexte, vrai_cin = self._contexte, self.cin()

        def relire(detail):
            p = next(p for p in detail['pieces'] if p['type'] == 'CIN')
            p['source'] = 'REANALYSE'
            for cle in ('cin', 'id_document_recto', 'mrz_document_number'):
                if cle in p['fields']:
                    p['fields'][cle] = vrai_cin
            detail['businessData']['civil']['cin'] = vrai_cin
            detail['reanalyses'].append(dict(controlId='IDT-13', pieceId=p['upstreamPieceId'], requestedFields=['cin'],
                                             result=dict(avant={'cin': sc['x17']['cin']}, apres={'cin': vrai_cin}),
                                             status='DONE', createdAt=detail['createdAt'],
                                             completedAt=detail['createdAt']))
        self.nouvelle_version(d['ref'], relire)
        contexte['identites'][0]['cin'] = vrai_cin
        contexte['mentions'][0]['cin'] = vrai_cin
        self._contexte = contexte
        self.noter(['S17'], niveau=None, niveau_avant_relecture='critique',
                   attendu='anciennes arêtes retirées ; état égal au lot')

        chassis = 'ZZFICTIFDOUBLE001'                                      # S18 : même châssis, deux dossiers
        for _ in range(2):
            self.dossier(self.individu(), produit='AUTO_CLASSIQUE', chassis=chassis)
            self.noter(['S18'], incoherences=['double financement'])

        rib = self.rib()                                                   # S19 : rafale, sans inscrit
        for _ in range(3):
            self.dossier(self.individu(), rib=rib)
            self.noter(['S19'], signaux=['dossiers en rafale'])

        employeur = E(sc['e20'])                                           # S20 : employeur de plus de 200 dossiers
        for _ in range(201):
            self.dossier(self.individu(), employeur=employeur)
            self.noter(['S20'], [], [lien('gérant', sc['e20']['ice'], sc['g20']['cin'], 0.7)], ['gérant'], 0.7,
                       propagation='nuit')

        self.dossier(self.individu(), statut='EN_COURS')                   # S21 : analyse non terminée
        self.noter(['S21'], attendu='stocké, dessiné « en cours », sans contrôle ni alerte')
        self.dossier(self.individu(), actif=False)                         # S22 : dossier archivé
        self.noter(['S22'], attendu='repris, marqué')

        rib = self.rib()                                                   # S23 : levée, puis chemin d'une autre nature
        self.dossier(R(sc['g23']), rib=rib); self.noter(['S23'], force=1.0)
        d = self.dossier(self.individu(), employeur=E(sc['e23']))
        contexte = self._contexte

        def meme_rib(detail):
            for p in detail['pieces']:
                if p['type'] in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB'):
                    for cle in ('rib', 'numero_compte'):
                        if cle in p['fields']:
                            p['fields'][cle] = rib
        self.nouvelle_version(d['ref'], meme_rib, heures=48)
        self._contexte = contexte
        self.noter(['S23'], [], [lien('gérant', sc['e23']['ice'], sc['g23']['cin'], 0.7),
                                 lien('même RIB', rib, sc['g23']['cin'], 0.9)], ['même RIB'], 0.9,
                   apres_levee='rouvre', premier_chemin='gérant (0,7), levé par l\'analyste')

        agence = dict(code='AG99', city='CASABLANCA')                      # S24 : même point de vente, hors score
        self.dossier(R(sc['x24']), agence=agence); self.noter(['S24'], force=1.0)
        self.dossier(self.individu(), agence=agence)
        self.noter(['S24'], niveau=None, mention='même point de vente qu\'un inscrit, hors score')

    # -- pièges T01 à T15, sur des dossiers sans lien avec la liste noire --
    def pieges(self):
        def note(*t):
            self.noter([], t, controle=False)

        self.dossier(self.individu(), relu=('RELEVE_BANCAIRE',), mois=(11, 12, 1)); note('T01', 'T10')
        self.dossier(self.individu(), relu=('RELEVE_BANCAIRE',)); note('T01', 'T10')
        self.dossier(self.individu()); note('T02')
        deux = [self.sem_cin(self.individu()) for _ in range(2)]
        self.dossier(self.individu(), sem_en_plus={'CIN': {'cartes': None}}); note('T03')
        self.finals[self._contexte['ref']]['pieces'][0]['fields']['cartes'] = [
            {c: x[c] for c in ('nom', 'prenom', 'cin', 'date_naissance', 'adresse')} for x in deux]
        doubles = {'ATTESTATION_TRAVAIL_SALAIRE': {'employeur', 'employeur.raison_sociale'},
                   'BULLETIN_DE_PAIE': {'remuneration', 'remuneration.salaire_net'},
                   'FACTURE_PROFORMA_VEHICULE': {'vehicule', 'vehicule.marque', 'prix', 'prix.prix_total_ttc'}}
        self.dossier(self.individu(), produit='AUTO_CLASSIQUE', relu=tuple(doubles), forcer_en_plus=doubles)
        note('T04', 'T10')
        inventees = {'BULLETIN_DE_PAIE': {'remeration.salaire_net'},
                     'ATTESTATION_TRAVAIL_SALAIRE': {'revelation.salaire_brut'},
                     'ATTESTATION_RIB': {'filiation_complete', 'date_expiration'},
                     'DOMICILIATION': {'filiation_complete', 'date_expiration'},
                     'CARTE_PROFESSIONNELLE': {'filiation_complete', 'date_expiration'}}
        self.dossier(self.individu(), relu=tuple(inventees), forcer_en_plus=inventees, rib_piece=True,
                     domiciliation=True, pieces_en_plus=('CARTE_PROFESSIONNELLE',)); note('T05', 'T10')
        self.dossier(self.individu(), relu=('BULLETIN_DE_PAIE',), sem_en_plus={
            'ATTESTATION_TRAVAIL_SALAIRE': {'salaire_net': self.montant(forme='dh'),
                                            'salaire_net_mensuel': self.montant(forme='texte')},
            'BULLETIN_DE_PAIE': {'salaire_net': self.montant(forme='nombre')}},
            forcer_en_plus={'ATTESTATION_TRAVAIL_SALAIRE': {'salaire_net', 'salaire_net_mensuel'},
                            'BULLETIN_DE_PAIE': {'salaire_net'}}); note('T06', 'T10')
        self.dossier(self.individu(), sem_en_plus={'ATTESTATION_TRAVAIL_SALAIRE': {
            'date_attestation': '12/03', 'date_embauche': '01/09/2019'}},
            forcer_en_plus={'ATTESTATION_TRAVAIL_SALAIRE': {'date_attestation', 'date_embauche'}}); note('T07')
        for vocabulaire, relu in (('amont', ()), ('moteur', ()), ('les deux', ('REGISTRE_COMMERCE',))):
            s = self.societe_hors_registre()
            self.dossier(s['gerants'][0], csp='SOCIETE', societe=s, vocabulaire=vocabulaire, relu=relu,
                         produit='LOA', chassis='ZZFICTIF%09d' % self.r.randrange(10 ** 9))
            note('T08', *(('T10',) if relu else ()))
        self.dossier(self.individu()); note('T09')
        s = self.societe_hors_registre()                                   # T11 : contexte amont partiel
        self.dossier(s['gerants'][0], csp='SOCIETE', societe=s); note('T11')
        self.dossier(self.individu(), declare=dict(employer=None, monthly_income=None, pension_organism=None))
        note('T11')
        self.dossier(self.individu(), declare=dict(employer='VAB', monthly_income=None, pension_organism=None))
        note('T11')
        self.dossier(self.individu(), csp='RETRAITE_INDETERMINE'); note('T11')
        gabarit = dict(self.individu(), nom='DOE', prenom='JOHN')          # T12 : valeurs gabarits
        self.dossier(gabarit, sem_en_plus={'CIN': {'cin': 'N/A', 'id_document_recto': 'N/A'}})
        self._contexte['identites'][0]['cin'] = None
        note('T12')
        self.dossier(self.individu(), rib_piece=True, domiciliation=True,
                     statuts_pieces={0: 'OK', 1: 'PARTIAL', 2: 'FAILED'}); note('T13')
        self.dossier(self.individu(), statut='EN_COURS'); note('T14')
        self.dossier(self.individu(), actif=False); note('T14')
        self.dossier(self.individu(), agence=None); note('T15')

    def remplissage(self, n):
        csps = self.enums['csp']
        for _ in range(n):
            csp = self.r.choice(csps)
            produit = self.r.choice(self.enums['product_type'])
            if csp == 'SOCIETE':
                s = self.societe_hors_registre()
                self.dossier(s['gerants'][0], csp=csp, societe=s, produit=produit)
            else:
                self.dossier(self.individu(), csp=csp, produit=produit, cnss=self.r.random() < 0.3)
            self.noter(controle=False)


def generer(n_dossiers=1000, n_societes=61043, graine=GRAINE, structure=None):
    structure = structure_kamal(structure)
    if n_dossiers < MINIMUM_DOSSIERS:
        raise ValueError(f'il faut au moins {MINIMUM_DOSSIERS} dossiers pour porter tous les scénarios')
    monde, scenes = construire_monde(n_societes, graine)
    f = Fabrique(monde, scenes, charger_inventaire(structure), charger_enumerations(structure), graine)
    f.scenarios()
    f.pieges()
    f.remplissage(n_dossiers - len(f.finals))
    from pipeline import modeles_v2
    cles_liste = [c.alias or n for n, c in modeles_v2.Dossier.model_fields.items()]
    dossiers = [f.finals[ref] for ref in f.finals]
    actifs = [d for d in dossiers if f.meta[d['ref']]['actif']]

    def compter(cle):
        comptes = {}
        for d in actifs:
            if d[cle] is not None:
                comptes[d[cle]] = comptes.get(d[cle], 0) + 1
        return comptes
    liste = dict(items=[{c: d[c] for c in cles_liste} for d in actifs], total=len(actifs),
                 counts=dict(verdict=compter('verdict'), status=compter('analysisStatus'), category=compter('category')))
    versions = {}
    chronologie = []
    for t, ref, detail in sorted(f.entrees, key=lambda e: (e[0], e[1])):
        versions[ref] = versions.get(ref, 0) + 1
        chronologie.append(dict(instant=Fabrique.iso(t), ref=ref, version=versions[ref], dossier=detail))
    return Jeu(monde, dossiers, chronologie, f.verite, f.meta, liste)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--sortie', required=True)
    ap.add_argument('--dossiers', type=int, default=1000)
    ap.add_argument('--societes', type=int, default=61043)
    ap.add_argument('--graine', type=int, default=GRAINE)
    a = ap.parse_args(argv)
    try:
        jeu = generer(a.dossiers, a.societes, a.graine)
    except PrealableManquant as e:
        print(f'arrêt : {e}', file=sys.stderr)
        return 2
    except ValueError as e:                    # jamais le texte : il pourrait citer une valeur lue
        print(f'arrêt : {type(e).__name__} (au moins {MINIMUM_DOSSIERS} dossiers ; inventaire de Kamal lisible ?)',
              file=sys.stderr)
        return 2
    os.makedirs(a.sortie, exist_ok=True)
    g = jeu.monde
    ecrire_csv(os.path.join(a.sortie, 'liste_noire.csv'), g.bl, COLONNES_BL)
    ecrire_csv(os.path.join(a.sortie, 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    ecrire_csv(os.path.join(a.sortie, 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    for nom, objet in (('dossiers', jeu.dossiers), ('liste', jeu.liste), ('chronologie', jeu.chronologie),
                       ('verite_v2', dict(graine=a.graine, dossiers=jeu.verite, meta=jeu.meta))):
        with open(os.path.join(a.sortie, nom + '.json'), 'w', encoding='utf-8') as f:
            json.dump(objet, f, ensure_ascii=False, indent=1)
    print(f'dossiers : {len(jeu.dossiers)} ; versions : {len(jeu.chronologie)} ; sociétés du registre : '
          f'{len(g.societes)} ; inscriptions : {len(g.bl)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
