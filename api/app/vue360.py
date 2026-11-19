"""Vue 360° d'une entité : profil (personne salariée, personne entrepreneur, personne morale), synthèse des revenus et
contrôles de la v2 rangés par famille, dans l'ordre utile au profil. Fonctions pures, appelées par la fiche.

Profil d'une personne : la CSP de son dernier dossier de demandeur (valeurs de `Csp` de la v2) ; sans CSP parlante
(aucun dossier propre, ou « AUTRE »), un rôle en cours de gérant, d'associé ou de dirigeant au registre ou dans un
dossier en fait un entrepreneur. Un salarié qui est aussi associé garde le profil salarié ; ses sociétés passent en
bandeau. Les retraités sont rangés avec les salariés (la pension tient lieu de salaire)."""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
from pipeline.analytique.controles import CATALOGUE, FAMILLES  # noqa: E402

CSP_SALARIE = frozenset({'SALARIE_PRIVE', 'FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE'})
CSP_RETRAITE = frozenset({'RETRAITE_PUBLIC', 'RETRAITE_CIMR', 'RETRAITE_INDETERMINE'})
CSP_INDEPENDANT = frozenset({'PROFESSION_LIBERALE', 'LOUEUR'})
ROLES_EN_COURS = frozenset({'gerant', 'associe', 'dirigeant', 'nouveau_gerant', 'associe_present', 'administrateur',
                            'representant'})
LIBELLES_EN_COURS = frozenset({'gérant', 'associé', 'dirigeant', 'nouveau gérant', 'associé présent', 'administrateur',
                               'représentant'})

# Familles de contrôles (préfixe du controlId), de la plus utile à la moins utile pour chaque profil.
ORDRE = {
    'salarie': ('EMP', 'IDT', 'BNQ', 'BLG', 'AUT', 'PRO'),
    'entrepreneur': ('PRO', 'IDT', 'BNQ', 'BLG', 'AUT', 'EMP'),
    'pm': ('IDT', 'BLG', 'BNQ', 'PRO', 'AUT', 'EMP'),
}
SOURCES_REVENU = ('BULLETIN_DE_PAIE', 'ATTESTATION_TRAVAIL_SALAIRE', 'ATTESTATION_PENSION', 'RELEVE_BANCAIRE')


def profil(type_fiche, csp, roles):
    """(profil, retraité) : `type_fiche` « personne » ou « societe », `csp` du dernier dossier propre (ou None),
    `roles` bruts de la fiche dans les sociétés (registre et dossiers)."""
    if type_fiche == 'societe':
        return 'pm', False
    if csp in CSP_RETRAITE:
        return 'salarie', True
    if csp in CSP_SALARIE:
        return 'salarie', False
    if csp in CSP_INDEPENDANT:
        return 'entrepreneur', False
    return ('entrepreneur' if ROLES_EN_COURS & set(roles) else 'salarie'), False


def aussi(prof, societes):
    """Sociétés d'un salarié où il a un rôle en cours (gérant, associé…) : bandeau « aussi associé de… »."""
    if prof != 'salarie':
        return []
    return [s for s in societes if s.get('role') in LIBELLES_EN_COURS]


def synthese_revenus(revenus):
    """Dernier montant déclaré, dernier montant lu sur chaque pièce de revenu, écart relatif entre pièces
    ((plus haut − plus bas) / plus haut, None sous deux pièces)."""
    def cle(r):
        return (r.get('annee') or 0, r.get('mois') or 0)
    declare, pieces, rang = None, {}, {}
    for r in sorted(revenus, key=cle):
        if r['nature'] == 'declare':
            declare = r['montant']
        elif r['source'] in SOURCES_REVENU and cle(r) >= rang.get(r['source'], (-1, -1)):
            pieces[r['source']], rang[r['source']] = r['montant'], cle(r)
    montants = [m for m in pieces.values() if m]
    ecart = (max(montants) - min(montants)) / max(montants) if len(montants) >= 2 else None
    return dict(declare=declare, pieces=pieces, ecart=ecart)


def controles(donnees, prof):
    """Contrôles des dossiers propres, avec libellé, criticité et description du catalogue, par famille ; les
    anomalies d'abord dans chaque famille ; les familles dans l'ordre du profil, « Autres » à la fin."""
    par_famille = {}
    for x in donnees:
        for c in x.get('controles') or []:
            cid = c['controle']
            lib, crit, desc = CATALOGUE.get(cid, (cid, None, None))
            famille = FAMILLES.get(cid.split('-')[0], 'Autres')
            par_famille.setdefault(famille, []).append(dict(
                controle=cid, libelle=lib, criticite=c.get('criticite') or crit, description=desc,
                resultat=c['resultat'], dossier=x.get('dossier')))
    ordre = [FAMILLES[p] for p in ORDRE[prof]]
    sortie = []
    for famille in sorted(par_famille, key=lambda f: (ordre.index(f) if f in ordre else len(ordre), f)):
        lignes = sorted(par_famille[famille], key=lambda c: (c['resultat'] != 'ANOMALIE', c['controle']))
        sortie.append(dict(famille=famille, controles=lignes,
                           anomalies=sum(c['resultat'] == 'ANOMALIE' for c in lignes)))
    return sortie
