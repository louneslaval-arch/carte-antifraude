#!/usr/bin/env python3
"""Générateur de données entièrement fictives, à l'échelle, au format d'entrée du pipeline.

Produit dans le dossier de sortie :
  liste_noire.csv      même colonnes que la liste noire EQDOM (lu par --liste-noire)
  rc_annonces.csv      modèle générique d'export (lu par --rc-annonces)
  rc_personnes.csv     modèle générique d'export (lu par --rc-personnes)
  verite.json          ce que le générateur a caché exprès : quel inscrit doit être retrouvé, par quelle règle

Marques du fictif, vérifiables par l'interface avant d'ouvrir une publication :
  - tous les CIN commencent par « ZZ » (aucune préfecture n'émet ce préfixe) ;
  - toutes les adresses de lien sont sur le domaine réservé « exemple.invalid » ;
  - toutes les inscriptions portent la note « Exemple fictif ».
Les noms sont fabriqués à partir de syllabes ; une ressemblance avec une personne existante serait fortuite.

Usage :
  python3 jeu_essai/generer.py --echelle moyen --sortie jeu_essai/sortie/generees
  python3 jeu_essai/generer.py --societes 300000 --sortie ...      (taille du registre réel)
"""

import argparse
import csv
import json
import os
import random
import sys
from datetime import date, timedelta

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, '..', 'pipeline'))
from construire_base import COLONNES_BL, VILLES  # noqa: E402  (référentiels du pipeline, pour rester cohérent)

ECHELLES = {'petit': 400, 'moyen': 8_000, 'grand': 60_000}
DOMAINE = 'https://exemple.invalid/annonce/'

# ---- noms : chaque morceau existe en écriture latine et arabe, pour que les deux graphies concordent ----------
CONSONNES = [('B', 'ب'), ('T', 'ت'), ('D', 'د'), ('R', 'ر'), ('Z', 'ز'), ('S', 'س'), ('CH', 'ش'), ('K', 'ك'),
             ('L', 'ل'), ('M', 'م'), ('N', 'ن'), ('H', 'ح'), ('F', 'ف'), ('J', 'ج'), ('Q', 'ق'), ('GH', 'غ'),
             ('KH', 'خ')]
VOYELLES = [('A', 'ا'), ('I', 'ي'), ('OU', 'و')]       # toujours longues : même squelette dans les deux écritures
PRENOMS = [('MOHAMED', 'محمد'), ('AHMED', 'أحمد'), ('KARIM', 'كريم'), ('YOUSSEF', 'يوسف'), ('MEHDI', 'مهدي'),
           ('SAMIR', 'سمير'), ('RACHID', 'رشيد'), ('HASSAN', 'حسن'), ('OMAR', 'عمر'), ('KHALID', 'خالد'),
           ('ADIL', 'عادل'), ('HAMZA', 'حمزة'), ('IMAD', 'عماد'), ('NABIL', 'نبيل'), ('TARIK', 'طارق'),
           ('JAMAL', 'جمال'), ('AZIZ', 'عزيز'), ('SAID', 'سعيد'), ('MUSTAPHA', 'مصطفى'), ('ANAS', 'أنس'),
           ('NADIA', 'نادية'), ('FATIMA', 'فاطمة'), ('KHADIJA', 'خديجة'), ('SAMIRA', 'سميرة'), ('LAILA', 'ليلى'),
           ('SALMA', 'سلمى'), ('HIND', 'هند'), ('ASMAA', 'أسماء'), ('MARIAM', 'مريم'), ('SOUAD', 'سعاد'),
           ('NAJAT', 'نجاة'), ('ZINEB', 'زينب'), ('HAJAR', 'هاجر'), ('IMANE', 'إيمان'), ('LATIFA', 'لطيفة')]
# Activité en latin et telle qu'une annonce arabe la translittère (comme « أطلس نيكوس » pour « ATLAS NEGOCE »)
ACTIVITES_AR = {'NEGOCE': 'نيكوس', 'TRANS': 'ترانس', 'IMMOBILIER': 'إموبيليي', 'DISTRIBUTION': 'ديستريبوسيون',
                'TEXTILE': 'تكستيل', 'AGRI': 'أكري', 'TRAVAUX': 'ترافو', 'COMMERCE': 'كومرس',
                'INDUSTRIE': 'أندوستري', 'LOGISTIQUE': 'لوجيستيك', 'EQUIPEMENT': 'إكيبمون', 'PROMOTION': 'بروموسيون'}
ACTIVITES = list(ACTIVITES_AR)
FORMES = [('SARL', 'ش.م.م'), ('SARL AU', 'ش.م.م ذات الشريك الوحيد'), ('SA', 'ش.م')]
ROLES_LAT = {'gerant': 'gerant', 'associe': 'associe', 'gerant_sortant': 'ancien gerant',
             'cedant': 'cedant', 'cessionnaire': 'cessionnaire', 'liquidateur': 'liquidateur'}
ROLES_AR = {'gerant': 'المسير', 'associe': 'شريك', 'gerant_sortant': 'المسير', 'cedant': 'المفوت',
            'cessionnaire': 'المفوت له', 'liquidateur': 'المصفي'}
SOURCES = [('jalmaroc', 'lat'), ('aumaroc', 'lat'), ('flasheconomie', 'lat'), ('bo', 'ar'), ('umaroc', 'ar')]
MOTIFS = ['Falsification', 'Usurpation', 'Impayés', 'Faux documents', 'Fraude à l\'identité', '']
LISTES = ['INDESIRABLE', 'BLACKLIST', 'INDESIRABLE RISQ']
ORIGINES = ['', 'APSF', 'DGSN', 'AGENCE']
# Poids des villes : quelques grandes villes concentrent l'activité, comme dans le registre
VILLES_UTILES = [(code, lat, ar) for code, lat, ar, _ in VILLES[:14]]
POIDS_VILLES = [30, 10, 10, 8, 6, 6, 4, 4, 4, 2, 2, 2, 2, 1]


class Generateur:
    def __init__(self, n_societes, graine):
        self.r = random.Random(graine)
        self.n_soc = n_societes
        self.cins_pris = set()
        self.noms_pris = set()
        # Réserve de noms de famille, tirée selon une loi de Zipf : quelques noms très courants (homonymies), beaucoup
        # de noms rares (ceux-là seuls relient deux sociétés)
        self.familles = [self._nom_famille() for _ in range(max(300, n_societes // 4))]
        self.zipf = [1 / (k + 1) ** 0.9 for k in range(len(self.familles))]
        self.personnes = []          # dict(id, prenom, nom, ville, cin, societes)
        self.par_ville = {code: [] for code, *_ in VILLES_UTILES}
        self.societes = []           # dict(id, nom, nom_ar, ville, rc, personnes=[(pid, role, parts)])
        self.annonces, self.lignes_pers = [], []
        self.verite = []

    # -- briques -----------------------------------------------------------------------------------------------
    def _syllabe(self):
        c, ca = self.r.choice(CONSONNES)
        v, va = self.r.choice(VOYELLES)
        return c + v, ca + va

    def _nom_famille(self):
        while True:
            morceaux = [self._syllabe() for _ in range(self.r.choice((2, 2, 3)))]
            c, ca = self.r.choice(CONSONNES)
            lat, ar = ''.join(m[0] for m in morceaux) + c, ''.join(m[1] for m in morceaux) + ca
            if self.r.random() < 0.25:
                lat, ar = lat + 'I', ar + 'ي'                         # nisba
            if self.r.random() < 0.2:
                lat, ar = 'EL ' + lat, 'ال' + ar
            if lat not in self.noms_pris:
                self.noms_pris.add(lat)
                return lat, ar

    def _cin(self):
        while True:
            c = 'ZZ%06d' % self.r.randrange(1, 1_000_000)
            if c not in self.cins_pris:
                self.cins_pris.add(c)
                return c

    def _ville(self):
        return self.r.choices(VILLES_UTILES, POIDS_VILLES)[0]

    def _date(self, debut=2022, fin=2026):
        d0 = date(debut, 1, 1)
        return d0 + timedelta(days=self.r.randrange((date(fin, 10, 1) - d0).days))

    def nouvelle_personne(self, ville):
        nom = self.r.choices(self.familles, self.zipf)[0]
        p = dict(id=len(self.personnes), prenom=self.r.choice(PRENOMS), nom=nom, ville=ville, cin=None,
                 societes=[], naissance=self._date(1950, 2000))
        if self.r.random() < 0.01:                                    # rares CIN publiés dans les annonces
            p['cin'] = self._cin()
        self.personnes.append(p)
        self.par_ville[ville[0]].append(p['id'])
        return p

    def personne_pour(self, ville, sauf=()):
        """Une personne de la ville : souvent nouvelle, parfois déjà dirigeante ailleurs (crée les ponts)."""
        candidats = self.par_ville[ville[0]]
        if candidats and self.r.random() < 0.3:
            for _ in range(4):
                p = self.personnes[self.r.choice(candidats)]
                if len(p['societes']) < 4 and p['id'] not in sauf:
                    return p
        return self.nouvelle_personne(ville)

    # -- registre ----------------------------------------------------------------------------------------------
    def registre(self):
        rc_par_ville = {code: self.r.randrange(20_000, 90_000) for code, *_ in VILLES_UTILES}
        for k in range(self.n_soc):
            ville = self._ville()
            s1, s2 = self._syllabe(), self._syllabe()
            mot, mot_ar = s1[0] + s2[0], s1[1] + s2[1]
            forme, forme_ar = self.r.choice(FORMES)
            act = self.r.choice(ACTIVITES)
            rc_par_ville[ville[0]] += self.r.choice((1, 1, 2, 7, 31))
            s = dict(id=k, nom=f'{mot} {act} {forme}', nom_ar=f'شركة {mot_ar} {ACTIVITES_AR[act]} {forme_ar}', ville=ville,
                     rc=str(rc_par_ville[ville[0]]), personnes=[], creation=self._date(2022, 2025))
            g = self.personne_pour(ville)
            s['personnes'].append((g['id'], 'gerant', None))
            ids = {g['id']}
            for _ in range(self.r.choice((0, 1, 1, 2, 3))):
                a = self.personne_pour(ville, sauf=ids)
                ids.add(a['id'])
                s['personnes'].append((a['id'], 'associe', self.r.choice((100, 250, 500, 1000))))
            if self.r.random() < 0.3:
                s['personnes'].append((g['id'], 'associe', 500))      # gérant associé
            for pid in ids:
                self.personnes[pid]['societes'].append(k)
            self.societes.append(s)

    def _entete_annonce(self, s, ecr):
        """Dénomination, RC, tribunal et siège tels qu'une annonce en latin ou en arabe les écrit."""
        _code, ville_lat, ville_ar = s['ville']
        if ecr == 'ar':
            rc = s['rc'].translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')) if self.r.random() < 0.5 else s['rc']
            return (s['nom_ar'], rc, f'المحكمة التجارية ب{ville_ar}',
                    f'زنقة المثال رقم {self.r.randrange(1, 99)} {ville_ar}')
        siege = f'{self.r.randrange(1, 99)} RUE EXEMPLE {ville_lat.upper()}'
        return s['nom'], s['rc'], self.r.choice((f'Tribunal de commerce de {ville_lat}', ville_lat)), siege

    def _ligne_personne(self, aid, pid, role, parts, ecr):
        p = self.personnes[pid]
        prenom, nom = p['prenom'], p['nom']
        if ecr == 'ar':
            nom_complet, role_txt = f'{prenom[1]} {nom[1]}', ROLES_AR[role]
        else:
            nom_complet = self.r.choice((f'{prenom[0].title()} {nom[0]}', f'M. {nom[0]} {prenom[0].title()}'))
            role_txt = ROLES_LAT[role]
        return dict(annonce_id=aid, role=role_txt, nom_complet=nom_complet, nom='', prenom='',
                    cin=p['cin'] or '', parts=parts or '', date_naissance='', nationalite='', adresse='')

    def _annoncer(self, s, type_acte, quand, personnes):
        source, ecr = self.r.choice(SOURCES)
        ecr = s.get('ecriture') or ecr
        aid = 'FX-%07d' % (len(self.annonces) + 1)
        denom, rc, tribunal, siege = self._entete_annonce(s, ecr)
        self.annonces.append(dict(
            annonce_id=aid, source=source, type_acte=type_acte, date_publication=quand.isoformat(),
            numero_publication='', denomination=denom, rc=rc, tribunal=tribunal, depot='',
            date_acte=(quand - timedelta(days=self.r.randrange(5, 40))).isoformat(),
            capital=self.r.choice(('10000', '100000', '')) if type_acte == 'Création' else '',
            siege=siege if type_acte in ('Création', 'Transfert de siège') else '', objet=act_de(s['nom']),
            nouveau_capital='', nouveau_siege='', nouvelle_denomination='', complet='1', ice='',
            url=DOMAINE + aid, cin=''))
        self.lignes_pers += [self._ligne_personne(aid, pid, role, parts, ecr) for pid, role, parts in personnes]
        return aid

    def annonces_registre(self):
        for s in self.societes:
            self._annoncer(s, 'Création', s['creation'], s['personnes'])
            jour = s['creation']
            for _ in range(self.r.choice((0, 0, 0, 1, 1, 2))):
                jour = jour + timedelta(days=self.r.randrange(60, 500))
                if jour > date(2026, 10, 20):
                    break
                evt = self.r.choice(('gerant', 'cession', 'siege', 'dissolution'))
                ancien = s['personnes'][0][0]
                if evt == 'gerant':
                    nouveau = self.personne_pour(s['ville'], sauf={ancien})
                    nouveau['societes'].append(s['id'])
                    s['personnes'].insert(0, (nouveau['id'], 'gerant', None))
                    self._annoncer(s, 'Changement de gérant', jour,
                                         [(ancien, 'gerant_sortant', None), (nouveau['id'], 'gerant', None)])
                elif evt == 'cession':
                    cess = self.personne_pour(s['ville'], sauf={ancien})
                    cess['societes'].append(s['id'])
                    self._annoncer(s, 'Cession de parts', jour,
                                         [(ancien, 'cedant', 500), (cess['id'], 'cessionnaire', 500)])
                elif evt == 'siege':
                    self._annoncer(s, 'Transfert de siège', jour, [])
                else:
                    self._annoncer(s, 'Dissolution', jour, [(ancien, 'liquidateur', None)])
                    break

    # -- liste noire -------------------------------------------------------------------------------------------
    def _inscription(self, **valeurs):
        """Ajoute une ligne de liste noire ; les champs non donnés sont tirés ou laissés vides."""
        self.num_seq += 1
        ligne = {c: '' for c in COLONNES_BL}
        ligne.update(num_seq=self.num_seq, note='Exemple fictif', type_liste=self.r.choice(LISTES),
                     motif2=self.r.choice(MOTIFS), orig_liste=self.r.choice(ORIGINES),
                     dat_sais=self._date(2018, 2026).isoformat())
        ligne.update(valeurs)
        self.bl.append(ligne)
        return ligne

    def _champs_societe(self, s, regle):
        """Ce que la liste noire saisit d'une société pour qu'elle soit retrouvée par `regle`."""
        code, ville_lat, _ = s['ville']
        if regle == 'R02':
            return dict(regist_com=s['rc'], regist_tribune=self.r.choice((code[:5], ville_lat.upper())))
        if regle == 'R03':
            return dict(regist_com='RC' + s['rc'])
        if regle == 'R04':
            return dict(ville=ville_lat.upper())
        return dict(regist_com=str(self.r.randrange(900_000, 999_999)))      # société absente du registre

    def _inscrire_societes(self, n_pm):
        for s in self.r.sample(self.societes, min(n_pm, len(self.societes))):
            regle = self.r.choices(['R02', 'R03', 'R04', 'absent'], [40, 20, 15, 25])[0]
            v = self._champs_societe(s, regle)
            nom_ras = s['nom'] if regle != 'absent' else f'{self._syllabe()[0]}{self._syllabe()[0]} SERVICES SARL'
            self._inscription(cli_phy_mor='PM', nom_ras=nom_ras, **v)
            self.verite.append(dict(type='PM', societe=s['id'] if regle != 'absent' else None, regle=regle))

    def _champs_personne(self, p, regle, cin):
        """Ce que la liste noire saisit d'une personne pour qu'elle soit retrouvée par `regle`."""
        code, ville_lat, _ = p['ville']
        v = dict(cin=cin + ('X' if regle == 'R01v' else ''), nom=p['nom'][0], prenom=p['prenom'][0],
                 date_naiss=p['naissance'].isoformat() if self.r.random() < 0.5 else '')
        if regle == 'R07':
            v['ville'] = '2' if code == 'CASABLANCA' and self.r.random() < 0.5 else ville_lat.upper()
        if regle == 'R08':
            v['lib_emp'] = 'STE ' + self.societes[p['societes'][0]]['nom']
        return v

    def _inscrire_dirigeants(self, n):
        dirigeants = [p for p in self.personnes if p['societes']]
        choisies = self.r.sample(dirigeants, min(n, len(dirigeants)))
        for p in choisies:
            regle = self.r.choices(['R01', 'R01v', 'R07', 'R08', 'nom_seul'], [25, 5, 40, 15, 15])[0]
            cin = p['cin'] or self._cin()
            if regle in ('R01', 'R01v'):
                p['cin'] = cin                                       # publié dans les annonces (écrites ensuite)
            premiere = self._inscription(cli_phy_mor='PP', **self._champs_personne(p, regle, cin))
            if self.r.random() < 0.15:                               # seconde inscription, CIN saisi autrement
                copie = {c: x for c, x in premiere.items() if c != 'num_seq'}
                self._inscription(**{**copie, 'cin': cin[:2] + ' ' + cin[2:], 'type_liste': 'BLACKLIST',
                                     'orig_liste': 'DGSN'})
            self.verite.append(dict(type='PP', personne=p['id'], regle=regle))
        return len(choisies)

    def _inscrire_absents(self, n):
        """Inscrits qu'aucune annonce ne cite."""
        for _ in range(n):
            nom, prenom = self.r.choices(self.familles, self.zipf)[0], self.r.choice(PRENOMS)
            ville = self._ville()
            self._inscription(cli_phy_mor='PP', cin=self._cin(), nom=nom[0], prenom=prenom[0], ville=ville[1].upper())
            self.verite.append(dict(type='PP', personne=None, regle='absent'))

    def _reseau_rc_consecutifs(self):
        """Trois sociétés inscrites aux RC consécutifs, gérées par la même personne, elle aussi inscrite."""
        ville = self._ville()
        g = self.nouvelle_personne(ville)
        g['cin'] = self._cin()
        base_rc = self.r.randrange(100_000, 800_000)
        for j in range(3):
            s = dict(id=len(self.societes), nom=f'{self._syllabe()[0]}{self._syllabe()[0]} {ACTIVITES[j]} SARL',
                     nom_ar=None, ville=ville, rc=str(base_rc + j), personnes=[(g['id'], 'gerant', None)],
                     creation=self._date(2023, 2026), ecriture='lat')     # nom sans graphie arabe
            s['nom_ar'] = 'شركة ' + s['nom']
            g['societes'].append(s['id'])
            self.societes.append(s)
            self._inscription(cli_phy_mor='PM', nom_ras=s['nom'], regist_com=s['rc'], regist_tribune=ville[0][:5])
        self._inscription(cli_phy_mor='PP', cin=g['cin'], nom=g['nom'][0], prenom=g['prenom'][0])
        self.verite.append(dict(type='reseau_rc_consecutifs', personne=g['id'], regle='R01+R02'))

    def _saisies_abimees(self):
        """Comme dans la vraie liste : type client dans la colonne tribunal, encodage cassé, CIN masqué."""
        self._inscription(cli_phy_mor='PP', regist_tribune='PP', nom='EXEMPLE', prenom='ANOMALIE',
                          motif2='IndÃ©sirable', lib_emp='7}%=%T30%; #M\\E[40M')
        self._inscription(cli_phy_mor='PP', cin='XXXXXXXX', nom='EXEMPLE', prenom='MASQUE', date_naiss='1890-01-01')

    def liste_noire(self):
        self.bl, self.num_seq = [], 100_000
        n_pp = max(40, int(self.n_soc * 0.03))
        self._inscrire_societes(max(15, int(self.n_soc * 0.01)))
        trouves = self._inscrire_dirigeants(int(n_pp * 0.7))
        self._inscrire_absents(n_pp - trouves)
        for _ in range(max(2, self.n_soc // 2000)):
            self._reseau_rc_consecutifs()
        self._saisies_abimees()
        return self.bl

    def tout(self):
        self.registre()
        bl = self.liste_noire()                 # avant les annonces : fixe les CIN qui doivent y être publiés
        self.annonces_registre()
        return bl


def act_de(nom):
    return next((a.title() for a in ACTIVITES if a in nom), '')


def ecrire_csv(chemin, lignes, colonnes):
    with open(chemin, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        w.writerows(lignes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--echelle', choices=list(ECHELLES), default='petit')
    ap.add_argument('--societes', type=int, help='Nombre de sociétés du registre (remplace --echelle)')
    ap.add_argument('--graine', type=int, default=20261109, help='Même graine, mêmes données')
    ap.add_argument('--sortie', required=True)
    a = ap.parse_args()
    g = Generateur(a.societes or ECHELLES[a.echelle], a.graine)
    bl = g.tout()
    os.makedirs(a.sortie, exist_ok=True)
    ecrire_csv(os.path.join(a.sortie, 'liste_noire.csv'), bl, COLONNES_BL)
    ecrire_csv(os.path.join(a.sortie, 'rc_annonces.csv'), g.annonces, list(g.annonces[0]))
    ecrire_csv(os.path.join(a.sortie, 'rc_personnes.csv'), g.lignes_pers, list(g.lignes_pers[0]))
    with open(os.path.join(a.sortie, 'verite.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(graine=a.graine, societes=len(g.societes), personnes=len(g.personnes), cas=g.verite),
                  f, ensure_ascii=False, indent=1)
    pp = sum(1 for l in bl if l['cli_phy_mor'] == 'PP')
    print(f'  registre : {len(g.societes)} sociétés, {len(g.personnes)} personnes, {len(g.annonces)} annonces, '
          f'{len(g.lignes_pers)} personnes citées')
    print(f'  liste noire : {len(bl)} inscriptions ({pp} lignes de personnes, {len(bl) - pp} de sociétés)')


if __name__ == '__main__':
    main()
