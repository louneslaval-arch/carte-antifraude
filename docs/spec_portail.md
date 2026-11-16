# Portail : la page d'accueil du front

SEVEN · réseaux de fraude EQDOM · 16/11/2026 · vision de Lounès, mise en forme pour l'étape K. **Aucun code tant que
l'étape K n'est pas lancée et que cette spécification n'est pas validée.** Règles qui s'appliquent : `CLAUDE.md`
(règles absolues), `.claude/rules/pages.md`, `docs/decisions.md`, `docs/questions_ouvertes.md` (n°11 et n°69 à 76).

## 1. Objet

Le portail est la page d'accueil du front : la **base client** au centre et, autour, des îlots qui flottent
doucement. D'un côté les **modules** branchés sur la base, de l'autre les **usages** possibles de cette base. Chaque
îlot mène à son module ou ouvre une fiche descriptive.

Seul le portail porte la mise en scène. Les écrans de travail (cartes, base client, fiche client, vue dossier)
gardent un style clair et sobre. Ce style devait être décrit dans `docs/spec_base_client.md`, **qui n'existe pas
dans le dépôt** : voir la question n°72.

## 2. Composition de la page

### 2.1 En-tête

- À gauche : le carré rouge marqué « E », puis « EQDOM » et « Plateforme clients ».
- À droite : l'interrupteur de langue, « Fr » et la lettre arabe aïn séparés par une barre, puis le rôle connecté.
  La lettre n'est pas écrite ici : la garde des données refuse l'écriture arabe dans un fichier du dépôt tant
  qu'elle n'est pas autorisée (question n°76).
- L'arabe peut rester inactif au début, mais l'interrupteur est visible (question n°73).
- L'en-tête garde la même marque sur tous les écrans.

### 2.2 Titre

- « Une base client, dix façons de s'en servir ».
- Une phrase d'introduction.
- Une légende de trois repères : module actif, module à venir, usage.

### 2.3 Scène

Environ 760 px de haut, 1 180 px de large au plus, centrée.

**Au centre, la tuile « Base client »**
- La plus grande, la seule pleine en rouge.
- Deux ou trois chiffres agrégés tirés de l'API : personnes, dossiers, mise à jour de la passe de nuit.
- Aucun nom ; aucun chiffre sous 5 (affiché « < 5 »).
- Un clic ouvre la vue « Base client » pour les rôles qui y ont droit ; sinon, un refus propre.

**Autour, cinq îlots de modules**, en pilules, reliés au centre par une courbe pleine.

| Module | État | Place | Au clic |
| --- | --- | --- | --- |
| Map antifraude | actif (point rouge) | à droite, en haut | ouvre la carte globale |
| Statistiques client | à venir | à fixer dans le fichier de contenu | ouvre son panneau |
| IA clients | à venir | à fixer | ouvre son panneau |
| Reco | source : son lien va vers le centre | à gauche, en haut | ouvre son panneau |
| À définir | place libre, en pointillé | à fixer | ouvre son panneau |

**Plus loin, dix bulles d'usages**, rondes, de tailles différentes, reliées au centre par une courbe en pointillé,
numérotées de 01 à 10 avec leur nom et une accroche.

| N° | Usage | Remarque |
| --- | --- | --- |
| 01 | Octroi | |
| 02 | Fraude | la bulle « en cours », mise en avant |
| 03 | Suivi du portefeuille | |
| 04 | Recouvrement | |
| 05 | Client et commercial | |
| 06 | Tarification | |
| 07 | Opérations | |
| 08 | Réglementaire | |
| 09 | IA générative | usage futur : voir § 5 |
| 10 | Données externes | |

Les positions sont données en pourcentage de la scène, dans le fichier de contenu, pour que les îlots ne se
chevauchent jamais. Un test vérifie qu'aucune bulle ne recouvre un module ni la tuile centrale.

### 2.4 Panneau de détail

Il s'ouvre au clic sur un îlot et contient :
- le nom et l'accroche ;
- un encadré de contexte ;
- la liste des usages, chacun marqué « en cours » ou « déjà dans la base » quand c'est vrai ;
- les données nécessaires et leurs sources.

Il se ferme par Échap, par un clic en dehors ou par le bouton de fermeture ; le focus revient sur l'îlot.

### 2.5 Bas de page : « Les quatre préalables »

Quatre cartes numérotées :
1. Historique de remboursement
2. Identité unique (le cœur de la base en construction)
3. Dictionnaire d'indicateurs
4. Cadre CNDP et gouvernance

## 3. Mouvement et lumière

- **Flottement.** Quelques pixels d'amplitude, 6 à 10 s par cycle, avec un décalage propre à chaque îlot pour
  qu'ils ne bougent jamais en même temps. Par `transform` seulement.
- **Illumination.** Toutes les 1,5 à 2 s, un usage au hasard s'illumine : bordure rouge, et sa courbe s'anime vers
  le centre pendant environ 1,2 s. Une seule bulle à la fois. Le cycle s'arrête quand la souris survole la scène ou
  qu'un panneau est ouvert.
- **Tuile centrale.** Deux halos qui respirent lentement. Le module actif porte un petit point rouge.
- **Survol ou focus clavier.** L'îlot grossit de 5 % et sa courbe passe en rouge.
- **`prefers-reduced-motion`.** Aucun flottement, aucune illumination automatique ; l'état au survol reste intact.
- **Onglet caché.** L'animation se met en pause (`visibilitychange`).

## 4. Charte

- **Fond** nuit `#060710` ; surfaces `#0E0F1A` et `#151726` ; filets blancs à 10 et 22 % d'opacité ; texte blanc,
  texte secondaire à 66 %.
- **Rouge EQDOM** `#EE3B45` (plus foncé `#C9262F`) pour la tuile centrale, le module actif, la bulle « Fraude » et
  les illuminations.
- **Police** système (`system-ui, -apple-system, "Segoe UI", sans-serif`), sauf décision de copier Montserrat
  (question n°71). Titres en graisse 800, resserrés.
- **Courbes** en SVG natif, calculées depuis les positions et recalculées au redimensionnement. Aucune bibliothèque.
- **Sous 900 px**, la scène devient une grille : tuile centrale en tête, puis modules, puis bulles, sans courbes ni
  flottement.
- **Passage aux écrans de travail** : on quitte la nuit pour le thème clair et sobre des écrans, et cela se voit.

**Point à trancher avant de coder (question n°74).** Le texte blanc sur `#EE3B45` a un contraste d'environ 3,9 pour
1 : sous le niveau AA pour un texte courant (4,5), suffisant seulement pour un grand texte (3). Sur `#C9262F`, il
est d'environ 5,4. Proposition : fond de la tuile centrale en `#C9262F` (ou dégradé qui reste au-dessus de 4,5 sous
le texte), `#EE3B45` réservé aux bordures, au point et aux illuminations.

## 5. Règles à tenir

- **Rien vers l'extérieur.** Aucune ressource externe ; politique « default-src 'self' » ; un essai vérifie
  qu'aucune requête ne sort de l'origine.
- **Aucune donnée personnelle sur le portail.** Seulement des chiffres agrégés, jamais sous 5.
- **Module « à venir ».** Il ouvre son panneau, jamais une route qui n'existe pas.
- **IA.** « IA générative » et « IA clients » décrivent un usage futur : aucun appel à un service, aucun texte
  généré. Leur panneau rappelle la gouvernance des modèles et le cadre CNDP.
- **Vocabulaire** (règle 5 de `CLAUDE.md`), accroches comprises : « inscrit », « lié à un inscrit » ; jamais
  « fraudeur » pour une personne liée.
- **Accessibilité.**
  - Chaque îlot est un bouton avec un nom accessible (« Fraude : le chantier en cours »).
  - L'ordre de tabulation suit : centre, modules, usages.
  - Le focus est visible ; les contrastes respectent le niveau AA.

## 6. Ce que le portail demande au reste du projet

| Besoin | Où | État aujourd'hui |
| --- | --- | --- |
| Chiffres agrégés de la tuile centrale (personnes, dossiers, date de la passe de nuit), avec « < 5 » | une route de l'API, ouverte aux rôles du portail | à écrire à l'étape J ; les comptages viennent de c2 et c3, la date de la passe de nuit de l'étape I |
| Vue « Base client » ouverte par la tuile centrale | étape K | **non spécifiée** : `docs/spec_base_client.md` manque (question n°72) |
| Droit « portail » par rôle | `api/app/roles.py`, table unique des droits | à ajouter à l'étape J (question n°69) |
| Fichier de contenu des îlots | `front/portail/contenu.json` | à créer à l'étape K (question n°70) ; la garde des données refuse aujourd'hui un `.json` hors de ses emplacements admis : à faire admettre par Lounès (question n°76) |
| Essais dans le navigateur | étape K | préalable déjà inscrit au plan : skill d'essai dans le navigateur contrôlé et installé |

Le portail ne change rien aux couches c0 à c6. Il renforce deux priorités déjà notées : finir l'identité unique
(étape F, partielle) et donner aux fiches un identifiant opaque et stable avant l'API (question n°54).

## 7. Tests (dans le navigateur, sur le jeu d'essai)

- Le portail s'affiche ; la tuile centrale montre les chiffres agrégés de l'API (« < 5 » si besoin).
- Un clic sur Map antifraude ouvre la carte ; sur la tuile centrale, la base client (ou un refus propre pour
  DIRECTION).
- Un clic sur une bulle ouvre son panneau ; Échap le referme et rend le focus.
- Aucun chevauchement à 1 280, 1 440 et 1 920 px de large ; grille propre à 375 px.
- Avec `prefers-reduced-motion` : aucune animation en cours.
- Aucune requête hors de l'origine ; aucune donnée personnelle dans le DOM du portail.

## 8. Fini quand

- Les tests sont verts.
- La garde des données est propre.
- Le journal est à jour.
- Des captures du portail à 1 440 px et à 375 px sont jointes au compte rendu.

## 9. Proposition de modification du plan (à valider ; `docs/plan_construction.md` n'est pas modifié)

**Étape J — API temps réel** : + 0,5 j. Ajouter une route de chiffres agrégés pour le portail (personnes, dossiers,
date de la passe de nuit ; « < 5 » ; aucun nom) et le droit « portail » dans la table des droits. Test : aucun
chiffre sous 5, DIRECTION servie, aucune identité dans la réponse.

**Étape K — Pages** : de 7–10 j à **10–14 j**, en deux lots.

| Lot | Contenu | Durée |
| --- | --- | --- |
| K1 | ce que le plan prévoit déjà : carte globale, carte par inscrit, vue dossier, deux vues synchronisées, curseur de force, filtres, bandeau d'alertes, `EventSource`, politique de sécurité du contenu | 7–10 j |
| K2 | le portail : en-tête commun, scène, panneau de détail, bas de page, mouvement, grille sous 900 px, fichier de contenu, essais dans le navigateur, captures | 3–4 j |

Texte proposé pour le plan, à ajouter à l'étape K :

> **Portail (lot K2).** Page d'accueil selon `docs/spec_portail.md` : base client au centre, cinq modules, dix
> usages, panneau de détail, quatre préalables ; contenu dans un fichier de configuration ; aucun chiffre sous 5,
> aucune donnée personnelle, aucune ressource externe. **Tests écrits d'abord** : affichage et chiffres agrégés ;
> navigation vers la carte et la base client ; panneau et retour du focus ; aucun chevauchement à 1 280, 1 440 et
> 1 920 px, grille à 375 px ; `prefers-reduced-motion` ; aucune requête hors de l'origine. **Fini quand** : essais
> verts, captures à 1 440 et 375 px jointes.

**Non chiffré, parce que non spécifié** : les écrans « Base client » et « Fiche client ». Ils ne sont ni dans le
plan actuel ni dans une spécification du dépôt. Sans eux, la tuile centrale n'a pas de destination : le lot K2 peut
la faire ouvrir son panneau en attendant (comme un module « à venir »), ou attendre leur spécification.

L'ordre des étapes ne change pas : H (graphe), I (alertes, nuit), J (API), K (pages).
