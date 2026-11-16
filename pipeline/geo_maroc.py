# -*- coding: utf-8 -*-
"""
geo_maroc.py — coordonnées des villes du référentiel (ref_ville) et contour du Maroc, pour la vue « carte du Maroc »
de la carte globale. Rien n'est chargé depuis internet : le contour est dans maroc_regions.json (Natural Earth,
16 régions de l'ancien découpage), les villes ci-dessous (latitude, longitude, centre-ville, précision ~1 km).

Repère « monde » de la carte : x = longitude × 87,5 (cos 29° ≈ 0,875 pour garder les proportions),
y = −latitude × 100 (y vers le bas sur l'écran). 1 unité ≈ 1,1 km.
"""
import json
import math
import os

VILLES = {
    'AGADIR': (30.42, -9.60), 'AHFIR': (34.95, -2.10), 'AIN HARROUDA': (33.64, -7.45), 'AIT MELLOUL': (30.34, -9.50),
    'AL HOCEIMA': (35.25, -3.93), 'ASSILAH': (35.47, -6.03), 'AZEMMOUR': (33.29, -8.34), 'AZILAL': (31.96, -6.57),
    'AZROU': (33.44, -5.22), 'BEN AHMED': (33.07, -7.24), 'BEN GUERIR': (32.23, -7.95), 'BENI MELLAL': (32.34, -6.35),
    'BENSLIMANE': (33.61, -7.12), 'BERKANE': (34.92, -2.32), 'BERRECHID': (33.27, -7.58), 'BIOUGRA': (30.21, -9.37),
    'BOUARFA': (32.53, -1.96), 'BOUJDOUR': (26.13, -14.48), 'BOUSKOURA': (33.45, -7.65), 'BOUZNIKA': (33.79, -7.16),
    'CASABLANCA': (33.57, -7.59), 'CHEFCHAOUEN': (35.17, -5.27), 'CHICHAOUA': (31.54, -8.76), 'DAKHLA': (23.68, -15.96),
    'DAR BOUAZZA': (33.52, -7.82), 'DRIOUCH': (34.98, -3.39), 'EL HAJEB': (33.69, -5.37), 'EL JADIDA': (33.25, -8.50),
    'EL KELAA DES SRAGHNA': (32.05, -7.40), 'ERRACHIDIA': (31.93, -4.43), 'ESSAOUIRA': (31.51, -9.77), 'FES': (34.03, -5.00),
    'FIGUIG': (32.11, -1.23), 'FNIDEQ': (35.85, -5.36), 'FQUIH BEN SALAH': (32.50, -6.69), 'GUELMIM': (28.99, -10.06),
    'GUERCIF': (34.23, -3.35), 'HAD SOUALEM': (33.42, -7.87), 'HARHOURA': (33.93, -6.96), 'IFRANE': (33.53, -5.11),
    'IMINTANOUT': (31.17, -8.85), 'INEZGANE': (30.36, -9.54), 'JERADA': (34.31, -2.16), 'KASBA TADLA': (32.60, -6.27),
    'KENITRA': (34.26, -6.58), 'KHEMISSET': (33.82, -6.07), 'KHENIFRA': (32.94, -5.67), 'KHOURIBGA': (32.88, -6.91),
    'KSAR EL KEBIR': (35.00, -5.90), 'LAAYOUNE': (27.15, -13.20), 'LARACHE': (35.19, -6.16), 'MARRAKECH': (31.63, -8.00),
    'MARTIL': (35.62, -5.27), 'MDIQ': (35.68, -5.33), 'MECHRA BEL KSIRI': (34.57, -5.96), 'MEDIOUNA': (33.45, -7.51),
    'MEKNES': (33.89, -5.55), 'MIDELT': (32.68, -4.74), 'MISSOUR': (33.05, -3.99), 'MOHAMMEDIA': (33.69, -7.38),
    'NADOR': (35.17, -2.93), 'NOUACEUR': (33.37, -7.58), 'OUARZAZATE': (30.92, -6.91), 'OUED ZEM': (32.86, -6.57),
    'OUEZZANE': (34.80, -5.58), 'OUJDA': (34.68, -1.91), 'RABAT': (34.02, -6.84), 'SAFI': (32.30, -9.24),
    'SALE': (34.04, -6.80), 'SEFROU': (33.83, -4.83), 'SETTAT': (33.00, -7.62), 'SIDI BENNOUR': (32.65, -8.43),
    'SIDI IFNI': (29.38, -10.17), 'SIDI KACEM': (34.22, -5.71), 'SIDI SLIMANE': (34.26, -5.93), 'SKHIRAT': (33.85, -7.03),
    'SMARA': (26.74, -11.67), 'SOUK EL ARBAA': (34.69, -5.98), 'SOUK SEBT OULAD NEMMA': (32.29, -6.70), 'TAMESNA': (33.84, -6.91),
    'TAN TAN': (28.44, -11.10), 'TANGER': (35.77, -5.80), 'TAOUNATE': (34.54, -4.64), 'TAOURIRT': (34.41, -2.90),
    'TAROUDANT': (30.47, -8.88), 'TATA': (29.75, -7.97), 'TAZA': (34.21, -4.01), 'TEMARA': (33.93, -6.91),
    'TETOUAN': (35.57, -5.37), 'TIFLET': (33.89, -6.31), 'TINGHIR': (31.51, -5.53), 'TIZNIT': (29.70, -9.73),
    'YOUSSOUFIA': (32.25, -8.53), 'ZAGORA': (30.33, -5.84),
}
ECHELLE_X, ECHELLE_Y = 87.5, 100.0


def monde(lat, lon):
    return lon * ECHELLE_X, -lat * ECHELLE_Y


def contour():
    """Anneaux des régions en coordonnées monde, [[x, y], …]."""
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maroc_regions.json')
    with open(chemin, encoding='utf-8') as f:
        d = json.load(f)
    return [dict(nom=r['nom'], pts=[[round(lon * ECHELLE_X, 1), round(-lat * ECHELLE_Y, 1)] for lon, lat in r['anneau']])
            for r in d['regions']]


def rayon_ville(n, plafond=38.0):
    """Rayon du disque d'une ville selon son nombre de nœuds : 2 × n^0,36, plafonné (Casablanca et Rabat saturent).
    Plafond bas exprès : l'axe Casablanca – Rabat concentre la moitié des nœuds sur 90 unités (≈ 100 km)."""
    return min(plafond, max(4.0, 2.0 * n ** 0.36))


def ecarter(disques, iterations=120):
    """Écarte les disques qui se recouvrent (le plus petit bouge le plus) ; disques = {clé: [x, y, r]}."""
    cles = list(disques)
    for _ in range(iterations):
        bouge = False
        for i in range(len(cles)):
            a = disques[cles[i]]
            for j in range(i + 1, len(cles)):
                b = disques[cles[j]]
                dx, dy = b[0] - a[0], b[1] - a[1]
                d = math.hypot(dx, dy) or 0.01
                chev = a[2] + b[2] + 6 - d
                if chev <= 0:
                    continue
                bouge = True
                ux, uy = dx / d, dy / d
                pa = b[2] ** 2 / (a[2] ** 2 + b[2] ** 2)     # le petit disque se déplace (presque) seul
                a[0] -= ux * chev * pa; a[1] -= uy * chev * pa
                b[0] += ux * chev * (1 - pa); b[1] += uy * chev * (1 - pa)
        if not bouge:
            break
    return disques


def tournesol(aires, rayon):
    """Place des blocs d'aires données dans un disque : angle d'or, rayon croissant avec l'aire cumulée.
    Renvoie [(x, y)] relatifs au centre, dans l'ordre donné (mettre les plus gros d'abord)."""
    total = sum(aires) or 1.0
    out, cum, phi = [], 0.0, math.pi * (3 - math.sqrt(5))
    for i, a in enumerate(aires):
        rho = rayon * math.sqrt((cum + a / 2) / total) if i else 0.0
        out.append((rho * math.cos(i * phi), rho * math.sin(i * phi)))
        cum += a
    return out
