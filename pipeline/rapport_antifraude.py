#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rapport_antifraude.py — classeur des liens créés entre les dossiers de l'antifraude, la liste noire et le registre du commerce.

  python3 rapport_antifraude.py --base bl_rc.sqlite --sortie Liens_antifraude.xlsx

À lancer après charger_antifraude.py. Feuilles : Synthèse · Liste noire (dossiers où apparaît un inscrit) · Réseau (dossiers reliés
à un inscrit par le registre) · Sociétés au registre · CIN apportés · Enrichissement de la liste noire · Présents dans plusieurs
dossiers · RIB partagés · Tiers bancaires.
"""
import argparse
import sqlite3
import time

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

POLICE = 'Arial'
ENTETE = PatternFill('solid', fgColor='1F3864')
ROUGE = PatternFill('solid', fgColor='F8CBAD')
JAUNE = PatternFill('solid', fgColor='FFF2CC')
fin = Side(style='thin', color='BFBFBF')
BORD = Border(left=fin, right=fin, top=fin, bottom=fin)
REGLES = [
    ('AF01', 'certain', 'Personne d\'un dossier = personne inscrite : même CIN'),
    ('AF01n', 'à vérifier', 'Personne d\'un dossier sans CIN = inscrit sans CIN : mêmes mots du nom'),
    ('AF02', 'certain', 'Société d\'un dossier = société inscrite : même RC, même tribunal, raisons sociales compatibles'),
    ('AF02n', 'à vérifier', 'Même RC et même tribunal, raisons sociales différentes'),
    ('AF02b', 'probable', 'Même RC, liste noire sans tribunal, raisons sociales compatibles : le dossier donne le tribunal'),
    ('AF02c', 'certain', 'Même ICE'),
    ('AF02d', 'à vérifier', 'Liste noire sans RC : même raison sociale (et même ville si connue)'),
    ('AF03', 'certain', 'Société d\'un dossier = société du registre : même RC, même tribunal, dénominations compatibles'),
    ('AF03b', 'probable', 'Même RC et même tribunal, dénomination non lue au registre : le dossier la donne'),
    ('AF03n', 'à vérifier', 'Même RC et même tribunal, dénominations différentes (souvent le nom du cabinet déposant lu à la place)'),
    ('AF04', 'certain', 'Personne d\'un dossier = personne du registre : même CIN'),
    ('AF05', 'certain', 'Gérant ou associé d\'un dossier = personne du registre de la même société, nom compatible : le dossier apporte le CIN'),
    ('AF07', 'à vérifier', 'Employeur d\'un dossier = société inscrite, ou employeur déclaré par un inscrit : même raison sociale'),
    ('AF09', 'indice', 'Même RIB dans des dossiers de clients différents et sans lien entre eux'),
    ('AF11', 'indice', 'Tiers bancaire d\'un relevé = inscrit : mêmes mots (indice faible si le nom est courant)'),
    ('AF20', 'réseau', 'Identité d\'un dossier retrouvée au registre et située sur un chemin partant d\'un inscrit (N arêtes)'),
]


def feuille(wb, titre, entetes, lignes, largeurs, couleur=None):
    ws = wb.create_sheet(titre)
    for j, t in enumerate(entetes, 1):
        c = ws.cell(row=1, column=j, value=t)
        c.font = Font(name=POLICE, bold=True, color='FFFFFF'); c.fill = ENTETE; c.border = BORD
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, ligne in enumerate(lignes, 2):
        for j, v in enumerate(ligne, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=POLICE, size=10); c.alignment = Alignment(wrap_text=True, vertical='top')
        if couleur:
            f = couleur(ligne)
            if f:
                ws.cell(row=i, column=1).fill = f
    for j, w in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'A2'
    if lignes:
        ws.auto_filter.ref = f'A1:{get_column_letter(len(entetes))}{len(lignes) + 1}'
    ws.row_dimensions[1].height = 30
    return ws


DOSSIERS = """(SELECT group_concat(x, ' ; ') FROM (SELECT DISTINCT d.ref || ' · ' || coalesce(d.verdict, 'sans verdict') || ' · ' || coalesce(d.recu_le, '') ||
              ' · ' || di.role AS x FROM af_dossier_identite di JOIN af_dossier d ON d.ref = di.dossier_ref WHERE di.identite_id = i.identite_id ORDER BY d.recu_le))"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True)
    ap.add_argument('--sortie', default='Liens_antifraude.xlsx')
    a = ap.parse_args()
    con = sqlite3.connect(f'file:{a.base}?mode=ro', uri=True)
    q = lambda s, *p: con.execute(s, p).fetchall()
    wb = Workbook(); wb.remove(wb.active)

    # ---- Synthèse
    ws = wb.create_sheet('Synthèse')
    ws['A1'] = 'Dossiers de l\'antifraude × liste noire × registre du commerce'
    ws['A1'].font = Font(name=POLICE, bold=True, size=13, color='1F3864')
    ws['A2'] = f'Base du {time.strftime("%d/%m/%Y")} · ' + ' · '.join(r[0] for r in q("SELECT description FROM parametre WHERE nom = 'antifraude_date'"))
    ws['A2'].font = Font(name=POLICE, italic=True, size=9, color='595959')
    r = 4

    def ligne(lib, val, gras=False):
        nonlocal r
        ws.cell(row=r, column=1, value=lib).font = Font(name=POLICE, bold=gras)
        c = ws.cell(row=r, column=2, value=val); c.font = Font(name=POLICE, bold=gras)
        if isinstance(val, (int, float)):
            c.number_format = '# ##0'
        r += 1

    def titre(t):
        nonlocal r
        r += 1
        ws.cell(row=r, column=1, value=t).font = Font(name=POLICE, bold=True, color='1F3864'); r += 1
    titre('Ce qui a été chargé')
    for lot, n, pp, pm in q("SELECT lot, count(*), sum(type_personne = 'PP'), sum(type_personne = 'PM') FROM af_dossier GROUP BY 1 ORDER BY 1 DESC"):
        ligne(f'Dossiers du lot {lot}', n, True); ligne('… personnes physiques', pp); ligne('… sociétés', pm)
    n, c = q('SELECT count(*), count(cin_norm) FROM af_personne')[0]
    ligne('Personnes lues dans les pièces', n, True); ligne('… avec un CIN valide', c)
    n, rc, rct, ice = q('SELECT count(*), count(rc_num), sum(rc_num IS NOT NULL AND tribunal_code IS NOT NULL), count(ice) FROM af_societe')[0]
    ligne('Sociétés lues dans les pièces (clientes, employeurs, vendeurs)', n, True); ligne('… avec RC et tribunal', rct); ligne('… avec ICE', ice)
    ligne('Comptes bancaires (RIB distincts)', q('SELECT count(DISTINCT rib) FROM af_compte')[0][0], True)
    ligne('Tiers bancaires nominatifs (par dossier)', q('SELECT count(*) FROM af_tiers')[0][0], True)
    titre('Identités reconstituées')
    for typ, niv, n, multi in q('SELECT type_identite, niveau_cle, count(*), sum(nb_dossiers >= 2) FROM af_identite GROUP BY 1, 2 ORDER BY 1 DESC, 2 DESC'):
        lib = ('Personnes' if typ == 'PP' else 'Sociétés') + (' identifiées par ' + ('leur CIN' if typ == 'PP' else 'RC + tribunal ou ICE') if niv == 'fort' else ' connues par leur nom seulement')
        ligne(lib, n, True); ligne('… présentes dans 2 dossiers ou plus', multi)
    ligne('Relations personne – société (gérant, associé, dirigeant, salarié)', q('SELECT count(*) FROM af_relation')[0][0], True)
    titre('Liens créés, par règle')
    compte = {(a_, b_): (n, i) for a_, b_, n, i in q('SELECT regle, niveau, count(*), count(DISTINCT coalesce(identite_id, dossier_ref)) FROM af_lien GROUP BY 1, 2')}
    for j, t in enumerate(['Règle', 'Liens', 'Identités ou dossiers', 'Niveau', 'Définition'], 1):
        c = ws.cell(row=r, column=j, value=t); c.font = Font(name=POLICE, bold=True, color='FFFFFF'); c.fill = ENTETE
    r += 1
    for regle, niveau, definition in REGLES:
        n = sum(v[0] for k, v in compte.items() if k[0] == regle); i = sum(v[1] for k, v in compte.items() if k[0] == regle)
        for j, val in enumerate([regle, n, i, niveau, definition], 1):
            c = ws.cell(row=r, column=j, value=val); c.font = Font(name=POLICE, size=10)
        r += 1
    etats = dict(q('SELECT etat, count(DISTINCT cin_norm) FROM af_cin_apporte GROUP BY 1'))
    titre('Ce que les dossiers apportent au registre')
    ligne('CIN apportés à une personne du registre qui n\'en avait pas', etats.get('apporte', 0), True)
    ligne('CIN du registre confirmés par un dossier', etats.get('confirme', 0)); ligne('CIN en conflit (registre ≠ dossier)', etats.get('conflit', 0))
    ws.column_dimensions['A'].width = 62; ws.column_dimensions['B'].width = 12; ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 14; ws.column_dimensions['E'].width = 110

    # ---- Liste noire
    lignes = q(f"""SELECT l.niveau, l.regle, i.type_identite, i.nom, coalesce(i.cin_norm, i.rc_num || coalesce(' ' || i.tribunal_code, '')), i.roles,
        e.nom_affiche, coalesce(e.cin, e.rc_num), e.types_liste, e.motifs, e.derniere_saisie, l.cle_type, l.cle_valeur, l.detail, {DOSSIERS}
        FROM af_lien l JOIN af_identite i USING (identite_id) JOIN bl_entite e ON e.entite_id = l.cible_id
        WHERE l.cible = 'bl_entite' AND l.regle LIKE 'AF0%'
        ORDER BY CASE l.niveau WHEN 'certain' THEN 0 WHEN 'probable' THEN 1 ELSE 2 END, l.regle, i.nom""")
    feuille(wb, 'Liste noire', ['Niveau', 'Règle', 'Type', 'Dans le dossier', 'CIN ou RC (dossier)', 'Rôles dans les dossiers', 'Inscrit en liste noire',
                               'CIN ou RC (liste noire)', 'Liste', 'Motifs', 'Dernière inscription', 'Clé', 'Valeur', 'Précision', 'Dossiers (référence · verdict · date · rôle)'],
            lignes, [11, 8, 6, 30, 18, 28, 30, 16, 18, 22, 13, 9, 20, 44, 80],
            couleur=lambda l: ROUGE if l[0] == 'certain' else JAUNE if l[0] == 'probable' else None)
    # ---- Réseau
    lignes = q(f"""SELECT l.niveau, i.type_identite, i.nom, coalesce(i.cin_norm, i.rc_num || coalesce(' ' || i.tribunal_code, '')), i.roles,
        e.nom_affiche, e.types_liste, e.motifs, l.detail, {DOSSIERS}
        FROM af_lien l JOIN af_identite i USING (identite_id) JOIN bl_entite e ON e.entite_id = l.cible_id WHERE l.regle = 'AF20' ORDER BY l.niveau, i.nom""")
    feuille(wb, 'Réseau', ['Distance', 'Type', 'Dans le dossier', 'CIN ou RC', 'Rôles dans les dossiers', 'Inscrit relié', 'Liste', 'Motifs', 'Chemin au registre', 'Dossiers'],
            lignes, [18, 6, 30, 18, 30, 30, 18, 22, 100, 70])
    # ---- Sociétés au registre
    lignes = q(f"""SELECT l.niveau, l.regle, i.nom, i.rc_num, i.tribunal_code, i.ice, s.denomination, s.denomination_latin, s.nb_annonces, s.derniere_publication, s.nb_personnes,
        l.detail, {DOSSIERS} FROM af_lien l JOIN af_identite i USING (identite_id) JOIN rc_societe s ON s.societe_id = l.cible_id
        WHERE l.cible = 'rc_societe' ORDER BY l.regle, i.nom""")
    feuille(wb, 'Sociétés au registre', ['Niveau', 'Règle', 'Société du dossier', 'RC', 'Tribunal', 'ICE', 'Dénomination au registre', 'Écriture latine', 'Annonces',
                                        'Dernière annonce', 'Personnes citées', 'Précision', 'Dossiers'], lignes, [11, 8, 34, 10, 14, 17, 34, 28, 9, 13, 9, 50, 70])
    # ---- CIN apportés
    lignes = q("""SELECT a.etat, a.cin_norm, a.nom_dossier, a.role_dossier, a.nom_registre, p.nom_latin, p.role, s.denomination, s.rc_num, s.tribunal_code, p.cin_norm, a.dossier_ref
        FROM af_cin_apporte a JOIN rc_personne p USING (personne_id) JOIN rc_societe s ON s.societe_id = a.societe_id ORDER BY a.etat, a.nom_dossier""")
    feuille(wb, 'CIN apportés', ['État', 'CIN (dossier)', 'Nom dans le dossier', 'Rôle (dossier)', 'Nom au registre', 'Écriture latine', 'Rôle (registre)', 'Société',
                                'RC', 'Tribunal', 'CIN déjà au registre', 'Dossier'], lignes, [10, 13, 30, 12, 30, 28, 22, 34, 10, 14, 16, 11],
            couleur=lambda l: ROUGE if l[0] == 'conflit' else None)
    # ---- Enrichissement de la liste noire
    lignes = []
    for eid, nom_bl, cin, dn, vil, iid, nom_d, dn_d, vil_d, adr_d in q("""SELECT e.entite_id, e.nom_affiche, e.cin, e.date_naissance, e.ville_code, i.identite_id, i.nom, i.date_naissance, i.ville_code, i.adresse
            FROM af_lien l JOIN af_identite i USING (identite_id) JOIN bl_entite e ON e.entite_id = l.cible_id WHERE l.regle = 'AF01'"""):
        if not nom_bl and nom_d:
            lignes.append(('nom', cin, nom_bl, None, nom_d, 'AF01'))
        if not dn and dn_d:
            lignes.append(('date de naissance', cin, nom_bl or nom_d, None, dn_d, 'AF01'))
        if not vil and vil_d:
            lignes.append(('ville', cin, nom_bl or nom_d, None, vil_d, 'AF01'))
    for rc, nom_bl, trib, det, ice in q("""SELECT e.rc_num, e.nom_affiche, i.tribunal_code, l.detail, i.ice FROM af_lien l JOIN af_identite i USING (identite_id)
            JOIN bl_entite e ON e.entite_id = l.cible_id WHERE l.regle IN ('AF02b', 'AF02', 'AF02n')"""):
        if det and 'tribunal apporté' in det:
            lignes.append(('tribunal', rc, nom_bl, None, trib, 'AF02b'))
        if ice:
            lignes.append(('ICE', rc, nom_bl, None, ice, 'AF02'))
    feuille(wb, 'Enrichissement liste noire', ['Champ', 'CIN ou RC (liste noire)', 'Inscrit', 'Valeur en liste noire', 'Valeur apportée par le dossier', 'Règle'],
            sorted(lignes, key=lambda x: (x[0], str(x[2]))), [18, 20, 34, 20, 34, 8])
    # ---- Présents dans plusieurs dossiers
    lignes = q("""SELECT i.type_identite, i.nom, coalesce(i.cin_norm, i.rc_num || coalesce(' ' || i.tribunal_code, ''), i.ice), i.nb_dossiers, i.roles,
        (SELECT count(DISTINCT d.client_nom) FROM af_dossier_identite di JOIN af_dossier d ON d.ref = di.dossier_ref WHERE di.identite_id = i.identite_id),
        (SELECT group_concat(x, ' ; ') FROM (SELECT DISTINCT d.ref || ' · ' || coalesce(d.client_nom, '?') || ' · ' || coalesce(d.verdict, '-') || ' · ' || di.role AS x
            FROM af_dossier_identite di JOIN af_dossier d ON d.ref = di.dossier_ref WHERE di.identite_id = i.identite_id ORDER BY d.recu_le))
        FROM af_identite i WHERE i.niveau_cle = 'fort' AND i.nb_dossiers >= 2
          AND (SELECT count(DISTINCT d.client_nom) FROM af_dossier_identite di JOIN af_dossier d ON d.ref = di.dossier_ref WHERE di.identite_id = i.identite_id) >= 2
        ORDER BY 6 DESC, i.nb_dossiers DESC LIMIT 3000""")
    feuille(wb, 'Plusieurs dossiers', ['Type', 'Personne ou société', 'CIN, RC ou ICE', 'Dossiers', 'Rôles', 'Clients différents', 'Dossiers (référence · client · verdict · rôle)'],
            lignes, [6, 34, 20, 9, 34, 10, 140])
    # ---- RIB partagés
    lignes = q("""SELECT l.cle_valeur, l.dossier_ref, a.client_nom, a.verdict, l.cible_id, b.client_nom, b.verdict,
        (SELECT group_concat(DISTINCT banque) FROM af_compte c WHERE c.rib = l.cle_valeur), (SELECT group_concat(DISTINCT titulaire) FROM af_compte c WHERE c.rib = l.cle_valeur)
        FROM af_lien l JOIN af_dossier a ON a.ref = l.dossier_ref JOIN af_dossier b ON b.ref = l.cible_id WHERE l.regle = 'AF09' ORDER BY 1, 2""")
    feuille(wb, 'RIB partagés', ['RIB', 'Dossier A', 'Client A', 'Verdict A', 'Dossier B', 'Client B', 'Verdict B', 'Banque', 'Titulaire(s) lus'], lignes, [28, 11, 32, 14, 11, 32, 14, 22, 50])
    # ---- Tiers bancaires
    lignes = q("""SELECT l.niveau, l.dossier_ref, d.client_nom, d.verdict, e.nom_affiche, coalesce(e.cin, e.rc_num), e.types_liste, e.motifs, l.detail
        FROM af_lien l JOIN af_dossier d ON d.ref = l.dossier_ref JOIN bl_entite e ON e.entite_id = l.cible_id WHERE l.regle = 'AF11' ORDER BY l.niveau, l.dossier_ref""")
    feuille(wb, 'Tiers bancaires', ['Niveau', 'Dossier', 'Client', 'Verdict', 'Inscrit au même nom', 'CIN ou RC', 'Liste', 'Motifs', 'Opérations'], lignes, [14, 11, 30, 14, 30, 14, 18, 22, 70])
    wb.save(a.sortie)
    print(f'  Classeur : {a.sortie}')


if __name__ == '__main__':
    main()
