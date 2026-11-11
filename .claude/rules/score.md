---
paths:
  - "pipeline/regles/**"
  - "pipeline/couches/c5_*.py"
  - "pipeline/couches/c6_*.py"
  - "flux/graphe_vivant.py"
  - "flux/traiteur.py"
  - "flux/nuit.py"
  - "**/test_*chemin*.py"
  - "**/test_*score*.py"
  - "**/test_*controle*.py"
  - "**/test_*graphe*.py"
---

# Score « lien avec la liste noire » (décisions n°19 à 24 du 09/11/2026)

Toute valeur se lit dans `c6_version_parametres`, jamais en dur. « Provisoire » : à calibrer en rejouant les fraudes
confirmées avec la cellule fraude (`docs/questions_ouvertes.md`, n°2 à 7).

## Effet
- Une seule alerte Tandem, trois niveaux : critique, majeure, mineure. Sous le seuil : rien (le lien reste en base).
- Le score ordonne la file de la cellule fraude ; il ne refuse jamais un dossier (loi 09-08, article 11).
- Seules la liste noire et les fraudes confirmées marquent un fraudeur ; jamais un verdict Tandem.

## Longueur et niveau maximal (n°20)
- Longueur = liens entre personnes ou sociétés, depuis l'identité du dossier la plus proche : demandeur, caution,
  gérant, société ou employeur. Un identifiant partagé (RIB, n° d'affiliation, châssis, adresse) est un nœud, pas un
  lien : A – RIB – B vaut un lien « même RIB ».
- 0 lien (même CIN, même RC + tribunal, même ICE) : critique. 1 ou 2 : majeure au plus. 3 : mineure au plus.
  4 et plus : jamais d'alerte ; calculé à la demande, affiché en gris « hors alerte ».
- Sous ce maximum, la force décide si le niveau est atteint et ordonne les dossiers à l'intérieur d'un niveau.

## Force (n°21, n°22)
force = produit des poids de départ × produit des coûts(n) des nœuds traversés (jamais les deux bouts) × produit des fiabilités.
- coût(n) = 1 si n ≤ 2, sinon √(2/n). Contrôle : n = 2 → 1 ; 3 → 0,82 ; 5 → 0,63 ; 8 → 0,50 ; 40 → 0,22 ; 500 → 0,06.
- n : personne → ses sociétés (rôles terminés compris) ; société → dirigeants et associés cités ; employeur → clients
  EQDOM qui le déclarent, ou l'effectif de la liste des grands employeurs s'il est plus grand ; RIB, téléphone,
  courriel, adresse → personnes distinctes qui le portent (des personnes, pas des dossiers). Lu dans `c5_compteur`
  au moment du calcul, jamais figé dans une arête.
- Fiabilité : 1 pour un même CIN ; de 0,4 à 0,9 selon la règle, multiplié par la rareté du nom, pour un rapprochement
  probable ; × 0,5 par rôle lu seulement dans une annonce mélangée.
- Homonymie non levée à un bout (identité du dossier ↔ registre, registre ↔ inscrit) : plafond « mineure », mention
  « homonymie à lever ». Levée « même personne » : plafond normal ; « homonyme écarté » : chemin supprimé. Au milieu
  du chemin : effet sur la force seulement. Un employeur reconnu par son seul nom est une homonymie.
- Exemples de référence (tests) : gérant de 8 sociétés entre l'employeur et une société inscrite :
  0,7 × 0,5 × 0,7 = 0,245, majeure ; liquidateur de 40 sociétés : 0,5 × √(2/40) × 0,5 ≈ 0,0559, affiché sans alerte.

## Barème des liens (n°23), poids de départ
| Lien | Poids |
| --- | ---: |
| même RIB | 0,9 |
| salaire versé par un autre que l'employeur déclaré | 0,8 |
| virements entre deux personnes | 0,5 pour un seul, 0,7 à partir de deux |
| même fichier dans deux dossiers (empreinte identique) | 0,9 |
| co-emprunteurs d'un même dossier | 0,9 |
| caution | 0,8 |
| référence personnelle citée | 0,5 |
| même téléphone mobile, même courriel | 0,8 |
| même numéro d'abonné à l'eau ou à l'électricité | 0,7 |
| gérant ou dirigeant | 0,7 |
| associé (personne ou société) | 0,3 + 0,4 × part ; 0,5 si la part est inconnue |
| liquidateur | 0,5 |
| employé déclaré (attestation, bulletins, CNSS) | 0,6 |
| signataire de l'attestation de travail | 0,5 |
| cabinet qui a établi la liasse fiscale | 0,4 |
| même logement, même téléphone fixe | 0,5 |
| même siège social | 0,4 |
| même immeuble seulement | 0,2 |

Hors score (dessinés, sans poids) : apporteur, point de vente, agent de saisie, prélèvements d'un autre organisme de
crédit, même concessionnaire (provisoire). Même châssis dans deux dossiers : incohérence « double financement », pas
un lien (provisoire). Une société associée d'une autre suit la formule de l'associé.

## Foyer (n°24)
Conjoint déclaré, ou même nom de famille avec le même logement, le même téléphone fixe ou le même immeuble. Entre
membres d'un foyer : argent et pièces au poids plein (même RIB, virements, salaire versé par l'autre, même fichier) ;
tout le reste à 0,1 et jamais plus que « mineure » (« même foyer qu'un inscrit »). Sans lien de foyer : barème tel quel.

## Paramètres provisoires
- Seuils : majeure à partir de 0,20 ; mineure à partir de 0,08 ; affichage par défaut à partir de 0,05.
- Inscrit actif : poids 1 au bout du chemin, quel que soit le motif. Inscription « victime » : compte à 0 lien
  seulement, aucun rebond ; en attendant le dictionnaire des motifs, toutes propagent.
- Rôles terminés : poids actuels des anciens rôles (0,3 à 0,5) ; pas de demi-vie.
- Plusieurs inscrits atteints : niveau et force du meilleur chemin, nombre d'inscrits atteints affiché.
- Dossiers en rafale (même RIB, adresse ou employeur inconnu dans plusieurs dossiers en moins de 30 jours) : signal à
  part ; la force ne change pas.

## Alertes
- Niveau du dossier = le plus haut de ses chemins ; on garde les trois meilleurs (niveau, puis force) et le nombre
  d'inscrits atteints.
- Une alerte ne baisse jamais en journée (« chemin modifié ») ; le déclassement se fait la nuit, avec sa trace.
- La levée vaut pour le couple (dossier, inscrit) ; un chemin d'une autre nature qui fait monter le niveau rouvre l'alerte.
- Propagation : dossiers à 3 liens au plus d'un élément modifié ; au-delà de 200 dossiers touchés, renvoi à la nuit.
- Sortie : élément de `controls[]` au format de la v2 (`docs/source_v2.md` § 7.7), sans nom de tiers.
