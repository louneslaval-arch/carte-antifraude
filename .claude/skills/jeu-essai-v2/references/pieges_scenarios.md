# Pièges et scénarios du jeu d'essai v2

Source : annexe H.2 du document de lancement (11/11/2026). Les attendus suivent les paramètres provisoires de
`.claude/rules/score.md`.

## Pièges (T)

| N° | Piège |
| --- | --- |
| T01 | relevé relu : `date_operation` au format `jj/mm` sans année, `date_valeur`, `libelle`, `debit`, `credit` ; année tirée de `mois[].annee` ; relevé à cheval sur décembre et janvier |
| T02 | relevé non relu : une ligne par mois, sans date, reconstituée par l'amont (salaire ou pension) |
| T03 | CIN multiple : `cartes[]` |
| T04 | clés en double, plate et imbriquée : `vehicule.marque` et `vehicule: {marque}` ; de même `prix.prix_total_ttc`, `employeur.raison_sociale`, `remuneration.salaire_net` |
| T05 | clés inventées : `remeration.salaire_net`, `revelation.salaire_brut` ; champs de CIN (`filiation_complete`, `date_expiration`, `cin`) sur un RIB, une quittance, une carte professionnelle |
| T06 | montants en texte (« 30 000,00 », « 1.250,50 DH ») et en nombre ; agrégats mensuels en objet `{"MM/AAAA": valeur}` ou en texte |
| T07 | dates en `jj/mm/aaaa` et en `jj/mm` |
| T08 | trois vocabulaires : amont (`nom_societe`, `siege_social`, `numero_cin_gerant`), moteur (`denomination_sociale`, `adresse_siege`, `cin`), libellés français de la carte grise ; après relecture, amont et moteur dans la même pièce |
| T09 | `raison_sociale` : titulaire du compte sur un relevé, société ailleurs |
| T10 | relecture : `source` REANALYSE, `fields` fusionnés, `reanalyses[].result.avant` et `apres` |
| T11 | contexte amont partiel : `businessData.civil.cin` vide pour une PM ; `declared` vide ; employeur déclaré « VAB » ; CSP « Retraité » indistincte |
| T12 | valeurs gabarits (nom « JOHN DOE », CIN de démonstration) |
| T13 | `extractionStatus` OK, PARTIAL ou FAILED |
| T14 | analyse non terminée ; dossier archivé (`actif = false`) |
| T15 | `agence` et `canal` vides |

## Scénarios (S)

Avec le résultat attendu sous les paramètres provisoires (majeure à partir de 0,20, mineure à partir de 0,08,
affichage à partir de 0,05) :

| N° | Scénario | Attendu |
| --- | --- | --- |
| S01 | demandeur inscrit (même CIN) | critique, 0 lien |
| S02 | société du dossier inscrite (même RC + tribunal) | critique |
| S03 | employeur = société inscrite (même ICE) | critique |
| S04 | employeur dont le gérant est inscrit | 1 lien, force 0,7 : majeure |
| S05 | RIB du demandeur porté aussi par un inscrit (2 porteurs) | 1 lien « même RIB », 0,9 : majeure |
| S06 | RIB porté par 5 personnes dont un inscrit | 0,9 × 0,63 ≈ 0,57 : majeure |
| S07 | gérant de 8 sociétés entre l'employeur et une société inscrite | 2 liens, 0,245 : majeure |
| S08 | liquidateur de 40 sociétés entre l'employeur et une société inscrite | 2 liens, 0,0559 : affiché, sans alerte |
| S09 | chemin fort de 3 liens | mineure au plus |
| S10 | chemin de 4 liens | gris « hors alerte », jamais d'alerte |
| S11 | gérant de l'employeur rapproché d'un inscrit par le nom et la ville seulement | plafonné à mineure, « homonymie à lever » ; levée « même personne » : majeure ; « homonyme écarté » : disparaît |
| S12 | employeur reconnu seulement par son nom | homonymie : mineure au plus |
| S13 | conjoint déclaré inscrit, même logement | foyer : 0,1, mineure, « même foyer qu'un inscrit » |
| S14 | même foyer et même RIB que le conjoint inscrit | argent au poids plein : 0,9, majeure |
| S15 | inscription qui désigne une victime | à 0 lien : critique ; au-delà : selon le paramètre (provisoire : propage) |
| S16 | B arrive avec le RIB de A, déjà relié ; puis l'ordre inverse | B relié à l'arrivée ; dans l'ordre inverse, B « nouvellement relié » |
| S17 | relecture qui change le CIN du demandeur | anciennes arêtes retirées ; état égal au lot |
| S18 | même châssis dans deux dossiers | incohérence « double financement », pas de lien |
| S19 | même RIB dans 3 dossiers en moins de 30 jours | signal « dossiers en rafale », force inchangée |
| S20 | employeur déclaré dans plus de 200 dossiers | propagation renvoyée à la nuit, noté |
| S21 | analyse non terminée | stocké, dessiné « en cours », sans contrôle ni alerte |
| S22 | dossier archivé | repris, marqué |
| S23 | alerte levée pour (dossier, inscrit), puis chemin d'une autre nature qui fait monter le niveau | ne revient pas ; rouvre avec le nouveau chemin |
| S24 | même apporteur ou même point de vente qu'un inscrit | dessiné, hors score |
