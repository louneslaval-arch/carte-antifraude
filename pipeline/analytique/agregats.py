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


def societes_retenues(lignes: list[Ligne]) -> dict[str, set[str]]:
    """Noms de sociétés comptant au moins 5 dossiers sur la période ; les autres sont regroupées, leur nom ne sort
    jamais, même dans la clé d'une case masquée."""
    retenues: dict[str, set[str]] = {}
    for dim in ind.DIMENSIONS_SOCIETES:
        comptes: dict[str, int] = defaultdict(int)
        for x in lignes:
            if x[dim]:
                comptes[x[dim]] += 1
        retenues[dim] = {v for v, n in comptes.items() if n >= ind.SEUIL}
    return retenues


def lecteur(villes: dict[str, str], societes: Optional[dict[str, set[str]]] = None) -> Callable[[Ligne, str], str]:
    """Valeur d'une dimension pour un dossier ; « non renseigné » quand la variable est NULL."""
    retenues = societes or {}

    def societe(dim: str) -> Callable[[Ligne], Any]:
        return lambda x: x[dim] if not x[dim] or x[dim] in retenues.get(dim, ()) else 'autres sociétés'
    derivees: dict[str, Callable[[Ligne], Any]] = {
        **{dim: societe(dim) for dim in ind.DIMENSIONS_SOCIETES},
        'ville': lambda x: villes.get(x['ville'], 'autres villes') if x['ville'] else 'ville inconnue',
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
        self.cases.append(dict(indicateur=indicateur, dimension1=d1, valeur1=v1, dimension2=d2, valeur2=v2,
                               numerateur=num, denominateur=den, valeur=valeur, borne_basse=bas, borne_haute=haut,
                               effectif=effectif, mediane=mediane))

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
            dims_taux: tuple[str, ...], dims_repartition: tuple[str, ...]) -> None:
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
    controles_de_tranche(calc, dossiers, controles)
    pieces_de_tranche(calc, dossiers, pieces)


def controles_de_tranche(calc: Calcul, dossiers: list[Ligne], controles: dict[str, list[tuple]]) -> None:
    applicables: dict[tuple[str, str], list[str]] = defaultdict(list)
    manquants: dict[str, int] = defaultdict(int)
    manquants_controle: dict[tuple[str, str], int] = defaultdict(int)
    for x in dossiers:
        for cid, famille, applicable, resultat, _crit, manque in controles.get(x['ref'], ()):
            if applicable:
                applicables[(famille, cid)].append(resultat)
            if resultat == 'NON_EXECUTABLE':
                for m in manque:
                    manquants[m] += 1
                    manquants_controle[(cid, m)] += 1
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
    for (cid, m), c in sorted(manquants_controle.items()):
        calc.case('elements_manquants', 'controle', cid, 'manquant', m, den=c, valeur=c, effectif=c)
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
    par_type: dict[str, list[tuple]] = defaultdict(list)
    for x in dossiers:
        for type_, statut, relue in pieces.get(x['ref'], ()):
            par_type[type_].append((statut, relue))
    for type_, ps in sorted(par_type.items()):
        k = sum(r for _s, r in ps)
        calc.case('taux_relecture_piece', 'type_piece', type_, num=k, den=len(ps), valeur=k / len(ps),
                  effectif=len(ps), proportion=True)
        statuts: dict[str, int] = defaultdict(int)
        for s, _r in ps:
            statuts[s or ind.NON_RENSEIGNE] += 1
        for s, c in sorted(statuts.items()):
            calc.case('part_statut_extraction', 'type_piece', type_, 'statut_extraction', s, num=c, den=len(ps),
                      valeur=c / len(ps), effectif=c, proportion=True)


def proteger(cases: list[Ligne]) -> None:
    """Secret primaire sur chaque case ; secondaire par répartition (une dimension) ou par tableau (deux)."""
    groupes: dict[tuple, list[Ligne]] = defaultdict(list)
    for c in cases:
        groupes[(c['indicateur'], c['dimension1'], c['dimension2'])].append(c)
    for (_i, d1, d2), g in groupes.items():
        if not d1 or g[0]['mediane']:
            secret.primaire(g)
        elif d2:
            secret.masquer_tableau(g)
        else:
            secret.masquer_repartition(g)


# ---- lecture, écriture, construction --------------------------------------------------------------------------------

def lire_controles(cx: Any, refs: set[str]) -> dict[str, list[tuple]]:
    """Contrôles de la dernière analyse de chaque dossier (miroir) ; la famille vient de la version brute (c0)."""
    familles: dict[str, str] = {}
    for (texte,) in cx.execute('SELECT b.json FROM c0_dossier_brut b WHERE b.updated_at = '
                               '(SELECT max(x.updated_at) FROM c0_dossier_brut x WHERE x.ref = b.ref)'):
        for c in ((json.loads(texte).get('latestAnalysis') or {}).get('controls') or ()):
            if c.get('controlId') and c.get('family'):
                familles[c['controlId']] = c['family']
    sortie: dict[str, list[tuple]] = defaultdict(list)
    for ref, cid, applicable, resultat, crit, manque in cx.execute(
            'SELECT d.ref, c."controlId", c.applicable, c.outcome, c.criticality, c.missing '
            'FROM "AnalysisControl" c JOIN "Dossier" d ON d.id = c."dossierId" '
            'JOIN "Analysis" a ON a.id = c."analysisId" '
            'WHERE a."startedAt" = (SELECT max(y."startedAt") FROM "Analysis" y WHERE y."dossierId" = d.id) '
            'ORDER BY d.ref, c."controlId"'):
        if ref in refs:
            try:
                liste = json.loads(manque) if manque else []
            except ValueError:
                liste = []
            sortie[ref].append((cid, familles.get(cid, 'famille inconnue'), bool(applicable), resultat, crit,
                                tuple(str(m) for m in liste if isinstance(m, (str, int)))))
    return sortie


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
    val = lecteur(villes, societes_retenues(lignes))
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
            tranche(calc, dossiers, controles, pieces, dims_taux, dims_repartition)
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
    periode = (periode_debut or (dates[0] if dates else ''), periode_fin or (dates[-1] if dates else ''))
    refs = {x['ref'] for x in lignes}
    calcule_le = calcule_le or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    cases = calculer(lignes, lire_controles(cx, refs), lire_pieces(cx, refs), periode, calcule_le, avec_noms_societes)
    with cx:
        variables.ecrire(cx, lignes)
        ecrire(cx, cases)
        ind.ecrire(cx)
    return dict(dossiers=len(lignes), cases=len(cases), masquees=sum(c['masque'] for c in cases))
