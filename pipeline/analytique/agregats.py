"""Agrégats de la couche 7 (`c7_agregat`) : chaque indicateur du dictionnaire, sur l'ensemble, par critère autorisé
pris seul, sur la liste fermée des croisements, pour chaque tranche de filtre (produit × catégorie). Fourchette de
Wilson à 95 % pour les proportions ; médianes publiées à partir de 5 valeurs, jamais de minimum ni de maximum.
Secret primaire et secondaire (`secret.py`) ; une case masquée ne garde aucune valeur, même dans la table.

`construire(cx, …)` reconstruit `c7_variable_dossier`, `c7_agregat` et `c7_indicateur` ; deux constructions de suite
donnent la même table (hors `calcule_le`, fixé par l'appelant s'il le veut). Rien n'est écrit en console.
"""
from __future__ import annotations

import datetime
import json
import math
import re
from collections import defaultdict
from typing import Any, Callable, Iterable, Optional

from pipeline.analytique import indicateurs as ind
from pipeline.analytique import secret, variables

Z = 1.96
Ligne = dict[str, Any]
PRODUITS_AUTO = ('AUTO_CLASSIQUE', 'LOA')
# Population concernée par une dimension (les autres dossiers n'y figurent pas, pas même en « non renseigné »).
PP = ('tranche_age', 'situation_familiale', 'personnes_a_charge', 'tranche_revenu', 'source_revenu', 'ecart_revenu',
      'anciennete_emploi', 'type_contrat', 'employeur') + ind.DIMENSIONS_REPARTITION_SEULE
PM = ('age_societe', 'associe_unique', 'capital_tranche')
AUTO = ('vehicule_etat', 'tranche_prix_vehicule', 'marque_vehicule', 'tranche_apport', 'concessionnaire')
# Variables suivies par le taux de remplissage, avec leur population.
REMPLISSAGE = (('age', 'PP'),) + tuple((d, 'PP') for d in ind.DIMENSIONS_REPARTITION_SEULE) + (
               ('revenu_verifie', 'PP'), ('revenu_declare', 'PP'),
               ('anciennete_emploi', 'PP'), ('type_contrat', 'PP'), ('situation_familiale', 'PP'), ('ville', ''),
               ('region', ''), ('banque', ''), ('vehicule_etat', 'AUTO'), ('prix_vehicule', 'AUTO'),
               ('apport_pct', 'AUTO'), ('age_societe', 'PM'), ('associe_unique', 'PM'), ('capital_tranche', 'PM'),
               ('releve_lignes_lues', ''), ('date_reference', ''))
COLONNES = ('indicateur', 'filtre_produit', 'filtre_categorie', 'dimension1', 'valeur1', 'dimension2', 'valeur2',
            'numerateur', 'denominateur', 'valeur', 'borne_basse', 'borne_haute', 'masque', 'motif_masque',
            'periode_debut', 'periode_fin', 'version', 'calcule_le')


# ---- calculs ---------------------------------------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = Z) -> tuple[Optional[float], Optional[float]]:
    """Fourchette de Wilson (95 % par défaut) d'une proportion k / n."""
    if not n:
        return None, None
    p, z2 = k / n, z * z
    d = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / d
    demi = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return (0.0 if k == 0 else max(0.0, centre - demi)), (1.0 if k == n else min(1.0, centre + demi))


def mediane(valeurs: Iterable[float]) -> Optional[float]:
    v = sorted(valeurs)
    if not v:
        return None
    m = len(v) // 2
    return float(v[m]) if len(v) % 2 else (v[m - 1] + v[m]) / 2


def concerne(dim: str, x: Ligne) -> bool:
    if dim in PP or dim in ('tranche_age',):
        return x['type_personne'] == 'PP'
    if dim in PM:
        return x['type_personne'] == 'PM'
    if dim in AUTO:
        return x['produit'] in PRODUITS_AUTO
    if dim == 'releve_lignes_lues':
        return x['releve_lignes_lues'] is not None
    return True


def _oui_non(v: Any) -> Optional[str]:
    return None if v is None else 'oui' if v else 'non'


# Dimensions dont les valeurs sont du texte venu des pièces (sans liste fermée) : une valeur rare est regroupée.
TEXTE_LIBRE = {**{d: 'autres valeurs' for d in ind.DIMENSIONS_REPARTITION_SEULE}, 'situation_familiale': 'autres situations',
               'marque_vehicule': 'autres marques', **{d: 'autres sociétés' for d in ind.DIMENSIONS_SOCIETES}}


# Forme sociale : un employeur ou un vendeur sans elle peut être une personne physique (vendeur d'occasion, employeur
# particulier) ; son nom ne sort jamais, même avec `--avec-noms-societes`.
FORME_SOCIALE = re.compile(r'\b(SARL|SARLAU|SA|SAS|SNC|SCS|SCA|GIE|STE|SOCIETE|GROUPE|COOPERATIVE|'
                           r'ETABLISSEMENTS|ETS|BANK|BANQUE|CREDIT)\b')


def est_societe(nom: str) -> bool:
    return bool(FORME_SOCIALE.search(nom.upper()))


def valeurs_retenues(lignes: list[Ligne]) -> dict[str, set[str]]:
    """Valeurs de texte libre (noms de sociétés, nationalités, situations, marques) comptant au moins 5 dossiers sur
    la période ; les autres sont regroupées : leur texte ne sort jamais, même dans la clé d'une case masquée. Un
    employeur ou un concessionnaire sans forme sociale est regroupé quel que soit son nombre de dossiers."""
    retenues: dict[str, set[str]] = {}
    for dim in TEXTE_LIBRE:
        comptes: dict[str, int] = defaultdict(int)
        for x in lignes:
            if x.get(dim):
                comptes[x[dim]] += 1
        retenues[dim] = {v for v, n in comptes.items() if n >= ind.SEUIL
                         and (dim not in ('employeur', 'concessionnaire') or est_societe(v))}
    return retenues


def regions_isolees(lignes: list[Ligne], villes: dict[str, str]) -> set[str]:
    """Régions dont tous les dossiers viennent d'une seule ville regroupée (moins de 30 dossiers) : la région
    redonnerait la ville ; elle est regroupée à son tour."""
    par_region: dict[str, set[str]] = defaultdict(set)
    for x in lignes:
        if x['region']:
            par_region[x['region']].add(x['ville'])
    return {r for r, vs in par_region.items() if len(vs) == 1 and villes.get(next(iter(vs))) == 'autres villes'}


societes_retenues = valeurs_retenues


def lecteur(villes: dict[str, str], retenues: Optional[dict[str, set[str]]] = None,
            regions: Optional[set[str]] = None) -> Callable[[Ligne, str], str]:
    """Valeur d'une dimension pour un dossier ; « non renseigné » quand la variable est NULL."""
    gardees, isolees = retenues or {}, regions or set()

    def regroupee(dim: str) -> Callable[[Ligne], Any]:
        return lambda x: x[dim] if not x[dim] or x[dim] in gardees.get(dim, ()) else TEXTE_LIBRE[dim]
    derivees: dict[str, Callable[[Ligne], Any]] = {
        **{dim: regroupee(dim) for dim in TEXTE_LIBRE},
        'ville': lambda x: villes.get(x['ville'], 'autres villes') if x['ville'] else 'ville inconnue',
        'region': lambda x: 'autres régions' if x['region'] in isolees else x['region'],
        'ecart_revenu': lambda x: x['tranche_ecart_revenu'],
        'anciennete_emploi': lambda x: x['tranche_anciennete'],
        'age_societe': lambda x: x['tranche_age_societe'],
        'associe_unique': lambda x: _oui_non(x['associe_unique']),
        'releve_lignes_lues': lambda x: _oui_non(x['releve_lignes_lues']),
        'tranche_apport': lambda x: variables.tranche_apport(x['apport_pct']),
        'personnes_a_charge': lambda x: variables.tranche_personnes(x['personnes_a_charge']),
    }

    def lire(x: Ligne, dim: str) -> str:
        v = derivees[dim](x) if dim in derivees else x[dim]
        return ind.NON_RENSEIGNE if v is None or v == '' else str(v)
    return lire


class Calcul:
    """Cases d'une tranche de filtre ; chaque case porte son effectif (base du secret)."""

    def __init__(self, filtre: tuple[str, str], val: Callable[[Ligne, str], str]):
        self.filtre, self.val = filtre, val
        self.cases: list[Ligne] = []

    def case(self, indicateur: str, d1: str = '', v1: str = '', d2: str = '', v2: str = '', *, num: Optional[int] = None,
             den: Optional[int], valeur: Optional[float], effectif: Optional[int], proportion: bool = False,
             mediane: bool = False) -> None:
        bas, haut = wilson(num, den) if proportion and num is not None and den else (None, None)
        sensible = mediane and (effectif or 0) < ind.SEUIL_MEDIANE
        if mediane and valeur is not None:
            valeur = float(round(valeur, ind.ARRONDI_MEDIANE.get(indicateur, 0)))
        if proportion and num is not None and den is not None and not indicateur.startswith('part_'):
            if indicateur in ind.INDICATEURS_VERDICT_CONTROLE:
                # 1 à 4 dossiers, ou tous sauf 0 à 4 (7 sur 7 jugés suspects désigne chacun d'eux)
                sensible = secret.petit_compte(num) or (num > 0 and den - num < ind.SEUIL)
            else:
                sensible = secret.petit_compte(num) or secret.petit_compte(den - num)
        self.cases.append(dict(indicateur=indicateur, dimension1=d1, valeur1=v1, dimension2=d2, valeur2=v2,
                               numerateur=num, denominateur=den, valeur=valeur, borne_basse=bas, borne_haute=haut,
                               effectif=effectif, sensible=sensible, mediane=mediane))

    # -- répartitions : nombre et part -----------------------------------------------------------------------------
    def repartition(self, dossiers: list[Ligne], dims: tuple[str, ...], indicateurs: tuple[str, ...]) -> None:
        cle = (lambda x: tuple(self.val(x, d) for d in dims))
        population = [x for x in dossiers if all(concerne(d, x) for d in dims)]
        comptes: dict[tuple, int] = defaultdict(int)
        for x in population:
            comptes[cle(x)] += 1
        total = len(population)
        d1, d2 = dims[0], dims[1] if len(dims) > 1 else ''
        for valeurs, c in sorted(comptes.items()):
            v1, v2 = valeurs[0], valeurs[1] if len(valeurs) > 1 else ''
            for nom in indicateurs:
                if nom in ('nb_dossiers', 'elements_manquants'):
                    self.case(nom, d1, v1, d2, v2, den=c, valeur=c, effectif=c)
                else:
                    self.case(nom, d1, v1, d2, v2, num=c, den=total, valeur=c / total, effectif=c, proportion=True)

    # -- taux, moyennes et médianes, par découpage ---------------------------------------------------------------
    def par_decoupage(self, dossiers: list[Ligne], dims: tuple[str, ...],
                      mesure: Callable[[list[Ligne]], tuple[Optional[int], int, Optional[float], bool]],
                      indicateur: str, mediane_: bool = False) -> None:
        groupes: dict[tuple, list[Ligne]] = defaultdict(list)
        for x in dossiers:
            if all(concerne(d, x) for d in dims):
                groupes[tuple(self.val(x, d) for d in dims)].append(x)
        if not dims:
            groupes = {(): dossiers}
        for valeurs, g in sorted(groupes.items()):
            num, den, valeur, proportion = mesure(g)
            if not den:
                continue
            v = list(valeurs) + ['', '']
            d = list(dims) + ['', '']
            self.case(indicateur, d[0], v[0], d[1], v[1], num=num, den=den, valeur=valeur, effectif=den,
                      proportion=proportion, mediane=mediane_)


def _taux(condition: Callable[[Ligne], Optional[bool]]):
    def mesure(g: list[Ligne]) -> tuple[Optional[int], int, Optional[float], bool]:
        valeurs = [c for c in (condition(x) for x in g) if c is not None]
        k = sum(valeurs)
        return k, len(valeurs), (k / len(valeurs) if valeurs else None), True
    return mesure


def _moyenne(f: Callable[[Ligne], Optional[float]]):
    def mesure(g: list[Ligne]) -> tuple[Optional[int], int, Optional[float], bool]:
        v = [y for y in (f(x) for x in g) if y is not None]
        return None, len(v), (sum(v) / len(v) if v else None), False
    return mesure


def _mediane(f: Callable[[Ligne], Optional[float]]):
    def mesure(g: list[Ligne]) -> tuple[Optional[int], int, Optional[float], bool]:
        v = [y for y in (f(x) for x in g) if y is not None]
        return None, len(v), mediane(v), False
    return mesure


def _avec_verdict(x: Ligne) -> bool:
    return x['juge_suspect'] is not None


def tranche(calc: Calcul, dossiers: list[Ligne], controles: dict[str, list[tuple]], pieces: dict[str, list[tuple]],
            dims_taux: tuple[str, ...], dims_repartition: tuple[str, ...], manquants: set[str]) -> None:
    """Toutes les cases d'une tranche de filtre."""
    croisements = tuple(c for c in ind.CROISEMENTS if c[0] in dims_taux and c[1] in dims_taux)
    calc.case('nb_dossiers', den=len(dossiers), valeur=len(dossiers), effectif=len(dossiers))
    for dim in dims_repartition:
        calc.repartition(dossiers, (dim,), ('nb_dossiers', 'part_dossiers'))
    for a, b in croisements:
        calc.repartition(dossiers, (a, b), ('nb_dossiers', 'part_dossiers'))
    calc.repartition(dossiers, ('source_revenu',), ('part_source_revenu',))
    calc.repartition(dossiers, ('statut_analyse',), ('part_statut_analyse',))
    juges = [x for x in dossiers if _avec_verdict(x)]
    calc.repartition(juges, ('verdict',), ('part_verdict',))
    # verdicts : taux et alertes, par critère autorisé seulement
    mesures = (('taux_juge_suspect', _taux(lambda x: x['juge_suspect'])),
               ('taux_tres_suspect', _taux(lambda x: None if x['juge_suspect'] is None else x['verdict'] == 'TRES_SUSPECT')),
               ('nb_moyen_alertes_majeures_critiques',
                _moyenne(lambda x: None if x['juge_suspect'] is None else (x['nb_alertes_majeures'] or 0)
                         + (x['nb_alertes_critiques'] or 0))))
    for nom, mesure in mesures:
        for dims in [()] + [(d,) for d in dims_taux] + list(croisements):
            calc.par_decoupage(dossiers, dims, mesure, nom)
    # médianes et relevés
    medianes = (('mediane_revenu_verifie', lambda x: x['revenu_verifie']), ('mediane_age', lambda x: x['age']),
                ('mediane_prix_vehicule', lambda x: x['prix_vehicule'] if x['produit'] in PRODUITS_AUTO else None))
    for nom, f in medianes:
        for dims in [()] + [(d,) for d in dims_taux]:
            calc.par_decoupage(dossiers, dims, _mediane(f), nom, mediane_=True)
    releve = _taux(lambda x: x['releve_lignes_lues'])
    for dims in [()] + [(d,) for d in dims_taux if d != 'releve_lignes_lues']:
        calc.par_decoupage(dossiers, dims, releve, 'taux_releve_relu')
    # remplissage des variables
    for var, population in REMPLISSAGE:
        concernes = [x for x in dossiers if population == '' or (population == 'PP' and x['type_personne'] == 'PP')
                     or (population == 'PM' and x['type_personne'] == 'PM')
                     or (population == 'AUTO' and x['produit'] in PRODUITS_AUTO)]
        if var == 'banque' and 'banque' not in dims_taux:
            continue
        if concernes:
            k = sum(x[var] is not None for x in concernes)
            calc.case('taux_remplissage', 'variable', var, num=k, den=len(concernes), valeur=k / len(concernes),
                      effectif=len(concernes), proportion=True)
    controles_de_tranche(calc, dossiers, controles, manquants)
    pieces_de_tranche(calc, dossiers, pieces)


def manquants_de(controles_dossier: Iterable[tuple]) -> set[str]:
    return {m for _cid, _f, _a, r, _c, manque in controles_dossier if r == 'NON_EXECUTABLE' for m in manque}


def manquants_retenus(lignes: list[Ligne], controles: dict[str, list[tuple]]) -> set[str]:
    """Éléments manquants cités par au moins 5 dossiers ; les autres sont regroupés (texte venu de l'amont)."""
    comptes: dict[str, int] = defaultdict(int)
    for x in lignes:
        for m in manquants_de(controles.get(x['ref'], ())):
            comptes[m] += 1
    return {m for m, n in comptes.items() if n >= ind.SEUIL}


def controles_de_tranche(calc: Calcul, dossiers: list[Ligne], controles: dict[str, list[tuple]],
                         retenus: set[str]) -> None:
    applicables: dict[tuple[str, str], list[str]] = defaultdict(list)
    manquants: dict[str, int] = defaultdict(int)          # dossiers où l'élément manque à un contrôle non exécutable
    for x in dossiers:
        for cid, famille, applicable, resultat, _crit, _manque in controles.get(x['ref'], ()):
            if applicable:
                applicables[(famille, cid)].append(resultat)
        for m in {m if m in retenus else 'autres éléments' for m in manquants_de(controles.get(x['ref'], ()))}:
            manquants[m] += 1
    for (famille, cid), resultats in sorted(applicables.items()):
        utiles = [r for r in resultats if r != 'NON_APPLICABLE']
        if utiles:
            k = sum(r == 'ANOMALIE' for r in utiles)
            calc.case('taux_anomalie_controle', 'famille', famille, 'controle', cid, num=k, den=len(utiles),
                      valeur=k / len(utiles), effectif=len(utiles), proportion=True)
        k = sum(r == 'NON_EXECUTABLE' for r in resultats)
        calc.case('taux_non_executable_controle', 'famille', famille, 'controle', cid, num=k, den=len(resultats),
                  valeur=k / len(resultats), effectif=len(resultats), proportion=True)
    for m, c in sorted(manquants.items()):
        calc.case('elements_manquants', 'manquant', m, den=c, valeur=c, effectif=c)
    # contrôle décisif : seule anomalie majeure ou critique d'un dossier jugé suspect
    suspects = [x for x in dossiers if x['juge_suspect'] == 1]
    familles = {cid: fam for (fam, cid) in applicables}
    decisifs: dict[str, int] = defaultdict(int)
    for x in suspects:
        graves = {cid for cid, _f, _a, r, crit, _m in controles.get(x['ref'], ())
                  if r == 'ANOMALIE' and crit in ('MAJEURE', 'CRITIQUE')}
        if len(graves) == 1:
            decisifs[graves.pop()] += 1
    if suspects:
        for cid in sorted(familles):
            k = decisifs.get(cid, 0)
            calc.case('controle_decisif', 'famille', familles[cid], 'controle', cid, num=k, den=len(suspects),
                      valeur=k / len(suspects), effectif=len(suspects), proportion=True)


def pieces_de_tranche(calc: Calcul, dossiers: list[Ligne], pieces: dict[str, list[tuple]]) -> None:
    # effectif du secret : des dossiers, jamais des pièces (un dossier peut porter plusieurs pièces d'un type)
    par_type: dict[str, list[tuple]] = defaultdict(list)
    for x in dossiers:
        for type_, statut, relue in pieces.get(x['ref'], ()):
            par_type[type_].append((x['ref'], statut, relue))
    for type_, ps in sorted(par_type.items()):
        k = sum(r for _d, _s, r in ps)
        relus = {d for d, _s, r in ps if r}
        calc.case('taux_relecture_piece', 'type_piece', type_, num=k, den=len(ps), valeur=k / len(ps),
                  effectif=len({d for d, _s, _r in ps}), proportion=True)
        if 0 < len(relus) < ind.SEUIL or 0 < len({d for d, _s, r in ps if not r}) < ind.SEUIL:
            calc.cases[-1]['sensible'] = True
        statuts: dict[str, list[str]] = defaultdict(list)
        for d, s, _r in ps:
            statuts[s or ind.NON_RENSEIGNE].append(d)
        for s, ds in sorted(statuts.items()):
            calc.case('part_statut_extraction', 'type_piece', type_, 'statut_extraction', s, num=len(ds),
                      den=len(ps), valeur=len(ds) / len(ps), effectif=len(set(ds)), proportion=True)


# Indicateurs qui ne s'additionnent pas d'une case à l'autre : secret primaire seulement.
NON_ADDITIFS = ('taux_anomalie_controle', 'taux_non_executable_controle', 'controle_decisif', 'taux_remplissage')
# Une valeur « non renseigné » d'une répartition est le complément du taux de remplissage de sa variable.
REMPLISSAGE_DE = {**{d: d for d in ind.DIMENSIONS_REPARTITION_SEULE}, 'tranche_age': 'age', 'tranche_revenu': 'revenu_verifie',
                  'anciennete_emploi': 'anciennete_emploi', 'type_contrat': 'type_contrat',
                  'situation_familiale': 'situation_familiale', 'ville': 'ville', 'region': 'region', 'banque': 'banque',
                  'vehicule_etat': 'vehicule_etat', 'tranche_prix_vehicule': 'prix_vehicule',
                  'tranche_apport': 'apport_pct', 'age_societe': 'age_societe', 'associe_unique': 'associe_unique',
                  'capital_tranche': 'capital_tranche'}
NON_RENSEIGNES = (ind.NON_RENSEIGNE, 'ville inconnue')


def _cle(c: Ligne) -> tuple[str, str, str, str]:
    return c['dimension1'], c['valeur1'], c['dimension2'], c['valeur2']


def propager(cases: list[Ligne]) -> bool:
    """Un même compte publié sous deux indicateurs : masqué dans l'un, masqué dans l'autre. Rend vrai si une case
    change."""
    masques = {_cle(c) for c in cases if c['indicateur'] in ('nb_dossiers', 'part_dossiers') and c['masque']
               and c['dimension1']}
    verdicts = {c['valeur1'] for c in cases if c['indicateur'] == 'part_verdict' and c['masque']}
    remplissage = {var for dim, var in REMPLISSAGE_DE.items() for nr in NON_RENSEIGNES if (dim, nr, '', '') in masques}
    if ('source_revenu', 'aucun', '', '') in masques:
        remplissage.add('revenu_verifie')
    change = False
    for c in cases:
        if c['masque']:
            continue
        i, ensemble = c['indicateur'], not c['dimension1']
        lie = (not ensemble and _cle(c) in masques) \
            or (i == 'taux_remplissage' and c['valeur1'] in remplissage) \
            or (ensemble and i == 'taux_tres_suspect' and 'TRES_SUSPECT' in verdicts) \
            or (ensemble and i == 'taux_juge_suspect' and bool(verdicts & {'SUSPECT', 'TRES_SUSPECT'})) \
            or (ensemble and i == 'taux_releve_relu'
                and any(('releve_lignes_lues', v, '', '') in masques for v in ('oui', 'non')))
        if lie:
            change |= secret.masquer(c)
    return change


def proteger(cases: list[Ligne]) -> None:
    """Secret primaire sur chaque case ; secondaire par répartition (une dimension) ou par tableau (deux) pour les
    indicateurs additifs ; propagation entre indicateurs qui publient le même compte ; jusqu'à stabilité."""
    groupes: dict[tuple, list[Ligne]] = defaultdict(list)
    for c in cases:
        groupes[(c['indicateur'], c['dimension1'], c['dimension2'])].append(c)
    secret.primaire(cases)
    additifs = [g for (i, d1, _d2), g in groupes.items() if d1 and i not in NON_ADDITIFS]
    change = True
    while change:
        change = False
        for g in additifs:
            change |= secret.completer_tableau(g) if g[0]['dimension2'] else secret.secondaire(g)
        change |= propager(cases)


# ---- lecture, écriture, construction --------------------------------------------------------------------------------

def lire_controles(cx: Any, refs: set[str]) -> dict[str, list[tuple]]:
    """Contrôles de la dernière analyse de chaque dossier (miroir) ; la famille vient de la version brute (c0)."""
    familles: dict[str, str] = {}
    derniere: dict[str, str] = {}
    for ref, texte in cx.execute('SELECT b.ref, b.json FROM c0_dossier_brut b WHERE b.updated_at = '
                                 '(SELECT max(x.updated_at) FROM c0_dossier_brut x WHERE x.ref = b.ref)'):
        analyse = json.loads(texte).get('latestAnalysis') or {}
        if analyse.get('id'):
            derniere[ref] = analyse['id']
        for c in analyse.get('controls') or ():
            if c.get('controlId') and c.get('family'):
                familles[c['controlId']] = c['family']
    sortie: dict[str, list[tuple]] = defaultdict(list)
    for ref, analyse_id, cid, applicable, resultat, crit, manque in cx.execute(
            'SELECT d.ref, c."analysisId", c."controlId", c.applicable, c.outcome, c.criticality, c.missing '
            'FROM "AnalysisControl" c JOIN "Dossier" d ON d.id = c."dossierId" ORDER BY d.ref, c."controlId"'):
        if ref in refs and derniere.get(ref) == analyse_id:
            sortie[ref].append((cid, familles.get(cid, 'famille inconnue'), bool(applicable), resultat, crit,
                                tuple(str(m) for m in _liste(manque) if isinstance(m, (str, int)))))
    return sortie


def _liste(manque: Any) -> list:
    """`missing` : texte JSON (SQLite) ou tableau (PostgreSQL, `TEXT[]`). Illisible : une liste vide."""
    if isinstance(manque, (list, tuple)):
        return list(manque)
    try:
        v = json.loads(manque) if manque else []
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def lire_pieces(cx: Any, refs: set[str]) -> dict[str, list[tuple]]:
    sortie: dict[str, list[tuple]] = defaultdict(list)
    for ref, type_, statut, relue in cx.execute(
            "SELECT ref, type, extraction_status, CASE WHEN source = 'REANALYSE' OR nb_champs_relus > 0 THEN 1 ELSE 0 "
            'END FROM c1_piece ORDER BY ref, upstream_piece_id'):
        if ref in refs:
            sortie[ref].append((type_, statut, relue))
    return sortie


def calculer(lignes: list[Ligne], controles: dict[str, list[tuple]], pieces: dict[str, list[tuple]],
             periode: tuple[str, str], calcule_le: str, avec_noms_societes: bool = False) -> list[Ligne]:
    villes = variables.ville_de_decoupage(lignes, ind.SEUIL_VILLE)
    val = lecteur(villes, valeurs_retenues(lignes), regions_isolees(lignes, villes))
    manquants = manquants_retenus(lignes, controles)
    societes = set() if avec_noms_societes else set(ind.DIMENSIONS_SOCIETES)
    dims_taux = tuple(d for d in ind.DIMENSIONS_TAUX if d not in societes)
    dims_repartition = tuple(d for d in ind.DIMENSIONS_TAUX + ind.DIMENSIONS_REPARTITION_SEULE
                             + ind.DIMENSIONS_REPARTITION + ind.DIMENSIONS_SOCIETES
                             if d not in societes and d != 'statut_analyse')
    dims_repartition = tuple(dict.fromkeys(dims_repartition))
    sortie: list[Ligne] = []
    for p in ind.FILTRES_PRODUIT:
        for c in ind.FILTRES_CATEGORIE:
            dossiers = [x for x in lignes if (p == 'tous' or x['produit'] == p) and (c == 'toutes' or x['categorie'] == c)]
            calc = Calcul((p, c), val)
            # sexe et nationalité : répartition simple, dans la tranche « tous × toutes » seulement (jamais croisés
            # avec un produit ni une catégorie de risque)
            dims = dims_repartition if (p, c) == ('tous', 'toutes') else tuple(
                d for d in dims_repartition if d not in ind.DIMENSIONS_REPARTITION_SEULE)
            tranche(calc, dossiers, controles, pieces, dims_taux, dims, manquants)
            proteger(calc.cases)
            for case in calc.cases:
                case.update(filtre_produit=p, filtre_categorie=c, periode_debut=periode[0], periode_fin=periode[1],
                            version=ind.VERSION, calcule_le=calcule_le, motif_masque=case.pop('motif'))
                if case['masque']:
                    case.update(numerateur=None, denominateur=None, valeur=None, borne_basse=None, borne_haute=None)
                sortie.append(case)
    return sortie


def ecrire(cx: Any, cases: list[Ligne]) -> None:
    cx.execute('DELETE FROM c7_agregat')
    cx.executemany(f'INSERT INTO c7_agregat ({", ".join(COLONNES)}) VALUES ({", ".join("?" * len(COLONNES))})',
                   [tuple(c[k] for k in COLONNES) for c in cases])


def construire(cx: Any, periode_debut: Optional[str] = None, periode_fin: Optional[str] = None,
               avec_archives: bool = False, avec_noms_societes: bool = False,
               calcule_le: Optional[str] = None) -> dict[str, int]:
    """(Re)construit les tables c7 dans une transaction ; rend des comptages seulement."""
    lignes = variables.lire(cx, avec_archives)
    if periode_debut:
        lignes = [x for x in lignes if x['date_reference'] and x['date_reference'] >= periode_debut]
    if periode_fin:
        lignes = [x for x in lignes if x['date_reference'] and x['date_reference'] <= periode_fin]
    dates = sorted(x['date_reference'] for x in lignes if x['date_reference'])
    periode = (periode_debut or (dates[0] if dates else ''), periode_fin or (dates[-1] if dates else periode_debut or ''))
    refs = {x['ref'] for x in lignes}
    calcule_le = calcule_le or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    cases = calculer(lignes, lire_controles(cx, refs), lire_pieces(cx, refs), periode, calcule_le, avec_noms_societes)
    with cx:
        variables.ecrire(cx, lignes)
        ecrire(cx, cases)
        ind.ecrire(cx)
    return dict(dossiers=len(lignes), cases=len(cases), masquees=sum(c['masque'] for c in cases))
