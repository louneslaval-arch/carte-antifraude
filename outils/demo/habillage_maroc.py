"""Habillage marocain de la démonstration (Lounès, 23/11/2026 : « prépare le fichier HTML avec de la fake data
marocaine »). Les dossiers du générateur portent des valeurs génériques (« 12 RUE EXEMPLE FÈS », « BANQUE EXEMPLE »,
« FICTIF FONCTION ») et des relevés tirés au hasard, sans lien avec le salaire. Ici, pour la seule démonstration :

- adresses : rue ou avenue, quartier et ville vraisemblables ; une même adresse donne toujours la même, deux adresses
  distinctes restent distinctes (aucun foyer créé par hasard) ; le socle (registre, liste noire) reçoit les mêmes ;
- banques, fonctions, situation familiale, professions libérales, caisses de retraite, véhicules : valeurs
  vraisemblables ; noms de banque inventés ;
- relevés : salaire versé proche du salaire déclaré (quelques écarts voulus), échéances de crédit constantes, soldes
  enchaînés d'un mois à l'autre.

Les identifiants restent ceux du générateur (CIN et références en « ZZ », RIB, ICE et n° CNSS en « 999 ») ; une valeur
piège en texte (format de montant à lire) n'est pas réécrite. Déterministe : chaque tirage dépend de la valeur habillée,
jamais de l'ordre. Le générateur du jeu d'essai, ses pièges et ses résultats attendus ne changent pas."""
import hashlib
import random
import re

import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
from pipeline.normalisation.valeurs import montant  # noqa: E402

ADRESSE = re.compile(r'^(\d+) (RUE|AVENUE) EXEMPLE (.+)$')
RUES = ('IBN BATOUTA', 'IBN KHALDOUN', 'AL MOUTANABBI', 'ABOU BAKR ESSEDDIK', 'OMAR IBN EL KHATTAB', 'IBN SINA',
        'AL FARABI', 'IBN ROCHD', 'EL MANSOUR', 'TARIK IBN ZIYAD', 'AL QODS', 'OUED ZIZ', 'OUED SEBOU', 'MOULAY ISMAIL',
        'ALLAL BEN ABDELLAH', 'IMAM MALIK', 'JABAL TOUBKAL', 'AL KHANSAA', 'ABDELKRIM EL KHATTABI', 'IBN ZOHR',
        'AHMED CHAWKI', 'AL WAHDA', 'LALLA YACOUT', 'EL ANDALOUS', 'IBN TOUMERT', 'AL MOUKAWAMA', 'OUED DRAA',
        'AL BOUSTANE', 'ESSAADIENS', 'AL AKHAWAYN', 'IBN ARABI', 'ABOU INANE', 'AL YASMINE', 'AL ARZ', 'SIDI BELYOUT')
AVENUES = ('HASSAN II', 'MOHAMMED V', 'DES FAR', 'ZERKTOUNI', 'MOULAY YOUSSEF', 'ABDELMOUMEN', 'MOHAMMED VI',
           'ALLAL EL FASSI', 'DE LA RÉSISTANCE', 'YOUSSEF IBN TACHFINE', 'AL MASSIRA', 'MOULAY RACHID', 'MOULAY ABDELLAH',
           'DES NATIONS UNIES', 'AL JAÂMIAA')
QUARTIERS = {
    'CASABLANCA': ('MAÂRIF', 'GAUTHIER', 'BOURGOGNE', 'AÏN SEBAÂ', 'HAY HASSANI', 'SIDI MAÂROUF', 'OULFA', 'AÏN CHOCK',
                   'HAY MOHAMMADI', 'CALIFORNIE', 'BERNOUSSI'),
    'RABAT': ('AGDAL', 'HAY RIAD', 'HASSAN', 'L’OCÉAN', 'YACOUB EL MANSOUR', 'SOUISSI', 'AKKARI'),
    'FÈS': ('FÈS JDID', 'NARJISS', 'SAÏSS', 'ATLAS', 'ZOUAGHA', 'AÏN CHKEF', 'BENSOUDA'),
    'MARRAKECH': ('GUÉLIZ', 'DAOUDIATE', 'MHAMID', 'HIVERNAGE', 'SYBA', 'MASSIRA', 'ISSIL'),
    'TANGER': ('MALABATA', 'IBERIA', 'BENI MAKADA', 'MARSHAN', 'MESNANA', 'BOUKHALEF'),
    'AGADIR': ('TALBORJT', 'DAKHLA', 'HAY MOHAMMADI', 'CHARAF', 'TILILA'),
    'MEKNÈS': ('HAMRIA', 'MARJANE', 'BASSATINE', 'SIDI BOUZEKRI', 'ZITOUNE'),
    'OUJDA': ('HAY EL QODS', 'LAZARET', 'SIDI MAAFA', 'HAY ANDALOUS'),
    'KÉNITRA': ('MAAMORA', 'OULED OUJIH', 'BIR RAMI', 'MIMOSAS', 'VALLÉE'),
    'TÉTOUAN': ('MHANNECH', 'TOUABEL', 'SANIAT RMEL', 'KORRAT SBAA'),
}
QUARTIERS_COMMUNS = ('HAY ESSALAM', 'HAY AL AMAL', 'HAY NAHDA', 'QUARTIER ADMINISTRATIF', 'HAY AL WAFAE', 'HAY EL FATH',
                     'LOTISSEMENT AL MANAR', 'HAY AL MASSIRA')
BANQUES = ('BANQUE DES OASIS', 'CRÉDIT DU DÉTROIT', 'BANQUE CHAOUIA', 'UNION BANCAIRE DU SOUSS', 'BANQUE DU MOYEN ATLAS',
           'BANQUE DU RIF ORIENTAL', 'CRÉDIT DES DEUX RIVES', 'BANQUE TANSIFT')
FONCTIONS = {
    'FONCTIONNAIRE': ('ADMINISTRATEUR', 'PROFESSEUR DE L’ENSEIGNEMENT SECONDAIRE', 'INFIRMIER', 'TECHNICIEN', 'ADJOINT ADMINISTRATIF',
                      'INGÉNIEUR D’ÉTAT', 'INSTITUTEUR', 'RÉDACTEUR'),
    'MILITAIRE': ('ADJUDANT', 'SERGENT-CHEF', 'CAPORAL-CHEF', 'LIEUTENANT', 'CAPITAINE'),
    'EMPLOYE_COMMUNE': ('AGENT TECHNIQUE', 'ADJOINT ADMINISTRATIF', 'TECHNICIEN', 'RÉDACTEUR', 'CHAUFFEUR'),
    'SALARIE_PRIVE': ('COMPTABLE', 'TECHNICIEN DE MAINTENANCE', 'CHEF DE RAYON', 'AGENT COMMERCIAL', 'RESPONSABLE LOGISTIQUE',
                      'CONSEILLER CLIENTÈLE', 'MAGASINIER', 'INGÉNIEUR D’ÉTUDES', 'ASSISTANT DE DIRECTION', 'CHAUFFEUR LIVREUR',
                      'OPÉRATEUR DE PRODUCTION', 'CHEF D’ÉQUIPE', 'TÉLÉCONSEILLER', 'CONTRÔLEUR DE GESTION'),
}
SITUATIONS = ('MARIÉ(E)', 'MARIÉ(E)', 'MARIÉ(E)', 'CÉLIBATAIRE', 'CÉLIBATAIRE', 'DIVORCÉ(E)', 'VEUF(VE)')
PROFESSIONS = (('MÉDECIN GÉNÉRALISTE', 'SANTÉ'), ('PHARMACIEN', 'SANTÉ'), ('CHIRURGIEN-DENTISTE', 'SANTÉ'),
               ('KINÉSITHÉRAPEUTE', 'SANTÉ'), ('AVOCAT', 'JURIDIQUE'), ('NOTAIRE', 'JURIDIQUE'),
               ('ARCHITECTE', 'BÂTIMENT'), ('EXPERT-COMPTABLE', 'CONSEIL'), ('VÉTÉRINAIRE', 'SANTÉ'),
               ('INGÉNIEUR-CONSEIL', 'CONSEIL'))
CAISSES = dict(RETRAITE_PUBLIC='CMR', RETRAITE_CIMR='CIMR')
VEHICULES = (('DACIA', 'LOGAN'), ('DACIA', 'SANDERO'), ('RENAULT', 'CLIO'), ('PEUGEOT', '208'), ('HYUNDAI', 'ACCENT'),
             ('KIA', 'PICANTO'), ('TOYOTA', 'YARIS'), ('FIAT', 'TIPO'), ('CITROËN', 'C3'), ('VOLKSWAGEN', 'POLO'))
REMPLACEMENTS = {'REGIE EXEMPLE': 'RÉGIE DE DISTRIBUTION D’EAU ET D’ÉLECTRICITÉ', 'CONCESSION EXEMPLE': 'GARAGE DU DÉTROIT',
                 'FICTIF ETAT VEHICULE': 'NEUF', 'FICTIF TYPE CARBURANT': 'DIESEL', 'CAISSE EXEMPLE': 'CNSS'}
OBJETS = (('TRAVAUX', 'Travaux de construction et de génie civil'), ('NEGOCE', 'Négoce de matériaux et import-export'),
          ('TRANSPORT', 'Transport de marchandises pour le compte d’autrui'), ('SERVICES', 'Services aux entreprises'),
          ('IMMOBILIER', 'Promotion immobilière'), ('COMMERCE', 'Commerce de détail de produits alimentaires'))
OBJETS_AUTRES = ('Conseil et services informatiques', 'Location de voitures sans chauffeur', 'Restauration et traiteur',
                 'Import-export de textiles', 'Entretien et nettoyage de locaux', 'Distribution de produits agricoles')
SALARIES = frozenset({'SALARIE_PRIVE', 'FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE'})


def _rng(*cles):
    """Tirage qui ne dépend que des clés données (jamais de l'ordre de passage)."""
    return random.Random(int(hashlib.sha256('|'.join(map(str, cles)).encode()).hexdigest()[:16], 16))


def _choix(liste, *cles):
    return _rng(*cles).choice(liste)


class Habillage:
    """Mémoire des adresses déjà habillées : une adresse donnée garde sa forme, deux adresses ne se rejoignent jamais."""

    def __init__(self):
        self.adresses, self.prises, self.local = {}, set(), {}

    # ---- adresses et textes ---------------------------------------------------------------------------------------
    def texte(self, s):
        if not isinstance(s, str):
            return s
        if s in self.local:
            return self.local[s]
        if s in REMPLACEMENTS:
            return REMPLACEMENTS[s]
        m = ADRESSE.match(s)
        if not m:
            return s
        if s not in self.adresses:
            n, voie, ville = int(m.group(1)), m.group(2), m.group(3).strip()
            r = _rng('adresse', s)
            nom = r.choice(RUES if voie == 'RUE' else AVENUES)
            quartier = r.choice(QUARTIERS.get(ville, QUARTIERS_COMMUNS))
            numero = 1 + n % 180
            while True:
                sortie = f'{numero} {voie} {nom}, {quartier}, {ville}'
                if sortie not in self.prises:
                    break
                numero += 1
            self.adresses[s] = sortie
            self.prises.add(sortie)
        return self.adresses[s]

    def _profond(self, x):
        if isinstance(x, dict):
            return {k: self._profond(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self._profond(v) for v in x]
        return self.texte(x)

    def ligne(self, ligne):
        """Une ligne du socle (registre, liste noire) : mêmes adresses que les dossiers."""
        return {k: self.texte(v) for k, v in ligne.items()}

    # ---- un dossier -----------------------------------------------------------------------------------------------
    def dossier(self, d):
        bd = d.get('businessData') or {}
        csp = d.get('csp') or bd.get('csp')
        ref = d.get('ref')
        declare = bd.get('declared') or {}
        salaire = montant(declare.get('monthly_income'))
        for p in d.get('pieces') or []:
            champs = p.get('fields') or {}
            if not salaire:
                for cle in ('salaire_net_mensuel', 'salaire_net', 'montant_pension_mensuel'):
                    if not salaire and not isinstance(champs.get(cle), (dict, list)):
                        salaire = montant(champs.get(cle))
        civil = bd.get('civil') or {}
        personne = civil.get('cin') or ref
        rib = next((p['fields'].get('rib') for p in d.get('pieces') or [] if (p.get('fields') or {}).get('rib')), ref)
        profession, secteur = _choix(PROFESSIONS, 'profession', personne)
        vehicule = _choix(VEHICULES, 'vehicule', ref)
        r = _rng('source', ref)
        source_ = round(salaire * r.uniform(0.04, 0.12), 2) if salaire and r.random() < 0.25 else 0
        self.local = {'BANQUE EXEMPLE': _choix(BANQUES, 'banque', rib),
                      'FICTIF FONCTION': _choix(FONCTIONS.get(csp, FONCTIONS['SALARIE_PRIVE']), 'fonction', personne),
                      'FICTIF SITUATION FAMILIALE': _choix(SITUATIONS, 'situation', personne),
                      'PROFESSION FICTIVE': profession, 'FICTIF SECTEUR': secteur,
                      'CAISSE EXEMPLE': CAISSES.get(csp, 'CNSS'), 'FICTIF CREDITS SOURCE': source_,
                      'MARQUE FICTIVE': vehicule[0], 'MODELE FICTIF': vehicule[1],
                      'FICTIF ADRESSE': self.texte(civil.get('address')) if civil.get('address') else None,
                      'FICTIF NUMERO INPE': '999%06d' % _rng('inpe', personne).randrange(10 ** 6)}
        nom = str(d.get('clientName') or '')
        objet = next((o for mot, o in OBJETS if mot in nom), None) or _choix(OBJETS_AUTRES, 'objet', nom)
        self.local.update({'FICTIF OBJET COMMERCE': objet, 'FICTIF OBJET SOCIAL': objet, 'FICTIF OBJET': objet})
        pm = d.get('personType') == 'PM' or bd.get('person_type') == 'PM'
        for p in d.get('pieces') or []:
            if p.get('type') == 'RELEVE_BANCAIRE':
                self._releve(p.get('fields') or {}, ref, salaire, pm, csp)
        try:
            return self._profond(d)
        finally:
            self.local = {}

    def _releve(self, champs, ref, salaire, pm, csp):
        """Relevés cohérents : salaire versé proche du déclaré (25 % d'écarts voulus), échéances constantes, soldes
        enchaînés. Une valeur piège (agrégat écrit en texte) reste telle quelle."""
        mois = [m for m in champs.get('mois') or [] if isinstance(m, dict)]
        if not mois:
            return
        r = _rng('releve', ref, champs.get('rib'))
        if pm:
            base = r.uniform(80_000, 600_000)
        else:
            base = salaire or r.uniform(9_000, 40_000)
        tirage = r.random()
        part_salaire = (0.97, 1.0) if tirage < 0.72 else (0.82, 0.9) if tirage < 0.9 else (0.6, 0.75)
        tirage = r.random()
        part_echeances = 0.0 if tirage < 0.25 else r.uniform(0.12, 0.34) if tirage < 0.85 else r.uniform(0.42, 0.6)
        if pm:
            part_echeances = r.uniform(0.02, 0.1)
        echeance = round(base * part_echeances, 2)
        solde = round(r.uniform(800, 0.6 * base), 2)
        agregats = {k: {} for k in ('montant_salaire', 'montant_echeances_credits', 'somme_echeance_credits',
                                    'solde_fin_periode', 'total_mouvements_credit', 'total_mouvements_debit')}
        for m in mois:
            cle = '%02d/%s' % (int(m.get('mois') or 0), m.get('annee'))
            verse = round(base * r.uniform(*part_salaire), 2) if not pm else None
            entrees = round((verse or base * r.uniform(0.85, 1.15)) + base * r.uniform(0, 0.12), 2)
            sorties = round(min(entrees + solde - 200, entrees * r.uniform(0.9, 1.06)), 2)
            m.update(solde_ouverture=solde, total_credit=entrees, total_debit=sorties,
                     solde_cloture=round(solde + entrees - sorties, 2))
            for o in m.get('operations') or []:
                if o.get('credit'):
                    o['credit'] = verse or entrees
                elif o.get('debit'):
                    o['debit'] = echeance or round(base * 0.02, 2)
            if verse is not None:
                agregats['montant_salaire'][cle] = verse
            agregats['montant_echeances_credits'][cle] = agregats['somme_echeance_credits'][cle] = echeance
            agregats['solde_fin_periode'][cle] = m['solde_cloture']
            agregats['total_mouvements_credit'][cle], agregats['total_mouvements_debit'][cle] = entrees, sorties
            solde = m['solde_cloture']
        for cle, valeurs in agregats.items():
            if isinstance(champs.get(cle), dict):
                champs[cle] = valeurs
