# Base « liste noire × registre du commerce »

SEVEN · réseaux de fraude EQDOM · 22/10/2026

Une base SQLite qui met face à face la liste noire EQDOM du 03/08/2026 et les annonces légales exportées par Kamal le 22/10/2026 (399 537 annonces). Chaque côté est réduit à des **clés de comparaison** calculées par la même fonction ; des règles rapprochent les clés de même type ; on suit ensuite les rebonds dans le registre (inscrit → société → autres dirigeants et associés → leurs autres sociétés).

La base et les fichiers produits contiennent des données personnelles réelles : ils restent en local, sans lien publié, tant que la conformité d'EQDOM n'a pas donné son feu vert.

## 1. Les chaînes du dessin (22/10/2026)

```
PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3
                 1 arête          2 arêtes          3 arêtes          4 arêtes
```

`chaines_dessin.py` part de chaque inscrit retrouvé au registre et suit les rôles publiés (gérant, associé, liquidateur, ancien gérant…) jusqu'à 4 arêtes. Une société associée d'une autre relie aussi deux sociétés en une arête. Il part aussi des sociétés inscrites retrouvées au registre.

| Au départ d'une personne inscrite | Chemins | Inscrits |
| --- | ---: | ---: |
| 1 arête : sociétés (PM n°1) | 139 | 99 |
| 2 arêtes : leurs autres dirigeants et associés (PP n°2) | 166 | 66 |
| 3 arêtes : les autres sociétés de ces personnes (PM n°2) | 35 | 19 |
| 4 arêtes : les dirigeants et associés de ces sociétés (PP n°3) | 11 | 5 |

Au départ des 151 sociétés inscrites retrouvées au registre : 300, 83, 66 et 24 chemins à 1, 2, 3 et 4 arêtes.

**Réseaux qui reviennent vers la liste noire : 324 chemins, au départ de 127 inscrits.** Un autre élément de la liste noire se trouve sur le chemin : un second inscrit, une société inscrite, ou l'employeur déclaré d'un inscrit. Trois formes reviennent :

- une société inscrite dont plusieurs dirigeants et associés sont eux-mêmes inscrits, souvent de la même famille ;
- un inscrit qui mène à un second inscrit, gérant lui-même d'autres sociétés ;
- des sociétés inscrites aux numéros RC consécutifs, gérées par la même personne.

Fichiers produits :

| Fichier | Contenu |
| --- | --- |
| `Chaines_liste_noire_RC.xlsx` | synthèse ; « Reliés à la liste noire » (en rouge) ; chemins à 4, 3, 2 et 1 arêtes au départ d'une personne ; chemins au départ d'une société inscrite. Chaque ligne donne la chaîne en clair, chaque arête, chaque nœud (RC, ville, dernière annonce, lien vers l'annonce) et la fiabilité. |
| `Carte_reseaux_liste_noire.html` | le réseau de chaque inscrit dessiné comme le schéma : colonnes 1 à 4 arêtes, rôles sur les arêtes, éléments de la liste noire en rouge, clic sur un nœud pour voir le chemin qui y mène et l'annonce. Fichier autonome, fonctionne sans connexion. |

### Comment on reconnaît une personne du registre

L'export ne porte quasiment pas de CIN : 412 sur 465 000 personnes citées. On procède donc ainsi :

1. **Inscrit ↔ registre** : nom + un élément qui confirme (la société est elle-même inscrite, ou même ville, ou employeur déclaré). Statut « probable », à valider par un analyste.
2. **Dans une même société** : même nom (ordre des mots indifférent), ou même nom écrit en latin et en arabe (mêmes consonnes, mêmes voyelles longues, mêmes coupures entre les mots), ou deux graphies arabes à une lettre sœur près (اصيل / اسيل).
3. **D'une société à l'autre** (le passage de PP n°2) : même CIN, ou même nom + même ville du siège quand ce nom figure dans 5 sociétés au plus. Un nom plus courant ne relie jamais deux sociétés.
4. L'inscrit ne revient pas en bout de chaîne sous une autre graphie de son nom (« جاموس » / « دجاموس »).

**Fiabilité** d'une chaîne = poids du rapprochement inscrit ↔ registre × passages d'une société à l'autre (1 pour un même CIN, 0,8 × n^-0,5 pour un même nom + même ville, n = nombre de sociétés qui portent ce nom). **Force** = fiabilité × poids des rôles (gérant 0,7 ; associé 0,3 à 0,7 selon les parts ; liquidateur et ancien gérant 0,5 ; cédant 0,3) × rareté de la taille de la société. La page masque les liens faibles avec un curseur.

## 2. Ce que contient la base

| | Nombre |
| --- | ---: |
| Inscriptions de la liste noire du 03/08/2026 | 7 396 |
| Entités inscrites (personnes 4 717, sociétés 1 535) | 6 252 |
| Personnes inscrites avec un CIN valide | 4 206 |
| Sociétés inscrites avec un RC / avec RC + tribunal | 1 433 / 207 |
| Annonces légales chargées (export de Kamal) | 399 537 |
| Sociétés du registre | 312 032 |
| Personnes citées (une ligne par personne et par société) | 475 692 |
| Entrées écartées (phrases, adresses, gabarits lus comme des noms) | 53 187 |
| Correspondances certaines (alerte) | 32 |
| Correspondances probables (à lever par un analyste) | 369 |
| Correspondances faibles (sous le seuil, masquées) | 576 |

Anomalies de la liste noire (vue `v_qualite_bl`) : « PP » ou « PM » saisis dans la colonne tribunal, dates de naissance hors bornes, CIN à lettre finale parasite, masqués ou sans lettres, identifiants fiscaux saisis comme RC, valeurs corrompues, encodage cassé réparé à la lecture.

## 3. Contrôles de l'export de Kamal

Vue `v_qualite_rc`. Chaque correction protège contre un faux lien :

- **Numéro RC** : égal au numéro de dépôt, à l'année de l'acte ou de la publication, plus de 8 chiffres, ou 1 à 2 chiffres (« RC 21 Casablanca » regroupait une vingtaine de sociétés sans rapport) → ignoré. Un RC qui porte trois noms incompatibles ou plus sous le même tribunal est mal lu → ignoré, chaque annonce est rattachée à son nom.
- **Dénomination** : en-têtes (« AVIS DE CONSTITUTION »), forme juridique seule, nom générique, adresse, nom porté par trois RC différents (fiduciaire) → pas utilisés comme identité. L'en-tête « VILLE MAROC » collé devant le nom est retiré.
- **Sous un même RC + tribunal**, des noms incompatibles séparent la société en deux (`rc_conflit`), sauf changement de dénomination publié (l'ancien et le nouveau nom restent ensemble) ou nom complété d'un quartier (« … AGDAL RABAT »). Une annonce sans nom lisible sous un RC partagé n'est rattachée à aucune des deux.
- **Personnes citées** : phrases juridiques, adresses, nombres écrits en lettres, champs vides → écartés et motivés (`rc_rejet`). Une annonce lue dans un bloc mélangé compte pour moitié (fiabilité 0,5).
- **Passage arabe ↔ latin** : le squelette consonantique propose ; les voyelles longues, les coupures entre les mots, la fin des mots (SAIDA ≠ سعيد, MABROUKI ≠ مبروك, NADIA ≠ ندى) et l'alif initial (HAMID ≠ احمد) décident. Sur 80 paires de test : 17 faux rejetés sur 17, 60 vrais gardés sur 63.

## 4. Les règles et les niveaux

| Règle | Ce qui doit concorder | Niveau | Poids |
| --- | --- | --- | --- |
| R01 | même CIN | certain | 1,0 |
| R01b | CIN saisi sur une société inscrite = personne citée | certain | 1,0 |
| R01v | CIN avec lettre finale parasite = CIN sans la lettre | probable | 0,8 |
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
# construire la base (environ 7 minutes)
python3 construire_base.py --liste-noire Liste_noir_03_08_2026.xlsx \
        --rc-kamal annonces-legales-2026-10-22.csv --base bl_rc.sqlite

# chaînes du dessin : Excel + carte (environ 1 minute)
python3 chaines_dessin.py --base bl_rc.sqlite --excel Chaines_liste_noire_RC.xlsx --html Carte_reseaux_liste_noire.html

# toutes les correspondances et la feuille « À lever » pour les analystes, puis réimport des décisions
python3 rapport_croisement.py --base bl_rc.sqlite --sortie Croisement_liste_noire_RC.xlsx
python3 rapport_croisement.py --base bl_rc.sqlite --decisions Croisement_liste_noire_RC.xlsx
python3 construire_base.py --base bl_rc.sqlite --regles-seulement
```

Python 3.9 ou plus, avec pandas et openpyxl. Le modèle générique d'export (deux fichiers à plat ou un JSON) reste accepté : `--rc-annonces`, `--rc-personnes`, `--rc-json` (modèles fictifs dans `modele_export_kamal/`).

## 6. Requêtes utiles

```sql
-- L'employeur d'un demandeur est-il relié à la liste noire ?
SELECT * FROM v_controle_employeur WHERE rc_num = '123456' AND tribunal_code = 'CASABLANCA';
-- File des homonymies à lever
SELECT * FROM v_homonymies_a_traiter;
-- Fiche d'un inscrit et ses liens
SELECT * FROM v_bl_fiche WHERE cle_entite = 'P:AB123456';
SELECT * FROM v_correspondance WHERE cle_entite = 'P:AB123456';
-- Qualité de l'export
SELECT * FROM v_qualite_rc;
```

## 7. Limites et ce qui les lèverait

1. **CIN absent de l'export (le verrou principal).** 412 CIN sur 465 000 personnes, aucun commun avec les 4 206 de la liste noire. Les annonces de constitution citent souvent « titulaire de la CIN n° … » : extraire ce champ (et la date de naissance) ferait passer les rapprochements de « probable » à « certain ».
2. **Écriture.** 94 % des personnes du registre sont en arabe, la liste noire est en latin. Les noms qui ne s'écrivent pas pareil (NAJAT / نجاة, LAZRAK / الأزرق) sont manqués plutôt que confondus.
3. **Tribunal manquant côté EQDOM** : 207 sociétés inscrites sur 1 433 ont un tribunal. Un RC n'est unique que dans son tribunal.
4. **Période** : l'export couvre surtout les annonces de 2022 à 2026. Une société sans annonce récente n'apparaît pas.
5. **Nom du déposant** : certaines annonces portent le nom du cabinet ou du domiciliataire à la place de celui de la société ; la chaîne le signale (« nom du déposant de l'annonce ? »), le RC reste juste.
6. **Poids et seuils** fixés à dire d'expert : à recalibrer en rejouant des fraudes confirmées.

## 8. Contenu du dossier

| Fichier | Rôle |
| --- | --- |
| `construire_base.py` | normalisation commune, lecture de l'export de Kamal, contrôles, règles, bilan |
| `schema_bl_rc.sql` | tables, index et vues, commentés |
| `regles_bl_rc.sql` | règles R01 à R11, décisions, graphe et chemins |
| `chaines_dessin.py` | chaînes du dessin, Excel et carte |
| `carte_chaines_modele.html` | modèle de la carte (les données y sont insérées) |
| `rapport_croisement.py` | classeur de toutes les correspondances, feuille « À lever », réimport des décisions |
| `modele_export_kamal/`, `jeu_essai/` | modèles et jeu d'essai entièrement fictifs |

La base (`bl_rc.sqlite`, près de 1 Go) se reconstruit en une commande à partir des deux fichiers sources ; elle n'est pas jointe au dossier.
