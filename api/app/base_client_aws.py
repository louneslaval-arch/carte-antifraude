"""Adaptateur de lecture AWS pour les tables EQDOM af_*.

Version de transition : contrats JSON des routes existantes, sans migration SQL.
Les données sans équivalent dans AWS sont retournées en listes vides, jamais inventées.
La connexion PostgreSQL reste en lecture seule.
"""

import random
import secrets

import psycopg
from psycopg.rows import dict_row

from .base_client_postgresql import (
    LIBELLES_NIVEAU, LIBELLES_ROLE, compte, masquer_groupe, trier,
)


def _type_identite(valeur):
    v = (valeur or '').lower()
    return 'societe' if v in ('pm', 'societe', 'morale', 'personne_morale') or 'morale' in v else 'personne'


def _niveau(valeur):
    """Le champ AWS mesure la certitude, pas la gravité de fraude.

    'affiche' indique un lien à présenter ; 'hors_alerte' un indice faible.
    Jamais de conversion automatique de 'certain' en 'critique'.
    """
    v = (valeur or '').lower()
    if v in ('indice faible',):
        return 'hors_alerte'
    if v in ('certain', 'probable', 'à vérifier', 'indice') or v.startswith('réseau à '):
        return 'affiche'
    return v if v in LIBELLES_NIVEAU and v is not None else None


def _rang(niveau):
    return ('critique', 'majeure', 'mineure', 'affiche', 'hors_alerte', None).index(niveau)


class BaseClient:
    def __init__(self, chemin, donnees_reelles=False):
        self.chemin = chemin
        self.epoque = secrets.token_hex(8)
        with self.connexion() as cx:
            colonnes = {r['column_name'] for r in cx.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'af_identite'")}
            if 'identite_id' not in colonnes:
                raise RuntimeError('Schéma AWS EQDOM introuvable : af_identite.identite_id absent')
            if not donnees_reelles and cx.execute(
                "SELECT EXISTS (SELECT 1 FROM af_identite WHERE cin_norm IS NOT NULL "
                "AND cin_norm <> '' AND cin_norm NOT LIKE 'ZZ%')").fetchone()['exists']:
                raise PermissionError('Données réelles : activer explicitement CARTE_DONNEES_REELLES')
            fiches = [r['identite_id'] for r in cx.execute('SELECT identite_id FROM af_identite')]
            dossiers = [r['ref'] for r in cx.execute('SELECT ref FROM af_dossier')]
            tirage = random.SystemRandom().sample(range(100_000, 50_000_000), len(fiches) + len(dossiers))
            self.indice_fiche = dict(zip(fiches, tirage))
            self.fiche_de = {v: k for k, v in self.indice_fiche.items()}
            self.indice_dossier = dict(zip(dossiers, tirage[len(fiches):]))
            self.dossier_de = {v: k for k, v in self.indice_dossier.items()}
            self.inscrits = set()
            self.chemins_dossier = {}
            self.niveau_dossier = {}
            self._charger_liens(cx)

    def connexion(self):
        return psycopg.connect(self.chemin, row_factory=dict_row, autocommit=True,
                               options='-c default_transaction_read_only=on', connect_timeout=8)

    def _charger_liens(self, cx):
        """Reprend les niveaux connus seulement ; aucune règle frauduleuse inférée."""
        for row in cx.execute('SELECT dossier_ref, identite_id, regle, niveau, cible, detail FROM af_lien'):
            ref = row['dossier_ref']
            if ref not in self.indice_dossier:
                continue
            niveau = _niveau(row['niveau'])
            chemin = dict(niveau=niveau, niveau_libelle=LIBELLES_NIVEAU[niveau], force=0,
                          longueur=1, homonymie=False, foyer=False,
                          regle=row['regle'], detail=row['detail'],
                          identite_id=row['identite_id'], cible=row['cible'], etapes=[])
            self.chemins_dossier.setdefault(ref, []).append(chemin)
        for ref, chemins in self.chemins_dossier.items():
            valides = [x['niveau'] for x in chemins if x['niveau']]
            self.niveau_dossier[ref] = min(valides, key=_rang) if valides else None

    def est_fiche(self, indice):
        return indice in self.fiche_de

    def resume(self):
        with self.connexion() as cx:
            un = lambda sql: next(iter(cx.execute(sql).fetchone().values()))
            actifs = {r['ref'] for r in cx.execute('SELECT ref FROM af_dossier WHERE actif = 1')}
            niveaux = {}
            for ref in actifs:
                n = self.niveau_dossier.get(ref)
                niveaux[n] = niveaux.get(n, 0) + 1
            def repartition(champ):
                return masquer_groupe([dict(valeur=r['valeur'] or 'non renseigné', nombre=compte(r['n']))
                    for r in cx.execute(f'SELECT {champ} AS valeur, count(*) AS n FROM af_dossier '
                                        f'WHERE actif = 1 GROUP BY {champ} ORDER BY n DESC')])
            return dict(
                clients=compte(un("SELECT count(DISTINCT identite_id) FROM af_dossier_identite "
                                 "WHERE lower(role) IN ('demandeur', 'societe_cliente')")),
                dossiers=compte(len(actifs)),
                dossiers_lies=compte(sum(niveaux.get(k, 0) for k in ('critique', 'majeure', 'affiche'))),
                societes_registre=compte(un("SELECT count(*) FROM af_identite WHERE lower(type_identite) IN ('pm','societe','morale','personne_morale')")),
                inscrits=compte(un('SELECT count(*) FROM bl_entite')),
                mise_a_jour=un('SELECT max(recu_le) FROM af_dossier'),
                produits=repartition('produit'), csp=repartition('csp'),
                niveaux=masquer_groupe([dict(niveau=k or 'aucun', libelle=LIBELLES_NIVEAU[k],
                                               nombre=compte(niveaux.get(k, 0)))
                                        for k in ('critique', 'majeure', 'mineure', 'affiche', 'hors_alerte', None)]),
                incoherences=[])

    def clients(self):
        if hasattr(self, '_clients'):
            return self._clients
        with self.connexion() as cx:
            rows = cx.execute('SELECT i.identite_id, i.type_identite, i.nom, i.ville_code, '
                'd.ref, d.produit, d.recu_le FROM af_identite i '
                'JOIN af_dossier_identite x ON x.identite_id = i.identite_id '
                "JOIN af_dossier d ON d.ref = x.dossier_ref WHERE lower(x.role) IN "
                "('demandeur', 'societe_cliente')").fetchall()
            groupes = {}
            for r in rows:
                k = r['identite_id']
                g = groupes.setdefault(k, dict(nom=r['nom'] or '—', type=_type_identite(r['type_identite']),
                                                 ville=r['ville_code'], refs=set(), produits=set(), dates=[]))
                g['refs'].add(r['ref'])
                if r['produit']: g['produits'].add(r['produit'])
                if r['recu_le']: g['dates'].append(r['recu_le'])
            result = []
            for k, g in groupes.items():
                ns = [self.niveau_dossier.get(r) for r in g['refs']]
                n = min(ns, key=_rang, default=None)
                result.append(dict(indice=self.indice_fiche[k], nom=g['nom'], type=g['type'],
                                   dossiers=len(g['refs']), produits=sorted(g['produits']),
                                   derniere_demande=max(g['dates'], default=None), ville=g['ville'],
                                   inscrit=k in self.inscrits, niveau=n, niveau_libelle=LIBELLES_NIVEAU[n],
                                   incoherences=0, revenu=None))
            result.sort(key=lambda c: (_rang(c['niveau']), c['nom']))
            self._clients = result
            return result

    def rechercher(self, texte=None, type_=None, niveau=None, produit=None, avec_incoherence=None,
                   page=1, taille=50, tri='gravite'):
        items = self.clients()
        if texte: items = [x for x in items if texte.strip().upper() in x['nom'].upper()]
        if type_: items = [x for x in items if x['type'] == type_]
        if niveau: items = [x for x in items if (x['niveau'] or 'aucun') == niveau]
        if produit: items = [x for x in items if produit in x['produits']]
        if avec_incoherence: items = [x for x in items if x['incoherences']]
        items = trier(items, tri)
        start = (page - 1) * taille
        return dict(items=items[start:start + taille], total=len(items), page=page, taille=taille)

    def _nom(self, cx, identite_id):
        r = cx.execute('SELECT nom FROM af_identite WHERE identite_id = %s', (identite_id,)).fetchone()
        return (r or {}).get('nom') or '—'

    def _resume_dossier(self, row, identite_id=None, demandeur=False):
        ref = row['ref']
        n = self.niveau_dossier.get(ref) if demandeur else None
        return dict(indice=self.indice_dossier[ref], produit=row['produit'],
                    csp=row['csp'] if demandeur else None,
                    paiement=row['mode_paiement'] if demandeur else None,
                    verdict=row['verdict'] if demandeur else None,
                    categorie=row['categorie'], analyse=row['statut_analyse'], actif=bool(row['actif']),
                    recu=row['recu_le'], ville=row['ville_code'],
                    revenu_declare=row['revenu_declare'] if demandeur else None,
                    role='demandeur' if demandeur else 'cité', demandeur=demandeur,
                    niveau=n, niveau_libelle=LIBELLES_NIVEAU[n], incoherences=None)

    def _identifiants(self, r):
        return [dict(type=k, valeur=r[v], dossier=None) for k, v in
                (('CIN', 'cin_norm'), ('RC', 'rc_num'), ('ICE', 'ice')) if r[v]]

    def _chemins(self, cx, ref, identite_id=None):
        return [dict(dossier=self.indice_dossier[ref], niveau=ch['niveau'],
                     niveau_libelle=ch['niveau_libelle'], force=ch['force'], longueur=ch['longueur'],
                     homonymie=False, foyer=False, regle=ch['regle'], detail=ch['detail'],
                     inscrit=dict(indice=None, nom='Correspondance liste noire'), etapes=[])
                for ch in self.chemins_dossier.get(ref, [])
                if identite_id is None or ch['identite_id'] == identite_id]

    def fiche(self, indice):
        identite_id = self.fiche_de.get(indice)
        if identite_id is None: return None
        with self.connexion() as cx:
            r = cx.execute('SELECT * FROM af_identite WHERE identite_id = %s', (identite_id,)).fetchone()
            if not r: return None
            personne = _type_identite(r['type_identite']) == 'personne'
            identite = dict(type='personne' if personne else 'societe', nom=r['nom'],
                            adresse=r['adresse'], inscrit=identite_id in self.inscrits)
            if personne:
                identite.update(cin=r['cin_norm'], date_naissance=r['date_naissance'])
            else:
                identite.update(rc=r['rc_num'], tribunal=r['tribunal_code'], ice=r['ice'])
            associations = cx.execute('SELECT x.dossier_ref, x.role, d.* FROM af_dossier_identite x '
                'JOIN af_dossier d ON d.ref = x.dossier_ref WHERE x.identite_id = %s', (identite_id,)).fetchall()
            refs = [a['dossier_ref'] for a in associations]
            dossiers = [self._resume_dossier(a, identite_id,
                (a['role'] or '').lower() in ('demandeur', 'societe_cliente')) for a in associations]
            dossiers.sort(key=lambda d: d['recu'] or '', reverse=True)
            relations = cx.execute('SELECT pp_identite_id, pm_identite_id, role, source '
                'FROM af_relation WHERE pp_identite_id = %s OR pm_identite_id = %s',
                (identite_id, identite_id)).fetchall()
            societes, personnes = [], []
            for rel in relations:
                autre = rel['pm_identite_id'] if rel['pp_identite_id'] == identite_id else rel['pp_identite_id']
                if autre not in self.indice_fiche: continue
                item = dict(indice=self.indice_fiche[autre], nom=self._nom(cx, autre),
                            role=LIBELLES_ROLE.get(rel['role'], rel['role']), source=rel['source'],
                            inscrit=autre in self.inscrits)
                (societes if personne else personnes).append(item)
            chemins = []
            for ref in refs: chemins.extend(self._chemins(cx, ref, identite_id))
            contexte = [dict(libelle=k, valeur=r[v]) for k, v in
                        (('Nom', 'nom'), ('Adresse', 'adresse')) if r[v]]
            propres = {a['dossier_ref'] for a in associations if
                       (a['role'] or '').lower() in ('demandeur', 'societe_cliente')}
            return dict(indice=indice, identite=identite, alias=[], adresses=[], sources={},
                        dossiers=dossiers, societes=societes, personnes=personnes, revenus=[], comptes=[],
                        vehicules=[], chemins=chemins[:5], charges=[], operations=[], incoherences=[],
                        identifiants=self._identifiants(r), donnees=[dict(dossier=self.indice_dossier[ref],
                        reference=ref, demandeur=ref in propres,
                        contexte=contexte if ref in propres else [], pieces=[], controles=[])
                        for ref in refs], liste_noire=[], registre=[])

    def tous_dossiers(self, page=1, taille=25):
        with self.connexion() as cx:
            total = cx.execute('SELECT count(*) AS n FROM af_dossier').fetchone()['n']
            rows = cx.execute('SELECT d.ref, d.produit, d.recu_le, d.actif, '
                'EXISTS(SELECT 1 FROM af_dossier_identite x WHERE x.dossier_ref = d.ref) AS avec_demandeur, '
                '(SELECT count(*) FROM af_lien l WHERE l.dossier_ref = d.ref) AS alertes, '
                '(SELECT count(*) FROM af_relation r WHERE r.dossier_ref = d.ref) AS relations '
                'FROM af_dossier d ORDER BY d.recu_le DESC NULLS LAST, d.ref LIMIT %s OFFSET %s',
                (taille, (page - 1) * taille)).fetchall()
            return dict(items=[dict(indice=self.indice_dossier[r['ref']], reference=r['ref'],
                     produit=r['produit'], recu=r['recu_le'], actif=bool(r['actif']),
                     avec_demandeur=r['avec_demandeur'], alertes=r['alertes'], relations=r['relations'])
                     for r in rows], total=total, page=page, taille=taille)

    def dossier(self, indice):
        ref = self.dossier_de.get(indice)
        if ref is None: return None
        with self.connexion() as cx:
            d = cx.execute('SELECT * FROM af_dossier WHERE ref = %s', (ref,)).fetchone()
            if not d: return None
            entete = self._resume_dossier(d, demandeur=True)
            entete['reference'] = ref
            parties = []
            for r in cx.execute('SELECT i.identite_id, i.nom, i.type_identite, x.role '
                    'FROM af_dossier_identite x JOIN af_identite i ON i.identite_id = x.identite_id '
                    'WHERE x.dossier_ref = %s', (ref,)):
                role = (r['role'] or '').lower()
                parties.append(dict(indice=self.indice_fiche.get(r['identite_id']), nom=r['nom'] or '—',
                    type=_type_identite(r['type_identite']), role=LIBELLES_ROLE.get(role, role),
                    demandeur=role in ('demandeur', 'societe_cliente'), inscrit=False))
            liens = cx.execute('SELECT regle, niveau, detail FROM af_lien WHERE dossier_ref = %s',
                               (ref,)).fetchall()
            alertes = [dict(code=r['regle'], nature='rapprochement', niveau=r['niveau'],
                            libelle=r['regle'], justification=r['detail']) for r in liens]
            relations = [dict(code=r['role'], libelle=LIBELLES_ROLE.get(r['role'], r['role']),
                              fiche_associee=r['pp_identite_id'] in self.indice_fiche or
                              r['pm_identite_id'] in self.indice_fiche)
                         for r in cx.execute('SELECT role, pp_identite_id, pm_identite_id FROM af_relation '
                                             'WHERE dossier_ref = %s', (ref,))]
            return dict(indice=indice, entete=entete, pieces=[], parties=parties, revenus=[], charges=[],
                        operations=[], vehicules=[], incoherences=[], controles=[],
                        chemins=self._chemins(cx, ref)[:3], relations_c7=relations, alertes_c6=alertes)

    def reseau(self, indice, profondeur=2, limite=120):
        """Réseau des identités et signaux explicites de rapprochement af_lien.

        Les signaux sont distincts des entités inscrites : af_lien ne prouve pas
        à lui seul que l'identité source figure sur une liste noire.
        """
        depart = self.fiche_de.get(indice)
        if depart is None: return None
        with self.connexion() as cx:
            connus, liens, front = {depart: 0}, [], [depart]
            for distance in range(1, profondeur + 1):
                suivant = []
                for identite in front:
                    for r in cx.execute('SELECT pp_identite_id, pm_identite_id, role FROM af_relation '
                            'WHERE pp_identite_id = %s OR pm_identite_id = %s', (identite, identite)):
                        autre = r['pm_identite_id'] if r['pp_identite_id'] == identite else r['pp_identite_id']
                        if autre not in self.indice_fiche: continue
                        if autre not in connus:
                            if len(connus) >= limite: continue
                            connus[autre] = distance
                            suivant.append(autre)
                        liens.append(dict(de=self.indice_fiche[identite], vers=self.indice_fiche[autre],
                                          code=LIBELLES_ROLE.get(r['role'], r['role'])))
                front = suivant
            types = {r['identite_id']: _type_identite(r['type_identite']) for r in cx.execute(
                'SELECT identite_id, type_identite FROM af_identite WHERE identite_id = ANY(%s)',
                (list(connus),))}
            noeuds = [dict(id=self.indice_fiche[i], type=types.get(i, 'personne'), nom=self._nom(cx, i),
                          niveau=distance, inscrit=i in self.inscrits, depart=i == depart)
                      for i, distance in connus.items()]
            # Signaux issus des rapprochements AWS : ne jamais exposer cible_id,
            # cle_valeur ni les identifiants internes dans la réponse du graphe.
            signaux = cx.execute(
                'SELECT lien_id, identite_id, regle, niveau FROM af_lien '
                'WHERE identite_id = ANY(%s) ORDER BY lien_id LIMIT %s',
                (list(connus), max(0, limite - len(noeuds)))).fetchall()
            for s in signaux:
                ident = s['identite_id']
                if ident not in connus:
                    continue
                signal_id = f"signal{len(noeuds)}"
                code = s['regle'] or 'signal'
                noeuds.append(dict(id=signal_id, type='identifiant', nom=f'Signal {code}',
                                   niveau=connus[ident] + 1, inscrit=False, depart=False))
                liens.append(dict(de=self.indice_fiche[ident], vers=signal_id, code=code))
            uniques = list({(l['de'], l['vers'], l['code']): l for l in liens}.values())
            return dict(noeuds=noeuds, liens=uniques)

    def fiches_nommees(self, objet):
        trouves, pile = set(), [objet]
        while pile:
            item = pile.pop()
            if isinstance(item, dict):
                for k, v in item.items():
                    if k in ('indice', 'id') and isinstance(v, int) and v in self.fiche_de:
                        trouves.add(v)
                    elif isinstance(v, (dict, list)): pile.append(v)
            elif isinstance(item, list): pile.extend(item)
        return trouves
