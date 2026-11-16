#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chaines_dessin.py — chaînes du dessin du 22/10/2026, sur les vraies données :

    PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3

    PM n°1 est à 1 arête de l'inscrit, PP n°2 à 2, PM n°2 à 3, PP n°3 à 4.
    Une société associée d'une autre (participation) relie aussi deux sociétés en une arête.
    On part aussi des sociétés inscrites retrouvées au registre.

Rôles datés. Chaque arête porte le rôle de la dernière annonce qui cite la personne dans la société :
« associé 50 % (01/2023) », « ancien associé (cédé 02/2023) », « ancien gérant (remplacé 05/2024) ». Un rôle lu
seulement dans une annonce mélangée (deux annonces dans un même bloc) compte pour moitié et le dit.

Une personne du registre n'a pas d'identifiant (l'export ne porte quasiment pas de CIN). On la reconnaît ainsi :
  - dans une même société : même nom (ordre des mots indifférent), même nom écrit en latin et en arabe (mêmes
    consonnes, voyelles longues, coupures entre les mots), ou deux graphies à une lettre sœur près (اصيل / اسيل) ;
  - d'une société à l'autre : même CIN ; ou même nom + même ville du siège, si le nom figure dans 5 sociétés au plus,
    ET s'il est rare (moins de 0,15 personne attendue par hasard avec ce prénom et ce nom) ou si un indice le
    confirme : même adresse, même cabinet déposant, ou un associé ou gérant commun aux deux sociétés.

Retour vers la liste noire. Un élément du chemin également inscrit est classé :
  - « même dossier » : saisi avec l'inscrit de départ (même date, même agent, même note, 20 inscriptions au plus) ;
    le registre confirme ce que la liste noire savait déjà ;
  - « même lot » : même saisie groupée de plus de 20 inscriptions (échange APSF…) ;
  - « découverte » : aucun lien dans la liste noire entre les deux.

Chaque chaîne porte :
  - fiabilité : rapprochement inscrit ↔ registre × passages d'une société à l'autre (1 pour un CIN,
    0,8 × n^-0,5 pour un même nom + même ville, n = sociétés qui portent ce nom au Maroc) × 0,5 par rôle lu
    seulement dans une annonce mélangée ;
  - force : fiabilité × poids des rôles (gérant 0,7, associé 0,3 à 0,7 selon les parts, ancien rôle 0,3 à 0,5)
    × rareté de la taille de la société.

  python3 chaines_dessin.py --base bl_rc.sqlite --excel Chaines_liste_noire_RC.xlsx --html Carte_reseaux_liste_noire.html
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import construire_base as cb  # noqa: E402
import translitteration as tl  # noqa: E402

ROLES_FR = {'gerant': 'gérant', 'administrateur': 'administrateur', 'associe': 'associé', 'liquidateur': 'liquidateur',
            'gerant_sortant': 'ancien gérant', 'associe_sortant': 'ancien associé', 'cessionnaire': 'associé',
            'cedant': 'ancien associé', 'representant': 'représentant', 'inconnu': 'cité'}
MOTS_DEPOSANT = {'CABINET', 'FIDUCIAIRE', 'FIDUCIARE', 'COMPTA', 'COMPTABLE', 'COMPTABILITE', 'DOMICILIATION',
                 'JURIC', 'JURIDIQUE', 'AVOCAT', 'NOTAIRE', 'MAITRE'}
ADRESSE_LATIN = {'LOTISS', 'LOTISSEMENT', 'KSAR', 'DOUAR', 'COMMUNE', 'CERCLE', 'PROVINCE', 'QUARTIER', 'HAY', 'DERB',
                 'IMMEUBLE', 'IMM', 'APPT', 'ETAGE', 'ETG', 'RESIDENCE', 'BOULEVARD', 'AVENUE', 'RUE'}   # adresse lue comme un nom
COUPE_ARABE = {'جديد', 'الجديد', 'سابق', 'السابق', 'قديم', 'القديم'}
# vocabulaire juridique relevé dans les noms restés sur la carte du 27/10 (en plus de cb.STOP_NOMS)
STOP_SUPPLEMENT = cb._norm_set('''تعديل المواد باوسع بأوسع أوسع اوسع صالحيات صلاحيات الصالحيات الصلاحيات واسعة الواسعة المدى
توقيع التوقيع وبتوقيع بتوقيع عنوان المقرالاجتماعي الاجتماعي الإجتماعي ليحل محل يحل ويشهد يشهد بانه بأنه يخضع
للمحظورات المحظورات المنصوص عليها اعطوا أعطوا البراءة براءة الكاملة كاملة والنهائية النهائية والنهايية النهايية للمصفي
المصفي مصفي تبعا لقرار الجمعية العمومية العادية الغير هولندا بامستردام أمستردام امستردام هولدين هولدينغ هولدينج وشركة
للتنمية العقارية الغرض موضوع نشاط النشاط الفرع فرع تحويل نقل التصفية التصفيه فسخ إغلاق اغلاق اختتام الإغلاق الاغلاق
المصادقة مصادقة الحسابات حسابات السنة المالية الزيادة زيادة تخفيض الرفع رفع تغيير تحيين استمرار استمرارية الاستمرار
توسيع التوسيع إضافة اضافة حذف إلغاء الغاء تفويض التفويض منح بيع شراء كراء إيجار ايجار رهن الرهن الدمج الضم الانضمام
الإقالة إقالة اقالة عزل العزل الاستقالة الوفاة بالوفاة المتوفى المتوفي المرحوم المرحومة الورثة ورثة
الشركة الشركات المحدودة المسؤولية المساهمة البسيطة التضامن التوصية بالأسهم الاسهم السهم الأسهم الحصص الحصة
الموقع الممضي الممضى المسجل المسجلة المؤرخ المؤرخة بمدينة مدينة بالدار بالرباط بمراكش بطنجة بفاس بأكادير بمكناس بوجدة
قررت قرر ليصبح يصبح المالك لتمثيل تمثيل لجميع جميع حصته حصتها حصصه قيمة اداري إداري مما يمنحه السلطة الاعمال الأعمال
المتعلقة بعرض الوضعية الاقفال الإقفال النهايي المفوت المفوتة المفوتين الحسابية مدقق كمدقق كشريك كشريكة كشريكين كمتصرف
كمتصرفة مناصفة بينهما بينهم مشاركين التزاماته وتحديد تحديد عددها وعددها خالل خلال وسيتم سيتم قيمته مواكب للقانون
القالة للقالة لقبول بقبول اداريا إداريا ملجلس لمجلس المجلس احد أحد مسيري الصوتي والصوتي الحراري والحراري والختم
مسبقة تبعا بمهامه بمهامها لتصفية التصفية للتصفية بالتصفية الخاطي الخاطئ الاسم الإسم
كل وتم وبالتالي بالتالي مشارك ابراءا ابراء وابراء إبراء ذمة النطق تاما تحفظ وبدون بدون مرتبط غيرمساهم مساهم
ياذن يأذن ويصدق يصدق مالكة مالك بالتبرع التبرع بصفتهم بصفتهما مساعد مساعدة علما بتوزيع
HOLDING HOLDINGS LTD LLC INC CORP SARL SA SAS SNC STE SOCIETE COMPANY GROUP GROUPE FIDUCIAIRE CABINET NOTAIRE AVOCAT
TRIBUNAL GREFFE COMMERCE''')
PREFIXES_AR = ('ولل', 'وال', 'لل', 'و', 'ب', 'ل')     # pas ك ni ف (« كمال » n'est pas « ك + مال »), ni بال (« بالجديد » est un nom)
PONT_MAX = 5            # un nom présent dans plus de 5 sociétés ne relie jamais deux sociétés
RARE_ATTENDU = 0.15     # en dessous : nom assez rare pour que même nom + même ville suffise
DOSSIER_MAX = 20        # au-delà : saisie groupée (lot d'échange), pas un dossier
PERSONNES_MAX = 25      # société trop grande (SA, coopérative) : on ne passe pas par ses membres
SOCIETES_MAX = 15       # personne présente dans trop de sociétés (fiduciaire, liquidateur de métier) : pas de passage
PROFONDEUR = 4
CHEMINS_PAR_CIBLE = 5
SORTIES = {'cedant', 'associe_sortant', 'gerant_sortant'}


# ---- noms ------------------------------------------------------------------------------------------------------
def _mot_juridique(m):
    """Le mot, ou le mot sans son préfixe (و, ب, ل, ف, ك, لل…), est du vocabulaire juridique."""
    if m in STOP_SUPPLEMENT or m in cb.STOP_NOMS:
        return True
    for p in PREFIXES_AR:
        if m.startswith(p) and len(m) >= len(p) + 4:
            r = m[len(p):]
            if p == 'ب' and r.startswith('ال'):
                continue                            # « بالجديد », « بالقاسم », « بالحاج » : noms de famille
            if r in STOP_SUPPLEMENT or r in cb.STOP_NOMS:
                return True
            if len(p) == 1 and len(r) >= 5 and (('ال' + r) in STOP_SUPPLEMENT or ('ال' + r) in cb.STOP_NOMS):
                return True                         # « بتحويل », « لتفويت » ; mais pas « كمال », « بوفي »
    return False


def nettoyer_nom(nom, freq_tok=None):
    """Nom affichable d'une personne citée, ou None si l'entrée n'est pas un nom (listes à jour, appliquées aussi à
    une base construite plus tôt). freq_tok : fréquence des mots dans les noms, pour repérer « X وY » (deux personnes
    collées : le mot qui suit la conjonction est un prénom ou un nom courant)."""
    mots = cb.mots_nom_nettoyes(nom)
    if cb.motif_rejet_nom(mots):
        return None
    if not cb.est_arabe(nom):
        mots_lat = set(cb.latin_maj(nom).split())
        return None if mots_lat & (ADRESSE_LATIN | cb.MARQUES_PM | cb.MARQUES_SOCIETE | STOP_SUPPLEMENT) else nom
    garde = []
    for m in mots:                                  # « مسيرجديد » (nouveau gérant) collé au nom
        if m.startswith('مسير') or m in COUPE_ARABE:
            break
        if _mot_juridique(m) and not (garde and garde[-1] == 'عبد'):   # « عبد المالك » reste un prénom
            # « سكينة السقاط تبعا لتفويت » : le nom s'arrête au vocabulaire juridique
            if len(garde) < 2:
                return None                         # phrase sans nom devant (« تعديل المواد », « عنوان المقر »)
            break
        garde.append(m)
    if cb.motif_rejet_nom(garde):
        return None
    if freq_tok and len(garde) >= 4:
        for m in garde[1:]:
            if m.startswith('و') and len(m) >= 4 and freq_tok.get(m[1:], 0) >= 30:
                return None                         # « مريم جيسوس ومهدية جيسوس » : plusieurs personnes dans une entrée
    return nom if len(garde) == len(nom.split()) else ' '.join(garde)


def charger_exclusions():
    """Noms à ne jamais dessiner (exclusions_carte.json : [{"nom": …, "motif": …}]) → clés de nom."""
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exclusions_carte.json')
    if not os.path.exists(chemin):
        return {}
    with open(chemin, encoding='utf-8') as f:
        out = {}
        for e in json.load(f):
            for n in [e['nom']] + e.get('variantes', []):
                k = cle_personne(n)
                if k:
                    out[k] = e.get('motif', '')
        return out


def cle_personne(nom):
    """Nom sans ordre des mots : article retiré, graphies ramenées (ال / لا, ة / ه, prénoms usuels)."""
    toks = jetons_nom(nom)
    return ' '.join(sorted(toks)) if len(toks) >= 2 else None


def jetons_nom(nom, compose=False):
    """Mots d'un nom normalisés ; compose=True recolle « عبد » au mot suivant (prénom composé, pour la rareté)."""
    if not nom:
        return []
    toks = []
    if cb.est_arabe(nom):
        prec = None
        for m in cb.latin_maj(nom).split():
            if not cb.est_arabe(m):
                continue
            if m.startswith('ال') and len(m) > 3 and m not in cb.NON_ARTICLE_AR:
                m = m[2:]
            m = cb.ar_simple(m).replace('ا', '').replace('ء', '')
            if len(m) < 2:
                continue
            if compose and prec == 'عبد' and toks:
                toks[-1] += m
                prec = None
                continue
            toks.append(m)
            prec = m
    else:
        toks = [cb.article_colle(m) or m for m in cb.mots_nom_latin(nom)]
    return toks


def _jetons_arabes(nom):
    sortie = []
    for m in cb.latin_maj(nom).split():
        if not cb.est_arabe(m):
            continue
        feminin = m.endswith('ة')
        if m.startswith('ال') and len(m) > 3 and m not in cb.NON_ARTICLE_AR:
            m = m[2:]
        m = cb.ar_simple(m)
        if len(m) >= 2:
            sortie.append((m, feminin))
    return sortie


def _mots_proches(x, y):
    """Deux mots d'un nom : identiques ; ou mêmes lettres à des lettres sœurs près (اصيل / اسيل, ص / س) ; ou une lettre
    d'écart sur un mot long (زغلول / زغلو, جاموس / دجاموس). Sinon les mots courts doivent être identiques :
    سعيد ≠ سعد, حسن ≠ حسين, عمر ≠ عمار."""
    if x == y:
        return True
    if len(x) == len(y) and all(a == b or (a in cb._SQ_AR and cb._SQ_AR.get(a) == cb._SQ_AR.get(b))
                                for a, b in zip(x, y)):
        return True
    return min(len(x), len(y)) >= 4 and max(len(x), len(y)) >= 5 and cb._ratio(x, y) >= 0.85


def arabes_proches(a, b):
    """Deux graphies arabes du même nom : même nombre de mots, au moins un mot identique, les autres proches,
    pas d'écart masculin / féminin (سعيد / سعيدة)."""
    ta, tb = _jetons_arabes(a), _jetons_arabes(b)
    if len(ta) < 2 or len(ta) != len(tb):
        return False
    restants, identique = list(tb), False
    for x, fx in ta:
        k = max(range(len(restants)), key=lambda i: (restants[i][0] == x, cb._ratio(x, restants[i][0])))
        y, fy = restants.pop(k)
        if fx != fy or not _mots_proches(x, y):
            return False
        identique |= x == y
    return identique


def latins_proches(a, b):
    """Deux graphies latines du même nom : même nombre de mots, chacun très proche (sans SAID / SAIDA)."""
    ma, mb = cb.mots_nom_latin(a), cb.mots_nom_latin(b)
    if len(ma) < 2 or len(ma) != len(mb):
        return False
    return all(any(_mots_proches(x, y) and not cb._formes_distinctes(x, y) for y in mb) for x in ma)


class Unions:
    def __init__(self):
        self.p = {}

    def racine(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def unir(self, a, b):
        ra, rb = self.racine(a), self.racine(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def ordre_annonce(annonce_id):
    """Ordre de parution dans un même numéro (« bo:5752-512 » → (5752, 512))."""
    n = [int(x) for x in re.findall(r'\d+', annonce_id or '')[:2]]
    return tuple(n + [0, 0])[:2]


def mois(date):
    return f'{date[5:7]}/{date[:4]}' if date and len(date) >= 7 else '?'


# ---- chargement --------------------------------------------------------------------------------------------------
def charger(con):
    t0 = time.time()
    soc = {}
    for sid, den, rc, trib, ville, prem, dern, diss, nbp, rar, siege in con.execute(
            """SELECT societe_id, denomination, rc_num, tribunal_code, ville_code, premiere_publication,
                      derniere_publication, dissoute, nb_personnes, rarete_taille, siege FROM rc_societe"""):
        soc[sid] = dict(den=den, rc=rc, trib=trib, ville=ville, prem=prem, dern=dern, diss=diss, nbp=nbp or 0,
                        rar=rar or 1.0, adr=cb.cle_adresse(siege) if siege else None,
                        cle_den=cb.cle_rs(den) if den else None)
    annonce = {}
    for aid, sid, url, date, mixte, titre, typ in con.execute(
            "SELECT annonce_id, societe_id, url, date_publication, bloc_mixte, titre, type_acte FROM rc_annonce"):
        cle_titre = cb.cle_rs(titre) if titre else None
        annonce[aid] = (date or '', ordre_annonce(aid), mixte or 0, cle_titre, cb.latin_maj(typ or ''))
        s = soc.get(sid)
        if s and url and (date or '') >= s.get('url_date', ''):
            s['url'], s['url_date'] = url, date or ''
        # nom affiché qui est celui du cabinet ou du domiciliataire qui a déposé l'annonce (« CABINET X 286 BD … »)
        if (s and s['den'] and cle_titre and not s.get('deposant')
                and set(cb.latin_maj(s['den']).split()) & MOTS_DEPOSANT):
            a = s['cle_den'] or ''
            if a and (a == cle_titre or cb._ratio(a, cle_titre) >= 0.8 or a in cle_titre or cle_titre in a):
                s['deposant'] = True
    lignes, par_soc, ecartees, exclues = {}, defaultdict(list), 0, 0
    brutes = con.execute("""SELECT personne_id, societe_id, nom_complet, ecriture, cin_norm FROM rc_personne
                            WHERE type_personne = 'PP' AND nom_complet IS NOT NULL""").fetchall()
    freq_tok = Counter(m for _p, _s, nom, ecr, _c in brutes if ecr == 'arabe' for m in cb.latin_maj(nom).split())
    exclusions = charger_exclusions()
    for pid, sid, nom, ecr, cin in brutes:
        propre = nettoyer_nom(nom, freq_tok)
        if not propre:
            ecartees += 1
            continue
        cle = cle_personne(propre)
        if cle in exclusions:
            exclues += 1
            continue
        lignes[pid] = dict(sid=sid, nom=propre, ecr=ecr, cin=cin, cle=cle, exact=''.join(jetons_nom(propre)))
        par_soc[sid].append(pid)
    mentions = defaultdict(list)            # personne_id → [(date, ordre, rôle, pct, mélangée, cabinet, type d'acte)]
    for pid, aid, role, pct in con.execute('SELECT personne_id, annonce_id, role, pct FROM rc_mention'):
        if pid in lignes and aid in annonce:
            date, ordre, mixte, cle_titre, typ = annonce[aid]
            mentions[pid].append((date, ordre, role, pct or None, mixte, cle_titre, typ))
    participations = defaultdict(set)              # société associée d'une autre : arête société – société
    for sid, cible in con.execute("""SELECT p.societe_id, r.societe_id FROM rc_participation r
                                     JOIN rc_personne p ON p.personne_id = r.personne_id"""):
        if sid != cible:
            participations[sid].add(cible)
            participations[cible].add(sid)
    print(f'  registre : {len(soc)} sociétés, {len(lignes)} personnes citées, {ecartees} noms écartés, {exclues} lignes exclues (exclusions_carte.json), '
          f'{sum(len(v) for v in mentions.values())} mentions ({time.time() - t0:.0f} s)', flush=True)
    return soc, lignes, par_soc, mentions, participations


def personnes_locales(lignes, par_soc):
    """Dans chaque société : lignes qui désignent la même personne (même nom sans ordre, latin ↔ arabe, variantes)."""
    t0 = time.time()
    u = Unions()
    fusions = Counter()
    for sid, pids in par_soc.items():
        if len(pids) < 2:
            continue
        par_cle = defaultdict(list)
        for p in pids:
            if lignes[p]['cle']:
                par_cle[lignes[p]['cle']].append(p)
        for groupe in par_cle.values():
            for p in groupe[1:]:
                u.unir(groupe[0], p)
                fusions['même nom'] += 1
        lat = [p for p in pids if lignes[p]['ecr'] == 'latin']
        ar = [p for p in pids if lignes[p]['ecr'] == 'arabe']
        for a in ar:
            for b in lat:
                if u.racine(a) != u.racine(b) and cb.profils_compatibles(lignes[b]['nom'], lignes[a]['nom']):
                    u.unir(a, b)
                    fusions['latin ↔ arabe'] += 1
        for i, a in enumerate(lat):
            for b in lat[i + 1:]:
                if u.racine(a) != u.racine(b) and latins_proches(lignes[a]['nom'], lignes[b]['nom']):
                    u.unir(a, b)
                    fusions['variante latine'] += 1
        for i, a in enumerate(ar):
            for b in ar[i + 1:]:
                if u.racine(a) != u.racine(b) and arabes_proches(lignes[a]['nom'], lignes[b]['nom']):
                    u.unir(a, b)
                    fusions['variante arabe'] += 1
    locales = defaultdict(list)
    for pid in lignes:
        locales[u.racine(pid)].append(pid)
    print(f"  personnes par société : {len(lignes)} lignes → {len(locales)} personnes "
          f"({', '.join(f'{k} {v}' for k, v in fusions.items())}) ({time.time() - t0:.0f} s)", flush=True)
    return locales


# ---- rôles datés -------------------------------------------------------------------------------------------------
ROLES_ASSOCIE = {'associe', 'cessionnaire', 'cedant', 'associe_sortant'}
ROLES_GERANT = {'gerant', 'administrateur', 'gerant_sortant'}
TYPES_NOMINATION = ('CHANGEMENT DE GERANT', 'CHANGEMENT D ADMINISTRATEUR', 'NOMINATION')


def etats_roles(lignes, locales, mentions):
    """Rôle de chaque personne locale dans sa société, daté. Parts et gérance sont suivies séparément : la dernière
    annonce qui touche aux parts dit si la personne est encore associée (cession = sortie), la dernière qui touche à
    la gérance dit si elle est encore gérante (un autre gérant nommé ensuite par un changement de gérant = remplacée)."""
    t0 = time.time()
    nominations = defaultdict(list)            # société → [(date, local)] des gérants nommés par un changement de gérant
    for lid, pids in locales.items():
        sid = lignes[lid]['sid']
        for p in pids:
            for date, ordre, role, pct, mixte, _ct, typ in mentions.get(p, ()):
                if role in ('gerant', 'administrateur') and typ.startswith(TYPES_NOMINATION):
                    nominations[sid].append((date, ordre, lid))
    etats = {}
    for lid, pids in locales.items():
        ms = sorted((m for p in pids for m in mentions.get(p, ())), key=lambda m: (m[0], m[1]))
        sid = lignes[lid]['sid']
        if not ms:
            etats[lid] = dict(lib='cité', role='inconnu', poids=0.3, fiab=1.0, actuel=True, date='', cabinets=set())
            continue
        actuels, anciens = [], []              # (poids, libellé, rôle)
        # parts
        ma = [m for m in ms if m[2] in ROLES_ASSOCIE]
        if ma:
            der = ma[-1]
            meme = [m for m in ma if (m[0], m[1]) == (der[0], der[1])]
            roles = {m[2] for m in meme}
            pct = next((m[3] for m in reversed(ma) if m[2] in ('associe', 'cessionnaire') and m[3] is not None), None)
            if roles & {'cedant', 'associe_sortant'}:
                ced = max((m[3] or 0) for m in meme if m[2] in ('cedant', 'associe_sortant'))
                reste = max([m[3] or 0 for m in meme if m[2] == 'associe'] or [0])
                if reste and ced and ced < reste:
                    actuels.append((0.4, f'associé, cession partielle ({mois(der[0])})', 'associe'))
                else:
                    anciens.append((0.3, f'ancien associé (cédé {mois(der[0])})', 'associe_sortant'))
            else:
                poids = 0.3 + 0.4 * min(pct, 100) / 100 if pct is not None else 0.5
                actuels.append((poids, (f'associé {pct:g} %' if pct is not None else 'associé') + f' ({mois(der[0])})',
                                'associe'))
        # gérance
        mg = [m for m in ms if m[2] in ROLES_GERANT]
        if mg:
            der = mg[-1]
            nom_role = 'administrateur' if der[2] == 'administrateur' else 'gérant'
            if der[2] == 'gerant_sortant':
                anciens.append((0.5, f'ancien gérant (sorti {mois(der[0])})', 'gerant_sortant'))
            else:
                apres = sorted(d for d, o, autre in nominations[sid] if (d, o) > (der[0], der[1]) and autre != lid)
                if apres:
                    anciens.append((0.5, f'ancien {nom_role} (autre {nom_role} nommé {mois(apres[0])})', 'gerant_sortant'))
                else:
                    actuels.append((0.7, f'{nom_role} ({mois(der[0])})', 'gerant'))
        ml = [m for m in ms if m[2] == 'liquidateur']
        if ml:
            actuels.append((0.5, f'liquidateur ({mois(ml[-1][0])})', 'liquidateur'))
        if not (actuels or anciens):
            r = ms[-1][2]
            (anciens if r in SORTIES else actuels).append((0.3, f'{ROLES_FR.get(r, r)} ({mois(ms[-1][0])})', r))
        principal = max(actuels or anciens)
        lib = ', '.join(x[1] for x in sorted(actuels, reverse=True) + sorted(anciens, reverse=True))
        fiab = 1.0 if any(not m[4] for m in ms) else 0.5
        if fiab < 1:
            lib += ' · annonce mélangée'
        etats[lid] = dict(lib=lib, role=principal[2], poids=principal[0], fiab=fiab, actuel=bool(actuels),
                          date=ms[-1][0], cabinets={m[5] for m in ms if m[5]})
    print(f"  rôles datés : {sum(1 for e in etats.values() if not e['actuel'])} personnes sans rôle en cours "
          f"(parts cédées, gérance reprise) sur {len(etats)} ({time.time() - t0:.0f} s)", flush=True)
    return etats


# ---- même personne d'une société à l'autre -------------------------------------------------------------------------
def individus(lignes, locales, soc, etats):
    """Même CIN ; ou même nom + même ville quand le nom figure dans PONT_MAX sociétés au plus, et qu'il est rare ou
    qu'un indice confirme (même adresse, même cabinet déposant, associé ou gérant commun)."""
    t0 = time.time()
    freq = defaultdict(set)
    for pid, l in lignes.items():
        if l['cle']:
            freq[l['cle']].add(l['sid'])
    freq = {k: len(v) for k, v in freq.items()}
    # rareté attendue d'un nom : produit des fréquences de ses mots (prénom composé recollé)
    f_tok, n_loc = Counter(), len(locales)
    jetons_loc = {}
    for lid, pids in locales.items():
        toks = set()
        for p in pids:
            toks |= set(jetons_nom(lignes[p]['nom'], compose=True))
        jetons_loc[lid] = toks
        f_tok.update(toks)

    def attendu(nom):
        toks = set(jetons_nom(nom, compose=True))
        if len(toks) < 2:
            return 99.0
        x = float(n_loc)
        for t in toks:
            x *= f_tok.get(t, 1) / n_loc
        return x
    cles_soc = defaultdict(set)                    # société → noms (clés) de ses personnes
    for lid, pids in locales.items():
        for p in pids:
            if lignes[p]['cle']:
                cles_soc[lignes[p]['sid']].add(lignes[p]['cle'])
    u = Unions()
    groupes_nom, ponts_cin = defaultdict(list), defaultdict(list)
    for lid, pids in locales.items():
        u.racine(lid)
        ville = soc[lignes[lid]['sid']]['ville']
        for p in pids:
            l = lignes[p]
            if l['cin']:
                ponts_cin[l['cin']].append(lid)
            if l['cle'] and ville and freq.get(l['cle'], 0) <= PONT_MAX:
                groupes_nom[(l['cle'], ville)].append((lid, p))
    voisins = defaultdict(dict)
    stats = Counter()
    def noms_de(lid):
        return [lignes[p]['nom'] for p in locales[lid]]

    def memes_noms(a, b):
        """Deux personnes locales portent-elles le même nom (même clé, variante arabe ou latine, arabe ↔ latin) ?"""
        for x in noms_de(a):
            for y in noms_de(b):
                if cle_personne(x) == cle_personne(y):
                    return True
                xa, ya = cb.est_arabe(x), cb.est_arabe(y)
                if xa and ya and arabes_proches(x, y):
                    return True
                if not xa and not ya and latins_proches(x, y):
                    return True
                if xa != ya and cb.profils_compatibles(y if xa else x, x if xa else y):
                    return True
        return False
    for cin, lids in ponts_cin.items():
        lids = sorted(set(lids))
        for i, a in enumerate(lids):
            for b in lids[i + 1:]:
                # même CIN mais noms différents : CIN rattaché à la mauvaise personne dans l'une des annonces → pas de pont
                if not memes_noms(a, b):
                    stats['CIN partagé par des noms différents : refusé'] += 1
                    continue
                voisins[a][b] = voisins[b][a] = (1.0, f'même CIN {cin}')
                u.unir(a, b)
    for (cle, ville), membres in groupes_nom.items():
        if len({lid for lid, _ in membres}) < 2:
            continue
        n = freq[cle]
        for i, (a, pa) in enumerate(membres):
            for b, pb in membres[i + 1:]:
                if a == b or lignes[a]['sid'] == lignes[b]['sid']:
                    continue
                sa, sb = soc[lignes[a]['sid']], soc[lignes[b]['sid']]
                indices = []
                if sa['adr'] and sa['adr'] == sb['adr']:
                    indices.append('même adresse')
                cab = (etats[a]['cabinets'] & etats[b]['cabinets']) - {sa['cle_den'], sb['cle_den'], None}
                if cab:
                    indices.append('même cabinet déposant')
                communs = (cles_soc[lignes[a]['sid']] & cles_soc[lignes[b]['sid']]) - {cle}
                if communs:
                    indices.append('associé ou gérant commun')
                att = attendu(lignes[pa]['nom'])
                if att >= RARE_ATTENDU and not indices:
                    stats['refusé : nom courant sans indice'] += 1
                    continue
                stats['accepté'] += 1
                motif = f'même nom + même ville ({ville}), nom présent dans {n} sociétés au Maroc'
                if lignes[pa]['exact'] != lignes[pb]['exact']:
                    motif += ', écrit dans un autre ordre'
                motif += ' ; ' + (', '.join(indices) if indices else 'nom rare')
                poids = 0.8 * n ** -0.5
                if poids > voisins[a].get(b, (0, ''))[0]:
                    voisins[a][b] = voisins[b][a] = (poids, motif)
                u.unir(a, b)
    groupes = defaultdict(list)
    for lid in locales:
        groupes[u.racine(lid)].append(lid)
    tailles = Counter(min(len(g), 6) for g in groupes.values())
    repartition = ', '.join(('6+' if k == 6 else str(k)) + f':{v}' for k, v in sorted(tailles.items()))
    print(f'  individus : {len(locales)} personnes → {len(groupes)} individus ; présents dans 1, 2, 3… sociétés : '
          f"{repartition} ; passages {dict(stats)} ({time.time() - t0:.0f} s)", flush=True)
    individu_de = {lid: g for g, lids in groupes.items() for lid in lids}
    return groupes, individu_de, voisins, freq


def meilleur_pont(voisins, depart, arrivee, membres):
    """Passage d'une personne locale à une autre du même individu : produit des ponts sur le meilleur chemin."""
    if depart == arrivee:
        return 1.0, []
    meilleur = {depart: (1.0, [])}
    file = deque([depart])
    while file:
        x = file.popleft()
        px, mx = meilleur[x]
        for y, (p, m) in voisins.get(x, {}).items():
            if y in membres and px * p > meilleur.get(y, (0, None))[0]:
                meilleur[y] = (px * p, mx + [m])
                file.append(y)
    return meilleur.get(arrivee, (0.0, ['pas de pont']))


# ---- inscrits et drapeaux ----------------------------------------------------------------------------------------
def inscrits(con):
    ent = {}
    for r in con.execute("""SELECT entite_id, cle_entite, type_entite, nom_affiche, cin, ville_code, employeur,
                                   types_liste, types_fraude, motifs, nb_inscriptions, derniere_saisie
                            FROM bl_entite"""):
        ent[r[0]] = dict(zip(('id', 'cle', 'type', 'nom', 'cin', 'ville', 'employeur', 'listes', 'fraudes', 'motifs',
                              'nb', 'saisie'), r))
        if not ent[r[0]]['nom']:                 # inscrit saisi sans nom : désigné par son CIN ou sa clé
            ent[r[0]]['nom'] = f"(sans nom, CIN {r[4]})" if r[4] else f"(sans nom, {r[1]})"
    variantes = defaultdict(list)      # nom + prénom de l'inscrit, dans les deux ordres
    dossiers, taille = defaultdict(set), Counter()
    for eid, nom, prenom, dat, user, note in con.execute(
            'SELECT entite_id, nom, prenom, dat_sais, user_sais, note FROM bl_inscription'):
        for v in ([f'{nom} {prenom}', f'{prenom} {nom}'] if nom and prenom else [nom or prenom]):
            if v and v not in variantes[eid]:
                variantes[eid].append(v)
        k = (dat, (user or '').lower(), note)
        dossiers[eid].add(k)
        taille[k] += 1
    lien_pers, lien_soc = defaultdict(list), defaultdict(list)
    for eid, objet, oid, regle, statut, poids, nature, conf in con.execute(
            """SELECT bl_entite_id, rc_objet, rc_objet_id, regle, statut, poids, nature, confirmation
               FROM correspondance WHERE statut NOT IN ('faible', 'ecarte')"""):
        if objet == 'rc_personne':
            lien_pers[oid].append((eid, regle, statut, poids, conf))
        else:
            lien_soc[oid].append((eid, regle, statut, poids, nature))
    return ent, lien_pers, lien_soc, variantes, dossiers, taille


def nature_lien(d, depart, autres):
    """Comment la liste noire relie déjà l'inscrit de départ aux autres inscrits du chemin."""
    if not autres:
        return None
    ks, natures = d['dossiers'].get(depart, set()), []
    for e in autres:
        commun = ks & d['dossiers'].get(e, set())
        if not commun:
            natures.append('découverte')
        elif min(d['taille'][k] for k in commun) <= DOSSIER_MAX:
            natures.append('même dossier')
        else:
            natures.append('même lot')
    for n in ('découverte', 'même lot', 'même dossier'):
        if n in natures:
            return n


# ---- parcours ----------------------------------------------------------------------------------------------------
def parcourir(eid, ctx, depart_lignes=None, depart_socs=None):
    """Chemins les plus courts (≤ PROFONDEUR arêtes) depuis un inscrit.
    - personne inscrite : depart_lignes {personne_id: (règle, statut, poids, confirmation)} ; la 1re arête mène à ses
      sociétés (PM n°1 du dessin) ;
    - société inscrite : depart_socs {societe_id: (règle, statut, poids, confirmation)} ; la société du registre est le
      point de départ (distance 0), la 1re arête mène à ses dirigeants et associés.
    Renvoie {noeud: (distance, [chemins])} ; un chemin = liste d'étapes (pour une société inscrite, la 1re étape est
    le point de départ lui-même)."""
    lignes, locales, individu_de, groupes, voisins, soc, par_soc, participations, etats = (
        ctx['lignes'], ctx['locales'], ctx['individu_de'], ctx['groupes'], ctx['voisins'], ctx['soc'],
        ctx['par_soc'], ctx['participations'], ctx['etats'])
    local_de = ctx['local_de']
    dist, resultats, frontiere = {}, defaultdict(list), []
    ind_depart, cache_soi = set(), {}
    soi_ar, soi_lat = set(), set()

    def est_soi(lid):
        """L'inscrit lui-même sous une autre graphie (« جاموس » / « دجاموس ») ne revient pas en PP n°2 ou n°3."""
        if not depart_lignes:
            return False
        if lid not in cache_soi:
            r = False
            for p in locales[lid]:
                n = lignes[p]['nom']
                if lignes[p]['ecr'] == 'arabe':
                    r = (any(arabes_proches(n, x) for x in soi_ar)
                         or any(cb.profils_compatibles(v, n) for v in ctx['variantes'].get(eid, [])))
                else:
                    r = any(latins_proches(n, x) for x in soi_lat)
                if r:
                    break
            cache_soi[lid] = r
        return cache_soi[lid]

    def etape_role(lid, sid, fiab, force, **extra):
        e = etats[lid]
        return dict(sid=sid, local=lid, role=e['role'], lib=e['lib'], actuel=e['actuel'], cle_soc=cle_soc(soc[sid]),
                    fiab=fiab * e['fiab'], force=force * e['fiab'] * e['poids'] * (soc[sid]['rar'] or 1.0), **extra)

    if depart_lignes:
        locaux_directs = {}
        for pid, m in depart_lignes.items():
            if pid not in local_de:
                continue
            lid = local_de[pid]
            if lid not in locaux_directs or m[2] > locaux_directs[lid][2]:
                locaux_directs[lid] = m
        ind_depart = {individu_de[lid] for lid in locaux_directs}
        soi = [lignes[p] for ind in ind_depart for lid in groupes[ind] for p in locales[lid]]
        soi_ar = {l['nom'] for l in soi if l['ecr'] == 'arabe'}
        soi_lat = {l['nom'] for l in soi if l['ecr'] != 'arabe'} | set(ctx['variantes'].get(eid, []))
        for ind in ind_depart:
            membres = set(groupes[ind])
            for lid in groupes[ind]:
                sid = lignes[lid]['sid']
                best = None
                for d, (regle, statut, poids, conf) in locaux_directs.items():
                    if d not in membres:
                        continue
                    pp, motifs = meilleur_pont(voisins, d, lid, membres)
                    if best is None or poids * pp > best[0]:
                        best = (poids * pp, regle, statut, poids, conf, motifs, d)
                if best is None:
                    continue
                etape = etape_role(lid, sid, best[0], best[0], type='S', regle=best[1], statut=best[2],
                                   rapprochement=best[3], confirmation=best[4], pont=best[5],
                                   nom_registre=lignes[best[6]]['nom'])
                ajouter(('S', sid), [etape], 1, dist, resultats, frontiere)
        premiere = 2
    else:
        for sid, (regle, statut, poids, conf) in depart_socs.items():
            etape = dict(type='S', sid=sid, role='depart', lib='', actuel=True, local=None, fiab=poids, force=poids,
                         regle=regle, statut=statut, rapprochement=poids, confirmation=conf, pont=[],
                         nom_registre=soc[sid]['den'], cle_soc=cle_soc(soc[sid]))
            ajouter(('S', sid), [etape], 0, dist, resultats, frontiere)
        premiere = 1
    for profondeur in range(premiere, PROFONDEUR + 1):
        suivante = []
        for noeud, chemin in frontiere:
            dernier = chemin[-1]
            if noeud[0] == 'S':
                sid = noeud[1]
                if soc[sid]['nbp'] > PERSONNES_MAX:
                    continue
                for lid in sorted({local_de[p] for p in par_soc.get(sid, ()) if p in local_de}):
                    ind = individu_de[lid]
                    if ind in ind_depart or est_soi(lid):
                        continue
                    n2 = ('I', ind)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    etape = etape_role(lid, sid, dernier['fiab'], dernier['force'], type='I', ind=ind,
                                       nom=nom_affiche(lignes, locales[lid]), sid_depuis=sid)
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
                for cible in sorted(participations.get(sid, ())):
                    n2 = ('S', cible)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    etape = dict(type='S', sid=cible, role='participation', lib='associée de', actuel=True, local=None,
                                 fiab=dernier['fiab'], force=dernier['force'] * 0.5, pont=[], cle_soc=cle_soc(soc[cible]))
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
            else:
                ind = noeud[1]
                membres = set(groupes[ind])
                if len(membres) > SOCIETES_MAX:
                    continue
                for lid in groupes[ind]:
                    if lid == dernier['local']:
                        continue
                    sid = lignes[lid]['sid']
                    n2 = ('S', sid)
                    if dist.get(n2, profondeur) < profondeur:
                        continue
                    pp, motifs = meilleur_pont(voisins, dernier['local'], lid, membres)
                    etape = etape_role(lid, sid, dernier['fiab'] * pp, dernier['force'] * pp, type='S', pont=motifs)
                    ajouter(n2, chemin + [etape], profondeur, dist, resultats, suivante)
        frontiere = suivante
    sortie = {}
    for n, chemins in resultats.items():
        if dist[n] == 0:
            continue
        vus, garde = set(), []
        for ch in sorted(chemins, key=lambda c: -c[-1]['force']):
            signature = tuple((e['type'], e.get('sid') or e.get('ind'), e['lib']) for e in ch)
            if signature not in vus:
                vus.add(signature)
                garde.append(ch)
        sortie[n] = (dist[n], garde[:CHEMINS_PAR_CIBLE])
    return sortie


def cle_soc(s):
    return f"{s['rc']}@{s['trib'] or '?'}" if s['rc'] else re.sub(r'\s+', '', s['den'] or '?')


def ajouter(noeud, chemin, profondeur, dist, resultats, suivante):
    if noeud not in dist:
        dist[noeud] = profondeur
        suivante.append((noeud, chemin))
    if dist[noeud] == profondeur:
        resultats[noeud].append(chemin)


def nom_affiche(lignes, pids):
    noms = sorted({lignes[p]['nom'] for p in pids}, key=lambda n: (cb.est_arabe(n), n))
    return ' / '.join(noms[:2])


# ---- programme ---------------------------------------------------------------------------------------------------
def calculer(base):
    con = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    soc, lignes, par_soc, mentions, participations = charger(con)
    locales = personnes_locales(lignes, par_soc)
    local_de = {p: lid for lid, pids in locales.items() for p in pids}
    etats = etats_roles(lignes, locales, mentions)
    groupes, individu_de, voisins, freq = individus(lignes, locales, soc, etats)
    ent, lien_pers, lien_soc, variantes, dossiers, taille = inscrits(con)
    ctx = dict(lignes=lignes, locales=locales, local_de=local_de, individu_de=individu_de, groupes=groupes,
               voisins=voisins, soc=soc, par_soc=par_soc, participations=participations, variantes=variantes,
               etats=etats)
    inscrits_ind = defaultdict(set)
    for pid, liens in lien_pers.items():
        if pid in local_de:
            for eid, *_ in liens:
                inscrits_ind[individu_de[local_de[pid]]].add(eid)
    inscrits_soc, employeur_de = defaultdict(set), defaultdict(set)
    departs_soc = defaultdict(dict)
    for sid, liens in lien_soc.items():
        for eid, regle, statut, poids, nature in liens:
            if nature in ('emploi', 'adresse'):
                employeur_de[sid].add(eid)
                continue
            inscrits_soc[sid].add(eid)
            if ent[eid]['type'] == 'PM' and (sid not in departs_soc[eid] or poids > departs_soc[eid][sid][2]):
                departs_soc[eid][sid] = (regle, statut, poids, None)
    departs = defaultdict(dict)
    for pid, liens in lien_pers.items():
        if pid not in lignes:
            continue
        for eid, regle, statut, poids, conf in liens:
            if ent[eid]['type'] == 'PP' and (pid not in departs[eid] or poids > departs[eid][pid][2]):
                departs[eid][pid] = (regle, statut, poids, conf)
    t0 = time.time()
    res = {eid: ('PP', parcourir(eid, ctx, depart_lignes=d)) for eid, d in departs.items()}
    res.update({eid: ('PM', parcourir(eid, ctx, depart_socs=d)) for eid, d in departs_soc.items()})
    # inscrits qui retombent sur la même personne du registre (doublon probable dans la liste noire)
    meme_registre = defaultdict(set)
    par_depart = defaultdict(set)
    for eid, d in departs.items():
        for pid in d:
            if pid in local_de:
                par_depart[individu_de[local_de[pid]]].add(eid)
    for eids in par_depart.values():
        for e in eids:
            meme_registre[e] |= eids - {e}
    print(f'  départs parcourus : {len(departs)} personnes inscrites, {len(departs_soc)} sociétés inscrites '
          f'({time.time() - t0:.0f} s)', flush=True)
    return dict(con=con, tr=tl.charger(con), soc=soc, lignes=lignes, locales=locales, groupes=groupes, ent=ent, res=res,
                inscrits_ind=inscrits_ind, inscrits_soc=inscrits_soc, employeur_de=employeur_de, freq=freq,
                departs_soc=departs_soc, dossiers=dossiers, taille=taille, meme_registre=meme_registre)


def autres_inscrits_soc(d, sid, eid):
    return (d['inscrits_soc'].get(sid, set()) | d['employeur_de'].get(sid, set())) - {eid}


def drapeau_soc(d, sid, eid):
    x = []
    autres = d['inscrits_soc'].get(sid, set()) - {eid}
    if autres:
        cle = cb.cle_rs(d['soc'][sid]['den'] or '') or ''
        noms = sorted(d['ent'][e]['nom'] for e in autres)
        if all(cle and cb._ratio(cle, cb.cle_rs(n) or '') >= 0.8 for n in noms):
            x.append('société inscrite')
        else:
            x.append('société inscrite : ' + ', '.join(noms))
    emp = d['employeur_de'].get(sid, set()) - {eid}
    if emp:
        noms = sorted(d['ent'][e]['nom'] for e in emp)
        x.append('employeur déclaré de ' + ', '.join(noms[:5]) + (f' (+{len(noms) - 5})' if len(noms) > 5 else ''))
    return ' ; '.join(x)


def drapeau_ind(d, ind, eid, nom=None):
    autres = d['inscrits_ind'].get(ind, set()) - {eid}
    if not autres:
        return ''
    noms = sorted(d['ent'][e]['nom'] for e in autres)
    if nom and not cb.est_arabe(nom) and all(cle_personne(n) == cle_personne(nom) for n in noms):
        return 'inscrit'
    return 'inscrit : ' + ', '.join(noms)


ADRESSE_RS = {'RUE', 'AVENUE', 'AV', 'BD', 'BOULEVARD', 'LOTISSEMENT', 'LOTISS', 'APPT', 'APPARTEMENT', 'ETAGE', 'ETG',
              'IMM', 'IMMEUBLE', 'RESIDENCE', 'RCE', 'ANGLE', 'QUARTIER', 'HAY', 'DERB', 'ROUTE', 'RTE', 'BLOC', 'SECTEUR',
              'N°', 'KSAR', 'DOUAR'}


ADMIN_RS = re.compile(r'^(PROVINCE|PREFECTURE|WILAYA|COMMUNE|DOUAR|ARRONDISSEMENT|CERCLE DE|CAIDAT|ROYAUME DU MAROC|CAPITAL DE|DHS|AU CAPITAL|'
                      r'SOCIETE A RESPONSABILITE|SARL|STE SARL|N[°R]? ?\d)\b')


def nom_soc(s):
    if not s['den']:
        return '(dénomination non lue)'
    den = s['den']
    if ADMIN_RS.match(cb.latin_maj(den)):          # « PROVINCE GUELMIM », « CAPITAL DE 500.000 DHS … » : adresse ou en-tête lu comme nom
        return f'(dénomination non lue : « {den[:40]} »)'
    mots = den.split()
    for k, m in enumerate(mots):                    # « MITAK CONSEIL BD MOHAMED VI IMM » : l'adresse collée est retirée
        if k >= 1 and cb.latin_maj(m) in ADRESSE_RS:
            den = ' '.join(mots[:k])
            break
    return den + (' (nom du déposant de l\'annonce ?)' if s.get('deposant') else '')


def isole(nom, oui):
    """Nom arabe isolé du texte latin qui l'entoure (sinon le navigateur réordonne la ligne)."""
    return f'⁨{nom}⁩' if oui and cb.est_arabe(nom) else nom


def decrire(d, eid, typ, ch, isoler=False):
    """Étapes d'un chemin prêtes à afficher, texte compact, éléments de liste noire touchés et nature du retour."""
    etapes = ch if typ == 'PP' else ch[1:]
    e = d['ent'][eid]
    if typ == 'PP':
        texte = [f"{e['nom']} (inscrit)"]
    else:
        s0 = d['soc'][ch[0]['sid']]
        texte = [f"{isole(nom_soc(s0), isoler)} [société inscrite, RC {s0['rc'] or '?'} {s0['trib'] or ''}]".replace(' ]', ']')]
    sortie, alertes, autres = [], [], set()
    for et in etapes:
        if et['type'] == 'S':
            s = d['soc'][et['sid']]
            n = dict(type='société', nom=nom_soc(s), rc=s['rc'], trib=s['trib'], ville=s['ville'], dern=s['dern'],
                     url=s.get('url'), bl=drapeau_soc(d, et['sid'], eid))
            liens = autres_inscrits_soc(d, et['sid'], eid)
            texte.append(f"–{et['lib']}– {isole(n['nom'], isoler)}" + (f" [RC {s['rc']}]" if s['rc'] else ''))
        else:
            n = dict(type='personne', nom=et['nom'], bl=drapeau_ind(d, et['ind'], eid, et['nom']))
            liens = d['inscrits_ind'].get(et['ind'], set()) - {eid}
            texte.append(f"–{et['lib']}– {isole(et['nom'], isoler)}")
        n['nature'] = nature_lien(d, eid, liens) if n['bl'] else None
        if n['bl']:
            autres |= liens
            alertes.append(f"{isole(n['nom'], isoler)} ({n['bl']} ; {n['nature']})")
            texte[-1] += ' ⚑'
        sortie.append((et['lib'], ' → '.join(et.get('pont') or []), n))
    return sortie, ' '.join(texte), ' | '.join(alertes), nature_lien(d, eid, autres)


def lignes_chaines(d):
    """Une ligne par chemin le plus court vers une cible à 1, 2, 3 ou 4 arêtes."""
    sortie = []
    for eid, (typ, noeuds) in d['res'].items():
        e = d['ent'][eid]
        doublons = ', '.join(sorted(d['ent'][x]['nom'] for x in d['meme_registre'].get(eid, ())))
        for (_t, _i), (dist_, chemins) in noeuds.items():
            for ch in chemins:
                etapes, texte, alertes, nature = decrire(d, eid, typ, ch)
                l = dict(depart=typ, inscrit=e['nom'], cle_inscrit=e['cle'], cin_inscrit=e['cin'], listes=e['listes'],
                         motifs=e['motifs'], distance=dist_, fiabilite=round(ch[-1]['fiab'], 4),
                         niveau='certain (CIN ou RC + tribunal)' if ch[0].get('statut') in ('alerte', 'confirme') else 'probable',
                         nouveau=None if d.get('precedent') is None else
                         ('oui' if signature_chaine(typ, ch) not in d['precedent'].get(f"{typ}:{e['cle']}", set()) else 'non'),
                         force=round(ch[-1]['force'], 5), chaine=texte, alerte_liste_noire=alertes, nature=nature,
                         nb_liste_noire=alertes.count(' | ') + 1 if alertes else 0, doublons=doublons or None,
                         anciens=sum(1 for x in (ch if typ == 'PP' else ch[1:]) if not x.get('actuel', True)))
                l['rapprochement'] = f"{ch[0]['regle']} ({ch[0]['statut']}, poids {ch[0]['rapprochement']:.2f})"
                l['nom_registre'] = ch[0]['nom_registre']
                for k, (lib, pont, n) in enumerate(etapes, start=1):
                    l[f'a{k}'], l[f'a{k}_pont'] = lib, pont
                    l[f'n{k}_type'], l[f'n{k}'] = n['type'], n['nom']
                    if n['type'] == 'société':
                        l[f'n{k}_rc'] = f"{n['rc'] or '?'} {n['trib'] or ''}".strip()
                        l[f'n{k}_ville'], l[f'n{k}_derniere_annonce'], l[f'n{k}_url'] = n['ville'], n['dern'], n['url']
                    l[f'n{k}_liste_noire'] = f"{n['bl']} ({n['nature']})" if n['bl'] else None
                sortie.append(l)
    return sortie


ORDRE_NATURE = {'découverte': 0, 'même lot': 1, 'même dossier': 2, None: 3}


def ecrire_excel(d, chemin):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    lignes = lignes_chaines(d)
    wb = Workbook()
    wb.remove(wb.active)
    entete = PatternFill('solid', fgColor='14212B')
    couleurs = {'découverte': PatternFill('solid', fgColor='F8D3CF'), 'même lot': PatternFill('solid', fgColor='FDEBD3'),
                'même dossier': PatternFill('solid', fgColor='EEF1F4')}

    def feuille(titre, colonnes, rangees, note, largeurs):
        ws = wb.create_sheet(titre)
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color='4A5866')
        for j, (c, lib) in enumerate(colonnes, start=1):
            x = ws.cell(row=3, column=j, value=lib)
            x.font, x.fill = Font(bold=True, color='FFFFFF'), entete
            x.alignment = Alignment(wrap_text=True, vertical='center')
            ws.column_dimensions[get_column_letter(j)].width = largeurs.get(c, 20)
        for i, r in enumerate(rangees, start=4):
            for j, (c, _) in enumerate(colonnes, start=1):
                ws.cell(row=i, column=j, value=r.get(c))
            if r.get('nature') in couleurs:
                for j in range(1, len(colonnes) + 1):
                    ws.cell(row=i, column=j).fill = couleurs[r['nature']]
        ws.freeze_panes = 'B4'
        ws.row_dimensions[3].height = 32
        if rangees:
            ws.auto_filter.ref = f'A3:{get_column_letter(len(colonnes))}{3 + len(rangees)}'

    larg = {'inscrit': 28, 'chaine': 110, 'alerte_liste_noire': 50, 'rapprochement': 24, 'nom_registre': 26,
            'nature': 16, 'doublons': 26}
    for k in range(1, 5):
        larg.update({f'a{k}': 26, f'n{k}': 32, f'a{k}_pont': 40, f'n{k}_liste_noire': 34, f'n{k}_url': 30})
    base = [('nouveau', 'Nouveau depuis le 22/10'), ('niveau', 'Niveau du rapprochement'),
            ('inscrit', 'Inscrit (point de départ)'), ('cin_inscrit', 'CIN inscrit'), ('listes', 'Listes'),
            ('rapprochement', 'Rapprochement liste noire ↔ registre'), ('nom_registre', 'Nom au registre'),
            ('distance', 'Arêtes'), ('nature', 'Retour vers la liste noire'), ('fiabilite', 'Fiabilité'),
            ('force', 'Force'), ('anciens', 'Rôles terminés sur le chemin'),
            ('alerte_liste_noire', 'Autres éléments de la liste noire sur le chemin'), ('chaine', 'Chaîne'),
            ('doublons', 'Autres inscrits sur la même personne du registre')]

    def detail(k, dessin):
        c = []
        for i in range(1, k + 1):
            c += [(f'a{i}', f'Arête {i} (rôle daté)'), (f'a{i}_pont', f'Arête {i} : même personne d\'une société à l\'autre'),
                  (f'n{i}', f'Nœud {i} ({dessin[i]})'), (f'n{i}_type', f'Nœud {i} : type'), (f'n{i}_rc', f'Nœud {i} : RC'),
                  (f'n{i}_ville', f'Nœud {i} : ville'), (f'n{i}_derniere_annonce', f'Nœud {i} : dernière annonce'),
                  (f'n{i}_liste_noire', f'Nœud {i} : liste noire'), (f'n{i}_url', f'Nœud {i} : annonce')]
        return c

    dessin_pp = {1: 'PM n°1', 2: 'PP n°2', 3: 'PM n°2', 4: 'PP n°3'}
    dessin_pm = {1: 'personne', 2: 'société', 3: 'personne', 4: 'société'}
    tri = lambda r: (ORDRE_NATURE[r['nature']], r['niveau'] != 'certain (CIN ou RC + tribunal)', -r['fiabilite'],
                     -r['force'], r['inscrit'])
    pp = [r for r in lignes if r['depart'] == 'PP']
    pm = [r for r in lignes if r['depart'] == 'PM']
    boucles = sorted((r for r in lignes if r['alerte_liste_noire']), key=tri)
    nb = lambda l, k: sum(1 for r in l if r['distance'] == k)
    ins = lambda l, k: len({r['cle_inscrit'] for r in l if r['distance'] == k})
    nat = Counter(r['nature'] for r in boucles)
    ins_nat = lambda n: len({r['cle_inscrit'] for r in boucles if r['nature'] == n})
    ws = wb.create_sheet('Synthèse')
    texte = [
        'Réseaux liste noire × registre du commerce — chaînes du dessin du 22/10/2026',
        'PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3',
        '',
        f"Personnes inscrites retrouvées au registre (point de départ) : {len({r['cle_inscrit'] for r in pp})}",
        f"   1 arête  : {nb(pp, 1)} chemins (PM n°1), {ins(pp, 1)} inscrits",
        f"   2 arêtes : {nb(pp, 2)} chemins (PP n°2 ou société associée), {ins(pp, 2)} inscrits",
        f"   3 arêtes : {nb(pp, 3)} chemins (PM n°2), {ins(pp, 3)} inscrits",
        f"   4 arêtes : {nb(pp, 4)} chemins (PP n°3), {ins(pp, 4)} inscrits",
        f"Sociétés inscrites retrouvées au registre (point de départ) : {len({r['cle_inscrit'] for r in pm})}",
        f"   1 à 4 arêtes : {nb(pm, 1)} / {nb(pm, 2)} / {nb(pm, 3)} / {nb(pm, 4)} chemins",
        '',
        f"Chemins dont le point de départ est certain (même CIN, ou même RC + tribunal) : "
        f"{sum(1 for r in lignes if r['niveau'].startswith('certain'))} ; probables (nom + élément qui confirme) : "
        f"{sum(1 for r in lignes if r['niveau'] == 'probable')}",
        (f"Chemins nouveaux depuis la construction du 22/10 : {sum(1 for r in lignes if r['nouveau'] == 'oui')} "
         f"(colonne « Nouveau depuis le 22/10 »)") if d.get('precedent') is not None else '',
        f"Chemins qui reviennent vers un autre élément de la liste noire : {len(boucles)}",
        f"   découverte (aucun lien entre eux dans la liste noire) : {nat['découverte']} chemins, "
        f"{ins_nat('découverte')} inscrits de départ",
        f"   même lot d'échange (saisie groupée de plus de {DOSSIER_MAX} inscriptions) : {nat['même lot']} chemins, "
        f"{ins_nat('même lot')} inscrits",
        f"   même dossier (même date, même agent, même note) : {nat['même dossier']} chemins, "
        f"{ins_nat('même dossier')} inscrits — le registre confirme ce que la liste noire savait déjà",
        '',
        'Lecture',
        '- Chaque ligne est un chemin le plus court vers une société ou une personne (au plus 5 par cible).',
        '- Rôle daté : celui de la dernière annonce qui cite la personne dans la société (« ancien associé (cédé '
        '02/2023) », « ancien gérant (remplacé 05/2024) »). « annonce mélangée » : lu dans un bloc qui mêle deux '
        'annonces, compte pour moitié.',
        '- ⚑ dans la chaîne : élément aussi présent dans la liste noire (autre inscrit, société inscrite, employeur '
        'déclaré). Couleur : rouge = découverte, orange = même lot, gris = même dossier.',
        '- Rapprochement liste noire ↔ registre : nom + élément qui confirme, à valider par un analyste (pas de CIN dans '
        'l\'export).',
        '- Même personne d\'une société à l\'autre : même CIN ; ou même nom + même ville, nom présent dans 5 sociétés au '
        'plus, et nom rare ou confirmé par une même adresse, un même cabinet déposant ou un associé commun.',
        '- Fiabilité = rapprochement × passages (1 pour un CIN, 0,8 × n^-0,5 pour nom + ville) × 0,5 par rôle lu dans '
        'une annonce mélangée. Force = fiabilité × poids des rôles × taille des sociétés.',
    ]
    for i, t in enumerate(texte, start=1):
        ws.cell(row=i, column=1, value=t).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    ws.column_dimensions['A'].width = 150
    feuille('Reliés à la liste noire', [('depart', 'Départ')] + base + detail(4, dessin_pp), boucles,
            f'{len(boucles)} chemins qui touchent un autre élément de la liste noire : découvertes d\'abord (rouge), '
            'puis même lot (orange), puis même dossier (gris)', larg)
    for k, titre in ((4, 'Personnes · 4 arêtes'), (3, 'Personnes · 3 arêtes'), (2, 'Personnes · 2 arêtes'),
                     (1, 'Personnes · 1 arête')):
        rang = sorted((r for r in pp if r['distance'] == k), key=tri)
        feuille(titre, base + detail(k, dessin_pp), rang,
                f'{len(rang)} chemins au départ d\'une personne inscrite', larg)
    feuille('Sociétés inscrites', base + detail(4, dessin_pm), sorted(pm, key=lambda r: (r['distance'],) + tri(r)),
            f'{len(pm)} chemins au départ d\'une société inscrite retrouvée au registre (1 à 4 arêtes)', larg)
    wb.save(chemin)
    print(f'  Excel : {chemin} ({len(lignes)} chemins, dont {len(boucles)} reliés à la liste noire : '
          f'{dict(nat)})', flush=True)
    return lignes


def signature_chaine(typ, ch):
    """Identité d'un chemin, stable d'une construction à l'autre : nœuds (RC + tribunal, ou nom) et rôles."""
    parts = []
    for et in ch:
        if et['type'] == 'S':
            parts.append('S:' + (et.get('cle_soc') or str(et['sid'])))
        else:
            parts.append('I:' + re.sub(r'\s+', '', et['nom']))
        parts.append(et.get('role') or '')
    return '|'.join(parts)


def donnees_carte(d, precedent=None):
    """Sous-graphe de chaque inscrit (chemins les plus courts) pour la page. precedent : {id inscrit: {clés des
    chaînes}} de la construction précédente, pour marquer ce qui est nouveau."""
    sortie = []
    for eid, (typ, noeuds) in d['res'].items():
        e = d['ent'][eid]
        if not noeuds:
            continue
        n_out, a_out, vus_a, chaines = {}, [], {}, []
        doublons = sorted(d['ent'][x]['nom'] for x in d['meme_registre'].get(eid, ()))
        if typ == 'PP':
            n_out['R'] = dict(t='PP', nom=e['nom'], d=0, sous='CIN ' + e['cin'] if e['cin'] else 'inscrit', bl='')
        else:
            sids = sorted(d['departs_soc'][eid])
            s0 = d['soc'][sids[0]]
            n_out['R'] = dict(t='PM', nom=nom_soc(s0), d=0, rc=s0['rc'], trib=s0['trib'], ville=s0['ville'],
                              dern=s0['dern'], url=s0.get('url'), bl='société inscrite : ' + e['nom'])
        compte = Counter()
        for (_t, _i), (dist_, chemins) in noeuds.items():
            compte[dist_] += 1
            for ch in chemins:
                etapes, texte, alertes, nature = decrire(d, eid, typ, ch, isoler=True)
                niveau = 'certain' if ch[0].get('statut') in ('alerte', 'confirme') else 'probable'
                chaines.append(dict(texte=texte, distance=dist_, fiab=round(ch[-1]['fiab'], 4),
                                    force=round(ch[-1]['force'], 5), bl=alertes, nature=nature, niveau=niveau,
                                    cle=signature_chaine(typ, ch)))
                prec = 'R'
                bruts = ch if typ == 'PP' else ch[1:]
                if typ == 'PM' and len(d['departs_soc'][eid]) > 1 and ch[0]['sid'] != sorted(d['departs_soc'][eid])[0]:
                    s0 = d['soc'][ch[0]['sid']]
                    n_out.setdefault(f"S{ch[0]['sid']}", dict(t='PM', nom=nom_soc(s0), d=0, rc=s0['rc'], trib=s0['trib'],
                                                              ville=s0['ville'], dern=s0['dern'], url=s0.get('url'),
                                                              bl='société inscrite : ' + e['nom']))
                    prec = f"S{ch[0]['sid']}"
                for k, ((lib, pont, n), et) in enumerate(zip(etapes, bruts), start=1):
                    if et['type'] == 'S':
                        cle = f"S{et['sid']}"
                        n_out.setdefault(cle, dict(t='PM', nom=n['nom'], d=k, rc=n['rc'], trib=n['trib'], ville=n['ville'],
                                                   dern=n['dern'], url=n['url'], bl=n['bl'], nature=n['nature'],
                                                   diss=d['soc'][et['sid']]['diss']))
                    else:
                        cle = f"I{et['ind']}"
                        n_out.setdefault(cle, dict(t='PP', nom=n['nom'], d=k, sous=lib, bl=n['bl'], nature=n['nature']))
                    style = '' if et.get('actuel', True) else 'ancien'
                    if typ == 'PP' and k == 1:
                        style = (style + (' certain' if et.get('statut') in ('alerte', 'confirme') else ' rap')).strip()
                        pont = (f"rapprochement {et['regle']} ({et['statut']}, poids {et['rapprochement']:.2f}) avec "
                                f"« {et['nom_registre']} »" + (f' ; puis {pont}' if pont else ''))
                    elif pont:
                        style = (style + ' pont').strip()
                    ka = (prec, cle)
                    if ka not in vus_a or et['force'] > vus_a[ka]['force']:
                        court = re.sub(r'\s*\([^)]*\)', '', lib).replace(' · annonce mélangée', ' (mélangée)')
                        a = dict(a=prec, b=cle, lib=lib, court=court, pont=pont, fiab=round(et['fiab'], 4),
                                 force=round(et['force'], 5), style=style)
                        if ka in vus_a:
                            a_out[a_out.index(vus_a[ka])] = a
                        else:
                            a_out.append(a)
                        vus_a[ka] = a
                    prec = cle
        for n in n_out.values():
            lat = ' / '.join(x for x in (d['tr'].nom(v) or '' for v in (n['nom'] or '').split(' / ')) if x)
            if lat:
                n['lat'] = lat
        chaines.sort(key=lambda c: (ORDRE_NATURE[c['nature']], c['distance'], -c['force']))
        natures = {c['nature'] for c in chaines if c['nature']}
        nature = min(natures, key=lambda n: ORDRE_NATURE[n]) if natures else None
        anciennes = precedent.get(f"{typ}:{e['cle']}") if precedent is not None else None
        for c in chaines:
            c['nouveau'] = anciennes is None or c['cle'] not in anciennes
        certain = any(c['niveau'] == 'certain' for c in chaines)
        sortie.append(dict(id=f"{typ}:{e['cle']}", nom=e['nom'], type=typ, cin=e['cin'], listes=e['listes'],
                           motifs=e['motifs'], compte={str(k): compte[k] for k in (1, 2, 3, 4)},
                           alerte=bool(natures), nature=nature, doublons=doublons, noeuds=n_out, aretes=a_out,
                           chaines=chaines, certain=certain,
                           nouveau=('inscrit' if anciennes is None else
                                    ('chaines' if any(c['nouveau'] for c in chaines) else None))
                           if precedent is not None else None))
    sortie.sort(key=lambda x: (x['type'], ORDRE_NATURE[x['nature']], -x['compte']['4'], -x['compte']['3'], x['nom']))
    return sortie


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default='bl_rc.sqlite')
    ap.add_argument('--excel', default='Chaines_liste_noire_RC.xlsx')
    ap.add_argument('--html', default='Carte_reseaux_liste_noire.html')
    ap.add_argument('--json', help='Écrire aussi les données de la carte en JSON')
    ap.add_argument('--precedent', help='JSON de la carte précédente : marque les inscrits et les chaînes nouveaux')
    a = ap.parse_args()
    t0 = time.time()
    d = calculer(a.base)
    precedent = None
    if a.precedent:
        with open(a.precedent, encoding='utf-8') as f:
            precedent = {x['id']: {c.get('cle') for c in x['chaines']} for x in json.load(f)}
        d['precedent'] = precedent
    ecrire_excel(d, a.excel)
    carte = donnees_carte(d, precedent)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(carte, f, ensure_ascii=False)
    if a.html:
        modele = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carte_chaines_modele.html')
        with open(modele, encoding='utf-8') as f:
            page = f.read()
        donnees = json.dumps(carte, ensure_ascii=False).replace('</', '<\\/')
        with open(a.html, 'w', encoding='utf-8') as f:
            f.write(page.replace('/*__DONNEES__*/[]', donnees))
        print(f'  Carte : {a.html}', flush=True)
    print(f'Terminé en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
