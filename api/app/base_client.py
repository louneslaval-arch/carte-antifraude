"""Lecture de la base client (couches c0 à c5) pour les pages : clients, fiches, dossiers, réseau.

La base est ouverte en lecture seule. Les identifiants internes (fiches `pp_…`, `pm_…`, références de dossier,
nœuds d'identifiant) ne sortent jamais : chaque fiche et chaque dossier reçoit, au chargement, un indice entier
tiré au hasard, seul identifiant qui passe dans une URL ou une réponse. Les chemins vers la liste noire sont
calculés une fois au chargement (c5) ; une nouvelle base se charge en redémarrant le service.

Aucun chiffre agrégé sous 5 (« < 5 ») ; aucune valeur d'identité dans un message d'erreur ni dans le journal.
"""

import os
import random
import sqlite3
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from pipeline.couches import c5_graphe  # noqa: E402

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


def compte(n):
    """Un comptage affichable : 0, ou au moins 5 ; sinon « < 5 »."""
    return n if n == 0 or n >= SEUIL else '< 5'


def masquer_rib(rib):
    return f'••• {rib[-4:]}' if rib else None


class BaseClient:
    def __init__(self, chemin, donnees_reelles=False):
        if not os.path.exists(chemin):
            raise FileNotFoundError('base client introuvable')
        self.chemin = chemin
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

    def connexion(self):
        cx = sqlite3.connect(f'file:{self.chemin}?mode=ro', uri=True, check_same_thread=False)
        cx.row_factory = sqlite3.Row
        return cx

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
            niveaux = {}
            for ref, niveau in self.niveau_dossier.items():
                niveaux[niveau] = niveaux.get(niveau, 0) + 1
            return dict(
                clients=compte(clients), dossiers=compte(dossiers), dossiers_total=compte(un('SELECT count(*) FROM c3_dossier')),
                societes_registre=compte(un("SELECT count(*) FROM c2_societe")),
                inscrits=compte(un('SELECT count(*) FROM ref_liste_noire WHERE active = 1')),
                mise_a_jour=mise_a_jour,
                produits=repartition('SELECT "productType", count(*) FROM c3_dossier GROUP BY 1 ORDER BY 2 DESC'),
                csp=repartition('SELECT csp, count(*) FROM c3_dossier GROUP BY 1 ORDER BY 2 DESC'),
                niveaux=[dict(niveau=n or 'aucun', libelle=LIBELLES_NIVEAU[n], nombre=compte(niveaux.get(n, 0)))
                         for n in (*NIVEAUX, None)],
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

    def rechercher(self, texte=None, type_=None, niveau=None, produit=None, avec_incoherence=None, page=1, taille=50):
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
                r = cx.execute('SELECT nom, cin, date_naissance, adresse, inscrit FROM c2_personne WHERE identifiant = ?',
                               (fiche,)).fetchone()
                identite = dict(type='personne', nom=r['nom'], cin=r['cin'], date_naissance=r['date_naissance'],
                                adresse=r['adresse'], inscrit=bool(r['inscrit']))
            else:
                r = cx.execute('SELECT denomination, rc, tribunal, ice, adresse, inscrit FROM c2_societe '
                               'WHERE identifiant = ?', (fiche,)).fetchone()
                identite = dict(type='societe', nom=r['denomination'], rc=r['rc'], tribunal=r['tribunal'], ice=r['ice'],
                                adresse=r['adresse'], inscrit=bool(r['inscrit']))
            refs = [x[0] for x in cx.execute('SELECT DISTINCT ref FROM c2_mention WHERE fiche = ? AND source = ? '
                                             'ORDER BY ref', (fiche, 'v2'))]
            dossiers = [self._resume_dossier(cx, ref, fiche) for ref in refs]
            dossiers.sort(key=lambda d: d['recu'] or '', reverse=True)
            alias = [dict(nom=a, ecriture=e, nombre=n) for a, e, n in cx.execute(
                'SELECT alias, ecriture, sum(nb_mentions) FROM c2_alias WHERE fiche = ? GROUP BY 1, 2 ORDER BY 3 DESC',
                (fiche,))]
            adresses = [dict(adresse=a, source=s, role=LIBELLES_ROLE.get(r, r)) for a, s, r in cx.execute(
                'SELECT DISTINCT adresse, source, role FROM c2_adresse WHERE fiche = ? ORDER BY 2, 1', (fiche,))]
            sources = dict(cx.execute('SELECT source, count(*) FROM c2_mention WHERE fiche = ? GROUP BY 1', (fiche,)))
            societes = []
            for s, role, src in cx.execute('SELECT DISTINCT societe, role, source FROM c2_role WHERE fiche = ? '
                                           'ORDER BY 2', (fiche,)):
                nom = cx.execute('SELECT denomination FROM c2_societe WHERE identifiant = ?', (s,)).fetchone()
                societes.append(dict(indice=self.indice_fiche.get(s), nom=nom[0] if nom else '—',
                                     role=LIBELLES_ROLE.get(role, role), source=src, inscrit=s in self.inscrits))
            personnes = []
            if not personne:
                for p, role, src in cx.execute('SELECT DISTINCT fiche, role, source FROM c2_role WHERE societe = ? '
                                               'ORDER BY 2', (fiche,)):
                    nom = cx.execute('SELECT nom FROM c2_personne WHERE identifiant = ?', (p,)).fetchone()
                    personnes.append(dict(indice=self.indice_fiche.get(p), nom=nom[0] if nom else '—',
                                          role=LIBELLES_ROLE.get(role, role), source=src, inscrit=p in self.inscrits))
            revenus = [dict(r) for r in cx.execute(
                f"SELECT ref, nature, source, montant, annee, mois FROM c3_revenu WHERE ref IN "
                f"({', '.join('?' * len(refs))}) ORDER BY ref, nature, source, annee, mois", refs)] if refs else []
            for r in revenus:
                r['dossier'] = self.indice_dossier.get(r.pop('ref'))
            par_rib = {}                                      # un compte par RIB : banque et titulaire lus où ils le sont
            for rib, b, t in cx.execute(
                    "SELECT DISTINCT i.valeur, c.banque, c.titulaire FROM c2_identifiant i LEFT JOIN c3_compte c ON "
                    "c.ref = i.ref AND c.rib = i.valeur WHERE i.fiche = ? AND i.type = 'RIB' ORDER BY 1, 2 DESC, 3 DESC",
                    (fiche,)):
                actuel = par_rib.setdefault(rib, dict(rib=masquer_rib(rib), banque=None, titulaire=None))
                actuel['banque'] = actuel['banque'] or b
                actuel['titulaire'] = actuel['titulaire'] or t
            comptes = list(par_rib.values())
            vehicules = [dict(r) for r in cx.execute(
                'SELECT DISTINCT v.type_piece, v.marque, v.modele, v.etat, v.prix FROM c3_vehicule v '
                f"WHERE v.ref IN ({', '.join('?' * len(refs))})", refs)] if refs else []
            chemins = []
            for ref in refs:
                for ch in self.chemins_dossier.get(ref, [])[:3]:
                    chemins.append(self._chemin_lisible(cx, ch, ref))
            chemins.sort(key=lambda c: (self._rang(c['niveau']), -c['force']))
            return dict(indice=indice, identite=identite, alias=alias, adresses=adresses, sources=sources,
                        dossiers=dossiers, societes=societes, personnes=personnes, revenus=revenus, comptes=comptes,
                        vehicules=vehicules, chemins=chemins[:5], donnees=[self._donnees_dossier(cx, ref, fiche)
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

    def _donnees_dossier(self, cx, ref, fiche):
        """Tout ce que le dossier dit : contexte déclaré, chaque valeur de chaque pièce (pour un dossier où le client
        est demandeur ; sinon, les seules pièces qui le citent), relevés mois par mois, contrôles de la v2."""
        d = dict(cx.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c, _ in self.CONTEXTE)} FROM c3_dossier '
                            'WHERE ref = ?', (ref,)).fetchone())
        demandeur = cx.execute('SELECT 1 FROM c3_demandeur WHERE ref = ? AND fiche = ?', (ref, fiche)).fetchone()
        if demandeur:
            pieces = [r[0] for r in cx.execute('SELECT upstream_piece_id FROM c1_piece WHERE ref = ? ORDER BY type',
                                               (ref,))]
        else:
            pieces = [r[0] for r in cx.execute('SELECT DISTINCT upstream_piece_id FROM c2_mention WHERE ref = ? '
                                               'AND fiche = ? ORDER BY 1', (ref, fiche))]
        sortie_pieces = []
        for upi in pieces:
            p = cx.execute('SELECT type, source, extraction_status FROM c1_piece WHERE ref = ? AND upstream_piece_id = ?',
                           (ref, upi)).fetchone()
            if p is None:
                continue
            faits = [dict(cle=c, valeur=v, origine=o, statut=s) for c, v, o, s in cx.execute(
                'SELECT cle_brute, valeur, origine, statut FROM c1_fait WHERE ref = ? AND upstream_piece_id = ? '
                'ORDER BY cle_brute', (ref, upi))]
            for f in faits:
                if f['cle'] in ('rib', 'numero_compte') and f['valeur']:
                    f['valeur'] = masquer_rib(f['valeur'])
            mois = [dict(r) for r in cx.execute(
                'SELECT annee, mois, solde_ouverture, solde_cloture, total_credit, total_debit, salaire_detecte, '
                'echeances_credits, nb_operations_lues FROM c1_releve_mois WHERE ref = ? AND upstream_piece_id = ? '
                'ORDER BY rang', (ref, upi))]
            sortie_pieces.append(dict(type=p['type'], source=p['source'], statut=p['extraction_status'], faits=faits,
                                      mois=mois))
        controles = [dict(r) for r in cx.execute(
            'SELECT c."controlId" AS controle, c.outcome AS resultat, c.criticality AS criticite, c.explanation AS '
            'explication FROM "AnalysisControl" c JOIN "Dossier" x ON x.id = c."dossierId" WHERE x.ref = ? '
            'ORDER BY c."controlId"', (ref,))]
        return dict(dossier=self.indice_dossier.get(ref), reference=ref, demandeur=bool(demandeur),
                    contexte=[dict(libelle=l, valeur=d[c]) for c, l in self.CONTEXTE if d[c] not in (None, '')],
                    pieces=sortie_pieces, controles=controles)

    def _liste_noire(self, cx, fiche):
        lignes = cx.execute(
            'SELECT l.label, l.kind, l."typeListe", l.motif, l.type_fraude, l.statut, l.date_statut, l.premiere_saisie, '
            'l.derniere_saisie, l.nb_inscriptions, l.source, l.city FROM ref_liste_noire l JOIN c2_mention m ON '
            "m.cle_origine = 'bl:' || l.cle_entite WHERE m.fiche = ?", (fiche,)).fetchall()
        return [dict(r) for r in lignes]

    def _registre(self, cx, fiche):
        """Mentions au registre du commerce : la société et le rôle (pour une personne), ou la société elle-même."""
        return [dict(societe=n, role=LIBELLES_ROLE.get(r, r), parts=p, adresse=a) for n, r, p, a in cx.execute(
            "SELECT coalesce(s.nom, m.nom), m.role, m.parts, m.adresse FROM c2_mention m LEFT JOIN c2_mention s "
            "ON s.id = m.societe_mention WHERE m.fiche = ? AND m.source = 'registre' ORDER BY 1", (fiche,))]

    def _resume_dossier(self, cx, ref, fiche=None):
        d = cx.execute('SELECT "productType", csp, "paymentMode", verdict, category, "analysisStatus", actif, '
                       '"businessReceivedAt", agency_city, declared_monthly_income FROM c3_dossier WHERE ref = ?',
                       (ref,)).fetchone()
        role = None
        if fiche:
            r = cx.execute('SELECT role FROM c2_mention WHERE ref = ? AND fiche = ? ORDER BY role LIMIT 1',
                           (ref, fiche)).fetchone()
            role = LIBELLES_ROLE.get(r[0], r[0]) if r else None
        niveau = self.niveau_dossier.get(ref)
        return dict(indice=self.indice_dossier.get(ref), produit=d['productType'], csp=d['csp'],
                    paiement=d['paymentMode'], verdict=d['verdict'], categorie=d['category'],
                    analyse=d['analysisStatus'], actif=bool(d['actif']), recu=d['businessReceivedAt'],
                    ville=d['agency_city'], revenu_declare=d['declared_monthly_income'], role=role,
                    niveau=niveau, niveau_libelle=LIBELLES_NIVEAU[niveau],
                    incoherences=cx.execute('SELECT count(*) FROM c3_incoherence WHERE ref = ?', (ref,)).fetchone()[0])

    def _nom(self, cx, fiche):
        r = cx.execute('SELECT nom FROM c2_personne WHERE identifiant = ? UNION ALL '
                       'SELECT denomination FROM c2_societe WHERE identifiant = ?', (fiche, fiche)).fetchone()
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

    # ---- dossier ---------------------------------------------------------------------------------------------------
    def dossier(self, indice):
        ref = self.dossier_de.get(indice)
        if ref is None:
            return None
        cx = self.connexion()
        try:
            entete = self._resume_dossier(cx, ref)
            entete['reference'] = ref
            pieces = [dict(type=t, source=s, statut=e, champs=n) for t, s, e, n in cx.execute(
                'SELECT type, source, extraction_status, nb_champs FROM c1_piece WHERE ref = ? ORDER BY type', (ref,))]
            parties = []
            for fiche, type_fiche, role, demandeur in cx.execute(
                    'SELECT fiche, type_fiche, role, demandeur FROM c3_partie_dossier WHERE ref = ? '
                    'ORDER BY demandeur DESC, role', (ref,)):
                parties.append(dict(indice=self.indice_fiche.get(fiche), nom=self._nom(cx, fiche), type=type_fiche,
                                    role=LIBELLES_ROLE.get(role, role), demandeur=bool(demandeur),
                                    inscrit=fiche in self.inscrits))
            revenus = [dict(r) for r in cx.execute('SELECT nature, source, montant, annee, mois FROM c3_revenu '
                                                   'WHERE ref = ? ORDER BY nature, source, annee, mois', (ref,))]
            charges = [dict(r) for r in cx.execute('SELECT nature, montant, annee, mois FROM c3_charge WHERE ref = ? '
                                                   'ORDER BY nature, annee, mois', (ref,))]
            operations = [dict(r) for r in cx.execute(
                'SELECT date_operation, type_operation, libelle, debit, credit FROM c3_operation WHERE ref = ? '
                'ORDER BY date_operation LIMIT 200', (ref,))]
            vehicules = [dict(r) for r in cx.execute('SELECT type_piece, marque, modele, etat, prix FROM c3_vehicule '
                                                     'WHERE ref = ?', (ref,))]
            incoherences = []
            for t, g, ref_b in cx.execute('SELECT type, gravite, ref_b FROM c3_incoherence WHERE ref = ? ORDER BY 1',
                                          (ref,)):
                incoherences.append(dict(type=t, libelle=LIBELLES_INCOHERENCE.get(t, t), gravite=g,
                                         autre_dossier=self.indice_dossier.get(ref_b) if ref_b != ref else None))
            controles = [dict(r) for r in cx.execute(
                'SELECT c."controlId" AS controle, c.outcome AS resultat, c.criticality AS criticite '
                'FROM "AnalysisControl" c JOIN "Dossier" d ON d.id = c."dossierId" WHERE d.ref = ? '
                'ORDER BY c."controlId"', (ref,))]
            chemins = [self._chemin_lisible(cx, ch, ref) for ch in self.chemins_dossier.get(ref, [])[:3]]
            return dict(indice=indice, entete=entete, pieces=pieces, parties=parties, revenus=revenus, charges=charges,
                        operations=operations, vehicules=vehicules, incoherences=incoherences, controles=controles,
                        chemins=chemins)
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
                    for v, code in cx.execute("SELECT vers, code FROM c5_arete WHERE type = 'role' AND de = ? UNION "
                                              "SELECT de, code FROM c5_arete WHERE type = 'role' AND vers = ?", (u, u)):
                        voisins.append((v, code, None))
                    for noeud, code in cx.execute("SELECT DISTINCT vers, code FROM c5_arete WHERE type = 'identifiant' "
                                                  'AND de = ?', (u,)).fetchall():
                        porteurs = [p[0] for p in cx.execute("SELECT DISTINCT de FROM c5_arete WHERE vers = ? AND de <> ?",
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
                        [cx.execute('SELECT code FROM c5_arete WHERE vers = ? LIMIT 1', (n,)).fetchone()[0]]}
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
