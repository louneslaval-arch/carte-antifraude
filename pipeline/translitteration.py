#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translitteration.py — écriture latine des noms arabes de la base (personnes citées, dénominations), apprise sur la
base elle-même, puis règles de secours.

  python3 translitteration.py --base bl_rc.sqlite            # remplit rc_personne.nom_latin, rc_societe.denomination_latin
  python3 translitteration.py --base bl_rc.sqlite --essai "محمد الادريسي"

Apprentissage : dans une même société, une personne citée une fois en latin et une fois en arabe (profils compatibles,
cf. construire_base.profils_compatibles) donne, mot à mot, des couples « mot arabe → mot latin » (محمد → MOHAMED,
الادريسي → EL IDRISSI, عبد الله → ABDELLAH). Le mot latin le plus fréquent pour chaque mot arabe est retenu
(table ref_translitteration). Un mot jamais vu en latin est translittéré par règles (convention marocaine :
ش → CH, خ → KH, غ → GH, ق → K, و → OU, ع → A), voyelle A insérée entre deux consonnes.

Ce n'est pas une traduction : « شركة » devient CHARIKA, pas « société ».
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import construire_base as cb  # noqa: E402

LETTRES = {'ا': 'A', 'أ': 'A', 'إ': 'I', 'آ': 'A', 'ب': 'B', 'پ': 'P', 'ت': 'T', 'ث': 'T', 'ج': 'J', 'ح': 'H', 'خ': 'KH',
           'د': 'D', 'ذ': 'D', 'ر': 'R', 'ز': 'Z', 'س': 'S', 'ش': 'CH', 'ص': 'S', 'ض': 'D', 'ط': 'T', 'ظ': 'D', 'ع': 'A',
           'غ': 'GH', 'ف': 'F', 'ڤ': 'V', 'ق': 'K', 'ك': 'K', 'ک': 'K', 'ڭ': 'G', 'گ': 'G', 'ل': 'L', 'م': 'M', 'ن': 'N',
           'ه': 'H', 'و': 'OU', 'ي': 'I', 'ى': 'A', 'ة': 'A', 'ء': '', 'ئ': 'I', 'ؤ': 'OU', 'ٱ': 'A'}
VOYELLES_AR = set('اأإآىةوي')
VOYELLES_LAT = set('AEIOUY')
COMPOSES = {'عبد', 'ابو', 'أبو', 'ابن', 'بن', 'ايت', 'آيت', 'أيت', 'اولاد', 'أولاد', 'ولد', 'سيدي', 'مولاي', 'لالة', 'ام', 'أم'}
PARTICULES_LAT = {'EL', 'AL', 'BEN', 'BEL', 'BOU', 'BENT', 'AIT', 'OULD', 'IBN', 'ABD', 'ABDEL', 'ABOU', 'ABU', 'ES', 'ER',
                  'ET', 'ED', 'EZ', 'ECH', 'EN', 'SIDI', 'MOULAY', 'LALLA', 'OUM', 'OULAD'}
MIN_OCC = 2            # un couple vu une seule fois n'est retenu que s'il n'a pas de concurrent


# ---- règles de secours ---------------------------------------------------------------------------------------------
def mot_par_regles(m):
    """Un mot arabe → latin par règles. « محمد » → MAHAMAD (le dictionnaire donne MOHAMED), « الادريسي » → EL IDRISSI."""
    m = cb.latin_maj(m)
    if not m or not cb.ARABE_RE.search(m):
        return m
    prefixe = ''
    if m.startswith('ال') and len(m) > 3 and m not in cb.NON_ARTICLE_AR:
        prefixe, m = 'EL ', m[2:]
    elif m.startswith('لل') and len(m) > 3:
        prefixe, m = 'LIL', m[2:]
    elif m.startswith('بن') and len(m) > 4:
        prefixe, m = 'BEN', m[2:]
    segs = []
    for i, ch in enumerate(m):
        debut = i == 0
        if ch == 'و':
            lat = 'W' if debut else 'OU'
        elif ch == 'ي':
            lat = 'Y' if debut else 'I'
        else:
            lat = LETTRES.get(ch, '')
        if lat:
            segs.append(lat)
    # voyelle d'appui A : après la première consonne si une consonne suit (M‑R → MA‑R), puis après deux consonnes
    # de suite si une troisième suit (MARZ‑K → MARZA‑K) : محمد → MAHMAD, مرزوق → MARZOUK, بلفقيه → BALFAKIH
    res, run = '', 0
    for i, seg in enumerate(segs):
        res += seg
        voy = seg[-1] in VOYELLES_LAT
        run = 0 if voy else run + 1
        suiv = segs[i + 1] if i + 1 < len(segs) else None
        if suiv and not voy and suiv[0] not in VOYELLES_LAT and (i == 0 or run >= 2):
            res += 'A'
            run = 0
    res = re.sub(r'A{2,}', 'A', res)
    return prefixe + res


# ---- apprentissage sur la base --------------------------------------------------------------------------------------
def _unites_ar(nom):
    """Mots arabes d'un nom, « عبد » / « ابو » / « ايت »… recollés au mot suivant."""
    mots = [m for m in cb.latin_maj(nom).split() if cb.ARABE_RE.search(m)]
    out, i = [], 0
    while i < len(mots):
        if mots[i] in COMPOSES and i + 1 < len(mots):
            out.append(mots[i] + ' ' + mots[i + 1])
            i += 2
        else:
            out.append(mots[i])
            i += 1
    return out


def _unites_lat(nom):
    """Mots latins d'un nom, particules recollées (« EL IDRISSI », « BEN ALI », « ABD EL LAH » → une unité)."""
    mots = [m for m in cb.latin_maj(nom).split() if not cb.ARABE_RE.search(m)]
    out, i = [], 0
    while i < len(mots):
        bloc = [mots[i]]
        while mots[i] in PARTICULES_LAT and i + 1 < len(mots):
            i += 1
            bloc.append(mots[i])
        out.append(' '.join(bloc))
        i += 1
    return out


def _sq(x):
    return cb.squelette(x) or ''


def apparier(nom_lat, nom_ar):
    """Couples (unité arabe, unité latine) d'un même nom écrit dans les deux écritures, par squelette consonantique."""
    ua, ul = _unites_ar(nom_ar), _unites_lat(nom_lat)
    if not ua or not ul:
        return []
    sa, sl = [_sq(x) for x in ua], [_sq(x) for x in ul]
    couples = []
    if len(ua) == len(ul):
        direct = sum(1 for a, b in zip(sa, sl) if a and a == b)
        inverse = sum(1 for a, b in zip(sa, reversed(sl)) if a and a == b)
        if direct >= inverse and direct >= max(1, len(ua) - 1):
            return list(zip(ua, ul))
        if inverse > direct and inverse >= max(1, len(ua) - 1):
            return list(zip(ua, reversed(ul)))
    # tailles différentes ou ordre mêlé : appariement par squelette unique
    restants = list(enumerate(sl))
    for a, s in zip(ua, sa):
        if not s:
            continue
        cand = [(j, t) for j, t in restants if t == s]
        if len(cand) == 1:
            j, _ = cand[0]
            couples.append((a, ul[j]))
            restants = [(k, t) for k, t in restants if k != j]
    return couples


def apprendre(con):
    """Dictionnaire mot arabe → mot latin appris sur les personnes citées dans les deux écritures d'une même société,
    puis sur les rapprochements liste noire (latin) ↔ registre (arabe) retenus."""
    t0 = time.time()
    comptes = defaultdict(Counter)
    par_soc = defaultdict(lambda: ([], []))
    for sid, nom, ecr in con.execute("SELECT societe_id, nom_complet, ecriture FROM rc_personne WHERE type_personne = 'PP'"):
        if nom:
            par_soc[sid][0 if ecr == 'latin' else 1].append(nom)
    paires = 0
    for sid, (lats, ars) in par_soc.items():
        if not lats or not ars or len(lats) * len(ars) > 400:
            continue
        for la in lats:
            for ar in ars:
                if cb.profils_compatibles(la, ar):
                    for a, b in apparier(la, ar):
                        comptes[a][b] += 1
                    paires += 1
    # liste noire (latin) ↔ registre (arabe) : rapprochements retenus par le nom
    for nom_bl, prenom_bl, nom_rc in con.execute("""
        SELECT i.nom, i.prenom, p.nom_complet FROM correspondance c
        JOIN bl_inscription i ON i.entite_id = c.bl_entite_id
        JOIN rc_personne p ON p.personne_id = c.rc_objet_id
        WHERE c.rc_objet = 'rc_personne' AND c.statut IN ('alerte', 'confirme', 'homonymie', 'a_verifier')
          AND p.ecriture = 'arabe' AND i.nom IS NOT NULL"""):
        la = f'{nom_bl or ""} {prenom_bl or ""}'.strip()
        if la and cb.profils_compatibles(la, nom_rc):
            for a, b in apparier(la, nom_rc):
                comptes[a][b] += 1
            paires += 1
    dico = {}
    for a, c in comptes.items():
        (b, n), = c.most_common(1)
        if n >= MIN_OCC or len(c) == 1:
            dico[a] = (b, n, sum(c.values()))
    print(f'  translittération : {paires} noms vus dans les deux écritures → {len(dico)} mots arabes connus '
          f'({time.time() - t0:.0f} s)', flush=True)
    return dico


# ---- application ---------------------------------------------------------------------------------------------------
class Translitterateur:
    def __init__(self, dico=None):
        self.dico = dico or {}
        self.cache = {}

    def mot(self, u):
        if u in self.cache:
            return self.cache[u]
        if u in self.dico:
            r = self.dico[u][0]
        elif ' ' in u:                                  # « عبد الكريم » inconnu tel quel : chaque moitié
            r = ' '.join(self.mot(x) for x in u.split())
            r = r.replace('ABD EL ', 'ABDEL').replace('ABD ', 'ABD')
        else:
            r = mot_par_regles(u)
        self.cache[u] = r
        return r

    def nom(self, nom):
        """Nom complet : les mots arabes sont translittérés, les autres gardés tels quels ; None si rien n'est arabe."""
        if not nom or not cb.ARABE_RE.search(nom):
            return None
        out = []
        for u in _unites_ar(nom):
            out.append(self.mot(u))
        return ' '.join(out) if out else None


def charger(con):
    """Translittérateur à partir de ref_translitteration (sinon dictionnaire vide : règles seules)."""
    try:
        rows = con.execute('SELECT mot_arabe, mot_latin, nb, total FROM ref_translitteration').fetchall()
    except sqlite3.OperationalError:
        rows = []
    return Translitterateur({a: (b, n, t) for a, b, n, t in rows})


def appliquer(con):
    """Apprend, écrit ref_translitteration, remplit rc_personne.nom_latin et rc_societe.denomination_latin."""
    dico = apprendre(con)
    con.execute('DROP TABLE IF EXISTS ref_translitteration')
    con.execute("""CREATE TABLE ref_translitteration (
        mot_arabe TEXT PRIMARY KEY,   -- mot (ou prénom composé) tel qu'il apparaît dans les annonces
        mot_latin TEXT NOT NULL,      -- écriture latine la plus fréquente pour ce mot dans la base
        nb INTEGER NOT NULL,          -- fois où cette écriture a été vue
        total INTEGER NOT NULL)       -- fois où le mot a été vu dans les deux écritures""")
    con.executemany('INSERT INTO ref_translitteration VALUES (?, ?, ?, ?)', [(a, b, n, t) for a, (b, n, t) in dico.items()])
    tr = Translitterateur(dico)
    for table, col, src in (('rc_personne', 'nom_latin', 'nom_complet'), ('rc_societe', 'denomination_latin', 'denomination')):
        cols = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        if col not in cols:
            con.execute(f'ALTER TABLE {table} ADD COLUMN {col} TEXT')
        cle = 'personne_id' if table == 'rc_personne' else 'societe_id'
        maj = []
        for pk, texte in con.execute(f'SELECT {cle}, {src} FROM {table} WHERE {src} IS NOT NULL'):
            lat = tr.nom(texte)
            if lat:
                maj.append((lat, pk))
        con.executemany(f'UPDATE {table} SET {col} = ? WHERE {cle} = ?', maj)
        print(f'  {table}.{col} : {len(maj)} valeurs', flush=True)
    for nom, val, desc in (('translitteration_mots', len(dico), 'mots arabes dont l’écriture latine est apprise sur la base'),
                           ('translitteration_date', 0, 'date de la translittération : ' + time.strftime('%Y-%m-%d'))):
        try:
            con.execute('INSERT OR REPLACE INTO parametre (nom, valeur, texte, description) VALUES (?, ?, ?, ?)',
                        (nom, val, None, desc))
        except sqlite3.OperationalError:
            pass
    con.commit()
    return tr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default='bl_rc.sqlite')
    ap.add_argument('--essai', nargs='*', help='Noms à translittérer avec le dictionnaire de la base, sans rien écrire')
    a = ap.parse_args()
    if a.essai:
        con = sqlite3.connect(f'file:{a.base}?mode=ro', uri=True)
        tr = charger(con)
        for n in a.essai:
            print(f'{n}  →  {tr.nom(n)}')
        return
    con = sqlite3.connect(a.base)
    appliquer(con)


if __name__ == '__main__':
    main()
