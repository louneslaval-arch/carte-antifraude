"""Couche 0 : versions brutes des dossiers de la v2 et miroir de sa base.

- `c0_dossier_brut` garde chaque version reçue telle quelle (JSON complet), avec son empreinte : une empreinte = un
  JSON ; une version déjà reçue n'ajoute rien ; une version modifiée s'ajoute, l'ancienne reste intacte.
- Le miroir (tables de Kamal, générées depuis `schema.prisma`) montre, pour chaque dossier, la projection de sa
  version la plus récente (`updatedAt` le plus grand). Rien n'est interprété : ni normalisation, ni filtre.

`recevoir` (au fil de l'eau), `traiter` (un dossier) et `construire_tout` (tout rejouer) passent par la même
fonction `projeter` : le flux et le lot donnent le même miroir.

Ce que l'API de la v2 n'expose pas et que sa base exige, posé ici (noté dans `docs/correspondance_v2.md`) :
`Piece.id` et `Reanalysis.id` (dérivés de l'identifiant du dossier), `Piece.createdAt` et `updatedAt` (ceux du
dossier), `AnalysisControl.dossierId`, `Dossier.actif` (connu par la liste, avec ou sans archives). En lecture
directe de la base de Kamal (production), ces valeurs viendront de ses tables, sans rien dériver.
"""
import datetime
import hashlib
import json
import sqlite3
import uuid

nom = 'c0'
BRUT = 'version brute seulement'

_DOSSIER = ('id', 'ref', 'personType', 'csp', 'productType', 'paymentMode', 'clientName', 'agence', 'canal',
            'category', 'categoryRule', 'categoryReason', 'analysisStatus', 'verdict', 'verdictProvisional',
            'alertsMinor', 'alertsMajor', 'alertsCritical', 'commentaireScore', 'commentaireAlerte', 'matrixVersion',
            'businessReceivedAt', 'resultsReceivedAt', 'createdAt', 'updatedAt', 'businessData')
_PIECE = ('upstreamPieceId', 'type', 'extractionStatus', 'pdfPath', 'fields', 'source')
_ANALYSE = ('id', 'trigger', 'status', 'verdict', 'provisional', 'startedAt', 'endedAt', 'matrixVersion',
            'engineVersion', 'error')
_RELECTURE = ('controlId', 'pieceId', 'requestedFields', 'result', 'status', 'createdAt', 'completedAt')
_CONTROLE = ('id', 'controlId', 'applicable', 'applicabilityReason', 'outcome', 'criticality', 'escalade',
             'explanation', 'details', 'missing', 'source', 'computedAt')
_CONTROLE_BRUT = ('label', 'family', 'numeroMetier', 'previousOutcome')     # enrichissements de l'API, hors base

# Place de chaque champ de DossierDetail : (table du miroir, colonne), ou la version brute seulement.
PLACES = {c: ('Dossier', c) for c in _DOSSIER}
PLACES.update({'pieces': ('Piece', 'dossierId'), 'analyses': ('Analysis', 'dossierId'),
               'reanalyses': ('Reanalysis', 'dossierId'), 'latestAnalysis': ('Analysis', 'id'), 'synthese': BRUT})
PLACES.update({'pieces[].' + c: ('Piece', c) for c in _PIECE})
PLACES.update({'analyses[].' + c: ('Analysis', c) for c in _ANALYSE})
PLACES.update({'reanalyses[].' + c: ('Reanalysis', c) for c in _RELECTURE})
PLACES.update({'latestAnalysis.' + c: ('Analysis', c) for c in _ANALYSE})
PLACES['latestAnalysis.controls'] = ('AnalysisControl', 'analysisId')
PLACES.update({'latestAnalysis.controls[].' + c: ('AnalysisControl', c) for c in _CONTROLE})
PLACES.update({'latestAnalysis.controls[].' + c: BRUT for c in _CONTROLE_BRUT})


class DossierIllisible(ValueError):
    """Dossier sans référence ou sans date de mise à jour. Le message ne cite jamais son contenu."""


class MiroirRefuse(ValueError):
    """La version est gardée brute, mais le miroir la refuse (valeur hors des énumérations de Kamal, clé manquante)."""


def _maintenant():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def empreinte(detail):
    """SHA-256 du JSON mis en forme canonique : indépendante de l'ordre des clés."""
    texte = json.dumps(detail, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(texte.encode('utf-8')).hexdigest()


def ouvrir_passage(cx, source, mode, maintenant=None):
    passage = str(uuid.uuid4())
    cx.execute('INSERT INTO c0_export (id, source, mode, commence_le) VALUES (?, ?, ?, ?)',
               (passage, source, mode, maintenant or _maintenant()))
    cx.commit()
    return passage


def fermer_passage(cx, passage, dossiers, versions_nouvelles, maintenant=None):
    cx.execute('UPDATE c0_export SET dossiers = ?, versions_nouvelles = ?, termine_le = ? WHERE id = ?',
               (dossiers, versions_nouvelles, maintenant or _maintenant(), passage))
    cx.commit()


def _valeur(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return v


def _inserer(cx, table, ligne):
    colonnes = ', '.join(f'"{c}"' for c in ligne)
    cx.execute(f'INSERT INTO "{table}" ({colonnes}) VALUES ({", ".join("?" * len(ligne))})',
               [_valeur(v) for v in ligne.values()])


def _retirer(cx, ref):
    ligne = cx.execute('SELECT id FROM "Dossier" WHERE ref = ?', (ref,)).fetchone()
    if ligne:
        for table in ('AnalysisControl', 'Reanalysis', 'Analysis', 'Piece'):
            cx.execute(f'DELETE FROM "{table}" WHERE "dossierId" = ?', (ligne[0],))
        cx.execute('DELETE FROM "Dossier" WHERE id = ?', (ligne[0],))


def projeter(cx, ref):
    """Remplace, dans le miroir, le dossier `ref` par la projection de sa version la plus récente."""
    version = cx.execute('SELECT json, actif FROM c0_dossier_brut WHERE ref = ? '
                         'ORDER BY updated_at DESC, recu_le DESC, empreinte DESC LIMIT 1', (ref,)).fetchone()
    _retirer(cx, ref)
    if version is None:
        return
    d, actif = json.loads(version[0]), version[1]
    identifiant = d['id']
    _inserer(cx, 'Dossier', dict({c: d.get(c) for c in _DOSSIER}, actif=actif))
    for p in d.get('pieces') or []:
        _inserer(cx, 'Piece', dict({c: p.get(c) for c in _PIECE}, id=f"{identifiant}:{p.get('upstreamPieceId')}",
                                   dossierId=identifiant, createdAt=d.get('createdAt'), updatedAt=d.get('updatedAt')))
    derniere = d.get('latestAnalysis')
    analyses = {a['id']: a for a in d.get('analyses') or []}
    if derniere:
        analyses.setdefault(derniere['id'], derniere)
    for a in analyses.values():
        _inserer(cx, 'Analysis', dict({c: a.get(c) for c in _ANALYSE}, dossierId=identifiant))
    for c in (derniere or {}).get('controls') or []:
        ligne = dict({k: c.get(k) for k in _CONTROLE}, analysisId=derniere['id'], dossierId=identifiant)
        ligne['applicabilityReason'] = ligne['applicabilityReason'] or ''     # obligatoire dans la base, vide permis
        _inserer(cx, 'AnalysisControl', ligne)
    for k, r in enumerate(d.get('reanalyses') or []):
        _inserer(cx, 'Reanalysis', dict({c: r.get(c) for c in _RELECTURE}, id=f'{identifiant}:relecture:{k}',
                                        dossierId=identifiant))


def recevoir(cx, passage, detail, actif=True, maintenant=None):
    """Garde la version reçue si elle est nouvelle, puis met le miroir à jour. Rend vrai si la version est nouvelle."""
    ref, mise_a_jour = (detail.get('ref'), detail.get('updatedAt')) if isinstance(detail, dict) else (None, None)
    if not isinstance(ref, str) or not ref or not isinstance(mise_a_jour, str) or not detail.get('id'):
        raise DossierIllisible('dossier sans référence, sans identifiant ou sans date de mise à jour')
    marque = empreinte(detail)
    nouvelle = cx.execute('SELECT 1 FROM c0_dossier_brut WHERE ref = ? AND empreinte = ?', (ref, marque)).fetchone() is None
    if nouvelle:
        cx.execute('INSERT INTO c0_dossier_brut (ref, empreinte, updated_at, json, actif, passage, recu_le) '
                   'VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (ref, marque, mise_a_jour, json.dumps(detail, ensure_ascii=False), int(actif), passage,
                    maintenant or _maintenant()))
    else:
        cx.execute('UPDATE c0_dossier_brut SET actif = ? WHERE ref = ? AND empreinte = ?', (int(actif), ref, marque))
    cx.commit()                                       # la version brute est acquise, quoi que dise le miroir
    try:
        projeter(cx, ref)
    except (sqlite3.IntegrityError, KeyError, TypeError) as e:
        cx.rollback()
        raise MiroirRefuse(f'miroir refusé ({type(e).__name__})') from None
    cx.commit()
    return nouvelle


def traiter(cx, ref):
    projeter(cx, ref)
    cx.commit()


def construire_tout(cx):
    """Reconstruit tout le miroir depuis les versions brutes."""
    for table in ('AnalysisControl', 'Reanalysis', 'Analysis', 'Piece', 'Dossier'):
        cx.execute(f'DELETE FROM "{table}"')
    for (ref,) in cx.execute('SELECT DISTINCT ref FROM c0_dossier_brut ORDER BY ref').fetchall():
        try:
            projeter(cx, ref)
        except (sqlite3.IntegrityError, KeyError, TypeError):
            _retirer(cx, ref)                         # version que le miroir refuse : elle reste brute seulement
    cx.commit()
