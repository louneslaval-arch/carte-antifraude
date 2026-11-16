"""Fabrication de publications fictives pour les tests : un seul endroit qui enchaîne le pipeline."""

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(os.path.dirname(ICI), 'pipeline')
KIT = os.path.join(ICI, 'donnees')


def lancer(*args):
    subprocess.run([sys.executable, *args], check=True, capture_output=True)


def base_et_chaines(dossier, liste_noire, annonces, personnes):
    """Construit la base et les chaînes ; renvoie (chemin de la base, chemin de chaines.json)."""
    base, chaines = os.path.join(dossier, 'base.sqlite'), os.path.join(dossier, 'chaines.json')
    lancer(os.path.join(PIPELINE, 'construire_base.py'), '--liste-noire', liste_noire, '--rc-annonces', annonces,
           '--rc-personnes', personnes, '--base', base)
    lancer(os.path.join(PIPELINE, 'chaines_dessin.py'), '--base', base, '--excel', os.path.join(dossier, 'c.xlsx'),
           '--html', '', '--json', chaines)
    return base, chaines


def du_kit(dossier):
    return base_et_chaines(dossier, os.path.join(KIT, 'liste_noire_fictive.csv'),
                           os.path.join(KIT, 'rc_annonces.csv'), os.path.join(KIT, 'rc_personnes.csv'))


def generee(dossier, echelle='petit'):
    g = os.path.join(dossier, 'donnees')
    lancer(os.path.join(ICI, 'generer.py'), '--echelle', echelle, '--sortie', g)
    return base_et_chaines(dossier, os.path.join(g, 'liste_noire.csv'), os.path.join(g, 'rc_annonces.csv'),
                           os.path.join(g, 'rc_personnes.csv'))
