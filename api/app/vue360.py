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
