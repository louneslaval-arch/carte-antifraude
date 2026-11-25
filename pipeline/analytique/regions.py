"""Région officielle (découpage de 2015, 12 régions, provinces du Sud comprises) de chaque ville du référentiel
(`construire_base.VILLES`, 94 villes). Saisi à la main ; un test vérifie qu'aucune ville du référentiel n'en manque.
Le contour du dépôt (`maroc_regions.py`) suit l'ancien découpage en 16 régions : la page dessine donc des barres."""

REGIONS = {
    'Tanger-Tétouan-Al Hoceïma': ('TANGER', 'TETOUAN', 'AL HOCEIMA', 'ASSILAH', 'CHEFCHAOUEN', 'FNIDEQ',
                                  'KSAR EL KEBIR', 'LARACHE', 'MARTIL', 'MDIQ', 'OUEZZANE'),
    'Oriental': ('OUJDA', 'NADOR', 'BERKANE', 'AHFIR', 'DRIOUCH', 'FIGUIG', 'BOUARFA', 'GUERCIF', 'JERADA',
                 'TAOURIRT'),
    'Fès-Meknès': ('FES', 'MEKNES', 'AZROU', 'EL HAJEB', 'IFRANE', 'MISSOUR', 'SEFROU', 'TAOUNATE', 'TAZA'),
    'Rabat-Salé-Kénitra': ('RABAT', 'SALE', 'KENITRA', 'TEMARA', 'SKHIRAT', 'HARHOURA', 'TAMESNA', 'KHEMISSET',
                           'TIFLET', 'SIDI KACEM', 'SIDI SLIMANE', 'SOUK EL ARBAA', 'MECHRA BEL KSIRI'),
    'Béni Mellal-Khénifra': ('BENI MELLAL', 'AZILAL', 'FQUIH BEN SALAH', 'KASBA TADLA', 'KHENIFRA', 'KHOURIBGA',
                             'OUED ZEM', 'SOUK SEBT OULAD NEMMA'),
    'Casablanca-Settat': ('CASABLANCA', 'MOHAMMEDIA', 'AIN HARROUDA', 'BOUSKOURA', 'DAR BOUAZZA', 'MEDIOUNA',
                          'NOUACEUR', 'BERRECHID', 'HAD SOUALEM', 'SETTAT', 'BEN AHMED', 'BENSLIMANE', 'BOUZNIKA',
                          'EL JADIDA', 'AZEMMOUR', 'SIDI BENNOUR'),
    'Marrakech-Safi': ('MARRAKECH', 'SAFI', 'ESSAOUIRA', 'CHICHAOUA', 'IMINTANOUT', 'EL KELAA DES SRAGHNA',
                       'BEN GUERIR', 'YOUSSOUFIA'),
    'Drâa-Tafilalet': ('ERRACHIDIA', 'MIDELT', 'OUARZAZATE', 'TINGHIR', 'ZAGORA'),
    'Souss-Massa': ('AGADIR', 'INEZGANE', 'AIT MELLOUL', 'BIOUGRA', 'TAROUDANT', 'TIZNIT', 'TATA'),
    'Guelmim-Oued Noun': ('GUELMIM', 'SIDI IFNI', 'TAN TAN'),
    'Laâyoune-Sakia El Hamra': ('LAAYOUNE', 'BOUJDOUR', 'SMARA'),
    'Dakhla-Oued Ed-Dahab': ('DAKHLA',),
}
REGION_DE_VILLE = {ville: region for region, villes in REGIONS.items() for ville in villes}
