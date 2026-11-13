#!/usr/bin/env python3
"""Collecteur en scrutation : va chercher dans la v2 chaque version de chaque dossier (étape D.4).

Un passage : connexion du compte de service (`POST /api/auth/login`), lecture de la liste
(`GET /api/dossiers?limit=200&offset=…`, avec et sans `archives=true` pour savoir quels dossiers sont écartés),
comparaison de `updatedAt` à ce qui est déjà reçu, puis `GET /api/dossiers/:ref` pour les seuls dossiers changés.
Chaque version reçue est gardée telle quelle et projetée dans le miroir (`pipeline/couches/c0_brut.py`).

- Liste triée par mise à jour décroissante : la lecture s'arrête dès qu'une page ne contient plus rien de nouveau.
  Sinon : relecture complète, au plus toutes les 5 minutes.
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
        except Exception as e:                           # panne de réseau, quelle que soit la bibliothèque
            raise ErreurV2('reseau') from e
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

    def _liste(self, archives, connus, triee_connue):
        """Éléments de la liste (ref, updatedAt), et si la première page est triée par mise à jour décroissante."""
        vus, decalage, triee = {}, 0, None
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
            except (ValueError, KeyError, TypeError):
                raise ErreurV2('liste_illisible') from None
            if triee is None:
                dates = [u for _, u in items]
                triee = dates == sorted(dates, reverse=True)
            vus.update(items)
            decalage += len(items)
            rien_de_neuf = all(connus.get(ref) == u for ref, u in items)
            if not items or decalage >= total or (triee and triee_connue and rien_de_neuf):
                return vus, triee

    # -- un passage --
    def passer(self):
        cx, maintenant = self.cx, self.horloge()
        bilan = dict(versions_nouvelles=0, dossiers=0, hors_modele=0, miroir_refuse=0, echecs_detail=0)
        prochaine, derniere_complete, triee_connue = cx.execute(
            'SELECT c.prochaine_scrutation, c.derniere_lecture_complete, s.liste_triee FROM flux_curseur c '
            'JOIN flux_source s ON s.nom = c.source WHERE c.source = ?', (self.source,)).fetchone()
        if prochaine and maintenant < _lire(prochaine):
            return dict(bilan, saute='trop tôt')
        try:
            derniere_complete = _lire(derniere_complete)
            if triee_connue == 0 and derniere_complete and \
                    (maintenant - derniere_complete).total_seconds() < RELECTURE_COMPLETE_S:
                bilan['liste'] = 'attente'               # liste non triée : relecture complète toutes les 5 min
            else:
                self._annoncer(maintenant, bool(triee_connue))
            passage = c0_brut.ouvrir_passage(cx, self.source, 'scrutation', _iso(maintenant))
            self._chercher(passage, maintenant, bilan)
            c0_brut.fermer_passage(cx, passage, bilan['dossiers'], bilan['versions_nouvelles'], _iso(maintenant))
        except ErreurV2 as e:
            cx.rollback()
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

    def _annoncer(self, maintenant, triee_connue):
        """Lit la liste et met en file les versions nouvelles ; note les dossiers écartés ou réactivés."""
        cx = self.cx
        connus = dict(cx.execute('SELECT ref, max(updated_at) FROM c0_dossier_brut GROUP BY ref').fetchall())
        actifs, triee = self._liste(False, connus, triee_connue)
        tous, _ = self._liste(True, connus, triee_connue)
        complete = not (triee and triee_connue)
        for ref, mise_a_jour in tous.items():
            actif = ref in actifs
            if connus.get(ref) != mise_a_jour:
                file.annoncer(cx, self.source, ref, mise_a_jour, actif, maintenant)
            elif complete:                               # même version : seul l'état « écarté » a pu changer
                ancien = cx.execute('SELECT actif FROM c0_dossier_brut WHERE ref = ? AND updated_at = ?',
                                    (ref, mise_a_jour)).fetchone()
                if ancien and bool(ancien[0]) != actif:
                    cx.execute('UPDATE c0_dossier_brut SET actif = ? WHERE ref = ? AND updated_at = ?',
                               (int(actif), ref, mise_a_jour))
                    c0_brut.projeter(cx, ref)
        dernier = max(tous.values(), default=None)
        cx.execute('UPDATE flux_source SET liste_triee = ? WHERE nom = ?', (int(triee), self.source))
        cx.execute('UPDATE flux_curseur SET dernier_updated_at = coalesce(max(coalesce(dernier_updated_at, ?), ?), '
                   'dernier_updated_at) WHERE source = ?', (dernier, dernier, self.source))
        if complete:
            cx.execute('UPDATE flux_curseur SET derniere_lecture_complete = ? WHERE source = ?',
                       (_iso(maintenant), self.source))
        cx.commit()

    def _chercher(self, passage, maintenant, bilan):
        """Va chercher le détail de chaque travail à faire ; un détail en échec n'arrête pas les autres."""
        cx = self.cx
        for travail, ref, actif in file.a_prendre(cx, self.source, maintenant):
            debut = time.monotonic()
            try:
                r = self._get('/api/dossiers/' + ref)
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
        except c0_brut.MiroirRefuse:
            nouvelle, code = True, 'miroir_refuse'       # la version brute est gardée ; le miroir attend
            bilan['miroir_refuse'] += 1
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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    cx = sqlite3.connect(a.base)
    cx.execute('PRAGMA journal_mode = WAL')
    cx.execute('PRAGMA foreign_keys = ON')
    migrer.appliquer(cx)
    with httpx.Client(base_url=os.environ['CARTE_V2_URL'], timeout=30) as client:
        collecteur = Collecteur(cx, client, os.environ['CARTE_V2_COMPTE'], os.environ['CARTE_V2_SECRET'],
                                adresse=os.environ['CARTE_V2_URL'])
        while True:
            collecteur.passer()
            if a.une_fois:
                return 0
            time.sleep(collecteur.intervalle_s)


if __name__ == '__main__':
    sys.exit(main())
