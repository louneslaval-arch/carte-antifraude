"""Lecture de la base client (couches c0 à c5) pour les pages : clients, fiches, dossiers, réseau.

La base est ouverte en lecture seule. Les identifiants internes (fiches `pp_…`, `pm_…`, références de dossier,
nœuds d'identifiant) ne sortent jamais : chaque fiche et chaque dossier reçoit, au chargement, un indice entier
tiré au hasard, seul identifiant qui passe dans une URL ou une réponse. Les chemins vers la liste noire sont
calculés une fois au chargement (c5) ; une nouvelle base se charge en redémarrant le service.

Aucun chiffre agrégé sous 5 (« < 5 ») ; aucune valeur d'identité dans un message d'erreur ni dans le journal.
"""

import os
import random
import re
import secrets
import sys

import psycopg

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from pipeline.couches import c5_graphe_postgresql as c5_graphe  # noqa: E402


class LigneCompatible:
    """Résultat PostgreSQL utilisable par indice, par nom et avec dict()."""

    def __init__(self, colonnes, valeurs):
        self._colonnes = colonnes
        self._valeurs = valeurs
        self._par_nom = dict(zip(colonnes, valeurs))

    def __getitem__(self, cle):
        return self._valeurs[cle] if isinstance(cle, (int, slice)) else self._par_nom[cle]

    def __iter__(self):
        return iter(self._valeurs)

    def __len__(self):
        return len(self._valeurs)

    def keys(self):
        return self._colonnes


def lignes_compatibles(curseur):
    colonnes = tuple(col.name for col in curseur.description)
    return lambda valeurs: LigneCompatible(colonnes, valeurs)

SEUIL = 5
NIVEAUX = ('critique', 'majeure', 'mineure', 'affiche', 'hors_alerte')
LIBELLES_NIVEAU = {'critique': 'Critique', 'majeure': 'Majeure', 'mineure': 'Mineure', 'affiche': 'Affiché',
                   'hors_alerte': 'Hors alerte', None: 'Aucun lien'}
LIBELLES_ROLE = {
    'titulaire_cin': 'titulaire de la CIN', 'employe': 'salarié', 'pensionne': 'pensionné', 'gerant': 'gérant',
    'dirigeant': 'dirigeant', 'associe': 'associé', 'associe_present': 'associé présent', 'nouveau_gerant':
    'nouveau gérant', 'proprietaire': 'propriétaire du véhicule', 'acheteur': 'acheteur', 'titulaire_compte':
    'titulaire du compte', 'titulaire_quittance': 'titulaire de la quittance', 'liquidateur': 'liquidateur',
    'cessionnaire': 'cessionnaire', 'cedant': 'cédant', 'gerant_sortant': 'gérant sortant', 'associe_sortant':
    'associé sortant', 'representant': 'représentant', 'administrateur': 'administrateur', 'inconnu': 'rôle inconnu',
    'societe': 'société', 'employeur': 'employeur', 'concessionnaire': 'concessionnaire'}
LIBELLES_INCOHERENCE = {
    'salaire_bulletin_releve': 'Salaire du bulletin différent du relevé',
    'adresse_cin_differente': 'Adresse de la CIN différente',
    'double_financement': 'Même châssis dans un autre dossier',
    'rib_autre_dossier': 'Même RIB dans le dossier d\'une autre personne',
    'dossiers_en_rafale': 'Dossiers en rafale',
    'employeur_absent_du_registre': 'Employeur absent du registre'}
LIBELLES_C7 = {
    'caution': 'Caution', 'coemprunteur': 'Co-emprunteur',
    'reference_personnelle': 'Référence personnelle', 'signataire': 'Signataire',
    'cabinet_comptable': 'Cabinet comptable', 'meme_immeuble': 'Même immeuble'}


def compte(n):
    """Un comptage affichable : 0, ou au moins 5 ; sinon « < 5 »."""
    return n if n == 0 or n >= SEUIL else '< 5'


def masquer_rib(rib):
    return f'••• {rib[-4:]}' if rib else None


SUITE_LONGUE = re.compile(r'\d(?:[ .-]?\d){15,}')       # RIB (24 chiffres) ou tout numéro de compte, espacé ou non


def masquer_numeros(valeur):
    """Masque tout numéro de compte dans un texte, quelle que soit la clé qui le porte (libellé, explication…)."""
    if not isinstance(valeur, str):
        return valeur
    return SUITE_LONGUE.sub(lambda m: masquer_rib(re.sub(r'\D', '', m.group())), valeur)


def masquer_groupe(lignes, cle='nombre'):
    """Masquage secondaire : un seul compte masqué dans un groupe se retrouverait par différence avec le total ;
    on masque alors aussi le plus petit compte affiché non nul."""
    masques = [x for x in lignes if x[cle] == '< 5']
    if len(masques) == 1:
        visibles = [x for x in lignes if isinstance(x[cle], int) and x[cle] > 0]
        if visibles:
            min(visibles, key=lambda x: x[cle])[cle] = '< 5'
    return lignes


def trier(lignes, tri):
    """Ordre de la liste des clients. « gravite » : l'ordre calculé par `clients()` (niveau, incohérences, nom).
    Les autres : la clé choisie, puis le nom ; une valeur absente (date, revenu) va toujours en fin de liste."""
    if tri == 'gravite':
        return lignes
    nom = lambda c: (c['nom'] or '').upper()
    if tri in ('alpha', 'alpha_inverse'):
        return sorted(lignes, key=lambda c: (nom(c), c['indice']), reverse=tri == 'alpha_inverse')
    if tri == 'dossiers':
        return sorted(lignes, key=lambda c: (-c['dossiers'], nom(c)))
    cle = {'recent': 'derniere_demande', 'ancien': 'derniere_demande', 'revenu': 'revenu'}[tri]
    presents = [c for c in lignes if c[cle] is not None]
    absents = sorted((c for c in lignes if c[cle] is None), key=nom)
    presents.sort(key=nom)                                   # à valeur égale, ordre alphabétique (tri stable)
    presents.sort(key=lambda c: c[cle], reverse=tri != 'ancien')
    return presents + absents


class BaseClient:
    def __init__(self, chemin, donnees_reelles=False):
        """`chemin` est désormais une chaîne de connexion PostgreSQL (DSN)."""
        self.chemin = chemin
        self.epoque = secrets.token_hex(8)
        cx = self.connexion()
        try:
            non_fictifs = cx.execute("SELECT count(*) FROM c2_personne WHERE cin IS NOT NULL AND cin NOT LIKE 'ZZ%'"
                                     ).fetchone()[0]
            if non_fictifs and not donnees_reelles:
                raise PermissionError('base client non fictive refusée sans le garde-fou des données réelles')
            self._indexer(cx)
            self._chemins(cx)
        finally:
            cx.close()

    def est_fiche(self, indice):
        return indice in self.fiche_de

    def connexion(self):
        return psycopg.connect(
            self.chemin,
            row_factory=lignes_compatibles,
            autocommit=True,
            options='-c default_transaction_read_only=on',
        )

    # ---- indices opaques -------------------------------------------------------------------------------------------
    def _indexer(self, cx):
        hasard = random.SystemRandom()
        fiches = [r[0] for r in cx.execute('SELECT identifiant FROM c2_personne UNION ALL '
                                           'SELECT identifiant FROM c2_societe')]
        dossiers = [r[0] for r in cx.execute('SELECT ref FROM c3_dossier')]
        tirage = hasard.sample(range(100_000, 10_000_000), len(fiches) + len(dossiers))
        self.indice_fiche = dict(zip(fiches, tirage))
        self.fiche_de = {v: k for k, v in self.indice_fiche.items()}
        self.indice_dossier = dict(zip(dossiers, tirage[len(fiches):]))
        self.dossier_de = {v: k for k, v in self.indice_dossier.items()}
        self.inscrits = {r[0] for r in cx.execute('SELECT identifiant FROM c2_personne WHERE inscrit = 1 UNION '
                                                  'SELECT identifiant FROM c2_societe WHERE inscrit = 1')}

    # ---- chemins vers la liste noire, calculés une fois ------------------------------------------------------------
    def _chemins(self, cx):
        contexte = c5_graphe.Contexte(cx)
        self.chemins_dossier = {}
        for ref in self.indice_dossier:
            self.chemins_dossier[ref] = c5_graphe.chemins(cx, ref, contexte)
        self.niveau_dossier = {ref: (ch[0]['niveau'] if ch else None) for ref, ch in self.chemins_dossier.items()}

    @staticmethod
    def _rang(niveau):
        return NIVEAUX.index(niveau) if niveau in NIVEAUX else len(NIVEAUX)

    # ---- résumé (aucun nom) ----------------------------------------------------------------------------------------
    def resume(self):
        cx = self.connexion()
        try:
            un = lambda sql: cx.execute(sql).fetchone()[0]  # noqa: E731
            clients = un('SELECT count(DISTINCT fiche) FROM c3_demandeur')
            dossiers = un('SELECT count(*) FROM c3_dossier WHERE actif = 1')
            mise_a_jour = un('SELECT max("updatedAt") FROM c3_dossier')

            def repartition(sql):
                return [dict(valeur=v or 'non renseigné', nombre=compte(n)) for v, n in cx.execute(sql)]
            actifs = {r for r, in cx.execute('SELECT ref FROM c3_dossier WHERE actif = 1')}
            niveaux = {}
            for ref, niveau in self.niveau_dossier.items():
                if ref in actifs:
                    niveaux[niveau] = niveaux.get(niveau, 0) + 1
            return dict(
                clients=compte(clients), dossiers=compte(dossiers),
                dossiers_lies=compte(niveaux.get('critique', 0) + niveaux.get('majeure', 0)),
                societes_registre=compte(un("SELECT count(*) FROM c2_societe")),
                inscrits=compte(un('SELECT count(*) FROM ref_liste_noire WHERE active = 1')),
                mise_a_jour=mise_a_jour,
                produits=masquer_groupe(repartition('SELECT "productType", count(*) FROM c3_dossier WHERE actif = 1 '
                                                    'GROUP BY 1 ORDER BY 2 DESC')),
                csp=masquer_groupe(repartition('SELECT csp, count(*) FROM c3_dossier WHERE actif = 1 GROUP BY 1 ORDER BY 2 DESC')),
                niveaux=masquer_groupe([dict(niveau=n or 'aucun', libelle=LIBELLES_NIVEAU[n], nombre=compte(niveaux.get(n, 0)))
                                        for n in (*NIVEAUX, None)]),
                incoherences=[dict(type=t, libelle=LIBELLES_INCOHERENCE.get(t, t), nombre=compte(n)) for t, n in
                              cx.execute('SELECT type, count(DISTINCT ref) FROM c3_incoherence GROUP BY 1 ORDER BY 2 DESC')])
        finally:
            cx.close()

    # ---- liste des clients -----------------------------------------------------------------------------------------
    def clients(self):
        """Une ligne par client (fiche demandeur d'au moins un dossier), déjà calculée pour le filtrage."""
        if hasattr(self, '_clients'):
            return self._clients
        cx = self.connexion()
        try:
            lignes = {}
            for fiche, ref, produit, recu, actif, ville in cx.execute(
                    'SELECT x.fiche, d.ref, d."productType", d."businessReceivedAt", d.actif, d.agency_city '
                    'FROM c3_demandeur x JOIN c3_dossier d ON d.ref = x.ref ORDER BY x.fiche, d."businessReceivedAt"'):
                c = lignes.setdefault(fiche, dict(fiche=fiche, refs=[], produits=set(), derniere=None, ville=None))
                c['refs'].append(ref)
                c['produits'].add(produit)
                c['derniere'] = max(filter(None, (c['derniere'], recu)), default=None)
                c['ville'] = ville or c['ville']
            noms = dict(cx.execute('SELECT identifiant, nom FROM c2_personne UNION ALL '
                                   'SELECT identifiant, denomination FROM c2_societe').fetchall())
            incoherences = dict(cx.execute('SELECT ref, count(*) FROM c3_incoherence GROUP BY ref').fetchall())
            revenus = dict(cx.execute("SELECT ref, max(montant) FROM c3_revenu WHERE nature = 'verifie' AND "
                                      "source <> 'RELEVE_BANCAIRE' GROUP BY ref").fetchall())
            sortie = []
            for c in lignes.values():
                niveaux = [self.niveau_dossier.get(r) for r in c['refs']]
                meilleur = min(niveaux, key=self._rang, default=None)
                sortie.append(dict(
                    indice=self.indice_fiche[c['fiche']], nom=noms.get(c['fiche']) or '—',
                    type='societe' if c['fiche'].startswith('pm_') else 'personne', dossiers=len(c['refs']),
                    produits=sorted(p for p in c['produits'] if p), derniere_demande=c['derniere'],
                    ville=c['ville'], inscrit=c['fiche'] in self.inscrits,
                    niveau=meilleur, niveau_libelle=LIBELLES_NIVEAU[meilleur],
                    incoherences=sum(incoherences.get(r, 0) for r in c['refs']),
                    revenu=max(filter(None, (revenus.get(r) for r in c['refs'])), default=None)))
            sortie.sort(key=lambda c: (self._rang(c['niveau']), -c['incoherences'], c['nom']))
            self._clients = sortie
            return sortie
        finally:
            cx.close()

    def rechercher(self, texte=None, type_=None, niveau=None, produit=None, avec_incoherence=None, page=1, taille=50,
                   tri='gravite'):
        lignes = self.clients()
        if texte:
            t = texte.strip().upper()
            lignes = [c for c in lignes if t in c['nom'].upper()]
        if type_:
            lignes = [c for c in lignes if c['type'] == type_]
        if niveau:
            lignes = [c for c in lignes if (c['niveau'] or 'aucun') == niveau]
        if produit:
            lignes = [c for c in lignes if produit in c['produits']]
        if avec_incoherence:
            lignes = [c for c in lignes if c['incoherences']]
        lignes = trier(lignes, tri)
        debut = (page - 1) * taille
        return dict(total=len(lignes), page=page, taille=taille, items=lignes[debut:debut + taille])

    # ---- fiche client ----------------------------------------------------------------------------------------------
    def fiche(self, indice):
        fiche = self.fiche_de.get(indice)
        if fiche is None:
            return None
        cx = self.connexion()
        try:
            personne = fiche.startswith('pp_')
            if personne:
                r = cx.execute('SELECT nom, cin, date_naissance, adresse, inscrit FROM c2_personne WHERE identifiant = %s',
                               (fiche,)).fetchone()
                identite = dict(type='personne', nom=r['nom'], cin=r['cin'], date_naissance=r['date_naissance'],
                                adresse=r['adresse'], inscrit=bool(r['inscrit']))
            else:
                r = cx.execute('SELECT denomination, rc, tribunal, ice, adresse, inscrit FROM c2_societe '
                               'WHERE identifiant = %s', (fiche,)).fetchone()
                identite = dict(type='societe', nom=r['denomination'], rc=r['rc'], tribunal=r['tribunal'], ice=r['ice'],
                                adresse=r['adresse'], inscrit=bool(r['inscrit']))
            refs = [x[0] for x in cx.execute('SELECT DISTINCT ref FROM c2_mention WHERE fiche = %s AND source = %s '
                                             'ORDER BY ref', (fiche, 'v2'))]
            # Dossiers où la fiche est demandeur : tout ce que le dossier dit est à elle. Dossiers où elle est seulement
            # citée (salarié, employeur, vendeur…) : revenus, charges, véhicules, contexte et contrôles appartiennent au
            # demandeur et ne passent pas ; seules les pièces qui la citent sont montrées.
            propres = {x[0] for x in cx.execute('SELECT ref FROM c3_demandeur WHERE fiche = %s', (fiche,))}
            refs_propres = [r for r in refs if r in propres]
            dossiers = [self._resume_dossier(cx, ref, fiche, demandeur=ref in propres) for ref in refs]
            dossiers.sort(key=lambda d: d['recu'] or '', reverse=True)
            alias = [dict(nom=a, ecriture=e, nombre=n) for a, e, n in cx.execute(
                'SELECT alias, ecriture, sum(nb_mentions) FROM c2_alias WHERE fiche = %s GROUP BY 1, 2 ORDER BY 3 DESC',
                (fiche,))]
            adresses = [dict(adresse=a, source=s, role=LIBELLES_ROLE.get(r, r)) for a, s, r in cx.execute(
                'SELECT DISTINCT adresse, source, role FROM c2_adresse WHERE fiche = %s ORDER BY 2, 1', (fiche,))]
            sources = dict(cx.execute('SELECT source, count(*) FROM c2_mention WHERE fiche = %s GROUP BY 1', (fiche,)))
            societes = []
            for s, role, src in cx.execute('SELECT DISTINCT societe, role, source FROM c2_role WHERE fiche = %s '
                                           'ORDER BY 2', (fiche,)):
                nom = cx.execute('SELECT denomination FROM c2_societe WHERE identifiant = %s', (s,)).fetchone()
                societes.append(dict(indice=self.indice_fiche.get(s), nom=nom[0] if nom else '—',
                                     role=LIBELLES_ROLE.get(role, role), source=src, inscrit=s in self.inscrits))
            personnes = []
            if not personne:
                for p, role, src in cx.execute('SELECT DISTINCT fiche, role, source FROM c2_role WHERE societe = %s '
                                               'ORDER BY 2', (fiche,)):
                    nom = cx.execute('SELECT nom FROM c2_personne WHERE identifiant = %s', (p,)).fetchone()
                    personnes.append(dict(indice=self.indice_fiche.get(p), nom=nom[0] if nom else '—',
                                          role=LIBELLES_ROLE.get(role, role), source=src, inscrit=p in self.inscrits))
            revenus = [dict(r) for r in cx.execute(
                f"SELECT ref, nature, source, montant, annee, mois FROM c3_revenu WHERE ref IN "
                f"({self._dans(refs_propres)}) ORDER BY ref, nature, source, annee, mois", refs_propres)] if refs_propres else []
            for r in revenus:
                r['dossier'] = self.indice_dossier.get(r.pop('ref'))
            par_rib = {}                                      # un compte par RIB : banque et titulaire lus où ils le sont
            for rib, b, t in cx.execute(
                    "SELECT DISTINCT i.valeur, c.banque, c.titulaire FROM c2_identifiant i LEFT JOIN c3_compte c ON "
                    "c.ref = i.ref AND c.rib = i.valeur WHERE i.fiche = %s AND i.type = 'RIB' ORDER BY 1, 2 DESC, 3 DESC",
                    (fiche,)):
                actuel = par_rib.setdefault(rib, dict(rib=masquer_rib(rib), banque=None, titulaire=None))
                actuel['banque'] = actuel['banque'] or b
                actuel['titulaire'] = actuel['titulaire'] or t
            comptes = list(par_rib.values())
            vehicules = [dict(r) for r in cx.execute(
                'SELECT DISTINCT v.type_piece, v.marque, v.modele, v.etat, v.prix FROM c3_vehicule v '
                f"WHERE v.ref IN ({self._dans(refs_propres)})", refs_propres)] if refs_propres else []
            chemins = []
            for ref in refs:
                for ch in self.chemins_dossier.get(ref, []):
                    if ref not in propres and self._depart(ch) != fiche:
                        continue                              # chemin d'une autre partie du dossier : pas le sien
                    chemins.append(self._chemin_lisible(cx, ch, ref))
            chemins.sort(key=lambda c: (self._rang(c['niveau']), -c['force']))
            return dict(indice=indice, identite=identite, alias=alias, adresses=adresses, sources=sources,
                        dossiers=dossiers, societes=societes, personnes=personnes, revenus=revenus, comptes=comptes,
                        vehicules=vehicules, chemins=chemins[:5], charges=self._charges(cx, refs_propres),
                        operations=self._operations(cx, refs_propres), incoherences=self._incoherences(cx, refs_propres),
                        identifiants=self._identifiants(cx, fiche), donnees=[self._donnees_dossier(cx, ref, fiche)
                                                                            for ref in refs],
                        liste_noire=self._liste_noire(cx, fiche), registre=self._registre(cx, fiche))
        finally:
            cx.close()

    # ---- toutes les données d'un client ---------------------------------------------------------------------------
    CONTEXTE = (('civil_full_name', 'Nom déclaré'), ('civil_cin', 'CIN déclaré'), ('civil_address', 'Adresse déclarée'),
                ('declared_employer', 'Employeur déclaré'), ('declared_monthly_income', 'Revenu mensuel déclaré'),
                ('declared_pension_organism', 'Organisme de pension déclaré'), ('known_client', 'Client connu'),
                ('agency_code', 'Agence'), ('agency_city', 'Ville de l\'agence'), ('csp', 'CSP'),
                ('productType', 'Produit'), ('paymentMode', 'Mode de paiement'), ('personType', 'Type de client'),
                ('category', 'Catégorie'), ('verdict', 'Verdict de la v2'), ('analysisStatus', 'Analyse'),
                ('alertsCritical', 'Alertes critiques (v2)'), ('alertsMajor', 'Alertes majeures (v2)'),
                ('alertsMinor', 'Alertes mineures (v2)'), ('businessReceivedAt', 'Reçu le'), ('updatedAt', 'Mis à jour le'))

    CHAMPS_MENTION = ('role', 'nom', 'cin', 'date_naissance', 'adresse', 'rc', 'tribunal', 'ice', 'identifiant_fiscal',
                      'affiliation_cnss')

    @staticmethod
    def _depart(ch):
        return ch['etapes'][0]['de'] if ch['etapes'] else ch['cible']

    def _donnees_dossier(self, cx, ref, fiche):
        """Tout ce que le dossier dit : contexte déclaré, chaque valeur de chaque pièce (pour un dossier où le client
        est demandeur ; sinon, les seules pièces qui le citent), relevés mois par mois, contrôles de la v2."""
        d = dict(cx.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c, _ in self.CONTEXTE)} FROM c3_dossier '
                            'WHERE ref = %s', (ref,)).fetchone())
        demandeur = cx.execute('SELECT 1 FROM c3_demandeur WHERE ref = %s AND fiche = %s', (ref, fiche)).fetchone()
        if demandeur:
            pieces = [r[0] for r in cx.execute('SELECT upstream_piece_id FROM c1_piece WHERE ref = %s ORDER BY type',
                                               (ref,))]
        else:
            pieces = [r[0] for r in cx.execute('SELECT DISTINCT upstream_piece_id FROM c2_mention WHERE ref = %s '
                                               'AND fiche = %s ORDER BY 1', (ref, fiche))]
        sortie_pieces = []
        for upi in pieces:
            p = cx.execute('SELECT type, source, extraction_status FROM c1_piece WHERE ref = %s AND upstream_piece_id = %s',
                           (ref, upi)).fetchone()
            if p is None:
                continue
            if not demandeur:                     # pièce d'un autre client : ce qu'elle dit de cette fiche, rien d'autre
                faits = []
                for m in cx.execute(f'SELECT {", ".join(self.CHAMPS_MENTION)} FROM c2_mention WHERE ref = %s AND '
                                    'upstream_piece_id = %s AND fiche = %s', (ref, upi, fiche)):
                    faits += [dict(cle=c, valeur=LIBELLES_ROLE.get(m[c], m[c]) if c == 'role' else m[c],
                                   origine='mention', statut='normal') for c in self.CHAMPS_MENTION if m[c] not in (None, '')]
                sortie_pieces.append(dict(type=p['type'], source=p['source'], statut=p['extraction_status'], faits=faits,
                                          mois=[]))
                continue
            faits = [dict(cle=c, valeur=v, origine=o, statut=s) for c, v, o, s in cx.execute(
                'SELECT cle_brute, valeur, origine, statut FROM c1_fait WHERE ref = %s AND upstream_piece_id = %s '
                'ORDER BY cle_brute', (ref, upi))]
            for f in faits:
                if f['cle'] in ('rib', 'numero_compte') and f['valeur']:
                    f['valeur'] = masquer_rib(re.sub(r'\D', '', str(f['valeur'])) or str(f['valeur']))
                else:
                    f['valeur'] = masquer_numeros(f['valeur'])
            mois = [dict(r) for r in cx.execute(
                'SELECT annee, mois, solde_ouverture, solde_cloture, total_credit, total_debit, salaire_detecte, '
                'echeances_credits, nb_operations_lues FROM c1_releve_mois WHERE ref = %s AND upstream_piece_id = %s '
                'ORDER BY rang', (ref, upi))]
            sortie_pieces.append(dict(type=p['type'], source=p['source'], statut=p['extraction_status'], faits=faits,
                                      mois=mois))
        controles = [dict(r, explication=masquer_numeros(r['explication'])) for r in cx.execute(
            'SELECT c."controlId" AS controle, c.outcome AS resultat, c.criticality AS criticite, c.explanation AS '
            'explication FROM "AnalysisControl" c JOIN "Dossier" x ON x.id = c."dossierId" WHERE x.ref = %s '
            'ORDER BY c."controlId"', (ref,))] if demandeur else []
        contexte = [dict(libelle=l, valeur=d[c]) for c, l in self.CONTEXTE if d[c] not in (None, '')] if demandeur else []
        return dict(dossier=self.indice_dossier.get(ref), reference=ref, demandeur=bool(demandeur),
                    contexte=contexte,
                    pieces=sortie_pieces, controles=controles)

    def _dans(self, refs):
        return ', '.join(['%s'] * len(refs))

    def _charges(self, cx, refs):
        if not refs:
            return []
        lignes = [dict(r) for r in cx.execute(
            f'SELECT ref, nature, montant, annee, mois FROM c3_charge WHERE ref IN ({self._dans(refs)}) '
            'ORDER BY ref, nature, annee, mois', refs)]
        for x in lignes:
            x['dossier'] = self.indice_dossier.get(x.pop('ref'))
        return lignes

    def _operations(self, cx, refs, limite=300):
        if not refs:
            return []
        lignes = [dict(r) for r in cx.execute(
            f'SELECT ref, date_operation, type_operation, libelle, debit, credit FROM c3_operation '
            f'WHERE ref IN ({self._dans(refs)}) ORDER BY date_operation LIMIT {int(limite)}', refs)]
        for x in lignes:
            x['dossier'] = self.indice_dossier.get(x.pop('ref'))
            x['libelle'] = masquer_numeros(x['libelle'])
        return lignes

    def _incoherences(self, cx, refs):
        if not refs:
            return []
        return [dict(type=t, libelle=LIBELLES_INCOHERENCE.get(t, t), gravite=g, dossier=self.indice_dossier.get(ref),
                     autre_dossier=self.indice_dossier.get(ref_b) if ref_b and ref_b != ref else None)
                for ref, t, g, ref_b in cx.execute(
                    f'SELECT ref, type, gravite, ref_b FROM c3_incoherence WHERE ref IN ({self._dans(refs)}) '
                    'ORDER BY ref, type', refs)]

    def _identifiants(self, cx, fiche):
        """Identifiants portés par la fiche (CIN, RC, ICE, CNSS, affiliation, pension, INPE, châssis…) ; le RIB, masqué,
        est dans les comptes."""
        return [dict(type=t, valeur=v, dossier=self.indice_dossier.get(ref)) for t, v, ref in cx.execute(
            "SELECT DISTINCT type, valeur, ref FROM c2_identifiant WHERE fiche = %s AND type <> 'RIB' ORDER BY 1, 2",
            (fiche,))]

    def _liste_noire(self, cx, fiche):
        lignes = cx.execute(
            'SELECT l.label, l.kind, l."typeListe", l.motif, l.type_fraude, l.statut, l.date_statut, l.premiere_saisie, '
            'l.derniere_saisie, l.nb_inscriptions, l.source, l.city FROM ref_liste_noire l JOIN c2_mention m ON '
            "m.cle_origine = 'bl:' || l.cle_entite WHERE m.fiche = %s", (fiche,)).fetchall()
        return [dict(r) for r in lignes]

    def _registre(self, cx, fiche):
        """Mentions au registre du commerce : la société et le rôle (pour une personne), ou la société elle-même."""
        return [dict(societe=n, role=LIBELLES_ROLE.get(r, r), parts=p, adresse=a) for n, r, p, a in cx.execute(
            "SELECT coalesce(s.nom, m.nom), m.role, m.parts, m.adresse FROM c2_mention m LEFT JOIN c2_mention s "
            "ON s.id = m.societe_mention WHERE m.fiche = %s AND m.source = 'registre' ORDER BY 1", (fiche,))]

    def _resume_dossier(self, cx, ref, fiche=None, demandeur=True):
        d = cx.execute('SELECT "productType", csp, "paymentMode", verdict, category, "analysisStatus", actif, '
                       '"businessReceivedAt", agency_city, declared_monthly_income FROM c3_dossier WHERE ref = %s',
                       (ref,)).fetchone()
        role = None
        if fiche and demandeur:
            role = 'demandeur'
        elif fiche:
            roles = sorted({LIBELLES_ROLE.get(r, r) for r, in cx.execute(
                'SELECT DISTINCT role FROM c2_mention WHERE ref = %s AND fiche = %s', (ref, fiche)) if r})
            role = ', '.join(roles) or 'cité'
        niveau = self.niveau_dossier.get(ref) if demandeur else None
        propre = (lambda v: v) if demandeur else (lambda v: None)    # ce qui appartient au demandeur ne passe pas
        return dict(indice=self.indice_dossier.get(ref), produit=d['productType'], csp=propre(d['csp']),
                    paiement=propre(d['paymentMode']), verdict=propre(d['verdict']), categorie=d['category'],
                    analyse=d['analysisStatus'], actif=bool(d['actif']), recu=d['businessReceivedAt'],
                    ville=d['agency_city'], revenu_declare=propre(d['declared_monthly_income']), role=role,
                    demandeur=demandeur, niveau=niveau, niveau_libelle=LIBELLES_NIVEAU[niveau],
                    incoherences=cx.execute('SELECT count(*) FROM c3_incoherence WHERE ref = %s', (ref,)).fetchone()[0]
                    if demandeur else None)

    def _nom(self, cx, fiche):
        r = cx.execute('SELECT nom FROM c2_personne WHERE identifiant = %s UNION ALL '
                       'SELECT denomination FROM c2_societe WHERE identifiant = %s', (fiche, fiche)).fetchone()
        return r[0] if r else '—'

    def _chemin_lisible(self, cx, ch, ref):
        etapes = []
        for e in ch['etapes']:
            etapes.append(dict(type=e['type'], code=LIBELLES_ROLE.get(e['code'], e['code']),
                               de=dict(indice=self.indice_fiche.get(e['de']), nom=self._nom(cx, e['de'])),
                               vers=dict(indice=self.indice_fiche.get(e['vers']), nom=self._nom(cx, e['vers']),
                                         inscrit=e['vers'] in self.inscrits)))
        return dict(dossier=self.indice_dossier.get(ref), niveau=ch['niveau'], niveau_libelle=LIBELLES_NIVEAU[ch['niveau']],
                    force=round(ch['force'], 3), longueur=ch['longueur'], homonymie=ch['homonymie'], foyer=ch['foyer'],
                    inscrit=dict(indice=self.indice_fiche.get(ch['cible']), nom=self._nom(cx, ch['cible'])),
                    etapes=etapes)

    def fiches_nommees(self, objet):
        """Indices de fiche présents dans une réponse (la fiche elle-même et chaque tiers nommé)."""
        trouves = set()
        pile = [objet]
        while pile:
            x = pile.pop()
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in ('indice', 'id') and isinstance(v, int) and v in self.fiche_de:
                        trouves.add(v)
                    elif isinstance(v, (dict, list)):
                        pile.append(v)
            elif isinstance(x, list):
                pile.extend(x)
        return trouves

    # ---- dossier ---------------------------------------------------------------------------------------------------
    def tous_dossiers(self, page=1, taille=25):
        """Tous les dossiers, même sans fiche demandeur ; aucun identifiant interne exposé."""
        cx = self.connexion()
        try:
            total = cx.execute('SELECT count(*) FROM c3_dossier').fetchone()[0]
            lignes = cx.execute(
                'SELECT d.ref, d."productType", d."businessReceivedAt", d.actif, '
                'EXISTS(SELECT 1 FROM c3_demandeur x WHERE x.ref = d.ref) AS avec_demandeur '
                'FROM c3_dossier d ORDER BY d."businessReceivedAt" DESC NULLS LAST, d.ref '
                'LIMIT %s OFFSET %s', (taille, (page - 1) * taille)).fetchall()
            a_c6 = cx.execute("SELECT to_regclass('c6_alerte')").fetchone()[0] is not None
            a_c7 = cx.execute("SELECT to_regclass('c7_relation')").fetchone()[0] is not None
            items = []
            for ref, produit, recu, actif, avec_demandeur in lignes:
                alertes = cx.execute('SELECT count(*) FROM c6_alerte WHERE ref = %s', (ref,)).fetchone()[0] \
                    if a_c6 else 0
                relations = cx.execute('SELECT count(*) FROM c7_relation WHERE ref = %s', (ref,)).fetchone()[0] \
                    if a_c7 else 0
                items.append(dict(indice=self.indice_dossier[ref], reference=ref,
                                  produit=produit, recu=recu, actif=bool(actif),
                                  avec_demandeur=bool(avec_demandeur),
                                  alertes=alertes, relations=relations))
            return dict(items=items, total=total, page=page, taille=taille)
        finally:
            cx.close()

    def dossier(self, indice):
        ref = self.dossier_de.get(indice)
        if ref is None:
            return None
        cx = self.connexion()
        try:
            entete = self._resume_dossier(cx, ref)
            entete['reference'] = ref
            pieces = [dict(type=t, source=s, statut=e, champs=n) for t, s, e, n in cx.execute(
                'SELECT type, source, extraction_status, nb_champs FROM c1_piece WHERE ref = %s ORDER BY type', (ref,))]
            parties = []
            for fiche, type_fiche, role, demandeur in cx.execute(
                    'SELECT fiche, type_fiche, role, demandeur FROM c3_partie_dossier WHERE ref = %s '
                    'ORDER BY demandeur DESC, role', (ref,)):
                parties.append(dict(indice=self.indice_fiche.get(fiche), nom=self._nom(cx, fiche), type=type_fiche,
                                    role=LIBELLES_ROLE.get(role, role), demandeur=bool(demandeur),
                                    inscrit=fiche in self.inscrits))
            revenus = [dict(r) for r in cx.execute('SELECT nature, source, montant, annee, mois FROM c3_revenu '
                                                   'WHERE ref = %s ORDER BY nature, source, annee, mois', (ref,))]
            charges = [dict(r) for r in cx.execute('SELECT nature, montant, annee, mois FROM c3_charge WHERE ref = %s '
                                                   'ORDER BY nature, annee, mois', (ref,))]
            operations = [dict(r) for r in cx.execute(
                'SELECT date_operation, type_operation, libelle, debit, credit FROM c3_operation WHERE ref = %s '
                'ORDER BY date_operation LIMIT 200', (ref,))]
            for o in operations:
                o['libelle'] = masquer_numeros(o['libelle'])
            vehicules = [dict(r) for r in cx.execute('SELECT type_piece, marque, modele, etat, prix FROM c3_vehicule '
                                                     'WHERE ref = %s', (ref,))]
            incoherences = []
            for t, g, ref_b in cx.execute('SELECT type, gravite, ref_b FROM c3_incoherence WHERE ref = %s ORDER BY 1',
                                          (ref,)):
                incoherences.append(dict(type=t, libelle=LIBELLES_INCOHERENCE.get(t, t), gravite=g,
                                         autre_dossier=self.indice_dossier.get(ref_b) if ref_b != ref else None))
            controles = [dict(r) for r in cx.execute(
                'SELECT c."controlId" AS controle, c.outcome AS resultat, c.criticality AS criticite '
                'FROM "AnalysisControl" c JOIN "Dossier" d ON d.id = c."dossierId" WHERE d.ref = %s '
                'ORDER BY c."controlId"', (ref,))]
            chemins = [self._chemin_lisible(cx, ch, ref) for ch in self.chemins_dossier.get(ref, [])[:3]]
            relations_c7 = []
            if cx.execute("SELECT to_regclass('c7_relation')").fetchone()[0] is not None:
                for code, fiche in cx.execute(
                        'SELECT code, fiche FROM c7_relation WHERE ref = %s ORDER BY code', (ref,)):
                    relations_c7.append(dict(code=code, libelle=LIBELLES_C7.get(code, code),
                                             fiche_associee=fiche in self.indice_fiche if fiche else False))
            alertes_c6 = []
            if cx.execute("SELECT to_regclass('c6_alerte')").fetchone()[0] is not None:
                for code, nature, niveau, justification in cx.execute(
                        'SELECT code, nature, niveau, justification FROM c6_alerte WHERE ref = %s '
                        'ORDER BY niveau NULLS LAST, code', (ref,)):
                    alertes_c6.append(dict(code=code, nature=nature, niveau=niveau,
                                           libelle=LIBELLES_INCOHERENCE.get(code, code.replace('_', ' ')),
                                           justification=masquer_numeros(justification)))
            return dict(indice=indice, entete=entete, pieces=pieces, parties=parties, revenus=revenus, charges=charges,
                        operations=operations, vehicules=vehicules, incoherences=incoherences, controles=controles,
                        chemins=chemins, relations_c7=relations_c7, alertes_c6=alertes_c6)
        finally:
            cx.close()

    # ---- réseau autour d'une fiche ---------------------------------------------------------------------------------
    def reseau(self, indice, profondeur=2, limite=120):
        """Fiches à `profondeur` liens au plus (rôles et identifiants partagés), pour le dessin. Les nœuds
        d'identifiant ne portent que leur type : jamais la valeur du RIB ni de l'adresse."""
        depart = self.fiche_de.get(indice)
        if depart is None:
            return None
        cx = self.connexion()
        try:
            noeuds, liens, front = {depart: 0}, [], [depart]
            identifiants = {}
            for niveau in range(1, profondeur + 1):
                suivant = []
                for u in front:
                    voisins = []
                    for v, code in cx.execute("SELECT vers, code FROM c5_arete WHERE type = 'role' AND de = %s UNION "
                                              "SELECT de, code FROM c5_arete WHERE type = 'role' AND vers = %s", (u, u)):
                        voisins.append((v, code, None))
                    for noeud, code in cx.execute("SELECT DISTINCT vers, code FROM c5_arete WHERE type = 'identifiant' "
                                                  'AND de = %s', (u,)).fetchall():
                        porteurs = [p[0] for p in cx.execute("SELECT DISTINCT de FROM c5_arete WHERE vers = %s AND de <> %s",
                                                             (noeud, u))]
                        if porteurs and len(porteurs) < 30:
                            for p in porteurs:
                                voisins.append((p, code, noeud))
                    for v, code, noeud in voisins:
                        if len(noeuds) >= limite and v not in noeuds:
                            continue
                        if noeud:
                            ident = identifiants.setdefault(noeud, f'id{len(identifiants)}')
                            if ident not in noeuds:
                                noeuds[ident] = niveau
                                liens.append(dict(de=self.indice_fiche[u], vers=ident, code=code))
                            if v not in noeuds:
                                noeuds[v] = niveau
                                suivant.append(v)
                            liens.append(dict(de=ident, vers=self.indice_fiche[v], code=code))
                        else:
                            if v not in noeuds:
                                noeuds[v] = niveau
                                suivant.append(v)
                            liens.append(dict(de=self.indice_fiche[u], vers=self.indice_fiche[v],
                                              code=LIBELLES_ROLE.get(code, code)))
                front = suivant
            types_id = {i: c for n, i in identifiants.items() for c in
                        [cx.execute('SELECT code FROM c5_arete WHERE vers = %s LIMIT 1', (n,)).fetchone()[0]]}
            sortie = []
            for n, niveau in noeuds.items():
                if n in types_id:
                    sortie.append(dict(id=n, type='identifiant', nom=types_id[n], niveau=niveau, inscrit=False))
                else:
                    sortie.append(dict(id=self.indice_fiche[n], type='societe' if n.startswith('pm_') else 'personne',
                                       nom=self._nom(cx, n), niveau=niveau, inscrit=n in self.inscrits,
                                       depart=n == depart))
            vus, uniques = set(), []
            for lien in liens:
                cle = (lien['de'], lien['vers'], lien['code'])
                if cle not in vus:
                    vus.add(cle)
                    uniques.append(lien)
            return dict(noeuds=sortie, liens=uniques)
        finally:
            cx.close()
