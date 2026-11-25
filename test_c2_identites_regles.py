"""Tests de non-régression C2, sans connexion à PostgreSQL.

À placer à la racine du dépôt carte-antifraude, puis exécuter :
    python -m pytest -q test_c2_identites_regles.py

Ces tests vérifient les décisions métier ; les tests SQL de reconstruction
et de persistance des décisions analyste restent à exécuter séparément.
"""

from pipeline.couches import c2_identites_postgresql as c2


def _mention(nom):
    return {"nom": nom, "nom_norm": nom}


def test_cin_normalise_valide():
    assert c2._cin("AB123456") == c2._cin("AB 123456")


def test_cin_incomplet_ne_fusionne_pas():
    assert c2._cin(None) is None
    assert c2._cin("") is None


def test_rc_trop_court_n_identifie_pas_une_societe():
    assert c2._rc("12") is None
    assert c2._rc("7") is None


def test_ice_exige_exactement_15_chiffres():
    assert c2._ice("123456789012345") == "123456789012345"
    assert c2._ice("12345678901234") is None
    assert c2._ice("1234567890123456") is None


def test_memes_noms_accepte_inversion():
    assert c2.memes_noms("AHMED BENALI", "BENALI AHMED")


def test_memes_noms_refuse_un_seul_mot():
    assert not c2.memes_noms("AHMED", "AHMED")


def test_noms_incompatibles_sur_meme_cin_restent_separes():
    assert c2.separes("AHMED BENALI", "FATIMA EL AMRANI")
    grappes = c2._grappes([_mention("AHMED BENALI"), _mention("FATIMA EL AMRANI")])
    assert len(grappes) == 2


def test_noms_compatibles_sur_meme_cin_reunis():
    grappes = c2._grappes([_mention("AHMED BENALI"), _mention("BENALI AHMED")])
    assert len(grappes) == 1


def test_societes_sans_rapport_sur_meme_rc_reste_separees():
    assert c2.societes_separees("ATLAS CONSTRUCTION", "ORIENT INFORMATIQUE")
    grappes = c2._grappes(
        [_mention("ATLAS CONSTRUCTION"), _mention("ORIENT INFORMATIQUE")],
        separes=c2.societes_separees,
    )
    assert len(grappes) == 2


def test_homonymie_seule_pas_preuve_de_fusion():
    # La présence d'un nom compatible ne doit pas produire une clé certaine.
    assert c2._cle_propre({
        "regle": "propre", "nom": "AHMED BENALI", "source": "v2", "ref": "D1",
        "type_fiche": "PP", "cle_nom": "AHMED BENALI", "nom_norm": "AHMED BENALI",
    }) != c2._cle_propre({
        "regle": "propre", "nom": "AHMED BENALI", "source": "v2", "ref": "D2",
        "type_fiche": "PP", "cle_nom": "AHMED BENALI", "nom_norm": "AHMED BENALI",
    })
