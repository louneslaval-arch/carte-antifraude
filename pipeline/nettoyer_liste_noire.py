#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nettoyer_liste_noire.py — liste noire EQDOM nettoyée, à partir du fichier brut.

  python3 nettoyer_liste_noire.py --entree Liste_noir_03_08_2026.xlsx --sortie Liste_noire_nettoyee.xlsx

Ce que le programme corrige seul (même logique que construire_base.py, donc même résultat dans la base) :
  - lignes strictement identiques (hors n° de séquence et utilisateur) : la première est gardée, les autres écartées ;
  - RC saisi dans la colonne CIN, identifiant fiscal saisi dans la colonne RC, CIN ou ICE : rangés dans leur colonne ;
  - CIN normalisé (espaces, casse, zéros de tête) ; « PP » / « PM » saisi dans la colonne tribunal : vidé ;
  - type de client vide ou contredit par les données : déduit ; codes tribunal et codes ville EQDOM traduits ;
  - date de naissance égale à une date de saisie ou à 01/01/1900 : vidée ; dates et montants au format normal ;
  - valeurs corrompues (séquences de terminal) vidées ; noms, prénoms, raisons sociales mis en forme ;
  - regroupement des inscriptions d'une même personne ou société sous un identifiant d'entité.

Ce qu'il ne peut pas corriger est listé dans la feuille « À traiter par EQDOM » (sans nom, CIN masqué, CIN porté par
deux noms, RC ou tribunal absent, code ville ou motif inconnu…) et les codes sans référentiel dans « Référentiels ».

La première feuille, « Inscriptions nettoyées », garde les colonnes du fichier EQDOM : elle peut remplacer le fichier
brut en entrée de construire_base.py (--bl Liste_noire_nettoyee.xlsx).
"""
import argparse
import difflib
import os
import re
import sys
import time
from collections import Counter, defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import construire_base as cb  # noqa: E402

POLICE = 'Arial'
MOTIFS_CONNUS = {'Domiciliat': 'Domiciliation', 'SUSPICION': 'Suspicion'}
COLONNES_SORTIE = cb.COLONNES_BL + ['identifiant_fiscal', 'ville_code_eqdom', 'id_entite', 'corrections', 'a_traiter']
LIBELLES = {'num_seq': 'N° séquence', 'cin': 'CIN', 'regist_com': 'RC', 'ice': 'ICE', 'regist_tribune': 'Tribunal',
            'cli_phy_mor': 'Type (PP/PM)', 'no_drpp': 'N° DRPP', 'nom_ras': 'Raison sociale', 't_cli': 'Type client',
            'date_naiss': 'Date de naissance', 'adresse': 'Adresse', 'ville': 'Ville', 'lib_emp': 'Employeur déclaré',
            'interm': 'Intermédiaire', 'part': 'Part', 'motif': 'Motif', 'motif2': 'Motif 2', 'type_liste': 'Type de liste',
            'type_fraude': 'Type de fraude', 'orig_liste': 'Origine', 'orig_agence': 'Agence', 'mt_exposition': 'Exposition',
            'note': 'Note', 'dat_sais': 'Date de saisie', 'user_sais': 'Saisi par', 'user_maj': 'Mis à jour par',
            'nom': 'Nom', 'prenom': 'Prénom', 'identifiant_fiscal': 'Identifiant fiscal', 'ville_code_eqdom': 'Code ville EQDOM',
            'id_entite': 'Entité', 'corrections': 'Corrections automatiques', 'a_traiter': 'À traiter par EQDOM'}


def forme(texte):
    """Nom, prénom, raison sociale : espaces multiples et bords retirés, majuscules pour l'écriture latine."""
    if not texte:
        return None
    t = ' '.join(str(texte).split())
    return t if cb.est_arabe(t) else t.upper()


def nettoyer(chemin_entree):
    """Lit le fichier brut, renvoie (lignes nettoyées, corrections, doublons, a_traiter, entites, referentiels, synthese)."""
    t0 = time.time()
    brutes = cb.lire_table(chemin_entree)
    inscriptions, originaux, anomalies_lecture = [], {}, []
    for brute in brutes:
        r, n, anos = cb.lire_ligne_bl(brute)
        originaux[n] = dict(r)
        anomalies_lecture += anos
        i, anos = cb.normaliser_inscription(r, n)
        anomalies_lecture += anos
        inscriptions.append(i)
    nb_lues = len(inscriptions)
    inscriptions, anos_doublons = cb.ecarter_doublons(inscriptions)
    groupes = cb.regrouper_inscriptions(inscriptions)
    id_entite = {}
    for eid, (cle, ins) in enumerate(sorted(groupes.items()), start=1):
        for i in ins:
            id_entite[i['num_seq']] = eid
    anomalies_par_ligne = defaultdict(list)
    for n, champ, valeur, anomalie, traitement in anomalies_lecture:
        anomalies_par_ligne[n].append((champ, valeur, anomalie, traitement))

    # CIN porté par plusieurs noms différents
    noms_par_cin = defaultdict(set)
    for i in inscriptions:
        if i['type_entite'] == 'PP' and i['cin_statut'] in ('valide', 'lettre_finale'):
            k = cb.cle_nom(i['nom'], i['prenom'])
            if k:
                noms_par_cin[i['cin_norm']].add(' '.join(x for x in (forme(i['nom']), forme(i['prenom'])) if x))
    # même CIN, plusieurs graphies : simple variante d'orthographe (même squelette) ou vrais noms différents
    cin_multi, cin_variantes = {}, {}
    for c, ns in noms_par_cin.items():
        if len(ns) < 2:
            continue
        sq = [{cb.squelette(m) for m in cb.latin_maj(n).split() if cb.squelette(m)} for n in ns]
        # « QIBOUSI ZIGHOUTAB » et « QIBOUSI ZIGHOUTAB NABIL » : même personne, un prénom en plus
        proche = lambda x, y: difflib.SequenceMatcher(None, ''.join(sorted(x)), ''.join(sorted(y))).ratio() >= 0.8
        if all(sq[0] <= s or s <= sq[0] or len(sq[0] & s) >= 2 or proche(sq[0], s) for s in sq[1:]):
            cin_variantes[c] = sorted(ns)
        else:
            cin_multi[c] = sorted(ns)

    # personne sans CIN valide dont le nom est celui d'un inscrit qui a un CIN : le CIN est probablement à reprendre
    cin_par_nom = defaultdict(set)
    for i in inscriptions:
        if i['type_entite'] == 'PP' and i['cin_statut'] in ('valide', 'lettre_finale'):
            k = cb.cle_nom(i['nom'], i['prenom'])
            if k:
                cin_par_nom[k].add(i['cin_norm'])

    corrections, a_traiter, lignes = [], [], []
    compte_corr, compte_trait = Counter(), Counter()

    def corr(n, champ, avant, apres, action):
        corrections.append((n, champ, avant, apres, action))
        compte_corr[action] += 1

    def trait(n, i, probleme, detail, attendu):
        a_traiter.append((n, id_entite[n], i['type_entite'], i['nom_affiche'], probleme, detail, attendu))
        compte_trait[probleme] += 1

    for i in inscriptions:
        n = i['num_seq']
        o = originaux[n]
        s = {c: o.get(c) for c in cb.COLONNES_BL}
        s['num_seq'] = n
        s['id_entite'] = id_entite[n]
        s['identifiant_fiscal'] = i['if_num']
        s['ville_code_eqdom'] = o['ville'] if o['ville'] and o['ville'].isdigit() else None
        t = i['type_entite']

        # valeurs corrompues et anomalies relevées à la lecture
        for champ, valeur, anomalie, traitement in anomalies_par_ligne.get(n, []):
            if traitement == 'vidée':
                s[champ] = None
                corr(n, champ, valeur, None, 'valeur corrompue vidée')
        # CIN
        if i['cin_statut'] in ('valide', 'lettre_finale'):
            s['cin'] = i['cin_norm']
            if (o['cin'] or '').strip() != i['cin_norm']:
                corr(n, 'cin', o['cin'], i['cin_norm'], 'CIN normalisé')
            if i['cin_statut'] == 'lettre_finale':
                trait(n, i, 'CIN avec une lettre finale', o['cin'], 'confirmer le CIN exact')
        elif i['cin_statut'] == 'rc_dans_cin':
            s['cin'] = None
            corr(n, 'cin', o['cin'], None, 'RC saisi dans la colonne CIN : déplacé en RC')
        elif i['cin_statut'] == 'identifiant_fiscal':
            s['cin'] = None
            corr(n, 'cin', o['cin'], None, 'identifiant fiscal saisi dans la colonne CIN : déplacé en IF')
        elif i['cin_statut'] == 'masque':
            s['cin'] = None
            corr(n, 'cin', o['cin'], None, 'CIN masqué vidé')
            if t == 'PP':
                trait(n, i, 'CIN masqué', o['cin'], 'retrouver le CIN dans le dossier')
        elif i['cin_statut'] in ('chiffres_seuls', 'non_standard'):
            s['cin'] = (o['cin'] or '').strip() or None
            if t == 'PP':
                trait(n, i, 'CIN au format non standard', o['cin'], 'corriger le CIN')
        elif t == 'PP':
            k = cb.cle_nom(i['nom'], i['prenom'])
            if k and cin_par_nom.get(k):
                trait(n, i, 'personne sans CIN, même nom qu\'un inscrit avec CIN', ', '.join(sorted(cin_par_nom[k])),
                      'vérifier s\'il s\'agit de la même personne et reprendre le CIN')
            else:
                trait(n, i, 'personne sans CIN', None, 'retrouver le CIN dans le dossier ou auprès de la source (' + (o['orig_liste'] or 'origine non renseignée') + ')')
        if t == 'PP' and i['cin_statut'] in ('valide', 'lettre_finale') and i['cin_norm'] in cin_multi:
            trait(n, i, 'CIN porté par des noms différents', ' ; '.join(cin_multi[i['cin_norm']]), 'faute de frappe sur le CIN ou usurpation : à trancher')
        elif t == 'PP' and i['cin_statut'] in ('valide', 'lettre_finale') and i['cin_norm'] in cin_variantes:
            trait(n, i, 'même CIN, orthographes différentes du nom', ' ; '.join(cin_variantes[i['cin_norm']]), 'retenir une seule orthographe')
        # RC, IF, ICE
        if i['rc_num']:
            s['regist_com'] = i['rc_num']
            if (o['regist_com'] or '').strip() != i['rc_num']:
                corr(n, 'regist_com', o['regist_com'], i['rc_num'], 'RC normalisé' if o['regist_com'] else 'RC repris de la colonne CIN')
        else:
            if i['rc_statut'] in ('identifiant_fiscal', 'masque'):
                s['regist_com'] = None
                corr(n, 'regist_com', o['regist_com'], None, 'identifiant fiscal saisi dans la colonne RC : déplacé en IF' if i['rc_statut'] == 'identifiant_fiscal' else 'RC masqué vidé')
            if t == 'PM':
                trait(n, i, 'société sans RC', o['regist_com'], 'retrouver le RC dans le dossier (extrait du registre)')
        if i['if_num'] and not (o['regist_com'] and i['if_num'] in o['regist_com']) and not (o['cin'] and i['if_num'] in o['cin']):
            corr(n, 'ice', o['ice'], None, 'identifiant fiscal saisi dans la colonne ICE : déplacé en IF')
        s['ice'] = i['ice_norm']
        if o['ice'] and not i['ice_norm'] and not (o['ice'] and cb.latin_maj(o['ice']).startswith('IF')):
            trait(n, i, 'ICE invalide', o['ice'], 'un ICE a 15 chiffres')
        # tribunal
        if i['tribunal_code']:
            s['regist_tribune'] = i['tribunal_code']
            if (o['regist_tribune'] or '').strip().upper() != i['tribunal_code']:
                corr(n, 'regist_tribune', o['regist_tribune'], i['tribunal_code'],
                     'tribunal déduit du RC' if i['tribunal_statut'] == 'deduit_du_rc' else 'code tribunal traduit')
        else:
            s['regist_tribune'] = None
            if o['regist_tribune']:
                corr(n, 'regist_tribune', o['regist_tribune'], None,
                     'type de client saisi dans la colonne tribunal : vidé' if i['tribunal_statut'] == 'type_client_saisi_dans_tribunal' else 'valeur sans rapport avec un tribunal : vidée')
            if t == 'PM':
                trait(n, i, 'société sans tribunal', o['regist_tribune'], 'tribunal du RC (dossier ou OMPIC)')
        # type de client
        s['cli_phy_mor'] = t
        if (o['cli_phy_mor'] or '').upper() != t:
            corr(n, 'cli_phy_mor', o['cli_phy_mor'], t, 'type de client déduit' if not o['cli_phy_mor'] else 'type de client corrigé (données contraires)')
        # noms
        for champ in ('nom', 'prenom', 'nom_ras', 'lib_emp'):
            v = forme(o[champ])
            s[champ] = v
            if v and v != o[champ] and ' '.join(o[champ].split()) != v:
                corr(n, champ, o[champ], v, 'mise en forme (casse, espaces)')
        if t == 'PP':
            if not s['nom'] and not s['prenom']:
                trait(n, i, 'personne sans nom ni prénom', o['orig_liste'], 'nom et prénom par le CIN (historique client) ou auprès de la source')
            elif not s['nom'] and s['prenom'] and len(s['prenom'].split()) >= 2:
                trait(n, i, 'nom et prénom dans la seule colonne prénom', s['prenom'], 'séparer nom et prénom')
            if any(ch.isdigit() for ch in (s['nom'] or '') + (s['prenom'] or '')):
                trait(n, i, 'nom ou prénom avec des chiffres', f"{s['nom']} / {s['prenom']}", 'corriger')
        else:
            if not s['nom_ras']:
                if s['nom'] or s['prenom']:
                    s['nom_ras'] = ' '.join(x for x in (s['nom'], s['prenom']) if x)
                    corr(n, 'nom_ras', None, s['nom_ras'], 'raison sociale reprise des colonnes nom / prénom')
                else:
                    trait(n, i, 'société sans raison sociale', None, 'raison sociale du RC')
        # date de naissance
        if t == 'PP':
            if i['date_naiss_valide']:
                s['date_naiss'] = i['date_naiss_valide']
                if (o['date_naiss'] or '')[:10] != i['date_naiss_valide']:
                    corr(n, 'date_naiss', o['date_naiss'], i['date_naiss_valide'], 'date au format AAAA-MM-JJ')
            else:
                if o['date_naiss']:
                    corr(n, 'date_naiss', o['date_naiss'], None, 'date de naissance impossible (date de saisie ou 1900) : vidée')
                s['date_naiss'] = None
        else:                                               # société : la date saisie est conservée (souvent une date de création)
            dn = cb.date_iso(o['date_naiss'])
            s['date_naiss'] = dn or o['date_naiss']
            if dn and (o['date_naiss'] or '')[:10] != dn:
                corr(n, 'date_naiss', o['date_naiss'], dn, 'date au format AAAA-MM-JJ')
        # ville
        if i['ville_code'] and i['ville_origine'] in ('code_deduit', 'texte'):
            s['ville'] = i['ville_code']
            if (o['ville'] or '').strip().upper() != i['ville_code']:
                corr(n, 'ville', o['ville'], i['ville_code'], 'code ville EQDOM traduit' if i['ville_origine'] == 'code_deduit' else 'ville normalisée')
        elif i['ville_code'] and i['ville_origine'] == 'adresse':
            s['ville'] = i['ville_code']
            corr(n, 'ville', o['ville'], i['ville_code'], 'ville lue dans l\'adresse')
        else:
            s['ville'] = (o['ville'] or '').strip() or None
            if s['ville'] and s['ville'].isdigit():
                trait(n, i, 'code ville inconnu', s['ville'], 'référentiel des codes ville')
            elif s['ville']:
                trait(n, i, 'ville non reconnue', s['ville'], 'orthographe ou référentiel')
        s['adresse'] = ' '.join(o['adresse'].split()) if o['adresse'] else None
        # libellés et dates
        s['type_liste'] = i['type_liste_norm'] or o['type_liste']
        if o['type_liste'] and i['type_liste_norm'] and o['type_liste'].strip() != i['type_liste_norm']:
            corr(n, 'type_liste', o['type_liste'], i['type_liste_norm'], 'type de liste normalisé')
        s['type_fraude'] = i['type_fraude_norm'] or o['type_fraude']
        for champ in ('motif', 'motif2'):
            v = (o[champ] or '').strip()
            s[champ] = None if v in ('', 'NULL') else MOTIFS_CONNUS.get(v, v)
        if i['dat_sais'] and re.match(r'\d{4}-\d{2}-\d{2}$', i['dat_sais'] or ''):
            s['dat_sais'] = i['dat_sais']
            if (o['dat_sais'] or '')[:10] != i['dat_sais']:
                corr(n, 'dat_sais', o['dat_sais'], i['dat_sais'], 'date au format AAAA-MM-JJ')
        else:
            s['dat_sais'] = o['dat_sais']
        s['mt_exposition'] = i['mt_exposition']
        s['note'] = ' '.join(o['note'].split()) if o['note'] else None
        for champ in ('orig_liste', 'orig_agence', 'user_sais', 'user_maj', 't_cli', 'interm', 'part', 'no_drpp'):
            s[champ] = (o[champ] or '').strip() or None
        lignes.append(s)

    # seconde passe de doublons, sur les valeurs nettoyées (« INDESIRABLE RISQ » et « INDESIRABLE RISQUE » sont devenus égaux)
    vues, gardees = {}, []
    for s in sorted(lignes, key=lambda x: x['num_seq']):
        cle = tuple(' '.join(cb.latin_maj(str(s.get(c)) if s.get(c) is not None else '').split()) for c in cb.COLONNES_DOUBLON)
        if cle in vues and any(s.get(c) for c in ('cin', 'regist_com', 'nom', 'prenom', 'nom_ras', 'ice')):
            anos_doublons.append((vues[cle], 'num_seq', str(s['num_seq']), f"doublon exact après nettoyage : ligne n° {s['num_seq']} écartée", 'écartée'))
            continue
        vues[cle] = s['num_seq']
        gardees.append(s)
    lignes = gardees
    ecartees = {int(v) for _n, _c, v, _a, _t in anos_doublons}
    corrections = [c for c in corrections if c[0] not in ecartees]
    a_traiter = [t for t in a_traiter if t[0] not in ecartees]
    compte_corr.clear(); compte_corr.update(Counter(c[4] for c in corrections))
    compte_trait.clear(); compte_trait.update(Counter(t[4] for t in a_traiter))

    # colonnes de synthèse par ligne
    corr_par_ligne, trait_par_ligne = defaultdict(list), defaultdict(list)
    for n, champ, avant, apres, action in corrections:
        corr_par_ligne[n].append(action)
    for n, eid, t, nom, probleme, detail, attendu in a_traiter:
        trait_par_ligne[n].append(probleme)
    for s in lignes:
        s['corrections'] = ' ; '.join(sorted(set(corr_par_ligne[s['num_seq']]))) or None
        s['a_traiter'] = ' ; '.join(sorted(set(trait_par_ligne[s['num_seq']]))) or None

    # entités
    par_entite = defaultdict(list)
    for s in lignes:
        par_entite[s['id_entite']].append(s)
    entites = []
    for eid, ins in sorted(par_entite.items()):
        t = ins[0]['cli_phy_mor']
        noms = Counter((' '.join(x for x in (i['nom'], i['prenom']) if x) if t == 'PP' else i['nom_ras']) for i in ins)
        noms.pop(None, None); noms.pop('', None)
        dates = sorted(i['dat_sais'] for i in ins if i['dat_sais'] and re.match(r'\d{4}-', i['dat_sais']))
        entites.append(dict(
            id_entite=eid, type=t, nom=noms.most_common(1)[0][0] if noms else None,
            cin=next((i['cin'] for i in ins if i['cin']), None) if t == 'PP' else None,
            rc=next((i['regist_com'] for i in ins if i['regist_com']), None),
            tribunal=next((i['regist_tribune'] for i in ins if i['regist_tribune']), None),
            identifiant_fiscal=next((i['identifiant_fiscal'] for i in ins if i['identifiant_fiscal']), None),
            ice=next((i['ice'] for i in ins if i['ice']), None),
            date_naissance=next((i['date_naiss'] for i in ins if i['date_naiss']), None),
            ville=next((i['ville'] for i in ins if i['ville']), None),
            nb_inscriptions=len(ins), premiere_saisie=dates[0] if dates else None, derniere_saisie=dates[-1] if dates else None,
            listes=' ; '.join(sorted({i['type_liste'] for i in ins if i['type_liste']})),
            origines=' ; '.join(sorted({i['orig_liste'] for i in ins if i['orig_liste']})),
            motifs=' ; '.join(sorted({x for i in ins for x in (i['motif'], i['motif2']) if x})),
            a_traiter=' ; '.join(sorted({p for i in ins for p in trait_par_ligne[i['num_seq']]})) or None,
            num_seqs=', '.join(str(i['num_seq']) for i in ins)))

    # référentiels à compléter
    ref = {}
    codes_ville = Counter(o['ville'].strip() for o in originaux.values() if o['ville'] and o['ville'].strip().isdigit())
    ref['Codes ville EQDOM'] = [(c, nb, cb.VILLE_CODES_EQDOM[c][0] if c in cb.VILLE_CODES_EQDOM else None,
                                cb.VILLE_CODES_EQDOM[c][1] if c in cb.VILLE_CODES_EQDOM else 'à fournir')
                               for c, nb in codes_ville.most_common()]
    codes_motif = Counter(v for o in originaux.values() for v in ((o['motif'] or '').strip(), (o['motif2'] or '').strip()) if v and v != 'NULL')
    ref['Codes motif'] = [(c, nb, MOTIFS_CONNUS.get(c), 'libellé à fournir' if not MOTIFS_CONNUS.get(c) else '') for c, nb in codes_motif.most_common()]
    codes_trib = Counter((o['regist_tribune'] or '').strip() for o in originaux.values() if (o['regist_tribune'] or '').strip())
    ref['Codes tribunal EQDOM'] = [(c, nb, cb.tribunal_code(c)[0], cb.tribunal_code(c)[1]) for c, nb in codes_trib.most_common()]
    ref['Origines et agences'] = [(f"origine : {c or '(vide)'}", nb, None, '') for c, nb in Counter((o['orig_liste'] or '').strip() for o in originaux.values()).most_common()] + \
                                 [(f"agence : {c}", nb, None, 'libellé à fournir') for c, nb in Counter((o['orig_agence'] or '').strip() for o in originaux.values() if (o['orig_agence'] or '').strip()).most_common()]
    ref['Types de liste'] = [(c or '(vide)', nb, cb.norme_type_liste(c), '') for c, nb in Counter((o['type_liste'] or '').strip() for o in originaux.values()).most_common()]

    # synthèse
    pp = [s for s in lignes if s['cli_phy_mor'] == 'PP']
    pm = [s for s in lignes if s['cli_phy_mor'] == 'PM']
    e_pp = [e for e in entites if e['type'] == 'PP']
    e_pm = [e for e in entites if e['type'] == 'PM']
    synthese = [
        ('Lignes lues dans le fichier EQDOM', nb_lues),
        ('Doublons exacts écartés', len(anos_doublons)),
        ('Inscriptions gardées', len(lignes)),
        ('… personnes physiques', len(pp)), ('… sociétés', len(pm)),
        ('Entités distinctes', len(entites)), ('… personnes', len(e_pp)), ('… sociétés', len(e_pm)),
        ('Corrections automatiques', sum(compte_corr.values())),
        ('Points à traiter par EQDOM', len(a_traiter)),
        ('Personnes avec CIN valide', sum(1 for e in e_pp if e['cin'])),
        ('Personnes avec nom ou prénom', sum(1 for e in e_pp if e['nom'])),
        ('Personnes avec date de naissance valide', sum(1 for e in e_pp if e['date_naissance'])),
        ('Personnes avec ville', sum(1 for e in e_pp if e['ville'])),
        ('Sociétés avec RC', sum(1 for e in e_pm if e['rc'])),
        ('Sociétés avec RC et tribunal', sum(1 for e in e_pm if e['rc'] and e['tribunal'])),
        ('Sociétés avec raison sociale', sum(1 for e in e_pm if e['nom'])),
        ('Sociétés avec ICE', sum(1 for e in e_pm if e['ice'])),
    ]
    doublons = [(int(valeur), n, 'ligne identique sur toutes les colonnes (hors n° de séquence et utilisateur)') for n, champ, valeur, anomalie, traitement in anos_doublons]
    print(f'  {nb_lues} lignes lues, {len(anos_doublons)} doublons écartés, {len(lignes)} gardées, {len(entites)} entités, '
          f'{sum(compte_corr.values())} corrections, {len(a_traiter)} points à traiter ({time.time() - t0:.0f} s)', flush=True)
    return lignes, corrections, doublons, a_traiter, entites, ref, synthese, compte_corr, compte_trait


# ---- classeur ---------------------------------------------------------------------------------------------------
ENTETE = PatternFill('solid', fgColor='1F3864')
BANDE = PatternFill('solid', fgColor='D9E1F2')
JAUNE = PatternFill('solid', fgColor='FFF2CC')
ROUGE = PatternFill('solid', fgColor='F8CBAD')
fin = Side(style='thin', color='BFBFBF')
BORD = Border(left=fin, right=fin, top=fin, bottom=fin)


def feuille(wb, titre, entetes, lignes, largeurs=None, gel='A2', filtre=True):
    ws = wb.create_sheet(titre)
    for j, t in enumerate(entetes, 1):
        c = ws.cell(row=1, column=j, value=t)
        c.font = Font(name=POLICE, bold=True, color='FFFFFF'); c.fill = ENTETE; c.border = BORD
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, ligne in enumerate(lignes, 2):
        for j, v in enumerate(ligne, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=POLICE, size=10)
    for j in range(1, len(entetes) + 1):
        ws.column_dimensions[get_column_letter(j)].width = (largeurs or {}).get(j, 16)
    ws.freeze_panes = gel
    if filtre and lignes:
        ws.auto_filter.ref = f'A1:{get_column_letter(len(entetes))}{len(lignes) + 1}'
    return ws


def ecrire_classeur(chemin, lignes, corrections, doublons, a_traiter, entites, ref, synthese, compte_corr, compte_trait, source):
    wb = Workbook()
    wb.remove(wb.active)
    # 1. inscriptions nettoyées : première feuille, colonnes EQDOM, lisible par construire_base.py
    ws = feuille(wb, 'Inscriptions nettoyées', list(COLONNES_SORTIE),      # noms techniques : lisibles par construire_base.py
                 [[s[c] for c in COLONNES_SORTIE] for s in lignes],
                 largeurs={1: 10, 2: 12, 3: 10, 4: 16, 5: 13, 6: 7, 8: 30, 10: 12, 11: 34, 12: 14, 13: 24, 16: 10, 17: 10,
                           18: 20, 19: 18, 20: 9, 23: 40, 24: 12, 27: 22, 28: 22, 29: 14, 30: 8, 31: 8, 32: 60, 33: 50})
    col_corr, col_trait = COLONNES_SORTIE.index('corrections') + 1, COLONNES_SORTIE.index('a_traiter') + 1
    for i, s in enumerate(lignes, 2):
        if s['corrections']:
            ws.cell(row=i, column=col_corr).fill = JAUNE
        if s['a_traiter']:
            ws.cell(row=i, column=col_trait).fill = ROUGE
    # 2. synthèse
    ws = wb.create_sheet('Synthèse', 0)
    ws['A1'] = 'Liste noire EQDOM nettoyée'; ws['A1'].font = Font(name=POLICE, bold=True, size=13, color='1F3864')
    ws['A2'] = f'Fichier source : {os.path.basename(source)} · nettoyage du {time.strftime("%d/%m/%Y")} · nettoyer_liste_noire.py'
    ws['A2'].font = Font(name=POLICE, italic=True, size=9, color='595959')
    r = 4
    for lib, val in synthese:
        ws.cell(row=r, column=1, value=lib).font = Font(name=POLICE, bold=not lib.startswith('…'))
        c = ws.cell(row=r, column=2, value=val); c.font = Font(name=POLICE); c.number_format = '# ##0'
        r += 1
    r += 1
    ws.cell(row=r, column=1, value='Corrections automatiques, par type').font = Font(name=POLICE, bold=True, color='1F3864'); r += 1
    for action, nb in compte_corr.most_common():
        ws.cell(row=r, column=1, value=action).font = Font(name=POLICE)
        c = ws.cell(row=r, column=2, value=nb); c.font = Font(name=POLICE); c.number_format = '# ##0'; r += 1
    r += 1
    ws.cell(row=r, column=1, value='Points à traiter par EQDOM, par type').font = Font(name=POLICE, bold=True, color='1F3864'); r += 1
    for probleme, nb in compte_trait.most_common():
        ws.cell(row=r, column=1, value=probleme).font = Font(name=POLICE)
        c = ws.cell(row=r, column=2, value=nb); c.font = Font(name=POLICE); c.number_format = '# ##0'; r += 1
    r += 1
    ws.cell(row=r, column=1, value='Colonnes de la feuille « Inscriptions nettoyées »').font = Font(name=POLICE, bold=True, color='1F3864'); r += 1
    for c in COLONNES_SORTIE:
        ws.cell(row=r, column=1, value=c).font = Font(name=POLICE, size=10)
        ws.cell(row=r, column=2, value=LIBELLES[c]).font = Font(name=POLICE, size=10); r += 1
    r += 1
    ws.cell(row=r, column=1, value='Feuilles : « Inscriptions nettoyées » remplace le fichier brut en entrée de la base (colonnes EQDOM + entité, IF, code ville, corrections, à traiter) ; '
            '« Corrections » détaille chaque valeur changée ; « Doublons écartés » ; « Entités » = une ligne par personne ou société avec l\'historique des inscriptions ; '
            '« À traiter par EQDOM » = ce que le programme ne peut pas corriger ; « Référentiels » = codes sans libellé.').font = Font(name=POLICE, size=9, color='595959')
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 3, end_column=4)
    ws.column_dimensions['A'].width = 58; ws.column_dimensions['B'].width = 12
    # 3. corrections
    feuille(wb, 'Corrections', ['N° séquence', 'Champ', 'Valeur d\'origine', 'Valeur corrigée', 'Action'],
            sorted(corrections), largeurs={1: 12, 2: 14, 3: 30, 4: 30, 5: 60})
    # 4. doublons
    feuille(wb, 'Doublons écartés', ['N° séquence écarté', 'Doublon de la ligne n°', 'Motif'], doublons, largeurs={1: 18, 2: 20, 3: 70})
    # 5. entités
    champs_e = ['id_entite', 'type', 'nom', 'cin', 'rc', 'tribunal', 'identifiant_fiscal', 'ice', 'date_naissance', 'ville',
                'nb_inscriptions', 'premiere_saisie', 'derniere_saisie', 'listes', 'origines', 'motifs', 'a_traiter', 'num_seqs']
    lib_e = ['Entité', 'Type', 'Nom ou raison sociale', 'CIN', 'RC', 'Tribunal', 'Identifiant fiscal', 'ICE', 'Date de naissance', 'Ville',
             'Inscriptions', 'Première saisie', 'Dernière saisie', 'Listes', 'Origines', 'Motifs', 'À traiter', 'N° de séquence']
    feuille(wb, 'Entités', lib_e, [[e[c] for c in champs_e] for e in entites],
            largeurs={1: 8, 2: 6, 3: 34, 4: 12, 5: 10, 6: 14, 7: 12, 8: 16, 9: 13, 10: 14, 11: 11, 12: 12, 13: 12, 14: 24, 15: 14, 16: 18, 17: 40, 18: 24})
    # 6. à traiter
    feuille(wb, 'À traiter par EQDOM', ['N° séquence', 'Entité', 'Type', 'Nom ou raison sociale', 'Problème', 'Détail', 'Ce qu\'il faut'],
            sorted(a_traiter, key=lambda x: (x[4], x[0])), largeurs={1: 12, 2: 8, 3: 6, 4: 34, 5: 34, 6: 34, 7: 50})
    # 7. référentiels
    ws = wb.create_sheet('Référentiels')
    r = 1
    for titre, lignes_ref in ref.items():
        ws.cell(row=r, column=1, value=titre).font = Font(name=POLICE, bold=True, color='1F3864'); r += 1
        for j, t in enumerate(['Code ou valeur', 'Nombre de lignes', 'Traduction connue', 'Commentaire'], 1):
            c = ws.cell(row=r, column=j, value=t); c.font = Font(name=POLICE, bold=True, color='FFFFFF'); c.fill = ENTETE; c.border = BORD
        r += 1
        for ligne in lignes_ref:
            for j, v in enumerate(ligne, 1):
                ws.cell(row=r, column=j, value=v).font = Font(name=POLICE, size=10)
            r += 1
        r += 1
    ws.column_dimensions['A'].width = 34; ws.column_dimensions['B'].width = 16; ws.column_dimensions['C'].width = 22; ws.column_dimensions['D'].width = 50
    wb.save(chemin)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--entree', required=True, help='fichier brut EQDOM (.xlsx ou .csv)')
    ap.add_argument('--sortie', default='Liste_noire_nettoyee.xlsx')
    a = ap.parse_args()
    res = nettoyer(a.entree)
    ecrire_classeur(a.sortie, *res, source=a.entree)
    print(f'  Classeur : {a.sortie}')


if __name__ == '__main__':
    main()
