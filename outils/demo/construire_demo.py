#!/usr/bin/env python3
"""Construit la base fictive de démonstration : dossiers de la v2 générés (format exact des types de Kamal), liste
noire et registre du commerce fictifs, puis toutes les couches (c0 à c5). Tout est fictif : CIN et références en
« ZZ », RIB, ICE et n° CNSS en « 999 », noms tirés de syllabes. Il faut la structure de Kamal
(`import/kamal_structure/`) pour générer ; la base produite, elle, se suffit à elle-même.

Avec `--carte DOSSIER`, publie aussi la carte globale du même registre et de la même liste noire (carte_globale.py,
puis publier_globale.py) ; `--archive-carte FICHIER.tar.gz` la range dans une archive (celle que livre le dépôt).

Usage : construire_demo.py [--sortie BASE] [--carte DOSSIER] [--archive-carte FICHIER.tar.gz]
                           [--dossiers 1500] [--societes 5000] [--graine 20261116]
Les valeurs par défaut sont celles de la base livrée (`jeu_essai/demo/base_demo.sqlite.gz`).
Sortie console : comptages seulement.
"""
import argparse
import gzip
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [RACINE, os.path.join(RACINE, 'jeu_essai', 'v2')]

import generer_dossiers as gd  # noqa: E402
from pipeline import migrer  # noqa: E402
from pipeline.couches import COUCHES, c0_brut, c2_identites  # noqa: E402

sys.path.insert(0, os.path.join(RACINE, 'pipeline'))
import publier_globale  # noqa: E402

T0 = '2026-11-16T08:00:00.000Z'


def socle(jeu, d):
    """Registre et liste noire fictifs du jeu, construits par le kit (construire_base.py) dans `d`."""
    g = jeu.monde
    gd.ecrire_csv(os.path.join(d, 'liste_noire.csv'), g.bl, gd.COLONNES_BL)
    gd.ecrire_csv(os.path.join(d, 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    gd.ecrire_csv(os.path.join(d, 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    chemin = os.path.join(d, 'socle.sqlite')
    subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'construire_base.py'),
                    '--liste-noire', os.path.join(d, 'liste_noire.csv'),
                    '--rc-annonces', os.path.join(d, 'rc_annonces.csv'),
                    '--rc-personnes', os.path.join(d, 'rc_personnes.csv'), '--base', chemin],
                   check=True, capture_output=True)
    return chemin


def publier_carte(chemin_socle, dossier, d):
    """Carte globale du socle (carte_globale.py), publiée en deux couches (publier_globale.py) dans `dossier`."""
    globale = os.path.join(d, 'globale.json')
    subprocess.run([sys.executable, os.path.join(RACINE, 'pipeline', 'carte_globale.py'), '--base', chemin_socle,
                    '--json', globale, '--html', os.path.join(d, 'carte_globale.html')], check=True, capture_output=True)
    return publier_globale.publier(globale, dossier)


def archiver(dossier, archive):
    """Range la publication (ses quatre fichiers, à plat) dans une archive compressée, reproductible : ni nom de poste
    ni date dans les en-têtes."""
    def neutre(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mtime = 0
        return info
    with open(archive, 'wb') as brut, gzip.GzipFile(fileobj=brut, mode='wb', mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode='w') as t:
        for nom in sorted(os.listdir(dossier)):
            t.add(os.path.join(dossier, nom), arcname=nom, filter=neutre)


def construire(sortie, n_dossiers=1500, n_societes=5000, graine=20261116, carte=None):
    """Base de démonstration dans `sortie` (si donné) et carte globale publiée dans `carte` (si donné), à partir du
    même jeu : même registre, même liste noire."""
    jeu = gd.generer(n_dossiers=n_dossiers, n_societes=n_societes, graine=graine)
    if sortie and os.path.exists(sortie):
        os.remove(sortie)
    with tempfile.TemporaryDirectory() as d:
        chemin_socle = socle(jeu, d)
        if carte:
            publier_carte(chemin_socle, carte, d)
        if not sortie:
            return {}
        cx = sqlite3.connect(sortie)
        migrer.appliquer(cx)
        passage = c0_brut.ouvrir_passage(cx, 'demo', 'lot', T0)
        for e in jeu.chronologie:
            c0_brut.recevoir(cx, passage, e['dossier'], actif=jeu.meta[e['ref']]['actif'], maintenant=T0)
        for couche in COUCHES[1:3]:
            couche.construire_tout(cx)
        c2_identites.charger_socle(cx, chemin_socle)
        for couche in COUCHES[COUCHES.index(c2_identites) + 1:]:
            couche.construire_tout(cx)
    cx.execute('DELETE FROM c0_dossier_brut WHERE rowid NOT IN (SELECT max(rowid) FROM c0_dossier_brut GROUP BY ref)')
    cx.commit()
    cx.execute('VACUUM')
    comptes = {t: cx.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
               for t in ('"Dossier"', 'c2_personne', 'c2_societe', 'ref_liste_noire', 'c5_arete')}
    cx.close()
    return comptes


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--sortie', help='base de démonstration à écrire')
    p.add_argument('--carte', help='dossier où publier la carte globale du même jeu')
    p.add_argument('--archive-carte', help='archive .tar.gz où ranger la carte publiée')
    p.add_argument('--dossiers', type=int, default=1500)
    p.add_argument('--societes', type=int, default=5000)
    p.add_argument('--graine', type=int, default=20261116)
    a = p.parse_args(argv)
    if not (a.sortie or a.carte or a.archive_carte):
        p.error('--sortie, --carte ou --archive-carte')
    with tempfile.TemporaryDirectory() as t:
        carte = a.carte or (os.path.join(t, 'carte') if a.archive_carte else None)
        comptes = construire(a.sortie, a.dossiers, a.societes, a.graine, carte=carte)
        if comptes:
            print(' ; '.join(f'{x.strip(chr(34))} : {n}' for x, n in comptes.items()))
            print(f'taille : {os.path.getsize(a.sortie) // 1024} Ko')
        if a.archive_carte:
            archiver(carte, a.archive_carte)
            print(f'carte globale : {os.path.getsize(a.archive_carte) // 1024} Ko')
    return 0


if __name__ == '__main__':
    sys.exit(main())
