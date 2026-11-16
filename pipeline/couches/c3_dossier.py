"""Couche 3 : la fiche du dossier (en-tête, revenus, charges, comptes, opérations, véhicules) et ses incohérences.

Sources : le miroir de la v2 (en-tête au format du modèle `Dossier` de Kamal, contexte `businessData`), la couche 1
(faits retenus, relevés, identifiants) et la couche 2 (fiches). `traiter(cx, ref)` réécrit les seules lignes du
dossier ; ce qui croise les dossiers ou le registre est calculé par des vues (`schema/040_c3.sql`) : le fil de l'eau
et le lot donnent donc le même état, sans propagation.

Règles tenues ici :
- les contrôles de la v2 ne sont pas recalculés ; les incohérences ajoutées croisent les pièces, les dossiers ou le
  registre ;
- une valeur déclarée par défaut (employeur « VAB ») est marquée et n'est jamais comparée ;
- un relevé non relu ne donne ni opération ni incohérence de flux ; une ligne reconstituée par l'amont n'est jamais
  une opération ;
- la contrepartie tirée d'un libellé est un indice, jamais une identité ;
- tolérances et seuils se lisent dans `c6_version_parametres` (vue `parametre`), jamais en dur.
Aucune sortie, aucun message ne porte de valeur.
"""
import datetime
import json
import re

from pipeline import construire_base as cb
from pipeline.couches import c2_identites as c2
from pipeline.normalisation.valeurs import montant, texte_norm

nom = 'c3'
TABLES = ('c3_dossier', 'c3_revenu', 'c3_charge', 'c3_compte', 'c3_operation', 'c3_vehicule', 'c3_cle_dossier',
          'c3_incoherence_locale')
EN_TETE = ('id', 'personType', 'csp', 'productType', 'paymentMode', 'clientName', 'agence', 'canal', 'category',
           'categoryRule', 'categoryReason', 'verdict', 'verdictProvisional', 'analysisStatus', 'alertsMinor',
           'alertsMajor', 'alertsCritical', 'commentaireScore', 'commentaireAlerte', 'matrixVersion', 'actif',
           'businessReceivedAt', 'resultsReceivedAt', 'createdAt', 'updatedAt')
# clés canoniques (moteur) du revenu d'une pièce, par ordre de préférence
REVENUS = {
    'BULLETIN_DE_PAIE': ('remuneration.salaire_net', 'salaire_net', 'salaire_net_mensuel'),
    'ATTESTATION_TRAVAIL_SALAIRE': ('salaire_net', 'salaire_net_mensuel', 'remuneration.salaire_net', 'salaire'),
    'ATTESTATION_PENSION': ('montant_pension_net', 'montant_pension_mensuel'),
}
VEHICULE = {'marque': ('marque', 'marque_vehicule'), 'modele': ('modele', 'modele_vehicule'), 'etat': ('etat_vehicule',)}
PIECES_VEHICULE = ('CARTE_GRISE', 'FACTURE_PROFORMA_VEHICULE')
ADRESSES_COMPAREES = (('titulaire_quittance', None), ('titulaire_compte', 'RELEVE_BANCAIRE'))
EPSILON = 0.005                                           # un demi-centime : jamais d'égalité stricte sur un montant

_TYPES = (('frais', {'FRAIS', 'COMMISSION', 'COMMISSIONS', 'AGIOS', 'TAXE', 'TVA'}),
          ('especes', {'RETRAIT', 'GAB', 'ESPECES', 'VERSEMENT'}),
          ('carte', {'CARTE', 'CB', 'TPE'}),
          ('cheque', {'CHEQUE', 'CHQ'}),
          ('prelevement', {'PRELEVEMENT', 'PRLV'}),
          ('virement', {'VIREMENT', 'VIR'}))
_DEBUT = re.compile(r'^(?:VIREMENT|VIR|PRELEVEMENT|PRLV|PAIEMENT|CHEQUE|CHQ|RETRAIT|VERSEMENT)'
                    r'(?: (?:RECU|RECUE|EMIS|PERMANENT|SEPA|PAR CARTE|CARTE))?'
                    r'(?: (?:DE|DU|VERS|EN FAVEUR DE|A|POUR))?(?: |$)')


def type_operation(libelle):
    """Type d'une opération d'après son libellé : virement, prelevement, carte, cheque, especes, frais ou autre. Le
    premier mot l'emporte (« VIREMENT … TVA » est un virement), sinon le premier mot reconnu."""
    mots = (texte_norm(libelle) or '').split()
    for mot in mots:
        type_ = next((type_ for type_, signes in _TYPES if mot in signes), None)
        if type_:
            return type_
    return 'autre'


def contrepartie(libelle):
    """Ce qui suit le mot d'opération dans le libellé (« VIREMENT RECU DE … ») : un indice, jamais une identité."""
    texte = texte_norm(libelle) or ''
    if not _DEBUT.match(texte):                           # sans mot d'opération, rien ne dit qui est en face
        return None
    reste = re.sub(r'^(?:\d[\d*X]*\s+)+', '', _DEBUT.sub('', texte).strip())   # numéro de carte ou de chèque retiré
    return reste or None


def _texte(x):
    return x.strip() if isinstance(x, str) and x.strip() else None


def _objet(x):
    return x if isinstance(x, dict) else {}


def _json(valeur):
    if isinstance(valeur, (dict, list)):
        return valeur
    try:
        return json.loads(valeur) if isinstance(valeur, str) else None
    except ValueError:
        return None


def _jour(*instants):
    """Jours depuis le 01/01/1970 du premier instant lisible (ISO 8601)."""
    for instant in instants:
        try:
            return datetime.date.fromisoformat(str(instant)[:10]).toordinal() - datetime.date(1970, 1, 1).toordinal()
        except ValueError:
            continue
    return None


def _parametre(cx, nom_):
    return cx.execute('SELECT valeur FROM parametre WHERE nom = ?', (nom_,)).fetchone()[0]


def _inserer(cx, table, lignes):
    if lignes:
        cx.executemany(f'INSERT INTO {table} VALUES ({", ".join("?" * len(lignes[0]))})', lignes)


# ---- un dossier ----------------------------------------------------------------------------------------------------

def _en_tete(cx, ref, d):
    contexte = _objet(_json(d['businessData']))
    civil, declare, agence = (_objet(contexte.get(c)) for c in ('civil', 'declared', 'agency'))
    employeur = _texte(declare.get('employer'))
    defaut = employeur is not None and cx.execute(
        "SELECT 1 FROM ref_valeur_defaut WHERE champ = 'employeur_declare' AND valeur = ?",
        (employeur.upper(),)).fetchone() is not None
    connu, production = contexte.get('known_client'), contexte.get('in_production')
    jour = _jour(d['businessReceivedAt'], d['createdAt'])
    cx.execute(
        f'INSERT INTO c3_dossier (ref, {", ".join(chr(34) + c + chr(34) for c in EN_TETE)}, en_cours, jour, '
        'civil_cin, civil_full_name, civil_address, declared_employer, employeur_par_defaut, declared_monthly_income, '
        'declared_pension_organism, known_client, in_production, agency_code, agency_city) '
        f'VALUES ({", ".join("?" * (len(EN_TETE) + 14))})',
        (ref, *(d[c] for c in EN_TETE), int(d['analysisStatus'] != 'COMPLETE'), jour,
         cb.normalise_cin(civil.get('cin'))[0] if _texte(civil.get('cin')) else None, _texte(civil.get('full_name')),
         _texte(civil.get('address')), employeur, int(defaut), montant(declare.get('monthly_income')),
         _texte(declare.get('pension_organism')), None if connu is None else int(bool(connu)),
         None if production is None else int(bool(production)),
         _texte(agence.get('code')), _texte(agence.get('city'))))
    return (jour, _texte(civil.get('address')), montant(declare.get('monthly_income')),
            cb.normalise_cin(civil.get('cin'))[0] if _texte(civil.get('cin')) else None)


def _revenus_et_charges(cx, ref, pieces, faits, mois, revenu_declare):
    revenus, charges = [], []
    if revenu_declare:                                    # un revenu déclaré nul ou absent n'est pas un revenu
        revenus.append((ref, 'declare', 'businessData', None, 'declared.monthly_income', None, None, revenu_declare, None,
                        'businessData'))
    for upi, type_piece in pieces:
        nombres = faits.get(upi, {})
        cle = next((c for c in REVENUS.get(type_piece, ()) if nombres.get(c, (None, None))[1] is not None), None)
        if cle:
            revenus.append((ref, 'verifie', type_piece, upi, cle, None, None, nombres[cle][1], None, upi))
        if type_piece == 'BULLETIN_DE_PAIE' and nombres.get('credits_source', (None, None))[1] is not None:
            charges.append((ref, 'credit_source', upi, 'credits_source', None, None, nombres['credits_source'][1]))
    for upi, rang, annee, mois_, salaire, echeances, lues in mois:
        if salaire is not None:
            revenus.append((ref, 'verifie', 'RELEVE_BANCAIRE', upi, f'mois:{rang}', annee, mois_, salaire, int(lues > 0),
                            upi))
        if echeances is not None:
            charges.append((ref, 'echeance_releve', upi, f'mois:{rang}', annee, mois_, echeances))
    return revenus, charges


def _incoherences(cx, ref, revenus, personnes, physique, cin_declare):
    trouvees = []
    tolerance = _parametre(cx, 'c3_tolerance_salaire')
    par_releve = {}
    for r in revenus:                                     # mois de relevé relu qui portent un salaire
        if r[2] == 'RELEVE_BANCAIRE' and r[8]:
            par_releve.setdefault(r[3], []).append(r)
    for bulletin in (r for r in revenus if r[2] == 'BULLETIN_DE_PAIE' and r[7] > 0):
        for upi, lignes in sorted(par_releve.items()):
            ecarts = sorted((abs(m[7] - bulletin[7]), m[4]) for m in lignes)
            if ecarts[0][0] > tolerance * bulletin[7] + EPSILON:      # aucun mois du relevé dans la tolérance
                trouvees.append((ref, 'salaire_bulletin_releve', bulletin[3], bulletin[4], upi, ecarts[0][1]))
    # adresse : seulement pour une personne physique, la carte du demandeur (CIN déclaré, sinon la première), et
    # les pièces à son nom (quittance, relevé d'un titulaire personne physique)
    cartes = [p for p in personnes if p[2] == 'titulaire_cin']
    carte = next((p for p in cartes if cin_declare and p[6] == cin_declare), None) or \
        (None if cin_declare and any(p[6] for p in cartes) else next((p for p in cartes if p[3] == 0), None))
    adresse_cin = cb.cle_adresse(carte[4]) if physique and carte and carte[4] else None
    if adresse_cin:
        for upi, type_piece, role, rang, adresse, nom_, cin, qualite in personnes:
            comparee = (role, None) in ADRESSES_COMPAREES or (role, type_piece) in ADRESSES_COMPAREES
            if not comparee or (qualite or '').strip().upper() in ('PM', 'MORALE', 'PERSONNE MORALE'):
                continue
            if not c2.memes_noms(nom_, carte[5]):         # la pièce est-elle bien au nom du demandeur ?
                continue
            cle = cb.cle_adresse(adresse) if adresse else None
            if cle and cle != adresse_cin:
                trouvees.append((ref, 'adresse_cin_differente', carte[0], 'adresse', upi, 'adresse'))
    return sorted(set(trouvees))


def _traiter(cx, ref):
    for table in TABLES:
        cx.execute(f'DELETE FROM {table} WHERE ref = ?', (ref,))
    curseur = cx.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in EN_TETE)}, "businessData" FROM "Dossier" '
                         'WHERE ref = ?', (ref,))
    ligne = curseur.fetchone()
    if ligne is None:
        return
    entete = dict(zip(EN_TETE + ('businessData',), ligne))
    jour, adresse_declaree, revenu_declare, cin_declare = _en_tete(cx, ref, entete)
    pieces = cx.execute('SELECT upstream_piece_id, type FROM c1_piece WHERE ref = ? ORDER BY 1', (ref,)).fetchall()
    faits = {}                                            # {pièce: {clé canonique: (valeur, nombre)}}
    for upi, cle, valeur, nombre in cx.execute(
            'SELECT upstream_piece_id, cle, valeur, nombre FROM c1_fait_retenu WHERE ref = ?', (ref,)).fetchall():
        faits.setdefault(upi, {})[cle] = (valeur, nombre)
    mois = cx.execute('SELECT upstream_piece_id, rang, annee, mois, salaire_detecte, echeances_credits, '
                      'nb_operations_lues FROM c1_releve_mois WHERE ref = ? ORDER BY 1, 2', (ref,)).fetchall()
    personnes = cx.execute('SELECT upstream_piece_id, type_piece, role, rang, adresse, nom_complet, cin, qualite '
                           'FROM c1_mention_personne WHERE ref = ? ORDER BY 1, 3, 4', (ref,)).fetchall()
    identifiants = cx.execute('SELECT upstream_piece_id, type, valeur, porteur FROM c1_identifiant_brut WHERE ref = ? '
                              'ORDER BY 1, 2, 3', (ref,)).fetchall()
    types = dict(pieces)

    revenus, charges = _revenus_et_charges(cx, ref, pieces, faits, mois, revenu_declare)
    _inserer(cx, 'c3_revenu', revenus)
    _inserer(cx, 'c3_charge', charges)

    banques = dict(cx.execute("SELECT upstream_piece_id, nom FROM c1_mention_societe WHERE ref = ? AND role = 'banque'",
                              (ref,)).fetchall())
    titulaires = dict(cx.execute("SELECT upstream_piece_id, nom_complet FROM c1_mention_personne WHERE ref = ? AND "
                                 "role = 'titulaire_compte'", (ref,)).fetchall())
    _inserer(cx, 'c3_compte', [(ref, upi, types.get(upi, ''), valeur, banques.get(upi), titulaires.get(upi) or porteur)
                               for upi, type_, valeur, porteur in identifiants if type_ == 'RIB'])
    _inserer(cx, 'c3_operation', [
        (ref, upi, rang_mois, rang, date, brute, libelle, debit, credit, type_operation(libelle), contrepartie(libelle))
        for upi, rang_mois, rang, date, brute, libelle, debit, credit in cx.execute(
            'SELECT upstream_piece_id, rang_mois, rang, date_operation, date_operation_brute, libelle, debit, credit '
            "FROM c1_releve_operation WHERE ref = ? AND nature = 'lue'", (ref,)).fetchall()])

    vehicules = []
    for upi, type_piece in pieces:
        if type_piece in PIECES_VEHICULE:
            lus = faits.get(upi, {})
            texte = {champ: next((lus[c][0] for c in cles if lus.get(c, (None,))[0]), None)
                     for champ, cles in VEHICULE.items()}
            propre = {type_: valeur for u, type_, valeur, _ in identifiants if u == upi}
            vehicules.append((ref, upi, type_piece, propre.get('CHASSIS'), propre.get('IMMATRICULATION'),
                              texte['marque'], texte['modele'], texte['etat'], lus.get('prix_ttc', (None, None))[1]))
    _inserer(cx, 'c3_vehicule', vehicules)

    cles = {}
    for upi, type_, valeur, _ in identifiants:
        if type_ in ('RIB', 'CHASSIS'):
            cles.setdefault((type_, valeur), upi)
    adresse = cb.cle_adresse(adresse_declaree) if adresse_declaree else None
    if adresse:
        cles[('ADRESSE', adresse)] = None
    _inserer(cx, 'c3_cle_dossier', [(ref, type_, valeur, upi, jour) for (type_, valeur), upi in sorted(cles.items())])
    _inserer(cx, 'c3_incoherence_locale', _incoherences(cx, ref, revenus, personnes,
                                                        entete['personType'] == 'PP', cin_declare))


# ---- lot et fil de l'eau -------------------------------------------------------------------------------------------

def _construire(cx):
    for table in TABLES:
        cx.execute(f'DELETE FROM {table}')
    for (ref,) in cx.execute('SELECT ref FROM "Dossier" ORDER BY ref').fetchall():
        _traiter(cx, ref)


def _tout_ou_rien(cx, action, *arguments):
    try:
        action(cx, *arguments)
    except BaseException:
        cx.rollback()
        raise
    cx.commit()


def traiter(cx, ref):
    _tout_ou_rien(cx, _traiter, ref)


def construire_tout(cx):
    _tout_ou_rien(cx, _construire)
