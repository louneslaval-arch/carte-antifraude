#!/usr/bin/env python3
"""Export Excel des données des dossiers EQDOM : les tables af_* de la base de la carte, une feuille par table.

Demandé par le comité de direction d'EQDOM (Lounès, 25/11/2026). Lit la copie SQLite de la base de la carte
(`outils/copier_pg_sqlite.py`) en lecture seule.

- CIN et RIB masqués par défaut (« AB****56 ») ; `--identifiants-complets` les garde en entier.
- Aucune valeur ne devient une formule : un texte qui commence par « = » reste du texte.
- Console : nom de chaque feuille et nombre de lignes.
- Données réelles : lancé par Lounès seulement, avec CARTE_DONNEES_REELLES=1, fichier rangé hors du dépôt.

Usage : python outils/exporter_dossiers_excel.py --base CARTE_KIT.sqlite --sortie DOSSIERS.xlsx [--identifiants-complets]
"""
import argparse
import datetime
import os
import re
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FEUILLES = {
    'af_dossier': 'Dossiers',
    'af_personne': 'Personnes',
    'af_societe': 'Sociétés',
    'af_compte': 'Comptes bancaires',
    'af_tiers': 'Tiers bancaires',
    'af_relation': 'Relations',
    'af_identite': 'Identités',
    'af_dossier_identite': 'Dossiers et identités',
    'af_lien': 'Liens trouvés',
}
DESCRIPTIONS = {
    'Dossiers': 'un dossier par ligne : lot, type de personne, produit, verdict, date',
    'Personnes': 'chaque personne lue dans une pièce d’un dossier (demandeur, caution, gérant, salarié…)',
    'Sociétés': 'chaque société lue dans une pièce (société cliente, employeur, vendeur…)',
    'Comptes bancaires': 'chaque RIB lu dans un relevé ou une attestation',
    'Tiers bancaires': 'libellés des virements des relevés, agrégés par dossier : aide de lecture, pas une identité',
    'Relations': 'personne gérante, associée, dirigeante ou salariée d’une société, d’après les dossiers',
    'Identités': 'une personne (clé : CIN) ou une société (clé : RC et tribunal, ICE ou nom), tous dossiers confondus',
    'Dossiers et identités': 'qui apparaît dans quel dossier, avec quel rôle',
    'Liens trouvés': 'liens créés avec la liste noire, le registre du commerce ou d’autres dossiers, avec leur règle',
}
_A_MASQUER = re.compile(r'(^|_)(cin|rib|iban)(_|$)')
_CLE_CIN = re.compile(r'^(C:)(.+)$')


def masquer(v):
    """Garde le début et la fin d'un identifiant : assez pour le reconnaître, pas assez pour le recopier."""
    if v is None:
        return None
    s = str(v)
    garde = 3 if len(s) >= 20 else 2
    if len(s) <= 2 * garde:
        return '*' * len(s)
    return s[:garde] + '*' * (len(s) - 2 * garde) + s[-garde:]


def _masqueur(table, colonne):
    if _A_MASQUER.search(colonne) or colonne == 'cle_valeur':
        return masquer
    if table == 'af_identite' and colonne == 'cle':              # « C:<CIN> » : le CIN seul est masqué
        return lambda v: _CLE_CIN.sub(lambda m: m.group(1) + masquer(m.group(2)), v) if isinstance(v, str) else v
    return None


def _cellule(feuille, v):
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    if isinstance(v, bytes):
        v = v.hex()
    if isinstance(v, str):
        v = ILLEGAL_CHARACTERS_RE.sub('', v)
    cellule = WriteOnlyCell(feuille, value=v)
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@'):
        cellule.data_type = 's'                                   # jamais une formule
    return cellule


def exporter(base, sortie, masques=True, afficher=False):
    import openpyxl
    from openpyxl.styles import Font
    source = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    presentes = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    classeur = openpyxl.Workbook(write_only=True)
    lisez = classeur.create_sheet('Lisez-moi')
    comptes = {}
    try:
        for table, nom in FEUILLES.items():
            if table not in presentes:
                continue
            feuille = classeur.create_sheet(nom)
            curseur = source.execute(f'SELECT * FROM "{table}"')
            colonnes = [d[0] for d in curseur.description]
            masqueurs = [(_masqueur(table, c) if masques else None) for c in colonnes]
            entete = []
            for c in colonnes:
                cellule = _cellule(feuille, c)
                cellule.font = Font(bold=True)
                entete.append(cellule)
            feuille.append(entete)
            n = 0
            for ligne in curseur:
                feuille.append([_cellule(feuille, m(v) if m and v is not None else v)
                                for v, m in zip(ligne, masqueurs)])
                n += 1
            comptes[nom] = n
            if afficher:
                print(f'  {nom} : {n} lignes', flush=True)
        lisez.append(['Données des dossiers EQDOM — export du '
                      + datetime.date.today().strftime('%d/%m/%Y')])
        lisez.append(['Document confidentiel : données personnelles (loi 09-08). Ne pas transférer hors d’EQDOM.'])
        lisez.append(['CIN et RIB : ' + ('masqués (début et fin seulement)' if masques else 'en entier')])
        lisez.append([])
        lisez.append(['Feuille', 'Contenu', 'Lignes'])
        for nom, n in comptes.items():
            lisez.append([nom, DESCRIPTIONS.get(nom, ''), n])
        partiel = sortie + '.partiel.xlsx'
        classeur.save(partiel)
        os.replace(partiel, sortie)
    finally:
        source.close()
    return comptes


def _dans_le_depot(chemin):
    return os.path.realpath(chemin).startswith(os.path.realpath(RACINE) + os.sep)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', required=True, help='copie SQLite de la base de la carte')
    ap.add_argument('--sortie', required=True, help='fichier Excel à écrire, hors du dépôt')
    ap.add_argument('--identifiants-complets', action='store_true', help='ne pas masquer les CIN et les RIB')
    a = ap.parse_args(argv)
    if _dans_le_depot(a.sortie):
        print('arrêt : le fichier Excel se range hors du dépôt (par exemple dans ~/antifraude-donnees)', file=sys.stderr)
        return 2
    if os.environ.get('CARTE_DONNEES_REELLES') != '1':
        print('arrêt : données réelles : la commande doit commencer par CARTE_DONNEES_REELLES=1', file=sys.stderr)
        return 2
    if not os.path.exists(a.base):
        print('arrêt : base introuvable', file=sys.stderr)
        return 2
    try:
        comptes = exporter(a.base, a.sortie, masques=not a.identifiants_complets, afficher=True)
    except Exception as e:                            # noqa: BLE001  jamais de contenu dans la sortie
        print(f'arrêt : export interrompu ({type(e).__name__})', file=sys.stderr)
        return 1
    print(f'export terminé : {len(comptes)} feuilles, {sum(comptes.values())} lignes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
