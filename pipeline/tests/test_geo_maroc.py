"""Contour du Maroc : versionné dans le dépôt (module généré), sans dépendre d'un fichier .json local ignoré."""

import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))
import geo_maroc as gm  # noqa: E402


def test_contour_des_seize_regions_sans_fichier_json(monkeypatch):
    import builtins
    ouvrir = builtins.open

    def sans_json(chemin, *a, **k):
        assert not str(chemin).endswith('.json'), 'le contour ne doit pas dépendre d\'un fichier .json'
        return ouvrir(chemin, *a, **k)
    monkeypatch.setattr(builtins, 'open', sans_json)
    regions = gm.contour()
    assert len(regions) == 16 and all(r['nom'] and len(r['pts']) >= 3 for r in regions)
    assert sum(len(r['pts']) for r in regions) == 2666


def test_module_du_contour_genere_depuis_sa_source():
    import maroc_regions
    assert maroc_regions.SOURCE.startswith('Natural Earth') and len(maroc_regions.REGIONS) == 16
