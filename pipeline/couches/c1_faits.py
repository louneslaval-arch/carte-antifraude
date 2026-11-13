"""Couche 1 : chaque valeur lue dans une pièce devient une ligne, normalisée, avec son origine.

Source : le miroir de la v2 (`"Piece".fields`, `"Reanalysis"`), jamais la réponse d'API : la couche ne dépend pas de
la façon dont les dossiers arrivent. Reprise d'`extraire_json_v2.py` (11/11) : ses tables `v2_*` deviennent
`c1_piece`, `c1_fait` (et la vue `c1_fait_retenu`), `c1_releve_mois`, `c1_releve_operation`, `c1_mention_personne`,
`c1_mention_societe`, `c1_identifiant_brut` ; la normalisation est dans `pipeline/normalisation/`.

`traiter(cx, ref)` (un dossier, comme le flux) et `construire_tout(cx)` (le lot) passent par la même fonction : un
dossier retraité donne les mêmes lignes, un dossier sorti du miroir n'en a plus. Rien n'est rapproché ici : les noms
sont gardés tels que lus ; les identités viennent à la couche 2. Une pièce au contenu inattendu ne fait jamais
échouer le traitement : ce qui est lisible est gardé. Aucune sortie ni journal ne porte de valeur.
"""
import json
import re

from pipeline.normalisation import cles
from pipeline.normalisation.valeurs import aplatir, cin_norm, date_iso, montant, rib_norm, texte_norm

nom = 'c1'
TABLES = ('c1_piece', 'c1_fait', 'c1_releve_mois', 'c1_releve_operation', 'c1_mention_personne',
          'c1_mention_societe', 'c1_identifiant_brut')
EMPLOI = ('ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE', 'ATTESTATION_CNSS')
LISTES_DE_PERSONNES = (('gerant', 'gerants'), ('dirigeant', 'dirigeants'), ('associe', 'associes'),
                       ('associe_present', 'associes_presents'), ('nouveau_gerant', 'nouveau_gerant'))

LISTES_RANGEES = {'mois', 'cartes'} | {cle for _, cle in LISTES_DE_PERSONNES}


def cle_connue(type_piece, cle_brute):
    """Vrai si la clé est dans `ref_cle_canonique` ; sinon elle sort au rapport des clés inconnues."""
    return cles.connue(type_piece, cle_brute)


# ---- lecture défensive ---------------------------------------------------------------------------------------------

def _objet(x):
    return x if isinstance(x, dict) else {}


def _objets(x):
    return [e for e in x if isinstance(e, dict)] if isinstance(x, list) else []


def _texte(x):
    return x if isinstance(x, str) and x.strip() else None


def _g(d, *chemins):
    """Première valeur non vide parmi des chemins pointés."""
    for chemin in chemins:
        x = d
        for partie in chemin.split('.'):
            x = x.get(partie) if isinstance(x, dict) else None
        if x not in (None, '', [], {}):
            return x
    return None


def _entier(x):
    try:
        n = int(x) if not isinstance(x, bool) else None
    except (TypeError, ValueError, OverflowError):
        return None
    return n if n is not None and abs(n) < 10 ** 9 else None      # au-delà : ni une année ni un mois, ni un entier SQL


def _json(valeur):
    """Contenu d'une colonne JSON : texte à décoder (SQLite) ou objet déjà décodé (jsonb de PostgreSQL)."""
    if isinstance(valeur, (dict, list)):
        return valeur
    try:
        return json.loads(valeur) if isinstance(valeur, str) else None
    except ValueError:
        return None


def _ident(x):
    """Identifiant en texte, sans espace autour ; un nombre JSON est gardé (comme le n° CNSS)."""
    if isinstance(x, bool) or not isinstance(x, (str, int)):
        return None
    return str(x).strip() or None


def _date_du_mois(v, annee, mois):
    """Date d'une ligne de relevé : l'année est celle du mois du relevé ; une date de janvier dans le bloc de
    décembre est de l'année suivante, une date de décembre dans le bloc de janvier de l'année précédente."""
    d = date_iso(v, annee)
    if d and annee is not None and mois in (1, 12):
        lu = int(d[5:7])
        if mois == 12 and lu == 1:
            return date_iso(v, annee + 1)
        if mois == 1 and lu == 12:
            return date_iso(v, annee - 1)
    return d


def _listes_ignorees(obj):
    """Nombre de listes d'objets que ni `aplatir` ni les mentions ne rangent : comptées, jamais perdues en silence."""
    if not isinstance(obj, dict):
        return 0
    n = 0
    for k, v in obj.items():
        if isinstance(v, dict):
            n += _listes_ignorees(v)
        elif isinstance(v, list) and v and k not in LISTES_RANGEES and (k in cles.LISTES or isinstance(v[0], dict)):
            n += 1
    return n


# ---- extraction d'une pièce ----------------------------------------------------------------------------------------

class _Lignes:
    def __init__(self, ref):
        self.ref = ref
        self.tables = {t: [] for t in TABLES}
        self._vues = set()

    def ajouter(self, table, upi, *valeurs, cle=None):
        if cle is not None:                               # clé primaire : la première ligne gagne
            if (table, upi, cle) in self._vues:
                return
            self._vues.add((table, upi, cle))
        self.tables[table].append((self.ref, upi) + valeurs)

    def identifiant(self, upi, type_, valeur, porteur):
        if valeur:
            self.ajouter('c1_identifiant_brut', upi, type_, str(valeur), _texte(porteur), cle=(type_, str(valeur)))

    def personne(self, upi, type_piece, role, x, rang=0):
        x = _objet(x)
        complet = _texte(_g(x, 'nom_complet')) or ' '.join(
            s for s in (_texte(_g(x, 'nom', 'nom_gerant')), _texte(_g(x, 'prenom', 'prenom_gerant'))) if s) or None
        cin = None if type_piece in cles.TYPES_SANS_CIN else cin_norm(_g(x, 'cin', 'numero_cin', 'numero_cin_gerant'))
        nom_norm = texte_norm(complet)
        self.ajouter('c1_mention_personne', upi, type_piece, role, rang, complet, nom_norm, cin,
                     date_iso(_g(x, 'date_naissance', 'date_naissance_gerant')), _texte(_g(x, 'qualite')),
                     montant(_g(x, 'parts_sociales', 'nombre_actions')),
                     _texte(_g(x, 'nationalite', 'nationalité_gerant')), _texte(_g(x, 'adresse', 'adresse_gerant')),
                     'gabarit' if cles.nom_gabarit(nom_norm) else 'normal', cle=(role, rang))
        self.identifiant(upi, 'CIN', cin, complet)

    def societe(self, upi, type_piece, role, nom_, rc=None, tribunal=None, ice=None, affiliation=None, adresse=None):
        nom_, rc, ice, affiliation = _texte(nom_), _ident(rc), _ident(ice), _ident(affiliation)
        if not nom_ and not rc and not ice:
            return
        tribunal = texte_norm(tribunal) if _texte(tribunal) else None
        ice = re.sub(r'[^0-9]', '', ice) or None if ice else None
        self.ajouter('c1_mention_societe', upi, type_piece, role, nom_, texte_norm(nom_), rc, tribunal, ice,
                     affiliation, _texte(adresse), cle=role)
        self.identifiant(upi, 'RC', f'{rc}|{tribunal}' if rc and tribunal else None, nom_)
        self.identifiant(upi, 'ICE', ice, nom_)
        self.identifiant(upi, 'AFFILIATION_CNSS', affiliation, nom_)


def _faits(lignes, upi, type_piece, source, champs, cles_relues):
    plat, vus = aplatir(champs), set()
    for cle_brute, v in plat:
        marque = (cle_brute, json.dumps(v, ensure_ascii=False, sort_keys=True, default=str))
        if marque in vus:                                 # clé plate et objet imbriqué : un seul fait
            continue
        vus.add(marque)
        racine = cle_brute.split('[')[0]
        if source == 'AMONT':
            origine = 'amont'
        elif racine in cles_relues or racine.split('.')[0] in cles_relues:
            origine = 'relue_ciblee'
        else:
            origine = 'fusion'                            # pièce relue : valeur relue ou clé amont gardée
        texte = v if isinstance(v, str) else None
        lignes.ajouter('c1_fait', upi, type_piece, cle_brute, cles.canon(type_piece, racine) + cle_brute[len(racine):],
                       None if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)),
                       texte_norm(texte) if texte else None, montant(v), date_iso(v), origine,
                       cles.statut_cle(type_piece, racine, v), int(cle_connue(type_piece, cle_brute)))
    return len(plat)


def _releve(lignes, upi, champs):
    agregats = {k: v for k, v in champs.items() if isinstance(v, dict)}

    def agregat(nom_, annee, mois):
        if annee is None or mois is None:
            return None
        return montant(_objet(agregats.get(nom_)).get(f'{mois:02d}/{annee}'))
    for rang_mois, m in enumerate(_objets(champs.get('mois'))):
        annee, mois = _entier(m.get('annee')), _entier(m.get('mois'))
        operations = _objets(m.get('operations'))
        lues = [o for o in operations if _texte(o.get('date_operation'))]
        lignes.ajouter('c1_releve_mois', upi, rang_mois, annee, mois, montant(m.get('solde_ouverture')),
                       montant(m.get('solde_cloture')), montant(m.get('total_credit')), montant(m.get('total_debit')),
                       agregat('montant_salaire', annee, mois), agregat('montant_echeances_credits', annee, mois),
                       len(lues))
        for rang, o in enumerate(operations):
            libelle = _texte(o.get('libelle'))
            lignes.ajouter('c1_releve_operation', upi, rang_mois, rang, annee, mois,
                           _date_du_mois(o.get('date_operation'), annee, mois),
                           _date_du_mois(o.get('date_valeur'), annee, mois), libelle,
                           texte_norm(libelle), montant(o.get('debit')), montant(o.get('credit')),
                           'lue' if _texte(o.get('date_operation')) else 'reconstituee_amont',
                           _texte(o.get('date_operation')))


def _piece(lignes, upi, type_piece, source, statut, version, champs, cles_relues):
    champs = _objet(champs)
    nb = _faits(lignes, upi, type_piece, source, champs, cles_relues)
    lignes.ajouter('c1_piece', upi, type_piece, source, statut, version, nb, len(cles_relues),
                   _listes_ignorees(champs))
    titulaire = _g(champs, 'titulaire_compte', 'nom_prenom')
    if type_piece in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB'):          # `raison_sociale` y est un titulaire (T09)
        titulaire = titulaire or _g(champs, 'raison_sociale')

    if type_piece == 'RELEVE_BANCAIRE':
        lignes.identifiant(upi, 'RIB', rib_norm(_g(champs, 'rib', 'numero_compte')), titulaire)
        _releve(lignes, upi, champs)
    if type_piece in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB'):
        lignes.societe(upi, type_piece, 'banque', _g(champs, 'banque'))
    if type_piece == 'CIN':
        for rang, carte in enumerate(_objets(champs.get('cartes')) or [champs]):
            lignes.personne(upi, type_piece, 'titulaire_cin', carte, rang)
    if type_piece in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB') and _texte(titulaire):
        # tel que lu : personne ou société, la couche 2 tranche (`type_titulaire` gardé en qualité)
        lignes.personne(upi, type_piece, 'titulaire_compte',
                        {'nom_complet': titulaire, 'qualite': _g(champs, 'type_titulaire'),
                         'adresse': _g(champs, 'adresse', 'adresse_complete')})
    for role, cle in LISTES_DE_PERSONNES:
        for rang, x in enumerate(_objets(champs.get(cle))):
            lignes.personne(upi, type_piece, role, x, rang)
    if type_piece in EMPLOI or type_piece == 'CARTE_PROFESSIONNELLE':
        lignes.personne(upi, type_piece, 'employe',
                        {**champs, **_objet(champs.get('employe')), **_objet(champs.get('assure'))})
        cnss = re.sub(r'[^0-9]', '', str(_g(champs, 'numero_cnss') or '')) or None
        lignes.identifiant(upi, 'CNSS', cnss, _g(champs, 'nom'))
    if type_piece == 'BULLETIN_DE_PAIE':
        lignes.identifiant(upi, 'RIB', rib_norm(_g(champs, 'rib')), _g(champs, 'nom'))
    if type_piece == 'ATTESTATION_PENSION':
        lignes.personne(upi, type_piece, 'pensionne', {**champs, **_objet(champs.get('pensionne'))})
        lignes.identifiant(upi, 'PENSION', _ident(_g(champs, 'numero_pension')), _g(champs, 'nom'))
    if type_piece == 'ATTESTATION_RIB':
        lignes.identifiant(upi, 'RIB', rib_norm(_g(champs, 'rib')), titulaire)
    if type_piece == 'CARTE_GRISE':
        chassis = (texte_norm(_g(champs, 'Numéro de chassis', 'numero_chassis')) or '').replace(' ', '') or None
        lignes.identifiant(upi, 'CHASSIS', chassis, None)
        lignes.identifiant(upi, 'IMMATRICULATION', texte_norm(_g(champs, 'Immatriculation', 'immatriculation')), None)
        if _g(champs, 'nom', 'cin'):
            lignes.personne(upi, type_piece, 'proprietaire', champs)
    if type_piece == 'FACTURE_PROFORMA_VEHICULE':
        acheteur = _texte(_g(champs, 'acheteur.nom', 'acheteur.nom_complet')) or ' '.join(
            s for s in (_texte(_g(champs, 'nom')), _texte(_g(champs, 'prenom'))) if s)
        if acheteur:
            lignes.personne(upi, type_piece, 'acheteur', {'nom_complet': acheteur})
        lignes.societe(upi, type_piece, 'concessionnaire',
                       _g(champs, 'nom_concessionnaire', 'vendeur.nom', 'vendeur.raison_sociale'))
    if type_piece == 'CARTE_PROFESSIONNELLE':
        lignes.identifiant(upi, 'INPE', _ident(_g(champs, 'numero_inpe')), _g(champs, 'nom'))
    if type_piece == 'DOMICILIATION' and _g(champs, 'titulaire', 'nom'):
        lignes.personne(upi, type_piece, 'titulaire_quittance',
                        {**champs, 'nom_complet': _texte(_g(champs, 'titulaire'))})
    if type_piece in ('REGISTRE_COMMERCE', 'STATUTS'):
        lignes.societe(upi, type_piece, 'societe', _g(champs, 'denomination_sociale', 'nom_societe'),
                       _g(champs, 'numero_analytique', 'numero_rc'), _g(champs, 'ville_tribunal', 'tribunal_commerce'),
                       _g(champs, 'ice', 'numero_ice'), None, _g(champs, 'adresse_siege', 'siege_social'))
    if type_piece in EMPLOI:
        employeur = _objet(champs.get('employeur'))
        lignes.societe(upi, type_piece, 'employeur',
                       _g(employeur, 'raison_sociale', 'nom') or _texte(champs.get('employeur'))
                       or _g(champs, 'employeur.raison_sociale', 'employeur_actuel'), None, None,
                       _g(employeur, 'ice'), _g(champs, 'numero_affiliation'),
                       _g(champs, 'adresse_employeur') or _g(employeur, 'adresse'))


# ---- écriture ------------------------------------------------------------------------------------------------------

def _traiter(cx, ref):
    semer_reference(cx)
    for table in TABLES:
        cx.execute(f'DELETE FROM {table} WHERE ref = ?', (ref,))
    dossier = cx.execute('SELECT id, "updatedAt" FROM "Dossier" WHERE ref = ?', (ref,)).fetchone()
    if dossier is None:
        return
    identifiant, version = dossier
    relus = {}                                            # champs relus de façon ciblée, par pièce
    for piece, statut, resultat in cx.execute('SELECT "pieceId", status, result FROM "Reanalysis" '
                                              'WHERE "dossierId" = ?', (identifiant,)).fetchall():
        if statut == 'DONE' and piece:
            relus.setdefault(piece, set()).update(_objet(_objet(_json(resultat)).get('apres')))
    lignes = _Lignes(ref)
    for upi, type_piece, source, statut, champs in cx.execute(
            'SELECT "upstreamPieceId", type, source, "extractionStatus", fields FROM "Piece" WHERE "dossierId" = ? '
            'ORDER BY "upstreamPieceId"', (identifiant,)).fetchall():
        _piece(lignes, upi, type_piece, source, statut, version, _json(champs), relus.get(upi, set()))
    for table, contenu in lignes.tables.items():
        if contenu:
            cx.executemany(f'INSERT INTO {table} VALUES ({", ".join("?" * len(contenu[0]))})', contenu)


def semer_reference(cx):
    """Remplit `ref_cle_canonique` depuis `pipeline/normalisation/cles.py` (table saisie, versionnée)."""
    attendu = len(cles.lignes_de_reference())
    if cx.execute('SELECT count(*), min(version), max(version) FROM ref_cle_canonique').fetchone() == \
            (attendu, cles.VERSION, cles.VERSION):
        return
    cx.execute('DELETE FROM ref_cle_canonique')
    cx.executemany('INSERT INTO ref_cle_canonique (type_piece, cle_brute, cle_moteur, version) VALUES (?, ?, ?, ?)',
                   [ligne + (cles.VERSION,) for ligne in cles.lignes_de_reference()])


def traiter(cx, ref):
    _traiter(cx, ref)
    cx.commit()


def construire_tout(cx):
    for table in TABLES:
        cx.execute(f'DELETE FROM {table}')
    for (ref,) in cx.execute('SELECT ref FROM "Dossier" ORDER BY ref').fetchall():
        _traiter(cx, ref)
    cx.commit()
