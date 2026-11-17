# Contenu des couches c0 à c7

SEVEN · réseaux de fraude EQDOM · 11/11/2026 · version du dépôt. Ce qui va dans chaque couche, les pièges, les tests et les invariants. L'ordre de construction est dans `docs/plan_construction.md` ; l'alignement sur la v2 de Kamal dans `docs/source_v2.md` § 7.

## c0 — brut et miroir de la v2

**But.** Recevoir les dossiers v2 et les garder tels quels, avec leur empreinte, pour pouvoir tout rejouer ; les ranger dans un miroir identique à la base de Kamal.

**Tables.** `c0_export` (un passage de collecte : date, source, mode, nombre de dossiers, version du serveur v2) ; `c0_dossier_brut` (ref, `updatedAt`, empreinte SHA-256 du JSON, JSON complet, passage, reçu le) ; le miroir de la v2 (`docs/source_v2.md` § 7.1).

**Pièges.** Ne rien interpréter à ce stade : pas de normalisation, pas de filtre. Un dossier relu par la v2 change d'`updatedAt` : on garde toutes les versions (ligne nouvelle si l'empreinte change) ; le miroir montre la plus récente. Les dossiers écartés (`actif = false`) sont aussi récupérés (`archives=true`), marqués comme tels.

**Tests.** Deux passages sur le même jeu : aucune ligne ajoutée. Un dossier modifié : une version de plus, l'ancienne intacte. Le miroir correspond à `schema.prisma`.

**Invariants.** Une empreinte = un JSON ; chaque ref de la liste a au moins une version ; aucune version orpheline de passage ; le miroir de chaque ref est la projection de sa dernière version.

## c1 — pièces et faits extraits

**But.** Chaque valeur lue dans une pièce devient une ligne, normalisée, avec son origine.

**Source.** Le miroir (`fields` de la pièce, relectures), jamais la réponse d'API.

**Tables.**
- Tables enfants proposées par le README de Kamal (§ 7) pour les opérations et les personnes, avec ses noms et ses clés. À défaut de nom chez lui : `c1_releve_operation` (pièce, n° → date complétée avec l'année, date de valeur, libellé, débit, crédit, nature « lue » ou « reconstituée par l'amont ») et `c1_mention_personne` (pièce, rang, rôle → nom tel que lu, CIN, date de naissance, nationalité, part, adresse ; rôles : titulaire de la CIN, employé, pensionné, assuré, gérants, dirigeants, associés, titulaire du compte, acheteur, titulaire de la quittance).
- Nos ajouts : `c1_fait` (clé brute aplatie, clé canonique = clé moteur de la v2, valeur brute, texte normalisé, nombre, date, origine amont, relue ciblée ou fusion, statut normal, clé inventée, champ CIN hors CIN ou gabarit) et la vue `c1_fait_retenu` (une valeur par pièce et clé canonique) ; `c1_releve_mois` (pièce, année, mois → soldes, totaux, agrégats amont « MM/AAAA » : salaire, échéances de crédit) ; `c1_mention_societe` (pièce, rôle → nom, RC, tribunal, ICE, n° d'affiliation ; société du RC et des statuts, employeur, vendeur et concessionnaire, banque) ; `c1_identifiant_brut` (pièce, type, valeur normalisée, porteur) ; `ref_cle_canonique` (type de pièce, clé brute → clé moteur), saisie à partir du README de Kamal et versionnée.

**Reprise de `extraire_json_v2.py` (11/11).** Constantes `CANON`, `CANON_PAR_TYPE`, `CLES_INVENTEES` (`^(remeration|revelation)\.`), `GABARITS` ; fonctions `montant()`, `date_iso(v, annee)`, `cin_norm()`, `rib_norm()`, `aplatir()` ; ses tables `v2_*` deviennent les tables ci-dessus.

**Pièges.** Dates d'opération `jj/mm` sans année ; un relevé à cheval sur décembre et janvier : l'année vient de `mois[].annee`, jamais de la date du jour. Montants en texte (« 30 000,00 », « 1.250,50 DH ») : une seule fonction `montant()`, testée sur toutes les formes rencontrées. Clé plate `vehicule.marque` et objet `vehicule.marque` : dédoublonner sur (clé, valeur). `raison_sociale` : correspondance propre au type de pièce. Opération reconstituée par l'amont : jamais comptée comme une opération lue (ni dans les tiers bancaires ni dans les flux).

**Tests.** Un test par forme de valeur et par piège ; sur les deux dossiers réels de l'échantillon, contrôlés par Lounès hors du dépôt : 182 valeurs, 160 retenues, 252 opérations lues, 2 reconstituées, 9 mentions de personnes.

**Invariants.** Toute opération a une date ou est marquée reconstituée ; tout montant de `c1_releve_mois` est numérique ; toute clé hors `ref_cle_canonique` figure au rapport des clés inconnues au lieu d'être acceptée en silence ; aucune ligne de fait sans pièce.

## c2 — tiers et identités

**But.** Une fiche maître par personne et par société, qui réunit la liste noire, le registre du commerce, les dossiers `af_*` et les dossiers v2.

**Tables.** `c2_personne`, `c2_societe` : identifiant stable (dérivé de la clé la plus forte, CIN ou RC + tribunal, sinon attribué une fois et conservé dans `c2_identifiant_attribue`) ; `c2_mention` : chaque apparition (annonce légale, pièce `af_*`, pièce v2, inscription en liste noire) rattachée à sa fiche, avec la règle de rattachement ; `c2_identifiant` : CIN, RC + tribunal, ICE, RIB, n° CNSS, n° d'affiliation, n° de pension, châssis, immatriculation, INPE, chacun avec sa source et sa date ; `c2_alias` (graphies, latin et arabe via `translitteration.py`) ; `c2_adresse` (datée, sourcée) ; `c2_role` (gérant, associé avec parts, dirigeant, salarié, titulaire du compte, acheteur ; daté) ; `c2_correspondance` : reprend telles quelles les règles R01–R11 et AF01–AF20 et leurs statuts (alerte, homonymie, confirmé, écarté), `decision_analyste` intacte ; `ref_regle_survie` : pour chaque attribut, la source qui l'emporte (décision n°16 pour l'adresse ; CIN de la pièce CIN plutôt que CIN cité ailleurs ; nom de la CIN plutôt que nom du relevé…). Liste noire dans la structure de `BlacklistEntry`, employeurs selon le référentiel `Employeur` (`docs/source_v2.md` § 7.6).

**Pièges.** Fusion irréversible : on ne fusionne automatiquement que sur une règle « certain » (même CIN valide, même RC + tribunal) ; tout le reste passe par la file d'homonymies ; une fusion se défait en supprimant la correspondance, sans perdre les mentions. CIN partagé par deux noms incompatibles (1 457 cas relevés dans le registre) : pas de fusion, signalement. Valeurs gabarits (nom « JOHN DOE », CIN de démonstration) et faits au statut non normal : exclus des règles d'identité. Identifiants stables jamais renumérotés, sinon les décisions d'analyste et les liens de la carte se perdent.

**Tests.** Cas fictifs : même personne en latin et en arabe ; homonymes à CIN différents ; CIN à lettre parasite ; société sous deux dénominations après un changement publié ; décision « homonyme écarté » qui survit à une reconstruction.

**Invariants.** Les chiffres de référence ne bougent pas (122, 16 300, 17, 301) tant que les dossiers v2 ne sont pas branchés ; ensuite, le rapport d'écart explique chaque nouveau lien par une mention v2. Une fiche = au plus un CIN valide ; aucune correspondance « certain » entre deux fiches non fusionnées.

## c3 — dossier, revenus, comptes, véhicules

**But.** La fiche client complète et les premières incohérences entre pièces.

**Tables.** `c3_dossier` : en-tête au format du modèle `Dossier` de la v2 (`personType`, `productType`, `paymentMode`, `category`, `verdict`, `csp`, contexte `businessData`) ; colonnes prévues mais vides pour montant, durée, apport, mensualité, statut final, agence, canal, qui se rempliront quand Kamal les enverra. `c3_partie_dossier` (rôle de chaque fiche dans le dossier). `c3_revenu` en deux natures : déclaré (contexte EQDOM) et vérifié (bulletin, attestation, pension, salaire repéré sur le relevé), avec la pièce source. `c3_charge` : échéances de crédit repérées sur le relevé, crédits prélevés à la source du bulletin. `c3_compte` (RIB normalisé, banque, titulaire) et `c3_operation` (vue sur les opérations lues, avec contrepartie normalisée depuis le libellé et type d'opération : virement, prélèvement, carte, chèque, espèces, frais). `c3_vehicule` (châssis, immatriculation, marque, modèle, neuf ou occasion, prix de la proforma). `c3_incoherence` : salaire du bulletin différent du virement du relevé (avec tolérance), adresse de la CIN différente de la quittance ou du relevé, employeur de l'attestation absent du registre ou radié, RIB vu dans un autre dossier sans lien, même châssis dans deux dossiers (« double financement »), dossiers en rafale.

**Pièges.** Ne pas recalculer ce que la v2 calcule : les 55 contrôles se lisent dans le miroir ; les incohérences ajoutées ici sont celles qui croisent les dossiers ou le registre, ce que la v2 ne fait pas. Le revenu déclaré est souvent vide ou par défaut (« VAB » pour l'employeur) : ne jamais comparer à une valeur par défaut. Contrepartie normalisée depuis un libellé : un indice, jamais une identité (même règle que les tiers bancaires AF11).

**Tests.** Cas fictifs pour chaque incohérence, avec la tolérance au bord ; relevé non relu : pas d'opération, pas d'incohérence de flux.

**Invariants.** Chaque revenu vérifié pointe vers une pièce ; aucune incohérence sans les deux faits qui la fondent.

## c4 — performance (historique EQDOM)

`c4_contrat`, `c4_echeance`, `c4_mouvement`, `c4_etat_mensuel` (avec classe BAM et étape IFRS 9) ; rapprochement dossier ↔ contrat. Attend l'historique EQDOM sur 36 mois (étape N).

## c5 — graphe

**But.** Un seul graphe pour le registre, les dossiers et la liste noire ; les chemins de `chaines_dessin.py` et la carte globale en sortent.

**Tables.** `c5_noeud` : fiches (personne, société) et identifiants partagés (RIB, adresse normalisée, n° d'affiliation de l'employeur, châssis, concessionnaire, cabinet déposant ; inscriptions de type TIERS_BANCAIRE et ZONE). `c5_arete` : type, dates de début et de fin, poids de départ (barème n°23), fiabilité, règle, source (dossier, pièce, version). `c5_compteur` : taille n de chaque nœud pour le coût √(2/n). `c5_composante`, `c5_chemin` (départ, cible inscrite, longueur, force, niveau, nature découverte, même lot ou même dossier), `c5_mesure` par dossier (identifiants partagés, taille de composante, distance à la liste noire, force du meilleur chemin). `chaines_dessin.py` et `carte_globale.py` lisent désormais `c5_*`.

**Pièges.** Un identifiant très partagé (grand employeur, domiciliataire, banque) écrase le graphe : le coût de taille et la liste des grands employeurs s'appliquent aussi aux nouveaux nœuds (RIB d'un concessionnaire, adresse d'un centre d'affaires). À partir de 4 liens, le chemin reste affiché mais ne déclenche pas d'alerte ; la limite est un paramètre, pas une constante.

**Tests.** Petit graphe fictif dont on connaît à la main les chemins et leurs forces.

**Invariants.** Avant branchement des nouveaux identifiants : tous les chemins de la référence retrouvés, chaque différence de force expliquée par le barème n°23 ou le coût n°21. Après : chaque nouveau chemin a au moins une arête issue d'un dossier v2 ou d'un nouvel identifiant, listée dans le rapport.

## c6 — contrôles, alertes, journal

**But.** Le contrôle à chaque dossier et la passe de nuit (décision n°9).

**Tables.** Les 55 contrôles de la v2 se lisent dans le miroir (résultat, criticité, escalade, détails), sans être recalculés. `c6_controle_reseau` : le contrôle « lien avec la liste noire » (niveau, force du meilleur chemin, trois meilleurs chemins, inscrits atteints), avec l'instantané des valeurs utilisées et la version des paramètres. `c6_alerte` (émise, destinataire, état), `c6_levee`, `c6_decision_analyste` (existante, migrée), `c6_journal_consultation` (passé du navigateur à une table), `c6_version_parametres` (barème, coût, seuils, limites de longueur, date). `sortie_tandem` au format de la v2 (`docs/source_v2.md` § 7.7).

**Pièges.** Une alerte ne réapparaît pas après qu'un analyste l'a levée : la levée est attachée au couple (dossier, inscrit), comme les homonymies. Une alerte ne baisse jamais en journée.

**Tests.** Rejouer deux nuits fictives : un dossier relié la deuxième nuit seulement donne une alerte ; une alerte levée ne donne pas de nouvelle alerte la nuit suivante ; et les tests de `docs/architecture_temps_reel.md` § 7.

## c7 — analytique

`c7_indicateur` : dictionnaire versionné des définitions, au format d'`IndicateurDossier` (valeur, fiabilité CERTAINE, EXTRAITE ou FRAGILE) ; `c7_table_analyse` : une ligne par dossier au moment de la décision, plus le défaut à 12 mois ; `c7_agregat`. Analyse par génération d'octroi, puis premiers scores. Le verdict Tandem n'est jamais la cible ; les variables sont celles connues au moment de la décision, jamais recalculées après coup.

**Fait en avance (17/11/2026, statistiques des dossiers)** : `c7_indicateur` (dictionnaire de 19 indicateurs, version 1 : nom, libellé, définition, formule, source, unité ; `IndicateurDossier` de la v2 décrit une valeur par dossier, pas une définition, voir `docs/correspondance_v2.md`), `c7_variable_dossier` (une ligne par dossier, dernière version : variables dérivées de c1, c3 et du miroir, NULL quand elles ne se calculent pas) et `c7_agregat` (cases par indicateur, tranche de filtre et découpage, secret primaire et secondaire, fourchettes de Wilson). Commande : `stats_dossiers.py`. Reste pour l'étape N : `c7_table_analyse`, le défaut à 12 mois (c4), l'analyse par génération d'octroi.
