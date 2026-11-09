#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rapport_croisement.py — classeur Excel des correspondances liste noire × registre du commerce,
et réimport des décisions d'analyste saisies dans la feuille « À lever ».

  python3 rapport_croisement.py --base bl_rc.sqlite --sortie Croisement_liste_noire_RC.xlsx
  python3 rapport_croisement.py --base bl_rc.sqlite --decisions Croisement_liste_noire_RC.xlsx
  (puis : python3 construire_base.py --base bl_rc.sqlite --regles-seulement)
"""
import argparse
import sqlite3
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ENTETE = PatternFill('solid', fgColor='14212B')
NIVEAU = {'alerte': 'FCE4E4', 'confirme': 'FCE4E4', 'homonymie': 'FFF4D6', 'a_verifier': 'FFF4D6', 'faible': 'F2F2F2'}

COLS_SOC = ['statut', 'niveau', 'regle', 'poids', 'inscrit', 'cle_entite', 'inscrit_rc', 'tribunal_inscrit',
            'types_liste', 'motifs', 'denomination', 'rc_num', 'tribunal_code', 'ville_siege', 'confirmation',
            'regles_touchees', 'nb_annonces', 'derniere_publication', 'url']
COLS_PERS = ['statut', 'niveau', 'regle', 'poids', 'inscrit', 'cle_entite', 'inscrit_cin', 'types_liste', 'motifs',
             'personne_registre', 'role_registre', 'cin_registre', 'nb_mentions', 'denomination', 'rc_num',
             'tribunal_code', 'ville_siege', 'confirmation', 'regles_touchees', 'date_publication', 'url']

REQ_CORR = """SELECT v.*, e.tribunal_code AS tribunal_inscrit, s.nb_annonces, s.derniere_publication
FROM v_correspondance v
JOIN bl_entite e ON e.entite_id = v.bl_entite_id
LEFT JOIN rc_societe s ON s.rc_num = v.rc_num AND s.denomination = v.denomination AND s.tribunal_code IS v.tribunal_code
WHERE {filtre}
ORDER BY CASE v.statut WHEN 'alerte' THEN 0 WHEN 'confirme' THEN 0 WHEN 'homonymie' THEN 1 WHEN 'a_verifier' THEN 1 ELSE 2 END,
         v.poids DESC, v.inscrit"""


def feuille(wb, titre, colonnes, lignes, largeurs=None, note=None, couleur_statut=True):
    ws = wb.create_sheet(titre)
    debut = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color='4A5866')
        debut = 3
    for j, c in enumerate(colonnes, start=1):
        x = ws.cell(row=debut, column=j, value=c)
        x.font, x.fill = Font(bold=True, color='FFFFFF'), ENTETE
        x.alignment = Alignment(vertical='center', wrap_text=True)
    for i, ligne in enumerate(lignes, start=debut + 1):
        for j, v in enumerate(ligne, start=1):
            ws.cell(row=i, column=j, value=v)
        if couleur_statut and ligne and ligne[0] in NIVEAU:
            ws.cell(row=i, column=1).fill = PatternFill('solid', fgColor=NIVEAU[ligne[0]])
    ws.freeze_panes = ws.cell(row=debut + 1, column=1)
    if lignes:
        ws.auto_filter.ref = f'A{debut}:{get_column_letter(len(colonnes))}{debut + len(lignes)}'
    for j, c in enumerate(colonnes, start=1):
        ws.column_dimensions[get_column_letter(j)].width = (largeurs or {}).get(c, min(max(len(c) + 2, 12), 45))
    return ws


def produire(base, sortie):
    con = sqlite3.connect(base)
    con.row_factory = sqlite3.Row
    wb = Workbook()
    wb.remove(wb.active)
    larg = {'inscrit': 30, 'denomination': 34, 'personne_registre': 28, 'confirmation': 55, 'motifs': 24,
            'types_liste': 22, 'url': 40, 'meilleur_chemin': 120, 'trace': 120, 'cle_entite': 22}

    lignes = [(r['indicateur'], r['valeur']) for r in con.execute('SELECT * FROM v_bilan ORDER BY ordre')]
    lignes += [('', '')] + [(f"{r['regle']} · {r['libelle']} ({r['niveau']})",
                             f"{r['correspondances']} correspondances, {r['inscrits']} inscrits")
                            for r in con.execute('SELECT * FROM v_couverture_regles')]
    construite = con.execute("SELECT texte FROM parametre WHERE nom = 'construction'").fetchone()
    feuille(wb, 'Synthèse', ['Indicateur', 'Valeur'], lignes, {'Indicateur': 80, 'Valeur': 40},
            note='Croisement liste noire du 03/08/2026 × annonces légales de Kamal · base construite le '
                 + (construite[0] if construite else '?'),
            couleur_statut=False)

    def corr(filtre, cols):
        return [tuple(r[c] for c in cols) for r in con.execute(REQ_CORR.format(filtre=filtre))]

    feuille(wb, 'Sociétés retrouvées', COLS_SOC,
            corr("v.rc_objet = 'rc_societe' AND v.nature = 'identite' AND v.statut <> 'faible'", COLS_SOC), larg,
            note='Société inscrite = société du registre. R02, R10, R11 : certain. R02n, R03, R03t, R04 : à vérifier.')
    feuille(wb, 'Personnes retrouvées', COLS_PERS,
            corr("v.rc_objet = 'rc_personne' AND v.statut <> 'faible'", COLS_PERS), larg,
            note='Personne inscrite = personne citée dans une annonce. Sans CIN dans l\'export, ces liens sont '
                 'probables : nom + élément qui confirme (même société, société inscrite, même ville).')
    feuille(wb, 'Employeurs déclarés', COLS_SOC,
            corr("v.nature IN ('emploi', 'adresse') AND v.statut <> 'faible'", COLS_SOC), larg,
            note='Employeur déclaré dans la liste noire (lib_emp) ou adresse = société du registre.')

    cols_dec = ['decision', 'analyste', 'justification', 'statut', 'regle', 'poids', 'inscrit', 'cle_entite',
                'personne_registre', 'role_registre', 'denomination', 'rc_num', 'tribunal_code', 'confirmation',
                'rc_objet', 'cle_rc']
    lignes = [(None, None, None) + tuple(r[c] for c in cols_dec[3:]) for r in con.execute(
        "SELECT * FROM v_correspondance WHERE statut IN ('homonymie', 'a_verifier') ORDER BY poids DESC")]
    ws = feuille(wb, 'À lever', cols_dec, lignes, dict(larg, decision=18, analyste=14, justification=40),
                 note='Colonne decision : meme_personne ou homonyme_ecarte. Réimport : '
                      'python3 rapport_croisement.py --base bl_rc.sqlite --decisions ce_fichier.xlsx',
                 couleur_statut=False)
    if lignes:
        dv = DataValidation(type='list', formula1='"meme_personne,homonyme_ecarte"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f'A4:A{3 + len(lignes)}')

    cols = ['denomination', 'rc_num', 'tribunal_code', 'ville_code', 'inscrits_relies', 'force_max',
            'profondeur_meilleur_chemin', 'inscrit_le_plus_proche', 'meilleur_chemin']
    feuille(wb, 'Contrôle employeur', cols,
            [tuple(r[c] for c in cols) for r in con.execute(
                'SELECT * FROM v_controle_employeur ORDER BY force_max DESC LIMIT 20000')], larg,
            note='Sociétés du registre reliées à au moins un inscrit, par force décroissante (20 000 premières). '
                 'Pour un employeur précis, interroger la vue v_controle_employeur.', couleur_statut=False)
    cols = ['inscrit', 'autre_inscrit', 'profondeur', 'force', 'trace']
    feuille(wb, 'Réseaux entre inscrits', cols,
            [tuple(r[c] for c in cols) for r in con.execute('SELECT * FROM v_reseau_inscrits ORDER BY force DESC')],
            larg, note='Deux inscrits reliés à travers le registre du commerce.', couleur_statut=False)
    cols = ['intermediaire', 'societes_reliees', 'societes']
    feuille(wb, 'Intermédiaires', cols,
            [tuple(r[c] for c in cols) for r in con.execute('SELECT * FROM v_intermediaire_signale LIMIT 500')],
            {'intermediaire': 50, 'societes': 120},
            note='Cabinets ou fiduciaires ayant déposé les annonces d\'au moins deux sociétés reliées à la liste noire '
                 '(information, pas un lien).', couleur_statut=False)
    lignes = [(r['controle'], r['detail'], r['nb']) for r in con.execute('SELECT * FROM v_qualite_rc')]
    lignes += [('Liste noire : ' + r['anomalie'], r['champ'], r['nb']) for r in con.execute('SELECT * FROM v_qualite_bl')]
    feuille(wb, 'Qualité des données', ['Contrôle', 'Détail', 'Nombre'], lignes, {'Contrôle': 60, 'Détail': 40},
            couleur_statut=False)
    cols = ['champ_bl', 'champ_rc', 'type_cle', 'normalisation', 'regles', 'remplissage_bl', 'remplissage_rc', 'remarque']
    feuille(wb, 'Données comparables', cols, [tuple(r[c] for c in cols) for r in
                                              con.execute('SELECT * FROM ref_correspondance_champs ORDER BY ordre')],
            {c: 36 for c in cols}, couleur_statut=False)
    cols = ['regle', 'libelle', 'nature', 'niveau', 'cle_bl', 'cle_rc', 'confirmation', 'poids']
    feuille(wb, 'Règles', cols, [tuple(r[c] for c in cols) for r in con.execute('SELECT * FROM ref_regle')],
            dict({c: 18 for c in cols}, libelle=70), couleur_statut=False)
    wb.save(sortie)
    print(f'Rapport écrit : {sortie}')


def importer_decisions(base, chemin):
    wb = load_workbook(chemin, read_only=True)
    ws = wb['À lever']
    lignes = list(ws.iter_rows(min_row=3, values_only=True))
    entetes = list(lignes[0])
    idx = {c: entetes.index(c) for c in ('decision', 'analyste', 'justification', 'cle_entite', 'rc_objet', 'cle_rc')}
    con = sqlite3.connect(base)
    n = 0
    for l in lignes[1:]:
        d = (l[idx['decision']] or '').strip() if l[idx['decision']] else ''
        if d not in ('meme_personne', 'homonyme_ecarte'):
            continue
        con.execute("""INSERT INTO decision_analyste (cle_bl, rc_objet, cle_rc, decision, analyste, date_decision, justification)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT (cle_bl, rc_objet, cle_rc) DO UPDATE SET decision = excluded.decision,
                       analyste = excluded.analyste, date_decision = excluded.date_decision,
                       justification = excluded.justification""",
                    (l[idx['cle_entite']], l[idx['rc_objet']], l[idx['cle_rc']], d, l[idx['analyste']],
                     date.today().isoformat(), l[idx['justification']]))
        n += 1
    con.commit()
    print(f'{n} décisions importées. Relancer : python3 construire_base.py --base {base} --regles-seulement')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='bl_rc.sqlite')
    ap.add_argument('--sortie', default='Croisement_liste_noire_RC.xlsx')
    ap.add_argument('--decisions', help='Classeur dont la feuille « À lever » porte des décisions à importer')
    a = ap.parse_args()
    importer_decisions(a.base, a.decisions) if a.decisions else produire(a.base, a.sortie)
