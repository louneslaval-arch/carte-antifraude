"""Motifs de la garde des données : fonctions pures, sans dépendance.

Un constat donne la ligne et le nom du motif, jamais la valeur trouvée.
Une ligne qui porte la marque fictif-volontaire n'est pas analysée.
Les expressions sont écrites pour ne pas se reconnaître elles-mêmes (X{4} plutôt que quatre X).
"""
import os
import re

ICI = os.path.dirname(os.path.abspath(__file__))
MARQUE = 'fictif-volontaire'

_CIN = re.compile(r'\b[A-Z]{1,2}\d{4,6}\b')
_REFERENCE = re.compile(r'\b[A-Z]\d{2}[A-Z]\d{4}\b')
_RIB = re.compile(r'\b\d{3} ?\d{3} ?\d{16} ?\d{2}\b')
_ICE = re.compile(r'\b\d{15}\b')
_TELEPHONE = re.compile(r'(?<!\d)(?:\+212[ .-]?|0)[5-7](?:[ .-]?\d{2}){4}(?!\d)')
_COURRIEL = re.compile(r'\b[\w.+-]+@(?:[\w-]+\.)+[\w-]+\b')
_ARABE = re.compile('[' + chr(0x0600) + '-' + chr(0x06FF) + ']')
_MUTATION = (re.compile(r"""(['"])X{2}.*?X{2}\1"""), re.compile(r"b'X{4}'"))

DOMAINES_FICTIFS = ('.invalid', '.test', '.example')
TELEPHONE_FICTIF = ('0600000000', '0600000099')

EXTENSIONS_REFUSEES = (
    '.sqlite', '.sqlite3', '.db', '.xlsx', '.xls', '.csv', '.json', '.parquet', '.jsonl',
    '.pdf', '.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff', '.pem', '.key',
)


def _chiffres(valeur):
    return re.sub(r'\D', '', valeur)


def _telephone_fictif(valeur):
    n = _chiffres(valeur)
    if n.startswith('212'):
        n = '0' + n[3:]
    return TELEPHONE_FICTIF[0] <= n <= TELEPHONE_FICTIF[1] and len(n) == 10


def _constats_ligne(ligne, arabe_admis):
    trouves = []
    if any(not m.group().startswith('ZZ') for m in _CIN.finditer(ligne)):
        trouves.append('cin')
    if _REFERENCE.search(ligne):
        trouves.append('reference_dossier')
    if any(not _chiffres(m.group()).startswith('999') for m in _RIB.finditer(ligne)):
        trouves.append('rib')
    if any(not m.group().startswith('999') for m in _ICE.finditer(ligne)):
        trouves.append('ice')
    if any(not _telephone_fictif(m.group()) for m in _TELEPHONE.finditer(ligne)):
        trouves.append('telephone')
    if any(not m.group().split('@', 1)[1].lower().endswith(DOMAINES_FICTIFS)
           for m in _COURRIEL.finditer(ligne)):
        trouves.append('courriel')
    if not arabe_admis and _ARABE.search(ligne):
        trouves.append('ecriture_arabe')
    if any(m.search(ligne) for m in _MUTATION):
        trouves.append('trace_mutation')
    return trouves


# --- Listes d'exceptions (motifs glob depuis la racine du dépôt) ---

def _glob_en_regex(motif):
    i, sortie = 0, ''
    while i < len(motif):
        if motif.startswith('**/', i):
            sortie += '(?:.*/)?'
            i += 3
        elif motif.startswith('**', i):
            sortie += '.*'
            i += 2
        elif motif[i] == '*':
            sortie += '[^/]*'
            i += 1
        elif motif[i] == '?':
            sortie += '[^/]'
            i += 1
        else:
            sortie += re.escape(motif[i])
            i += 1
    return re.compile(sortie + r'\Z')


def lire_liste(nom):
    chemin = os.path.join(ICI, nom)
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding='utf-8') as f:
        return [_glob_en_regex(l.strip()) for l in f
                if l.strip() and not l.lstrip().startswith('#')]


def _couvert(chemin_relatif, liste):
    return any(m.match(chemin_relatif) for m in liste)


def relatif(chemin, racine=None):
    """Chemin relatif à la racine du dépôt, avec des barres obliques."""
    if os.path.isabs(chemin) and racine:
        chemin = os.path.relpath(chemin, racine)
    chemin = chemin.replace(os.sep, '/')
    while chemin.startswith('./'):
        chemin = chemin[2:]
    return chemin


def dans_api_de_kamal(chemin_relatif):
    """Fichier sous un dossier api/ du lot de Kamal (import/ ou reference/v2/)."""
    parties = chemin_relatif.split('/')
    du_lot = parties[0] == 'import' or parties[:2] == ['reference', 'v2'] or 'kamal_structure' in parties
    return du_lot and 'api' in parties[:-1]


def fichier_refuse(chemin, racine=None):
    rel = relatif(chemin, racine)
    if dans_api_de_kamal(rel):
        return True
    nom = rel.rsplit('/', 1)[-1]
    refuse = nom.lower().endswith(EXTENSIONS_REFUSEES) or nom == '.env' or nom.startswith('.env.')
    return refuse and not _couvert(rel, lire_liste('fichiers_autorises.txt'))


def analyser(texte, chemin, racine=None):
    """Rend la liste des constats (numéro de ligne, motif), jamais la valeur trouvée."""
    rel = relatif(chemin, racine)
    arabe_admis = _couvert(rel, lire_liste('arabe_autorise.txt'))
    constats = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if MARQUE in ligne:
            continue
        constats.extend((numero, m) for m in _constats_ligne(ligne, arabe_admis))
    return constats
