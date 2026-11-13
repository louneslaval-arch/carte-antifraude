#!/usr/bin/env python3
"""Serveur v2 fictif (étape C.3) : sert des dossiers fictifs comme l'antifraude v2 de Kamal, sans Kamal ni donnée
réelle, pour éprouver le collecteur de bout en bout.

Routes, paramètres, réponses et erreurs repris du README de Kamal (§ 2) et de ses types :
  POST /api/auth/login {email, password}            → {token, role, fullName}
  GET  /api/dossiers?limit&offset&status&verdict&category&search&from&to&archives
                                                    → {items, total, counts: {verdict, status, category}}, sans pièces
  GET  /api/dossiers/:ref                           → DossierDetail
  GET  /api/dossiers/:ref/controls/:controlId       → un contrôle, enrichi de sourcePrincipale
Erreurs : {"error": "unauthorized" | "dossier_inconnu" | …}, jamais une valeur reçue.

Chronologie : chaque dossier arrive à son instant, une relecture remplace sa version au sien ; l'horloge se règle
(`application.state.horloge`). À chaque événement franchi, une notification signée peut partir vers
`POST /api/flux/v2` : corps {ref, updatedAt, analysisStatus, trigger}, HMAC SHA-256 du corps, horodatage.

Provisoire, faute de précision chez Kamal (questions ouvertes) : tri de la liste (création décroissante), valeur par
défaut et maximum de `limit` (50, 500), noms des en-têtes de la notification, code 400 `parametre_invalide`.

Usage : serveur_v2.py [--port 8720] [--dossiers 1000] [--societes 400] [--notifier http://127.0.0.1:8710/api/flux/v2]
Comptes fictifs : analyste@exemple.invalid / mot-de-passe-fictif.
"""
import argparse
import datetime
import hashlib
import hmac
import json
import os
import secrets
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path[:0] = [RACINE, ICI]

ENTETE_SIGNATURE = 'X-Signature'
ENTETE_HORODATAGE = 'X-Horodatage'
LIMITE_DEFAUT, LIMITE_MAX = 50, 500
COMPTES = {'analyste@exemple.invalid': dict(password='mot-de-passe-fictif', role='ANALYST', fullName='Analyste Fictif')}
FORMAT = '%Y-%m-%dT%H:%M:%S.000Z'
DEBUT = datetime.datetime(2026, 1, 1)


def _erreur(code, statut):
    return JSONResponse({'error': code}, status_code=statut, headers={'Cache-Control': 'no-store'})


class Horloge:
    """Instant courant du serveur ; chaque avancée publie les événements franchis."""

    def __init__(self, a_chaque_reglage):
        self.maintenant = DEBUT
        self._publier = a_chaque_reglage

    def regler(self, instant):
        self.maintenant = instant
        self._publier()

    def avancer(self, **duree):
        self.regler(self.maintenant + datetime.timedelta(**duree))


def creer_application(jeu, secret, notifier=None, comptes=None):
    """`notifier(corps: bytes, entetes: dict)` reçoit chaque notification ; None : aucune notification."""
    comptes = comptes or COMPTES
    appli = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    evenements = [(datetime.datetime.strptime(e['instant'], FORMAT), e) for e in jeu.chronologie]
    jetons = {}
    etat = dict(publies=0, visibles={})           # visibles : ref → dernière version dont l'instant est passé

    def publier():
        maintenant = appli.state.horloge.maintenant
        etat['visibles'] = {}
        franchis = 0
        for instant, e in evenements:
            if instant > maintenant:
                break
            etat['visibles'][e['ref']] = e
            franchis += 1
        if notifier:
            for instant, e in evenements[etat['publies']:franchis]:
                d = e['dossier']
                corps = json.dumps(dict(ref=d['ref'], updatedAt=d['updatedAt'], analysisStatus=d['analysisStatus'],
                                        trigger='INITIAL' if e['version'] == 1 else 'REANALYSIS'),
                                   separators=(',', ':')).encode()
                notifier(corps, {ENTETE_SIGNATURE: hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest(),
                                 ENTETE_HORODATAGE: instant.strftime(FORMAT), 'Content-Type': 'application/json'})
        etat['publies'] = max(etat['publies'], franchis)

    appli.state.horloge = Horloge(publier)
    cles_liste = list(jeu.liste['items'][0]) if jeu.liste['items'] else []

    def connecte(requete):
        entete = requete.headers.get('authorization', '')
        return entete.startswith('Bearer ') and entete[7:] in jetons

    @appli.post('/api/auth/login')
    async def connexion(requete: Request):
        try:
            corps = await requete.json()
        except ValueError:
            return _erreur('unauthorized', 401)
        courriel = corps.get('email') if isinstance(corps, dict) else None
        mot_de_passe = corps.get('password') if isinstance(corps, dict) else None
        compte = comptes.get(courriel) if isinstance(courriel, str) else None
        if not compte or not isinstance(mot_de_passe, str) or not hmac.compare_digest(
                mot_de_passe.encode(), compte['password'].encode()):
            return _erreur('unauthorized', 401)
        jeton = secrets.token_urlsafe(32)
        jetons[jeton] = compte['role']
        return {'token': jeton, 'role': compte['role'], 'fullName': compte['fullName']}

    def entier(valeur, defaut, mini, maxi):
        if valeur is None:
            return defaut
        n = int(valeur)                                   # ValueError si ce n'est pas un entier
        if not mini <= n <= maxi:
            raise ValueError
        return n

    @appli.get('/api/dossiers')
    def liste(requete: Request):
        if not connecte(requete):
            return _erreur('unauthorized', 401)
        q = requete.query_params
        try:
            limite = entier(q.get('limit'), LIMITE_DEFAUT, 1, LIMITE_MAX)
            decalage = entier(q.get('offset'), 0, 0, 10 ** 9)
            for cle, permis in (('status', modeles_v2_valeurs('DossierStatus')), ('verdict', modeles_v2_valeurs('Verdict')),
                                ('category', modeles_v2_valeurs('RiskCategory'))):
                if q.get(cle) is not None and q[cle] not in permis:
                    raise ValueError
            for cle in ('from', 'to'):
                if q.get(cle) is not None:
                    datetime.date.fromisoformat(q[cle])
        except ValueError:
            return _erreur('parametre_invalide', 400)
        archives = q.get('archives') == 'true'
        dossiers = [e['dossier'] for e in etat['visibles'].values() if archives or jeu.meta[e['ref']]['actif']]
        for cle, champ in (('status', 'analysisStatus'), ('verdict', 'verdict'), ('category', 'category')):
            if q.get(cle) is not None:
                dossiers = [d for d in dossiers if d[champ] == q[cle]]
        if q.get('search'):
            cherche = q['search'].casefold()
            dossiers = [d for d in dossiers if cherche in d['ref'].casefold()
                        or cherche in (d['clientName'] or '').casefold()]
        if q.get('from'):
            dossiers = [d for d in dossiers if d['createdAt'][:10] >= q['from']]
        if q.get('to'):
            dossiers = [d for d in dossiers if d['createdAt'][:10] <= q['to']]
        dossiers.sort(key=lambda d: (d['createdAt'], d['ref']), reverse=True)

        def compter(champ):
            comptes_ = {}
            for d in dossiers:
                if d[champ] is not None:
                    comptes_[d[champ]] = comptes_.get(d[champ], 0) + 1
            return comptes_
        return JSONResponse(dict(
            items=[{c: d[c] for c in cles_liste} for d in dossiers[decalage:decalage + limite]], total=len(dossiers),
            counts=dict(verdict=compter('verdict'), status=compter('analysisStatus'), category=compter('category'))),
            headers={'Cache-Control': 'no-store'})

    @appli.get('/api/dossiers/{ref}')
    def detail(ref: str, requete: Request):
        if not connecte(requete):
            return _erreur('unauthorized', 401)
        e = etat['visibles'].get(ref)
        if e is None:
            return _erreur('dossier_inconnu', 404)
        return JSONResponse(e['dossier'], headers={'Cache-Control': 'no-store'})

    @appli.get('/api/dossiers/{ref}/controls/{control_id}')
    def controle(ref: str, control_id: str, requete: Request):
        if not connecte(requete):
            return _erreur('unauthorized', 401)
        e = etat['visibles'].get(ref)
        if e is None:
            return _erreur('dossier_inconnu', 404)
        analyse = e['dossier']['latestAnalysis'] or {'controls': []}
        for c in analyse['controls']:
            if c['controlId'] == control_id:
                return JSONResponse(dict(c, sourcePrincipale='pièces du dossier'), headers={'Cache-Control': 'no-store'})
        return _erreur('controle_inconnu', 404)

    return appli


def modeles_v2_valeurs(nom):
    """Valeurs d'une énumération de Kamal, lues dans les modèles générés depuis ses types."""
    from typing import get_args

    from pipeline import modeles_v2
    return get_args(getattr(modeles_v2, nom))


def adresse_locale(adresse):
    """Vrai si l'adresse désigne cette machine : http, hôte 127.0.0.1 ou localhost, sans partie « utilisateur@ »."""
    import urllib.parse
    try:
        u = urllib.parse.urlsplit(adresse)
        u.port                                              # ValueError si le port est illisible
    except ValueError:
        return False
    return u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost') and u.username is None \
        and u.password is None


def _notifier_par_http(adresse):
    """Envoi de la notification vers cette machine seulement : ni mandataire, ni redirection suivie."""
    import urllib.request
    if not adresse_locale(adresse):
        raise ValueError('la notification ne part que vers cette machine')

    class SansRedirection(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection)

    def envoyer(corps, entetes):
        requete = urllib.request.Request(adresse, data=corps, headers=entetes, method='POST')
        try:
            ouvreur.open(requete, timeout=5).close()
        except OSError as e:
            print(f'notification non remise ({type(e).__name__})', file=sys.stderr)
    return envoyer


def main(argv=None):
    import generer_dossiers
    import uvicorn
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--port', type=int, default=8720)
    ap.add_argument('--dossiers', type=int, default=1000)
    ap.add_argument('--societes', type=int, default=400)
    ap.add_argument('--graine', type=int, default=generer_dossiers.GRAINE)
    ap.add_argument('--notifier', help='adresse locale de POST /api/flux/v2 (127.0.0.1 ou localhost seulement)')
    a = ap.parse_args(argv)
    if a.notifier and not adresse_locale(a.notifier):
        print('arrêt : la notification ne part que vers cette machine', file=sys.stderr)
        return 2
    jeu = generer_dossiers.generer(a.dossiers, a.societes, a.graine)
    secret = os.environ.get('V2_FICTIVE_SECRET', 'secret-fictif-de-notification')
    appli = creer_application(jeu, secret, _notifier_par_http(a.notifier) if a.notifier else None)
    appli.state.horloge.regler(datetime.datetime(2027, 1, 1))
    print(f'serveur v2 fictif : {len(jeu.dossiers)} dossiers, port {a.port}')
    uvicorn.run(appli, host='127.0.0.1', port=a.port, log_level='warning')
    return 0


if __name__ == '__main__':
    sys.exit(main())
