#!/usr/bin/env python3
"""Collecteur en scrutation : va chercher dans la v2 chaque version de chaque dossier (étape D.4).

Un passage : connexion du compte de service (`POST /api/auth/login`), lecture de la liste
(`GET /api/dossiers?limit=200&offset=…`, avec et sans `archives=true` pour savoir quels dossiers sont écartés),
comparaison de `updatedAt` à ce qui est déjà reçu, puis `GET /api/dossiers/:ref` pour les seuls dossiers changés.
Chaque version reçue est gardée telle quelle et projetée dans le miroir (`pipeline/couches/c0_brut.py`).

- Une relecture complète de la liste a lieu au moins toutes les 5 minutes : c'est elle qui garantit qu'aucun dossier
  modifié n'est manqué. Entre deux, si la liste est triée par mise à jour décroissante, la lecture s'arrête dès
  qu'une page ne contient plus rien de nouveau ; sinon, la liste n'est pas relue.
- Serveur injoignable : le passage échoue, le suivant est repoussé à intervalle croissant ; rien n'est perdu.
- Détail en échec : le travail reste dans la file et se retente plus tard ; les autres dossiers passent.
- Un champ que les types de Kamal ne connaissent pas est toléré : la version est gardée, et comptée « hors modèle ».
- Journaux : comptages et codes seulement, jamais une référence ni un contenu de dossier.

Réglages par variables d'environnement : `CARTE_V2_URL`, `CARTE_V2_COMPTE`, `CARTE_V2_SECRET` (aucun secret dans le
dépôt ni dans la base). Usage : python -m flux.collecteur --base CHEMIN [--une-fois]
"""
import argparse
import datetime
import logging
import os
import sqlite3
import sys
import time
import urllib.parse

import pydantic

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from flux import file  # noqa: E402
from pipeline import migrer, modeles_v2  # noqa: E402
from pipeline.couches import c0_brut  # noqa: E402

FORMAT = file.FORMAT
PAGE = 200
RELECTURE_COMPLETE_S = 300
journal = logging.getLogger('carte.flux')
logging.getLogger('httpx').setLevel(logging.WARNING)       # httpx journalise l'adresse complète, référence comprise


class ErreurV2(Exception):
    """Échec d'un appel à la v2 ; `code` ne contient jamais de valeur reçue."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def adresse_admise(adresse):
    """Vrai si l'adresse de la v2 est acceptable : https, ou http vers cette machine seulement ; jamais
    d'identifiants dans l'adresse (elle est écrite dans `flux_source`)."""
    try:
        u = urllib.parse.urlsplit(adresse)
        u.port
    except ValueError:
        return False
    if not u.hostname or u.username is not None or u.password is not None:
        return False
    return u.scheme == 'https' or (u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost'))


def _iso(t):
    return t.strftime(FORMAT)


def _lire(texte):
    return datetime.datetime.strptime(texte, FORMAT) if texte else None


class Collecteur:
    def __init__(self, cx, client, compte, secret, source='v2', adresse='', intervalle_s=60, horloge=None):
        self.cx, self.client, self.compte, self.secret, self.source = cx, client, compte, secret, source
        self.horloge = horloge or (lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
        self.jeton = None
        cx.execute('INSERT INTO flux_source (nom, adresse, intervalle_s) VALUES (?, ?, ?) ON CONFLICT (nom) DO NOTHING',
                   (source, adresse, intervalle_s))
        cx.execute('INSERT INTO flux_curseur (source) VALUES (?) ON CONFLICT (source) DO NOTHING', (source,))
        cx.commit()
        self.intervalle_s = cx.execute('SELECT intervalle_s FROM flux_source WHERE nom = ?', (source,)).fetchone()[0]

    # -- appels à la v2 --
    def _appel(self, methode, url, **k):
        try:
            r = getattr(self.client, methode)(url, **k)
        except Exception:                           # panne de réseau, quelle que soit la bibliothèque
            raise ErreurV2('reseau') from None           # l'exception d'origine porte l'adresse et le jeton
        if r.status_code >= 500:
            raise ErreurV2(f'http_{r.status_code}')
        return r

    def _connecter(self):
        r = self._appel('post', '/api/auth/login', json={'email': self.compte, 'password': self.secret})
        if r.status_code != 200:
            raise ErreurV2('connexion_refusee')
        try:
            self.jeton = r.json()['token']
        except (ValueError, KeyError, TypeError):
            raise ErreurV2('connexion_illisible') from None

    def _get(self, url, **params):
        for essai in (1, 2):
            if self.jeton is None:
                self._connecter()
            r = self._appel('get', url, params=params, headers={'Authorization': 'Bearer ' + self.jeton})
            if r.status_code != 401:
                return r
            self.jeton = None                            # jeton expiré : une nouvelle connexion, une seule
        raise ErreurV2('jeton_refuse')

    def _lire_liste(self, archives, connus, rapide):
        """Éléments (ref, updatedAt) de la liste, dans l'ordre reçu, et si la lecture est allée jusqu'au bout.
        En lecture rapide, elle s'arrête à la première page qui ne contient rien de nouveau."""
        vus, decalage = [], 0
        while True:
            params = dict(limit=PAGE, offset=decalage)
            if archives:
                params['archives'] = 'true'
            r = self._get('/api/dossiers', **params)
            if r.status_code != 200:
                raise ErreurV2(f'liste_http_{r.status_code}')
            try:
                corps = r.json()
                items = [(d['ref'], d['updatedAt']) for d in corps['items']]
                total = int(corps['total'])
                if not all(isinstance(ref, str) and isinstance(u, str) for ref, u in items):
                    raise TypeError
            except (ValueError, KeyError, TypeError):
                raise ErreurV2('liste_illisible') from None
            vus.extend(items)
            decalage += len(items)
            if not items or decalage >= total:
                return vus, True
            if rapide and all(connus.get(ref) == u for ref, u in items):
                return vus, False

    # -- un passage --
    def passer(self):
        cx, maintenant = self.cx, self.horloge()
        bilan = dict(versions_nouvelles=0, dossiers=0, hors_modele=0, miroir_refuse=0, echecs_detail=0)
        prochaine, derniere_complete, triee_connue = cx.execute(
            'SELECT c.prochaine_scrutation, c.derniere_lecture_complete, s.liste_triee FROM flux_curseur c '
            'JOIN flux_source s ON s.nom = c.source WHERE c.source = ?', (self.source,)).fetchone()
        if prochaine and maintenant < _lire(prochaine):
            return dict(bilan, saute='trop tôt')
        derniere_complete = _lire(derniere_complete)
        recente = derniere_complete is not None and \
            (maintenant - derniere_complete).total_seconds() < RELECTURE_COMPLETE_S
        passage = None
        try:
            if recente and not triee_connue:
                bilan['liste'] = 'attente'               # liste non triée : relecture complète toutes les 5 min
            else:
                self._annoncer(maintenant, rapide=recente)
            passage = c0_brut.ouvrir_passage(cx, self.source, 'scrutation', _iso(maintenant))
            self._chercher(passage, maintenant, bilan)
            c0_brut.fermer_passage(cx, passage, bilan['dossiers'], bilan['versions_nouvelles'], _iso(maintenant))
        except ErreurV2 as e:
            cx.rollback()
            if passage:                                  # ce qui a été reçu avant la panne reste compté
                c0_brut.fermer_passage(cx, passage, bilan['dossiers'], bilan['versions_nouvelles'], _iso(maintenant))
            echecs = cx.execute('SELECT echecs FROM flux_curseur WHERE source = ?', (self.source,)).fetchone()[0] + 1
            attente = file.delai(echecs, initial=self.intervalle_s)
            cx.execute('UPDATE flux_curseur SET echecs = ?, derniere_scrutation = ?, prochaine_scrutation = ? '
                       'WHERE source = ?',
                       (echecs, _iso(maintenant), _iso(maintenant + datetime.timedelta(seconds=attente)), self.source))
            cx.commit()
            journal.warning('passage en échec : code=%s échecs=%d prochaine tentative dans %d s', e.code, echecs, attente)
            return dict(bilan, echec=e.code)
        cx.execute('UPDATE flux_curseur SET echecs = 0, derniere_scrutation = ?, derniere_reussite = ?, '
                   'prochaine_scrutation = NULL WHERE source = ?', (_iso(maintenant), _iso(maintenant), self.source))
        cx.commit()
        journal.info('passage : %s', ' '.join(f'{k}={v}' for k, v in sorted(bilan.items())))
        return bilan

    def _annoncer(self, maintenant, rapide):
        """Lit la liste et met en file les versions nouvelles ; note les dossiers écartés ou réactivés.

        Une lecture complète a lieu au moins toutes les 5 minutes, que la liste soit triée ou non : c'est elle qui
        garantit qu'aucun dossier modifié n'est manqué, et elle seule décide si la liste est triée (sur toutes ses
        pages) et quels dossiers sont écartés. Entre deux, si la liste est triée par mise à jour décroissante, une
        lecture rapide s'arrête à la première page sans nouveauté ; au moindre doute, elle redevient complète.
        La liste avec archives est lue avant celle des actifs : un dossier créé entre les deux lectures n'est alors
        vu que comme actif, au passage suivant, et jamais pris pour un dossier écarté."""
        cx = self.cx
        connus = dict(cx.execute('SELECT ref, max(updated_at) FROM c0_dossier_brut GROUP BY ref').fetchall())

        def lire(rapide):
            tous, bout_tous = self._lire_liste(True, connus, rapide)
            actifs, bout_actifs = self._lire_liste(False, connus, rapide)
            dates = [u for _, u in tous]
            return tous, {ref for ref, _ in actifs}, bout_tous and bout_actifs, dates == sorted(dates, reverse=True)
        tous, actifs, complete, triee = lire(rapide)
        changes = {ref: u for ref, u in tous if connus.get(ref) != u}
        if not complete and (not triee or any(ref not in actifs for ref in changes)):
            tous, actifs, complete, triee = lire(False)  # doute sur le tri ou sur un dossier écarté : tout relire
            changes = {ref: u for ref, u in tous if connus.get(ref) != u}
        for ref, mise_a_jour in changes.items():
            file.annoncer(cx, self.source, ref, mise_a_jour, ref in actifs, maintenant)
        if complete:                                     # même version : seul l'état « écarté » a pu changer
            for ref, mise_a_jour in tous:
                if ref in changes:
                    continue
                ancien = cx.execute('SELECT actif FROM c0_dossier_brut WHERE ref = ? AND updated_at = ?',
                                    (ref, mise_a_jour)).fetchone()
                if ancien and bool(ancien[0]) != (ref in actifs):
                    cx.execute('UPDATE c0_dossier_brut SET actif = ? WHERE ref = ? AND updated_at = ?',
                               (int(ref in actifs), ref, mise_a_jour))
                    try:
                        c0_brut.projeter(cx, ref)
                    except Exception:                    # noqa: BLE001  le miroir refuse : la version reste brute
                        journal.warning('miroir refusé à la mise à jour de l\'état écarté')
            cx.execute('UPDATE flux_source SET liste_triee = ? WHERE nom = ?', (int(triee), self.source))
            cx.execute('UPDATE flux_curseur SET derniere_lecture_complete = ? WHERE source = ?',
                       (_iso(maintenant), self.source))
        elif not triee:
            cx.execute('UPDATE flux_source SET liste_triee = 0 WHERE nom = ?', (self.source,))
        ancien = cx.execute('SELECT dernier_updated_at FROM flux_curseur WHERE source = ?', (self.source,)).fetchone()[0]
        dernier = max([u for _, u in tous] + ([ancien] if ancien else []), default=None)
        cx.execute('UPDATE flux_curseur SET dernier_updated_at = ? WHERE source = ?', (dernier, self.source))
        cx.commit()

    def _chercher(self, passage, maintenant, bilan):
        """Va chercher le détail de chaque travail à faire ; un détail en échec n'arrête pas les autres."""
        cx = self.cx
        for travail, ref, actif in file.a_prendre(cx, self.source, maintenant):
            debut = time.monotonic()
            try:
                r = self._get('/api/dossiers/' + urllib.parse.quote(ref, safe=''))
            except ErreurV2 as e:
                if e.code == 'reseau':
                    raise                                # serveur injoignable : inutile d'insister sur les suivants
                file.echouer(cx, travail, e.code, maintenant)
                bilan['echecs_detail'] += 1
                cx.commit()
                continue
            duree = int((time.monotonic() - debut) * 1000)
            if r.status_code == 404:
                file.bloquer(cx, travail, 'dossier_inconnu')
            elif r.status_code != 200:
                file.echouer(cx, travail, f'http_{r.status_code}', maintenant)
                bilan['echecs_detail'] += 1
            else:
                self._recevoir(passage, travail, r, bool(actif), duree, maintenant, bilan)
            cx.commit()

    def _recevoir(self, passage, travail, reponse, actif, duree, maintenant, bilan):
        cx = self.cx
        try:
            detail = reponse.json()
        except ValueError:
            file.echouer(cx, travail, 'detail_illisible', maintenant)
            bilan['echecs_detail'] += 1
            return
        code = None
        try:
            modeles_v2.DossierDetail.model_validate(detail)
        except pydantic.ValidationError:
            bilan['hors_modele'] += 1                    # champ nouveau ou forme inattendue : gardé quand même
            code = 'hors_modele'
        try:
            nouvelle = c0_brut.recevoir(cx, passage, detail, actif=actif, maintenant=_iso(maintenant))
        except c0_brut.DossierIllisible:
            file.echouer(cx, travail, 'detail_illisible', maintenant)
            bilan['echecs_detail'] += 1
            return
        except c0_brut.MiroirRefuse:                     # la version brute est gardée ; le travail reste visible
            bilan['miroir_refuse'] += 1
            bilan['dossiers'] += 1
            file.bloquer(cx, travail, 'miroir_refuse')
            return
        bilan['dossiers'] += 1
        bilan['versions_nouvelles'] += int(nouvelle)
        file.reussir(cx, travail, c0_brut.empreinte(detail), duree, code)


def main(argv=None):
    import httpx
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', required=True)
    ap.add_argument('--une-fois', action='store_true')
    a = ap.parse_args(argv)
    manquantes = [v for v in ('CARTE_V2_URL', 'CARTE_V2_COMPTE', 'CARTE_V2_SECRET') if not os.environ.get(v)]
    if manquantes:
        print('arrêt : variables absentes : ' + ', '.join(manquantes), file=sys.stderr)
        return 2
    if not adresse_admise(os.environ['CARTE_V2_URL']):
        print('arrêt : CARTE_V2_URL doit être en https (ou http vers cette machine), sans identifiants', file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    cx = sqlite3.connect(a.base)
    cx.execute('PRAGMA journal_mode = WAL')
    cx.execute('PRAGMA foreign_keys = ON')
    migrer.appliquer(cx)
    # trust_env=False : ni mandataire ni fichier netrc de l'environnement ne s'intercale
    with httpx.Client(base_url=os.environ['CARTE_V2_URL'], timeout=30, trust_env=False) as client:
        collecteur = Collecteur(cx, client, os.environ['CARTE_V2_COMPTE'], os.environ['CARTE_V2_SECRET'],
                                adresse=os.environ['CARTE_V2_URL'])
        while True:
            collecteur.passer()
            if a.une_fois:
                return 0
            time.sleep(collecteur.intervalle_s)


if __name__ == '__main__':
    sys.exit(main())
