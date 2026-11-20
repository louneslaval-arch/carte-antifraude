"""Couche 2 : une fiche maître par personne et par société.

Trois sources de « mentions » : la liste noire et le registre du commerce, recopiés du socle que construit le kit
(`construire_base.py`, inchangé) par `charger_socle` ; les dossiers de la v2, relus dans la couche 1. Une fiche
réunit les mentions qui partagent une clé forte :

- personne : même CIN valide, aux noms compatibles (un CIN porté par deux noms incompatibles de la même écriture
  donne deux fiches et un signalement `CIN_PARTAGE`) ; une mention sans CIN prend le CIN de la seule mention au nom compatible du même
  dossier (`nom_dans_dossier`) ; une personne du registre sans CIN prend celui du seul gérant ou associé au nom
  compatible lu dans un dossier pour la même société (`AF05` : le dossier apporte le CIN) ;
- société : même RC et même tribunal (un RC porté par deux dénominations sans rapport de la même écriture donne
  deux fiches et un signalement `RC_PARTAGE`), même ICE, même identifiant fiscal, même n° d'affiliation CNSS d'un
  employeur ; deux RC différents ne sont jamais réunis par un autre identifiant ;
- une société d'un dossier lue sans aucun identifiant rejoint la seule société du même dossier qui en porte un, à
  dénomination compatible (`societe_dans_dossier`) ;
- sinon, une fiche propre à la source (au dossier pour la v2).

Tout le reste est un rapprochement, jamais une fusion : règles R01 à R11 du kit, recopiées telles quelles ; règles
écrites en SQL sur la vue `perimetre` (toutes les mentions v2 en lot, celles du dossier au fil de l'eau).

L'identifiant d'une fiche est dérivé de sa clé naturelle (empreinte) : il ne dépend ni de l'ordre d'arrivée ni de la
base. Il ne montre aucune valeur, mais se retrouve par énumération des CIN : il se traite comme le CIN lui-même et
ne sort jamais vers une URL, un journal, un événement ou Tandem (questions ouvertes). `traiter(cx, ref)` et `construire_tout(cx)` passent par les mêmes fonctions : les
fiches sont une fonction des mentions. Aucune sortie, aucun message ne porte de valeur.

Hors de ce lot (questions ouvertes) : les dossiers `af_*` de l'ancien export ; les règles AF qui croisent les
dossiers ou les chemins (AF09, AF11, AF20 : couches 3 et 5) ; le signalement d'un RC porté par des noms
incompatibles (AF02n, AF03n).
"""
import functools
import hashlib
import re
import sqlite3

from pipeline import construire_base as cb
from pipeline.normalisation.cles import GABARITS
from pipeline.normalisation.valeurs import texte_norm

nom = 'c2'
DIRIGEANTS = ('gerant', 'dirigeant', 'associe', 'associe_present', 'nouveau_gerant')
SOCIETE_DU_ROLE = dict({r: 'societe' for r in DIRIGEANTS}, employe='employeur')
COLONNES = ('id', 'cle_origine', 'source', 'type_fiche', 'ref', 'upstream_piece_id', 'type_piece', 'role', 'rang',
            'nom', 'nom_norm', 'cle_nom', 'ecriture', 'cin', 'cin_effectif', 'date_naissance', 'adresse', 'rc',
            'tribunal', 'rc_cle', 'ice', 'identifiant_fiscal', 'affiliation_cnss', 'societe_mention', 'societe_cle',
            'parts', 'statut', 'inscrit', 'fiche', 'regle')
CLES_SOCIETE = (('RC', 'rc_cle', 'RC_TRIB'), ('ICE', 'ice', 'ICE'), ('IF', 'identifiant_fiscal', 'IF'),
                ('AFF', 'affiliation_cnss', 'AFFILIATION'))
DECISIONS = ('meme_personne', 'homonyme_ecarte')
TITULAIRE_SOCIETE = ('PM', 'MORALE', 'PERSONNE MORALE')   # `type_titulaire` d'un relevé ou d'une attestation de RIB
LOT = 400                                                 # taille des listes passées à une requête

# Règles sur le périmètre : (nature, règle, niveau, statut, type de clé, jointure sur l'inscrit `s`, filtre sur `p`)
REGLES = (
    ('identite', 'AF01n', 'a_verifier', 'homonymie', 'NOM',
     "s.type_fiche = 'PP' AND s.cin IS NULL", "p.type_fiche = 'PP' AND p.cin_effectif IS NULL"),
    ('identite', 'AF02b', 'probable', 'homonymie', 'RC',
     "s.type_fiche = 'PM' AND s.rc = p.rc AND s.tribunal IS NULL", "p.type_fiche = 'PM' AND p.rc_cle IS NOT NULL"),
    ('identite', 'AF02d', 'a_verifier', 'homonymie', 'RS',
     "s.type_fiche = 'PM' AND s.rc IS NULL AND s.ice IS NULL", "p.type_fiche = 'PM' AND p.role <> 'employeur'"),
    ('emploi', 'AF07', 'a_verifier', 'homonymie', 'RS',
     "s.type_fiche = 'PM'", "p.type_fiche = 'PM' AND p.role = 'employeur'"),
)


# ---- identifiants et normalisation ---------------------------------------------------------------------------------

def _empreinte(texte, taille):
    return hashlib.sha256(texte.encode('utf-8')).hexdigest()[:taille]


def identifiant(type_fiche, cle_naturelle):
    """Identifiant stable d'une fiche : empreinte de sa clé naturelle (interne : réversible par énumération)."""
    return ('pp_' if type_fiche == 'PP' else 'pm_') + _empreinte(f'{type_fiche}|{cle_naturelle}', 16)


def _id_mention(cle_origine):
    return 'm_' + _empreinte(cle_origine, 20)


def _texte(x):
    return x.strip() if isinstance(x, str) and x.strip() else None


def _ecriture(texte):
    return None if not texte else ('arabe' if cb.est_arabe(texte) else 'latin')


def _chiffres(x, minimum):
    s = re.sub(r'[^0-9]', '', str(x)) if x not in (None, '') else ''
    return s if len(s) >= minimum and s.strip('0') else None


def _rc(x):
    if x in (None, ''):
        return None
    if isinstance(x, float):
        x = int(x) if x == int(x) else None
    s = re.sub(r'\.0+$', '', str(x).strip()) if x is not None else ''
    if re.fullmatch(r'\d{1,3}(?:[ .]\d{3})+', s):          # « 70 001 », « 70.001 » : séparateurs de milliers seulement
        s = re.sub(r'[ .]', '', s)
    if not re.fullmatch(r'[A-Za-z]{0,3} ?\d+(?:/\d+)?', s):   # jamais un numéro fabriqué en recollant autre chose
        return None
    numero, _, statut = cb.normalise_rc(s)
    # un RC à 1 ou 2 chiffres n'identifie pas une société (règles de méthode, `docs/decisions.md`)
    return numero if statut == 'rc' and numero and len(numero.lstrip('0')) >= 3 else None


def _ice(x):
    s = _chiffres(x, 15)
    return s if s and len(s) == 15 else None


def _cin(x, lettre_finale=False):
    """CIN valide hors gabarit. Dans le socle, un CIN à lettre finale est aussi une clé : le kit en fait un
    rapprochement « certain » quand il est écrit à l'identique des deux côtés (R01)."""
    if not x:
        return None
    norme, statut = cb.normalise_cin(x)
    admis = ('valide', 'lettre_finale') if lettre_finale else ('valide',)
    return norme if statut in admis and norme not in GABARITS else None


def _une_valeur(x):
    """La valeur d'une colonne du kit, sauf s'il y en a plusieurs (« a | b ») : jamais de clé recollée."""
    return None if isinstance(x, str) and '|' in x else x


def memes_noms(a, b):
    """Deux noms complets désignent-ils la même personne, assez sûrement pour lui apporter un CIN ? Mêmes mots (deux
    au moins) : ni un nom d'un seul mot, ni un nom inclus dans un autre."""
    if not a or not b:
        return False
    arabe_a, arabe_b = cb.est_arabe(a), cb.est_arabe(b)
    if arabe_a and arabe_b:
        mots = sorted(cb.ar_simple(a).split())
        return len(mots) >= 2 and mots == sorted(cb.ar_simple(b).split())
    if arabe_a != arabe_b:
        return len(a.split()) >= 2 and len(b.split()) >= 2 and compatibles(a, b)
    cle = cb.cle_nom(a)
    return bool(cle) and cle == cb.cle_nom(b)


@functools.lru_cache(maxsize=200_000)
def _compatibles(a, b):
    if not a or not b or a == b:
        return True
    arabe_a, arabe_b = cb.est_arabe(a), cb.est_arabe(b)
    if arabe_a and arabe_b:
        return sorted(cb.ar_simple(a).split()) == sorted(cb.ar_simple(b).split())
    if arabe_a != arabe_b:
        latin, arabe = (b, a) if arabe_a else (a, b)
        return bool(cb.profils_compatibles(latin, arabe))
    cle_a, cle_b = cb.cle_nom(a), cb.cle_nom(b)
    return bool(cle_a and cle_a == cle_b) or bool(cb.mots_latins_proches(a, b))


def compatibles(a, b):
    """Deux noms peuvent-ils désigner la même personne ? (latin ou arabe ; un nom absent est compatible avec tout)"""
    return _compatibles(*sorted((a or '', b or '')))


def separes(a, b):
    """Deux noms portés par un même CIN désignent-ils sûrement deux personnes ? Seulement s'ils sont de la même
    écriture et incompatibles : entre le latin et l'arabe, rien ne prouve l'incompatibilité."""
    return bool(a and b) and cb.est_arabe(a) == cb.est_arabe(b) and not compatibles(a, b)


def societes_separees(a, b):
    """Deux dénominations portées par un même RC désignent-elles sûrement deux sociétés ? Seulement si elles sont de
    la même écriture et sans rapport (ni mêmes mots, ni mots de l'une dans l'autre, ni graphies proches)."""
    if not a or not b or cb.est_arabe(a) != cb.est_arabe(b):
        return False
    cle_a, cle_b = cb.cle_rs(a), cb.cle_rs(b)
    if not cle_a or not cle_b or cle_a == cle_b or cb._ratio(cle_a, cle_b) >= 0.8:
        return False
    mots_a, mots_b = set(cle_a.split()), set(cle_b.split())
    return not (mots_a <= mots_b or mots_b <= mots_a)


def societes_compatibles(a, b):
    """Deux dénominations désignent-elles sûrement la même société ? Même écriture, et mêmes mots, mots de l'une dans
    l'autre, ou graphies proches (le contraire de « sans rapport » ne suffit pas : il faut une preuve positive)."""
    if not a or not b or cb.est_arabe(a) != cb.est_arabe(b):
        return False
    cle_a, cle_b = cb.cle_rs(a), cb.cle_rs(b)
    if not cle_a or not cle_b:
        return False
    if cle_a == cle_b or cb._ratio(cle_a, cle_b) >= 0.8:
        return True
    mots_a, mots_b = set(cle_a.split()), set(cle_b.split())
    return mots_a <= mots_b or mots_b <= mots_a


def _mention(source, type_fiche, cle_origine, **valeurs):
    m = dict.fromkeys(COLONNES)
    m.update(source=source, type_fiche=type_fiche, cle_origine=cle_origine, id=_id_mention(cle_origine),
             statut='normal', inscrit=0)
    m.update(valeurs)
    nom_ = m['nom'] = _texte(m['nom'])
    m['nom_norm'], m['ecriture'] = texte_norm(nom_), _ecriture(nom_)
    m['cle_nom'] = (cb.cle_nom(nom_) if type_fiche == 'PP' else cb.cle_rs(nom_)) if nom_ else None
    m['adresse'], m['date_naissance'] = _texte(m['adresse']), _texte(m['date_naissance'])
    if m['rc'] and m['tribunal']:
        m['rc_cle'] = m['rc_cle'] or f"{m['rc']}|{m['tribunal']}"
    return m


def _ecrire_mentions(cx, mentions):
    cx.executemany(f'INSERT INTO c2_mention ({", ".join(COLONNES)}) VALUES ({", ".join("?" * len(COLONNES))})',
                   [tuple(m[c] for c in COLONNES) for m in mentions])


def _par_lots(valeurs):
    valeurs = sorted(v for v in set(valeurs) if v is not None)
    for i in range(0, len(valeurs), LOT):
        yield valeurs[i:i + LOT]


def _lire(cx, condition='', parametres=()):
    curseur = cx.execute(f'SELECT {", ".join(COLONNES)} FROM c2_mention {condition}', tuple(parametres))
    return [dict(zip(COLONNES, ligne)) for ligne in curseur.fetchall()]


def _lire_dans(cx, colonne, valeurs, filtre=''):
    sortie = []
    for lot in _par_lots(valeurs):
        sortie += _lire(cx, f'WHERE {colonne} IN ({", ".join("?" * len(lot))}) {filtre}', lot)
    return sortie


# ---- mentions de la v2 (depuis la couche 1) ------------------------------------------------------------------------

def _mentions_v2(cx, ref=None):
    ou, parametres = (' WHERE ref = ?', (ref,)) if ref is not None else ('', ())
    societes, mentions = {}, []
    for ref_, upi, type_piece, role, nom_, rc, tribunal, ice, affiliation, adresse in cx.execute(
            'SELECT ref, upstream_piece_id, type_piece, role, nom, rc, tribunal, ice, affiliation_cnss, adresse '
            'FROM c1_mention_societe' + ou, parametres).fetchall():
        if role == 'banque':                              # une banque n'est pas une identité du dossier
            continue
        m = _mention('v2', 'PM', f'v2:{ref_}:{upi}:PM:{role}', ref=ref_, upstream_piece_id=upi, type_piece=type_piece,
                     role=role, rang=0, nom=nom_, rc=_rc(rc), tribunal=cb.tribunal_code(tribunal)[0] if tribunal else None,
                     ice=_ice(ice), adresse=adresse,
                     affiliation_cnss=_chiffres(affiliation, 5) if role == 'employeur' else None)
        societes[(ref_, upi, role)] = m
        mentions.append(m)
    for ref_, upi, type_piece, role, rang, nom_, cin, naissance, parts, adresse, statut, qualite in cx.execute(
            'SELECT ref, upstream_piece_id, type_piece, role, rang, nom_complet, cin, date_naissance, parts_sociales, '
            'adresse, statut, qualite FROM c1_mention_personne' + ou, parametres).fetchall():
        if role == 'titulaire_compte' and (qualite or '').strip().upper() in TITULAIRE_SOCIETE:
            mentions.append(_mention('v2', 'PM', f'v2:{ref_}:{upi}:PM:{role}', ref=ref_, upstream_piece_id=upi,
                                     type_piece=type_piece, role=role, rang=rang, nom=nom_, adresse=adresse))
            continue
        societe = societes.get((ref_, upi, SOCIETE_DU_ROLE.get(role)))
        mentions.append(_mention(
            'v2', 'PP', f'v2:{ref_}:{upi}:PP:{role}:{rang}', ref=ref_, upstream_piece_id=upi, type_piece=type_piece,
            role=role, rang=rang, nom=nom_, cin=_cin(cin), date_naissance=naissance, adresse=adresse, statut=statut,
            parts=None if parts is None else f'{parts:g}', societe_mention=societe and societe['id'],
            societe_cle=societe and societe['rc_cle']))
    return mentions


# ---- socle : liste noire et registre du kit ------------------------------------------------------------------------

def _dicts(con, sql):
    curseur = con.execute(sql)
    colonnes = [d[0] for d in curseur.description]
    return [dict(zip(colonnes, ligne)) for ligne in curseur.fetchall()]


def _existe(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def charger_socle(cx, chemin_base_kit):
    """Recopie la liste noire et le registre de la base du kit : liste noire dans la structure de `BlacklistEntry`,
    mentions du socle, rapprochements et décisions du kit. Puis reconstruit les fiches. Tout ou rien."""
    _tout_ou_rien(cx, _charger_socle, chemin_base_kit)


def _charger_socle(cx, chemin_base_kit):
    kit = sqlite3.connect(f'file:{chemin_base_kit}?mode=ro', uri=True)
    try:
        entites = _dicts(kit, 'SELECT * FROM bl_entite ORDER BY entite_id')
        premiers = {e: (n, p) for e, n, p in kit.execute(
            'SELECT entite_id, nom, prenom FROM bl_inscription ORDER BY num_seq DESC')}
        societes = _dicts(kit, 'SELECT * FROM rc_societe ORDER BY societe_id')
        personnes = _dicts(kit, 'SELECT * FROM rc_personne ORDER BY personne_id')
        correspondances = _dicts(kit, 'SELECT * FROM correspondance_retenue')
        decisions = _dicts(kit, 'SELECT * FROM decision_analyste') if _existe(kit, 'decision_analyste') else []
    finally:
        kit.close()
    cx.execute("DELETE FROM c2_mention WHERE source <> 'v2'")
    cx.execute("DELETE FROM c2_correspondance_mention WHERE source = 'kit'")
    cx.execute('DELETE FROM ref_liste_noire')
    mentions, par_entite, par_societe, par_personne = [], {}, {}, {}
    for e in entites:
        morale = e['type_entite'] == 'PM'
        nom_, prenom = premiers.get(e['entite_id'], (None, None))
        libelle = e['nom_affiche'] or ''
        statut = e['statut'] or 'actif'                   # sans statut : actif, comme le défaut du kit
        actif = statut == 'actif'                         # une inscription retirée reste visible, sans compter (n°4)
        cx.execute(
            'INSERT INTO ref_liste_noire (id, kind, label, normalized, city, active, "createdAt", personne, nom, '
            'prenom, "raisonSociale", cin, rc, "typeListe", motif, source, cle_entite, tribunal, ice, '
            'identifiant_fiscal, date_naissance, adresse, employeur, statut, date_statut, type_fraude, '
            'nb_inscriptions, premiere_saisie, derniere_saisie) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '
            '?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            ('bl_' + _empreinte(e['cle_entite'], 16), 'EMPLOYEUR' if morale else 'CLIENT', libelle,
             texte_norm(libelle) or '', e['ville_code'], int(actif), e['premiere_saisie'],
             e['type_entite'], None if morale else nom_, None if morale else prenom, libelle if morale else None,
             e['cin'], e['rc_num'], e['types_liste'], e['motifs'], e['origines'], e['cle_entite'], e['tribunal_code'],
             e['ice'], e['if_num'], e['date_naissance'], e['adresse'], e['employeur'], statut,
             e['date_reference'], e['types_fraude'], e['nb_inscriptions'], e['premiere_saisie'], e['derniere_saisie']))
        m = _mention('liste_noire', e['type_entite'], 'bl:' + e['cle_entite'], nom=e['nom_affiche'],
                     cin=None if morale else _cin(e['cin'], True), date_naissance=e['date_naissance'], adresse=e['adresse'],
                     rc=_rc(e['rc_num']) if morale else None, tribunal=e['tribunal_code'] if morale else None,
                     ice=_ice(_une_valeur(e['ice'])) if morale else None,
                     identifiant_fiscal=_chiffres(_une_valeur(e['if_num']), 4) if morale else None,
                     inscrit=int(actif))
        par_entite[e['entite_id']] = m
        mentions.append(m)
    for s in societes:
        rc, tribunal = _rc(s['rc_num']), s['tribunal_code']
        conflit = re.search(r'#\d+$', s['cle_societe'] or '')        # même RC, noms incompatibles : séparés par le kit
        m = _mention('registre', 'PM', 'rcs:' + s['cle_societe'], nom=s['denomination'], rc=rc, tribunal=tribunal,
                     rc_cle=f'{rc}|{tribunal}{conflit.group(0)}' if rc and tribunal and conflit else None,
                     ice=_ice(_une_valeur(s['ice'])), identifiant_fiscal=_chiffres(_une_valeur(s['if_num']), 4),
                     adresse=s['siege'], role='societe')
        par_societe[s['societe_id']] = m
        mentions.append(m)
    for p in personnes:
        societe = par_societe.get(p['societe_id'])
        physique = p['type_personne'] != 'PM'
        m = _mention('registre', 'PP' if physique else 'PM', 'rcp:' + p['cle_stable'], nom=p['nom_complet'],
                     cin=_cin(p['cin_norm'], True) if physique else None,
                     date_naissance=p['date_naissance'], adresse=p['adresse'], role=p['role'],
                     parts=_texte(p['parts']) if isinstance(p['parts'], str) else p['parts'] and str(p['parts']),
                     societe_mention=societe and societe['id'], societe_cle=societe and societe['rc_cle'])
        par_personne[p['personne_id']] = m
        mentions.append(m)
    _ecrire_mentions(cx, mentions)
    objets = {'rc_societe': par_societe, 'rc_personne': par_personne}
    for c in correspondances:
        a, b = par_entite.get(c['bl_entite_id']), objets.get(c['rc_objet'], {}).get(c['rc_objet_id'])
        if a and b:
            cx.execute(
                'INSERT INTO c2_correspondance_mention (mention_a, mention_b, nature, regle, niveau, statut, cle_type, '
                "cle_valeur, confirmation, poids, source, ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'kit', NULL) "
                'ON CONFLICT (mention_a, mention_b, regle) DO NOTHING',
                (a['id'], b['id'], c['nature'] or 'identite', c['regle'], c['niveau'], c['statut'] or 'a_verifier',
                 c['cle_type'], c['cle_valeur'], c['confirmation'], c['poids']))
    _construire(cx)
    for d in decisions:                                   # décisions d'analyste du kit, attachées aux mentions
        if d['decision'] in DECISIONS:
            couple = ('bl:' + d['cle_bl'], ('rcs:' if d['rc_objet'] == 'rc_societe' else 'rcp:') + d['cle_rc'])
            _ecrire_decision(cx, _id_mention(couple[0]), _id_mention(couple[1]), d['decision'], d['analyste'],
                             d['date_decision'], d['justification'], remplacer=False)


def _ecrire_decision(cx, mention_a, mention_b, decision, analyste, date_decision, justification, remplacer=True):
    suite = ('DO UPDATE SET decision = excluded.decision, analyste = excluded.analyste, date_decision = '
             'excluded.date_decision, justification = excluded.justification') if remplacer else 'DO NOTHING'
    cx.execute('INSERT INTO c2_decision (mention_a, mention_b, decision, analyste, date_decision, justification) '
               f'VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (mention_a, mention_b) {suite}',
               (mention_a, mention_b, decision, analyste, date_decision, justification))


def decider(cx, fiche_a, fiche_b, decision, analyste=None, justification=None, date_decision=None):
    """Enregistre la décision d'un analyste sur le rapprochement de deux fiches. Elle s'attache aux couples de
    mentions qui fondent ce rapprochement : elle survit aux reconstructions et au changement de clé d'une fiche."""
    if decision not in DECISIONS or not fiche_a or not fiche_b or fiche_a == fiche_b:
        raise ValueError('décision ou couple de fiches invalide')
    couples = cx.execute(
        'SELECT c.mention_a, c.mention_b FROM c2_correspondance_mention c JOIN c2_mention a ON a.id = c.mention_a '
        'JOIN c2_mention b ON b.id = c.mention_b WHERE (a.fiche = ? AND b.fiche = ?) OR (a.fiche = ? AND b.fiche = ?)',
        (fiche_a, fiche_b, fiche_b, fiche_a)).fetchall()
    if not couples:
        raise ValueError('aucun rapprochement entre ces deux fiches')
    for mention_a, mention_b in couples:
        _ecrire_decision(cx, mention_a, mention_b, decision, analyste, date_decision, justification)
    cx.commit()


# ---- fiches des personnes ------------------------------------------------------------------------------------------

def _cin_effectif(cx, m, cache):
    """(CIN que porte la mention, ou qu'une règle lui apporte ; règle de rattachement)."""
    if m['statut'] == 'gabarit':
        return None, 'gabarit'
    if m['cin']:
        return m['cin'], 'CIN'
    if not m['nom']:
        return None, 'sans_nom'
    if m['source'] == 'v2':
        cle, regle = ('ref', m['ref']), 'nom_dans_dossier'
        sql = "SELECT DISTINCT cin, nom FROM c2_mention WHERE type_fiche = 'PP' AND ref = ? AND cin IS NOT NULL " \
              "AND statut = 'normal'"
    elif m['source'] == 'registre' and m['societe_cle']:
        cle, regle = ('societe', m['societe_cle']), 'AF05'
        sql = "SELECT DISTINCT cin, nom FROM c2_mention WHERE type_fiche = 'PP' AND source = 'v2' AND societe_cle = ? " \
              "AND cin IS NOT NULL AND statut = 'normal' AND role IN ('gerant', 'dirigeant', 'associe', " \
              "'associe_present', 'nouveau_gerant')"
    else:
        return None, 'propre'
    if cle not in cache:
        cache[cle] = cx.execute(sql, (cle[1],)).fetchall()
    cins = {cin for cin, autre in cache[cle] if memes_noms(m['nom'], autre)}
    return (cins.pop(), regle) if len(cins) == 1 else (None, 'propre')


def _cle_propre(m):
    if m['regle'] in ('gabarit', 'sans_nom') or not m['nom']:
        return None
    if m['source'] == 'v2':
        return f"V2:{m['ref']}|{m['type_fiche']}|{m['cle_nom'] or m['nom_norm']}"
    return 'S:' + m['cle_origine']


def _grappes(mentions, separes=separes, proches=None):
    """Mentions d'une même clé (CIN, RC), réparties par noms compatibles : la graphie la plus fréquente fonde la
    première grappe."""
    comptes = {}
    for m in mentions:
        if m['nom_norm']:
            comptes[m['nom']] = comptes.get(m['nom'], 0) + 1
    grappes = []                                          # [(nom fondateur, {noms})]
    for nom_ in sorted(comptes, key=lambda n: (-comptes[n], n)):
        admises = [g for g in grappes if not separes(nom_, g[0])]
        # d'abord la grappe d'un nom reconnu compatible (une graphie arabe suit son nom latin), sinon la première
        voulue = next((g for g in admises if proches and any(n != nom_ and proches(nom_, n) and
                                                             cb.est_arabe(n) != cb.est_arabe(nom_) for n in g[1])),
                      admises[0] if admises else None)
        if voulue:
            voulue[1].add(nom_)
        else:
            grappes.append((nom_, {nom_}))
    return grappes or [(None, set())]


def _recalculer_personnes(cx, a_evaluer, cins):
    """Réévalue le CIN effectif des mentions données, puis refait les fiches de tous les CIN touchés."""
    cache, anciennes, cles = {}, {m['fiche'] for m in a_evaluer}, {}
    cins = set(cins) | {m['cin_effectif'] for m in a_evaluer}
    for m in a_evaluer:
        m['cin_effectif'], m['regle'] = _cin_effectif(cx, m, cache)
        cins.add(m['cin_effectif'])
        cle = None if m['cin_effectif'] else _cle_propre(m)
        m['fiche'] = cle and identifiant('PP', cle)
        cles[m['fiche']] = cle
    cx.executemany('UPDATE c2_mention SET cin_effectif = ?, regle = ?, fiche = ? WHERE id = ?',
                   [(m['cin_effectif'], m['regle'], m['fiche'], m['id']) for m in a_evaluer])
    cins.discard(None)
    par_cin = {}
    for m in _lire_dans(cx, 'cin_effectif', cins, "AND type_fiche = 'PP'"):
        par_cin.setdefault(m['cin_effectif'], []).append(m)
        anciennes.add(m['fiche'])
    for lot in _par_lots(cins):
        cx.execute(f"DELETE FROM c2_correspondance_mention WHERE regle = 'CIN_PARTAGE' AND cle_valeur IN "
                   f"({', '.join('?' * len(lot))})", lot)
    for cin, mentions in sorted(par_cin.items()):
        grappes, representants = _grappes(mentions, proches=compatibles), []
        for rang, (fondateur, noms) in enumerate(grappes):
            cle = f'CIN:{cin}' if rang == 0 else f'CIN:{cin}#{texte_norm(fondateur)}'
            membres = [m for m in mentions if m['nom'] in noms or (rang == 0 and not m['nom_norm'])]
            cles[identifiant('PP', cle)] = cle
            cx.executemany('UPDATE c2_mention SET fiche = ? WHERE id = ?',
                           [(identifiant('PP', cle), m['id']) for m in membres])
            representants.append(min(m['id'] for m in membres))
        for autre in representants[1:]:
            cx.execute("INSERT INTO c2_correspondance_mention (mention_a, mention_b, nature, regle, niveau, statut, "
                       "cle_type, cle_valeur, source) VALUES (?, ?, 'identite', 'CIN_PARTAGE', 'a_verifier', 'alerte', "
                       "'CIN', ?, 'c2')", (representants[0], autre, cin))
    _ecrire_fiches(cx, 'PP', dict.fromkeys(anciennes) | cles)


# ---- fiches des sociétés -------------------------------------------------------------------------------------------

def _fermeture(cx, mentions, fiches):
    """Toutes les mentions de société reliées, par une clé forte ou par leur fiche actuelle, à celles données."""
    connues = {m['id']: m for m in mentions}
    vues = {colonne: set() for _, colonne, _ in CLES_SOCIETE}
    fiches, fiches_vues = set(fiches) | {m['fiche'] for m in mentions}, set()
    while True:
        nouvelles = []
        for _, colonne, _ in CLES_SOCIETE:
            a_voir = {m[colonne] for m in connues.values() if m[colonne]} - vues[colonne]
            vues[colonne] |= a_voir
            nouvelles += _lire_dans(cx, colonne, a_voir, "AND type_fiche = 'PM'")
        a_voir = {f for f in fiches if f} - fiches_vues
        fiches_vues |= a_voir
        nouvelles += _lire_dans(cx, 'fiche', a_voir, "AND type_fiche = 'PM'")
        ajoutees = [m for m in nouvelles if m['id'] not in connues]
        if not ajoutees:
            return list(connues.values()), fiches
        for m in ajoutees:
            connues[m['id']] = m
            fiches.add(m['fiche'])


def _recalculer_societes(cx, mentions, anciennes):
    """Refait les fiches des sociétés données (déjà fermées par leurs clés fortes)."""
    parent = {m['id']: m['id'] for m in mentions}
    par_rc = {}
    for m in mentions:
        m['rc_effectif'] = m['rc_cle']
        if m['rc_cle']:
            par_rc.setdefault(m['rc_cle'], []).append(m)
    for lot in _par_lots(par_rc):
        cx.execute(f"DELETE FROM c2_correspondance_mention WHERE regle = 'RC_PARTAGE' AND cle_valeur IN "
                   f"({', '.join('?' * len(lot))})", lot)
    for rc_cle, membres in sorted(par_rc.items()):        # même RC, noms sans rapport : deux fiches, signalées
        grappes, representants = _grappes(membres, societes_separees), []
        for rang, (fondateur, noms) in enumerate(grappes):
            groupe = [m for m in membres if m['nom'] in noms or (rang == 0 and not m['nom_norm'])]
            for m in groupe if rang else ():
                m['rc_effectif'] = f'{rc_cle}#{texte_norm(fondateur)}'
            representants.append(min(m['id'] for m in groupe))
        for autre in representants[1:]:
            cx.execute("INSERT INTO c2_correspondance_mention (mention_a, mention_b, nature, regle, niveau, statut, "
                       "cle_type, cle_valeur, source) VALUES (?, ?, 'identite', 'RC_PARTAGE', 'a_verifier', 'alerte', "
                       "'RC_TRIB', ?, 'c2')", (representants[0], autre, rc_cle))
    rc_de = {m['id']: m['rc_effectif'] for m in mentions}

    def racine(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def unir(a, b):
        a, b = racine(a), racine(b)
        if a == b or (rc_de[a] and rc_de[b] and rc_de[a] != rc_de[b]):     # deux RC différents ne se réunissent pas
            return
        a, b = min(a, b), max(a, b)
        parent[b] = a
        rc_de[a] = rc_de[a] or rc_de[b]

    effectif = lambda colonne: 'rc_effectif' if colonne == 'rc_cle' else colonne  # noqa: E731
    autres = [f'{prefixe}:{m[colonne]}' for prefixe, colonne, _ in CLES_SOCIETE[1:] for m in mentions if m[colonne]]
    for lot in _par_lots(autres):
        cx.execute(f"DELETE FROM c2_correspondance_mention WHERE regle = 'CLE_PARTAGEE' AND cle_valeur IN "
                   f"({', '.join('?' * len(lot))})", lot)
    for prefixe, colonne, _ in CLES_SOCIETE:
        groupes = {}
        for m in mentions:
            if m[effectif(colonne)]:
                groupes.setdefault(m[effectif(colonne)], []).append(m['id'])
        for valeur in sorted(groupes):
            membres = sorted(groupes[valeur])
            par_rc_ = {}
            for i in membres:
                if rc_de[racine(i)]:
                    par_rc_.setdefault(rc_de[racine(i)], i)
            if colonne != 'rc_cle' and len(par_rc_) > 1:    # un ICE porté par deux RC ne rattache rien : signalé
                premiers = [par_rc_[k] for k in sorted(par_rc_)]
                for autre in premiers[1:]:
                    cx.execute("INSERT INTO c2_correspondance_mention (mention_a, mention_b, nature, regle, niveau, "
                               "statut, cle_type, cle_valeur, source) VALUES (?, ?, 'identite', 'CLE_PARTAGEE', "
                               "'a_verifier', 'alerte', ?, ?, 'c2') ON CONFLICT (mention_a, mention_b, regle) "
                               "DO NOTHING", (premiers[0], autre, prefixe, f'{prefixe}:{valeur}'))
                continue
            for autre in membres[1:]:
                unir(membres[0], autre)
    # Société d'un dossier lue sans aucun identifiant (statuts, nom sur un relevé) : elle rejoint la seule société du
    # même dossier qui en porte un, à nom compatible (règle `societe_dans_dossier`, Lounès, 20/11/2026) ; jamais d'un
    # dossier à l'autre, jamais entre deux candidates.
    def sans_cle(m):
        return not any(m[effectif(colonne)] for _, colonne, _ in CLES_SOCIETE)
    par_ref, rattachees = {}, set()
    for m in mentions:
        if m['source'] == 'v2' and m['ref'] and m['statut'] == 'normal':
            par_ref.setdefault(m['ref'], []).append(m)
    for ref in sorted(par_ref):
        du_dossier = par_ref[ref]
        for m in du_dossier:
            if not sans_cle(m) or not m['nom']:
                continue
            candidates = {racine(x['id']) for x in du_dossier if not sans_cle(x) and societes_compatibles(m['nom'], x['nom'])}
            if len(candidates) == 1:
                unir(m['id'], candidates.pop())
                rattachees.add(m['id'])
    composantes = {}
    for m in mentions:
        composantes.setdefault(racine(m['id']), []).append(m)
    cles = {}
    for membres in composantes.values():
        cle = None
        for prefixe, colonne, _ in CLES_SOCIETE:
            valeurs = sorted({m[effectif(colonne)] for m in membres if m[effectif(colonne)]})
            if valeurs:
                cle = f'{prefixe}:{valeurs[0]}'
                break
        for m in membres:
            propre = cle or _cle_propre(m)
            m['regle'] = next((regle for _, colonne, regle in CLES_SOCIETE if m[colonne]),
                              'societe_dans_dossier' if m['id'] in rattachees else 'propre' if propre else 'sans_nom')
            m['fiche'] = propre and identifiant('PM', propre)
            cles[m['fiche']] = propre
    cx.executemany('UPDATE c2_mention SET fiche = ?, regle = ? WHERE id = ?',
                   [(m['fiche'], m['regle'], m['id']) for m in mentions])
    _ecrire_fiches(cx, 'PM', dict.fromkeys(anciennes) | cles)


# ---- écriture des fiches (attributs qui survivent) -----------------------------------------------------------------

def _survivant(regles, mentions, attribut):
    for source, role in regles.get(attribut, ()):
        comptes = {}
        for m in mentions:
            if m['source'] == source and role in ('*', m['role']) and m[attribut]:
                comptes[m[attribut]] = comptes.get(m[attribut], 0) + 1
        if comptes:                                       # écriture latine d'abord, puis la plus fréquente
            return min(comptes, key=lambda v: (cb.est_arabe(v), -comptes[v], v))
    return None


def _ecrire_fiches(cx, type_fiche, cles):
    """Réécrit les fiches données ({identifiant: clé naturelle, ou rien si inconnue}) depuis leurs mentions."""
    table = 'c2_personne' if type_fiche == 'PP' else 'c2_societe'
    regles = {}
    for attribut, source, role in cx.execute('SELECT attribut, source, role FROM ref_regle_survie WHERE type_fiche = ? '
                                             'ORDER BY attribut, rang', (type_fiche,)):
        regles.setdefault(attribut, []).append((source, role))
    identifiants = sorted(i for i in cles if i)
    par_fiche = {}
    for m in _lire_dans(cx, 'fiche', identifiants):
        par_fiche.setdefault(m['fiche'], []).append(m)
    for i in identifiants:
        mentions, cle = par_fiche.get(i), cles[i]
        if cle is None:
            connue = cx.execute(f'SELECT cle_naturelle FROM {table} WHERE identifiant = ?', (i,)).fetchone()
            cle = connue and connue[0]
        cx.execute(f'DELETE FROM {table} WHERE identifiant = ?', (i,))
        if not mentions or cle is None:
            continue
        inscrit, premier = max(m['inscrit'] for m in mentions), lambda c: min((m[c] for m in mentions if m[c]), default=None)
        if type_fiche == 'PP':
            cx.execute('INSERT INTO c2_personne (identifiant, cle_naturelle, nom, cin, date_naissance, adresse, '
                       'inscrit, nb_mentions) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (i, cle, _survivant(regles, mentions, 'nom'), premier('cin_effectif'),
                        _survivant(regles, mentions, 'date_naissance'), _survivant(regles, mentions, 'adresse'),
                        inscrit, len(mentions)))
        else:
            avec_rc = min((m for m in mentions if m['rc_cle']), key=lambda m: m['rc_cle'], default=None)
            cx.execute('INSERT INTO c2_societe (identifiant, cle_naturelle, denomination, rc, tribunal, ice, '
                       'affiliation_cnss, adresse, inscrit, nb_mentions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (i, cle, _survivant(regles, mentions, 'nom'), avec_rc and avec_rc['rc'],
                        avec_rc and avec_rc['tribunal'], premier('ice'), premier('affiliation_cnss'),
                        _survivant(regles, mentions, 'adresse'), inscrit, len(mentions)))
        cx.execute('INSERT INTO c2_identifiant_attribue (cle_naturelle, type_fiche, identifiant) VALUES (?, ?, ?) '
                   'ON CONFLICT (cle_naturelle) DO NOTHING', (cle, type_fiche, i))


# ---- règles sur le périmètre ---------------------------------------------------------------------------------------

def _regles(cx, ref=None):
    """Rapprochements entre les mentions du périmètre et les inscrits : le même SQL en lot et au fil de l'eau."""
    ou, parametres = (' AND ref = ?', (ref,)) if ref is not None else ('', ())
    cx.execute("DELETE FROM c2_correspondance_mention WHERE source = 'v2'" + ou, parametres)
    cx.execute('DELETE FROM c2_perimetre')
    cx.execute("INSERT INTO c2_perimetre (mention) SELECT id FROM c2_mention WHERE source = 'v2'" + ou, parametres)
    for nature, regle, niveau, statut, cle_type, jointure, filtre in REGLES:
        cx.execute(
            'INSERT INTO c2_correspondance_mention (mention_a, mention_b, nature, regle, niveau, statut, cle_type, '
            'cle_valeur, source, ref) '
            f"SELECT s.id, p.id, '{nature}', '{regle}', '{niveau}', '{statut}', '{cle_type}', p.cle_nom, 'v2', p.ref "
            "FROM perimetre p JOIN c2_mention s ON s.source = 'liste_noire' AND s.inscrit = 1 AND s.cle_nom = p.cle_nom "
            f"AND {jointure} WHERE p.statut = 'normal' AND p.cle_nom IS NOT NULL AND {filtre} "
            'ON CONFLICT (mention_a, mention_b, regle) DO NOTHING')
    cx.execute('DELETE FROM c2_perimetre')


# ---- lot et fil de l'eau -------------------------------------------------------------------------------------------

def _construire(cx):
    cx.execute("DELETE FROM c2_mention WHERE source = 'v2'")
    cx.execute('DELETE FROM c2_personne')
    cx.execute('DELETE FROM c2_societe')
    cx.execute("DELETE FROM c2_correspondance_mention WHERE source = 'c2'")
    cx.execute('UPDATE c2_mention SET fiche = NULL, regle = NULL, cin_effectif = NULL')
    _ecrire_mentions(cx, _mentions_v2(cx))
    _recalculer_personnes(cx, _lire(cx, "WHERE type_fiche = 'PP'"), ())
    _recalculer_societes(cx, _lire(cx, "WHERE type_fiche = 'PM'"), ())
    _regles(cx)


def _traiter(cx, ref):
    anciennes = _lire(cx, "WHERE source = 'v2' AND ref = ?", (ref,))
    cx.execute("DELETE FROM c2_mention WHERE source = 'v2' AND ref = ?", (ref,))
    nouvelles = _mentions_v2(cx, ref)
    _ecrire_mentions(cx, nouvelles)
    personnes = lambda mentions: [m for m in mentions if m['type_fiche'] == 'PP']  # noqa: E731
    societes = {m['societe_cle'] for m in personnes(anciennes + nouvelles) if m['societe_cle']}
    du_registre = _lire_dans(cx, 'societe_cle', societes, "AND source = 'registre' AND type_fiche = 'PP' AND cin IS NULL")
    a_evaluer = _lire(cx, "WHERE source = 'v2' AND type_fiche = 'PP' AND ref = ?", (ref,)) + du_registre
    cins = {m['cin_effectif'] for m in personnes(anciennes)}
    _recalculer_personnes(cx, a_evaluer, cins)
    _ecrire_fiches(cx, 'PP', dict.fromkeys(m['fiche'] for m in personnes(anciennes)))
    morales = [m for m in anciennes if m['type_fiche'] == 'PM']
    graines = _lire(cx, "WHERE source = 'v2' AND type_fiche = 'PM' AND ref = ?", (ref,))
    cles = {colonne: {m[colonne] for m in morales if m[colonne]} for _, colonne, _ in CLES_SOCIETE}
    for colonne, valeurs in cles.items():
        graines += _lire_dans(cx, colonne, valeurs, "AND type_fiche = 'PM'")
    mentions, fiches = _fermeture(cx, list({m['id']: m for m in graines}.values()), {m['fiche'] for m in morales})
    _recalculer_societes(cx, mentions, fiches)
    _regles(cx, ref)


def _tout_ou_rien(cx, action, *arguments):
    try:
        action(cx, *arguments)
    except BaseException:
        cx.rollback()                                     # rien d'à moitié écrit, périmètre compris
        raise
    cx.commit()


def traiter(cx, ref):
    _tout_ou_rien(cx, _traiter, ref)


def construire_tout(cx):
    _tout_ou_rien(cx, _construire)
