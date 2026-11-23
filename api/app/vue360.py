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
# taux d'endettement. Épuré le même jour : rien de ce que l'en-tête montre déjà, une incohérence ou une famille de
# contrôles seulement si elle alerte, aucune tuile vide hors du groupe « À venir » (sources non branchées).
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


def _t(libelle, valeur, format='texte', ton='neutre', source=None, detail=None, lien=None):
    return dict(libelle=libelle, valeur=valeur, format=format, ton=ton, source=LIBELLES_SOURCE.get(source, source),
                detail=detail, lien=lien)


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


def _compte_bancaire(f):
    c = (f.get('comptes') or [None])[0] or {}
    valeur = ' · '.join(filter(None, (c.get('rib'), c.get('banque')))) or None
    n = len(f.get('comptes') or [])
    return _t('Compte', valeur, source='relevés', detail=f'{n} comptes lus' if n > 1 else c.get('titulaire'))


def _liste_noire(f):
    ident, ln, chemins = f['identite'], f.get('liste_noire') or [], f.get('chemins') or []
    if ident.get('inscrit'):
        x = ln[0] if ln else {}
        detail = ' · '.join(filter(None, (x.get('motif') or x.get('type_fraude'), x.get('statut'),
                                           f"depuis le {_iso(x.get('premiere_saisie'))}" if x.get('premiere_saisie') else None)))
        tuiles = [_t('Liste noire', x.get('typeListe') or 'Inscrit', ton='critique', source='liste noire EQDOM',
                     detail=detail or None)]
    else:
        tuiles = [_t('Liste noire', 'Non inscrit', ton='bon', source='liste noire EQDOM')]
    if chemins:
        c = chemins[0]
        force = f"{c.get('force', 0):.2f}".replace('.', ',')
        tuiles += [_t('Meilleur chemin', f"{c.get('niveau')} · force {force}", ton=TON_NIVEAU.get(c.get('niveau'), 'neutre'),
                      source='carte des réseaux', detail=f"{c.get('longueur')} lien(s), {len(chemins)} chemin(s)"
                      + (' · homonymie à lever' if c.get('homonymie') else '') + (' · même foyer' if c.get('foyer') else '')),
                   _t('Inscrit atteint', (c.get('inscrit') or {}).get('nom'), ton='attention', source='liste noire EQDOM')]
    elif not ident.get('inscrit'):
        tuiles.append(_t('Meilleur chemin', 'aucun', ton='bon', source='carte des réseaux', detail='à moins de 4 liens'))
    return tuiles


def _alertes(f):
    """Incohérences et familles de contrôles : une tuile par alerte, sinon une seule tuile rassurante pour chacune."""
    libelles = {'rib_autre_dossier': ('Même RIB dans le dossier d’un autre', 'critique'),
                'double_financement': ('Même châssis ailleurs', 'critique'),
                'dossiers_en_rafale': ('Dossiers en rafale', 'attention')}
    incoh = {i.get('type') for i in f.get('incoherences') or []}
    tuiles = [_t(lib, 'Oui', ton=ton, source='dossiers') for cle, (lib, ton) in libelles.items() if cle in incoh]
    autres = len(f.get('incoherences') or []) - len(tuiles)
    if autres > 0:
        tuiles.append(_t('Autres incohérences', autres, 'nombre', 'attention', 'dossiers et pièces'))
    if not tuiles:
        tuiles.append(_t('Incohérences', 'aucune', ton='bon', source='dossiers et pièces'))
    familles = f['vue360'].get('controles') or []
    for fam in familles:
        n = fam['anomalies']
        if not n:
            continue
        en_anomalie = [c for c in fam['controles'] if c['resultat'] == 'ANOMALIE']
        tuiles.append(_t(fam['famille'], f"{n} anomalie{'s' if n > 1 else ''}",
                         ton='critique' if any(c.get('criticite') == 'CRITIQUE' for c in en_anomalie) else 'attention',
                         source='antifraude v2', detail='; '.join(f"{c['controle']} {c.get('libelle') or ''}".strip()
                                                                  for c in en_anomalie)))
    if familles and not any(fam['anomalies'] for fam in familles):
        tuiles.append(_t('Contrôles', 'tous conformes', ton='bon', source='antifraude v2',
                         detail=f"{sum(len(x['controles']) for x in familles)} contrôle(s)"))
    return tuiles


def _historique(f):
    """Les 3 derniers dossiers (produit, rôle, verdict), puis le véhicule."""
    tuiles = []
    for d in sorted(f.get('dossiers') or [], key=lambda d: d.get('recu') or '', reverse=True)[:3]:
        jour = _jour(d.get('recu'))
        libelle = f'Dossier du {jour.day} {MOIS[jour.month - 1]} {jour.year}' if jour else 'Dossier'
        while any(x['libelle'] == libelle for x in tuiles):
            libelle += ' (bis)'
        verdict = d.get('verdict') if d.get('demandeur') else None
        tuiles.append(_t(libelle, ' · '.join(filter(None, (d.get('produit'), 'demandeur' if d.get('demandeur')
                                                              else d.get('role') or 'cité'))),
                         ton='neutre' if not verdict else 'bon' if verdict == 'CONFORME' else 'attention',
                         source='dossiers', detail=f'verdict {verdict}' if verdict else
                         ('dossier d’un autre client' if not d.get('demandeur') else 'verdict en attente'),
                         lien=f"dossier.html?i={d['indice']}" if d.get('indice') else None))
    vehicules = f.get('vehicules') or []
    if vehicules:
        x = vehicules[0]
        prix = max((v['prix'] for v in vehicules if v.get('prix')), default=None)
        tuiles.append(_t('Véhicule', ' '.join(filter(None, (x.get('marque'), x.get('modele')))) or None,
                         source=SOURCES.get(x.get('type_piece'), x.get('type_piece')),
                         detail=' · '.join(filter(None, (x.get('etat'), f'{prix:,.0f} DH'.replace(',', ' ') if prix else None)))))
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
    rel = _releves(f)
    groupes = [('Liste noire', _liste_noire(f)), ('Alertes', _alertes(f))]
    a_venir = [_t('Historique EQDOM', None, source='historique EQDOM', detail='contrats, impayés, classe BAM : ' + ATTEND_EQDOM),
               _t('Recouvrement', None, source='Reco', detail='relances et promesses : ' + ATTEND_RECO)]

    if prof == 'pm':
        forme, src_f = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['forme_juridique'])
        capital, src_k = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['capital_social', 'capital'])
        immat, src_i = _fait(f, ['REGISTRE_COMMERCE'], ['date_immatriculation', 'date_creation'])
        siege = entite.get('siege_partage')
        groupes.append(('Identité légale', [
            _t('Forme juridique', forme, source=src_f),
            _t('Capital', montant(capital) if capital is not None else None, 'montant', source=src_k),
            _t('Immatriculée le', _iso(immat), 'date', source=src_i),
            _t('Sociétés au même siège', siege, 'nombre', 'attention' if (siege or 0) >= 5 else 'neutre',
               'registre du commerce', 'au-delà de 5 : domiciliation probable')]))
        personnes = _regrouper(f.get('personnes') or [])
        changements = [p for p in personnes if any(t in r for r in p['roles'] for t in ('nouveau', 'sortant', 'cédant'))]
        dirigeants = [_t(p['nom'], ', '.join(p['roles']), ton='critique' if p.get('inscrit') else 'neutre',
                         source=p.get('source'), detail='inscrit sur la liste noire' if p.get('inscrit') else None)
                      for p in personnes[:4]]
        if changements:
            dirigeants.append(_t('Changements de dirigeants', len(changements), 'nombre', 'attention',
                                 'registre du commerce', 'nouveau gérant, sortant, cession'))
        groupes.append(('Dirigeants', dirigeants))
        soeurs = entite.get('soeurs') or []
        groupes.append(('Comptes et réseau', [
            _compte_bancaire(f),
            _t('Crédits par mois', rel['moyenne']('total_credit'), 'montant', source='relevés',
               detail=f"débits {rel['moyenne']('total_debit'):,.0f} DH".replace(',', ' ') if rel['moyenne']('total_debit') else None),
            _t('Sociétés sœurs', ', '.join(soeurs[:3]) or None, ton='attention', source='registre du commerce',
               detail=f'{len(soeurs)} société(s) au même gérant ou associé')]))
        a_venir.append(_t('Chiffre d’affaires déclaré', None, source='liasse fiscale', detail='liasse fiscale non fournie'))

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
        groupes.append(('Sociétés et activité', societes[:4] + [_t('Activité depuis', _iso(creation), 'date', source=src_c)]))
        profession, src_p = _fait(f, ['CARTE_PROFESSIONNELLE'], ['profession', 'secteur'])
        fin = _jour(_fait(f, ['CARTE_PROFESSIONNELLE'], ['date_validite', 'date_expiration'])[0])
        titulaire, src_t = _fait(f, ['RELEVE_BANCAIRE', 'ATTESTATION_RIB'], ['type_titulaire'])
        types = {'PP': 'personnel', 'PM': 'professionnel', 'MORALE': 'professionnel'}
        groupes.append(('Revenus et pièces', [
            _t('Revenu retrouvé sur les relevés', pieces.get('RELEVE_BANCAIRE'), 'montant', source='relevés'),
            _t('Profession', profession, source=src_p),
            _t('Carte professionnelle valide jusqu’au', fin.isoformat() if fin else None, 'date',
               _validite(fin, ref, S['cin_bientot_jours']), 'carte professionnelle'),
            _compte_bancaire(f),
            _t('Type de compte', types.get(str(titulaire).upper(), titulaire) if titulaire else None, source=src_t)]))

    else:
        retraite = v.get('retraite')
        revenus = [_t('Revenu déclaré', rev.get('declare'), 'montant', source='déclaration')]
        for s, n in (('BULLETIN_DE_PAIE', 'Bulletin de paie'), ('ATTESTATION_TRAVAIL_SALAIRE', 'Attestation de salaire'),
                     ('ATTESTATION_PENSION', 'Pension')):
            if s in pieces:
                revenus.append(_t(n, pieces[s], 'montant', source=SOURCES[s]))
        revenus += [_t('Salaire retrouvé sur les relevés', pieces.get('RELEVE_BANCAIRE'), 'montant', source='relevés'),
                    _t('Écart entre pièces', rev.get('ecart'), 'pourcent',
                       _seuil(rev.get('ecart'), S['ecart_attention'], S['ecart_critique']), 'pièces de revenu',
                       'signalé au-delà de 15 %')]
        source_ = next((c['montant'] for c in sorted(f.get('charges') or [], key=lambda c: (c.get('annee') or 0,
                        c.get('mois') or 0), reverse=True) if c.get('nature') == 'credit_source'), None)
        echeances = rel['echeances']
        verifie = next((pieces[s] for s in ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION',
                                            'RELEVE_BANCAIRE') if pieces.get(s)), None)
        endettement = ((echeances or 0) + (source_ or 0)) / verifie if verifie and (
            echeances is not None or source_ is not None) else None
        revenus.append(_t('Taux d’endettement', endettement, 'pourcent',
                          _seuil(endettement, S['endettement_attention'], S['endettement_critique']),
                          'relevés et pièces de revenu',
                          ' + '.join(filter(None, (f'échéances {echeances:,.0f} DH'.replace(',', ' ') if echeances else None,
                                                   f'à la source {source_:,.0f} DH'.replace(',', ' ') if source_ else None)))
                          or None))
        groupes.append(('Revenus et charges', revenus))

        ids = f.get('identifiants') or []
        if retraite:
            organisme, src = _fait(f, ['ATTESTATION_PENSION'], ['nom_organisme_retraite', 'caisse'])
            emploi = [_t('Organisme de pension', organisme, source=src),
                      _t('N° de pension', next((i['valeur'] for i in ids if i.get('type') == 'PENSION'), None),
                         source='attestation de pension')]
        else:
            employeur, src = _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'],
                                   ['employeur.raison_sociale', 'employeur.nom', 'raison_sociale'])
            relie = next((s for s in f.get('societes') or [] if s.get('role') in ROLES_SALARIE), None)
            embauche, src_e = _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'], ['date_embauche', 'date_entree'])
            emploi = [_t('Employeur', employeur or (relie or {}).get('nom'), ton='critique' if relie and relie.get('inscrit')
                         else 'neutre', source=src or 'registre du commerce',
                         detail='inscrit sur la liste noire' if relie and relie.get('inscrit') else None),
                      _t('Date d’embauche', _iso(embauche), 'date', source=src_e),
                      _t('Clients EQDOM qui le déclarent', entite.get('employeur_clients'), 'nombre', source='base client'),
                      _t('N° CNSS', next((i['valeur'] for i in ids if i.get('type') == 'CNSS'), None),
                         source='bulletin de paie')]
            a_venir.append(_t('Salaire versé par un autre', None, source='relevés', detail=NON_EXTRAIT))
        emploi.append(_compte_bancaire(f))
        if v.get('aussi'):
            roles = sorted({s.get('role') for s in v['aussi'] if s.get('role')})
            emploi.append(_t(f"Aussi {' et '.join(roles)} de", ', '.join(s['nom'] for s in v['aussi']), ton='attention',
                             source='registre du commerce'))
        groupes.append(('Pension et compte' if retraite else 'Emploi et compte', emploi))

    expiration = None if prof == 'pm' else _jour(_fait(f, ['CIN'], ['date_expiration'])[0])
    if expiration:
        groupes.append(('Identité', [_t('Expiration de la CIN', expiration.isoformat(), 'date',
                                        _validite(expiration, ref, S['cin_bientot_jours']), 'CIN',
                                        'à la date du dernier dossier')]))
    groupes.append(('Historique des dossiers', _historique(f)))
    groupes.append(('À venir', a_venir))
    sortie = []
    for nom, liste in groupes:
        garde = liste if nom == 'À venir' else [x for x in liste if x['valeur'] not in (None, '')]
        if garde:
            sortie.append(dict(groupe=nom, tuiles=garde))
    return sortie


# ---- présentation pour la direction (Lounès, 19/11/2026) : est-ce un bon client, demande-t-il souvent des prêts ? ---
# Des faits et des points forts ou de vigilance rédigés en clair, jamais un verdict « bon / mauvais client » calculé
# (le score ne décide jamais seul, loi 09-08 art. 11) ; aucun vocabulaire de fraude : l'antifraude tient dans une petite
# partie à part. Seuils provisoires (formulation seulement), à valider avec la direction des risques.
SEUILS_PRESENTATION = dict(endettement=0.40, ecart=0.15, emploi_stable_ans=2, emploi_recent_ans=1,
                           activite_installee_ans=3, demandes_rapprochees_mois=6)


def _annees(debut, fin):
    if not debut or not fin or debut > fin:
        return None
    return fin.year - debut.year - ((fin.month, fin.day) < (debut.month, debut.day))


def _jour_lisible(j):
    return f'{j.day} {MOIS[j.month - 1]} {j.year}'


def _pct(x):
    return f'{round(x * 100)} %'


def _parts(x):
    """Parts lues (« 60 », 60.0, « 33,5 ») en nombre ; un entier reste entier ; None si illisible."""
    if x in (None, ''):
        return None
    try:
        n = float(str(x).replace(',', '.').replace('%', '').strip())
    except ValueError:
        return None
    return int(n) if n == int(n) else n


def _portrait(f, prof):
    """Qui est le client, en clair : quelques faits lus dans ses pièces, et les personnes (gérants, associés) ou les
    sociétés qui l'entourent, avec les parts. Rien de l'antifraude (ni inscription ni lien)."""
    faits, personnes, titre, groupe = [], [], None, []
    if prof == 'pm':
        objet = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['objet_social', 'objet_commerce', 'objet_du_commerce'])[0]
        forme = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['forme_juridique'])[0]
        capital = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['capital_social', 'capital'])[0]
        capital = montant(capital) if capital is not None else None
        tribunal = _fait(f, ['REGISTRE_COMMERCE'], ['tribunal_commerce', 'ville_tribunal'])[0] or f['identite'].get('tribunal')
        faits = [('Activité', objet),
                 ('Forme et capital', ' · '.join(filter(None, (forme, f'{capital:,.0f} DH'.replace(',', ' ')
                                                                    if capital is not None else None))) or None),
                 ('Siège', f['identite'].get('adresse')), ('Tribunal', tribunal)]
        par = {}
        for x in f.get('personnes') or []:
            q = par.setdefault(x.get('indice') or x.get('nom'), dict(nom=x.get('nom'), roles=[], parts=None,
                                                                    indice=x.get('indice')))
            if x.get('role') and x['role'] not in q['roles']:
                q['roles'].append(x['role'])
            n = _parts(x.get('parts'))
            if n is not None and (q['parts'] is None or n > q['parts']):
                q['parts'] = n
        dirigeant = lambda q: any(r in ('gérant', 'dirigeant', 'nouveau gérant') for r in q['roles'])  # noqa: E731
        total = sum(q['parts'] for q in par.values() if q['parts'])     # parts sociales : un nombre, pas un pourcentage
        for q in par.values():
            q['pourcentage'] = round(100 * q['parts'] / total, 1) if total and q['parts'] else None
        personnes = [dict(nom=q['nom'], roles=q['roles'], parts=q['parts'], pourcentage=q['pourcentage'], indice=q['indice'])
                     for q in sorted(par.values(), key=lambda q: (not dirigeant(q), -(q['parts'] or 0), q['nom'] or ''))]
        titre, groupe = 'Gérants et associés', list((f['vue360'].get('entite') or {}).get('soeurs') or [])[:6]
    elif prof == 'entrepreneur':
        faits = [('Profession', _fait(f, ['CARTE_PROFESSIONNELLE'], ['profession'])[0]),
                 ('Secteur', _fait(f, ['CARTE_PROFESSIONNELLE'], ['secteur'])[0]),
                 ('Adresse', f['identite'].get('adresse'))]
        parts = {m.get('societe'): _parts(m.get('parts')) for m in f.get('registre') or []}
        for s in _regrouper(f.get('societes') or []):
            if any(r in ROLES_SALARIE for r in s['roles']):
                continue
            personnes.append(dict(nom=s['nom'], roles=s['roles'], parts=parts.get(s['nom']), pourcentage=None,
                                  indice=s.get('indice'),
                                  termine=all(any(t in r for t in ROLES_TERMINES) for r in s['roles'])))
        personnes.sort(key=lambda q: (q['termine'], q['nom'] or ''))
        titre = 'Ses sociétés'
    else:
        if f['vue360'].get('retraite'):
            faits = [('Organisme de pension', _fait(f, ['ATTESTATION_PENSION'], ['nom_organisme_retraite', 'caisse'])[0])]
        else:
            relie = next((s for s in f.get('societes') or [] if s.get('role') in ROLES_SALARIE), None)
            faits = [('Employeur', _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'],
                                         ['employeur.raison_sociale', 'employeur.nom', 'raison_sociale'])[0]
                      or (relie or {}).get('nom')),
                     ('Fonction', _fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'], ['fonction', 'profession'])[0]),
                     ('Contrat', _fait(f, ['ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE'], ['type_contrat'])[0])]
        faits.append(('Adresse', f['identite'].get('adresse')))
    return dict(faits=[dict(libelle=k, valeur=v) for k, v in faits if v not in (None, '')], titre=titre,
                personnes=personnes, groupe=groupe)


def presentation(f):
    """{chiffres, demandes, rythme, forts, vigilance, remboursements, antifraude} : la présentation du client."""
    S = SEUILS_PRESENTATION
    v = f['vue360']
    prof, retraite = v['profil'], v.get('retraite')
    pieces, ecart = (v.get('revenus') or {}).get('pieces') or {}, (v.get('revenus') or {}).get('ecart')
    propres = sorted((d for d in f.get('dossiers') or [] if d.get('demandeur') and _jour(d.get('recu'))),
                     key=lambda d: d['recu'])
    ref = _jour(propres[-1]['recu']) if propres else None
    connu = {'1': 'oui', 'true': 'oui', '0': 'non', 'false': 'non'}.get(str(_contexte(f, 'Client connu')).lower())
    forts, vigilance = [], []

    demandes = [dict(date=_jour(d['recu']).isoformat(), produit=d.get('produit'), verdict=d.get('verdict'),
                     indice=d.get('indice')) for d in propres]
    if not demandes:
        rythme = 'aucune demande en propre'
    elif len(demandes) == 1:
        rythme = f"1 demande, le {_jour_lisible(_jour(demandes[0]['date']))}"
    else:
        a, b = _jour(demandes[0]['date']), _jour(demandes[-1]['date'])
        mois = (b.year - a.year) * 12 + b.month - a.month
        rythme = f'{len(demandes)} demandes ' + (f'en {mois} mois' if mois else 'le même mois')
        (vigilance if mois <= S['demandes_rapprochees_mois'] else forts).append(
            f'Demandes rapprochées : {rythme}' if mois <= S['demandes_rapprochees_mois']
            else f'Client fidèle : {rythme}')
    if connu == 'oui':
        forts.append('Déjà client d’EQDOM')
    demandes_chiffre = dict(libelle='Demandes de prêt', valeur=len(demandes), format='nombre',
                            detail=f"depuis le {_jour_lisible(_jour(demandes[0]['date']))}" if demandes else None)
    connu_chiffre = dict(libelle='Client connu d’EQDOM', valeur=connu, format='texte', detail='déclaré au dossier')

    if prof == 'pm':
        rel = _releves(f)
        immat = _jour(_fait(f, ['REGISTRE_COMMERCE'], ['date_immatriculation', 'date_creation'])[0])
        age = _annees(immat, ref)
        capital = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['capital_social', 'capital'])[0]
        chiffres = [dict(libelle='Crédits mensuels', valeur=rel['moyenne']('total_credit'), format='montant',
                         detail='moyenne des relevés'),
                    dict(libelle='Ancienneté de la société', valeur=age, format='ans',
                         detail=f'immatriculée le {_jour_lisible(immat)}' if immat else None),
                    dict(libelle='Capital', valeur=montant(capital) if capital is not None else None, format='montant',
                         detail=_fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['forme_juridique'])[0]),
                    demandes_chiffre, connu_chiffre]
        if age is not None:
            if age >= S['activite_installee_ans']:
                forts.append(f'Société établie depuis {age} ans')
            elif age < S['emploi_recent_ans']:
                vigilance.append('Société créée il y a moins d’un an')
    else:
        verifie = next((pieces[s] for s in ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION',
                                            'RELEVE_BANCAIRE') if pieces.get(s)), None)
        source_ = next((c['montant'] for c in sorted(f.get('charges') or [], key=lambda c: (c.get('annee') or 0,
                        c.get('mois') or 0), reverse=True) if c.get('nature') == 'credit_source'), None)
        echeances = _releves(f)['echeances']
        endettement = ((echeances or 0) + (source_ or 0)) / verifie if verifie and (
            echeances is not None or source_ is not None) else None
        if prof == 'entrepreneur':
            creation = _jour(_fait(f, ['REGISTRE_COMMERCE'], ['date_creation', 'date_immatriculation', 'date_debut'])[0])
            activite = _annees(creation, ref)
            societes = [s for s in _regrouper(f.get('societes') or []) if not any(r in ROLES_SALARIE for r in s['roles'])
                        and not all(any(t in r for t in ROLES_TERMINES) for r in s['roles'])]
            chiffres = [dict(libelle='Revenu mensuel sur les relevés', valeur=pieces.get('RELEVE_BANCAIRE'),
                             format='montant', detail='revenu d’activité'),
                        dict(libelle='Activité depuis', valeur=activite, format='ans',
                             detail=_jour_lisible(creation) if creation else None),
                        dict(libelle='Sociétés', valeur=len(societes), format='nombre', detail='rôles en cours'),
                        demandes_chiffre, connu_chiffre]
            if activite is not None:
                if activite >= S['activite_installee_ans']:
                    forts.append(f'Activité installée depuis {activite} ans')
                elif activite < S['emploi_recent_ans']:
                    vigilance.append('Activité de moins d’un an')
        else:
            embauche = None if retraite else _jour(_fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'],
                                                         ['date_embauche', 'date_entree'])[0])
            anciennete = _annees(embauche, ref)
            chiffres = [dict(libelle='Pension mensuelle' if retraite else 'Revenu mensuel vérifié',
                             valeur=pieces.get('ATTESTATION_PENSION') if retraite else verifie, format='montant',
                             detail='justifiée par l’attestation' if retraite else 'bulletin, attestation ou relevés'),
                        dict(libelle='Taux d’endettement', valeur=endettement, format='pourcent',
                             detail='crédits du mois / revenu vérifié')]
            if not retraite:
                chiffres.append(dict(libelle='Ancienneté chez l’employeur', valeur=anciennete, format='ans',
                                     detail=_fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'],
                                                  ['employeur.raison_sociale', 'employeur.nom'])[0]))
            chiffres += [demandes_chiffre, connu_chiffre]
            if anciennete is not None:
                if anciennete >= S['emploi_stable_ans']:
                    forts.append(f'Emploi stable : {anciennete} ans chez le même employeur')
                elif anciennete < S['emploi_recent_ans']:
                    vigilance.append('Embauche de moins d’un an')
        if endettement is not None:
            (forts if endettement < S['endettement'] else vigilance).append(
                f"Endettement {'maîtrisé' if endettement < S['endettement'] else 'élevé'} ({_pct(endettement)} du revenu)")
        if ecart is not None and len([p for p in pieces.values() if p]) >= 2:
            (forts if ecart <= S['ecart'] else vigilance).append(
                f"Revenus {'concordants' if ecart <= S['ecart'] else 'divergents'} entre les pièces (écart {_pct(ecart)})")

    for c in chiffres:
        c['ton'] = ('attention' if c['libelle'] == 'Taux d’endettement' and c['valeur'] is not None
                    and c['valeur'] >= S['endettement'] else 'neutre')
    chemins = f.get('chemins') or []
    anomalies = sum(fam['anomalies'] for fam in v.get('controles') or [])
    return dict(chiffres=chiffres, portrait=_portrait(f, prof), demandes=demandes, rythme=rythme, forts=forts,
                vigilance=vigilance,
                remboursements='Contrats, impayés et classe BAM chez EQDOM : ' + ATTEND_EQDOM + '.',
                antifraude=dict(liste_noire=bool(f['identite'].get('inscrit')),
                                lien=chemins[0].get('niveau') if chemins else None,
                                alertes=len(f.get('incoherences') or []) + anomalies))


# ---- vue en étoile (Lounès, 23/11/2026) : au centre un bonhomme ou une maison, autour ses informations ---------------
# Les branches reprennent la présentation (chiffres, portrait, demandes) et l'identité ; rien de l'antifraude.
PRODUITS = dict(DISPO='Crédit disponible', AUTO_CLASSIQUE='Crédit auto', LOA='Location avec option d’achat')
PROFILS_LISIBLES = dict(salarie='Personne physique · salariée', entrepreneur='Personne physique · entrepreneur',
                        pm='Personne morale')


def _ligne(libelle, valeur, format_='texte', lien=None):
    return dict(libelle=libelle, valeur=valeur, format=format_, lien=lien)


def _fiche_lien(indice):
    return f'fiche.html?i={indice}' if indice else None


def etoile(f, p):
    """{centre: {figure, nom, profil}, branches: [{cle, titre, resume, lignes}]} ; une branche sans ligne disparaît,
    sauf les demandes de prêt."""
    v, ident = f['vue360'], f['identite']
    prof, retraite = v['profil'], v.get('retraite')
    chiffre = {c['libelle']: c for c in p['chiffres']}
    fait = {x['libelle']: x['valeur'] for x in p['portrait']['faits']}
    val = lambda libelle: (chiffre.get(libelle) or {}).get('valeur')  # noqa: E731
    branches = []

    def branche(cle, titre, lignes, resume=None, garder=False):
        lignes = [x for x in lignes if x['valeur'] not in (None, '')]
        if lignes or garder:
            branches.append(dict(cle=cle, titre=titre, resume=resume, lignes=lignes))

    def personnes(liste):
        sortie = []
        for q in liste:
            pct = q.get('pourcentage')
            pct = None if pct is None else (f'{int(pct)} %' if pct == int(pct) else f'{pct} %'.replace('.', ','))
            libelle = ', '.join(q['roles']) + (f' · {pct}' if pct else '') + (' · terminé' if q.get('termine') else '')
            sortie.append(_ligne(libelle or 'rôle non lu', q['nom'], lien=_fiche_lien(q.get('indice'))))
        return sortie

    if prof == 'pm':
        rc = ' · '.join(filter(None, (ident.get('rc'), ident.get('tribunal')))) or None
        forme = _fait(f, ['REGISTRE_COMMERCE', 'STATUTS'], ['forme_juridique'])[0]
        branche('legal', 'Identité légale', [_ligne('RC', rc), _ligne('ICE', ident.get('ice')), _ligne('Forme juridique', forme),
                                             _ligne('Capital', val('Capital'), 'montant')])
        branche('activite', 'Activité', [_ligne('Objet', fait.get('Activité')),
                                         _ligne('Ancienneté', val('Ancienneté de la société'), 'ans')])
        branche('dirigeants', 'Gérants et associés', personnes(p['portrait']['personnes']))
        branche('siege', 'Siège', [_ligne('Adresse', ident.get('adresse'))])
        branche('groupe', 'Sociétés sœurs', [_ligne('même dirigeant', g) for g in p['portrait'].get('groupe') or []])
        branche('flux', 'Flux bancaires', [_ligne('Banque', ((f.get('comptes') or [{}])[0]).get('banque'))])
    else:
        cin = ident.get('cin')
        branche('identite', 'Identité', [_ligne('CIN', cin), _ligne('Date de naissance', ident.get('date_naissance'), 'date'),
                                         _ligne('Adresse', ident.get('adresse'))])
        if prof == 'entrepreneur':
            branche('activite', 'Activité', [_ligne('Profession', fait.get('Profession')),
                                             _ligne('Secteur', fait.get('Secteur')),
                                             _ligne('Activité depuis', val('Activité depuis'), 'ans')])
        elif retraite:
            branche('emploi', 'Pension', [_ligne('Organisme', fait.get('Organisme de pension'))])
        else:
            branche('emploi', 'Emploi', [_ligne('Employeur', fait.get('Employeur')), _ligne('Fonction', fait.get('Fonction')),
                                         _ligne('Contrat', fait.get('Contrat')),
                                         _ligne('Ancienneté', val('Ancienneté chez l’employeur'), 'ans')])
        branche('revenus', 'Revenus', [_ligne(c['libelle'], c['valeur'], c['format']) for c in p['chiffres']
                                       if c['format'] in ('montant', 'pourcent')])
        comptes = f.get('comptes') or []
        branche('banque', 'Banque', [_ligne('Banque', (comptes[0] if comptes else {}).get('banque')),
                                     _ligne('Comptes lus', len(comptes) or None, 'nombre')])
        if prof == 'entrepreneur':
            branche('societes', 'Ses sociétés', personnes(p['portrait']['personnes']))
        else:
            branche('societes', 'Ses sociétés', [_ligne(s.get('role') or 'rôle non lu', s['nom'],
                                                        lien=_fiche_lien(s.get('indice'))) for s in v.get('aussi') or []])

    demandes = []
    for d in p['demandes']:
        x = _ligne(_jour_lisible(_jour(d['date'])), PRODUITS.get(d.get('produit'), d.get('produit') or 'prêt'),
                   lien=f"dossier.html?i={d['indice']}" if d.get('indice') else None)
        x['ton'] = (d.get('verdict') or 'attente').lower()
        demandes.append(x)
    branche('demandes', 'Demandes de prêt', demandes, resume=p['rythme'], garder=True)
    branche('eqdom', 'Chez EQDOM', [_ligne('Client connu', val('Client connu d’EQDOM'))])
    branches, a_venir = _organiser(_completer(branches, f, prof), f, p, prof)
    nom_profil = 'Personne physique · retraitée' if retraite and prof != 'pm' else PROFILS_LISIBLES[prof]
    return dict(centre=dict(figure='maison' if prof == 'pm' else 'personne', nom=ident.get('nom'), profil=nom_profil,
                            faits=_centre_faits(f, p)),
                signaux=_signaux(f), essentiel=_essentiel(f, p), branches=branches, a_venir=a_venir)


# ---- toutes les informations sur les plaques (Lounès, 23/11/2026 : « vraiment toutes les infos visibles au premier coup
# d'œil ») : les tuiles du détail, les identifiants, comptes, charges, incohérences et contrôles rejoignent les plaques ;
# l'antifraude a ses trois plaques à elle, en fin d'étoile. Restent repliées les seules données brutes (opérations,
# pièces champ par champ).
TITRES_BRANCHES = dict(identite='Identité', emploi='Emploi', activite='Activité', revenus='Revenus', banque='Banque',
                       societes='Ses sociétés', demandes='Demandes de prêt', eqdom='Chez EQDOM', legal='Identité légale',
                       dirigeants='Gérants et associés', siege='Siège', groupe='Sociétés sœurs', flux='Flux bancaires',
                       liste_noire='Liste noire et réseau', controles='Contrôles de l’antifraude')
ANTIFRAUDE = ('liste_noire', 'controles')      # pas de plaque « Alertes » (Lounès, 23/11/2026)
ORDRE_BRANCHES = dict(pp=('identite', 'emploi', 'activite', 'revenus', 'banque', 'societes', 'demandes', 'eqdom') + ANTIFRAUDE,
                      pm=('legal', 'activite', 'dirigeants', 'siege', 'groupe', 'flux', 'demandes', 'eqdom') + ANTIFRAUDE)
ROUTE_GROUPE = {'Liste noire': 'liste_noire', 'Revenus et charges': 'revenus',
                'Revenus et pièces': 'revenus', 'Emploi et compte': 'emploi', 'Pension et compte': 'emploi',
                'Identité légale': 'legal', 'Sociétés et activité': 'societes', 'Dirigeants': 'dirigeants',
                'Comptes et réseau': 'flux', 'Identité': 'identite', 'Historique des dossiers': 'demandes',
                'À venir': 'eqdom'}
ROUTE_LIBELLE = {'Compte': 'banque', 'Type de compte': 'banque', 'N° CNSS': 'identite', 'N° de pension': 'identite',
                 'Profession': 'activite', 'Carte professionnelle valide jusqu’au': 'activite',
                 'Activité depuis': 'activite', 'Sociétés au même siège': 'siege', 'Sociétés sœurs': 'groupe',
                 'Chiffre d’affaires déclaré': 'flux'}
NOMS_IDENTIFIANTS = dict(CIN='CIN', CNSS='N° CNSS', PENSION='N° de pension', ICE='ICE', RC='RC', RC_TRIB='RC',
                         IF='Identifiant fiscal',
                         PATENTE='Patente', AFFILIATION='N° d’affiliation')


def _completer(branches, f, prof):
    """Ajoute aux plaques tout ce que montrait le détail, sans doublon (même libellé, même nom, même lien)."""
    par = {b['cle']: b for b in branches}
    v, ident = f['vue360'], f['identite']

    def ajouter(cle, x):
        if prof == 'pm' and cle in ('banque', 'identite'):
            cle = 'flux' if cle == 'banque' else 'legal'
        if cle not in par:
            par[cle] = dict(cle=cle, titre=TITRES_BRANCHES[cle], resume=None, lignes=[])
        par[cle]['lignes'].append(x)

    def connu(t):
        for b in par.values():
            for x in b['lignes']:
                if x['libelle'] == t['libelle'] or (t.get('lien') and x.get('lien') == t['lien']):
                    return True
                if isinstance(t['valeur'], str) and len(t['valeur']) > 6 and str(x['valeur']) in (t['valeur'], t['libelle']):
                    return True
                if str(x['valeur']) == t['libelle']:
                    return True
        if isinstance(t['valeur'], str) and ', ' in t['valeur']:     # une liste de noms déjà tous sur les plaques
            noms = {str(x['valeur']) for b in par.values() for x in b['lignes']}
            return all(n in noms for n in t['valeur'].split(', '))
        return False

    # identifiants, autres écritures du nom, autres adresses
    for i in f.get('identifiants') or []:
        nom = NOMS_IDENTIFIANTS.get(i.get('type'), i.get('type'))
        x = _ligne(nom, i.get('valeur'))
        if i.get('valeur') and not connu(x):
            ajouter('identite', x)
    alias = [a['nom'] for a in f.get('alias') or [] if a.get('nom') and a['nom'] != ident.get('nom')]
    if alias:
        ajouter('identite', _ligne('Autres écritures du nom', ', '.join(alias)))
    for a in f.get('adresses') or []:
        if a.get('adresse') and a['adresse'] != ident.get('adresse') and not connu(_ligne('Adresse', a['adresse'])):
            ajouter('siege' if prof == 'pm' else 'identite', _ligne('Autre adresse', a['adresse']))
    # comptes et charges
    for c in f.get('comptes') or []:
        valeur = ' · '.join(filter(None, (c.get('rib'), c.get('banque'))))
        if valeur:
            ajouter('banque', _ligne('RIB', valeur))
    charges = sorted(f.get('charges') or [], key=lambda c: (c.get('annee') or 0, c.get('mois') or 0), reverse=True)
    source_ = next((c for c in charges if c.get('nature') == 'credit_source'), None)
    if source_:
        ajouter('banque', _ligne('Crédit prélevé à la source', source_['montant'], 'montant'))
    echeances = _releves(f)['echeances']
    if echeances:
        ajouter('banque', _ligne('Échéances de crédit repérées', echeances, 'montant'))
    # tuiles du détail, sauf les alertes : ni plaque ni ligne « Alertes » (Lounès, 23/11/2026, « retire-la partout ») ;
    # les incohérences restent dans les données brutes
    for g in tuiles(f):
        for t in g['tuiles']:
            if connu(t) or g['groupe'] == 'Alertes':
                continue
            a_venir = t['valeur'] in (None, '')
            x = _ligne(t['libelle'], 'à venir' if a_venir else t['valeur'], 'texte' if a_venir else t['format'], t.get('lien'))
            x.update(ton=t.get('ton'), detail=t.get('detail'), source=t.get('source'))
            ajouter(ROUTE_LIBELLE.get(t['libelle']) or ROUTE_GROUPE.get(g['groupe'], 'eqdom'), x)
    # contrôles par famille
    for fam in v.get('controles') or []:
        n, a = len(fam['controles']), fam['anomalies']
        anomalies = [c for c in fam['controles'] if c['resultat'] == 'ANOMALIE']
        x = _ligne(fam['famille'], f"{a} anomalie{'s' if a > 1 else ''} sur {n}" if a else f"{n} conforme{'s' if n > 1 else ''}")
        x.update(ton='critique' if any(c.get('criticite') == 'CRITIQUE' for c in anomalies) else 'attention' if a else 'bon',
                 detail='; '.join(f"{c['controle']} {c.get('libelle') or ''}".strip() for c in anomalies) or None)
        ajouter('controles', x)
    ordre = ORDRE_BRANCHES['pm' if prof == 'pm' else 'pp']
    return [par[k] for k in ordre if k in par and (par[k]['lignes'] or k == 'demandes')] + \
        [b for k, b in par.items() if k not in ordre and b['lignes']]


# ---- lecture par la direction (Lounès, 23/11/2026 : « que les dirigeants puissent tout comprendre d'un client, sans
# inventer de données ») : au centre qui est le client, trois signaux factuels et l'essentiel chiffré ; autour, trois
# zones qui répondent chacune à une question : qui est-ce ? peut-il rembourser ? que s'est-il passé ? Les sources pas
# encore branchées passent en pied de page. Aucune donnée nouvelle : tout est lu dans la fiche servie.
ZONES_BRANCHES = dict(identite='qui', emploi='qui', activite='qui', societes='qui', legal='qui', siege='qui',
                      dirigeants='qui', groupe='qui', revenus='capacite', credits='capacite', banque='capacite',
                      flux='capacite', demandes='historique', liste_noire='historique', controles='historique')
ZONES = ('qui', 'capacite', 'historique')
ORDRE_LECTURE = dict(pp=('identite', 'emploi', 'activite', 'societes', 'revenus', 'credits', 'banque', 'demandes',
                         'liste_noire', 'controles'),
                     pm=('legal', 'activite', 'siege', 'dirigeants', 'groupe', 'flux', 'demandes', 'liste_noire',
                         'controles'))
LIENS_CHEMIN = dict(RIB='même RIB', SIEGE='même siège', CHASSIS='même châssis', AFFILIATION='même n° d’affiliation',
                    CNSS='même n° CNSS', ADRESSE='même adresse', TELEPHONE='même téléphone', ICE='même ICE')
EN_BARRES = frozenset({'Revenu mensuel vérifié', 'Revenu déclaré', 'Bulletin de paie', 'Attestation de salaire', 'Pension',
                       'Pension mensuelle', 'Salaire retrouvé sur les relevés', 'Revenu mensuel sur les relevés',
                       'Revenu retrouvé sur les relevés', 'Taux d’endettement'})
VERS_CREDITS = frozenset({'Échéances de crédit repérées', 'Crédit prélevé à la source', 'Taux d’endettement'})
REPERE_ENDETTEMENT_NOTE = 'repère de 40 % provisoire, à valider par la direction des risques'


def _pluriel(n, mot, pluriel=None):
    return f"{n} {mot if n <= 1 else (pluriel or mot + 's')}"


def _mois_releves(f):
    mois = [m for x in f.get('donnees') or [] if x.get('demandeur') for p in x.get('pieces') or []
            if p.get('type') == 'RELEVE_BANCAIRE' for m in p.get('mois') or [] if m.get('mois')]
    par = {}
    for m in mois:                                  # un mois lu deux fois (deux relevés) : le dernier lu
        par[(m.get('annee') or 0, m['mois'])] = m
    return [par[k] for k in sorted(par)]


def _tableau_mois(mois, lignes):
    if not mois:
        return None
    sortie = []
    for libelle, cle in lignes:
        valeurs = [m.get(cle) for m in mois]
        if any(v is not None for v in valeurs):
            sortie.append(dict(libelle=libelle, valeurs=valeurs))
    return dict(type='tableau', colonnes=[f"{MOIS[m['mois'] - 1]} {m.get('annee')}" for m in mois],
                lignes=sortie) if sortie else None


def _capacite(f, p):
    """(revenu vérifié, échéances, crédit à la source, endettement, reste) des pièces et relevés, ou None."""
    v = f['vue360']
    pieces = (v.get('revenus') or {}).get('pieces') or {}
    verifie = next((pieces[s] for s in ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION',
                                        'RELEVE_BANCAIRE') if pieces.get(s)), None)
    source_ = next((c['montant'] for c in sorted(f.get('charges') or [], key=lambda c: (c.get('annee') or 0,
                    c.get('mois') or 0), reverse=True) if c.get('nature') == 'credit_source'), None)
    echeances = _releves(f)['echeances']
    endettement = ((echeances or 0) + (source_ or 0)) / verifie if verifie and (
        echeances is not None or source_ is not None) else None
    reste = verifie - (echeances or 0) - (source_ or 0) if endettement is not None else None
    return verifie, echeances, source_, (round(endettement, 4) if endettement is not None else None), reste


def _signaux(f):
    ident, chemins = f['identite'], f.get('chemins') or []
    if ident.get('inscrit'):
        x = (f.get('liste_noire') or [{}])[0]
        ln = dict(cle='liste_noire', libelle='Liste noire', valeur=x.get('typeListe') or 'Inscrit', ton='critique',
                  detail=x.get('motif') or x.get('type_fraude') or None)
    else:
        ln = dict(cle='liste_noire', libelle='Liste noire', valeur='Non inscrit', ton='bon', detail=None)
    if chemins:
        c = chemins[0]
        n, inscrit = c.get('longueur') or 0, (c.get('inscrit') or {}).get('nom')
        soi = (c.get('inscrit') or {}).get('indice') == f.get('indice') and f.get('indice') is not None
        valeur = (f'À {_pluriel(n, "lien")} d’une personne inscrite' if n else 'Une identité du dossier est inscrite')
        etapes = c.get('etapes') or []
        fin = f'{inscrit}, sur la liste noire' if inscrit else 'une personne sur la liste noire'
        e0 = etapes[0] if len(etapes) == 1 else {}
        if e0.get('type') == 'identifiant':
            detail = f"{LIENS_CHEMIN.get(e0.get('code'), 'même ' + str(e0.get('code')).lower())} que {fin}"
        elif e0:
            detail = f"{inscrit or 'une personne'}, {e0.get('code') or 'lié'} de {(e0.get('de') or {}).get('nom')}, sur la liste noire"
        else:
            detail = f'jusqu’à {fin}'
        detail = None if soi else detail + (' · homonymie à lever' if c.get('homonymie') else '') + (
            ' · même foyer' if c.get('foyer') else '')
        reseau = dict(cle='reseau', libelle='Réseau', valeur=valeur, ton=TON_NIVEAU.get(c.get('niveau'), 'neutre'),
                      detail=detail)
    else:
        reseau = dict(cle='reseau', libelle='Réseau', valeur='Aucune personne inscrite à moins de 4 liens', ton='bon',
                      detail=None)
    familles = f['vue360'].get('controles') or []
    n = sum(len(x['controles']) for x in familles)
    a = sum(x['anomalies'] for x in familles)
    critique = any(c.get('criticite') == 'CRITIQUE' and c['resultat'] == 'ANOMALIE' for x in familles for c in x['controles'])
    if not n:
        ctrl = dict(cle='controles', libelle='Contrôles de la v2', valeur='aucun contrôle', ton='neutre', detail=None)
    elif a:
        ctrl = dict(cle='controles', libelle='Contrôles de la v2',
                    valeur=f"{_pluriel(a, 'anomalie')} sur {_pluriel(n, 'contrôle')}",
                    ton='critique' if critique else 'attention',
                    detail=', '.join(x['famille'] for x in familles if x['anomalies']))
    else:
        ctrl = dict(cle='controles', libelle='Contrôles de la v2',
                    valeur=f"{_pluriel(n, 'contrôle')} sur {n} {'conforme' if n == 1 else 'conformes'}", ton='bon',
                    detail=None)
    return [ln, reseau, ctrl]


def _centre_faits(f, p):
    propres = sorted((d for d in f.get('dossiers') or [] if d.get('demandeur') and _jour(d.get('recu'))),
                     key=lambda d: d['recu'])
    ref = _jour(propres[-1]['recu']) if propres else None
    faits = []
    if f['identite'].get('type') != 'societe':
        age = _annees(_jour(f['identite'].get('date_naissance')), ref)
        if age is not None:
            faits.append(f'{age} ans')
    connu = {'1': 'client EQDOM', 'true': 'client EQDOM', '0': 'nouveau client', 'false': 'nouveau client'}.get(
        str(_contexte(f, 'Client connu')).lower())
    if connu:
        faits.append(connu)
    agence, ville = _contexte(f, 'Agence'), _contexte(f, 'Ville de l\'agence')
    if agence:
        faits.append(' · '.join(filter(None, (f'agence {agence}', ville))))
    if propres:
        faits.append(f"première demande le {_jour_lisible(_jour(propres[0]['recu']))}")
    return faits


def _essentiel(f, p):
    S = SEUILS_PROVISOIRES
    v = f['vue360']
    prof, retraite = v['profil'], v.get('retraite')
    chiffre = {c['libelle']: c for c in p['chiffres']}
    vigilance, forts = list(p['vigilance']), list(p['forts'])
    if prof == 'pm':
        rel = _releves(f)
        chiffres = [dict(chiffre.get('Crédits mensuels') or {}, libelle='Crédits mensuels'),
                    dict(libelle='Échéances de crédit par mois', valeur=rel['echeances'], format='montant',
                         detail='dernier relevé'),
                    chiffre.get('Ancienneté de la société'), chiffre.get('Capital')]
    else:
        verifie, echeances, source_, endettement, reste = _capacite(f, p)
        if retraite:
            premier = dict(libelle='Pension mensuelle', valeur=verifie, format='montant', detail='attestation de pension')
        elif prof == 'entrepreneur':
            premier = dict(libelle='Revenu sur les relevés', valeur=verifie, format='montant', detail='revenu d’activité')
        else:
            sources = [SOURCES[s] for s in ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'RELEVE_BANCAIRE')
                       if ((v.get('revenus') or {}).get('pieces') or {}).get(s)]
            premier = dict(libelle='Revenu vérifié', valeur=verifie, format='montant',
                           detail=', '.join(sources) if sources else None)
        chiffres = [premier,
                    dict(libelle='Taux d’endettement', valeur=endettement, format='pourcent',
                         ton=_seuil(endettement, S['endettement_attention'], S['endettement_critique']),
                         detail='crédits du mois / revenu'),
                    dict(libelle='Reste après crédits', valeur=reste, format='montant', detail='par mois')]
        if prof == 'entrepreneur':
            chiffres.append(chiffre.get('Activité depuis'))
        elif not retraite:
            chiffres.append(dict(chiffre.get('Ancienneté chez l’employeur') or {}, libelle='Ancienneté chez l’employeur'))
        expiration = _jour(_fait(f, ['CIN'], ['date_expiration'])[0])
        propres = [_jour(d.get('recu')) for d in f.get('dossiers') or [] if d.get('demandeur') and _jour(d.get('recu'))]
        etat = _validite(expiration, max(propres) if propres else None, S['cin_bientot_jours'])
        if etat == 'critique':
            vigilance.append('CIN expirée à la date du dernier dossier')
        elif etat == 'attention':
            vigilance.append('CIN expirant dans moins de 3 mois')
        if prof == 'entrepreneur':
            fin = _jour(_fait(f, ['CARTE_PROFESSIONNELLE'], ['date_validite', 'date_expiration'])[0])
            if _validite(fin, max(propres) if propres else None, S['cin_bientot_jours']) == 'critique':
                vigilance.append('Carte professionnelle expirée à la date du dernier dossier')
    sortie = []
    for c in chiffres:
        if c and c.get('valeur') not in (None, ''):
            sortie.append(dict(libelle=c['libelle'], valeur=c['valeur'], format=c.get('format', 'texte'),
                               ton=c.get('ton') or 'neutre', detail=c.get('detail')))
    return dict(chiffres=sortie, forts=forts, vigilance=vigilance)


def _organiser(branches, f, p, prof):
    """Range les plaques par zone et par question ; transforme ce qui se lit mieux en visuel (revenus en barres,
    endettement en jauge, relevés mois par mois, chemin vers l'inscrit) ; sort les sources à venir en pied de page."""
    S = SEUILS_PROVISOIRES
    v, pm = f['vue360'], prof == 'pm'
    par = {b['cle']: b for b in branches}
    a_venir = []
    for b in branches:
        garde = []
        for x in b['lignes']:
            if x.get('valeur') == 'à venir':
                a_venir.append(dict(libelle=x['libelle'], detail=x.get('detail')))
            else:
                garde.append(x)
        b['lignes'] = garde
    eqdom = par.pop('eqdom', None)
    if eqdom and par.get('demandes'):
        par['demandes']['lignes'] += [x for x in eqdom['lignes'] if x['libelle'] != 'Client connu']

    def nouvelle(cle, titre):
        if cle not in par:
            par[cle] = dict(cle=cle, titre=titre, resume=None, lignes=[])
        return par[cle]

    def retirer(b, libelles):
        sortis = [x for x in b['lignes'] if x['libelle'] in libelles]
        b['lignes'] = [x for x in b['lignes'] if x['libelle'] not in libelles]
        return sortis

    mois = _mois_releves(f)
    if not pm:
        pieces = (v.get('revenus') or {}).get('pieces') or {}
        rev = par.get('revenus')
        if rev:
            retirer(rev, EN_BARRES)
            items = [('Déclaré', (v.get('revenus') or {}).get('declare')), ('Bulletin de paie', pieces.get('BULLETIN_DE_PAIE')),
                     ('Attestation de salaire', pieces.get('ATTESTATION_TRAVAIL_SALAIRE')),
                     ('Pension', pieces.get('ATTESTATION_PENSION')), ('Relevés (dernier mois)', pieces.get('RELEVE_BANCAIRE'))]
            items = [dict(libelle=k, valeur=x) for k, x in items if x]
            if items:
                rev['visuel'] = dict(type='barres', items=items)
        verifie, echeances, source_, endettement, reste = _capacite(f, p)
        for b in list(par.values()):
            if b['cle'] != 'credits':
                retirer(b, VERS_CREDITS)
        lignes = [_ligne('Échéances repérées sur les relevés', echeances, 'montant'),
                  _ligne('Crédit prélevé à la source', source_, 'montant'),
                  _ligne('Reste après crédits', reste, 'montant')]
        lignes = [x for x in lignes if x['valeur'] is not None]
        if lignes or endettement is not None:
            c = nouvelle('credits', 'Crédits en cours')
            c['lignes'] = lignes
            if endettement is not None:
                c['visuel'] = dict(type='jauge', libelle='Taux d’endettement', valeur=endettement,
                                   repere=S['endettement_attention'],
                                   ton=_seuil(endettement, S['endettement_attention'], S['endettement_critique']),
                                   note=REPERE_ENDETTEMENT_NOTE)
        banque = par.get('banque')
        if banque:
            ribs = [str(x['valeur']) for x in banque['lignes'] if x['libelle'] == 'RIB']
            banque['lignes'] = [x for x in banque['lignes'] if not (
                (x['libelle'] == 'Banque' and any(str(x['valeur']) in r for r in ribs))
                or (x['libelle'] == 'Comptes lus' and (x['valeur'] or 0) <= 1))]
            t = _tableau_mois(mois, (('Salaire reçu', 'salaire_detecte'), ('Échéances de crédit', 'echeances_credits'),
                                     ('Solde en fin de mois', 'solde_cloture')))
            if t:
                banque['visuel'] = t
        emploi = par.get('emploi')
        if emploi:
            embauche = _jour(_fait(f, ['BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE'], ['date_embauche', 'date_entree'])[0])
            for x in emploi['lignes']:
                if x['libelle'] == 'Ancienneté' and embauche:
                    x['detail'] = f'depuis le {_jour_lisible(embauche)}'
                if x['libelle'] == 'Clients EQDOM qui le déclarent':
                    x['libelle'] = 'Clients EQDOM chez cet employeur'
            emploi['lignes'] = [x for x in emploi['lignes'] if not (
                x['libelle'] == 'Date d’embauche' and embauche
                or x['libelle'] == 'Clients EQDOM chez cet employeur' and (x['valeur'] or 0) <= 1)]
        ident = par.get('identite')
        situation = _fait(f, ['ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE', 'ATTESTATION_PENSION'],
                          ['situation_familiale'])[0]
        enfants = _fait(f, ['ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE'], ['nombre_enfants', 'nbre_enfants_charge'])[0]
        if situation and ident is not None:
            n = _parts(enfants)
            texte = situation + ('' if n is None else ' · sans enfant' if n == 0 else f" · {_pluriel(int(n), 'enfant')}")
            ident['lignes'].insert(min(3, len(ident['lignes'])), _ligne('Situation familiale', texte))
    else:
        flux = par.get('flux')
        if flux:
            retirer(flux, {'Échéances de crédit repérées', 'Crédits par mois'})     # au centre et dans le tableau
            t = _tableau_mois(mois, (('Crédits', 'total_credit'), ('Débits', 'total_debit'),
                                     ('Échéances de crédit', 'echeances_credits'), ('Solde en fin de mois', 'solde_cloture')))
            if t:
                flux['visuel'] = t

    ln = par.get('liste_noire')
    chemins = f.get('chemins') or []
    if ln:
        retirer(ln, {'Meilleur chemin', 'Inscrit atteint'})
        c = chemins[0] if chemins else {}
        inscrit = c.get('inscrit') or {}
        if chemins and not (inscrit.get('indice') is not None and inscrit.get('indice') == f.get('indice')):
            x = _ligne('Personne inscrite la plus proche', inscrit.get('nom'), lien=_fiche_lien(inscrit.get('indice')))
            x.update(ton=TON_NIVEAU.get(c.get('niveau'), 'neutre'),
                     detail=f"à {_pluriel(c.get('longueur') or 0, 'lien')} · alerte {c.get('niveau_libelle') or c.get('niveau')}".lower()
                     .replace('alerte hors_alerte', 'hors alerte'))
            ln['lignes'].append(x)
            if len(chemins) > 1:
                ln['lignes'].append(_ligne('Chemins vers des inscrits', len(chemins), 'nombre'))
            etapes = [dict(de=(e.get('de') or {}).get('nom'),
                           lien=LIENS_CHEMIN.get(e.get('code'), e.get('code')) if e.get('type') == 'identifiant' else e.get('code'),
                           vers=(e.get('vers') or {}).get('nom'), inscrit=bool((e.get('vers') or {}).get('inscrit')),
                           fiche=_fiche_lien((e.get('vers') or {}).get('indice'))) for e in c.get('etapes') or []]
            if etapes:
                ln['visuel'] = dict(type='chemin', etapes=etapes)
    ctrl = par.get('controles')
    familles = v.get('controles') or []
    if ctrl is not None and familles:
        conformes = [x for x in familles if not x['anomalies']]
        ctrl['lignes'] = [x for x in ctrl['lignes'] if x['libelle'] in {y['famille'] for y in familles if y['anomalies']}]
        if conformes:
            n = sum(len(x['controles']) for x in conformes)
            x = _ligne('Contrôles de la v2' if not ctrl['lignes'] else 'Autres contrôles',
                       f"{n} sur {n} {'conforme' if n == 1 else 'conformes'}")
            x.update(ton='bon', detail=', '.join(y['famille'] for y in conformes))
            ctrl['lignes'].append(x)

    ordre = ORDRE_LECTURE['pm' if pm else 'pp']
    garde = [b for b in par.values() if b['lignes'] or b.get('visuel') or b['cle'] == 'demandes']
    for b in garde:
        b['zone'] = ZONES_BRANCHES.get(b['cle'], 'qui')
    garde.sort(key=lambda b: (ZONES.index(b['zone']), ordre.index(b['cle']) if b['cle'] in ordre else len(ordre)))
    return garde, a_venir
