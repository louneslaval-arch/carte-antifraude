#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
construire_base.py — base SQLite « liste noire × registre du commerce »
SEVEN · réseaux de fraude EQDOM · version du 21/10/2026

Entrées :
  • la liste noire EQDOM (Excel ou CSV, 28 colonnes d'origine) ;
  • l'export des annonces légales collectées par Kamal (facultatif) :
      - deux fichiers à plat : annonces + personnes citées (CSV, Excel, Parquet ou JSON) ;
      - ou un seul fichier JSON / JSONL d'annonces avec les personnes imbriquées.
Sorties : la base SQLite (tables, clés de comparaison, correspondances R01 à R09,
graphe pondéré et chemins de rebond), et un bilan à l'écran.

Exemples :
  python3 construire_base.py --liste-noire Liste_noir_03_08_2026.xlsx --base bl_rc.sqlite
  python3 construire_base.py --liste-noire Liste_noir_03_08_2026.xlsx \\
          --rc-annonces rc_annonces.csv --rc-personnes rc_personnes.csv --base bl_rc.sqlite
  python3 construire_base.py --liste-noire Liste_noir_03_08_2026.xlsx --rc-json annonces.jsonl --base bl_rc.sqlite
  python3 construire_base.py --base bl_rc.sqlite --regles-seulement

Dépendances : Python 3.8+ ; pandas et openpyxl pour lire un Excel ; pyarrow pour un Parquet.
"""
import argparse
import csv
import difflib
import functools
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

ICI = os.path.dirname(os.path.abspath(__file__))
VERSION = '2026-10-21'
DATE_REFERENCE_LISTE = '2026-08-03'

# =============================================================================
# 1. Référentiels
# =============================================================================
# (ville canonique, libellé, nom arabe, autres graphies latines)
VILLES = [
    ('CASABLANCA', 'Casablanca', 'الدار البيضاء', ['CASA', 'DAR EL BEIDA', 'DAR BEIDA']),
    ('RABAT', 'Rabat', 'الرباط', []),
    ('TANGER', 'Tanger', 'طنجة', ['TANGIER', 'TANGIERS']),
    ('MARRAKECH', 'Marrakech', 'مراكش', ['MARRAKESH', 'MARRAKCH']),
    ('AGADIR', 'Agadir', 'أكادير', []),
    ('FES', 'Fès', 'فاس', ['FEZ']),
    ('MEKNES', 'Meknès', 'مكناس', []),
    ('OUJDA', 'Oujda', 'وجدة', []),
    ('KENITRA', 'Kénitra', 'القنيطرة', []),
    ('LAAYOUNE', 'Laâyoune', 'العيون', ['LAAYOUN', 'LAYOUNE', 'EL AYOUN', 'EL AIOUN']),
    ('BERRECHID', 'Berrechid', 'برشيد', ['BERRCHID']),
    ('KHOURIBGA', 'Khouribga', 'خريبكة', []),
    ('TEMARA', 'Témara', 'تمارة', []),
    ('SKHIRAT', 'Skhirat', 'الصخيرات', []),
    ('SAFI', 'Safi', 'آسفي', []),
    ('TETOUAN', 'Tétouan', 'تطوان', ['TETOUANE']),
    ('BERKANE', 'Berkane', 'بركان', []),
    ('OUED ZEM', 'Oued Zem', 'وادي زم', ['OUEDZEM']),
    ('GUELMIM', 'Guelmim', 'كلميم', ['GOULMIM']),
    ('CHEFCHAOUEN', 'Chefchaouen', 'شفشاون', ['CHAOUEN']),
    ('SALE', 'Salé', 'سلا', []),
    ('BENI MELLAL', 'Béni Mellal', 'بني ملال', ['BENIMELLAL']),
    ('SEFROU', 'Sefrou', 'صفرو', []),
    ('DAKHLA', 'Dakhla', 'الداخلة', []),
    ('BEN GUERIR', 'Ben Guerir', 'ابن جرير', ['BENGUERIR', 'BENGRIR']),
    ('NADOR', 'Nador', 'الناظور', []),
    ('EL JADIDA', 'El Jadida', 'الجديدة', ['ELJADIDA', 'JADIDA']),
    ('SETTAT', 'Settat', 'سطات', []),
    ('MOHAMMEDIA', 'Mohammedia', 'المحمدية', ['MOHAMMADIA', 'MOHAMEDIA']),
    ('LARACHE', 'Larache', 'العرائش', []),
    ('ESSAOUIRA', 'Essaouira', 'الصويرة', []),
    ('TAZA', 'Taza', 'تازة', []),
    ('KHEMISSET', 'Khémisset', 'الخميسات', []),
    ('ERRACHIDIA', 'Errachidia', 'الرشيدية', ['ER RACHIDIA']),
    ('OUARZAZATE', 'Ouarzazate', 'ورزازات', []),
    ('TAROUDANT', 'Taroudant', 'تارودانت', []),
    ('TIZNIT', 'Tiznit', 'تيزنيت', []),
    ('INEZGANE', 'Inezgane', 'إنزكان', ['INZEGANE', 'INZGANE']),
    ('BENSLIMANE', 'Benslimane', 'بنسليمان', ['BEN SLIMANE']),
    ('SIDI KACEM', 'Sidi Kacem', 'سيدي قاسم', []),
    ('SIDI SLIMANE', 'Sidi Slimane', 'سيدي سليمان', []),
    ('SIDI BENNOUR', 'Sidi Bennour', 'سيدي بنور', []),
    ('AL HOCEIMA', 'Al Hoceïma', 'الحسيمة', ['HOCEIMA', 'EL HOCEIMA', 'ALHOCEIMA']),
    ('KHENIFRA', 'Khénifra', 'خنيفرة', []),
    ('TAOURIRT', 'Taourirt', 'تاوريرت', []),
    ('KSAR EL KEBIR', 'Ksar El Kébir', 'القصر الكبير', ['KSAR KEBIR']),
    ('SOUK EL ARBAA', 'Souk El Arbaâ', 'سوق الأربعاء', ['SOUK LARBAA', 'SOUK ARBAA']),
    ('FQUIH BEN SALAH', 'Fquih Ben Salah', 'الفقيه بن صالح', ['FKIH BEN SALAH']),
    ('EL KELAA DES SRAGHNA', 'El Kelâa des Sraghna', 'قلعة السراغنة', ['KELAA DES SRAGHNA', 'KELAAT SRAGHNA']),
    ('YOUSSOUFIA', 'Youssoufia', 'اليوسفية', []),
    ('AZILAL', 'Azilal', 'أزيلال', []),
    ('OUEZZANE', 'Ouezzane', 'وزان', []),
    ('MIDELT', 'Midelt', 'ميدلت', []),
    ('TAN TAN', 'Tan-Tan', 'طانطان', ['TANTAN']),
    ('SMARA', 'Es-Semara', 'السمارة', ['ES SEMARA', 'SEMARA']),
    ('IFRANE', 'Ifrane', 'إفران', []),
    ('AZEMMOUR', 'Azemmour', 'أزمور', []),
    ('HAD SOUALEM', 'Had Soualem', 'حد السوالم', ['SOUALEM']),
    ('BOUSKOURA', 'Bouskoura', 'بوسكورة', []),
    ('ASSILAH', 'Assilah', 'أصيلة', ['ASILAH']),
    ('FNIDEQ', 'Fnideq', 'الفنيدق', ['FNIDEK']),
    ('MARTIL', 'Martil', 'مرتيل', []),
    ('ZAGORA', 'Zagora', 'زاكورة', []),
    ('TINGHIR', 'Tinghir', 'تنغير', []),
    ('GUERCIF', 'Guercif', 'جرسيف', []),
    ('JERADA', 'Jerada', 'جرادة', []),
    ('FIGUIG', 'Figuig', 'فجيج', []),
    ('DRIOUCH', 'Driouch', 'الدريوش', []),
    ('SIDI IFNI', 'Sidi Ifni', 'سيدي إفني', []),
    ('BOUJDOUR', 'Boujdour', 'بوجدور', []),
    # villes présentes dans l'export de Kamal (tribunal ou ville du siège)
    ('TAOUNATE', 'Taounate', 'تاونات', []),
    ('AZROU', 'Azrou', 'أزرو', []),
    ('EL HAJEB', 'El Hajeb', 'الحاجب', ['ELHAJEB']),
    ('BOUARFA', 'Bouarfa', 'بوعرفة', []),
    ('BOUZNIKA', 'Bouznika', 'بوزنيقة', []),
    ('MDIQ', "M'diq", 'المضيق', ['M DIQ']),
    ('AIN HARROUDA', 'Aïn Harrouda', 'عين حرودة', []),
    ('DAR BOUAZZA', 'Dar Bouazza', 'دار بوعزة', []),
    ('NOUACEUR', 'Nouaceur', 'النواصر', []),
    ('MEDIOUNA', 'Médiouna', 'مديونة', []),
    ('TAMESNA', 'Tamesna', 'تامسنا', []),
    ('HARHOURA', 'Harhoura', 'الهرهورة', []),
    ('AHFIR', 'Ahfir', 'أحفير', []),
    ('AIT MELLOUL', 'Aït Melloul', 'أيت ملول', []),
    ('TIFLET', 'Tiflet', 'تيفلت', []),
    ('MECHRA BEL KSIRI', 'Mechra Bel Ksiri', 'مشرع بلقصيري', ['MACHRAA BEL KSSIRI', 'MACHRAA BELKSIRI', 'BELKSIRI', 'BEL KSIRI']),
    ('KASBA TADLA', 'Kasba Tadla', 'قصبة تادلة', ['KASBAT TADLA']),
    ('MISSOUR', 'Missour', 'ميسور', []),
    ('BEN AHMED', 'Ben Ahmed', 'ابن أحمد', []),
    ('TATA', 'Tata', 'طاطا', []),
    ('IMINTANOUT', 'Imintanout', 'إمنتانوت', ['IMINTANOUTE']),
    ('SOUK SEBT OULAD NEMMA', 'Souk Sebt Oulad Nemma', 'سوق السبت أولاد النمة', ['SOUK SEBT OULED NEMMA', 'SOUK SEBT OLD NEMMA']),
    ('BIOUGRA', 'Biougra', 'بيوكرى', []),
    ('CHICHAOUA', 'Chichaoua', 'شيشاوة', []),
]
# graphies supplémentaires de villes déjà connues (vues dans l'export de Kamal)
for _code, _extra in (('DAKHLA', ['OUED EDDAHAB', 'OUED DAHABE', 'OUED ED DAHAB']), ('LAAYOUNE', ['LA YOUNE']),
                      ('ASSILAH', ['ASILAH']), ('OUEZZANE', ['OUAZZANE', 'OEZZANE']), ('KHOURIBGA', ['KHOURTIBGA']),
                      ('EL KELAA DES SRAGHNA', ['KALAA DES SRAGHNA', 'ELKELAA SRAGHNAS', 'KELAA SRAGHNA']),
                      ('BERRECHID', ['BERCHID', 'BARRECHID', 'BERRECHIDE']), ('LARACHE', ['LAARACHE'])):
    for _v in VILLES:
        if _v[0] == _code:
            _v[3].extend(_extra)

# Codes numériques de la colonne « ville » de la liste noire : référentiel EQDOM non fourni.
# Seuls les codes dont les adresses désignent sans ambiguïté une ville sont repris.
VILLE_CODES_EQDOM = {
    '1': ('RABAT', 'déduit des adresses : Agdal, quartier Hassan'),
    '2': ('CASABLANCA', 'déduit des adresses : Maârif, Oulfa, Aïn Sebaâ, Anfa, Sidi Bernoussi'),
    '3': ('TANGER', 'déduit des adresses : Beni Makada, Souani, Branes'),
    '4': ('MARRAKECH', 'déduit des adresses : Sidi Abbad, Bab Doukala, Arset, Tasseltante'),
    '6': ('FES', 'déduit des adresses : Merja Oued Fès, Zouagha, Narjis'),
    '14': ('MOHAMMEDIA', 'déduit des adresses : Alia, La Colline, Cité El Qods'),
}

# (rôle, libellé, code lien du cadrage, poids de départ, graphies) — « cessionnaire » avant « cédant »
ROLES = [
    # (rôle, libellé, code lien du cadrage, poids de départ, graphies) — l'ordre compte : « cessionnaire » avant « cédant »
    ('cessionnaire', 'Cessionnaire de parts', 'L09', 0.5,
     ['CESSIONNAIRE', 'CESSIONNAIRES', 'CESSIONAIRE', 'المفوت له', 'المفوت لها', 'المفوت اليه', 'المتنازل له', 'المتنازل لفائدته', 'المفوت لهم']),
    ('cedant', 'Cédant de parts (sortant)', 'L09', 0.3,
     ['CEDANT', 'CEDANTE', 'CEDANTS', 'المفوت', 'مفوت', 'المتنازل', 'متنازل']),
    ('liquidateur', 'Liquidateur', 'L08', 0.5,
     ['LIQUIDATEUR', 'LIQUIDATRICE', 'LIQUIDATEURS', 'المصفي', 'مصفي', 'مصفية', 'المصفية']),
    ('gerant_sortant', 'Gérant sortant', 'L08', 0.5, ['GERANT SORTANT', 'ANCIEN GERANT', 'DIRIGEANT SORTANT']),
    ('associe_sortant', 'Associé sortant', 'L09', 0.3, ['ASSOCIE SORTANT', 'ANCIEN ASSOCIE']),
    ('gerant', 'Gérant ou cogérant', 'L08', 0.7,
     ['GERANT', 'GERANTE', 'GERANTS', 'COGERANT', 'CO GERANT', 'GERANCE', 'DIRIGEANT', 'DIRIGEANTE',
      'المسير', 'مسير', 'مسيرة', 'المسيرة', 'المسيرين', 'مسيري', 'التسيير', 'تسيير', 'مسيرا']),
    ('administrateur', 'Administrateur, président ou directeur général', 'L08', 0.7,
     ['ADMINISTRATEUR', 'ADMINISTRATRICE', 'ADMINISTRATEURS', 'PRESIDENT', 'PRESIDENTE', 'PDG',
      'DIRECTEUR GENERAL', 'DIRECTEUR', 'DG', 'متصرف', 'المتصرف', 'رئيس', 'الرئيس', 'المدير', 'مدير']),
    ('associe', 'Associé (poids 0,3 + 0,4 × part détenue quand elle est connue)', 'L09', 0.5,
     ['ASSOCIE', 'ASSOCIEE', 'ASSOCIES', 'ASSOCIEES', 'ACTIONNAIRE', 'ACTIONNAIRES',
      'شريك', 'الشريك', 'شركاء', 'الشركاء', 'شريكة', 'مساهم', 'المساهم', 'المساهمين']),
    ('representant', 'Représentant', 'L08', 0.3, ['REPRESENTANT', 'REPRESENTANTE']),
    ('inconnu', 'Rôle non précisé (CIN cité sans personne rattachée)', 'L09', 0.3, []),
]

REGLES = [
    # (règle, libellé, nature, niveau, clé liste noire, clé registre, confirmation, poids)
    ('R01', 'Même CIN : l\'inscrit est cité dans une annonce', 'identite', 'certain',
     'cin (personne)', 'CIN cité dans le texte de l\'annonce', '—', '1,0'),
    ('R01b', 'CIN saisi sur une société inscrite = personne citée (son dirigeant)', 'dirigeant', 'certain',
     'cin (ligne société)', 'CIN cité dans le texte', '—', '1,0'),
    ('R01v', 'CIN saisi avec une lettre finale parasite = même CIN sans cette lettre', 'identite', 'probable',
     'cin sans la lettre finale', 'CIN cité dans le texte', '—', '0,8'),
    ('R01n', 'Même CIN, mais le nom cité ne correspond pas : CIN peut-être rattaché à la mauvaise personne '
     'de l\'annonce', 'identite', 'probable', 'cin (personne)', 'CIN cité dans le texte', 'nom à vérifier', '0,7'),
    ('R02', 'Même numéro RC, même tribunal et raison sociale compatible', 'identite', 'certain',
     'regist_com (ou RC saisi dans cin) + regist_tribune', 'rc + tribunal', 'similarité des noms ≥ 0,6', '1,0'),
    ('R02n', 'Même numéro RC et même tribunal, mais raison sociale différente ou annonce douteuse', 'identite',
     'probable', 'regist_com + regist_tribune', 'rc + tribunal', 'à vérifier', '0,5'),
    ('R03', 'Même numéro RC, tribunal absent d\'un côté, raison sociale proche', 'identite', 'probable',
     'regist_com', 'rc', 'similarité des noms ≥ 0,8', '0,9 × similarité'),
    ('R03t', 'Même numéro RC, tribunaux différents, raison sociale quasi identique', 'identite', 'probable',
     'regist_com + regist_tribune', 'rc + tribunal', 'similarité des noms ≥ 0,9', '0,6'),
    ('R04', 'Même raison sociale et même ville (siège ou tribunal)', 'identite', 'probable',
     'nom_ras', 'denomination', 'ville', '0,7 exacte / 0,6 squelette × rareté'),
    ('R04u', 'Raison sociale unique au registre (option r04_sans_ville)', 'identite', 'probable',
     'nom_ras', 'denomination', 'unicité au registre', '0,6'),
    ('R10', 'Même ICE', 'identite', 'certain', 'ice', 'ice', '—', '1,0'),
    ('R11', 'Même identifiant fiscal', 'identite', 'certain', 'IF (regist_com, cin ou ice)', 'identifiant_fiscal',
     '—', '1,0'),
    ('R05', 'Même nom de personne et même société (employeur déclaré = société de l\'annonce)', 'identite',
     'probable', 'nom + prenom, lib_emp', 'personne citée + denomination', 'société', '0,8 / 0,7 × rareté'),
    ('R05b', 'Même nom de personne et société de l\'annonce reliée à une société inscrite', 'identite', 'probable',
     'nom + prenom', 'personne citée', 'société inscrite', '0,8 / 0,7 × rareté'),
    ('R06', 'Même nom de personne et même date de naissance', 'identite', 'probable',
     'nom + prenom, date_naiss', 'personne citée + date de naissance', 'date de naissance', '0,8 / 0,7 × rareté'),
    ('R07', 'Même nom de personne et même ville', 'identite', 'probable',
     'nom + prenom, ville, adresse', 'personne citée + siège ou tribunal', 'ville', '0,5 / 0,4 × rareté'),
    ('R08', 'Employeur déclaré de l\'inscrit = société du registre (lien L06)', 'emploi', 'probable',
     'lib_emp', 'denomination', '—', '0,6 / 0,5 × rareté'),
    ('R09', 'Même adresse précise : adresse de l\'inscrit = siège d\'une société', 'adresse', 'probable',
     'adresse', 'siege', '—', '0,4 × rareté'),
]

SOURCES_RC = [
    ('bo', 'Bulletin officiel', 'arabe', '374 498 annonces dans l\'export du 22/10/2026, 2022 à octobre 2026'),
    ('flasheconomie', 'Flash Économie', 'français', '17 330 annonces'),
    ('umaroc', 'Annonce légale umaroc', 'français', '2 444 annonces'),
    ('aujourdhui', "Aujourd'hui le Maroc", 'français', '2 270 annonces'),
    ('jaldumaroc', 'JAL du Maroc', 'français', '1 997 annonces'),
    ('jalmaroc', 'JAL Maroc', 'français', '998 annonces'),
]

PARAMETRES = [
    ('alpha_rarete', 0.5, None, 'Rareté = n^(-alpha), n = nombre de sociétés du registre qui partagent la valeur'),
    ('seuil_chemin', 0.05, None, 'Force minimale d\'un chemin conservé (produit des poids des arêtes) ; l\'affichage filtre ensuite'),
    ('profondeur_max', 6, None, 'Nombre maximal d\'arêtes dans un chemin'),
    ('homonyme_max', 5, None, 'Un même nom écrit à l\'identique dans la même ville relie des personnes du registre s\'il apparaît dans au plus ce nombre de sociétés'),
    ('poids_homonyme', 0.8, None, 'Poids de départ du lien « même nom écrit à l\'identique, même ville » (× rareté)'),
    ('r04_sans_ville', 0, None, '1 = rapprocher aussi une société inscrite sur sa seule raison sociale quand elle est unique au registre'),
    ('poids_min_lien', 0.1, None, 'Sous ce poids, un lien probable passe en statut « faible » : gardé, mais hors file des analystes et hors graphe'),
    ('date_reference_liste', None, DATE_REFERENCE_LISTE, 'Liste noire qui fait foi'),
    ('annee_naissance_min', 1920, None, 'Bornes de validité d\'une date de naissance'),
    ('annee_naissance_max', 2008, None, ''),
]

# =============================================================================
# 2. Normalisation commune aux deux bases
#    (la même fonction des deux côtés : c'est ce qui rend les clés comparables)
# =============================================================================
CHIFFRES_AR = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
_LETTRES_AR = '\u0621-\u063A\u0641-\u064A\u066E\u066F\u0671-\u06D3'
ARABE_RE = re.compile('[' + _LETTRES_AR + ']')
_NON_ALNUM = re.compile('[^A-Z0-9' + _LETTRES_AR + ']+')
CORROMPU_RE = re.compile(r'\\E\[|%[=?;]|\[4~|\x1b|%P\d')


def repare(v):
    """Cellule nettoyée : espaces, encodage cassé (Ã©, Â), valeurs vides."""
    if v is None:
        return None
    if isinstance(v, float):
        if v != v:
            return None
        if v.is_integer():
            v = int(v)
    s = str(v)
    if 'Ã' in s or 'Â' in s:
        for enc in ('cp1252', 'latin-1'):
            try:
                s = s.encode(enc).decode('utf-8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        else:
            s = s.replace('Â', ' ')
    s = s.replace('\xa0', ' ').replace('\u200e', '').replace('\u200f', '')
    s = re.sub(r'\s+', ' ', s).strip()
    if s.lower() in ('', 'nan', 'none', 'null', 'nat', '-', '*'):
        return None
    return s


def latin_maj(s):
    """Majuscules sans accents ni ponctuation ; l'arabe est gardé, sans hamza ni voyelles brèves."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', str(s).translate(CHIFFRES_AR))
    s = ''.join(c for c in s if not unicodedata.combining(c)).upper()
    s = s.replace('Œ', 'OE').replace('Æ', 'AE').replace('ß', 'SS')
    return ' '.join(_NON_ALNUM.sub(' ', s).split())


def ar_simple(t):
    return t.replace('ة', 'ه').replace('ى', 'ي')


def est_arabe(s):
    return bool(s and ARABE_RE.search(s))


# ---- squelette consonantique (comparaison latin ↔ arabe) --------------------
_SQ_AR = {'ب': 'b', 'پ': 'b', 'ت': 't', 'ط': 't', 'ث': 't', 'ج': 'j', 'ح': 'h', 'خ': 'h', 'ه': 'h',
          'د': 'd', 'ذ': 'd', 'ض': 'd', 'ظ': 'd', 'ر': 'r', 'ز': 'z', 'س': 's', 'ص': 's', 'ش': 'c',
          'غ': 'g', 'ف': 'f', 'ڤ': 'f', 'ق': 'k', 'ك': 'k', 'ک': 'k', 'ڭ': 'k', 'گ': 'k',
          'ل': 'l', 'م': 'm', 'ن': 'n'}          # ignorées : alif, hamza, ع, و, ي, ى, ة
_SOLAIRES = set('تثدذرزسشصضطظلن')
NON_ARTICLE_AR = {'الياس', 'الهام'}               # « ال » qui n'est pas l'article : Ilyas, Ilham
_SQ_LAT = dict([('SCH', 'c'), ('CH', 'c'), ('SH', 'c'), ('KH', 'h'), ('GH', 'g'), ('DH', 'd'), ('TH', 't'),
                ('PH', 'f'), ('QU', 'k'), ('CK', 'k'), ('GU', 'k'), ('DJ', 'j'), ('OU', ''), ('CE', 's'),
                ('CI', 's'), ('CY', 's'), ('GE', 'j'), ('GI', 'j'), ('GY', 'j'), ('X', 'ks'), ('C', 'k'),
                ('Q', 'k'), ('G', 'k'), ('P', 'b'), ('V', 'f'), ('W', ''), ('Y', ''), ('A', ''), ('E', ''),
                ('I', ''), ('O', ''), ('U', '')] + [(c, c.lower()) for c in 'BDFHJKLMNRSTZ0123456789'])
_SQ_LAT_RE = re.compile('|'.join(sorted((re.escape(k) for k in _SQ_LAT), key=len, reverse=True)))


def squelette(texte, a_retirer=frozenset()):
    """Squelette consonantique : voyelles, ع, و, ي et article retirés ; mêmes classes en arabe et en latin.
    « EL ZOUBAQIRI MOHAMED » et « محمد الزوباقيري » (ordre inversé) donnent ZBKRMHMD / MHMDZBKR."""
    mots = [m for m in latin_maj(texte).split() if m not in a_retirer]
    sortie, prec = [], None
    for m in mots:
        if ARABE_RE.search(m):
            if len(m) == 1:
                prec = m
                continue
            if m.startswith('ال') and len(m) > 3 and m not in NON_ARTICLE_AR:
                if prec == 'عبد':                       # « Abd al- » : le L reste devant une lettre lunaire
                    m = m[2:] if m[2] in _SOLAIRES else 'ل' + m[2:]
                else:
                    m = m[2:]
            sortie.append(''.join(_SQ_AR.get(ch, '') for ch in m))
        else:
            if m in ('EL', 'AL', 'L') and prec != 'ABD':
                prec = m
                continue
            sortie.append(_SQ_LAT_RE.sub(lambda x: _SQ_LAT[x.group(0)], m))
        prec = m
    s = re.sub(r'(.)\1+', r'\1', ''.join(sortie))
    return s.upper() or None


# ---- noms de personnes ------------------------------------------------------
HONORIFIQUES = {'M', 'MR', 'MRS', 'MME', 'MLLE', 'MLE', 'MONSIEUR', 'MADAME', 'MADEMOISELLE', 'SIEUR', 'DAME',
                'DR', 'DOCTEUR', 'ME', 'MAITRE', 'HAJ', 'HADJ', 'HAJJ', 'HAJA', 'HAJJA', 'HADJA', 'SI'}
HONORIFIQUES |= {latin_maj(x) for x in ['السيد', 'السيدة', 'سيد', 'سيدة', 'الآنسة', 'آنسة', 'السادة', 'الحاج',
                                         'الحاجة', 'حاج', 'حاجة', 'الأستاذ', 'الأستاذة', 'ذ', 'الدكتور', 'الدكتورة']}
PARTICULES = {'EL', 'AL', 'BEN', 'BEL', 'BOU', 'BENT', 'AIT', 'OULD', 'IBN', 'ABD', 'ABDEL', 'ABOU', 'ABU',
              'EN', 'ES', 'ER', 'ET', 'ED', 'EZ', 'ECH', 'DE', 'DU', 'DA', 'DI', 'LA', 'LE', 'D', 'L'}
PRENOMS_CANON = {
    'MOHAMMED': 'MOHAMED', 'MOHAMMAD': 'MOHAMED', 'MOHAMAD': 'MOHAMED', 'MUHAMMAD': 'MOHAMED',
    'MUHAMMED': 'MOHAMED', 'MOHAMMMED': 'MOHAMED', 'MED': 'MOHAMED', 'MOHD': 'MOHAMED',
    'ABDALLAH': 'ABDELLAH', 'ABDALLA': 'ABDELLAH', 'ABDELLA': 'ABDELLAH',
    'MUSTAFA': 'MUSTAPHA', 'MOSTAFA': 'MUSTAPHA', 'MOSTAPHA': 'MUSTAPHA',
    'YOUSEF': 'YOUSSEF', 'YUSUF': 'YOUSSEF', 'YOUSUF': 'YOUSSEF', 'HISHAM': 'HICHAM', 'RASHID': 'RACHID',
    'KHALED': 'KHALID', 'AHMAD': 'AHMED', 'AISHA': 'AICHA', 'AYCHA': 'AICHA', 'YASINE': 'YASSINE',
    'YACINE': 'YASSINE', 'OUSAMA': 'OUSSAMA', 'OSSAMA': 'OUSSAMA', 'OSAMA': 'OUSSAMA',
    'ZAKARIAE': 'ZAKARIA', 'ZAKARIYA': 'ZAKARIA', 'ISMAEL': 'ISMAIL', 'ILIAS': 'ILYAS', 'ILYASS': 'ILYAS',
    'NOUREDINE': 'NOUREDDINE', 'ABDERAHIM': 'ABDERRAHIM', 'ABDERAHMANE': 'ABDERRAHMANE',
    'ABDERRAHMAN': 'ABDERRAHMANE', 'SALAHEDINE': 'SALAHEDDINE', 'HAMZAH': 'HAMZA',
}


def mots_nom_latin(texte):
    mots = [m for m in latin_maj(texte).split() if m not in HONORIFIQUES and not ARABE_RE.search(m)]
    sortie, i = [], 0
    while i < len(mots):
        if mots[i] in PARTICULES and i + 1 < len(mots):
            bloc, j = '', i
            while j < len(mots) - 1 and mots[j] in PARTICULES:
                bloc += mots[j]
                j += 1
            m = bloc + mots[j]
            i = j + 1
        else:
            m = mots[i]
            i += 1
        sortie.append(PRENOMS_CANON.get(m, m))
    return sortie


def cle_nom(*parties):
    """Clé exacte d'un nom de personne en écriture latine : mots triés (l'ordre nom / prénom ne compte pas)."""
    texte = ' '.join(p for p in parties if p)
    if not texte or est_arabe(texte):
        return None
    mots = mots_nom_latin(texte)
    return ' '.join(sorted(mots)) if len(mots) >= 2 else None


def article_colle(m):
    """« ELMOSTAFA » → « MOSTAFA », « ELZOUBAQIRI » → « ZOUBAQIRI » ; mais « ALOUBI », « ALIMOU » restent
    entiers : ce qui suit « AL » doit garder au moins deux consonnes, sinon le A est la voyelle du ع."""
    if re.fullmatch(r'(EL|AL)[A-Z]{3,}', m):
        reste = m[2:]
        if len(squelette(reste) or '') >= 2:
            return reste
    return None


def squelettes_nom(nom, prenom=None):
    """Squelettes d'un nom complet dans les deux ordres (+ variante sans article collé : ELZOUBAQIRI → ZOUBAQIRI)."""
    if prenom and nom:
        ordres = [f'{nom} {prenom}', f'{prenom} {nom}']
    else:
        texte = nom or prenom
        if not texte:
            return set()
        mots = texte.split()
        ordres = [texte, ' '.join(reversed(mots))]
    sortie = set()
    for o in ordres:
        mots = [m for m in latin_maj(o).split() if m not in HONORIFIQUES]
        if len(mots) < 2:
            continue
        variantes = {' '.join(mots)}
        if any(article_colle(m) for m in mots):
            variantes.add(' '.join(article_colle(m) or m for m in mots))
        for v in variantes:
            s = squelette(v)
            if s and len(s) >= 3:
                sortie.add(s)
    return sortie


# ---- raisons sociales ---------------------------------------------------------
FORMES_JURIDIQUES = {'STE', 'STES', 'SOCIETE', 'SOCIETES', 'SOC', 'SARL', 'SARLAU', 'SARLU', 'SA', 'SAS', 'SASU',
                     'SNC', 'SCS', 'SCA', 'GIE', 'ETS', 'ETABLISSEMENT', 'ETABLISSEMENTS', 'EURL', 'AU', 'CIE',
                     'SCI', 'SCP', 'SPRL', 'LTD', 'LLC', 'INC'}
FORMES_JURIDIQUES |= {latin_maj(x) for x in ['شركة', 'الشركة', 'شركه', 'ذات', 'المسؤولية', 'مسؤولية', 'المحدودة',
                                              'محدودة', 'الشريك', 'الوحيد', 'مساهمة', 'المساهمة', 'التضامن']}
MOTS_VIDES = {'DE', 'DU', 'DES', 'LA', 'LE', 'LES', 'L', 'D', 'ET', 'EN', 'AUX', 'A', 'POUR', 'PAR',
              'THE', 'OF', 'AND', 'SUR'}
MARQUES_SOCIETE = {'STE', 'SOCIETE', 'SARL', 'SARLAU', 'SA', 'SAS', 'SNC', 'GIE', 'ETS', 'ETABLISSEMENT', 'GROUPE',
                   'GROUP', 'HOLDING', 'TRANS', 'TRANSPORT', 'TRANSPORTS', 'LOGISTIQUE', 'NEGOCE', 'NEGOCES',
                   'SERVICE', 'SERVICES', 'CONSEIL', 'CONSULTING', 'DISTRIBUTION', 'TRAVAUX', 'CONSTRUCTION',
                   'IMMOBILIER', 'IMMOBILIERE', 'IMPORT', 'EXPORT', 'TRADING', 'CAR', 'CARS', 'LOCATION', 'AGENCE',
                   'SOLUTIONS', 'SOLUTION', 'TECHNOLOGIES', 'INDUSTRIE', 'INDUSTRIES', 'EQUIPEMENT', 'EQUIPEMENTS',
                   'TOURS', 'VOYAGES', 'BTP', 'INVEST', 'COMMERCE', 'COMMERCIAL', 'AUTO', 'AUTOS', 'MOTORS',
                   'INTERNATIONAL', 'COMPANY', 'FOOD', 'CONFECTION', 'TEXTILE', 'AGRICULTURE', 'ENTREPRISE',
                   'PRESTATION', 'PRESTATIONS', 'DIVERS', 'BATIMENT', 'IMPRIMERIE', 'COMMUNICATION', 'TRAITEUR',
                   'PROMOTION', 'ASSURANCES', 'MAROC', 'MOROCCO'}


def mots_societe(texte):
    t = ' ' + latin_maj(texte) + ' '
    for motif, rempl in ((r' S A R L A U ', ' SARLAU '), (r' S A R L ', ' SARL '), (r' S A S ', ' SAS '),
                         (r' S N C ', ' SNC '), (r' S A ', ' SA '), (r' A U ', ' AU '), (r' S T E ', ' STE ')):
        t = re.sub(motif, rempl, t)
    # sigles écrits lettre par lettre : « T G V NEGOS » → « TGV NEGOS »
    t = re.sub(r'(?<![A-Z0-9])((?:[A-Z] )+[A-Z])(?![A-Z0-9])', lambda m: m.group(1).replace(' ', ''), t)
    return [m for m in t.split()
            if m not in FORMES_JURIDIQUES and m not in MOTS_VIDES and len(m) > 1]


def cle_rs(texte):
    mots = mots_societe(texte)
    k = ' '.join(sorted(mots))
    return k if len(k) >= 3 else None


def squelette_rs(texte):
    mots = mots_societe(texte)
    s = squelette(' '.join(mots)) if mots else None
    return s if s and len(s) >= 5 else None


# ---- villes, tribunaux, adresses ---------------------------------------------
_VAR_VILLE = {}                                   # graphie latine → ville canonique
for _code, _lib, _ar, _autres in VILLES:
    for _v in [_code, latin_maj(_lib)] + _autres:
        _VAR_VILLE[latin_maj(_v)] = _code
_VILLE_LAT_RE = re.compile(r'(?<![A-Z0-9])(' + '|'.join(sorted(map(re.escape, _VAR_VILLE), key=len, reverse=True))
                           + r')(?![A-Z0-9])')
_VAR_VILLE_AR = {ar_simple(latin_maj(ar)): code for code, _l, ar, _a in VILLES}
_VILLE_AR_RE = re.compile(r'(?:^|\s)[وبل]?(' + '|'.join(sorted(map(re.escape, _VAR_VILLE_AR), key=len, reverse=True))
                          + r')(?=\s|$)')
MOTS_VOIE = {'RUE', 'AV', 'AVENUE', 'BD', 'BOULEVARD', 'ZENKAT', 'ZANKAT', 'ROUTE', 'RTE', 'CHEMIN',
             'IMPASSE', 'PLACE', 'RES', 'RESIDENCE', 'IMM', 'IMMEUBLE', 'LOT', 'LOTISSEMENT', 'CITE', 'HAY',
             'QUARTIER', 'DERB', 'DOUAR', 'ANGLE', 'PASSAGE', 'ALLEE'}


def villes_dans(texte, derniere=True, filtre_voie=True):
    """Ville canonique citée dans un texte (adresse : la dernière ; tribunal : la première)."""
    t = latin_maj(texte)
    if not t:
        return None
    trouvees = []
    for m in _VILLE_LAT_RE.finditer(t):
        avant = t[:m.start()].split()
        if filtre_voie and avant and (avant[-1] in MOTS_VOIE or            # « RUE AGADIR », « ROUTE DE RABAT »
                                      (avant[-1] in ('DE', 'D', 'DU') and len(avant) > 1 and avant[-2] in MOTS_VOIE)):
            continue
        trouvees.append((m.start(), _VAR_VILLE[m.group(1)]))
    ta = ar_simple(t)
    for m in _VILLE_AR_RE.finditer(ta):
        trouvees.append((m.start(1), _VAR_VILLE_AR[m.group(1)]))
    if not trouvees:
        return None
    trouvees.sort()
    return trouvees[-1][1] if derniere else trouvees[0][1]


BRUIT_TRIBUNAL = {'COMMERCE', 'PREMIERE', 'PREMIER', 'INSTANCE', 'GRANDE', 'COMPETENT', 'TRIBUNAL', 'DE', 'DU', 'LA',
                  'LE', 'L', 'D', 'DATE', 'POUR', 'AVIS', 'ET', 'MENTION', 'RC', 'REGISTRE', 'MODIFICATION', 'APRES',
                  'PUBLICATION', 'LEGALE', 'VILLE', 'A', 'FRAIS', 'MAROC', 'DOCUMENTS', 'CES', 'UN', 'UNE', 'DES', 'TC'}
_VARIANTES_LONGUES = sorted((v for v in _VAR_VILLE if len(v.replace(' ', '')) >= 5), key=len, reverse=True)


@functools.lru_cache(maxsize=None)
def tribunal_code(texte):
    """Ville du tribunal : code EQDOM tronqué (CASAB), nom français ou arabe, avec bruit et fautes → ville canonique."""
    t = latin_maj(texte)
    if not t:
        return None, 'absent'
    if t in ('PP', 'PM'):
        return None, 'type_client_saisi_dans_tribunal'
    if re.fullmatch(r'RC ?\d*', t) or t.isdigit():
        return None, 'valeur_erronee'
    v = villes_dans(texte, derniere=False, filtre_voie=False)
    if v:
        return v, 'reconnu'
    t2 = ' '.join(m for m in t.split() if m not in BRUIT_TRIBUNAL)
    if not t2:
        return None, 'valeur_erronee'
    v = villes_dans(t2, derniere=False, filtre_voie=False)
    if v:
        return v, 'reconnu'
    if len(t2) >= 3:                                     # code EQDOM : début du nom canonique de la ville
        candidats = {code for code, *_ in VILLES if code.startswith(t2)}
        if len(candidats) == 1:
            return candidats.pop(), 'code_eqdom'
        if len(candidats) > 1:
            return None, 'ambigu'
    colle = t2.replace(' ', '')
    for var in _VARIANTES_LONGUES:                       # « DECASABLANCA »
        if var.replace(' ', '') in colle:
            return _VAR_VILLE[var], 'reconnu_colle'
    proche = difflib.get_close_matches(t2, list(_VAR_VILLE), n=1, cutoff=0.84)   # « CASABLNCA », « MARRALECH »
    if proche:
        return _VAR_VILLE[proche[0]], 'faute_corrigee'
    return None, 'inconnu'


ABREV_ADR = {'AVENUE': 'AV', 'AVE': 'AV', 'BOULEVARD': 'BD', 'BLD': 'BD', 'BVD': 'BD', 'NUMERO': 'N', 'NUM': 'N',
             'NR': 'N', 'NO': 'N', 'ETAGE': 'ETG', 'EME': '', 'ER': '', 'ERE': '', 'APPARTEMENT': 'APT',
             'APPT': 'APT', 'APP': 'APT', 'IMMEUBLE': 'IMM', 'IMB': 'IMM', 'RESIDENCE': 'RES', 'RESID': 'RES',
             'LOTISSEMENT': 'LOT', 'QUARTIER': 'QR', 'QRT': 'QR', 'ZANKAT': 'RUE', 'ZENKAT': 'RUE',
             'BUREAU': 'BUR', 'MAGASIN': 'MAG', 'LOCAL': 'LOC', 'MAROC': ''}


def cle_adresse(texte):
    t = latin_maj(texte)
    if not t:
        return None
    if not est_arabe(t):
        t = ' '.join(x for x in (ABREV_ADR.get(m, m) for m in t.split()) if x and x not in MOTS_VIDES)
        t = _VILLE_LAT_RE.sub(' ', t)
    mots = t.split()
    if len(mots) < 3 or not any(ch.isdigit() for ch in t):
        return None
    return ' '.join(mots)


# ---- identifiants ---------------------------------------------------------------
def normalise_cin(v):
    s = repare(v)
    if not s:
        return None, 'absent'
    t = re.sub(r'[^A-Z0-9]', '', latin_maj(s))
    if not t:
        return None, 'absent'
    if re.fullmatch(r'X{3,}\d*', t):
        return None, 'masque'
    if re.fullmatch(r'RC[A-Z]?\d+', t):
        return t, 'rc_dans_cin'
    if re.fullmatch(r'IF\d{6,9}', t):
        return t[2:], 'identifiant_fiscal'
    m = re.fullmatch(r'([A-Z]{1,2})0*(\d{1,7})', t)
    if m:
        return m.group(1) + m.group(2), 'valide'
    m = re.fullmatch(r'([A-Z]{1,2})0*(\d{1,7})([A-Z])', t)
    if m:
        return m.group(1) + m.group(2) + m.group(3), 'lettre_finale'
    if t.isdigit():
        return t, 'chiffres_seuls'
    return t, 'non_standard'


def normalise_rc(v):
    """Numéro de registre analytique sans préfixe ni zéros de tête (+ indice de ville éventuel : FES99999)."""
    s = repare(v)
    if not s:
        return None, None, 'absent'
    t = latin_maj(s)
    if re.fullmatch(r'X{3,}\d*', t.replace(' ', '')):
        return None, None, 'masque'
    if re.fullmatch(r'IF ?\d{6,9}', t):
        return re.sub(r'\D', '', t), None, 'identifiant_fiscal'
    nombres = re.findall(r'\d+', t)
    if not nombres:
        return None, None, 'non_standard'
    num = str(int(max(nombres, key=len)))
    indice = None
    for mot in re.sub(r'\d+', ' ', t).split():
        if len(mot) >= 3 and mot not in ('RCR', 'RCZ', 'RCA', 'NUM', 'NUMERO', 'RC'):
            code, _ = tribunal_code(mot)
            indice = code or indice
    return num, indice, 'rc'


def date_iso(v):
    s = repare(v)
    if not s:
        return None
    s = s.translate(CHIFFRES_AR)
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        a, mo, j = map(int, m.groups())
    else:
        m = re.match(r'^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})', s)
        if not m:
            return None
        j, mo, a = map(int, m.groups())
    try:
        return datetime(a, mo, j).strftime('%Y-%m-%d')
    except ValueError:
        return None


def nombre(v):
    s = repare(v)
    if not s:
        return None
    try:
        return float(s.replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


# =============================================================================
# 3. Lecture des fichiers
# =============================================================================
def _cle_col(c):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(c)).encode('ascii', 'ignore').decode().lower())


def lire_table(chemin):
    ext = os.path.splitext(chemin)[1].lower()
    if ext in ('.csv', '.tsv', '.txt'):
        with open(chemin, encoding='utf-8-sig', newline='') as f:
            echantillon = f.read(50000)
            f.seek(0)
            try:
                dialecte = csv.Sniffer().sniff(echantillon, delimiters=',;\t|')
            except csv.Error:
                dialecte = csv.excel
            return list(csv.DictReader(f, dialect=dialecte))
    if ext in ('.xlsx', '.xlsm', '.xls'):
        import pandas as pd
        feuilles = pd.ExcelFile(chemin).sheet_names
        # liste noire nettoyée (nettoyer_liste_noire.py) : la feuille des inscriptions, sinon la première feuille
        feuille = next((f for f in feuilles if _cle_col(f) == 'inscriptionsnettoyees'), feuilles[0])
        return pd.read_excel(chemin, sheet_name=feuille, dtype=str).to_dict('records')
    if ext == '.parquet':
        import pandas as pd
        return pd.read_parquet(chemin).astype(object).to_dict('records')
    if ext in ('.json', '.jsonl', '.ndjson'):
        with open(chemin, encoding='utf-8-sig') as f:
            texte = f.read()
        debut = texte.lstrip()[:1]
        if debut == '[':
            return json.loads(texte)
        if debut == '{':
            try:
                obj = json.loads(texte)
                for k in ('annonces', 'rows', 'data', 'results', 'records'):
                    if isinstance(obj.get(k), list):
                        return obj[k]
                return [obj]
            except json.JSONDecodeError:
                pass
        return [json.loads(l) for l in texte.splitlines() if l.strip()]
    sys.exit(f'Format non reconnu : {chemin}')


ALIAS_ANNONCE = {
    'annonce_id': ['annonce_id', 'id_annonce', 'id', 'uid', 'identifiant'],
    'source': ['source', 'journal', 'support'],
    'type_acte': ['type_acte', 'typeActe', 'type', 'acte', 'nature_acte'],
    'date_publication': ['date_publication', 'datePublication', 'date_parution', 'dateParution', 'date'],
    'numero_publication': ['numero_publication', 'numeroPublication', 'numero_bo', 'numero'],
    'denomination': ['denomination', 'nom_societe', 'raison_sociale', 'societe', 'nom'],
    'rc': ['rc', 'numero_rc', 'num_rc', 'registre', 'registre_commerce'],
    'tribunal': ['tribunal', 'greffe', 'juridiction'],
    'depot': ['depot', 'depot_legal', 'depotLegal'],
    'date_acte': ['date_acte', 'dateActe'],
    'capital': ['capital', 'capital_social'],
    'siege': ['siege', 'siege_social', 'adresse_siege', 'adresse'],
    'objet': ['objet', 'objet_social', 'activite'],
    'nouveau_capital': ['nouveau_capital', 'nouveauCapital'],
    'nouveau_siege': ['nouveau_siege', 'nouveauSiege'],
    'nouvelle_denomination': ['nouvelle_denomination', 'nouvelleDenomination', 'nouveau_nom', 'nouveauNom'],
    'complet': ['complet', 'lecture_complete'],
    'ice': ['ice'],
    'url': ['url', 'lien'],
    'cin': ['cin', 'cins', 'cin_passeport'],
}
ALIAS_PERSONNE = {
    'annonce_id': ['annonce_id', 'id_annonce', 'uid'],
    'role': ['role', 'qualite', 'fonction'],
    'nom_complet': ['nom_complet', 'nomComplet', 'nom_prenom', 'personne', 'identite', 'nom_et_prenom'],
    'nom': ['nom', 'nom_famille'],
    'prenom': ['prenom', 'prenoms'],
    'cin': ['cin', 'cin_passeport', 'piece_identite', 'numero_cin', 'passeport'],
    'parts': ['parts', 'nb_parts', 'nombre_parts'],
    'date_naissance': ['date_naissance', 'dateNaissance', 'naissance'],
    'nationalite': ['nationalite'],
    'adresse': ['adresse', 'domicile'],
}
CLES_PERSONNES_JSON = {'gerant': 'gerant', 'gerants': 'gerant', 'cogerants': 'gerant', 'associes': 'associe',
                       'associe': 'associe', 'cedant': 'cedant', 'cedants': 'cedant', 'cessionnaire': 'cessionnaire',
                       'cessionnaires': 'cessionnaire', 'liquidateur': 'liquidateur', 'liquidateurs': 'liquidateur',
                       'administrateur': 'administrateur', 'administrateurs': 'administrateur',
                       'president': 'administrateur', 'personnes': None}


def renommer(ligne, alias):
    dispo = {_cle_col(k): v for k, v in ligne.items()}
    sortie = {}
    for champ, noms in alias.items():
        for n in noms:
            v = dispo.get(_cle_col(n))
            if v not in (None, '') and not isinstance(v, (list, dict)):
                sortie[champ] = v
                break
    return sortie


def personnes_imbriquees(brute):
    """Personnes d'une annonce JSON : listes ou textes sous gerant, associes, cedant, liquidateur, personnes…"""
    sortie = []
    for k, v in brute.items():
        ck = _cle_col(k)
        if ck not in CLES_PERSONNES_JSON or v in (None, '', []):
            continue
        role = CLES_PERSONNES_JSON[ck]
        for el in (v if isinstance(v, list) else [v]):
            if isinstance(el, dict):
                p = renommer(el, ALIAS_PERSONNE)
                p['role'] = p.get('role') or role or 'inconnu'
                sortie.append(p)
            elif isinstance(el, str):
                for nom in re.split(r'\s*(?:;|\n|\bet\b| و )\s*', el):
                    if nom.strip():
                        sortie.append({'role': role or 'inconnu', 'nom_complet': nom.strip()})
    return sortie


# =============================================================================
# 4. Construction
# =============================================================================
def role_normalise(texte):
    t = ' ' + latin_maj(texte) + ' '
    if not t.strip():
        return 'inconnu'
    for role, _l, _c, _p, variantes in ROLES:
        for v in variantes:
            if ' ' + latin_maj(v) + ' ' in t:
                return role
    if t.strip().lower() in {r[0] for r in ROLES}:
        return t.strip().lower()
    return 'inconnu'


def creer_base(chemin_base):
    decisions = []
    if os.path.exists(chemin_base):
        try:
            ancienne = sqlite3.connect(chemin_base)
            decisions = ancienne.execute(
                'SELECT cle_bl, rc_objet, cle_rc, decision, analyste, date_decision, justification '
                'FROM decision_analyste').fetchall()
            ancienne.close()
        except sqlite3.Error:
            pass
        os.remove(chemin_base)
    con = sqlite3.connect(chemin_base)
    with open(os.path.join(ICI, 'schema_bl_rc.sql'), encoding='utf-8') as f:
        con.executescript(f.read())
    con.executemany('INSERT INTO decision_analyste (cle_bl, rc_objet, cle_rc, decision, analyste, date_decision, '
                    'justification) VALUES (?,?,?,?,?,?,?)', decisions)
    con.commit()
    if decisions:
        print(f'  {len(decisions)} décisions d\'analyste reprises de la base précédente')
    return con


def charger_referentiels(con):
    con.executemany('INSERT INTO parametre VALUES (?,?,?,?)', PARAMETRES)
    con.executemany('INSERT INTO ref_ville VALUES (?,?,?,?,?)',
                    [(c, l, ar, c[:5], ' | '.join([c] + a)) for c, l, ar, a in VILLES])
    con.executemany('INSERT INTO ref_ville_code_eqdom VALUES (?,?,?,?)',
                    [(k, v[0], 'déduit des adresses, à confirmer par EQDOM', v[1]) for k, v in VILLE_CODES_EQDOM.items()])
    con.executemany('INSERT INTO ref_role VALUES (?,?,?,?,?)',
                    [(r, l, c, p, ' | '.join(v)) for r, l, c, p, v in ROLES])
    con.executemany('INSERT INTO ref_regle VALUES (?,?,?,?,?,?,?,?)', REGLES)
    con.executemany('INSERT INTO ref_source_rc VALUES (?,?,?,?)', SOURCES_RC)


def charger_correspondance_champs(con, rb):
    champs = [
        ('cin (personne)', 'CIN cité dans le texte libre (pas de colonne CIN dans l\'export)', 'CIN',
         'lettres + numéro sans zéros de tête ; lettre finale parasite → CIN_VAR', 'R01, R01v',
         rb.get('cin_pp'), '235 annonces sur 399 537 (0,06 %)',
         'La clé la plus sûre, mais rare dans les annonces : la plupart des liens personne passeront par le nom.'),
        ('cin (ligne société)', 'cin des personnes citées', 'CIN (dirigeant)', 'idem', 'R01b',
         rb.get('cin_pm_personne'), 'idem', 'CIN d\'une personne saisi sur une société inscrite : son dirigeant probable.'),
        ('regist_com + cin commençant par RC', 'rc — numéro de registre', 'RC_NUM',
         'préfixe RC et zéros de tête retirés ; IF et valeurs masquées écartés', 'R02, R03',
         rb.get('rc'), '83,2 % (n° de dépôt, années et numéros trop longs écartés)', 'Clé principale des sociétés.'),
        ('regist_tribune', 'tribunal (nom de ville, avec bruit et fautes)', 'RC_TRIB, VILLE', 'code EQDOM sur 5 lettres, nom français ou arabe, fautes corrigées → ville',
         'R02, R04', rb.get('tribunal'), '87,2 %',
         'Un numéro RC n\'est unique que dans son tribunal.'),
        ('nom_ras (et nom des sociétés)', 'denomination (+ nouvelle dénomination)', 'RS, RS_SQ',
         'formes juridiques et mots vides retirés, mots triés ; squelette consonantique pour l\'arabe',
         'R02, R03, R04, R04u', rb.get('rs'), '≈ 100 % (en-têtes, formes seules, noms de fiduciaires écartés)',
         'La dénomination est protégée au niveau national (certificat négatif).'),
        ('nom + prenom', 'dirigeants, dirigeants_sortants, associes, associes_sortants, cedants, cessionnaires, liquidateurs, representants', 'NOM, NOM_SQ',
         'honorifiques retirés, particules collées, prénoms ramenés à une graphie, mots triés ; '
         'squelette dans les deux ordres', 'R05, R06, R07', rb.get('nom_pp'),
         'dirigeants 54,9 %, associés 58,3 % des annonces ; faux noms écartés',
         'Nom seul : jamais un lien. Il faut un élément qui confirme.'),
        ('lib_emp (employeur déclaré)', 'denomination', 'RS, RS_SQ (rôle employeur)', 'comme une raison sociale',
         'R05, R08', rb.get('lib_emp'), 'idem denomination', 'Relie l\'inscrit à une société et à ses dirigeants.'),
        ('date_naiss (personnes, 1920 à 2008)', 'date de naissance (si Kamal l\'extrait)', 'DATE_NAISS', 'AAAA-MM-JJ',
         'R06', rb.get('date_naiss'), 'non mesuré', 'Les dates après 2008 sur la liste noire sont des dates de saisie.'),
        ('ville (texte ou code déduit), adresse', 'siege, tribunal, adresse de la personne', 'VILLE',
         'ville canonique, graphies latines et arabes', 'R04, R07', rb.get('ville'),
         'siège : BO 78,4 % ; autres 70 à 86 %', 'Élément de confirmation seulement.'),
        ('adresse', 'siege', 'ADR', 'abréviations unifiées, ville retirée, au moins 3 mots dont un chiffre', 'R09',
         rb.get('adresse'), 'siège : BO 78,4 %', 'Une adresse de domiciliation est partagée : la rareté l\'atténue.'),
        ('ice', 'ice', 'ICE', '15 chiffres', 'R10', rb.get('ice'), '1 155 annonces', 'Identifiant unique : lien certain.'),
        ('IF (regist_com, cin ou ice commençant par IF)', 'identifiant_fiscal', 'IF', 'chiffres', 'R11', '', '1 269 annonces',
         'Identifiant unique : lien certain.'),
        ('motif, motif2, type_liste, type_fraude, orig_liste, note, dat_sais, mt_exposition', '—', '—', '—', '—',
         '', '', 'Décrivent l\'inscription : affichés dans la fiche, pas comparés.'),
        ('—', 'type d\'acte, capital, objet, dépôt, date de l\'acte', '—', '—', '—', '', '',
         'Décrivent la société (âge, capital minimal, activité) : signaux pour la fiche.'),
    ]
    con.executemany('INSERT INTO ref_correspondance_champs VALUES (?,?,?,?,?,?,?,?,?)',
                    [(i + 1,) + c for i, c in enumerate(champs)])


# ---- liste noire ------------------------------------------------------------------
COLONNES_BL = ['num_seq', 'cin', 'regist_com', 'ice', 'regist_tribune', 'cli_phy_mor', 'no_drpp', 'nom_ras', 't_cli',
               'date_naiss', 'adresse', 'ville', 'lib_emp', 'interm', 'part', 'motif', 'motif2', 'type_liste',
               'type_fraude', 'orig_liste', 'orig_agence', 'mt_exposition', 'note', 'dat_sais', 'user_sais',
               'user_maj', 'nom', 'prenom']
# colonnes ajoutées par nettoyer_liste_noire.py dans la liste nettoyée (lues si présentes, ignorées sinon)
COLONNES_BL_NETTOYEES = ['identifiant_fiscal', 'ville_code_eqdom', 'id_entite']


def norme_type_liste(s):
    t = latin_maj(s)
    if not t:
        return None
    if 'CONFORM' in t:
        return 'INDESIRABLE CONFORMITE'
    if 'RISQ' in t:
        return 'INDESIRABLE RISQUE'
    if t.startswith('IND'):
        return 'INDESIRABLE'
    return t


def norme_type_fraude(s):
    t = latin_maj(s)
    return {'ALERTE EXTERNE': 'Alerte externe', 'FRAUDE EVITEE': 'Fraude évitée',
            'FRAUDE SUBIE': 'Fraude subie'}.get(t, s)


def lire_ligne_bl(brute):
    """Une ligne brute du fichier (dict colonne → valeur) → (dict COLONNES_BL réparé, num_seq, anomalies de corruption)."""
    r = {c: None for c in COLONNES_BL + COLONNES_BL_NETTOYEES}
    for k, v in brute.items():
        ck = _cle_col(k)
        for c in COLONNES_BL + COLONNES_BL_NETTOYEES:
            if _cle_col(c) == ck:
                r[c] = repare(v)
    n = int(float(r['num_seq']))
    anomalies = []
    for c in COLONNES_BL:
        if r[c] and CORROMPU_RE.search(r[c]):
            anomalies.append((n, c, r[c][:60], 'valeur corrompue (séquence de terminal)', 'vidée'))
            r[c] = None
    return r, n, anomalies


def normaliser_inscription(r, n, annee_min=1920, annee_max=2008):
    """Normalise une inscription de la liste noire (dict COLONNES_BL) : identifiants, type d'entité, tribunal, ville,
    dates, libellés. Renvoie (inscription, anomalies). Même logique pour la base et pour nettoyer_liste_noire.py."""
    anomalies = []
    cin_norm, cin_statut = normalise_cin(r['cin'])
    rc_num, indice_trib, rc_statut = normalise_rc(r['regist_com'])
    if_num = rc_num if rc_statut == 'identifiant_fiscal' else None
    if rc_statut == 'identifiant_fiscal':
        rc_num = None
        anomalies.append((n, 'regist_com', r['regist_com'], 'identifiant fiscal saisi comme RC', 'rangé en IF'))
    if rc_statut == 'masque':
        anomalies.append((n, 'regist_com', r['regist_com'], 'RC masqué (XXXXXX)', 'ignoré'))
    if cin_statut == 'identifiant_fiscal':
        if_num = if_num or cin_norm
    if not if_num and r.get('identifiant_fiscal'):               # liste nettoyée : IF déjà rangé dans sa colonne
        if_num = re.sub(r'\D', '', r['identifiant_fiscal']) or None
    if cin_statut == 'rc_dans_cin':
        rc_cin = str(int(re.sub(r'\D', '', cin_norm)))
        if rc_num and rc_num != rc_cin:
            anomalies.append((n, 'cin', r['cin'], f'RC différent de regist_com ({rc_num})', 'regist_com retenu'))
        rc_num = rc_num or rc_cin
    if cin_statut in ('masque', 'non_standard', 'chiffres_seuls', 'lettre_finale'):
        anomalies.append((n, 'cin', r['cin'], {'masque': 'CIN masqué (XXXXXX)',
                                               'non_standard': 'CIN au format non standard',
                                               'chiffres_seuls': 'CIN sans lettres',
                                               'lettre_finale': 'CIN avec une lettre finale parasite'}[cin_statut],
                          'variante sans la lettre pour R01v' if cin_statut == 'lettre_finale' else 'ignoré'))

    ice = re.sub(r'\D', '', r['ice'] or '')
    ice_norm = ice if len(ice) == 15 else None
    if r['ice'] and not ice_norm:
        if latin_maj(r['ice']).startswith('IF'):
            if_num = if_num or re.sub(r'\D', '', r['ice'])
            anomalies.append((n, 'ice', r['ice'], 'identifiant fiscal saisi comme ICE', 'rangé en IF'))

    trib, trib_statut = tribunal_code(r['regist_tribune'])
    if trib_statut in ('type_client_saisi_dans_tribunal', 'valeur_erronee', 'ambigu', 'inconnu'):
        anomalies.append((n, 'regist_tribune', r['regist_tribune'],
                          {'type_client_saisi_dans_tribunal': 'PP ou PM saisi dans la colonne tribunal',
                           'valeur_erronee': 'valeur sans rapport avec un tribunal',
                           'ambigu': 'code tribunal ambigu', 'inconnu': 'code tribunal inconnu'}[trib_statut],
                          'tribunal vide'))
    if not trib and indice_trib:
        trib, trib_statut = indice_trib, 'deduit_du_rc'

    # type d'entité : PP / PM, corrigé si les données le contredisent
    declare = (r['cli_phy_mor'] or '').upper()
    if declare not in ('PP', 'PM'):
        declare = latin_maj(r['regist_tribune']) if latin_maj(r['regist_tribune']) in ('PP', 'PM') else None
    nom_texte = r['nom_ras'] or r['nom'] or ''
    marque = bool(set(latin_maj(nom_texte).split()) & MARQUES_SOCIETE)
    if declare == 'PM':
        t = 'PM'
    elif cin_statut in ('rc_dans_cin', 'identifiant_fiscal') and not r['prenom']:
        t = 'PM'
    elif r['nom_ras'] and not r['prenom']:
        t = 'PM'
    elif not r['prenom'] and marque:
        t = 'PM'
    elif declare == 'PP' or cin_statut in ('valide', 'lettre_finale') or r['prenom']:
        t = 'PP'
    elif rc_num:
        t = 'PM'
    else:
        t = 'PP'
    if declare and declare != t:
        anomalies.append((n, 'cli_phy_mor', r['cli_phy_mor'] or r['regist_tribune'],
                          f'déclaré {declare}, données de {"société" if t == "PM" else "personne"}',
                          f'classé {t}'))

    if t == 'PM':
        nom_affiche = r['nom_ras'] or r['nom'] or r['prenom']
    else:
        nom_affiche = ' '.join(x for x in (r['nom'], r['prenom']) if x) or r['nom_ras']

    dn = date_iso(r['date_naiss'])
    dn_valide = dn if (t == 'PP' and dn and annee_min <= int(dn[:4]) <= annee_max) else None
    if dn and not dn_valide and t == 'PP':
        anomalies.append((n, 'date_naiss', dn, 'date de naissance hors bornes (saisie ou valeur par défaut)',
                          'ignorée'))

    ville, ville_origine = None, None
    if r['ville']:
        if r['ville'].isdigit():
            if r['ville'] in VILLE_CODES_EQDOM:
                ville, ville_origine = VILLE_CODES_EQDOM[r['ville']][0], 'code_deduit'
        else:
            ville, ville_origine = villes_dans(r['ville']), 'texte'
    if not ville and r['adresse']:
        ville = villes_dans(r['adresse'])
        ville_origine = 'adresse' if ville else None

    return dict(
        r, num_seq=n, mt_exposition=nombre(r['mt_exposition']), date_naiss=dn or r['date_naiss'],
        dat_sais=date_iso(r['dat_sais']) or r['dat_sais'], type_entite=t, cin_norm=cin_norm,
        cin_statut=cin_statut, rc_num=rc_num, rc_statut=rc_statut, if_num=if_num, ice_norm=ice_norm,
        tribunal_code=trib, tribunal_statut=trib_statut, ville_code=ville, ville_origine=ville_origine,
        date_naiss_valide=dn_valide, nom_affiche=nom_affiche, type_liste_norm=norme_type_liste(r['type_liste']),
        type_fraude_norm=norme_type_fraude(r['type_fraude']), statut_inscription='actif',
        date_reference=DATE_REFERENCE_LISTE, rs=cle_rs(nom_texte) if t == 'PM' else None), anomalies


COLONNES_DOUBLON = [c for c in COLONNES_BL if c not in ('num_seq', 'user_sais', 'user_maj')]


def ecarter_doublons(inscriptions):
    """Lignes strictement identiques (mêmes valeurs sur toutes les colonnes hors n° de séquence et utilisateur) :
    on garde la première (n° de séquence le plus petit), les autres sont écartées. Une ligne sans aucun identifiant
    ni nom n'est jamais considérée comme doublon."""
    vues, gardees, anomalies = {}, [], []
    for i in sorted(inscriptions, key=lambda x: x['num_seq']):
        if not any(i.get(c) for c in ('cin', 'regist_com', 'nom', 'prenom', 'nom_ras', 'ice')):
            gardees.append(i)
            continue
        cle = tuple(' '.join(latin_maj(i.get(c) or '').split()) for c in COLONNES_DOUBLON)
        if cle in vues:                                 # l'anomalie est portée par la ligne gardée (clé étrangère)
            anomalies.append((vues[cle], 'num_seq', str(i['num_seq']), f"doublon exact : ligne n° {i['num_seq']} écartée", 'écartée'))
            continue
        vues[cle] = i['num_seq']
        gardees.append(i)
    return gardees, anomalies


def regrouper_inscriptions(inscriptions):
    """Clé d'entité de chaque inscription (i['cle']) : CIN pour une personne, RC + tribunal pour une société, sinon
    RC + raison sociale, IF, ou la ligne seule. Un RC sans tribunal rejoint la société du même RC et du même nom
    dont le tribunal est connu. Renvoie {clé: [inscriptions]}."""
    def cle_entite(i):
        if i['type_entite'] == 'PP':
            if i['cin_statut'] in ('valide', 'lettre_finale'):
                return 'P:' + i['cin_norm']
            return f"P#{i['num_seq']}"
        if i['rc_num'] and i['tribunal_code']:
            return f"M:{i['rc_num']}@{i['tribunal_code']}"
        if i['rc_num']:
            return f"M:{i['rc_num']}@?:{i['rs'] or ''}"
        if i['if_num']:
            return 'F:' + i['if_num']
        return f"M#{i['num_seq']}"

    for i in inscriptions:
        i['cle'] = cle_entite(i)
    # un RC sans tribunal rejoint la société du même RC et du même nom dont le tribunal est connu
    avec_trib = defaultdict(set)
    for i in inscriptions:
        if i['cle'].startswith('M:') and '@?' not in i['cle']:
            avec_trib[(i['rc_num'], i['rs'])].add(i['cle'])
    for i in inscriptions:
        if '@?' in i['cle']:
            cands = avec_trib.get((i['rc_num'], i['rs']), set())
            if len(cands) == 1:
                i['cle'] = next(iter(cands))


    groupes = defaultdict(list)
    for i in inscriptions:
        groupes[i['cle']].append(i)
    return groupes


def charger_liste_noire(con, chemin):
    lignes = lire_table(chemin)
    anomalies, inscriptions = [], []
    for brute in lignes:
        r, n, anos = lire_ligne_bl(brute)
        anomalies += anos
        i, anos = normaliser_inscription(r, n)
        anomalies += anos
        inscriptions.append(i)
    inscriptions, anos = ecarter_doublons(inscriptions)
    gardees = {i['num_seq'] for i in inscriptions}
    anomalies = [a for a in anomalies if a[0] in gardees] + anos     # les anomalies d'un doublon écarté sont celles de la ligne gardée
    groupes = regrouper_inscriptions(inscriptions)

    def distincts(valeurs, sep=' ; '):
        vus = []
        for v in valeurs:
            if v and v not in vus:
                vus.append(v)
        return sep.join(vus) or None

    entites, cles = [], set()
    for eid, (cle, ins) in enumerate(sorted(groupes.items()), start=1):
        t = ins[0]['type_entite']
        noms = Counter(i['nom_affiche'] for i in ins if i['nom_affiche'])
        saisies = sorted(i['dat_sais'] for i in ins if i['dat_sais'] and re.match(r'\d{4}-', i['dat_sais']))
        cin = next((i['cin_norm'] for i in ins if i['cin_statut'] in ('valide', 'lettre_finale')), None)
        rc = next((i['rc_num'] for i in ins if i['rc_num']), None)
        trib = next((i['tribunal_code'] for i in ins if i['tribunal_code']), None)

        def ajoute(type_cle, role, valeur):
            if valeur:
                cles.add(('BL', 'bl_entite', eid, type_cle, role, valeur, None))

        for i in ins:
            i['entite_id'] = eid
            if t == 'PP':
                if i['cin_statut'] == 'valide':
                    ajoute('CIN', 'identite', i['cin_norm'])
                elif i['cin_statut'] == 'lettre_finale':
                    ajoute('CIN', 'identite', i['cin_norm'])
                    ajoute('CIN_VAR', 'identite', i['cin_norm'][:-1])
                ajoute('NOM', 'identite', cle_nom(i['nom'], i['prenom']))
                for s in squelettes_nom(i['nom'], i['prenom']):
                    ajoute('NOM_SQ', 'identite', s)
                ajoute('DATE_NAISS', 'identite', i['date_naiss_valide'])
                for employeur in (i['lib_emp'], i['nom_ras']):
                    ajoute('RS', 'employeur', cle_rs(employeur))
                    ajoute('RS_SQ', 'employeur', squelette_rs(employeur))
                if i['rc_num']:                                  # commerçant personne physique
                    ajoute('RC_NUM', 'identite', i['rc_num'])
                    if i['tribunal_code']:
                        ajoute('RC_TRIB', 'identite', f"{i['rc_num']}@{i['tribunal_code']}")
            else:
                if i['rc_num']:
                    ajoute('RC_NUM', 'identite', i['rc_num'])
                    if i['tribunal_code']:
                        ajoute('RC_TRIB', 'identite', f"{i['rc_num']}@{i['tribunal_code']}")
                nom_soc = i['nom_ras'] or i['nom']
                ajoute('RS', 'identite', cle_rs(nom_soc))
                ajoute('RS_SQ', 'identite', squelette_rs(nom_soc))
                if i['cin_statut'] == 'valide':
                    ajoute('CIN', 'dirigeant', i['cin_norm'])
                ajoute('VILLE', 'tribunal', i['tribunal_code'])
            ajoute('ICE', 'identite', i['ice_norm'])
            ajoute('IF', 'identite', i['if_num'])
            ajoute('VILLE', 'residence' if t == 'PP' else 'siege', i['ville_code'])
            ajoute('ADR', 'residence' if t == 'PP' else 'siege', cle_adresse(i['adresse']))

        rattache = 'cle_dure' if (t == 'PP' and cin) or (t == 'PM' and rc) else 'a_calculer'
        entites.append(dict(
            entite_id=eid, cle_entite=cle, type_entite=t,
            nom_affiche=noms.most_common(1)[0][0] if noms else None,
            cin=cin, rc_num=rc, tribunal_code=trib,
            if_num=next((i['if_num'] for i in ins if i['if_num']), None),
            ice=next((i['ice_norm'] for i in ins if i['ice_norm']), None),
            date_naissance=next((i['date_naiss_valide'] for i in ins if i['date_naiss_valide']), None),
            ville_code=next((i['ville_code'] for i in ins if i['ville_code']), None),
            adresse=next((i['adresse'] for i in ins if i['adresse']), None),
            employeur=next((i['lib_emp'] for i in ins if i['lib_emp']), None) if t == 'PP' else None,
            nb_inscriptions=len(ins), premiere_saisie=saisies[0] if saisies else None,
            derniere_saisie=saisies[-1] if saisies else None,
            types_liste=distincts(i['type_liste_norm'] for i in ins),
            types_fraude=distincts(i['type_fraude_norm'] for i in ins),
            origines=distincts(i['orig_liste'] for i in ins),
            motifs=distincts(x for i in ins for x in (i['motif'], i['motif2']) if x and x != 'NULL'),
            exposition_max=max((i['mt_exposition'] for i in ins if i['mt_exposition'] is not None), default=None),
            statut='actif', date_reference=DATE_REFERENCE_LISTE, rattachement=rattache))

    cles_par_entite = defaultdict(set)
    for c in cles:
        cles_par_entite[c[2]].add(c[3])
    for e in entites:
        if e['rattachement'] != 'cle_dure':
            e['rattachement'] = 'nom' if cles_par_entite[e['entite_id']] & {'NOM', 'NOM_SQ', 'RS', 'RS_SQ'} else 'aucun'

    champs_e = list(entites[0].keys())
    con.executemany(f"INSERT INTO bl_entite ({','.join(champs_e)}) VALUES ({','.join('?' * len(champs_e))})",
                    [tuple(e[c] for c in champs_e) for e in entites])
    champs_i = ['num_seq', 'entite_id'] + COLONNES_BL[1:] + [
        'type_entite', 'cin_norm', 'cin_statut', 'rc_num', 'rc_statut', 'if_num', 'ice_norm', 'tribunal_code',
        'tribunal_statut', 'ville_code', 'ville_origine', 'date_naiss_valide', 'nom_affiche', 'type_liste_norm',
        'type_fraude_norm', 'statut_inscription', 'date_reference']
    con.executemany(f"INSERT INTO bl_inscription ({','.join(champs_i)}) VALUES ({','.join('?' * len(champs_i))})",
                    [tuple(i[c] for c in champs_i) for i in inscriptions])
    con.executemany('INSERT INTO bl_anomalie (num_seq, champ, valeur, anomalie, traitement) VALUES (?,?,?,?,?)',
                    anomalies)
    con.executemany('INSERT OR IGNORE INTO cle (cote, objet, objet_id, type_cle, role, valeur, societe_id) '
                    'VALUES (?,?,?,?,?,?,?)', sorted(cles))

    nb = len(inscriptions)
    pct = lambda k: f'{100 * k / nb:.1f} %' if nb else '—'
    pp = [i for i in inscriptions if i['type_entite'] == 'PP']
    pm = [i for i in inscriptions if i['type_entite'] == 'PM']
    remplissage = {
        'cin_pp': f"{pct(sum(i['cin_statut'] in ('valide', 'lettre_finale') for i in pp))} des lignes (PP)",
        'cin_pm_personne': f"{sum(i['cin_statut'] == 'valide' for i in pm)} lignes PM",
        'rc': pct(sum(bool(i['rc_num']) for i in inscriptions)),
        'tribunal': pct(sum(bool(i['tribunal_code']) for i in inscriptions)),
        'rs': f"{pct(sum(bool(i['rs']) for i in pm))} des lignes PM" if pm else '—',
        'nom_pp': pct(sum(bool(cle_nom(i['nom'], i['prenom'])) for i in pp)) + ' des lignes PP',
        'lib_emp': pct(sum(bool(i['lib_emp']) for i in inscriptions)),
        'date_naiss': f"{sum(bool(i['date_naiss_valide']) for i in inscriptions)} dates valides",
        'ville': pct(sum(bool(i['ville_code']) for i in inscriptions)),
        'adresse': pct(sum(bool(cle_adresse(i['adresse'])) for i in inscriptions)),
        'ice': f"{sum(bool(i['ice_norm']) for i in inscriptions)} lignes",
    }
    return {'inscriptions': nb, 'entites': len(entites), 'anomalies': len(anomalies), 'cles': len(cles)}, remplissage


# ---- registre du commerce : lecture -------------------------------------------------
# Export de Kamal (annonces-legales-AAAA-MM-JJ.csv) : une ligne par annonce, personnes dans des champs texte
#   dirigeants      « Nom — Gérant | Nom — Co-gérant »
#   associes…       « Nom (1000 parts, 50 %) | NOM SOCIETE (société) (…) »
# Le modèle générique (rc_annonces + rc_personnes) reste accepté.

SOURCES_KAMAL = {'BULLETIN OFFICIEL': 'bo', 'FLASH ECONOMIE': 'flasheconomie', 'ANNONCE LEGALE UMAROC': 'umaroc',
                 'AUJOURD HUI LE MAROC': 'aujourdhui', 'JAL DU MAROC': 'jaldumaroc', 'JAL MAROC': 'jalmaroc'}
CHAMPS_PERSONNES = [('dirigeants', None), ('dirigeants_sortants', 'gerant_sortant'), ('associes', 'associe'),
                    ('associes_sortants', 'associe_sortant'), ('cedants', 'cedant'), ('cessionnaires', 'cessionnaire'),
                    ('liquidateurs', 'liquidateur'), ('representants', 'representant')]


def _norm_set(mots):
    return {latin_maj(m) for m in mots.split()} - {''}


# mots qui ne sont jamais des noms de personnes (vocabulaire juridique relevé dans l'export)
STOP_NOMS = _norm_set('''أنيطت مهمة لمدة ولمدة غير محدودة يعهد يعتبر يتولى يعين تعين عينت معين تعيين تقرر قرر قرار
قراررقم التسيير تسيير مسير مسيرين مسيرأو أومسيرين مسيرللشركة مسيرالشركة ستسير ويسيرها يسيرها ويدير يدير وتدار تدار
إدارة الإدارة ادارة مدير مديرعام المدير العام عامة منتدب منتدبة رئيس الرئيس مجلس السابق السابقة السابقين القديم القديمة
الجديد الجديدة الحالي الحالية عنوانه عنوانها العنوان وإعفائه إعفائه إعفاء لشركة الشركة شركة للشركة الشريك شريك الشركاء
شركاء المساهم المساهمين المشارك مشترك المذكورة المذكور أعاله أعلاه اعلاه والتي الذي التي هي هو وتبعا لذلك المخول البت
الإيداع الايداع إيداع سيتم تم يتم تحيين بصفة والكائن الكائن الكائنة الشكل المسماة المسمى بناء ثاني الثاني الثانية قدره
واحد قبول المغرب الاجتماعية رأسمالها رأسمال المال درهم غاية بواسطة السباكة الكهرباء المصادقة ابتداء يعود أصبحت المؤرخ
تاريخ التصفية الوطنية الوطني التعريف حصصه حصصها حصة حصص الأصل الاصل التجاري الإعالنات الاعالنات الإعلانات القانونية
والادارية الادارية المحكمة التجارية الابتدائية السجل الضبط كتابة العقد عقد عرفي موثق الموثق المحامي المحاسب الخبير وكيل
الوكيل نيابة عنه عنها لفائدة لحساب ذات المسؤولية المحدودة الوحيد والمسماة بموجب بمقتضى طبقا وفقا حسب نفس النظام الأساسي
الاساسي القانون الفصل البند المادة استقالة الاستقالة وفاة الهالك ورثة الورثة مدة سنة سنوات تجديد المهام مهام مهامه مهامها
المهمة الجمع العادي الاستثنائي العمومي المائي والمصادقة إلى الى في على من مع أو او وفي ثم
بيانات بند حول وعند عند الاقتضاء الإقتضاء الحدود المفروضة قاضيا منتدبا مسيروحيد أعطي اعطي حق بدون مقابل وتلزم تلزم
بإمضاء بامضاء الصلاحيات الصالحيات الضرورية لإنجاز النجاز الإجراءات الاجراءات الأخيرة الاخيرة الناتجة بسومة شهرية قدرها
أرضا ارضا قيمت قدمت يعتبران المسيران لتسيير توكيله وإنهاء وانهاء والموافقة وتكلفه وتكلف بالقيام بكل عملية تهدف
الأعضاء الاعضاء الآتية الاتية التالية التالي الآتي الاتي مواطن مواطنة بريطاني فرنسي اسباني الصرف الصحي التكييف الخ
PRENOM PRENOMS NOM NOMS ANONYME NEANT GERANT GERANTE ASSOCIE ASSOCIEE UNIQUE SORTANT QUALITE SOCIETE''')
# à partir de ces mots, la suite n'est plus le nom (rôle, pièce d'identité, adresse, nationalité, parts)
COUPE_NOMS = _norm_set('''بطاقة البطاقة للبطاقة لبطاقة حامل الحامل صاحب صاحبة جميع مجموعه مجموع عدد رقم المزداد المزدادة
المولود المولودة بتاريخ الساكن الساكنة القاطن القاطنة الجنسية مغربي مغربية المغربي المغربية بصفته بصفتها كمسير كمسيرة
مسيرا مسيرة مديرا مديرة كمدير كمديرة كمتصرف متصرفا متصرفة رئيسا كرئيس وذلك بنسبة
درب زنقة شارع تجزئة عمارة الطابق شقة الشقة دوار إقامة اقامة مكتب الرقم بلوك جماعة إقليم اقليم عمالة المدينة
NE NEE TITULAIRE CIN CNIE DEMEURANT DOMICILIE NATIONALITE MAROCAIN MAROCAINE ADRESSE DETENANT RUE AV AVENUE BD
BOULEVARD LOT RESIDENCE IMM APPT
زوجة أرملة ارملة بقيمة بمبلغ حي طريق
ألف الف آلاف الاف مائة مئة مائتي مائتين ثلاثمائة أربعمائة اربعمائة خمسمائة ستمائة سبعمائة ثمانمائة تسعمائة
عشرة عشر خمسة ستة سبعة ثمانية تسعة عشرون عشرين ثلاثون ثلاثين أربعون اربعون أربعين اربعين خمسون خمسين''')
COUPE_COLLES = [latin_maj(x) for x in ['البطاقة', 'للبطاقة', 'لبطاقة', 'بطاقة', 'حامل', 'كمسير', 'كمدير', 'كمتصرف',
                                        'مسيرللشركة', 'مسيرالشركة']]
CIVILITES_COLLEES = [latin_maj(x) for x in ['السيدة', 'السيد', 'السادة', 'الآنسة']]
MARQUES_PM = {'SARL', 'SARLAU', 'SA', 'SAS', 'SASU', 'STE', 'SOCIETE', 'HOLDING', 'GROUP', 'GROUPE', 'INVEST',
              'INVESTMENT', 'INVESTMENTS', 'CAPITAL', 'LLC', 'LTD', 'LIMITED', 'INC', 'GMBH', 'BV', 'SPA', 'SRL',
              'CORPORATION', 'CORP', 'COMPANY', 'FUND', 'PARTNERS', 'TRADING', 'IMMOBILIERE', 'INTERNATIONAL',
              latin_maj('شركة'), latin_maj('الشركة')}
GENERIQUES_RS = {'SERVICES', 'SERVICE', 'CONSTRUCTION', 'CONSULTING', 'MODIFICATION', 'PRIVE', 'MAROC', 'HOLDING',
                 'INVEST', 'TRADING', 'GROUP', 'GROUPE', 'COMMERCE', 'TRANSPORT', 'IMMOBILIER', 'DISTRIBUTION',
                 'CONSEIL', 'NEGOCE', 'TRAVAUX', 'IMPORT', 'EXPORT', 'CAPITAL', 'PROMOTION', 'ETUDES', 'GESTION'}
ENTETES_RS = {latin_maj(x) for x in ['الاعالنات القانونية والادارية', 'الإعلانات القانونية والإدارية', 'الاعالن',
                                      'الإعلان', 'FLASH ECONOMIE', 'ANNONCES LEGALES', 'ANNONCE LEGALE', 'موثق', 'JAL',
                                      'AUJOURD HUI LE MAROC', 'LE MATIN', 'MODIFICATION', 'CONSTITUTION']}
# en-têtes du Bulletin officiel lus comme une dénomination : « المحكمة التجارية بالرباط », « استدراك خطإ وقع
# بالجريدة », « المقر الاجتماعي : … », « إعلان … » (les ligatures cassées du PDF donnent « املحكمة », « اإلعالن »)
ENTETE_AR_RE = re.compile('|'.join(['محكمة', 'املحكمة', 'استدراك', 'إستدراك', 'تصحيح', 'الجريدة', 'جريدة', 'املقر',
                                   'المقر', 'اإلعالن', 'الإعلان', 'إعالن', 'اعالن', 'اعلان', 'إعلان', 'كتابة الضبط',
                                   'السجل التجاري', 'رقم السجل', 'مكتب التوثيق', 'ديوان الأستاذ', 'ديوان االستاذ',
                                   'مؤرخ', 'بتاريخ']))
MOTS_ADRESSE = {'RUE', 'AV', 'AVENUE', 'BD', 'BOULEVARD', 'ETG', 'ETAGE', 'IMM', 'IMMEUBLE', 'N', 'BUREAU', 'APPT',
                'LOT', 'RES', 'RESIDENCE', 'QUARTIER', 'HAY'}
CIN_TEXTE_RE = re.compile(r'(?:\bCIN\b|\bCNIE\b|CARTE NATIONALE|بطاقة|البطاقة|للبطاقة|لبطاقة)'
                          r'((?:\s+[^\sA-Z0-9]+|\s+N|\s+NO|\s+NUMERO){0,6})\s+([A-Z]{1,2})\s?(\d{3,7})(?![0-9])')


def nettoyer_denomination(d):
    """Retire l'en-tête « VILLE MAROC » collé devant certaines dénominations (« FES MAROC STE X »)."""
    t = latin_maj(d)
    m = re.match(r'^(.{2,25}?) MAROC (.+)$', t)
    if m and villes_dans(m.group(1), filtre_voie=False):
        t = m.group(2)
    return t


def nom_affichage(d):
    """Dénomination telle qu'écrite, sans l'en-tête « VILLE MAROC » collé devant (« FES MAROC RAPIDITY CAR »)."""
    if not d:
        return d
    m = re.match(r'^\s*(.{2,25}?)\s+MAROC\s+(.+)$', d, re.I)
    if m and villes_dans(m.group(1), filtre_voie=False):
        return m.group(2).strip()
    return d.strip()


def statut_denomination(d):
    if not d:
        return 'absente'
    t = nettoyer_denomination(d)
    if not t or t in ENTETES_RS or re.match(r'(AVIS|ANNONCE|EXTRAIT|RECTIFICATIF)\b', t) or ENTETE_AR_RE.search(t):
        return 'entete'
    if re.search(r'\bRC\s*\d{3,}', t) or re.search(r'\b(APPT|ETG|ETAGE|RDC)\b', t):
        return 'adresse'                                # « APPART 0121 RUE SEBOU RDC RABAT RC 57899 »
    mots = mots_societe(t)
    if not mots:
        return 'forme_seule'
    if all(m in GENERIQUES_RS or m in _VAR_VILLE for m in mots):
        return 'generique'
    if re.search(r'\d', t) and len(set(t.split()) & MOTS_ADRESSE) >= 2:
        return 'adresse'
    return 'valide'


def nom_exact(mots):
    """Nom écrit à l'identique, insensible aux espaces et à l'inversion « لا » / « ال » des PDF (alifs retirés)."""
    sortie = []
    for m in mots:
        if est_arabe(m):
            sortie.append(ar_simple(m).replace('ا', '').replace('ء', ''))
        else:
            sortie.append(PRENOMS_CANON.get(m, m))
    k = ''.join(sortie)
    return k if len(k) >= 4 else None


def role_dirigeant(libelle):
    t = latin_maj(libelle)
    if 'GERANT' in t:
        return 'gerant'
    if any(x in t for x in ('ADMINISTRATEUR', 'PRESIDENT', 'DIRECTEUR')):
        return 'administrateur'
    return 'gerant'


def mots_nom_nettoyes(texte):
    """Mots du nom : civilités retirées (on garde ce qui suit la dernière), coupe au rôle, à la pièce d'identité…"""
    mots = latin_maj(texte).split()
    dernier = max((k for k, m in enumerate(mots) if m in HONORIFIQUES), default=-1)
    mots = mots[dernier + 1:]
    sortie = []
    for k, m in enumerate(mots):
        for civ in CIVILITES_COLLEES:                       # « السيدةرقية »
            if m.startswith(civ) and len(m) > len(civ) + 1:
                m = m[len(civ):]
                break
        if m in COUPE_NOMS:
            break
        colle = next((c for c in COUPE_COLLES if c in m), None)
        if colle:
            debut = m[:m.index(colle)]
            if len(debut) > 1:
                sortie.append(debut)
            break
        sortie.append(m)
    return [m for m in sortie if len(m) > 1]


def motif_rejet_nom(mots):
    if not mots:
        return 'vide'
    if any(re.search(r'\d', m) for m in mots):
        return 'chiffres'
    if any(m in STOP_NOMS for m in mots):
        return 'phrase_juridique'
    if len(mots) == 1:
        return 'mot_unique'
    if len(mots) > 6:
        return 'trop_long'
    if sum(len(m) for m in mots) < 5:
        return 'trop_court'
    return None


def analyser_entree(brut, champ, role_defaut):
    """Une entrée d'un champ personnes → personne, société associée, ou rejet motivé."""
    texte, role_texte = brut.strip(), None
    if ' — ' in texte:
        texte, role_texte = texte.rsplit(' — ', 1)
    if champ == 'dirigeants':
        role = role_dirigeant(role_texte)
    else:
        role = role_defaut or role_normalise(role_texte)
    parenth = re.findall(r'\(([^)]*)\)', texte)
    societe = any('SOCIETE' in latin_maj(p) for p in parenth)
    parts = pct = None
    for p in parenth:
        m = re.search(r'(\d[\d\s.,]*)\s*parts', p)
        if m:
            parts = re.sub(r'\D', '', m.group(1)) or None
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*%', p)
        if m:
            pct = float(m.group(1).replace(',', '.'))
    texte = re.sub(r'\([^)]*\)', ' ', texte)
    e = dict(champ=champ, role=role, role_texte=role_texte, texte_brut=brut.strip()[:300], parts=parts, pct=pct,
             type='PP', mots=None, nom=None, rejet=None, cin=None)
    brut_maj = set(latin_maj(texte).split())
    if societe or (brut_maj & MARQUES_PM):
        rs = cle_rs(texte)
        if rs and statut_denomination(texte) == 'valide':
            e.update(type='PM', nom=' '.join(latin_maj(texte).split()), rs=rs, sq=squelette_rs(texte))
        else:
            e['rejet'] = 'societe_illisible'
        return e
    mots = mots_nom_nettoyes(texte)
    e['rejet'] = motif_rejet_nom(mots)
    e['mots'], e['nom'] = mots, ' '.join(mots)
    return e


def cins_dans_texte(texte):
    """CIN cités avec leur libellé (« titulaire de la CIN n° … », « البطاقة الوطنية رقم … ») et le nom qui précède."""
    t = latin_maj(texte)
    trouves = []
    for m in CIN_TEXTE_RE.finditer(t):
        cin, statut = normalise_cin(m.group(2) + m.group(3))
        if statut not in ('valide', 'lettre_finale'):
            continue
        avant = t[max(0, m.start() - 160):m.start()].split()
        civ = max((k for k, x in enumerate(avant) if x in HONORIFIQUES), default=None)
        mots = mots_nom_nettoyes(' '.join(avant[civ:civ + 6])) if civ is not None else []
        trouves.append((cin, mots if not motif_rejet_nom(mots) else None))
    return trouves


ROLES_KAMAL = {'GERANT': 'gerant', 'CO GERANT': 'gerant', 'COGERANT': 'gerant', 'ASSOCIE': 'associe',
               'CEDANT': 'cedant', 'CESSIONNAIRE': 'cessionnaire', 'LIQUIDATEUR': 'liquidateur',
               'ADMINISTRATEUR': 'administrateur', 'PRESIDENT': 'administrateur', 'REPRESENTANT': 'representant'}
SORTIES_KAMAL = {'gerant': 'gerant_sortant', 'associe': 'associe_sortant', 'administrateur': 'gerant_sortant'}
CHAMP_PAR_ROLE = {'gerant': 'dirigeants', 'administrateur': 'dirigeants', 'gerant_sortant': 'dirigeants_sortants',
                  'associe': 'associes', 'associe_sortant': 'associes_sortants', 'cedant': 'cedants',
                  'cessionnaire': 'cessionnaires', 'liquidateur': 'liquidateurs', 'representant': 'representants',
                  'inconnu': 'texte'}


def entrees_personnes_kamal(lignes):
    """Lignes du fichier « personnes » de Kamal (26/10/2026) pour une annonce → entrées au format commun :
    une entrée par rôle (« Associé, Gérant » en donne deux), CIN, parts et pourcentage repris tels quels."""
    sortie = []
    for p in lignes:
        roles = [ROLES_KAMAL.get(latin_maj(x), 'inconnu') for x in (p.get('roles') or '').split(',') if x.strip()]
        roles = list(dict.fromkeys(roles)) or ['inconnu']
        if p.get('mouvement') == 'sortie':
            roles = [SORTIES_KAMAL.get(r, r) for r in roles]
        parts = re.sub(r'\D', '', p.get('parts') or '') or None
        try:
            pct = float((p.get('pourcentage') or '').replace(',', '.')) if p.get('pourcentage') else None
        except ValueError:
            pct = None
        cin = (p.get('cin') or '').strip() or None
        nom = p.get('nom') or ''
        for role in roles:
            champ = CHAMP_PAR_ROLE.get(role, 'texte')
            e = analyser_entree(nom, 'personnes', role)
            e.update(champ=champ, role=role, role_texte=p.get('roles') or None, cin=cin,
                     texte_brut=(nom + (' — ' + p['roles'] if p.get('roles') else '')
                                 + (f" ({parts or '?'} parts, {pct:g} %)" if pct is not None else ''))[:300])
            if parts:
                e['parts'] = parts
            if pct is not None:
                e['pct'] = pct
            if p.get('personne_morale') == 'oui' and e['type'] != 'PM' and not e['rejet']:
                rs = cle_rs(nom)
                if rs:
                    e.update(type='PM', nom=' '.join(latin_maj(nom).split()), rs=rs, sq=squelette_rs(nom), mots=None)
                else:
                    e['rejet'] = 'societe_illisible'
            sortie.append(e)
    return sortie


def lire_export_kamal(chemin, chemin_personnes=None):
    """Annonces de l'export de Kamal, normalisées au format commun. Avec le fichier « personnes » (export du
    26/10/2026), les personnes citées, leurs rôles, leurs parts et leurs CIN viennent de ce fichier ; sans lui, elles
    sont lues dans les colonnes de texte de l'annonce."""
    csv.field_size_limit(10 ** 9)
    par_annonce = {}
    if chemin_personnes:
        with open(chemin_personnes, encoding='utf-8-sig', newline='') as f:
            for p in csv.DictReader(f, delimiter=';'):
                par_annonce.setdefault(p.get('identifiant_source'), []).append(
                    {k: (v.strip() if isinstance(v, str) else v) for k, v in p.items()})
        print(f'    fichier personnes : {sum(len(v) for v in par_annonce.values())} lignes, '
              f'{len(par_annonce)} annonces', flush=True)
    with open(chemin, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            source = SOURCES_KAMAL.get(latin_maj(r.get('source')), latin_maj(r.get('source')).lower())
            lignes_p = par_annonce.get(r.get('identifiant_source'))
            cins = []
            if lignes_p:
                personnes = entrees_personnes_kamal(lignes_p)
            else:
                personnes = []
                for champ, role_defaut in CHAMPS_PERSONNES:
                    for brut in (r.get(champ) or '').split(' | '):
                        if brut.strip():
                            personnes.append(analyser_entree(brut, champ, role_defaut))
                for c in (r.get('cin') or '').split('|'):          # CIN cités, sans personne rattachée
                    c = c.strip()
                    if c:
                        cins.append((c, None))
            for c in ('objet', 'siege', 'titre', 'denomination') + tuple(ch for ch, _ in CHAMPS_PERSONNES):
                if r.get(c) and re.search(r'CIN|CNIE|بطاقة|NATIONALE', r[c], re.I):
                    cins += cins_dans_texte(r[c])
            yield dict(
                annonce_id=f"{source}:{r.get('identifiant_source')}", source=source, type_acte=r.get('type'),
                date_publication=date_iso(r.get('date_publication')), numero_publication=r.get('numero_bo') or None,
                url=r.get('url') or None, denomination=repare(r.get('denomination')),
                forme_juridique=r.get('forme_juridique') or None, rc=r.get('rc') or None,
                tribunal=r.get('tribunal') or None, ice=r.get('ice') or None, if_brut=r.get('identifiant_fiscal') or None,
                capital=r.get('capital_dh') or None, siege=repare(r.get('siege')), ville=r.get('ville') or None,
                objet=repare(r.get('objet')), date_acte=date_iso(r.get('date_acte')),
                date_depot=date_iso(r.get('date_depot')), numero_depot=r.get('numero_depot') or None,
                nouvelle_denomination=repare(r.get('nouvelle_denomination')),
                nouveau_siege=repare(r.get('nouveau_siege')), nouveau_capital=r.get('nouveau_capital_dh') or None,
                nouvelle_forme=r.get('nouvelle_forme') or None, total_parts=r.get('total_parts') or None,
                lecture_complete=1 if r.get('lecture_complete') == 'oui' else 0,
                information_absente=1 if r.get('information_absente_du_texte') == 'oui' else 0,
                bloc_mixte=1 if r.get('plusieurs_annonces_dans_le_bloc') == 'oui' else 0,
                titre=repare(r.get('titre')), personnes=personnes, cins=cins)


def lire_modele(annonces_brutes, personnes_brutes):
    """Modèle générique (rc_annonces + rc_personnes, ou JSON à personnes imbriquées), au même format commun."""
    par_annonce = defaultdict(list)
    for p in personnes_brutes:
        q = renommer(p, ALIAS_PERSONNE)
        if q.get('annonce_id') is not None:
            par_annonce[str(repare(q['annonce_id']))].append(q)
    for k, brute in enumerate(annonces_brutes, start=1):
        a = {c: repare(v) for c, v in renommer(brute, ALIAS_ANNONCE).items()}
        aid = a.get('annonce_id') or f'L{k}'
        personnes = []
        for q in (par_annonce.get(str(aid)) or personnes_imbriquees(brute)):
            q = {c: repare(v) for c, v in q.items()}
            texte = q.get('nom_complet') or ' '.join(x for x in (q.get('prenom'), q.get('nom')) if x) or ''
            e = analyser_entree(texte, 'modele', role_normalise(q.get('role'))) if texte else dict(
                champ='modele', role=role_normalise(q.get('role')), role_texte=None, texte_brut='', parts=None,
                pct=None, type='PP', mots=None, nom=None, rejet='vide', cin=None)
            e['role_texte'] = q.get('role')
            e['parts'] = q.get('parts') or e.get('parts')
            cin, statut = normalise_cin(q.get('cin'))
            e['cin'] = cin if statut in ('valide', 'lettre_finale') else None
            e['date_naissance'] = date_iso(q.get('date_naissance'))
            e['nationalite'], e['adresse'] = q.get('nationalite'), q.get('adresse')
            if e['rejet'] == 'vide' and e['cin']:
                e['rejet'] = None                                   # CIN sans nom : gardé
            personnes.append(e)
        cins = []
        brut_cin = brute.get('cin') if isinstance(brute, dict) else None
        valeurs = brut_cin if isinstance(brut_cin, list) else re.split(r'[;,/|]', a.get('cin') or '')
        for v in valeurs:
            cin, statut = normalise_cin(v)
            if statut in ('valide', 'lettre_finale'):
                cins.append((cin, None))
        yield dict(
            annonce_id=str(aid), source=a.get('source'), type_acte=a.get('type_acte'),
            date_publication=date_iso(a.get('date_publication')) or a.get('date_publication'),
            numero_publication=a.get('numero_publication'), url=a.get('url'), denomination=a.get('denomination'),
            forme_juridique=None, rc=a.get('rc'), tribunal=a.get('tribunal'), ice=a.get('ice'), if_brut=None,
            capital=a.get('capital'), siege=a.get('siege'), ville=None, objet=a.get('objet'),
            date_acte=date_iso(a.get('date_acte')) or a.get('date_acte'), date_depot=None, numero_depot=a.get('depot'),
            nouvelle_denomination=a.get('nouvelle_denomination'), nouveau_siege=a.get('nouveau_siege'),
            nouveau_capital=a.get('nouveau_capital'), nouvelle_forme=None, total_parts=None,
            lecture_complete=1 if str(a.get('complet')).lower() in ('1', 'true', 'vrai', 'oui', '1.0') else 0,
            information_absente=0, bloc_mixte=0, titre=None, personnes=personnes, cins=cins)


# ---- registre du commerce : assemblage -----------------------------------------------
def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def forme_nom(texte):
    """(clé raison sociale, squelette, mots) d'une dénomination, pour comparer deux noms de société."""
    t = nettoyer_denomination(texte)
    return cle_rs(t), squelette_rs(t), frozenset(mots_societe(t))


def _mots_distinctifs(mots):
    return {m for m in mots if len(m) >= 3 and m not in GENERIQUES_RS and m not in _VAR_VILLE}


def similarite_noms(liste_a, liste_b, souple=False):
    """Similarité de 0 à 1 entre deux séries de noms de société (latin ou arabe).
    souple : comparaison sous un même RC et un même tribunal ; les mots courts et les noms de ville ou de
    quartier ajoutés à la dénomination (« STE ON BRAND BEAUTY AGDAL RABAT ») ne séparent plus deux graphies."""
    meilleure = 0.0
    for ra, sa, ta in liste_a:
        for rb, sb, tb in liste_b:
            s = 0.0
            if ra and rb:
                s = _ratio(ra, rb)
                commun = {m for m in ta & tb if len(m) >= 3 and m not in GENERIQUES_RS and m not in _VAR_VILLE}
                if commun and (commun == ta - GENERIQUES_RS or commun == tb - GENERIQUES_RS):
                    s = max(s, 0.9)
                elif (souple and commun and (commun == _mots_distinctifs(ta) or commun == _mots_distinctifs(tb))
                      and (len(commun) >= 2 or max(map(len, commun)) >= 5)):
                    s = max(s, 0.85)
                elif commun:
                    s = max(s, 0.8 * len(commun) / max(1, min(len(ta), len(tb))))
            if sa and sb and (est_arabe(' '.join(ta)) != est_arabe(' '.join(tb))):
                s = max(s, _ratio(sa, sb))
                court, long_ = sorted((sa, sb), key=len)
                if len(court) >= 5 and court in long_ and len(court) / len(long_) >= 0.75:
                    s = max(s, 0.85)
            meilleure = max(meilleure, s)
            if meilleure >= 0.99:
                return meilleure
    return meilleure


def grouper_noms(noms, liens=()):
    """noms : [(forme, nombre d'annonces)] par fréquence décroissante → groupes de noms compatibles (≥ 0,6).
    liens : paires (ancien nom, nouveau nom) d'un changement de dénomination publié sous ce RC ; les deux noms
    restent dans le même groupe, même s'ils n'ont rien de commun."""
    groupes = []
    for forme, n in noms:
        for g in groupes:
            if similarite_noms([forme], g[0], souple=True) >= 0.6:
                g[0].append(forme)
                g[1] += n
                break
        else:
            groupes.append([[forme], n])
    if liens and len(groupes) > 1:
        parent = list(range(len(groupes)))

        def racine(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        indice = {f: i for i, (formes, _) in enumerate(groupes) for f in formes}
        for a, b in liens:
            if a in indice and b in indice:
                ra, rb = racine(indice[a]), racine(indice[b])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
        fusion = {}
        for i, (formes, n) in enumerate(groupes):
            g = fusion.setdefault(racine(i), [[], 0])
            g[0].extend(formes)
            g[1] += n
        groupes = sorted(fusion.values(), key=lambda g: -g[1])
    return groupes


def assembler_rc(con, annonces_iter):
    t0 = time.time()
    annonces = []
    for a in annonces_iter:
        rc_num, indice, statut = normalise_rc(a['rc'])
        if statut == 'rc':
            annees = {x[:4] for x in (a['date_acte'], a['date_publication'], a['date_depot']) if x}
            depot = re.sub(r'\D', '', a['numero_depot'] or '')
            if depot and depot.lstrip('0') == rc_num:
                statut = 'suspect_depot'
            elif rc_num in annees:
                statut = 'suspect_annee'
            elif len(rc_num) > 8:
                statut = 'suspect_long'
            elif len(rc_num) <= 2:                  # « RC 21 » : morceau mal lu, porté par des dizaines de sociétés
                statut = 'suspect_court'
            else:
                statut = 'valide'
        a['rc_statut'] = statut
        a['rc_num'] = rc_num if statut == 'valide' else None
        a['tribunal_code'] = tribunal_code(a['tribunal'])[0] or indice
        a['ville_code'] = (tribunal_code(a['ville'])[0] if a['ville'] else None) or villes_dans(a['siege'])
        a['denomination_statut'] = statut_denomination(a['denomination'])
        a['forme'] = forme_nom(a['denomination']) if a['denomination_statut'] == 'valide' else None
        a['nouvelle_forme_nom'] = (forme_nom(a['nouvelle_denomination'])
                                   if statut_denomination(a['nouvelle_denomination']) == 'valide' else None)
        ice = re.sub(r'\D', '', a['ice'] or '')
        a['ice_norm'] = ice if len(ice) == 15 else None
        if_num = re.sub(r'\D', '', a['if_brut'] or '')
        a['if_num'] = if_num if 6 <= len(if_num) <= 9 else None
        a['fiabilite'] = 0.5 if a['bloc_mixte'] else 1.0
        annonces.append(a)
    print(f'    {len(annonces)} annonces lues ({time.time() - t0:.0f} s)', flush=True)

    # dénomination portée par au moins 3 couples RC + tribunal différents : fiduciaire ou nom générique
    porteurs = defaultdict(set)
    for a in annonces:
        if a['forme'] and a['rc_num']:
            porteurs[a['forme'][0]].add((a['rc_num'], a['tribunal_code']))
    ambigues = {rs for rs, s in porteurs.items() if len(s) >= 3}
    for a in annonces:
        if a['forme'] and a['forme'][0] in ambigues:
            a['denomination_statut'], a['forme'] = 'ambigue', None

    # sociétés : RC + tribunal, puis séparation des noms incompatibles sous un même RC
    groupes = defaultdict(list)
    for k, a in enumerate(annonces):
        if a['rc_num'] and a['tribunal_code']:
            groupes[('RC', a['rc_num'], a['tribunal_code'])].append(k)
        elif a['rc_num']:
            groupes[('RCX', a['rc_num'], a['forme'][0] if a['forme'] else '')].append(k)
        elif a['forme']:
            groupes[('RS', a['forme'][0])].append(k)
        else:
            groupes[('ANN', a['annonce_id'])].append(k)
    cle_annonce, conflits = {}, set()
    for g, ks in groupes.items():
        if g[0] == 'RC':
            base = f'RC:{g[1]}@{g[2]}'
            compte, liens = Counter(), []
            for k in ks:
                a = annonces[k]
                if a['forme']:
                    compte[a['forme']] += 1
                if a['nouvelle_forme_nom']:                 # nouveau nom : présent dans le groupe, sans annonce à lui
                    compte[a['nouvelle_forme_nom']] += 0
                    if a['forme']:
                        liens.append((a['forme'], a['nouvelle_forme_nom']))
            grp = grouper_noms(sorted(compte.items(), key=lambda x: -x[1]), liens) if len(compte) > 1 else []
            grp = [g_ for g_ in grp if g_[1] > 0]                 # groupe fait d'un seul « nouveau nom » : pas une société
            if len(grp) >= 3:
                # trois noms incompatibles ou plus sous un même RC : le numéro est mal lu, il n'identifie rien ;
                # chaque annonce est rattachée à son nom, comme une annonce sans RC
                for k in ks:
                    a = annonces[k]
                    a['rc_statut'], a['rc_num'] = 'suspect_partage', None
                    cle_annonce[k] = f"RS:{a['forme'][0]}" if a['forme'] else f"ANN:{a['annonce_id']}"
            elif len(grp) > 1:
                indice_forme = {f: i for i, (formes, _) in enumerate(grp) for f in formes}
                for k in ks:
                    i = indice_forme.get(annonces[k]['forme'])
                    if i is None:                       # annonce sans nom lisible sous un RC partagé : on ne devine pas
                        cle_annonce[k] = f"{base}#?{annonces[k]['annonce_id']}"
                    else:
                        cle_annonce[k] = base if i == 0 else f'{base}#{i + 1}'
                    conflits.add(cle_annonce[k])
            else:
                for k in ks:
                    cle_annonce[k] = base
        elif g[0] == 'RCX':
            for k in ks:
                cle_annonce[k] = f'RC:{g[1]}@?:{g[2]}'
        elif g[0] == 'RS':
            for k in ks:
                cle_annonce[k] = f'RS:{g[1]}'
        else:
            for k in ks:
                cle_annonce[k] = f'ANN:{g[1]}'
    # « RC sans tribunal » ou « nom sans RC » rattachés à la seule société connue qui leur correspond
    par_rc_rs, par_rs = defaultdict(set), defaultdict(set)
    for k, a in enumerate(annonces):
        c = cle_annonce[k]
        if c.startswith('RC:') and '@?' not in c and a['forme']:
            par_rc_rs[(a['rc_num'], a['forme'][0])].add(c)
            par_rs[a['forme'][0]].add(c)
    for k, a in enumerate(annonces):
        c = cle_annonce[k]
        if '@?:' in c and a['forme']:
            cands = par_rc_rs.get((a['rc_num'], a['forme'][0]), set())
        elif c.startswith('RS:'):
            cands = par_rs.get(c[3:], set())
        else:
            continue
        if len(cands) == 1:
            cle_annonce[k] = next(iter(cands))

    # agrégats par société
    soc = {}
    for k, a in enumerate(annonces):
        c = cle_annonce[k]
        s = soc.setdefault(c, dict(rc=None, trib=None, noms=Counter(), noms_date={}, sieges=[], villes=set(),
                                   capitaux=[], dates=[], types=Counter(), ice=set(), ifs=set(), formes=Counter(),
                                   fiab=0.0, inter=Counter(), nb=0, cles_rs=set(), noms_secours=Counter()))
        s['nb'] += 1
        if a['denomination'] and a['denomination_statut'] == 'ambigue':
            s['noms_secours'][a['denomination']] += 1     # nom réel mais partagé : affiché faute de mieux
        s['rc'] = s['rc'] or a['rc_num']
        s['trib'] = s['trib'] or a['tribunal_code']
        s['fiab'] = max(s['fiab'], a['fiabilite'])
        for d, forme in ((a['denomination'], a['forme']), (a['nouvelle_denomination'], a['nouvelle_forme_nom'])):
            if forme:
                s['noms'][d] += 1
                s['noms_date'][d] = max(s['noms_date'].get(d, ''), a['date_publication'] or '')
                s['cles_rs'].add(d)
        for x in (a['nouveau_siege'], a['siege']):
            if x:
                s['sieges'].append((a['date_publication'] or '', x))
                break
        for v in (a['ville_code'], villes_dans(a['nouveau_siege']) if a['nouveau_siege'] else None, a['tribunal_code']):
            if v:
                s['villes'].add(v)
        cap = a['nouveau_capital'] or a['capital']
        if cap:
            s['capitaux'].append((a['date_publication'] or '', cap))
        if a['date_publication']:
            s['dates'].append(a['date_publication'])
        if a['type_acte']:
            s['types'][a['type_acte']] += 1
        if a['ice_norm']:
            s['ice'].add(a['ice_norm'])
        if a['if_num']:
            s['ifs'].add(a['if_num'])
        if a['nouvelle_forme'] or a['forme_juridique']:
            s['formes'][a['nouvelle_forme'] or a['forme_juridique']] += 1
        if a['titre'] and a['forme'] and forme_nom(a['titre'])[0] != a['forme'][0]:
            s['inter'][a['titre']] += 1

    ids_soc = {c: i for i, c in enumerate(sorted(soc), start=1)}
    alpha = con.execute("SELECT valeur FROM parametre WHERE nom = 'alpha_rarete'").fetchone()[0]
    cles = []

    def cle(objet, oid, type_cle, role, valeur, sid):
        if valeur:
            cles.append(('RC', objet, oid, type_cle, role, valeur, sid))

    # ---- personnes : une ligne par personne et par société, mentions détaillées à part ----
    personnes, mentions, rejets = {}, [], []
    for k, a in enumerate(annonces):
        c = cle_annonce[k]
        sid = ids_soc[c]
        valides = []
        for e in a['personnes']:
            if e['rejet']:
                rejets.append((a['annonce_id'], e['champ'], e['texte_brut'], e['rejet']))
                continue
            valides.append(e)
        # page du Bulletin officiel lue comme une seule annonce (en-tête du tribunal, dizaines de personnes sans
        # rapport) : aucune de ces personnes ne peut être rattachée à une société
        nb_pp = sum(1 for e in valides if e['type'] == 'PP')
        if nb_pp >= 30 or (a['denomination_statut'] != 'valide' and nb_pp >= 8):
            for e in valides:
                rejets.append((a['annonce_id'], e['champ'], e['texte_brut'], 'page_fusionnee'))
            valides, a['cins'] = [], []
        # CIN cités dans le texte : rattachés au nom qui les précède, sinon à la seule personne sans CIN ;
        # un même nom suivi de deux CIN différents est ambigu : aucun des deux n'est rattaché à ce nom
        noms_cin = defaultdict(set)
        for cin, mots in a['cins']:
            if mots:
                noms_cin[' '.join(mots)].add(cin)
        vus, cins = set(), []
        for cin, mots in a['cins']:
            if mots and len(noms_cin[' '.join(mots)]) > 1:
                mots = None
            cle_c = (cin, ' '.join(mots) if mots else None)
            if cle_c not in vus:
                vus.add(cle_c)
                cins.append((cin, mots))
        a['cins'] = cins
        for cin, mots in a['cins']:
            cible = None
            if mots:
                cle_n = nom_exact(mots)
                cible = next((e for e in valides if e['type'] == 'PP' and e['mots'] and nom_exact(e['mots']) == cle_n), None)
                if not cible:
                    sq = squelettes_nom(' '.join(mots))
                    cible = next((e for e in valides if e['type'] == 'PP' and e['mots']
                                  and sq & squelettes_nom(' '.join(e['mots']))), None)
            if not cible:
                sans = [e for e in valides if e['type'] == 'PP' and not e['cin']]
                if len(sans) == 1 and len(a['cins']) == 1:
                    cible = sans[0]
            if cible and not cible['cin']:
                cible['cin'] = cin
            elif not any(e['cin'] == cin for e in valides):
                valides.append(dict(champ='texte', role='inconnu', role_texte=None, texte_brut='', parts=None,
                                    pct=None, type='PP', mots=mots, nom=' '.join(mots) if mots else None,
                                    rejet=None, cin=cin))
        for e in valides:
            if e['type'] == 'PM':
                ident = 'S:' + e['rs']
            elif e['mots']:
                ident = 'N:' + (nom_exact(e['mots']) or e['nom'])
            else:
                ident = 'CIN:' + e['cin']
            cs = f'{c}|{ident}'
            p = personnes.get(cs)
            if p is None:
                p = personnes[cs] = dict(cle_stable=cs, societe_id=sid, type=e['type'], noms=Counter(), mots=e['mots'],
                                         rs=e.get('rs'), sq=e.get('sq'), cin=None, roles=Counter(), poids=0.0,
                                         parts=None, pct=None, sortant=True, fiab=0.0, nb=0, dates=[],
                                         date_naissance=e.get('date_naissance'), nationalite=e.get('nationalite'),
                                         adresse=e.get('adresse'))
            p['noms'][e['nom']] += 1
            p['cin'] = p['cin'] or e['cin']
            p['roles'][e['role']] += 1
            poids = next(r[3] for r in ROLES if r[0] == e['role'])
            if e['role'] == 'associe' and e['pct'] is not None:
                poids = 0.3 + 0.4 * min(e['pct'], 100) / 100
            p['poids'] = max(p['poids'], poids)
            if e['parts']:
                p['parts'] = e['parts']
            if e['pct'] is not None:
                p['pct'] = e['pct']
            p['sortant'] = p['sortant'] and e['role'] in ('gerant_sortant', 'associe_sortant', 'cedant')
            p['fiab'] = max(p['fiab'], a['fiabilite'])
            p['nb'] += 1
            if a['date_publication']:
                p['dates'].append(a['date_publication'])
            mentions.append((cs, a['annonce_id'], e['champ'], e['role'], e['role_texte'], e['texte_brut'],
                             e['parts'], e['pct']))
    print(f'    {len(personnes)} personnes distinctes par société, {len(mentions)} mentions, '
          f'{len(rejets)} entrées écartées ({time.time() - t0:.0f} s)', flush=True)

    # ---- sociétés ----
    nb_pers = Counter(p['societe_id'] for p in personnes.values())
    lignes_soc = []
    for c, s in soc.items():
        sid = ids_soc[c]
        noms = sorted(s['noms'].items(), key=lambda x: (est_arabe(x[0]), -x[1], x[0]))
        affiche = nom_affichage(noms[0][0] if noms else
                                (s['noms_secours'].most_common(1)[0][0] if s['noms_secours'] else None))
        sieges = [x for _, x in sorted(s['sieges'])]
        dates = sorted(s['dates'])
        n = nb_pers.get(sid, 0)
        lignes_soc.append((sid, c, affiche, ' | '.join(d for d, _ in noms[1:6]) or None, s['rc'], s['trib'],
                           (villes_dans(sieges[-1]) if sieges else None) or (sorted(s['villes'])[0] if s['villes'] else None),
                           sieges[-1] if sieges else None, sorted(s['capitaux'])[-1][1] if s['capitaux'] else None,
                           dates[0] if dates else None, dates[-1] if dates else None, s['nb'],
                           ' ; '.join(f'{t} ({x})' for t, x in s['types'].most_common()),
                           int(any(t in ('Dissolution', 'Clôture de liquidation') for t in s['types'])),
                           n, float(max(n, 1)) ** -alpha, ' | '.join(sorted(s['ice'])) or None,
                           ' | '.join(sorted(s['ifs'])) or None,
                           s['formes'].most_common(1)[0][0] if s['formes'] else None, int(c in conflits),
                           s['fiab'], ' | '.join(t for t, _ in s['inter'].most_common(3)) or None))
        if s['rc']:
            cle('rc_societe', sid, 'RC_NUM', 'identite', s['rc'], sid)
            if s['trib']:
                cle('rc_societe', sid, 'RC_TRIB', 'identite', f"{s['rc']}@{s['trib']}", sid)
        for x in s['ice']:
            cle('rc_societe', sid, 'ICE', 'identite', x, sid)
        for x in s['ifs']:
            cle('rc_societe', sid, 'IF', 'identite', x, sid)
        for d in s['cles_rs']:
            rs, sq, _ = forme_nom(d)
            cle('rc_societe', sid, 'RS', 'identite', rs, sid)
            if est_arabe(d):                         # le squelette ne sert qu'à passer de l'arabe au latin
                cle('rc_societe', sid, 'RS_SQ', 'identite', sq, sid)
        for v in s['villes']:
            cle('rc_societe', sid, 'VILLE', 'siege', v, sid)
        for x in set(sieges):
            if not est_arabe(x):
                cle('rc_societe', sid, 'ADR', 'siege', cle_adresse(x), sid)
    con.executemany('INSERT INTO rc_societe VALUES (' + ','.join('?' * 22) + ')', lignes_soc)

    champs_a = ['annonce_id', 'societe_id', 'source', 'type_acte', 'date_publication', 'numero_publication', 'url',
                'denomination', 'denomination_statut', 'forme_juridique', 'rc', 'rc_statut', 'tribunal', 'ice',
                'if_brut', 'capital', 'siege', 'ville', 'objet', 'date_acte', 'date_depot', 'numero_depot',
                'nouvelle_denomination', 'nouveau_siege', 'nouveau_capital', 'nouvelle_forme', 'total_parts',
                'lecture_complete', 'information_absente', 'bloc_mixte', 'titre', 'fiabilite', 'rc_num',
                'tribunal_code', 'ville_code']
    for k, a in enumerate(annonces):
        a['societe_id'] = ids_soc[cle_annonce[k]]
    con.executemany(f"INSERT OR REPLACE INTO rc_annonce ({','.join(champs_a)}) VALUES ({','.join('?' * len(champs_a))})",
                    [tuple(a[c] for c in champs_a) for a in annonces])

    lignes_p, ids_p = [], {}
    for pid, (cs, p) in enumerate(sorted(personnes.items()), start=1):
        ids_p[cs] = pid
        sid = p['societe_id']
        nom = p['noms'].most_common(1)[0][0] if p['noms'] else None
        role = max(p['roles'], key=lambda r: (next(x[3] for x in ROLES if x[0] == r), p['roles'][r]))
        cin_norm, cin_statut = normalise_cin(p['cin'])
        dates = sorted(p['dates'])
        lignes_p.append((pid, cs, sid, p['type'], nom, 'arabe' if est_arabe(nom) else 'latin',
                         nom_exact(p['mots']) if p['mots'] else None, p['cin'],
                         cin_norm if cin_statut in ('valide', 'lettre_finale') else None, cin_statut, role,
                         ', '.join(r for r, _ in p['roles'].most_common()), p['poids'], p['parts'], p['pct'],
                         int(p['sortant']), p['fiab'], p['nb'], dates[0] if dates else None,
                         dates[-1] if dates else None, None, p['date_naissance'], p['nationalite'], p['adresse']))
        if p['type'] == 'PP':
            if cin_norm and cin_statut in ('valide', 'lettre_finale'):
                cle('rc_personne', pid, 'CIN', 'personne', cin_norm, sid)
            if p['mots']:
                texte = ' '.join(p['mots'])
                cle('rc_personne', pid, 'NOM', 'personne', cle_nom(texte), sid)
                for v in squelettes_nom(texte):
                    cle('rc_personne', pid, 'NOM_SQ', 'personne', v, sid)
            cle('rc_personne', pid, 'DATE_NAISS', 'personne', p['date_naissance'], sid)
    con.executemany('INSERT INTO rc_personne VALUES (' + ','.join('?' * 24) + ')', lignes_p)
    con.executemany('INSERT INTO rc_mention (personne_id, annonce_id, champ, role, role_texte, texte_brut, parts, pct) '
                    'VALUES (?,?,?,?,?,?,?,?)', [(ids_p[m[0]],) + m[1:] for m in mentions])
    con.executemany('INSERT INTO rc_rejet (annonce_id, champ, texte_brut, motif) VALUES (?,?,?,?)', rejets)

    # associé « société » : rattaché à la société du registre qui porte ce nom, si elle est unique
    sq_soc = defaultdict(set)
    for c, s in soc.items():
        for d in s['cles_rs']:
            sq_soc[forme_nom(d)[0]].add(ids_soc[c])
    participations = []
    for cs, p in personnes.items():
        if p['type'] == 'PM' and p['rs']:
            cands = sq_soc.get(p['rs'], set()) - {p['societe_id']}
            if len(cands) == 1:
                participations.append((ids_p[cs], next(iter(cands))))
    con.executemany('INSERT INTO rc_participation (personne_id, societe_id) VALUES (?,?)', participations)

    con.executemany('INSERT OR IGNORE INTO cle (cote, objet, objet_id, type_cle, role, valeur, societe_id) '
                    'VALUES (?,?,?,?,?,?,?)', cles)
    print(f'    {len(lignes_soc)} sociétés, {len(cles)} clés, {len(participations)} participations '
          f'({time.time() - t0:.0f} s)', flush=True)
    return {'annonces': len(annonces), 'societes': len(lignes_soc), 'personnes': len(lignes_p),
            'mentions': len(mentions), 'rejets': len(rejets), 'cles': len(cles)}


# ---- comparaisons préparées en Python (similarité des raisons sociales, rareté, homonymes) ----
def calculer_similarites(con):
    """Pour chaque société inscrite qui partage un numéro RC avec une société du registre : similarité des noms,
    tribunaux, fiabilité, et règle proposée (R02, R02n, R03, R03t)."""
    con.execute('DELETE FROM similarite_societe')
    noms_bl = defaultdict(list)
    for eid, a, b in con.execute("SELECT entite_id, nom_ras, nom FROM bl_inscription"):
        for x in (a, b):
            if x:
                noms_bl[eid].append((x, forme_nom(x)))
    paires = con.execute("""SELECT DISTINCT b.objet_id, r.objet_id FROM cle b
        JOIN cle r ON r.cote = 'RC' AND r.objet = 'rc_societe' AND r.type_cle = 'RC_NUM' AND r.valeur = b.valeur
        WHERE b.cote = 'BL' AND b.type_cle = 'RC_NUM'""").fetchall()
    ids = {s for _, s in paires}
    noms_rc, info = defaultdict(list), {}
    if ids:
        for sid, d in con.execute(f"""SELECT societe_id, denomination FROM rc_annonce
                WHERE denomination_statut IN ('valide', 'ambigue') AND societe_id IN ({','.join(map(str, ids))})"""):
            if all(d != x for x, _ in noms_rc[sid]):
                noms_rc[sid].append((d, forme_nom(d)))
        for sid, trib, fiab, conflit, den in con.execute(
                f"SELECT societe_id, tribunal_code, fiabilite, rc_conflit, denomination FROM rc_societe "
                f"WHERE societe_id IN ({','.join(map(str, ids))})"):
            info[sid] = (trib, fiab, conflit, den)
    trib_bl = dict(con.execute('SELECT entite_id, tribunal_code FROM bl_entite'))
    lignes = []
    for eid, sid in paires:
        tb, (tr, fiab, conflit, den) = trib_bl.get(eid), info[sid]
        a = [f for _, f in noms_bl.get(eid, []) if f[0]]
        b = [f for _, f in noms_rc.get(sid, []) if f[0]]
        sim = similarite_noms(a, b) if a and b else None
        regle = niveau = None
        poids = None
        if tb and tr and tb == tr:
            if (sim is None or sim >= 0.6) and fiab >= 1:
                regle, niveau, poids = 'R02', 'certain', 1.0
            else:
                regle, niveau, poids = 'R02n', 'probable', 0.5
        elif tb and tr:
            if sim is not None and sim >= 0.9:
                regle, niveau, poids = 'R03t', 'probable', 0.6
        elif sim is not None and sim >= 0.8:
            regle, niveau, poids = 'R03', 'probable', round(0.9 * sim, 3)
        nb = (noms_bl.get(eid) or [(None,)])[0][0]
        lignes.append((eid, sid, sim, tb, tr, fiab, conflit, regle, niveau, poids,
                       f"similarité {sim:.2f} : « {nb} » / « {den} »" if sim is not None else 'noms non comparables'))
    avec_r02 = {l[0] for l in lignes if l[7] == 'R02'}
    lignes = [l[:7] + (None, None, None, l[10] + ' (doublon d\'un RC séparé, déjà rapproché)')
              if l[7] == 'R02n' and l[0] in avec_r02 else l for l in lignes]
    con.executemany('INSERT INTO similarite_societe VALUES (?,?,?,?,?,?,?,?,?,?,?)', lignes)
    return len(lignes)


def calculer_frequences(con):
    alpha = con.execute("SELECT valeur FROM parametre WHERE nom = 'alpha_rarete'").fetchone()[0]
    hmax = con.execute("SELECT valeur FROM parametre WHERE nom = 'homonyme_max'").fetchone()[0]
    ph = con.execute("SELECT valeur FROM parametre WHERE nom = 'poids_homonyme'").fetchone()[0]
    con.create_function('puissance', 2, lambda x, y: float(x) ** float(y))
    con.execute('DELETE FROM cle_frequence')
    con.execute("INSERT INTO cle_frequence (type_cle, valeur, n) "
                "SELECT type_cle, valeur, count(DISTINCT coalesce(societe_id, -objet_id)) "
                "FROM cle WHERE cote = 'RC' GROUP BY type_cle, valeur")
    con.execute('UPDATE cle_frequence SET rarete = puissance(n, ?)', (-alpha,))
    con.execute('UPDATE rc_societe SET rarete_taille = puissance(max(nb_personnes, 1), ?)', (-alpha,))
    # même nom écrit à l'identique dans la même ville, dans peu de sociétés : probablement la même personne
    con.execute('DELETE FROM rc_homonyme')
    con.execute('DELETE FROM rc_homonyme_membre')
    con.execute("""INSERT INTO rc_homonyme (cle, nom, ville_code, n)
        SELECT p.nom_exact || '@' || s.ville_code, min(p.nom_complet), s.ville_code, count(DISTINCT p.societe_id)
        FROM rc_personne p JOIN rc_societe s ON s.societe_id = p.societe_id
        WHERE p.type_personne = 'PP' AND p.nom_exact IS NOT NULL AND s.ville_code IS NOT NULL
        GROUP BY p.nom_exact, s.ville_code
        HAVING count(DISTINCT p.societe_id) BETWEEN 2 AND ?""", (hmax,))
    con.execute('UPDATE rc_homonyme SET poids = ? * puissance(n, ?)', (ph, -alpha))
    con.execute("""INSERT INTO rc_homonyme_membre (cle, personne_id)
        SELECT h.cle, p.personne_id FROM rc_personne p JOIN rc_societe s ON s.societe_id = p.societe_id
        JOIN rc_homonyme h ON h.cle = p.nom_exact || '@' || s.ville_code
        WHERE p.type_personne = 'PP'""")


# ---- second contrôle des rapprochements par squelette : voyelles longues et mots latins ----
_VOY_AR = {'ا': 'a', 'و': 'u', 'ي': 'i', 'ى': 'a'}          # ة, ع, ء : facultatifs
_COMPAT = {'a': {'a', 'e'}, 'u': {'u'}, 'i': {'i', 'e'}}
_LAT_TOK = re.compile('SCH|CH|SH|KH|GH|DH|TH|PH|QU|CK|GU|DJ|OU|[A-Z]')
_LAT_VOY = {'A': 'a', 'E': 'e', 'I': 'i', 'Y': 'i', 'O': 'u', 'U': 'u', 'OU': 'u', 'W': 'u'}
_LAT_CONS = {'SCH': 'c', 'CH': 'c', 'SH': 'c', 'KH': 'h', 'GH': 'g', 'DH': 'd', 'TH': 't', 'PH': 'f', 'QU': 'k',
             'CK': 'k', 'GU': 'k', 'DJ': 'j', 'Q': 'k', 'P': 'b', 'V': 'f'}


ARTICLES_ASSIMILES = {'ES': 'S', 'ER': 'R', 'ET': 'T', 'ED': 'D', 'EZ': 'Z', 'EN': 'N', 'ECH': 'CH', 'ESS': 'S',
                      'ERR': 'R', 'ETT': 'T', 'EDD': 'D', 'EZZ': 'Z', 'ENN': 'N'}


def _mots_pour_profil(texte):
    """Mêmes mots que le squelette : civilités et articles retirés selon les mêmes règles, y compris l'article
    assimilé écrit à part (« EZ-ZARIY » = الزرعي, « ES SAIDI » = السعيدي)."""
    mots, sortie, prec = [m for m in latin_maj(texte).split() if m not in HONORIFIQUES], [], None
    for i, m in enumerate(mots):
        if est_arabe(m):
            if len(m) == 1:
                prec = m
                continue
            if m.startswith('ال') and len(m) > 3 and m not in NON_ARTICLE_AR:
                m = (m[2:] if m[2] in _SOLAIRES else 'ل' + m[2:]) if prec == 'عبد' else m[2:]
        elif (m in ('EL', 'AL', 'L') and prec != 'ABD') or (
                m in ARTICLES_ASSIMILES and i + 1 < len(mots) and mots[i + 1].startswith(ARTICLES_ASSIMILES[m])):
            prec = m
            continue
        sortie.append(m)
        prec = m
    return sortie


def _profil(mots):
    """Consonnes (classes du squelette), voyelles qui suivent chacune (consonnes doublées fusionnées), et découpage
    en mots : (début, fin) dans la suite des consonnes, rang de la première consonne propre au mot, mot.
    Chaque voyelle garde son origine : 0 = mot qui a posé la consonne, 1 = mot suivant dont la première consonne
    s'est fondue dans la précédente (« DAOUD ADEL » : le E d'ADEL ne compte pas pour DAOUD).
    Renvoie (consonnes, voyelles, découpage, rangs des consonnes fondues entre deux mots)."""
    cons, slots, decoupe, fusions, auteur = [], [set()], [], set(), []
    for w, m in enumerate(mots):
        # voyelle en tête de mot (« ا » d'« اسامة », « OU » d'« OUSSAMA ») ignorée
        debut, premiere, vu = len(cons), [None], [False]

        def cons_mot(c):
            nouvelle = not (cons and cons[-1] == c)
            if not vu[0] and nouvelle:
                premiere[0] = len(cons)
            vu[0] = True
            if nouvelle:
                cons.append(c)
                slots.append(set())
                auteur.append(w)
            elif auteur[-1] != w:
                fusions.add(len(cons))

        def voyelle(v):
            if vu[0]:
                slots[-1].add((v, 0 if auteur[-1] == w else 1))
        if est_arabe(m):
            for ch in m:
                if ch in _SQ_AR:
                    cons_mot(_SQ_AR[ch])
                elif ch in _VOY_AR:
                    voyelle(_VOY_AR[ch])
        else:
            toks = _LAT_TOK.findall(m)
            for k, t in enumerate(toks):
                suivant = toks[k + 1] if k + 1 < len(toks) else ''
                if t in _LAT_VOY:
                    voyelle(_LAT_VOY[t])
                elif t == 'X':
                    cons_mot('k')
                    cons_mot('s')
                elif t in ('C', 'G'):
                    doux = suivant[:1] in ('E', 'I', 'Y')
                    cons_mot(('s' if t == 'C' else 'j') if doux else 'k')
                elif t in _LAT_CONS:
                    cons_mot(_LAT_CONS[t])
                elif t.isalpha():
                    cons_mot(t.lower())
        decoupe.append((debut, len(cons), premiere[0], m))
    return cons, slots, decoupe, fusions


def _voyelles_retrouvees(sa, sl, fa, fl):
    """Chaque voyelle longue écrite en arabe après une consonne se retrouve au même endroit en latin ; quand la
    consonne est fondue entre deux mots des deux côtés, la voyelle doit venir du même mot."""
    for k in range(1, len(sa)):
        par_mot = k in fa and k in fl
        for v, o in sa[k]:
            if not any(vl in _COMPAT.get(v, {v}) and (not par_mot or ol == o) for vl, ol in sl[k]):
                return False
    return True


def _variantes_arabes(mots):
    """Le PDF inverse souvent « لا » en « ال » à l'intérieur des mots : on essaie les deux lectures."""
    v2 = [m[:1] + m[1:].replace('ال', 'لا') if est_arabe(m) else m for m in mots]
    return [mots] if v2 == mots else [mots, v2]


_FIN_VOY_AR = set('اىيوةهءع')


def _frontieres(decoupe):
    """Fins de mots (sauf le dernier), comptées en consonnes."""
    return {fin for _d, fin, _p, _m in decoupe[:-1]}


def _mots_coherents(dl, da, slots_l):
    """Mot latin et mot arabe qui couvrent exactement les mêmes consonnes : débuts et fins doivent concorder.
    - voyelle finale latine (A, I, O, OU, Y ; pas le E muet) → le mot arabe finit par une voyelle longue,
      ة, ه, ء ou ع : SAIDA ≠ سعيد, MABROUKI ≠ مبروك, ZIANI ≠ الزين ; finale en -IA, -YA → ي en fin de mot
      arabe : NADIA ≠ ندى ;
    - ة finale → le mot latin finit par A, E, T ou H : SAID ≠ سعيدة, NAJI ≠ ناجية, AISSAM ≠ اسامة
      (sauf FATIM-ZAHRA) ;
    - alif initial suivi d'une consonne (احمد, ابراهيم) → le mot latin commence par une voyelle ou par deux
      consonnes accolées, au plus séparées d'un E muet (BRAHIM, SMAIL, MHAMED, JERADI) : HAMID ≠ احمد."""
    arabes = {(d, f): m for d, f, _p, m in da if f > d}
    for d, f, p, lat in dl:
        ar = arabes.get((d, f))
        if f <= d or not ar:
            continue
        toks = _LAT_TOK.findall(lat)
        if not toks:
            continue
        if toks[-1] in ('A', 'I', 'O', 'U', 'Y', 'OU') and ar[-1] not in _FIN_VOY_AR:
            return False
        if ar[-1] == 'ة' and lat[-1] not in 'AETH' and ar != 'فاطمة':
            return False
        if len(toks) >= 3 and toks[-1] == 'A' and toks[-2] in ('I', 'Y') and 'ي' not in ar[-3:]:
            return False
        if (len(ar) > 1 and ar[0] == 'ا' and ar[1] in _SQ_AR and lat[0] not in 'AEIOUY'
                and p is not None and any(v != 'e' for v, _o in slots_l[p + 1])):
            return False
    return True


def profils_compatibles(texte_latin, texte_arabe):
    """Même suite de consonnes ; chaque voyelle longue écrite en arabe retrouvée au même endroit en latin ;
    mêmes coupures entre les mots (ou l'un des deux écrit en moins de mots) ; débuts et fins de mots cohérents."""
    mots_l = _mots_pour_profil(texte_latin)
    variantes_l = [mots_l]
    if any(article_colle(m) for m in mots_l):                       # article collé : « ELMOSTAFA »
        variantes_l.append([article_colle(m) or m for m in mots_l])
    profils_l = [_profil(v) for v in variantes_l]
    for mots in _variantes_arabes(_mots_pour_profil(texte_arabe)):
        for ordre in (mots, list(reversed(mots))):
            ca, sa, da, fua = _profil(ordre)
            if not ca:
                continue
            fa = _frontieres(da)
            for cl, sl, dl, ful in profils_l:
                if ca != cl or not _voyelles_retrouvees(sa, sl, fua, ful):
                    continue
                fl = _frontieres(dl)
                if not (fa <= fl or fl <= fa):          # « OUMAIMA KHERIBI » (M|HRB) ≠ « امهار ايوب » (MHR|B)
                    continue
                if _mots_coherents(dl, da, sl):
                    return True
    return False


def _formes_distinctes(x, y, nisba=True):
    """Même racine mais deux noms différents : SAID / SAIDA, AMINE / AMINA (masculin, féminin) ;
    MABROUK / MABROUKI (nom en -I), sauf dans un nom de trois mots ou plus, où c'est plutôt une lettre perdue."""
    for a, b in ((x, y), (y, x)):
        if len(a) >= 4 and a.endswith('A'):
            racine = a[:-1]
            if racine[-1] not in 'AEIOUY' and racine != 'FATIM' and b in (racine, racine + 'E'):
                return True
        if nisba and len(b) >= 3 and a == b + 'I' and b[-1] not in 'AEIOUY':
            return True
    return False


def mots_latins_proches(a, b, seuil=0.8):
    """Deux noms latins : chaque mot du plus court a un mot très proche dans l'autre."""
    ma, mb = mots_nom_latin(a), mots_nom_latin(b)
    if not ma or not mb:
        return False
    court, long_ = sorted((ma, mb), key=len)
    nisba = len(court) < 3
    return all(any(_ratio(x, y) >= seuil and not _formes_distinctes(x, y, nisba) for y in long_) for x in court)


def noms_compatibles(variantes_bl, nom_rc, societe=False):
    """Le nom du registre est-il compatible avec l'un des noms de la liste noire ? Renvoie le nom retenu."""
    for v in variantes_bl:
        if est_arabe(nom_rc):
            if profils_compatibles(v, nom_rc):
                return v
        elif societe:
            if cle_rs(v) and _ratio(cle_rs(v), cle_rs(nom_rc) or '') >= 0.85:
                return v
        elif mots_latins_proches(v, nom_rc):
            return v
    return None


def filtrer_par_squelette(con):
    """Retire les rapprochements par squelette que les voyelles ou les mots contredisent. Une personne du registre
    est comparée au nom et au prénom de l'inscrit, jamais à son employeur ; une société, à la raison sociale et à
    l'employeur déclaré."""
    noms_pp, noms_pm = defaultdict(list), defaultdict(list)
    for eid, nom, prenom, ras in con.execute('SELECT entite_id, nom, prenom, nom_ras FROM bl_inscription'):
        for v in ([f'{nom} {prenom}', f'{prenom} {nom}'] if nom and prenom else [nom or prenom]):
            if v and v not in noms_pp[eid]:
                noms_pp[eid].append(v)
        if ras and ras not in noms_pm[eid]:
            noms_pm[eid].append(ras)
    for eid, emp in con.execute('SELECT entite_id, employeur FROM bl_entite WHERE employeur IS NOT NULL'):
        if emp not in noms_pm[eid]:
            noms_pm[eid].append(emp)
    a_retirer, notes = [], []
    # liens par CIN : le nom cité doit correspondre à l'inscrit ; sinon le CIN est peut-être rattaché à la mauvaise
    # personne de l'annonce (extraction) → R01n, probable
    retrogrades = []
    for cid, eid, oid in con.execute("""SELECT c.id, c.bl_entite_id, c.rc_objet_id FROM correspondance c
            WHERE c.regle = 'R01' AND c.rc_objet = 'rc_personne'""").fetchall():
        nom_rc = con.execute('SELECT nom_complet FROM rc_personne WHERE personne_id = ?', (oid,)).fetchone()[0]
        variantes = noms_pp.get(eid) or []
        if not variantes or not nom_rc:
            continue
        if noms_compatibles(variantes, nom_rc):
            notes.append((f' ; nom au registre : {nom_rc}', cid))
            continue
        # même nom de famille au moins (CIN d'un parent cité dans la même annonce) : on garde, mais probable
        retrogrades.append((f'CIN cité dans l\'annonce, mais nom différent : « {nom_rc} » / « {variantes[0]} »', cid))
    con.executemany("""UPDATE correspondance SET regle = 'R01n', niveau = 'probable', poids_regle = 0.7,
                        confirmation = ? WHERE id = ?""", retrogrades)
    lignes = con.execute("""SELECT c.id, c.bl_entite_id, c.rc_objet, c.cle_type,
            CASE c.rc_objet WHEN 'rc_personne' THEN (SELECT nom_complet FROM rc_personne WHERE personne_id = c.rc_objet_id)
                            ELSE (SELECT denomination FROM rc_societe WHERE societe_id = c.rc_objet_id) END,
            c.rc_objet_id
        FROM correspondance c WHERE c.cle_type IN ('NOM_SQ', 'RS_SQ', 'NOM')""").fetchall()
    for cid, eid, objet, type_cle, nom_rc, oid in lignes:
        if not nom_rc:
            continue
        if objet == 'rc_societe' or type_cle == 'RS_SQ':
            variantes = noms_pm[eid] or noms_pp[eid]
            noms = ([n for (n,) in con.execute("SELECT DISTINCT denomination FROM rc_annonce WHERE societe_id = ? "
                                               "AND denomination_statut = 'valide'", (oid,))]
                    if objet == 'rc_societe' else []) or [nom_rc]
            retenu = next((r for r in (noms_compatibles(variantes, n, societe=True) for n in noms) if r), None)
        else:
            variantes = noms_pp[eid] or noms_pm[eid]
            retenu = noms_compatibles(variantes, nom_rc)
        if type_cle == 'NOM' and not retenu:
            retenu = variantes[0] if variantes else None          # clé exacte : déjà sûre
        if retenu:
            notes.append((f' ; nom inscrit : {retenu}', cid))
        else:
            a_retirer.append((cid,))
    con.executemany('DELETE FROM correspondance WHERE id = ?', a_retirer)
    con.executemany("UPDATE correspondance SET confirmation = coalesce(confirmation, '') || ? WHERE id = ?", notes)
    if retrogrades:
        print(f'  liens par CIN dont le nom ne correspond pas : {len(retrogrades)} passés en probable (R01n)', flush=True)
    return len(a_retirer), len(notes)


def appliquer_regles(con):
    con.execute('ANALYZE')                      # sans statistiques, SQLite choisit de mauvais ordres de jointure
    calculer_similarites(con)
    calculer_frequences(con)
    with open(os.path.join(ICI, 'regles_bl_rc.sql'), encoding='utf-8') as f:
        etape1, etape2 = f.read().split('-- ==== ÉTAPE 2', 1)
    con.executescript(etape1)
    retires, gardes = filtrer_par_squelette(con)
    print(f'  contrôle des voyelles et des mots : {retires} rapprochements par squelette retirés, {gardes} gardés',
          flush=True)
    con.executescript('-- ==== ÉTAPE 2' + etape2)


def bilan(con):
    print('\nBilan')
    for _, indicateur, valeur in con.execute('SELECT * FROM v_bilan ORDER BY ordre'):
        print(f'  {indicateur:<58} ' + f'{valeur:>10,}'.replace(',', ' '))
    lignes = con.execute('SELECT regle, niveau, correspondances, inscrits, societes FROM v_couverture_regles').fetchall()
    if lignes:
        print('\nCorrespondances par règle (avant choix de la meilleure)')
        for r in lignes:
            print(f'  {r[0]:<5} {r[1]:<9} {r[2]:>8} correspondances · {r[3]:>6} inscrits · {r[4]:>6} sociétés')


def main():
    ap = argparse.ArgumentParser(description='Base SQLite liste noire × registre du commerce')
    ap.add_argument('--liste-noire', help='Excel ou CSV de la liste noire EQDOM')
    ap.add_argument('--rc-kamal', help='Export des annonces légales de Kamal (CSV point-virgule)')
    ap.add_argument('--rc-kamal-personnes', help='Fichier « personnes » de Kamal (une ligne par personne citée, avec CIN)')
    ap.add_argument('--rc-annonces', help='Modèle générique : annonces (CSV, Excel, Parquet ou JSON à plat)')
    ap.add_argument('--rc-personnes', help='Modèle générique : personnes citées')
    ap.add_argument('--rc-json', help='Modèle générique : JSON / JSONL d\'annonces avec personnes imbriquées')
    ap.add_argument('--base', default='bl_rc.sqlite', help='Fichier SQLite à produire')
    ap.add_argument('--regles-seulement', action='store_true', help='Relancer les règles sur une base existante')
    args = ap.parse_args()
    t0 = time.time()

    if args.regles_seulement:
        con = sqlite3.connect(args.base)
        con.execute('DELETE FROM ref_regle')                 # règles et poids à jour
        con.executemany('INSERT INTO ref_regle VALUES (?,?,?,?,?,?,?,?)', REGLES)
        appliquer_regles(con)
        con.commit()
        import translitteration as tl
        tl.appliquer(con)
        bilan(con)
        return
    if not args.liste_noire:
        ap.error('--liste-noire est obligatoire (sauf avec --regles-seulement)')

    print(f'Construction de {args.base}', flush=True)
    con = creer_base(args.base)
    con.execute('PRAGMA journal_mode = OFF')
    con.execute('PRAGMA synchronous = OFF')
    charger_referentiels(con)
    stats_bl, remplissage = charger_liste_noire(con, args.liste_noire)
    charger_correspondance_champs(con, remplissage)
    print(f"  liste noire : {stats_bl['inscriptions']} inscriptions → {stats_bl['entites']} entités, "
          f"{stats_bl['anomalies']} anomalies, {stats_bl['cles']} clés", flush=True)

    annonces = None
    if args.rc_kamal:
        annonces = lire_export_kamal(args.rc_kamal, args.rc_kamal_personnes)
    elif args.rc_annonces or args.rc_json:
        brutes = lire_table(args.rc_annonces or args.rc_json)
        personnes = lire_table(args.rc_personnes) if args.rc_personnes else []
        annonces = lire_modele(brutes, personnes)
    if annonces is not None:
        st = assembler_rc(con, annonces)
        print(f"  registre : {st['annonces']} annonces → {st['societes']} sociétés, {st['personnes']} personnes "
              f"({st['mentions']} mentions, {st['rejets']} entrées écartées), {st['cles']} clés", flush=True)
    else:
        print('  registre : aucun export fourni, tables prêtes à recevoir celui de Kamal')
    con.commit()                                # données chargées : les règles peuvent être relancées seules

    appliquer_regles(con)
    con.execute("INSERT INTO parametre VALUES ('construction', NULL, ?, 'Date de construction de la base')",
                (datetime.now().strftime('%Y-%m-%d %H:%M'),))
    con.commit()
    # écriture latine des noms arabes (rc_personne.nom_latin, rc_societe.denomination_latin, ref_translitteration)
    import translitteration as tl
    tl.appliquer(con)
    bilan(con)
    con.execute('VACUUM')
    con.close()
    print(f'\nTerminé en {time.time() - t0:.1f} s')


if __name__ == '__main__':
    main()
