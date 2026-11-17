"""Variables par dossier de la couche 7 (`c7_variable_dossier`), lues dans c3 (en-tête, revenus, comptes, véhicules),
c1 (faits retenus, mentions, pièces, relevés) : une ligne par dossier, dernière version. Une variable qui ne se calcule
pas vaut NULL, jamais devinée. Montants et dates : normalisation du dépôt (`pipeline/normalisation/valeurs.py`) ;
villes : référentiel du dépôt (`construire_base.villes_dans`).

Les fonctions de calcul sont pures ; `lire` et `ecrire` seules touchent la base. Rien n'est écrit en console.
"""
from __future__ import annotations

import datetime
import statistics
from collections import defaultdict
from typing import Any, Iterable, Optional

from pipeline.analytique.regions import REGION_DE_VILLE
from pipeline.normalisation.valeurs import date_iso, montant, texte_norm

AGE_MIN, AGE_MAX = 18, 90
REVENU_MIN, REVENU_MAX = 500.0, 500000.0
VERDICTS = ('CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT')
SANS_VERDICT = 'sans verdict'
CLES_REVENU_BULLETIN = ('remuneration.salaire_net', 'salaire_net', 'salaire_net_mensuel')
CLES_REVENU_ATTESTATION = ('salaire_net', 'salaire_net_mensuel', 'remuneration.salaire_net')
CLES_PENSION = ('montant_pension_net',)
CLES_PERSONNES_A_CHARGE = ('nbre_total_personnes_charge', 'nombre_personnes_charge', 'nombre_enfants',
                           'nbre_enfants_charge')
# Graphies des banques (relevé, attestation de RIB) → nom retenu. Les noms de banque ne sortent qu'avec
# `--avec-noms-societes`.
GRAPHIES_BANQUE = {
    'BQ': 'BANQUE', 'BNQ': 'BANQUE', 'STE': 'SOCIETE', 'CDT': 'CREDIT', 'CRED': 'CREDIT', 'GLE': 'GENERALE',
}


# ---- fonctions pures ------------------------------------------------------------------------------------------------

def _jour(v: Optional[str]) -> Optional[datetime.date]:
    if not v:
        return None
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def annees_entre(debut: Optional[str], fin: Optional[str]) -> Optional[float]:
    """Années (décimales) entre deux dates ISO ; NULL si l'une manque ou si la seconde précède la première."""
    a, b = _jour(debut), _jour(fin)
    if a is None or b is None or b < a:
        return None
    return round((b - a).days / 365.25, 4)


def age_revolu(naissance: Optional[str], reference: Optional[str]) -> Optional[int]:
    """Âge révolu à la date de référence, au jour près ; hors de 18–90 ans : NULL."""
    n, r = _jour(naissance), _jour(reference)
    if n is None or r is None:
        return None
    age = r.year - n.year - ((r.month, r.day) < (n.month, n.day))
    return age if AGE_MIN <= age <= AGE_MAX else None


def _tranche(v: Optional[float], bornes: Iterable[tuple[float, str]], dernier: str) -> Optional[str]:
    if v is None:
        return None
    for borne, nom in bornes:
        if v < borne:
            return nom
    return dernier


def tranche_age(a: Optional[float]) -> Optional[str]:
    return _tranche(a, ((26, '18–25'), (36, '26–35'), (46, '36–45'), (56, '46–55'), (66, '56–65')), 'plus de 65')


def tranche_revenu(v: Optional[float]) -> Optional[str]:
    return _tranche(v, ((3000, 'moins de 3 000'), (5000, '3 000–4 999'), (8000, '5 000–7 999'),
                        (12000, '8 000–11 999'), (20000, '12 000–19 999')), '20 000 et plus')


def tranche_ecart(e: Optional[float]) -> Optional[str]:
    if e is None:
        return None
    return 'plus de 20 % en dessous' if e < -0.2 else 'plus de 20 % au-dessus' if e > 0.2 else '±20 %'


def tranche_anciennete(a: Optional[float]) -> Optional[str]:
    return _tranche(a, ((1, 'moins de 1 an'), (3, '1–3 ans'), (5, '3–5 ans'), (10, '5–10 ans')), 'plus de 10 ans')


def tranche_prix(p: Optional[float]) -> Optional[str]:
    return _tranche(p, ((100000, 'moins de 100 000'), (200000, '100 000–199 999'), (300000, '200 000–299 999'),
                        (500000, '300 000–499 999')), '500 000 et plus')


def tranche_age_societe(a: Optional[float]) -> Optional[str]:
    return _tranche(a, ((1, 'moins de 1 an'), (2, '1–2 ans'), (5, '2–5 ans'), (10, '5–10 ans')), 'plus de 10 ans')


def tranche_capital(c: Optional[float]) -> Optional[str]:
    return _tranche(c, ((10000, 'moins de 10 000'), (100000, '10 000–99 999'), (1000000, '100 000–999 999')),
                    '1 million et plus')


def tranche_apport(a: Optional[float]) -> Optional[str]:
    return _tranche(a, ((0.1, 'moins de 10 %'), (0.2, '10–19 %'), (0.3, '20–29 %')), '30 % et plus')


def tranche_personnes(n: Optional[int]) -> Optional[str]:
    return None if n is None else '3 et plus' if n >= 3 else str(n)


def semaine_iso(jour: Optional[str]) -> Optional[str]:
    d = _jour(jour)
    if d is None:
        return None
    annee, semaine, _ = d.isocalendar()
    return f'{annee}-S{semaine:02d}'


def normaliser_sexe(v: Any) -> Optional[str]:
    t = texte_norm(v)
    if t in ('M', 'H', 'MASCULIN', 'HOMME', 'MALE'):
        return 'H'
    if t in ('F', 'FEMININ', 'FEMME', 'FEMALE'):
        return 'F'
    return None


def normaliser_contrat(v: Any) -> Optional[str]:
    t = texte_norm(v)
    if not t:
        return None
    if t == 'CDI' or 'INDETERMINEE' in t:
        return 'CDI'
    if t == 'CDD' or 'DETERMINEE' in t:
        return 'CDD'
    return 'autre'


def normaliser_etat(v: Any) -> Optional[str]:
    t = texte_norm(v)
    if t in ('NEUF', 'NEUVE', 'VN'):
        return 'neuf'
    if t in ('OCCASION', 'VO', 'USAGE', 'USAGEE'):
        return 'occasion'
    return None


def normaliser_banque(v: Any) -> Optional[str]:
    t = texte_norm(v)
    if not t:
        return None
    return ' '.join(GRAPHIES_BANQUE.get(m, m) for m in t.split())


def normaliser_texte(v: Any) -> Optional[str]:
    t = texte_norm(v)
    return t or None


def ecart_relatif(verifie: Optional[float], declare: Optional[float]) -> Optional[float]:
    if verifie is None or declare is None or declare <= 0:
        return None
    return (verifie - declare) / declare


def _dans_bornes(v: Optional[float]) -> bool:
    return v is not None and REVENU_MIN <= v <= REVENU_MAX


def choisir_revenu(bulletins: Iterable[tuple[str, Optional[float]]] = (), attestations: Iterable[Optional[float]] = (),
                   pensions: Iterable[Optional[float]] = (), releves: Iterable[Optional[float]] = ()
                   ) -> tuple[Optional[float], str]:
    """Revenu mensuel vérifié et sa source : bulletin le plus récent, attestation, pension, médiane du relevé. Une
    valeur hors de 500–500 000 dirhams est écartée et la source suivante est lue."""
    for _mois, v in sorted(bulletins, key=lambda b: b[0] or '', reverse=True):
        if _dans_bornes(v):
            return v, 'bulletin'
    for v in attestations:
        if _dans_bornes(v):
            return v, 'attestation'
    for v in pensions:
        if _dans_bornes(v):
            return v, 'pension'
    mois = [v for v in releves if v is not None and v > 0]
    if mois:
        m = float(statistics.median(mois))
        if _dans_bornes(m):
            return m, 'releve'
    return None, 'aucun'


def _ville(texte: Any) -> Optional[str]:
    from pipeline.construire_base import villes_dans
    return villes_dans(texte) if texte else None


def choisir_ville(domiciliation: Iterable[Any] = (), cin: Iterable[Any] = (), releve: Iterable[Any] = ()
                  ) -> tuple[Optional[str], str]:
    """Ville (canonique, du référentiel) et sa source : quittance de domiciliation, puis CIN, puis relevé."""
    for source, textes in (('quittance', domiciliation), ('CIN', cin), ('relevé', releve)):
        for t in textes:
            v = _ville(t)
            if v:
                return v, source
    return None, 'aucune'


# ---- lecture de la base ----------------------------------------------------------------------------------------------

COLONNES = ('ref', 'actif', 'date_reference', 'semaine', 'type_personne', 'csp', 'produit', 'mode_paiement',
            'categorie', 'verdict', 'juge_suspect', 'statut_analyse', 'nb_alertes_mineures', 'nb_alertes_majeures',
            'nb_alertes_critiques', 'age', 'tranche_age', 'sexe', 'nationalite', 'situation_familiale',
            'personnes_a_charge', 'revenu_verifie', 'source_revenu', 'tranche_revenu', 'revenu_declare',
            'ecart_revenu', 'tranche_ecart_revenu', 'anciennete_emploi', 'tranche_anciennete', 'type_contrat',
            'banque', 'ville', 'region', 'source_ville', 'vehicule_etat', 'prix_vehicule', 'tranche_prix_vehicule',
            'marque_vehicule', 'apport_pct', 'age_societe', 'tranche_age_societe', 'associe_unique',
            'capital_tranche', 'nb_pieces', 'nb_pieces_relues', 'taux_relecture', 'releve_lignes_lues', 'employeur',
            'concessionnaire')
CLES_FAITS = ('sexe', 'nationalite', 'situation_familiale', 'date_embauche', 'type_contrat', 'ville',
              'ville_residence', 'adresse', 'mois_paie', 'montant_avance', 'prix_ttc', 'capital_social',
              'date_creation') + CLES_REVENU_BULLETIN + CLES_REVENU_ATTESTATION + CLES_PENSION + CLES_PERSONNES_A_CHARGE


class _Faits:
    """Faits retenus d'un dossier : (type de pièce, clé) → valeurs, dans l'ordre des pièces."""

    def __init__(self) -> None:
        self.par: dict[tuple[str, str], list[tuple[str, Any, Optional[float], Optional[str]]]] = defaultdict(list)

    def ajouter(self, upi: str, type_: str, cle: str, valeur: Any, nombre: Optional[float], date: Optional[str]) -> None:
        self.par[(type_, cle)].append((upi, valeur, nombre, date))

    def valeurs(self, type_: str, *cles: str) -> list[Any]:
        return [x[1] for c in cles for x in self.par.get((type_, c), ()) if x[1] not in (None, '')]

    def premier(self, types: Iterable[str], *cles: str) -> Any:
        for t in types:
            for v in self.valeurs(t, *cles):
                return v
        return None

    def date(self, types: Iterable[str], cle: str) -> Optional[str]:
        for t in types:
            for _u, v, _n, d in self.par.get((t, cle), ()):
                d = d or date_iso(v)
                if d:
                    return d
        return None

    def montant_de(self, type_: str, cles: Iterable[str], upi: Optional[str] = None) -> list[tuple[str, Optional[float]]]:
        """(pièce, montant) : la première clé renseignée de chaque pièce."""
        sortie: dict[str, Optional[float]] = {}
        for c in cles:
            for u, v, n, _d in self.par.get((type_, c), ()):
                if u not in sortie and (upi is None or u == upi):
                    m = n if n is not None else montant(v)
                    if m is not None:
                        sortie[u] = m
        return list(sortie.items())


def _entier(v: Any) -> Optional[int]:
    m = montant(v)
    return int(m) if m is not None and float(m).is_integer() and 0 <= m <= 20 else None


def lire(cx: Any, avec_archives: bool = False) -> list[dict[str, Any]]:
    """Une ligne par dossier de c3 (actifs seulement, sauf `avec_archives`)."""
    dossiers = cx.execute(
        'SELECT ref, coalesce(actif, 1), coalesce("businessReceivedAt", "createdAt", "updatedAt"), "personType", '
        'csp, "productType", "paymentMode", category, verdict, coalesce("verdictProvisional", 0), en_cours, '
        '"analysisStatus", "alertsMinor", "alertsMajor", "alertsCritical", declared_monthly_income '
        'FROM c3_dossier ORDER BY ref').fetchall()
    if not avec_archives:
        dossiers = [d for d in dossiers if d[1]]
    faits: dict[str, _Faits] = defaultdict(_Faits)
    marque = ','.join('?' * len(CLES_FAITS))
    for ref, upi, type_, cle, valeur, nombre, date in cx.execute(
            f'SELECT ref, upstream_piece_id, type, cle, valeur, nombre, date FROM c1_fait_retenu WHERE cle IN ({marque}) '
            'ORDER BY ref, upstream_piece_id', CLES_FAITS):
        faits[ref].ajouter(upi, type_, cle, valeur, nombre, date)
    naissance: dict[str, str] = {}
    for ref, d in cx.execute("SELECT ref, date_naissance FROM c1_mention_personne WHERE role = 'titulaire_cin' "
                             "AND rang = 0 AND date_naissance IS NOT NULL ORDER BY ref, upstream_piece_id"):
        naissance.setdefault(ref, d)
    associes: dict[str, int] = defaultdict(int)
    for ref, n in cx.execute("SELECT ref, max(n) FROM (SELECT ref, upstream_piece_id, count(*) AS n FROM "
                             "c1_mention_personne WHERE type_piece = 'STATUTS' AND role = 'associe' "
                             "GROUP BY ref, upstream_piece_id) x GROUP BY ref"):
        associes[ref] = n
    revenus: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for ref, source, upi, montant_ in cx.execute(
            "SELECT ref, source, upstream_piece_id, montant FROM c3_revenu WHERE nature = 'verifie' "
            'ORDER BY ref, upstream_piece_id, annee, mois'):
        revenus[ref][source].append((upi, montant_))
    banques: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for ref, type_, banque in cx.execute('SELECT ref, type_piece, banque FROM c3_compte WHERE banque IS NOT NULL '
                                         'ORDER BY ref, upstream_piece_id'):
        banques[ref].append((type_, banque))
    vehicules: dict[str, tuple[Any, Any, Any, str]] = {}
    for ref, etat, prix, marque_, upi in cx.execute(
            "SELECT ref, etat, prix, marque, upstream_piece_id FROM c3_vehicule "
            "WHERE type_piece = 'FACTURE_PROFORMA_VEHICULE' ORDER BY ref, upstream_piece_id"):
        vehicules.setdefault(ref, (etat, prix, marque_, upi))
    pieces = {ref: (n, r) for ref, n, r in cx.execute(
        "SELECT ref, count(*), sum(CASE WHEN source = 'REANALYSE' OR nb_champs_relus > 0 THEN 1 ELSE 0 END) "
        'FROM c1_piece GROUP BY ref')}
    releves = {ref: lues for ref, lues in cx.execute(
        'SELECT ref, max(CASE WHEN nb_operations_lues > 0 THEN 1 ELSE 0 END) FROM c1_releve_mois GROUP BY ref')}
    societes: dict[str, dict[str, Any]] = defaultdict(dict)
    for ref, role, nom in cx.execute("SELECT ref, role, nom_norm FROM c1_mention_societe WHERE role IN "
                                     "('employeur', 'concessionnaire') AND nom_norm IS NOT NULL "
                                     'ORDER BY ref, upstream_piece_id'):
        societes[ref].setdefault(role, nom)
    return [_ligne(d, faits[d[0]], naissance.get(d[0]), associes.get(d[0]), revenus.get(d[0], {}),
                   banques.get(d[0], []), vehicules.get(d[0]), pieces.get(d[0], (0, 0)), releves.get(d[0]),
                   societes.get(d[0], {})) for d in dossiers]


def _ligne(d: tuple, f: _Faits, naissance: Optional[str], nb_associes: Optional[int], revenus: dict,
           banques: list, vehicule: Optional[tuple], pieces: tuple, releve: Optional[int], societes: dict
           ) -> dict[str, Any]:
    (ref, actif, recu, tp, csp, produit, mode, categorie, verdict, provisoire, en_cours, statut, mineures, majeures,
     critiques, declare) = d
    reference = date_iso(recu) or (str(recu)[:10] if recu else None)
    a_verdict = verdict in VERDICTS and not provisoire and not en_cours
    pp, pm, auto = tp == 'PP', tp == 'PM', produit in ('AUTO_CLASSIQUE', 'LOA')
    x: dict[str, Any] = dict(ref=ref, actif=int(actif), date_reference=reference, semaine=semaine_iso(reference),
                             type_personne=tp, csp=csp, produit=produit, mode_paiement=mode, categorie=categorie,
                             verdict=verdict if a_verdict else SANS_VERDICT,
                             juge_suspect=int(verdict in ('SUSPECT', 'TRES_SUSPECT')) if a_verdict else None,
                             statut_analyse=statut, nb_alertes_mineures=mineures, nb_alertes_majeures=majeures,
                             nb_alertes_critiques=critiques)
    # personne
    x['age'] = age_revolu(naissance, reference) if pp else None
    x['tranche_age'] = tranche_age(x['age'])
    x['sexe'] = normaliser_sexe(f.premier(('CIN',), 'sexe')) if pp else None
    x['nationalite'] = normaliser_texte(f.premier(('CIN',), 'nationalite')) if pp else None
    emploi = ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE')
    x['situation_familiale'] = normaliser_texte(f.premier(emploi, 'situation_familiale'))
    x['personnes_a_charge'] = next((n for n in (_entier(v) for t in emploi
                                                 for v in f.valeurs(t, *CLES_PERSONNES_A_CHARGE)) if n is not None), None)
    # revenu : bulletin le plus récent (mois de paie), attestation, pension, relevé
    mois_paie = {u: date_iso('01/' + str(v)) or '' for u, v, _n, _d in f.par.get(('BULLETIN_DE_PAIE', 'mois_paie'), ())}
    x['revenu_verifie'], x['source_revenu'] = choisir_revenu(
        bulletins=[(mois_paie.get(u, ''), m) for u, m in revenus.get('BULLETIN_DE_PAIE', ())],
        attestations=[m for _u, m in revenus.get('ATTESTATION_TRAVAIL_SALAIRE', ())],
        pensions=[m for _u, m in revenus.get('ATTESTATION_PENSION', ())],
        releves=[m for _u, m in revenus.get('RELEVE_BANCAIRE', ())])
    x['tranche_revenu'] = tranche_revenu(x['revenu_verifie'])
    x['revenu_declare'] = declare if declare is not None and declare > 0 else None
    x['ecart_revenu'] = ecart_relatif(x['revenu_verifie'], x['revenu_declare'])
    x['tranche_ecart_revenu'] = tranche_ecart(x['ecart_revenu'])
    x['anciennete_emploi'] = annees_entre(f.date(emploi, 'date_embauche'), reference)
    x['tranche_anciennete'] = tranche_anciennete(x['anciennete_emploi'])
    x['type_contrat'] = normaliser_contrat(f.premier(('ATTESTATION_TRAVAIL_SALAIRE',), 'type_contrat'))
    banque = next((b for t in ('RELEVE_BANCAIRE', 'ATTESTATION_RIB') for tt, b in banques if tt == t), None)
    x['banque'] = normaliser_banque(banque)
    # ville
    x['ville'], x['source_ville'] = choisir_ville(
        domiciliation=f.valeurs('DOMICILIATION', 'ville', 'adresse'),
        cin=f.valeurs('CIN', 'ville_residence', 'adresse'),
        releve=f.valeurs('RELEVE_BANCAIRE', 'ville', 'adresse'))
    x['region'] = REGION_DE_VILLE.get(x['ville']) if x['ville'] else None
    # véhicule (AUTO et LOA)
    etat, prix, marque_, upi = vehicule if auto and vehicule else (None, None, None, None)
    x['vehicule_etat'] = normaliser_etat(etat)
    x['prix_vehicule'] = prix if prix is not None and prix > 0 else None
    x['tranche_prix_vehicule'] = tranche_prix(x['prix_vehicule'])
    x['marque_vehicule'] = normaliser_texte(marque_)
    avance = f.montant_de('FACTURE_PROFORMA_VEHICULE', ('montant_avance',), upi) if upi else []
    x['apport_pct'] = (round(avance[0][1] / x['prix_vehicule'], 4)
                       if avance and avance[0][1] is not None and x['prix_vehicule'] else None)
    # société (PM)
    x['age_societe'] = annees_entre(f.date(('REGISTRE_COMMERCE',), 'date_creation'), reference) if pm else None
    x['tranche_age_societe'] = tranche_age_societe(x['age_societe'])
    x['associe_unique'] = (int(nb_associes == 1) if nb_associes else None) if pm else None
    capital = (f.montant_de('STATUTS', ('capital_social',)) or f.montant_de('REGISTRE_COMMERCE', ('capital_social',))
               ) if pm else []
    x['capital_tranche'] = tranche_capital(capital[0][1]) if capital else None
    # pièces et relevés
    x['nb_pieces'], x['nb_pieces_relues'] = pieces[0], pieces[1] or 0
    x['taux_relecture'] = round(x['nb_pieces_relues'] / x['nb_pieces'], 4) if x['nb_pieces'] else None
    x['releve_lignes_lues'] = releve
    x['employeur'] = societes.get('employeur')
    x['concessionnaire'] = societes.get('concessionnaire')
    return x


def ecrire(cx: Any, lignes: list[dict[str, Any]]) -> None:
    cx.execute('DELETE FROM c7_variable_dossier')
    cx.executemany(f'INSERT INTO c7_variable_dossier ({", ".join(COLONNES)}) VALUES ({", ".join("?" * len(COLONNES))})',
                   [tuple(x[c] for c in COLONNES) for x in lignes])


def ville_de_decoupage(lignes: list[dict[str, Any]], seuil: int) -> dict[str, str]:
    """Ville → libellé de découpage : la ville si elle compte au moins `seuil` dossiers, sinon « autres villes »."""
    comptes: dict[str, int] = defaultdict(int)
    for x in lignes:
        if x['ville']:
            comptes[x['ville']] += 1
    return {v: (v if n >= seuil else 'autres villes') for v, n in comptes.items()}

