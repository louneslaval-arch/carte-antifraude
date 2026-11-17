"""Secret statistique de la couche 7 : primaire (moins de 5), secondaire (une seule case masquée dans une répartition
en entraîne une seconde), et aucune valeur masquée dans la table ni retrouvable par différence."""
from collections import defaultdict

from .commun import SANS_KAMAL, lignes_agregat
from pipeline.analytique import secret


def cases(*effectifs):
    return [dict(valeur1=f'v{k}', valeur2='', effectif=e) for k, e in enumerate(effectifs)]


def masques(cs):
    return [(c['masque'], c['motif']) for c in cs]


def test_case_a_4_masquee_case_a_5_publiee():
    cs = cases(4, 5, 5)
    secret.masquer_repartition(cs)
    assert cs[0]['masque'] == 1 and cs[0]['motif'] == 'moins de 5'
    assert cs[1]['masque'] + cs[2]['masque'] == 1          # secret secondaire sur l'une des deux


def test_une_seule_case_masquee_en_masque_une_seconde_la_plus_petite():
    cs = cases(3, 40, 12, 90)
    secret.masquer_repartition(cs)
    assert masques(cs) == [(1, 'moins de 5'), (0, None), (1, 'secret secondaire'), (0, None)]


def test_deux_cases_deja_masquees_rien_de_plus():
    cs = cases(3, 2, 12, 90)
    secret.masquer_repartition(cs)
    assert masques(cs) == [(1, 'moins de 5'), (1, 'moins de 5'), (0, None), (0, None)]


def test_repartition_sans_case_masquee_inchangee():
    cs = cases(5, 6, 70)
    secret.masquer_repartition(cs)
    assert [c['masque'] for c in cs] == [0, 0, 0]


def test_egalite_departagee_par_la_valeur_toujours_la_meme():
    a, b = cases(1, 9, 9), cases(1, 9, 9)
    secret.masquer_repartition(a)
    secret.masquer_repartition(list(reversed(b)))
    assert masques(a) == masques(b) == [(1, 'moins de 5'), (1, 'secret secondaire'), (0, None)]


def test_tableau_croise_protege_en_ligne_et_en_colonne():
    cs = [dict(valeur1=l, valeur2=c, effectif=e) for (l, c), e in {
        ('a', 'x'): 3, ('a', 'y'): 20, ('a', 'z'): 30,
        ('b', 'x'): 25, ('b', 'y'): 22, ('b', 'z'): 40,
        ('c', 'x'): 50, ('c', 'y'): 60, ('c', 'z'): 70}.items()]
    secret.masquer_tableau(cs)
    for axe in ('valeur1', 'valeur2'):
        groupes = defaultdict(list)
        for c in cs:
            groupes[c[axe]].append(c['masque'])
        assert all(sum(m) != 1 for m in groupes.values()), axe


@SANS_KAMAL
def test_aucune_case_masquee_n_a_de_valeur_dans_la_table(base_stats):
    for r in lignes_agregat(base_stats):
        if r['masque']:
            assert (r['valeur'], r['numerateur'], r['denominateur'], r['borne_basse'], r['borne_haute']) == \
                   (None,) * 5, r
            assert r['motif_masque'] in ('moins de 5', 'secret secondaire'), r
        else:
            assert r['motif_masque'] is None, r


@SANS_KAMAL
def test_aucune_case_publiee_sous_cinq(base_stats):
    for r in lignes_agregat(base_stats):
        if not r['masque']:
            effectif = r['numerateur'] if r['indicateur'].startswith('part_') else r['denominateur']
            if r['indicateur'] in ('nb_dossiers', 'elements_manquants'):
                effectif = r['valeur']
            assert effectif is not None and effectif >= 5, r


@SANS_KAMAL
def test_aucune_valeur_masquee_retrouvable_par_difference(base_stats):
    """Toute répartition (une dimension, ou une ligne ou colonne d'un croisement) a zéro ou au moins deux cases
    masquées : la différence avec le total ne rend qu'une somme, jamais une case."""
    groupes = defaultdict(list)
    for r in lignes_agregat(base_stats):
        if r['indicateur'].startswith('mediane_') or not r['dimension1']:
            continue
        base = (r['indicateur'], r['filtre_produit'], r['filtre_categorie'], r['dimension1'], r['dimension2'])
        if r['dimension2']:
            groupes[base + ('ligne', r['valeur1'])].append(r['masque'])
            groupes[base + ('colonne', r['valeur2'])].append(r['masque'])
        else:
            groupes[base].append(r['masque'])
    assert groupes
    fautifs = [k for k, m in groupes.items() if sum(m) == 1 and len(m) > 1]
    assert not fautifs, fautifs[:3]
