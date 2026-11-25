"""Couche 5 : le graphe et la recherche des chemins vers la liste noire.

Nœuds : les fiches de c2 (personnes, sociétés) et les identifiants partagés (RIB, logement, siège). Arêtes, une par
mention de c2 : rôle d'une personne dans une société (gérant, associé, liquidateur, employé…), ou fiche qui porte un
identifiant. Les homonymies (rapprochements de c2 non fusionnés, avec la décision de l'analyste) sont lues dans c2
au moment de la recherche. Rien de global n'est figé dans une arête : la taille n de chaque nœud est dans
`c5_compteur`, lue au moment du calcul ; le barème, les seuils et les limites dans `c6_version_parametres`.

`traiter(cx, ref)` refait les arêtes des mentions du dossier et de toute mention dont la fiche a changé, puis les
compteurs des nœuds touchés : le fil de l'eau égale le lot. `chemins(cx, ref)` cherche, depuis les identités du
dossier, les meilleurs chemins vers les inscrits (règles de `.claude/rules/score.md`). Les chemins d'un dossier ne
sont pas stockés ici : leur mise à jour quand un autre dossier change est la propagation de l'étape I.

Aucune sortie, aucun message ne porte de valeur ; un chemin rendu ne cite que des identifiants internes de fiche et
des codes, jamais la valeur d'un identifiant partagé.
"""
import hashlib
import heapq
import math

from pipeline import construire_base as cb

nom = 'c5'


def _executemany(cx, requete, lignes):
    with cx.cursor() as curseur:
        curseur.executemany(requete, lignes)

TABLES = ('c5_cle_adresse', 'c5_arete', 'c5_compteur')
NIVEAUX = ('critique', 'majeure', 'mineure', 'affiche', 'hors_alerte')
POIDS_IDENTIFIANT = {'RIB': 'c5_poids_meme_rib', 'LOGEMENT': 'c5_poids_meme_logement', 'SIEGE': 'c5_poids_meme_siege'}
ROLES_RIB = ('titulaire_compte', 'employe')
ROLES_DE_DEPART = ('societe', 'employeur', 'gerant', 'dirigeant', 'nouveau_gerant')
SIGNALEMENTS = ('CIN_PARTAGE', 'RC_PARTAGE', 'CLE_PARTAGEE')      # signalés par c2, ce ne sont pas des liens
# rapprochement du kit selon sa nature : le rôle du barème qu'il représente (un lien, pas une identité)
RAPPROCHEMENTS = {'dirigeant': 'dirigeant', 'emploi': 'employe', 'adresse': 'meme_siege'}
HOMONYMIES_AUTRES = ('AF07',)                                     # employeur reconnu par son seul nom : une homonymie
PRENOMS = set(cb.PRENOMS_CANON) | set(cb.PRENOMS_CANON.values())


class ParametreAbsent(LookupError):
    """Un paramètre dont la couche a besoin manque dans `c6_version_parametres`."""


def noeud_identifiant(code, valeur):
    """Nœud d'un identifiant partagé : son type et une empreinte de sa valeur, jamais la valeur en clair (une clé de
    nœud peut finir dans une URL, un événement ou un message d'erreur)."""
    return f'{code.lower()}_' + hashlib.sha256(f'{code}|{valeur}'.encode('utf-8')).hexdigest()[:16]


def cout(n):
    """Coût de taille d'un nœud traversé (décision n°21) : 1 jusqu'à 2, sinon √(2/n)."""
    return 1.0 if n <= 2 else math.sqrt(2 / n)


def parametres(cx):
    p = dict(cx.execute("SELECT nom, valeur FROM parametre WHERE nom LIKE 'c5\\_%' ESCAPE '\\'").fetchall())
    besoins = ('c5_seuil_majeure', 'c5_seuil_mineure', 'c5_seuil_affichage', 'c5_longueur_alerte',
               'c5_longueur_recherche', 'c5_fiabilite_homonymie', 'c5_poids_foyer', 'c5_poids_inconnu') + \
        tuple(POIDS_IDENTIFIANT.values())
    if set(besoins) - set(p):
        raise ParametreAbsent('paramètre de c5 absent de c6_version_parametres')
    return p


def poids_role(p, code):
    """Poids de départ d'un rôle (barème n°23) ; un rôle absent du barème vaut le poids d'un rôle inconnu."""
    return p.get('c5_poids_' + code, p['c5_poids_inconnu'])


def poids_participation(p, code, parts):
    """Barème des associés : 0,3 + 0,4 × part (part exprimée en %).

    Une participation absente ou invalide conserve le poids de rôle paramétré.
    """
    if code not in ('associe', 'associe_present') or parts is None:
        return poids_role(p, code)
    try:
        brut = str(parts).strip().replace('%', '').replace(',', '.')
        valeur = float(brut)
    except (ValueError, TypeError):
        return poids_role(p, code)
    if not math.isfinite(valeur) or valeur < 0 or valeur > 100:
        return poids_role(p, code)
    return 0.3 + 0.4 * valeur / 100.0


def niveau(p, longueur, force, plafond=None):
    """Niveau d'un chemin : la force le décide, sous le maximum que permet sa longueur (et un plafond éventuel)."""
    force = round(force, 9)                               # 0,6 × √(2/18) atteint bien 0,20
    if force < p['c5_seuil_affichage']:
        return None
    if longueur > p['c5_longueur_alerte']:
        return 'hors_alerte'
    par_force = 'majeure' if force >= p['c5_seuil_majeure'] else 'mineure' if force >= p['c5_seuil_mineure'] \
        else 'affiche'
    maximum = 'critique' if longueur == 0 else 'majeure' if longueur <= 2 else 'mineure'
    if plafond:
        maximum = max(maximum, plafond, key=NIVEAUX.index)
    if longueur == 0 and not plafond:
        return 'critique'
    return max(par_force, maximum, key=NIVEAUX.index)


# ---- construction des arêtes ---------------------------------------------------------------------------------------

COLONNES_MENTION = ('id', 'source', 'type_fiche', 'ref', 'upstream_piece_id', 'role', 'adresse', 'fiche',
                    'societe_mention', 'parts')


def _mentions(cx, ids):
    sortie, ids = [], sorted(set(ids))
    for i in range(0, len(ids), 400):
        lot = ids[i:i + 400]
        sortie += [dict(zip(COLONNES_MENTION, r)) for r in cx.execute(
            f'SELECT {", ".join(COLONNES_MENTION)} FROM c2_mention WHERE id IN ({", ".join(["%s"] * len(lot))})', lot)]
    return sortie


def _adresses(cx, mentions):
    lignes = []
    for m in mentions:
        cle = cb.cle_adresse(m['adresse']) if m['adresse'] else None
        if cle:                                           # la ville reste dans la clé : même rue, autre ville, autre lieu
            lignes.append((m['id'], m['ref'], f"{cle}|{cb.villes_dans(m['adresse']) or ''}"))
    _executemany(cx, 'INSERT INTO c5_cle_adresse (mention, ref, cle) VALUES (%s, %s, %s)', lignes)


def _aretes(cx, mentions):
    """Arêtes des mentions données (lues dans c2 et c1 telles qu'elles sont maintenant)."""
    fiches = {m['id']: m['fiche'] for m in mentions}
    manquantes = {m['societe_mention'] for m in mentions if m['societe_mention']} - set(fiches)
    fiches.update({m['id']: m['fiche'] for m in _mentions(cx, manquantes)})
    adresses, ids = {}, [m['id'] for m in mentions]
    for i in range(0, len(ids), 400):
        lot = ids[i:i + 400]
        adresses.update(cx.execute(f'SELECT mention, cle FROM c5_cle_adresse WHERE mention IN ({", ".join(["%s"] * len(lot))})',
                                   lot).fetchall())
    lignes = []
    for m in mentions:
        if not m['fiche']:
            continue
        societe = fiches.get(m['societe_mention']) if m['societe_mention'] else None
        if societe:
            lignes.append(('R|' + m['id'], 'role', m['id'], m['societe_mention'], m['fiche'], societe,
                           m['role'] or 'inconnu', m['parts'], m['source'], m['ref']))
        if m['id'] in adresses:
            code = 'LOGEMENT' if m['type_fiche'] == 'PP' else 'SIEGE'
            lignes.append(('A|' + m['id'], 'identifiant', m['id'], None, m['fiche'],
                           noeud_identifiant(code, adresses[m['id']]), code, None, m['source'], m['ref']))
        if m['source'] == 'v2' and m['role'] in ROLES_RIB:
            for rang, (rib,) in enumerate(cx.execute(
                    "SELECT valeur FROM c1_identifiant_brut WHERE ref = %s AND upstream_piece_id = %s AND type = 'RIB' "
                    'ORDER BY valeur', (m['ref'], m['upstream_piece_id'])).fetchall()):
                lignes.append((f'B|{m["id"]}|{rang}', 'identifiant', m['id'], None, m['fiche'],
                               noeud_identifiant('RIB', rib), 'RIB', None, m['source'], m['ref']))
    _executemany(cx, 'INSERT INTO c5_arete VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', lignes)
    return {x for ligne in lignes for x in (ligne[4], ligne[5])}


def _compter(cx, noeuds):
    """Recalcule la taille des nœuds donnés : voisins distincts par un rôle, ou porteurs distincts d'un identifiant."""
    noeuds = sorted(n for n in set(noeuds) if n)
    for i in range(0, len(noeuds), 400):
        lot = noeuds[i:i + 400]
        marques = ', '.join(['%s'] * len(lot))
        cx.execute(f'DELETE FROM c5_compteur WHERE noeud IN ({marques})', lot)
        cx.execute(
            'INSERT INTO c5_compteur (noeud, n) SELECT noeud, count(DISTINCT voisin) FROM ('
            f"SELECT de AS noeud, vers AS voisin FROM c5_arete WHERE type = 'role' AND de IN ({marques}) "
            f"UNION ALL SELECT vers, de FROM c5_arete WHERE type = 'role' AND vers IN ({marques}) "
            f"UNION ALL SELECT vers, de FROM c5_arete WHERE type = 'identifiant' AND vers IN ({marques})"
            ') v GROUP BY noeud', lot * 3)


def _construire(cx):
    parametres(cx)
    cx.execute('DELETE FROM c5_a_refaire')
    for table in TABLES:
        cx.execute(f'DELETE FROM {table}')
    mentions = [dict(zip(COLONNES_MENTION, r)) for r in cx.execute(
        f'SELECT {", ".join(COLONNES_MENTION)} FROM c2_mention ORDER BY id').fetchall()]
    _adresses(cx, mentions)
    for i in range(0, len(mentions), 2000):
        _aretes(cx, mentions[i:i + 2000])
    cx.execute(
        'INSERT INTO c5_compteur (noeud, n) SELECT noeud, count(DISTINCT voisin) FROM ('
        "SELECT de AS noeud, vers AS voisin FROM c5_arete WHERE type = 'role' "
        "UNION ALL SELECT vers, de FROM c5_arete WHERE type = 'role' "
        "UNION ALL SELECT vers, de FROM c5_arete WHERE type = 'identifiant') v GROUP BY noeud")


def _traiter(cx, ref):
    parametres(cx)
    actuelles = [m for (m,) in cx.execute("SELECT id FROM c2_mention WHERE source = 'v2' AND ref = %s", (ref,))]
    cx.execute('DELETE FROM c5_cle_adresse WHERE ref = %s', (ref,))
    _adresses(cx, _mentions(cx, actuelles))
    touchees = set(actuelles) | {m for (m,) in cx.execute('SELECT mention FROM c5_arete WHERE ref = %s', (ref,))}
    # mentions dont la fiche a changé ou qui ont disparu (relevées par les déclencheurs de c2_mention), et les
    # personnes dont la société est l'une d'elles
    changees = {m for (m,) in cx.execute('SELECT mention FROM c5_a_refaire')}
    touchees |= changees
    lot_ = sorted(changees)
    for i in range(0, len(lot_), 400):
        morceau = lot_[i:i + 400]
        touchees |= {m for (m,) in cx.execute(
            f'SELECT mention FROM c5_arete WHERE mention_b IN ({", ".join(["%s"] * len(morceau))})', morceau)}
    cx.execute('DELETE FROM c5_a_refaire')
    noeuds = set()
    ids = sorted(touchees)
    for i in range(0, len(ids), 400):
        lot = ids[i:i + 400]
        marques = ', '.join(['%s'] * len(lot))
        for de, vers in cx.execute(f'SELECT de, vers FROM c5_arete WHERE mention IN ({marques})', lot):
            noeuds |= {de, vers}
        cx.execute(f'DELETE FROM c5_arete WHERE mention IN ({marques})', lot)
    # une mention touchée qui reste dans c2 retrouve ses arêtes ; une mention du registre sans adresse normalisée
    # (rechargée hors de c5) garde sa clé d'adresse
    restantes = _mentions(cx, touchees)
    sans_cle = [m for m in restantes if m['adresse'] and m['source'] != 'v2' and not cx.execute(
        'SELECT 1 FROM c5_cle_adresse WHERE mention = %s', (m['id'],)).fetchone()]
    _adresses(cx, sans_cle)
    for i in range(0, len(restantes), 2000):
        noeuds |= _aretes(cx, restantes[i:i + 2000])
    _compter(cx, noeuds)


def _tout_ou_rien(cx, action, *arguments):
    try:
        action(cx, *arguments)
    except BaseException:
        cx.rollback()
        raise
    cx.commit()


def traiter(cx, ref):
    _tout_ou_rien(cx, _traiter, ref)


def construire_tout(cx):
    _tout_ou_rien(cx, _construire)


# ---- recherche des chemins -----------------------------------------------------------------------------------------

def _famille(nom_):
    """Mots d'un nom qui ne sont pas des prénoms connus : de quoi reconnaître un même nom de famille."""
    return set(cb.mots_nom_latin(nom_ or '')) - PRENOMS


def _graphe_c7(relations, demandeurs, poids):
    """Construit les voisins C7 sans dévoiler les clés et sans inventer de liens.

    `relations`: (ref, code, fiche, noeud). Les liens entre dossiers sont
    fondés exclusivement sur une même clé C7 explicitement attestée.
    """
    from collections import defaultdict

    voisins, groupes = defaultdict(list), defaultdict(set)
    for ref, code, fiche, noeud in relations:
        force = poids.get('c7_poids_' + code)
        if force is None:
            raise ParametreAbsent('poids C7 absent : ' + code)
        if code in ('caution', 'coemprunteur', 'reference_personnelle'):
            if fiche:
                for depart in demandeurs.get(ref, ()):
                    if depart != fiche:
                        for a, b in ((depart, fiche), (fiche, depart)):
                            voisins[a].append((b, 1, force, dict(type='c7', code=code, de=a, vers=b),
                                               None, False, None))
        elif noeud:
            groupes[(code, noeud)].add(ref)
    tailles = {}
    for (code, noeud), refs in groupes.items():
        if len(refs) < 2:
            continue
        fiches = set().union(*(demandeurs.get(ref, set()) for ref in refs))
        tailles[noeud] = len(fiches)
        for ref in refs:
            autres = set().union(*(demandeurs.get(r, set()) for r in refs - {ref}))
            for a in demandeurs.get(ref, ()):
                for b in autres - {a}:
                    voisins[a].append((b, 1, poids['c7_poids_' + code],
                                       dict(type='c7', code=code, de=a, vers=b), None, False, noeud))
    return voisins, tailles


class Contexte:
    """Ce qu'une recherche lit une fois : paramètres, inscrits, homonymies de c2. Réutilisable pour plusieurs
    dossiers tant que la base ne change pas."""

    def __init__(self, cx):
        self.cx = cx
        self.p = parametres(cx)
        self.inscrits = {i for (i,) in cx.execute('SELECT identifiant FROM c2_personne WHERE inscrit = 1 UNION '
                                                  'SELECT identifiant FROM c2_societe WHERE inscrit = 1')}
        poids = {}
        for a, b, regle, valeur in cx.execute(
                'SELECT ma.fiche, mb.fiche, c.regle, max(c.poids) FROM c2_correspondance_mention c '
                'JOIN c2_mention ma ON ma.id = c.mention_a JOIN c2_mention mb ON mb.id = c.mention_b '
                'WHERE ma.fiche IS NOT NULL AND mb.fiche IS NOT NULL GROUP BY 1, 2, 3'):
            poids[(a, b, regle)] = valeur
        self.homonymies, self.rapprochements = {}, {}
        for a, b, regle, nature, niveau_, statut in cx.execute(
                'SELECT fiche_a, fiche_b, regle, nature, niveau, statut FROM c2_correspondance ORDER BY 1, 2, 3'):
            if statut in ('ecarte', 'faible') or regle in SIGNALEMENTS:     # « faible » : hors graphe, comme le kit
                continue
            certain = statut == 'confirme' or niveau_ == 'certain'
            lu = poids.get((a, b, regle))
            fiabilite = 1.0 if certain else (lu if lu is not None else self.p['c5_fiabilite_homonymie'])
            if nature != 'identite' and regle not in HOMONYMIES_AUTRES:
                # un rapprochement qui n'est pas une identité (dirigeant, emploi, adresse) : un lien du barème
                lien = poids_role(self.p, RAPPROCHEMENTS.get(nature, 'inconnu')) * min(fiabilite, 1.0)
                for x, y in ((a, b), (b, a)):
                    actuel = self.rapprochements.get((x, y))
                    if actuel is None or lien > actuel[0]:
                        self.rapprochements[(x, y)] = (lien, None if certain else 'mineure', regle)
                continue
            for x, y in ((a, b), (b, a)):
                actuel = self.homonymies.get((x, y))
                candidat = (min(fiabilite, 1.0), not certain, regle)
                if actuel is None or (candidat[1], -candidat[0]) < (actuel[1], -actuel[0]):
                    self.homonymies[(x, y)] = candidat
        self.voisins_rapproches = {}
        for x, y in self.rapprochements:
            self.voisins_rapproches.setdefault(x, []).append(y)
        self.voisins_homonymes = {}
        for x, y in self.homonymies:
            self.voisins_homonymes.setdefault(x, []).append(y)
        self.voisins_c7, self.tailles_c7 = {}, {}
        if cx.execute("SELECT to_regclass('c7_relation')").fetchone()[0] is not None:
            poids_c7 = dict(cx.execute("SELECT nom, valeur FROM parametre WHERE nom LIKE 'c7_poids_%'").fetchall())
            demandes = {}
            for ref, fiche in cx.execute('SELECT ref, fiche FROM c3_demandeur WHERE fiche IS NOT NULL'):
                demandes.setdefault(ref, set()).add(fiche)
            lignes = cx.execute('SELECT ref, code, fiche, noeud FROM c7_relation').fetchall()
            self.voisins_c7, self.tailles_c7 = _graphe_c7(lignes, demandes, poids_c7)
        self._n, self._noms = {}, {}

    def n(self, noeud):
        if noeud in self.tailles_c7:
            return self.tailles_c7[noeud]
        if noeud not in self._n:
            ligne = self.cx.execute('SELECT n FROM c5_compteur WHERE noeud = %s', (noeud,)).fetchone()
            self._n[noeud] = ligne[0] if ligne else 1
        return self._n[noeud]

    def famille(self, fiche):
        """Nom de famille lu à part sur la CIN (champ `nom` de la pièce) ; sans CIN lue, aucun foyer n'est reconnu."""
        if fiche not in self._noms:
            self._noms[fiche] = {mot for (nom_,) in self.cx.execute(
                "SELECT f.texte_norm FROM c2_mention m JOIN c1_fait_retenu f ON f.ref = m.ref AND f.upstream_piece_id = "
                "m.upstream_piece_id AND f.type = 'CIN' AND f.cle = 'nom' WHERE m.fiche = %s AND m.role = 'titulaire_cin'",
                (fiche,)) if nom_ for mot in nom_.split() if len(mot) > 2}
        return self._noms[fiche]

    def liens(self, u):
        """Liens qui partent d'une fiche : (voisin, longueur ajoutée, poids, étape, plafond, foyer, nœud traversé)."""
        p, sortie = self.p, []
        sortie.extend(self.voisins_c7.get(u, ()))
        roles = {}
        for voisin, code, parts in self.cx.execute("SELECT vers, code, parts FROM c5_arete WHERE type = 'role' AND de = %s "
                                            "UNION SELECT de, code, parts FROM c5_arete WHERE type = 'role' AND vers = %s",
                                            (u, u)):
            poids = poids_participation(p, code, parts)
            if voisin != u and poids > roles.get(voisin, (0, None))[0]:
                roles[voisin] = (poids, code)
        for voisin, (poids, code) in sorted(roles.items()):
            sortie.append((voisin, 1, poids, dict(type='role', code=code, de=u, vers=voisin), None, False, None))
        for noeud, code in self.cx.execute("SELECT DISTINCT vers, code FROM c5_arete WHERE type = 'identifiant' "
                                           'AND de = %s ORDER BY 1', (u,)).fetchall():
            for (voisin,) in self.cx.execute("SELECT DISTINCT de FROM c5_arete WHERE type = 'identifiant' AND vers = %s "
                                             'AND de <> %s ORDER BY 1', (noeud, u)).fetchall():
                foyer = code == 'LOGEMENT' and u.startswith('pp_') and voisin.startswith('pp_') and \
                    bool(self.famille(u) & self.famille(voisin))
                poids = p['c5_poids_foyer'] if foyer else p[POIDS_IDENTIFIANT[code]]
                sortie.append((voisin, 1, poids, dict(type='identifiant', code=code, de=u, vers=voisin),
                               'mineure' if foyer else None, foyer, noeud))
        for voisin in sorted(self.voisins_rapproches.get(u, ())):
            poids, plafond, regle = self.rapprochements[(u, voisin)]
            sortie.append((voisin, 1, poids, dict(type='rapprochement', code=regle, de=u, vers=voisin), plafond,
                           False, None))
        for voisin in sorted(self.voisins_homonymes.get(u, ())):
            fiabilite, a_lever, regle = self.homonymies[(u, voisin)]
            sortie.append((voisin, 0, fiabilite, dict(type='homonymie', code=regle, de=u, vers=voisin),
                           'mineure' if a_lever else None, False, None))
        return sortie


def _departs(cx, ref):
    return sorted({f for (f,) in cx.execute(
        'SELECT fiche FROM c3_demandeur WHERE ref = %s UNION SELECT fiche FROM c3_partie_dossier WHERE ref = %s '
        f'AND role IN ({", ".join(["%s"] * len(ROLES_DE_DEPART))})', (ref, ref, *ROLES_DE_DEPART))})


def chemins(cx, ref, contexte=None):
    """Meilleur chemin vers chaque inscrit atteint depuis les identités du dossier, du plus grave au moins grave."""
    return chercher(contexte or Contexte(cx), _departs(cx, ref))


def chercher(k, departs):
    """Recherche par force décroissante. Chaque chemin rendu : cible (fiche inscrite), longueur, force, niveau,
    homonymie (à lever, à un bout), foyer, étapes (identifiants internes de fiche et codes seulement).

    Règles (`.claude/rules/score.md`) : le coût de taille s'applique aux nœuds traversés, jamais aux deux bouts ; une
    homonymie (0 lien) qui touche un bout (le départ, ou l'inscrit) fait de la fiche rapprochée ce bout lui-même (pas
    de coût) et plafonne le niveau à « mineure » ; au milieu, elle n'agit que sur la force. On s'arrête au premier
    inscrit atteint ; un chemin ne repasse ni par une fiche ni par un identifiant."""
    p = k.p
    limite, plancher = p['c5_longueur_recherche'], p['c5_seuil_affichage']
    departs = sorted(set(departs))
    # état : (-force, longueur, nœud, rang, étapes, plafond, foyer, est un bout de départ, départ d'origine, passés)
    tas = [(-1.0, 0, d, r, (), None, False, True, True, frozenset({d})) for r, d in enumerate(departs)]
    rang = len(tas)
    vus, meilleurs = {}, {}
    while tas:
        moins_force, longueur, u, _, etapes, plafond, foyer, bout, origine, passes = heapq.heappop(tas)
        force = -moins_force
        etat = (plafond is not None, foyer)
        if any(lg <= longueur and f >= force and e[0] <= etat[0] and e[1] <= etat[1] for lg, f, e in vus.get(u, ())):
            continue
        vus.setdefault(u, []).append((longueur, force, etat))
        if u in k.inscrits:
            niv = niveau(p, longueur, force, plafond)
            if niv:
                candidat = dict(cible=u, longueur=longueur, force=round(force, 6), niveau=niv,
                                homonymie=plafond is not None and any(e['type'] == 'homonymie' for e in etapes),
                                foyer=foyer, etapes=list(etapes))
                actuel = meilleurs.get(u)
                if actuel is None or (NIVEAUX.index(niv), -candidat['force'], longueur) < \
                        (NIVEAUX.index(actuel['niveau']), -actuel['force'], actuel['longueur']):
                    meilleurs[u] = candidat
            if not origine:
                continue                                  # on s'arrête au premier inscrit atteint
        for voisin, ajout, poids, etape, plafond_lien, foyer_lien, noeud in k.liens(u):
            homonymie = etape['type'] == 'homonymie'
            vers_inscrit = voisin in k.inscrits
            # le coût de u : jamais s'il est un bout (départ, ou fiche rapprochée de l'inscrit qu'on rejoint)
            traverse = 1.0 if bout or (homonymie and vers_inscrit) else cout(k.n(u))
            nouvelle = force * traverse * poids * (cout(k.n(noeud)) if noeud else 1.0)
            if longueur + ajout > limite or nouvelle < plancher or voisin in departs or voisin in passes \
                    or (noeud and noeud in passes):     # un chemin ne repasse ni par une fiche ni par un identifiant
                continue
            if homonymie and not (bout or vers_inscrit):
                plafond_lien = None                       # homonymie au milieu : la force seulement
            rang += 1                                     # départage stable : jamais de comparaison d'étapes
            heapq.heappush(tas, (-nouvelle, longueur + ajout, voisin, rang, etapes + (dict(etape),),
                                 plafond_lien or plafond, foyer or foyer_lien, bout and homonymie, False,
                                 passes | {voisin} | ({noeud} if noeud else set())))
    return sorted(meilleurs.values(), key=lambda c: (NIVEAUX.index(c['niveau']), -c['force'], c['longueur'], c['cible']))
