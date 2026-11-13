"""Normalisation des valeurs lues dans les pièces : fonctions pures, sans entrée ni sortie.

Reprises d'`extraire_json_v2.py` (11/11). Aucune ne lève d'exception, quelle que soit la valeur reçue, et toutes sont
stables : normaliser deux fois revient à normaliser une fois. Écarts voulus avec le script d'origine, notés au
journal : une date impossible (31/02) rend rien ; un texte qui n'a pas la forme d'un montant rend rien ; les accents
sont retirés sans perdre les caractères d'une autre écriture.
"""
import datetime
import json
import math
import re
import unicodedata

from pipeline.normalisation.cles import GABARITS, LISTES

_FORME_MONTANT = re.compile(r'\s*-?[\d\s.,]+\s*(DH|MAD)?\s*', re.IGNORECASE)
_AGREGAT = re.compile(r'\d{2}/\d{4}', re.ASCII)


def montant(v):
    """Nombre lu dans « 30 000,00 », « 1.250,50 DH », « 1,250.50 », ou un nombre ; rien si ce n'est pas un montant."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            x = float(v)
        except OverflowError:
            return None
        return x if math.isfinite(x) else None
    if not isinstance(v, str) or not _FORME_MONTANT.fullmatch(v):
        return None
    v = ''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in v)      # chiffres d'une autre écriture
    s = re.sub(r'[^\d,.\-]', '', v, flags=re.ASCII)
    if not s:
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _date(annee, mois, jour):
    try:
        return datetime.date(int(annee), int(mois), int(jour)).isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def date_iso(v, annee=None):
    """Date AAAA-MM-JJ lue dans « jj/mm/aaaa », « aaaa-mm-jj… », ou « jj/mm » avec l'année donnée (celle du mois
    du relevé, jamais celle du jour) ; rien si la date est illisible ou impossible."""
    if not isinstance(v, str):
        return None
    s = v.strip()
    m = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)', s, re.ASCII)
    if m:
        return _date(m.group(3), m.group(2), m.group(1))
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?!\d)', s, re.ASCII)
    if m:
        return _date(m.group(1), m.group(2), m.group(3))
    m = re.match(r'^(\d{1,2})[/.-](\d{1,2})$', s, re.ASCII)
    if m and isinstance(annee, int) and not isinstance(annee, bool):
        return _date(annee, m.group(2), m.group(1))
    return None


def _sans_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if unicodedata.category(c) != 'Mn')


def texte_norm(v):
    """Texte en majuscules, sans accents, espaces réduits ; rien si vide."""
    if v is None:
        return None
    s = str(v)
    for _ in range(4):                                    # jusqu'au point fixe : la mise en majuscules peut décomposer
        suivant = re.sub(r'\s+', ' ', _sans_accents(_sans_accents(s).upper())).strip()
        if suivant == s:
            break
        s = suivant
    return s or None


def cin_norm(v):
    """CIN en majuscules sans séparateur, si elle a la forme d'une CIN et n'est pas une valeur gabarit."""
    if not v:
        return None
    s = re.sub(r'[^A-Za-z0-9]', '', str(v), flags=re.ASCII).upper()
    return s if re.fullmatch(r'[A-Z]{1,2}\d{3,7}', s, re.ASCII) and s not in GABARITS else None


def rib_norm(v):
    """Chiffres du RIB, s'il y en a au moins 16."""
    if not v:
        return None
    s = re.sub(r'[^0-9]', '', str(v))
    return s if len(s) >= 16 else None


def aplatir(obj, prefixe=''):
    """Objet → [(clé pointée, valeur scalaire)]. Un agrégat mensuel {"MM/AAAA": x} devient `cle[MM/AAAA]` ; les
    listes d'objets connues (mois, gérants…) sont traitées à part ; une liste de scalaires est gardée en texte."""
    if not isinstance(obj, dict):
        return []
    sortie = []
    for k, v in obj.items():
        cle = f'{prefixe}{k}'
        if isinstance(v, dict):
            if v and all(isinstance(kk, str) and _AGREGAT.fullmatch(kk) for kk in v):
                sortie.extend((f'{cle}[{kk}]', vv) for kk, vv in v.items())
            else:
                sortie.extend(aplatir(v, cle + '.'))
        elif isinstance(v, list):
            if k in LISTES or (v and isinstance(v[0], dict)):
                continue
            sortie.append((cle, json.dumps(v, ensure_ascii=False)))
        else:
            sortie.append((cle, v))
    return sortie
