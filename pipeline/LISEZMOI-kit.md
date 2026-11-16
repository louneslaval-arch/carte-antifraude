# Base « liste noire × registre du commerce »

SEVEN · réseaux de fraude EQDOM · 26/10/2026

Une base SQLite qui met face à face la liste noire EQDOM du 03/08/2026 et les annonces légales exportées par Kamal le 26/10/2026 (399 537 annonces, plus un fichier « personnes » de 536 805 lignes avec rôles, parts et CIN). Chaque côté est réduit à des **clés de comparaison** calculées par la même fonction ; des règles rapprochent les clés de même type ; on suit ensuite les rebonds dans le registre (inscrit → société → autres dirigeants et associés → leurs autres sociétés).

La base et les fichiers produits contiennent des données personnelles réelles : ils restent en local, sans lien publié, tant que la conformité d'EQDOM n'a pas donné son feu vert.

## 1. Les chaînes du dessin (22/10/2026)

```
PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3
                 1 arête          2 arêtes          3 arêtes          4 arêtes
```

`chaines_dessin.py` part de chaque inscrit retrouvé au registre et suit les rôles publiés (gérant, associé, liquidateur…) jusqu'à 4 arêtes. Une société associée d'une autre relie aussi deux sociétés en une arête. Il part aussi des sociétés inscrites retrouvées au registre.

| Au départ d'une personne inscrite | Chemins | Inscrits |
| --- | ---: | ---: |
| 1 arête : sociétés (PM n°1) | 172 | 121 |
| 2 arêtes : leurs autres dirigeants et associés (PP n°2) | 196 | 79 |
| 3 arêtes : les autres sociétés de ces personnes (PM n°2) | 23 | 14 |
| 4 arêtes : les dirigeants et associés de ces sociétés (PP n°3) | 13 | 6 |

Point de départ certain (même CIN, ou même RC + tribunal) pour 19 personnes inscrites ; les autres départs sont probables (nom + élément qui confirme). 93 chemins sont nouveaux depuis l'export du 22/10 (colonne « Nouveau depuis le 22/10 », étiquette « nouveau » dans la carte).

Au départ des 151 sociétés inscrites retrouvées au registre : 299, 56, 47 et 13 chemins à 1, 2, 3 et 4 arêtes.

**Retours vers la liste noire : 301 chemins.** Un autre élément de la liste noire se trouve sur le chemin (un second inscrit, une société inscrite, l'employeur déclaré d'un inscrit). Chacun est classé selon ce que la liste noire savait déjà :

| Nature | Chemins | Inscrits de départ | Sens |
| --- | ---: | ---: | --- |
| découverte | 80 | 40 | aucun lien entre les deux inscrits dans la liste noire : le registre apporte l'information |
| même lot | 94 | 58 | saisis dans une même saisie groupée de plus de 20 inscriptions (échange APSF…) |
| même dossier | 127 | 37 | saisis ensemble (même date, même agent, même note) : le registre confirme ce que la liste noire savait déjà |

Fichiers produits :

| Fichier | Contenu |
| --- | --- |
| `Chaines_liste_noire_RC.xlsx` | synthèse ; « Reliés à la liste noire » (découvertes en rouge, même lot en orange, même dossier en gris) ; chemins à 4, 3, 2 et 1 arêtes au départ d'une personne ; chemins au départ d'une société inscrite. Chaque ligne donne la chaîne en clair, chaque arête avec son rôle daté, chaque passage d'une société à l'autre et sa justification, chaque nœud (RC, ville, dernière annonce, lien vers l'annonce) et la fiabilité. |
| `Carte_globale_liste_noire.html` | tout le registre relié sur un seul écran (18 Mo) : 41 238 sociétés, 22 968 personnes présentes dans au moins deux sociétés, 53 871 liens, 16 387 réseaux (le plus grand : 23 nœuds) ; la liste noire par-dessus (121 inscrits, 363 sociétés et personnes inscrites). Filtre « liste noire seulement » (à 2, 4, 6 arêtes d'un inscrit, ou tout le réseau), départs certains, rôles terminés, nombre de sociétés par personne, seuil de force ; recherche, touches Z et A pour zoomer à la souris, clic pour le détail, double-clic pour isoler un réseau. Les personnes qui n'ont qu'une société et aucun lien avec la liste noire ne sont pas dessinées (leur nombre figure dans la fiche de la société). |
| `Carte_reseaux_liste_noire.html` | le réseau de chaque inscrit dessiné comme le schéma : colonnes 1 à 4 arêtes, éléments de la liste noire en rouge (plein : découverte ; pointillé : déjà lié dans la liste noire), rôles terminés en pointillé gris, filtre « découvertes seulement », clic sur un nœud pour voir le chemin et l'annonce. Fichier autonome, fonctionne sans connexion. |

### Rôles datés

Chaque arête porte le rôle de la dernière annonce qui cite la personne dans la société, avec sa date. Les parts et la gérance sont suivies à part :

- **parts** : la dernière annonce qui touche aux parts décide. Si la personne y est cédante, elle devient « ancien associé (cédé 02/2023) », sauf cession partielle ;
- **gérance** : un autre gérant nommé ensuite par un changement de gérant donne « ancien gérant (autre gérant nommé 01/2024) ».

Deux pourcentages lus à des dates différentes ne s'additionnent donc plus comme s'ils étaient contemporains. Un rôle lu seulement dans une annonce mélangée (deux annonces dans un même bloc) est marqué « annonce mélangée » et compte pour moitié.

### Comment on reconnaît une personne du registre

L'export ne porte quasiment pas de CIN : 412 sur 465 000 personnes citées. On procède donc ainsi :

1. **Inscrit ↔ registre** : nom + un élément qui confirme (la société est elle-même inscrite, ou même ville, ou employeur déclaré). Statut « probable », à valider par un analyste.
2. **Dans une même société** : même nom (ordre des mots indifférent), même nom écrit en latin et en arabe (mêmes consonnes, mêmes voyelles longues, mêmes coupures entre les mots), ou deux graphies à une lettre sœur près ([arabe]).
3. **D'une société à l'autre** (le passage de PP n°2) :
   - même CIN ;
   - ou même nom + même ville du siège, si ce nom figure dans 5 sociétés au plus. Il faut en plus que le nom soit rare (moins de 0,15 personne attendue par hasard avec ce prénom et ce nom), ou qu'un indice confirme : même adresse, même cabinet déposant, ou un associé ou gérant commun aux deux sociétés.
   - Le passage indique s'il repose sur un nom rare ou sur un indice, et si le nom est écrit dans un autre ordre. 17 441 passages par un nom courant sans indice ont été refusés.
   - Un même CIN ne relie deux sociétés que si les noms portés sont compatibles (même clé, variante, ou latin ↔ arabe) : 1 457 CIN partagés par des noms différents (CIN rattaché à la mauvaise personne dans une annonce) ont été refusés (02/11/2026).
4. L'inscrit ne revient pas en bout de chaîne sous une autre graphie de son nom (« [arabe] » / « [arabe] »).

**Fiabilité** d'une chaîne = poids du rapprochement inscrit ↔ registre × passages d'une société à l'autre (1 pour un même CIN, 0,8 × n^-0,5 pour un même nom + même ville, n = nombre de sociétés qui portent ce nom au Maroc) × 0,5 par rôle lu seulement dans une annonce mélangée. **Force** = fiabilité × poids des rôles (gérant 0,7 ; associé 0,3 à 0,7 selon les parts ; liquidateur 0,5 ; ancien rôle 0,3 à 0,5) × rareté de la taille de la société. La page masque les liens faibles avec un curseur.

### Nettoyage renforcé des noms (02/11/2026)

Relecture des 64 000 nœuds de la carte globale : des phrases juridiques restaient lues comme des noms (« [exemple retiré] », « [exemple retiré] », « [exemple retiré] »), parfois présentes dans deux sociétés, donc faux ponts ; des entrées collaient deux personnes (« [exemple retiré] ») ; des CIN mal rattachés fusionnaient deux personnes différentes (« [exemple retiré] »). `chaines_dessin.nettoyer_nom` s'applique au chargement, sans reconstruire la base :

- vocabulaire juridique supplémentaire (`STOP_SUPPLEMENT`), reconnu aussi derrière un préfixe [arabe] (« [arabe] », « [arabe] ») ; le nom est coupé au premier mot juridique s'il reste au moins deux mots devant (« [arabe] » → « [arabe] »), sinon écarté ; « [arabe] », « [arabe] », « [arabe] » restent des noms ;
- entrée qui enchaîne deux personnes par « [arabe] » + prénom courant → écartée (1 060 entrées) ;
- adresses lues comme un nom ([exemples retirés]) → écartées ; adresse collée à une dénomination retirée à l'affichage (« [exemple retiré] » → « [exemple retiré] ») ;
- même CIN mais noms incompatibles → pas de pont (voir ci-dessus).

Au total 3 132 entrées écartées au lieu de 257. Les 122 inscrits reliés et les 16 300 réseaux sont inchangés ; le plus grand réseau de la liste noire passe de 23 à 17 nœuds.

`exclusions_carte.json` : noms à ne jamais dessiner (variantes et motif), appliqués au chargement ; les mentions restent dans la base. Des entrées au 02/11/2026.

### Dossiers de l'antifraude (11/11/2026)

`charger_antifraude.py` ajoute à la base l'export « antifraude_export_complet » (données extraites des pièces des dossiers : lot de
production du 13/10 au 10/11/2026, 4 250 dossiers ; lot de préproduction depuis juillet, 1 271 dossiers). Rien n'est modifié dans les
tables `bl_*` et `rc_*` ; tout est dans des tables `af_*`, recréées à chaque passage.

- **Ce qui est lu** : contexte du dossier (type de client, produit, verdict, état civil déclaré) ; pièce CIN (identité, filiation, adresse) ;
  extrait du registre et statuts (société, RC, tribunal, ICE, gérants, associés, dirigeants avec leur CIN) ; attestations de travail,
  bulletins de paie, attestations CNSS (salarié et employeur) ; pension, carte professionnelle, carte grise ; RIB des relevés et des
  attestations ; vendeur des factures proforma ; tiers bancaires (libellés des virements, versements et chèques, agrégés par dossier).
- **Identités** (`af_identite`) : une personne = un CIN (5 906 personnes, 811 dans plusieurs dossiers ; 514 sans CIN restent propres à
  leur dossier) ; une société = RC + tribunal, sinon ICE (1 387), sinon son nom dans le dossier ; employeurs et vendeurs par leur raison
  sociale. `af_dossier_identite` dit qui apparaît dans quel dossier et avec quel rôle ; `af_relation` porte les 7 449 relations
  personne – société (gérant, associé, dirigeant, salarié). Les valeurs d'exemple rendues par le modèle de lecture (« JOHN DOE »,
  CIN « A123456 ») sont écartées. <!-- fictif-volontaire : valeur gabarit -->
- **Liens** (`af_lien`, vue `v_af_lien`) : AF01 même CIN qu'un inscrit (13, certains) ; AF02 / AF02b / AF02n / AF02d société inscrite par
  RC + tribunal, RC seul, ou raison sociale (7) ; AF03 / AF03b / AF03n société du registre par RC + tribunal (341 certains, 6 probables,
  31 à vérifier : le registre porte alors souvent le nom du cabinet déposant) ; AF04 personne du registre par CIN (110) ; AF05 gérant ou
  associé retrouvé dans la même société du registre par son nom : **le dossier apporte le CIN** (339 CIN nouveaux, 12 confirmés,
  2 conflits, table `af_cin_apporte`) ; AF07 employeur = société inscrite ou employeur déclaré d'un inscrit (7, à vérifier) ; AF09 même RIB
  dans des dossiers de clients sans lien (16, indice) ; AF11 tiers bancaire au nom d'un inscrit (36, indice, faible si nom courant) ;
  AF20 identité d'un dossier située sur un chemin du registre partant d'un inscrit (5).
- `rapport_antifraude.py` produit `Liens_antifraude.xlsx` (Synthèse, Liste noire, Réseau, Sociétés au registre, CIN apportés,
  Enrichissement de la liste noire, Plusieurs dossiers, RIB partagés, Tiers bancaires).

Limites : les sociétés des dossiers ne sont retrouvées au registre que pour un quart (347 sur 1 387), l'export des annonces ne couvrant
que 2021-2026 et une partie des dénominations ; un tiers bancaire n'est qu'un libellé, jamais une identité ; l'export contient des
données personnelles réelles (diffusion limitée, suppression après usage, d'après sa notice).

### Nettoyage de la liste noire (09/11/2026)

`nettoyer_liste_noire.py` applique au fichier brut EQDOM la même normalisation que `construire_base.py` (fonctions partagées
`lire_ligne_bl`, `normaliser_inscription`, `ecarter_doublons`, `regrouper_inscriptions`) et produit `Liste_noire_nettoyee.xlsx` :

- **Inscriptions nettoyées** (première feuille, colonnes EQDOM + entité, identifiant fiscal, code ville d'origine, corrections, à traiter) :
  remplace le fichier brut en entrée de la base ;
- **Corrections** : chaque valeur changée (n° de séquence, champ, avant, après, action) ; **Doublons écartés** ; **Entités** : une ligne par
  personne ou société avec l'historique des inscriptions ; **À traiter par EQDOM** : ce que le programme ne peut pas corriger ;
  **Référentiels** : codes ville, motif, tribunal, agence sans libellé.

Sur la liste du 03/08/2026 : 7 396 lignes, 330 doublons exacts (mêmes valeurs sur toutes les colonnes hors n° de séquence et
utilisateur), 7 066 inscriptions, 6 248 entités (4 713 personnes, 1 535 sociétés), 6 614 corrections automatiques
(1 665 RC normalisés, 1 031 RC repris de la colonne CIN, 771 types de client déduits, 544 codes ville traduits, 225 « PP/PM »
retirés de la colonne tribunal, 218 codes tribunal traduits, 203 dates de naissance impossibles vidées…), 3 648 points à
traiter (1 600 sociétés sans tribunal, 917 personnes sans nom, 459 sans CIN, 217 codes ville inconnus, 132 CIN avec des
orthographes différentes du même nom, 47 CIN portés par des noms différents, 103 sociétés sans RC…).

La base est désormais construite depuis la liste nettoyée ; `construire_base.py` écarte aussi les doublons exacts s'il lit le fichier brut.

### Écriture latine des noms arabes (03/11/2026)

`translitteration.py` apprend, dans la base elle-même, l'écriture latine de chaque mot arabe : quand une personne a été publiée dans les deux écritures dans une même société (4 418 cas), les mots sont appariés par squelette consonantique ([arabe] → MOHAMED, [arabe] → IDRISSI, [arabe] → ABDELLAH) ; l'écriture la plus fréquente est gardée (`ref_translitteration`, 3 488 mots). Un mot jamais vu en latin est translittéré par règles ([arabe] → CH, [arabe] → KH, [arabe] → GH, [arabe] → K, [arabe] → OU, voyelle A d'appui entre consonnes). Résultat dans `rc_personne.nom_latin` (430 000 lignes) et `rc_societe.denomination_latin` (14 900), calculé à la fin de chaque construction. Ce n'est pas une traduction (« [arabe] » → CHARKA). Les deux cartes ont une case « translittération » : les noms arabes s'affichent alors avec leur écriture latine entre parenthèses ; la recherche la prend aussi en compte.

### Relecture indépendante (22/10/2026)

Un relecteur a repris 25 chaînes contre le texte brut des annonces : 15 solides, 7 plausibles, 2 douteuses, 1 fausse. Aucun rôle n'était inventé. Il a relevé quatre défauts : rôles sans date, annonces mélangées non signalées, passages par des noms courants, retours vers la liste noire non distingués d'une simple confirmation. Les quatre sont corrigés dans cette version : rôles datés, annonces mélangées signalées, indice exigé pour un nom courant, nature du retour.

## 2. Ce que contient la base

| | Nombre |
| --- | ---: |
| Inscriptions de la liste noire du 03/08/2026 | 7 396 |
| Entités inscrites (personnes 4 717, sociétés 1 535) | 6 252 |
| Personnes inscrites avec un CIN valide | 4 206 |
| Sociétés inscrites avec un RC / avec RC + tribunal | 1 433 / 207 |
| Annonces légales chargées (export de Kamal) | 399 537 |
| Sociétés du registre | 312 032 |
| Personnes citées (une ligne par personne et par société) | 477 765 |
| Entrées écartées (phrases, adresses, gabarits lus comme des noms) | 24 025 |
| Personnes citées avec un CIN / CIN distincts | 17 415 / 12 753 |
| CIN communs avec la liste noire | 25 (19 inscrits, 23 sociétés) |
| Correspondances certaines (alerte) | 55 |
| Correspondances probables (à lever par un analyste) | 378 |
| Correspondances faibles (sous le seuil, masquées) | 579 |

Anomalies de la liste noire (vue `v_qualite_bl`) : « PP » ou « PM » saisis dans la colonne tribunal, dates de naissance hors bornes, CIN à lettre finale parasite, masqués ou sans lettres, identifiants fiscaux saisis comme RC, valeurs corrompues, encodage cassé réparé à la lecture.

## 3. Contrôles de l'export de Kamal

Vue `v_qualite_rc`. Chaque correction protège contre un faux lien :

- **Numéro RC** : égal au numéro de dépôt, à l'année de l'acte ou de la publication, plus de 8 chiffres, ou 1 à 2 chiffres (« RC 21 Casablanca » regroupait une vingtaine de sociétés sans rapport) → ignoré. Un RC qui porte trois noms incompatibles ou plus sous le même tribunal est mal lu → ignoré, chaque annonce est rattachée à son nom.
- **Dénomination** : en-têtes (« AVIS DE CONSTITUTION »), forme juridique seule, nom générique, adresse, nom porté par trois RC différents (fiduciaire) → pas utilisés comme identité. L'en-tête « VILLE MAROC » collé devant le nom est retiré.
- **Sous un même RC + tribunal**, des noms incompatibles séparent la société en deux (`rc_conflit`), sauf changement de dénomination publié (l'ancien et le nouveau nom restent ensemble) ou nom complété d'un quartier (« … AGDAL RABAT »). Une annonce sans nom lisible sous un RC partagé n'est rattachée à aucune des deux.
- **Personnes citées** : phrases juridiques, adresses, nombres écrits en lettres, champs vides → écartés et motivés (`rc_rejet`). Une page du Bulletin officiel lue comme une seule annonce (en-tête du tribunal « [arabe]… », dizaines de personnes sans rapport) → toutes ses personnes écartées (`page_fusionnee`) : sans cela, elles formaient un faux réseau de 2 800 nœuds. Une annonce lue dans un bloc mélangé compte pour moitié (fiabilité 0,5).
- **Passage arabe ↔ latin** : le squelette consonantique propose ; les voyelles longues, les coupures entre les mots, la fin des mots (SAIDA ≠ [arabe], MABROUKI ≠ [arabe], NADIA ≠ [arabe]) et l'alif initial (HAMID ≠ [arabe]) décident. Sur 80 paires de test : 17 faux rejetés sur 17, 60 vrais gardés sur 63.

## 4. Les règles et les niveaux

| Règle | Ce qui doit concorder | Niveau | Poids |
| --- | --- | --- | --- |
| R01 | même CIN | certain | 1,0 |
| R01b | CIN saisi sur une société inscrite = personne citée | certain | 1,0 |
| R01v | CIN avec lettre finale parasite = CIN sans la lettre | probable | 0,8 |
| R01n | même CIN, mais le nom cité ne correspond pas (CIN peut-être rattaché à la mauvaise personne de l'annonce) | probable | 0,7 |
| R02 | même RC, même tribunal, noms compatibles | certain | 1,0 |
| R02n | même RC et même tribunal, noms différents ou annonce douteuse | probable | 0,5 |
| R03 | même RC (tribunal absent d'un côté), même raison sociale | probable | 0,9 × similarité |
| R03t | même RC dans deux tribunaux différents, raison sociale très proche | probable | 0,6 |
| R04 | même raison sociale et même ville | probable | 0,7 / 0,6 × rareté |
| R05 | même nom de personne et même société | probable | 0,8 / 0,7 × rareté |
| R05b | même nom, dans une société elle-même reliée à une société inscrite | probable | 0,8 / 0,7 × rareté |
| R06 | même nom et même date de naissance | probable | 0,8 / 0,7 × rareté |
| R07 | même nom et même ville | probable | 0,5 / 0,4 × rareté |
| R08 | employeur déclaré de l'inscrit = société du registre | probable | 0,6 / 0,5 × rareté |
| R09 | adresse de l'inscrit = siège d'une société | probable | 0,4 × rareté |
| R10, R11 | même ICE, même identifiant fiscal | certain | 1,0 |

Le nom seul n'est jamais un lien. **Rareté** = n^-0,5 (n = nombre de sociétés qui partagent la valeur). **Statuts** : `alerte`, `homonymie` (à lever par un analyste), `a_verifier`, `faible` (sous 0,1 : gardé, hors file et hors graphe), `confirme`, `ecarte`. Une décision d'analyste (`decision_analyste`) survit aux reconstructions.

## 5. Commandes

```
# 0. nettoyer la liste noire brute (quelques secondes) : doublons, colonnes inversées, codes, dates, entités
python3 nettoyer_liste_noire.py --entree Liste_noir_03_08_2026.xlsx --sortie Liste_noire_nettoyee.xlsx

# construire la base (environ 6 minutes) : liste noire nettoyée + annonces + fichier « personnes » de Kamal
python3 construire_base.py --liste-noire Liste_noire_nettoyee.xlsx \
        --rc-kamal annonces-legales-2026-10-26.csv \
        --rc-kamal-personnes personnes-annonces-legales-2026-10-26.csv --base bl_rc.sqlite

# dossiers de l'antifraude : chargement, identités, liens (10 secondes), puis classeur des liens
python3 charger_antifraude.py --base bl_rc.sqlite --export antifraude_export_complet_2026-11-10
python3 rapport_antifraude.py --base bl_rc.sqlite --sortie Liens_antifraude.xlsx

# écart entre deux constructions (nouvel export)
python3 comparer_bases.py --avant bl_rc_22-10.sqlite --apres bl_rc.sqlite

# chaînes du dessin : Excel + carte (environ 1 minute)
python3 chaines_dessin.py --base bl_rc.sqlite --excel Chaines_liste_noire_RC.xlsx --html Carte_reseaux_liste_noire.html \
        --json carte.json --precedent carte_precedente.json      # --precedent : marque ce qui est nouveau
python3 carte_globale.py --base bl_rc.sqlite --html Carte_globale_liste_noire.html   # tout le registre relié, un seul écran (3 min)
# La page a deux vues : « Vue réseau » (réseaux rangés) et « Carte du Maroc 3D » (bouton ou touche M) : société à la ville de son
# siège sinon de son tribunal, personne à la ville la plus fréquente de ses sociétés, inscrit à la ville de la personne reliée ;
# plateau incliné (clic droit / Maj + glisser), épingles rouges = liste noire, arcs = liens entre villes, zone à droite = sans ville.

# toutes les correspondances et la feuille « À lever » pour les analystes, puis réimport des décisions
python3 rapport_croisement.py --base bl_rc.sqlite --sortie Croisement_liste_noire_RC.xlsx
python3 rapport_croisement.py --base bl_rc.sqlite --decisions Croisement_liste_noire_RC.xlsx
python3 construire_base.py --base bl_rc.sqlite --regles-seulement

# écriture latine des noms arabes sur une base déjà construite (sinon faite à la fin de la construction)
python3 translitteration.py --base bl_rc.sqlite
python3 translitteration.py --base bl_rc.sqlite --essai "[arabe]"      # essai sans rien écrire
```

Python 3.9 ou plus, avec pandas et openpyxl. Le modèle générique d'export (deux fichiers à plat ou un JSON) reste accepté : `--rc-annonces`, `--rc-personnes`, `--rc-json` (modèles fictifs dans `modele_export_kamal/`).

## 6. Requêtes utiles

```sql
-- L'employeur d'un demandeur est-il relié à la liste noire ?
SELECT * FROM v_controle_employeur WHERE rc_num = '123456' AND tribunal_code = 'CASABLANCA';
-- File des homonymies à lever
SELECT * FROM v_homonymies_a_traiter;
-- Fiche d'un inscrit et ses liens
SELECT * FROM v_bl_fiche WHERE cle_entite = 'P:ZZ123456';
SELECT * FROM v_correspondance WHERE cle_entite = 'P:ZZ123456';
-- Qualité de l'export
SELECT * FROM v_qualite_rc;
```

## 7. Limites et ce qui les lèverait

1. **CIN encore rare dans l'export.** Depuis le 26/10, 17 415 personnes citées ont un CIN (3,7 %), 25 CIN sont communs avec la liste noire. Dans 7 cas sur 30, le CIN est rattaché à une personne dont le nom ne correspond pas (règle R01n, à vérifier). Les annonces du Bulletin officiel citent le CIN en arabe (« [arabe] ») : l'extraction doit le lire aussi. La date de naissance manque toujours.
2. **Écriture.** 94 % des personnes du registre sont en arabe, la liste noire est en latin. Les noms qui ne s'écrivent pas pareil (NAJAT / [arabe], LAZRAK / [arabe]) sont manqués plutôt que confondus.
3. **Tribunal manquant côté EQDOM** : 207 sociétés inscrites sur 1 433 ont un tribunal. Un RC n'est unique que dans son tribunal.
4. **Période** : l'export couvre surtout les annonces de 2022 à 2026. Une société sans annonce récente n'apparaît pas.
5. **Nom du déposant** : certaines annonces portent le nom du cabinet ou du domiciliataire à la place de celui de la société ; la chaîne le signale (« nom du déposant de l'annonce ? »), le RC reste juste.
6. **Poids et seuils** fixés à dire d'expert : à recalibrer en rejouant des fraudes confirmées.
7. **Doublons dans la liste noire** : quelques inscrits retombent sur la même personne du registre ([exemples retirés]) ; la carte et l'Excel le signalent (« [exemple retiré] »). La clé « [exemple retiré] » ignore les lettres isolées : « [exemple retiré] » et « [exemple retiré] » se confondent.

## 8. Contenu du dossier

| Fichier | Rôle |
| --- | --- |
| `construire_base.py` | normalisation commune, lecture de l'export de Kamal, contrôles, règles, bilan |
| `schema_bl_rc.sql` | tables, index et vues, commentés |
| `regles_bl_rc.sql` | règles R01 à R11, décisions, graphe et chemins |
| `chaines_dessin.py` | chaînes du dessin, Excel et carte ; `--precedent` marque les nouveautés |
| `comparer_bases.py` | écart entre deux constructions de la base |
| `carte_chaines_modele.html` | modèle de la carte par inscrit (les données y sont insérées) |
| `carte_globale.py`, `carte_globale_modele.html` | vue d'ensemble : disposition calculée réseau par réseau (networkx), page autonome |
| `geo_maroc.py`, `maroc_regions.json` | vue « Carte du Maroc 3D » de la carte globale : coordonnées des 94 villes du référentiel, contour des régions (Natural Earth, local), disposition par ville (disques, tournesol par réseau, zone « sans ville connue » à droite) |
| `nettoyer_liste_noire.py` | liste noire nettoyée (classeur à 7 feuilles) à partir du fichier brut EQDOM ; même logique que la lecture de la base |
| `charger_antifraude.py`, `rapport_antifraude.py` | dossiers de l'antifraude : tables `af_*`, identités, liens avec la liste noire et le registre, classeur des liens |
| `translitteration.py` | écriture latine des noms arabes, apprise sur la base puis par règles ; colonnes `nom_latin`, `denomination_latin`, table `ref_translitteration` |
| `exclusions_carte.json` | noms à ne jamais dessiner sur les cartes (variantes, motif) |
| `rapport_croisement.py` | classeur de toutes les correspondances, feuille « À lever », réimport des décisions |
| `modele_export_kamal/`, `jeu_essai/` | modèles et jeu d'essai entièrement fictifs |

La base (`bl_rc.sqlite`, près de 1 Go) se reconstruit en une commande à partir des deux fichiers sources ; elle n'est pas jointe au dossier.
