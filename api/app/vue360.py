"""Vue 360° d'une entité : profil (personne salariée, personne entrepreneur, personne morale), synthèse des revenus et
contrôles de la v2 rangés par famille, dans l'ordre utile au profil. Fonctions pures, appelées par la fiche.

Profil d'une personne : la CSP de son dernier dossier de demandeur (valeurs de `Csp` de la v2) ; sans CSP parlante
(aucun dossier propre, ou « AUTRE »), un rôle en cours de gérant, d'associé ou de dirigeant au registre ou dans un
dossier en fait un entrepreneur. Un salarié qui est aussi associé garde le profil salarié ; ses sociétés passent en
bandeau. Les retraités sont rangés avec les salariés (la pension tient lieu de salaire)."""
import datetime
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
from pipeline.analytique.controles import CATALOGUE, FAMILLES  # noqa: E402
from pipeline.normalisation.valeurs import date_iso, montant  # noqa: E402

CSP_SALARIE = frozenset({'SALARIE_PRIVE', 'FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE'})
CSP_RETRAITE = frozenset({'RETRAITE_PUBLIC', 'RETRAITE_CIMR', 'RETRAITE_INDETERMINE'})
CSP_INDEPENDANT = frozenset({'PROFESSION_LIBERALE', 'LOUEUR'})
ROLES_EN_COURS = frozenset({'gerant', 'associe', 'dirigeant', 'nouveau_gerant', 'associe_present', 'administrateur',
                            'representant'})
LIBELLES_EN_COURS = frozenset({'gérant', 'associé', 'dirigeant', 'nouveau gérant', 'associé présent', 'administrateur',
                               'représentant'})

# Familles de contrôles (préfixe du controlId), de la plus utile à la moins utile pour chaque profil.
ORDRE = {
    'salarie': ('EMP', 'IDT', 'BNQ', 'BLG', 'AUT', 'PRO'),
    'entrepreneur': ('PRO', 'IDT', 'BNQ', 'BLG', 'AUT', 'EMP'),
    'pm': ('IDT', 'BLG', 'BNQ', 'PRO', 'AUT', 'EMP'),
}
SOURCES_REVENU = ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION', 'RELEVE_BANCAIRE')


def profil(type_fiche, csp, roles):
    """(profil, retraité) : `type_fiche` « personne » ou « societe », `csp` du dernier dossier propre (ou None),
    `roles` bruts de la fiche dans les sociétés (registre et dossiers)."""
    if type_fiche == 'societe':
        return 'pm', False
    if csp in CSP_RETRAITE:
        return 'salarie', True
    if csp in CSP_SALARIE:
        return 'salarie', False
    if csp in CSP_INDEPENDANT:
        return 'entrepreneur', False
    return ('entrepreneur' if ROLES_EN_COURS & set(roles) else 'salarie'), False


def aussi(prof, societes):
    """Sociétés d'un salarié où il a un rôle en cours (gérant, associé…) : bandeau « aussi associé de… »."""
    if prof != 'salarie':
        return []
    return [s for s in societes if s.get('role') in LIBELLES_EN_COURS]


def synthese_revenus(revenus):
    """Dernier montant déclaré, dernier montant lu sur chaque pièce de revenu, écart relatif entre pièces
    ((plus haut − plus bas) / plus haut, None sous deux pièces)."""
    def cle(r):
        return (r.get('annee') or 0, r.get('mois') or 0)
    declare, pieces, rang = None, {}, {}
    for r in sorted(revenus, key=cle):
        if r['nature'] == 'declare':
            declare = r['montant']
        elif r['source'] in SOURCES_REVENU and cle(r) >= rang.get(r['source'], (-1, -1)):
            pieces[r['source']], rang[r['source']] = r['montant'], cle(r)
    montants = [m for m in pieces.values() if m]
    ecart = (max(montants) - min(montants)) / max(montants) if len(montants) >= 2 else None
    return dict(declare=declare, pieces=pieces, ecart=ecart)


def controles(donnees, prof):
    """Contrôles des dossiers propres, avec libellé, criticité et description du catalogue, par famille ; les
    anomalies d'abord dans chaque famille ; les familles dans l'ordre du profil, « Autres » à la fin."""
    par_famille = {}
    for x in donnees:
        for c in x.get('controles') or []:
            cid = c['controle']
            lib, crit, desc = CATALOGUE.get(cid, (cid, None, None))
            famille = FAMILLES.get(cid.split('-')[0], 'Autres')
            par_famille.setdefault(famille, []).append(dict(
                controle=cid, libelle=lib, criticite=c.get('criticite') or crit, description=desc,
                resultat=c['resultat'], dossier=x.get('dossier')))
    ordre = [FAMILLES[p] for p in ORDRE[prof]]
    sortie = []
    for famille in sorted(par_famille, key=lambda f: (ordre.index(f) if f in ordre else len(ordre), f)):
        lignes = sorted(par_famille[famille], key=lambda c: (c['resultat'] != 'ANOMALIE', c['controle']))
        sortie.append(dict(famille=famille, controles=lignes,
                           anomalies=sum(c['resultat'] == 'ANOMALIE' for c in lignes)))
    return sortie


# ---- mur de tuiles : les données lues dans les documents (pièces, registre, liste noire), chacune avec sa source ----
# Liste de Lounès (19/11/2026), dont, en rouge et à garder : historique des dossiers, historique EQDOM, recouvrement,
# taux d'endettement. Historique EQDOM et recouvrement : tuiles grisées tant que leurs sources ne sont pas branchées.
# Seuils de couleur provisoires (affichage seulement, jamais une décision) : à
# valider avec la cellule fraude, puis à passer dans `c6_version_parametres` s'ils sont retenus.
SEUILS_PROVISOIRES = dict(ecart_attention=0.15, ecart_critique=0.30, cin_bientot_jours=90,
                          endettement_attention=0.40, endettement_critique=0.60)
TON_NIVEAU = {'critique': 'critique', 'majeure': 'attention', 'mineure': 'neutre', 'affiche': 'neutre',
              'hors_alerte': 'neutre'}
ROLES_TERMINES = ('sortant', 'cédant', 'liquidateur')
ROLES_SALARIE = ('salarié', 'pensionné')
SOURCES = {'BULLETIN_DE_PAIE': 'bulletin de paie', 'ATTESTATION_TRAVAIL_SALAIRE': 'attestation de salaire',
           'ATTESTATION_PENSION': 'attestation de pension', 'RELEVE_BANCAIRE': 'relevés', 'CIN': 'CIN',
           'CARTE_PROFESSIONNELLE': 'carte professionnelle', 'REGISTRE_COMMERCE': 'registre du commerce',
           'STATUTS': 'statuts', 'ATTESTATION_CNSS': 'attestation CNSS'}
NON_EXTRAIT = 'non extrait par Tandem pour l’instant'
ATTEND_EQDOM = 'attend l’historique sur 36 mois (couche c4)'
ATTEND_RECO = 'attend le branchement de l’outil de recouvrement (Reco)'
MOIS = ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')


LIBELLES_SOURCE = {'v2': 'dossiers', 'registre': 'registre du commerce', 'liste_noire': 'liste noire EQDOM'}


def _t(libelle, valeur, format='texte', ton='neutre', source=None, detail=None):
    return dict(libelle=libelle, valeur=valeur, format=format, ton=ton, source=LIBELLES_SOURCE.get(source, source),
                detail=detail)


def _jour(v):
    """Date lue (« jj/mm/aaaa » des pièces ou ISO), par la normalisation du projet ; None si illisible."""
    iso = date_iso(str(v)) if v else None
    return datetime.date.fromisoformat(iso) if iso else None


def _iso(v):
    j = _jour(v)
    return j.isoformat() if j else None


def _fait(f, types, cles):
    """(valeur, source) du fait lu sur les pièces des dossiers propres, le plus récent dossier d'abord."""
    for x in reversed(f.get('donnees') or []):
        if not x.get('demandeur'):
            continue
        for type_piece in types:
            for p in x.get('pieces') or []:
                if p.get('type') != type_piece:
                    continue
                for cle in cles:
                    for fa in p.get('faits') or []:
                        if fa.get('cle') == cle and fa.get('valeur') not in (None, ''):
                            return fa['valeur'], SOURCES.get(type_piece, type_piece)
    return None, None


def _contexte(f, libelle):
    for x in reversed(f.get('donnees') or []):
        for c in x.get('contexte') or []:
            if c.get('libelle') == libelle and c.get('valeur') not in (None, ''):
                return c['valeur']
    return None


def _releves(f):
    mois = [m for x in f.get('donnees') or [] if x.get('demandeur') for p in x.get('pieces') or []
            for m in p.get('mois') or []]
    mois.sort(key=lambda m: (m.get('annee') or 0, m.get('mois') or 0))

    def somme(cle):
        vals = [m[cle] for m in mois if m.get(cle) is not None]
        return sum(vals) if vals else None

    def dernier(cle):
        return next((m[cle] for m in reversed(mois) if m.get(cle) is not None), None)
    n = len(mois)
    return dict(n=n, credit=somme('total_credit'), debit=somme('total_debit'), echeances=dernier('echeances_credits'),
                moyenne=lambda cle: (somme(cle) / n) if n and somme(cle) is not None else None)


def _seuil(v, attention, critique):
    if v is None:
        return 'neutre'
    return 'critique' if v >= critique else 'attention' if v >= attention else 'bon'


def _validite(fin, ref, jours):
    if not fin or not ref:
        return 'neutre'
    return 'critique' if fin < ref else 'attention' if fin < ref + datetime.timedelta(days=jours) else 'bon'


def _regrouper(personnes):
    par = {}
    for p in personnes:
        x = par.setdefault(p.get('indice') or p.get('nom'), dict(p, roles=[]))
        if p.get('role') and p['role'] not in x['roles']:
            x['roles'].append(p['role'])
        x['inscrit'] = x.get('inscrit') or p.get('inscrit')
    return list(par.values())


def _commun_identite(f, ref):
    ident, S = f['identite'], SEUILS_PROVISOIRES
    graphies = ', '.join(a['nom'] for a in f.get('alias') or [] if a.get('nom')) or None
    tuiles = [_t('Nom', ident.get('nom'), source='fiche'), _t('Graphies', graphies, source='pièces, registre, liste noire')]
    if ident.get('type') == 'societe':
        rc = ' · '.join(filter(None, (ident.get('rc'), ident.get('tribunal')))) or None
        tuiles += [_t('RC', rc, ton='neutre' if ident.get('tribunal') else 'attention', source='registre du commerce',
                      detail=None if ident.get('tribunal') else 'tribunal inconnu'),
                   _t('ICE', ident.get('ice'), source='registre du commerce')]
    else:
        naissance, src = _fait(f, ['CIN'], ['lieu_naissance'])
        expiration = _jour(_fait(f, ['CIN'], ['date_expiration'])[0])
        tuiles += [_t('CIN', ident.get('cin'), source='CIN'),
                   _t('Date de naissance', _iso(ident.get('date_naissance')), 'date', source='CIN'),
                   _t('Lieu de naissance', naissance, source=src),
                   _t('Expiration de la CIN', expiration.isoformat() if expiration else None, 'date',
                      _validite(expiration, ref, S['cin_bientot_jours']), 'CIN',
                      'à la date du dernier dossier')]
    adresses = f.get('adresses') or []
    tuiles.append(_t('Adresse retenue', ident.get('adresse'), source='règle de l’adresse la plus récente',
                     detail=f'{len(adresses)} adresse(s) connue(s)' if adresses else None))
    autres = [a for a in adresses if a.get('adresse') and a['adresse'] != ident.get('adresse')]
    if autres:
        tuiles.append(_t('Autre adresse', autres[0]['adresse'], source=autres[0].get('role') or autres[0].get('source')))
    return tuiles


def _commun_liste_noire(f):
    ident, ln, chemins = f['identite'], f.get('liste_noire') or [], f.get('chemins') or []
    tuiles = [_t('Liste noire', 'Inscrit' if ident.get('inscrit') else 'Non inscrit',
                 ton='critique' if ident.get('inscrit') else 'bon', source='liste noire EQDOM')]
    if ln:
        x = ln[0]
        tuiles += [_t('Type de liste', x.get('typeListe'), ton='critique', source='liste noire EQDOM'),
                   _t('Motif', x.get('motif') or x.get('type_fraude'), source='liste noire EQDOM'),
                   _t('Statut de l’inscription', x.get('statut'), source='liste noire EQDOM'),
                   _t('Inscrit depuis', _iso(x.get('premiere_saisie')), 'date', source='liste noire EQDOM')]
    if chemins:
        c = chemins[0]
        force = f"{c.get('force', 0):.2f}".replace('.', ',')
        tuiles += [_t('Meilleur chemin', f"{c.get('niveau')} · force {force}", ton=TON_NIVEAU.get(c.get('niveau'), 'neutre'),
                      source='carte des réseaux', detail=f"{c.get('longueur')} lien(s)"
                      + (' · homonymie à lever' if c.get('homonymie') else '') + (' · même foyer' if c.get('foyer') else '')),
                   _t('Inscrit atteint', (c.get('inscrit') or {}).get('nom'), ton='attention', source='liste noire EQDOM'),
                   _t('Chemins vers des inscrits', len(chemins), 'nombre', 'attention', 'carte des réseaux',
                      'à moins de 4 liens')]
    else:
        tuiles.append(_t('Meilleur chemin', 'aucun', ton='bon', source='carte des réseaux', detail='à moins de 4 liens'))
    return tuiles


def _commun_incoherences(f):
    incoh = {i.get('type') for i in f.get('incoherences') or []}
    def oui(cle, libelle, ton):
        return _t(libelle, 'Oui' if cle in incoh else 'Non', ton=ton if cle in incoh else 'bon', source='dossiers')
    return [oui('rib_autre_dossier', 'Même RIB dans le dossier d’un autre', 'critique'),
            oui('double_financement', 'Même châssis ailleurs', 'critique'),
            oui('dossiers_en_rafale', 'Dossiers en rafale', 'attention')]


def _commun_controles(f):
    tuiles = []
    for fam in f['vue360'].get('controles') or []:
        n = fam['anomalies']
        en_anomalie = [f"{c['controle']} {c.get('libelle') or ''}".strip() for c in fam['controles']
                       if c['resultat'] == 'ANOMALIE']
        critique = any(c.get('criticite') == 'CRITIQUE' for c in fam['controles'] if c['resultat'] == 'ANOMALIE')
        tuiles.append(_t(fam['famille'], f"{n} anomalie{'s' if n > 1 else ''}" if n else 'conforme',
                         ton='critique' if critique else 'attention' if n else 'bon', source='antifraude v2',
                         detail='; '.join(en_anomalie) or f"{len(fam['controles'])} contrôle(s)"))
    return tuiles


def _comptes(f, avec_type=False):
    rel = _releves(f)
    c = (f.get('comptes') or [None])[0] or {}
    tuiles = [_t('RIB', c.get('rib'), source='relevés'), _t('Banque', c.get('banque'), source='relevés'),
              _t('Titulaire', c.get('titulaire'), source='relevés'),
              _t('Crédits cumulés', rel['credit'], 'montant', source='relevés', detail=f"{rel['n']} mois lus"),
              _t('Débits cumulés', rel['debit'], 'montant', source='relevés', detail=f"{rel['n']} mois lus")]
    if avec_type:
        titulaire, src = _fait(f, ['RELEVE_BANCAIRE', 'ATTESTATION_RIB'], ['type_titulaire'])
        types = {'PP': 'personnel', 'PM': 'professionnel', 'MORALE': 'professionnel'}
        tuiles.append(_t('Type de compte', types.get(str(titulaire).upper(), titulaire) if titulaire else None,
                         source=src, detail=f"{len(f.get('comptes') or [])} compte(s) lu(s)"))
    return tuiles


def tuiles(f):
    """Groupes de tuiles de la vue 360° : [{groupe, tuiles: [{libelle, valeur, format, ton, source, detail}]}].
    Fonction pure sur la fiche servie ; date de référence = dernier dossier propre (jamais la date du jour)."""
    S = SEUILS_PROVISOIRES
    v = f['vue360']
    prof, entite = v['profil'], v.get('entite') or {}
    propres = [d for d in f.get('dossiers') or [] if d.get('demandeur')]
    ref = max((_jour(d.get('recu')) for d in (propres or f.get('dossiers') or []) if _jour(d.get('recu'))), default=None)
    rev, pieces = v.get('revenus') or {}, (v.get('revenus') or {}).get('pieces') or {}
    controles = {c['controle']: c for fam in v.get('controles') or [] for c in fam['controles']}

    def controle(cid, libelle):
        c = controles.get(cid)
        if not c:
            return _t(libelle, 'non exécuté', source='antifraude v2', detail=CATALOGUE.get(cid, (cid, None, None))[0])
        ano = c['resultat'] == 'ANOMALIE'
        return _t(libelle, 'anomalie' if ano else c['resultat'].lower().replace('_', ' '),
                  ton=('critique' if c.get('criticite') == 'CRITIQUE' else 'attention') if ano else 'bon',
                  source='antifraude v2', detail=c.get('libelle') or CATALOGUE.get(cid, (cid,))[0])

    groupes = [dict(groupe='Identité', tuiles=_commun_identite(f, ref)),
               dict(groupe='Liste noire', tuiles=_commun_liste_noire(f))]

    if prof == 'salarie':
        retraite = v.get('retraite')
        revenus = [_t('Revenu déclaré', rev.get('declare'), 'montant', source='déclaration')]
        for s, n in (('BULLETIN_DE_PAIE', 'Bulletin de paie'), ('ATTESTATION_TRAVAIL_SALAIRE', 'Attestation de salaire'),
                     ('ATTESTATION_PENSION', 'Pension')):
            if s in pieces or (s == 'ATTESTATION_PENSION' and retraite):
                revenus.append(_t(n, pieces.get(s), 'montant', source=SOURCES[s]))
        revenus += [_t('Salaire retrouvé sur les relevés', pieces.get('RELEVE_BANCAIRE'), 'montant', source='relevés'),
                    _t('Écart entre pièces', rev.get('ecart'), 'pourcent',
                       _seuil(rev.get('ecart'), S['ecart_attention'], S['ecart_critique']), 'pièces de revenu',
                       'signalé au-delà de 15 %')]
        groupes.append(dict(groupe='Revenus', tuiles=revenus))

        relie = next((s for s in f.get('societes') or [] if s.get('role') in ROLES_SALARIE), None)
        if retraite:
            organisme, src = _fait(f, ['ATTESTATION_PENSION'], ['nom_organisme_retraite', 'caisse'])
            emploi = [_t('Organisme de pension', organisme, source=src),
                      _t('Organisme déclaré', _contexte(f, 'Organisme de pension déclaré'), source='déclaration')]
        else:
            sur_bulletin, src = _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'],
                                      ['employeur.raison_sociale', 'employeur.nom', 'raison_sociale'])
            embauche, src_e = _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'], ['date_embauche', 'date_entree'])
            fonction, src_f = _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'], ['fonction', 'profession'])
            emploi = [_t('Employeur sur le bulletin', sur_bulletin, source=src),
                      _t('Employeur déclaré au dossier', _contexte(f, 'Employeur déclaré'), source='déclaration',
                         detail='« VAB » : valeur par défaut, jamais comparée'),
                      _t('Fonction', fonction, source=src_f),
                      _t('Date d’embauche', _iso(embauche), 'date', source=src_e),
                      controle('EMP-05', 'Contrôle EMP-05')]
        if not retraite:
            emploi += [_t('Employeur relié', relie['nom'] if relie else None,
                          ton='critique' if relie and relie.get('inscrit') else 'neutre', source='registre du commerce',
                          detail='inscrit sur la liste noire' if relie and relie.get('inscrit') else None),
                       _t('Clients EQDOM qui le déclarent', entite.get('employeur_clients'), 'nombre', source='base client'),
                       _t('Salaire versé par un autre', None, source='relevés', detail=NON_EXTRAIT)]
        groupes.append(dict(groupe='Pension' if retraite else 'Employeur', tuiles=emploi))

        charges = f.get('charges') or []
        source_ = next((c['montant'] for c in sorted(charges, key=lambda c: (c.get('annee') or 0, c.get('mois') or 0),
                                                       reverse=True) if c.get('nature') == 'credit_source'), None)
        echeances = _releves(f)['echeances']
        verifie = next((pieces[s] for s in ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION',
                                            'RELEVE_BANCAIRE') if pieces.get(s)), None)
        charges_mois = (echeances or 0) + (source_ or 0)
        endettement = charges_mois / verifie if verifie and (echeances is not None or source_ is not None) else None
        groupes.append(dict(groupe='Charges', tuiles=[
            _t('Échéances de crédit sur les relevés', echeances, 'montant', source='relevés', detail='dernier mois lu'),
            _t('Crédit prélevé à la source', source_, 'montant', source='bulletin de paie'),
            _t('Taux d’endettement', endettement, 'pourcent',
               _seuil(endettement, S['endettement_attention'], S['endettement_critique']), 'relevés et pièces de revenu',
               '(échéances du relevé + crédit prélevé à la source) / revenu vérifié')]))
        groupes.append(dict(groupe='Comptes', tuiles=_comptes(f)))
        ids = f.get('identifiants') or []
        idt = [_t('N° CNSS', next((i['valeur'] for i in ids if i.get('type') == 'CNSS'), None), source='bulletin de paie'),
               _t('N° de pension', next((i['valeur'] for i in ids if i.get('type') == 'PENSION'), None),
                  source='attestation de pension')]
        if v.get('aussi'):
            roles = sorted({s.get('role') for s in v['aussi'] if s.get('role')})
            idt.append(_t(f"Aussi {' et '.join(roles)} de", ', '.join(s['nom'] for s in v['aussi']), ton='attention',
                          source='registre du commerce'))
        groupes.append(dict(groupe='Identifiants', tuiles=idt))

    elif prof == 'entrepreneur':
        parts = {m.get('societe'): m.get('parts') for m in f.get('registre') or [] if m.get('parts') not in (None, '')}
        societes = []
        for s in _regrouper(f.get('societes') or []):
            if any(r in ROLES_SALARIE for r in s['roles']):
                continue
            termine = all(any(t in r for t in ROLES_TERMINES) for r in s['roles'])
            texte = ', '.join(s['roles']) + (f" · associé {parts[s['nom']]} %" if s['nom'] in parts else '')
            societes.append(_t(s['nom'], texte, ton='critique' if s.get('inscrit') else 'attention' if termine else 'neutre',
                               source=s.get('source'), detail='rôle terminé' if termine else
                               ('société inscrite' if s.get('inscrit') else None)))
        creation, src_c = _fait(f, ['REGISTRE_COMMERCE'], ['date_creation', 'date_immatriculation', 'date_debut'])
        groupes.append(dict(groupe='Sociétés et rôles', tuiles=societes[:8] + [
            _t('Mentions au registre', len(f.get('registre') or []), 'nombre', source='registre du commerce'),
            _t('Activité depuis', _iso(creation), 'date', source=src_c)]))
        rel = _releves(f)
        groupes.append(dict(groupe='Revenus d’activité', tuiles=[
            _t('Revenu déclaré', rev.get('declare'), 'montant', source='déclaration'),
            _t('Revenu retrouvé sur les relevés', pieces.get('RELEVE_BANCAIRE'), 'montant', source='relevés'),
            _t('Crédits par mois', rel['moyenne']('total_credit'), 'montant', source='relevés', detail='moyenne des mois lus')]))
        profession, src_p = _fait(f, ['CARTE_PROFESSIONNELLE'], ['profession', 'secteur'])
        numero, src_n = _fait(f, ['CARTE_PROFESSIONNELLE'], ['numero_inscription', 'numero_inpe'])
        fin = _jour(_fait(f, ['CARTE_PROFESSIONNELLE'], ['date_validite', 'date_expiration'])[0])
        groupes.append(dict(groupe='Pièces professionnelles', tuiles=[
            _t('Profession', profession, source=src_p), _t('N° d’inscription', numero, source=src_n),
            _t('Carte professionnelle valide jusqu’au', fin.isoformat() if fin else None, 'date',
               _validite(fin, ref, S['cin_bientot_jours']), 'carte professionnelle'),
            controle('PRO-01', 'Contrôle PRO-01'), controle('PRO-03', 'Contrôle PRO-03'),
            controle('IDT-10', 'Contrôle IDT-10'), controle('IDT-11', 'Contrôle IDT-11')]))
        groupes.append(dict(groupe='Comptes et flux', tuiles=_comptes(f, avec_type=True)))

    else:
        forme, src_f = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['forme_juridique'])
        capital, src_k = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['capital_social', 'capital'])
        immat, src_i = _fait(f, ['REGISTRE_COMMERCE'], ['date_immatriculation', 'date_creation'])
        objet, src_o = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['objet_social', 'objet_commerce', 'objet_du_commerce'])
        siege, src_s = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['adresse_siege', 'siege_social'])
        groupes.append(dict(groupe='Identité légale', tuiles=[
            _t('Forme juridique', forme, source=src_f),
            _t('Capital', montant(capital) if capital is not None else None, 'montant', source=src_k),
            _t('Immatriculée le', _iso(immat), 'date', source=src_i),
            _t('Objet social', objet, source=src_o),
            _t('Siège', siege or f['identite'].get('adresse'), source=src_s or 'registre du commerce'),
            _t('Sociétés au même siège', entite.get('siege_partage'), 'nombre',
               'attention' if (entite.get('siege_partage') or 0) >= 5 else 'neutre', 'registre du commerce',
               'au-delà de 5 : domiciliation probable')]))
        personnes = [_t(p['nom'], ', '.join(p['roles']), ton='critique' if p.get('inscrit') else 'neutre',
                        source=p.get('source'), detail='inscrit sur la liste noire' if p.get('inscrit') else None)
                     for p in _regrouper(f.get('personnes') or [])]
        changements = [p for p in _regrouper(f.get('personnes') or [])
                       if any(t in r for r in p['roles'] for t in ('nouveau', 'sortant', 'cédant', 'cessionnaire'))]
        groupes.append(dict(groupe='Gérants, associés et bénéficiaires', tuiles=personnes[:8] + [
            _t('Changements de dirigeants', len(changements), 'nombre', 'attention' if changements else 'neutre',
               'registre du commerce', 'nouveau gérant, sortant, cession')]))
        groupes.append(dict(groupe='Cohérence des dirigeants', tuiles=[
            controle('IDT-12', 'Contrôle IDT-12'), controle('IDT-17', 'Contrôle IDT-17'),
            controle('IDT-20', 'Contrôle IDT-20'), controle('IDT-21', 'Contrôle IDT-21')]))
        rel = _releves(f)
        groupes.append(dict(groupe='Comptes et flux', tuiles=[
            _t('RIB', ((f.get('comptes') or [{}])[0]).get('rib'), source='relevés'),
            _t('Banque', ((f.get('comptes') or [{}])[0]).get('banque'), source='relevés'),
            _t('Crédits par mois', rel['moyenne']('total_credit'), 'montant', source='relevés', detail='moyenne des mois lus'),
            _t('Débits par mois', rel['moyenne']('total_debit'), 'montant', source='relevés', detail='moyenne des mois lus'),
            _t('Échéances par mois', rel['moyenne']('echeances_credits'), 'montant', source='relevés'),
            _t('Chiffre d’affaires déclaré', None, source='liasse fiscale', detail='liasse fiscale non fournie'),
            controle('BNQ-10', 'BNQ-10 · Flux aller-retour'), controle('BNQ-11', 'BNQ-11 · Espèces puis virement'),
            controle('BNQ-12', 'BNQ-12 · Siège dans le Sud')]))
        soeurs = entite.get('soeurs') or []
        groupes.append(dict(groupe='Réseau de la société', tuiles=[
            _t('Sociétés sœurs', ', '.join(soeurs[:5]) or None, ton='attention' if soeurs else 'neutre',
               source='registre du commerce', detail=f'{len(soeurs)} société(s) au même gérant ou associé')]))

    groupes.append(dict(groupe='Incohérences', tuiles=_commun_incoherences(f)))
    ctl = _commun_controles(f)
    if ctl:
        groupes.append(dict(groupe='Contrôles de l’antifraude', tuiles=ctl))
    groupes.append(dict(groupe='Historique des dossiers', tuiles=_historique(f)))
    groupes.append(dict(groupe='Historique EQDOM', tuiles=[
        _t('Contrats EQDOM', None, source='historique EQDOM', detail=ATTEND_EQDOM),
        _t('Impayés', None, source='historique EQDOM', detail=ATTEND_EQDOM),
        _t('Classe BAM', None, source='historique EQDOM', detail=ATTEND_EQDOM)]))
    groupes.append(dict(groupe='Recouvrement', tuiles=[
        _t('Relances', None, source='Reco', detail=ATTEND_RECO),
        _t('Promesses de paiement', None, source='Reco', detail=ATTEND_RECO)]))
    return groupes


def _historique(f):
    """Une tuile par dossier (6 au plus, le plus récent d'abord) : produit, rôle, verdict ; puis les véhicules."""
    tuiles = []
    for d in sorted(f.get('dossiers') or [], key=lambda d: d.get('recu') or '', reverse=True)[:6]:
        jour = _jour(d.get('recu'))
        quand = f'{jour.day} {MOIS[jour.month - 1]} {jour.year}' if jour else 'date inconnue'
        libelle = f'Dossier du {quand}'
        while any(t['libelle'] == libelle for t in tuiles):
            libelle += ' (bis)'
        verdict = d.get('verdict') if d.get('demandeur') else None
        tuiles.append(_t(libelle, ' · '.join(filter(None, (d.get('produit'), 'demandeur' if d.get('demandeur')
                                                              else d.get('role') or 'cité'))),
                         ton='neutre' if not verdict else 'bon' if verdict == 'CONFORME' else 'attention',
                         source='dossiers', detail=f'verdict {verdict}' if verdict else
                         ('dossier d’un autre client' if not d.get('demandeur') else 'verdict en attente')))
    vehicules = f.get('vehicules') or []
    if vehicules:
        x = vehicules[0]
        prix = [v['prix'] for v in vehicules if v.get('prix')]
        tuiles += [_t('Véhicule', ' '.join(filter(None, (x.get('marque'), x.get('modele')))) or None,
                      source=SOURCES.get(x.get('type_piece'), x.get('type_piece')), detail=x.get('etat')),
                   _t('Prix du véhicule', max(prix) if prix else None, 'montant', source='facture proforma')]
    return tuiles
