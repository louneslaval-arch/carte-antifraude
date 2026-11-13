*Plan de construction de la carte antifraude en temps réel. Repris du document de lancement du 11/11/2026 ; Claude Code tient à jour la colonne « État » et rien d'autre sans l'accord de Lounès.*

### État des étapes

| Étape | Contenu | Durée indicative | État |
| --- | --- | --- | --- |
| 1 | skills et cadre de travail | 1 séance | fait (11/11/2026), fusionné |
| A | remise à niveau, import contrôlé du kit et de la structure de Kamal | 1–2 j | partielle (13/11) : attend la mesure réelle (A.8) |
| B | socle des couches, lecture de la structure de Kamal, carte de correspondance | 3–4 j | partielle (13/11) : attend comparer_bases.py (kit du 11/11), ruff et mypy installés |
| C | générateur et serveur v2 fictifs, au format exact des types de Kamal | 2–3 j | à faire |
| D | c0 : versions brutes, miroir de la v2, collecteur | 2–3 j | à faire |
| E | c1 pièces et faits | 4–5 j | à faire |
| F | c2 identités | 5–7 j | à faire |
| G | c3 dossier, revenus, comptes, véhicules | 4–5 j | à faire |
| H | c5 graphe | 4–5 j | à faire |
| I | c6 contrôle réseau, alertes, propagation, nuit | 4–5 j | à faire |
| J | API temps réel | 4–5 j | à faire |
| K | pages | 7–10 j | à faire |
| L | PostgreSQL et déploiement | 4–5 j | à faire |
| M | jeton Tandem, notification de la v2, pseudonymisation | 3–4 j | à faire |
| N | performance (c4) et analytique (c7) | 6–8 sem. | à faire |

Les étapes A à K ne dépendent que des fichiers que Lounès dépose dans `import/` et des questions ouvertes indiquées. Premier essai réel possible à la fin de l'étape I.

### Règles communes à toutes les étapes

1. **Une étape = une couche = un module = une branche.** On ne touche jamais deux couches dans le même lot de modifications.
2. **Fictif d'abord, réel ensuite.** Chaque module est écrit et testé sur le jeu d'essai ; l'essai sur données réelles vient après le vert, et c'est Lounès qui le lance.
3. **Chaque couche se reconstruit entièrement depuis celle du dessous**, en une commande, sans état caché. Seules survivent aux reconstructions, dans des tables à part : décisions d'analyste, levées, exclusions, référentiels saisis à la main, identifiants attribués.
4. **Schéma versionné** : migrations numérotées, `schema_version`, application idempotente.
5. **Invariants après chaque construction** (`verifier.py`) : requêtes qui doivent rendre zéro ligne, comptages qui ne bougent pas sans raison.
6. **Rapport d'écart avant / après** (`comparer_bases.py` étendu à toutes les couches) : lu avant de valider une étape.
7. **Référence figée** : la copie de la base réelle de l'étape A, hors du dépôt, et ses chiffres (122 inscrits reliés, 16 300 réseaux, plus grand réseau de la liste noire à 17 nœuds, 301 chemins de retour). Ils ne bougent pas tant qu'une étape n'est pas censée les changer.
8. **Structure de Kamal d'abord** : pour ce qui vient de la v2 ou y retourne, ses entités, noms, clés, énumérations et formats (`docs/source_v2.md` § 7).
9. **Données personnelles** : règles absolues de `CLAUDE.md`.

### Étape A — Remise à niveau

**But.** Un dépôt sain, à jour du kit du 11/11, avec la structure de Kamal à portée et une référence chiffrée sur les vraies données.

**Préalables.** Étape 1 fusionnée ; `import/kamal_structure/`, `import/kit_2026-11-11/` et `import/reference/` déposés par Lounès ; réponse de Kamal sur le versionnement de sa structure (questions ouvertes, n°15).

**À faire.**
1. Vérifier que la mutation de `graphe.py` est annulée et que les tests passent.
2. **Contrôle de tout ce qui est importé** : `garde_donnees.py --fichiers` sur chaque fichier, puis relecture des chaînes littérales (noms, identifiants, exemples). Pour la structure de Kamal, vérifier en plus qu'aucune réponse d'API ni aucun dossier n'est présent (pas de dossier `api/`, pas de fichier de réponse). Chaque nom ou identifiant qui pourrait être réel est montré à Lounès par fichier et ligne, sans être recopié ; il tranche (exemple fictif à la place, ou valeur générique à garder). Même contrôle sur la notice du kit déjà versionnée.
3. **Structure de Kamal** : si Kamal est d'accord, la copier telle quelle dans `reference/v2/` (`schema/schema.prisma`, `schema/openapi_api_v1_export_metier.json`, `types/web_types.ts`, `types/engine-core_types.ts`, `reference/CONTRAT_TANDEM_AI.md`, `reference/business-data.schema.json`, `reference/tandem-results.schema.json`, `reference/champs_par_type_prod.csv`, `README.md`, avec les noms exacts trouvés dans le lot), avec `PROVENANCE.md` (nom et date du lot, liste des fichiers, empreintes SHA-256) ; réautoriser ces fichiers dans `.gitignore` et dans `outils/garde/fichiers_autorises.txt`. Sinon, elle reste dans `import/kamal_structure/` (ignoré) et seule la carte de correspondance de l'étape B est versionnée.
4. **Kit du 11/11** : importer sans modification ses scripts dans `pipeline/` (remplacer les versions du 22/10 ; ajouter `carte_globale.py`, `translitteration.py`, `geo_maroc.py`, `nettoyer_liste_noire.py`, `comparer_bases.py`, `charger_antifraude.py`, `rapport_antifraude.py`) ; noter dans le journal l'empreinte SHA-256 de chaque fichier importé.
5. **Référentiels** (villes, grands employeurs : raisons sociales et effectifs, pas de données personnelles, à confirmer par Lounès) : les ranger dans `reference/` et les réautoriser comme au point 3.
6. `jeu_essai/construire.sh` et `publier_carte.py` produisent aussi la carte globale. `attendu_kit.json` n'est régénéré que si chaque écart est expliqué par une nouveauté du kit (rôles datés, nettoyage des noms, R01n…), écart par écart dans le journal.
7. **Outils de développement**, à valider par Lounès (questions ouvertes, n°9) : `requirements-dev.txt` (pytest, ruff en vérification seule, mypy, hypothesis, mutmut 2.5.1 figé, pyright s'il est retenu). Aucune mise en forme automatique de tout le dépôt sans décision.
8. **Référence réelle** : préparer avec le skill `essai-donnees-reelles` la commande que Lounès lance dans `~/antifraude-donnees/` (construction de la base réelle avec le kit du 11/11, copie de référence `bl_rc_reference_2026-11-11.sqlite`, quatre chiffres).

**Tests écrits d'abord.** Le kit du 11/11 sur le jeu d'essai fictif : bilan attendu mis à jour, carte globale publiée et contrôlée (aucune identité dans la géométrie).

**Fini quand.** Tests verts ; garde verte sur tout le dépôt, ou constats tranchés par Lounès ; structure de Kamal en place (versionnée ou dans `import/`) ; Lounès a reproduit hors du dépôt : 122 inscrits reliés, 16 300 réseaux, plus grand réseau de la liste noire à 17 nœuds, 301 chemins de retour.

**Pièges.** Ne pas « améliorer » les scripts du kit à l'import : les changements viennent avec les couches. `exclusions_carte.json` (noms réels) reste à côté des données, hors du dépôt.

### Étape B — Socle des couches et lecture de la structure de Kamal

**But.** Un dépôt où l'on ne peut pas casser la base sans le voir, et où la structure de Kamal est lue par programme au lieu d'être recopiée.

**À faire.**
1. Arborescence (`docs/architecture_temps_reel.md` § 3.9) : `pipeline/normalisation/`, `pipeline/couches/`, `pipeline/regles/`, `flux/`, `schema/`, `tests/`, `jeu_essai/v2/`, `outils/v2/`.
2. Migrations : `schema/000_schema_version.sql` et un script d'application idempotent ; aucune modification de table à la main.
3. `construire.py` : `--jeu-essai`, `--base`, `--jusqua cN`, `--depuis cN`, `--dossier REF` (un seul dossier, comme le flux). Chaque couche expose `construire_tout(connexion)` et `traiter(connexion, ref)`, qui appellent les mêmes fonctions ; les règles s'écrivent sur une vue `perimetre` (tout en lot, le seul dossier en flux).
4. `verifier.py` et `invariants.yaml` : requêtes qui doivent rendre zéro ligne, comptages stables avec tolérance déclarée ; arrêt au premier écart ; sortie en comptages seulement.
5. `comparer_bases.py` (du kit) étendu : rapport d'écart table par table, couche par couche.
6. **Lecture de la structure de Kamal** (`outils/v2/`) :
   - `lire_prisma.py` : modèles, champs, types, champs facultatifs et listes, `@id`, `@unique`, `@@id`, `@@unique`, `@default`, `@map`, `@@map`, relations, énumérations → structure Python ;
   - `lire_types_ts.py` : interfaces, alias de types et unions de chaînes (énumérations) de `web_types.ts` et `engine-core_types.ts` → structure Python ;
   - `carte_correspondance.py` : écrit `docs/correspondance_v2.md` (partie générée : modèles → miroir, types d'échange → générateur et collecteur, énumérations → valeurs reprises, vocabulaire des clés du README § 4 → `ref_cle_canonique`, proposition du README § 7 → tables de c1) ; la partie écrite à la main (nos ajouts, chacun justifié) est conservée d'une génération à l'autre.
7. **Vérification complète** `outils/verifier_tout.sh` : garde, ruff (E9, F), mypy sur `pipeline/normalisation/` et `outils/v2/`, pytest, construction du jeu d'essai, `verifier.py`, carte de correspondance à jour. Configuration de pytest : chemins des tests, dossiers exclus (`.venv`, `.verif`, `mutants`, `jeu_essai/sortie`, `import`).
8. Choix à signaler : pas d'intégration continue distante (aucun dépôt distant) ; le crochet git et `verifier_tout.sh` en tiennent lieu.

**Tests écrits d'abord.** Base vide → migrations → `verifier.py` vert ; migration rejouée sans effet ; un invariant violé exprès fait échouer `verifier.py` ; `--depuis` ne reconstruit que les couches demandées ; les lecteurs de structure sur de petits extraits fictifs couvrant chaque construction de `schema.prisma` et des types ; **dérive** : si les fichiers de Kamal changent, la carte de correspondance générée diffère et le test échoue jusqu'à régénération relue ; propriétés (hypothesis) sur les premières fonctions de normalisation reprises du kit.

**Fini quand.** `.venv/bin/python construire.py --jeu-essai && .venv/bin/python verifier.py` vert sur une base vide, en une commande ; `verifier_tout.sh` vert ; `docs/correspondance_v2.md` couvre 100 % des modèles, champs et énumérations de Kamal (chacun : repris, dérivé, ou non utilisé avec la raison).

### Étape C — Générateur et serveur v2 fictifs

**But.** Faire arriver des dossiers v2 indiscernables, par leur forme, de ceux de Kamal, avec leurs pièges et des chemins connus d'avance, sans Kamal ni donnée réelle.

**Préalables.** Étape B (lecteurs de structure).

**À faire.**
1. **Modèles d'échange** : modèles pydantic (déjà une dépendance de FastAPI) de `DossierDetail` et des objets qu'il contient, générés ou vérifiés depuis `web_types.ts` par `outils/v2/` ; un test compare champ par champ les modèles et les types de Kamal.
2. `jeu_essai/v2/generer_dossiers.py` : dossiers au format exact de `GET /api/dossiers/:ref`, liste au format de `GET /api/dossiers` (`items`, `total`, `counts`) ; graine fixe ; les 14 types de pièces de la v2 ; clés de `fields` tirées de l'inventaire de Kamal (`champs_par_type_prod.csv`), par type et par source ; valeurs d'énumération de ses types ; tous les pièges T01 à T15 et scénarios S01 à S24 du skill `jeu-essai-v2` ; branché sur le registre et la liste noire fictifs de `jeu_essai/generer.py` pour que les chemins attendus existent ; `verite_v2.json` (pour chaque dossier : mentions, identités, liens, niveau et force attendus, incohérences).
3. `jeu_essai/v2/serveur_v2.py` : mêmes routes, paramètres, réponses et erreurs que la v2 (`POST /api/auth/login`, `GET /api/dossiers` avec `limit`, `offset`, `archives`, `GET /api/dossiers/:ref`, et le détail d'un contrôle si la v2 l'expose) ; chronologie scénarisée (arrivées, relectures, rejeux, corrections, retraits de pièce) avec horloge réglable ; envoi facultatif de la notification signée vers `POST /api/flux/v2`.
4. Volumes : 1 000 dossiers fictifs sur le grand registre fictif (61 043 sociétés).

**Tests écrits d'abord.** Les modèles refusent un dossier mal formé ; chaque piège et chaque scénario est présent au moins une fois ; deux générations avec la même graine sont identiques ; la répartition des clés par type suit l'inventaire de Kamal ; garde verte sur tout ce qui est généré.

**Fini quand.** 1 000 dossiers servis comme par la v2, 100 % valides au regard des types de Kamal ; vérité attendue couvrant chaque scénario.

### Étape D — c0 : versions brutes, miroir de la v2, collecteur

**But.** Recevoir chaque version de chaque dossier, la garder telle quelle, la ranger dans un miroir identique à la base de Kamal, ne rien perdre, ne rien doubler.

**À faire.**
1. `c0_export` et `c0_dossier_brut` (`docs/couches.md`, c0) : chaque version reçue, avec son empreinte.
2. **Miroir de la v2** : migrations générées depuis `schema.prisma` par `outils/v2/` (une version SQLite, une version PostgreSQL), mêmes noms de tables et de colonnes que la base de Kamal, mêmes clés, mêmes contraintes d'unicité, énumérations en contrôle de valeurs. Rempli à partir de `DossierDetail` pour ce que l'API expose ; les modèles que l'API n'expose pas (par exemple `IntakeMessage`, `IndicateurDossier`, `Employeur`, `BlacklistEntry`) sont créés vides, prêts pour un accès direct.
3. Tables du temps réel : `flux_source`, `flux_curseur`, `flux_travail` (`docs/architecture_temps_reel.md` § 5).
4. `flux/collecteur.py` en scrutation (compte de service en variables d'environnement, noms proposés : `CARTE_V2_URL`, `CARTE_V2_COMPTE`, `CARTE_V2_SECRET`) ; `flux/file.py` ; route `POST /api/flux/v2` prête mais inactive (charge utile `{ref, updatedAt, analysisStatus, trigger}`, noms de la v2 ; signature HMAC SHA-256 du corps ; horodatage à 5 min près ; sans effet si déjà reçue).

**Tests écrits d'abord.** Le miroir contient chaque modèle et chaque champ de `schema.prisma`, et rien d'autre ; chaque champ de `DossierDetail` a sa place déclarée (colonne du miroir, ou version brute seulement) ; deux passages identiques n'ajoutent aucune ligne ; un dossier modifié ajoute une version, l'ancienne reste intacte, le miroir montre la dernière ; serveur v2 coupé : nouvelles tentatives à intervalle croissant, aucune perte ; liste non triée : relecture complète toutes les 5 min ; analyse non terminée : stockée « en cours » ; dossier archivé : repris et marqué ; notification en double sans effet ; signature fausse ou horodatage trop vieux refusés ; journaux techniques sans contenu de dossier.

**Fini quand.** Collecteur branché sur le serveur fictif, scénario complet sans perte ni doublon ; miroir vérifié sur SQLite (et sur PostgreSQL si Lounès l'a installé en local, questions ouvertes n°18).

### Étape E — c1 pièces et faits

**Préalables.** `import/v2/extraire_json_v2.py` et `profil_json.py`, contrôlés.

**À faire.** c1 lit le miroir (`fields` de la pièce), jamais la réponse d'API : la couche ne dépend donc pas de la source. Tables de `docs/couches.md`, c1 : d'abord les tables enfants que propose le README de Kamal (§ 7 : opérations et personnes), avec ses noms et ses clés ; puis nos ajouts (faits normalisés, mois de relevé, identifiants bruts, relectures), chacun inscrit dans la carte de correspondance. Découper `extraire_json_v2.py` entre `pipeline/normalisation/` (montants, dates, CIN, RIB, aplatissement) et `pipeline/couches/c1_faits.py`, écrit d'emblée en `traiter(ref)` et `construire_tout()`. `ref_cle_canonique` par type de pièce, dont la cible est le vocabulaire « moteur » de la v2 (correspondance du README § 4, clés des types de Kamal), versionnée ; liste d'exclusion (clés inventées, champs de CIN hors pièce CIN, gabarits).

**Tests écrits d'abord.** Un test par forme de valeur et par piège (T01 à T13) ; propriétés : `montant()` et `date_iso()` ne lèvent jamais d'exception sur une chaîne quelconque et sont stables (normaliser deux fois revient à normaliser une fois) ; toute clé de l'inventaire de Kamal a une clé canonique ou figure au rapport des clés inconnues ; flux = lot sur c1.

**Fini quand.** Invariants c1 verts ; Lounès retrouve sur les deux dossiers réels de l'échantillon : 182 valeurs, 160 retenues, 252 opérations lues, 2 reconstituées, 9 mentions de personnes.

### Étape F — c2 identités

**But.** Une fiche maître par personne et par société, qui réunit liste noire, registre, dossiers `af_*` et dossiers v2.

**À faire.** `docs/couches.md`, c2. Rattachement par clé forte (CIN valide hors gabarit ; RC + tribunal ; ICE ; n° d'affiliation CNSS pour un employeur), sinon fiche propre au dossier avec un identifiant attribué une fois et conservé ; règles R01–R11 et AF01–AF20 reprises telles quelles sur `perimetre` ; homonymies jamais fusionnées ; levées attachées au couple. **Alignement** : la liste noire est rangée dans la structure de `BlacklistEntry` de Kamal (types CLIENT, EMPLOYEUR, GERANT, BENEFICIAIRE, TIERS_BANCAIRE, ZONE ; champs de son modèle, plus le statut daté actif ou retiré de la décision n°4 s'il manque) ; les employeurs suivent la clé et la structure de son référentiel `Employeur` (ICE, graphies lues), qui deviendra une source dès l'accès direct.

**Tests écrits d'abord.** Cas fictifs : même personne en latin et en arabe ; homonymes à CIN différents ; CIN à lettre parasite ; société sous deux dénominations ; CIN partagé par deux noms incompatibles (pas de fusion, signalement) ; décision « homonyme écarté » qui survit à une reconstruction ; identifiants stables d'une construction à l'autre ; chargement de la liste noire fictive dans la structure `BlacklistEntry` sans perte ; flux = lot sur c1 et c2.

**Fini quand.** Sans dossiers v2, la référence ne bouge pas (Lounès : 122, 16 300, 17, 301) ; avec eux, chaque nouveau lien du rapport d'écart s'explique par une mention v2.

### Étape G — c3 dossier, revenus, comptes, véhicules

**À faire.** `docs/couches.md`, c3. L'en-tête de dossier reprend les champs et les valeurs du modèle `Dossier` de Kamal (`personType`, `productType`, `paymentMode`, `category`, `verdict`, `csp`, `businessData`…). Incohérences qui croisent les dossiers ou le registre ; les 55 contrôles de la v2 ne sont pas recalculés : ils se lisent dans le miroir. Signal « dossiers en rafale » ; même châssis : incohérence « double financement ».

**Tests écrits d'abord.** Chaque incohérence, avec la tolérance au bord ; relevé non relu : ni opération ni incohérence de flux ; jamais de comparaison à une valeur par défaut (« VAB ») ; flux = lot.

**Fini quand.** Fiche client complète sur le jeu d'essai ; chaque incohérence pointe ses deux faits.

### Étape H — c5 graphe

**À faire.** `docs/couches.md`, c5, et `.claude/rules/score.md` : barème n°23, coût de taille √(2/n) lu dans `c5_compteur` au moment du calcul, fiabilités, identifiants partagés en nœuds (y compris les inscriptions de type TIERS_BANCAIRE et ZONE) ; `flux/graphe_vivant.py` (tableaux en mémoire, recherche bornée à 3 liens pour les alertes, chemins de 4 liens et plus à la demande) ; liste des modifications ; positions provisoires (angle d'or et décalage déterministe ; bande « arrivées du jour » ; ville de l'adresse qui fait foi) ; `chaines_dessin.py` et `carte_globale.py` lisent `c5_*`.

**Tests écrits d'abord.** Petit graphe fait à la main : table des coûts (n = 2, 3, 5, 8, 40, 500) ; exemples 0,245 (majeure) et 0,0559 (affiché sans alerte) ; scénarios S04 à S14 ; flux = lot sur c5, dans l'ordre et dans un ordre tiré au hasard ; propriété : ajouter puis retirer un dossier rend le graphe identique.

**Fini quand.** Avant branchement des dossiers v2, tous les chemins de la référence sont retrouvés et chaque différence de chemin ou de force s'explique par le barème n°23 ou le coût n°21 (rapport d'écart lu avec Lounès) ; flux = lot vert.

### Étape I — c6 contrôle réseau, alertes, propagation, nuit

**Préalables.** Questions ouvertes n°2, 3, 7, 8 et 17 tranchées ou laissées à leur valeur provisoire, par écrit.

**À faire.** `docs/couches.md`, c6 ; `docs/architecture_temps_reel.md` § 3.3 (étapes 6 à 8) et § 3.7 (nuit). `c6_controle_reseau` (instantané des entrées, version des paramètres), `c6_alerte`, `c6_levee`, `c6_version_parametres` (valeurs provisoires de `docs/decisions.md`), `sortie_tandem` ; les 55 contrôles de la v2 se lisent dans le miroir (`AnalysisControl` ou son nom exact). **Format de sortie** : le contrôle « lien avec la liste noire » est rendu comme un élément de `controls[]` de la v2 (mêmes champs, mêmes valeurs d'énumération ; identifiant, famille et correspondance des niveaux convenus avec Kamal), le détail des chemins dans son champ de détails ; les mesures (force, inscrits atteints, distance) au format d'`IndicateurDossier`. Propagation : 3 liens au plus ; au-delà de 200 dossiers touchés, renvoi à la nuit. Une alerte ne baisse jamais en journée. `flux/traiteur.py` (boucle) et `flux/nuit.py`.

**Tests écrits d'abord.** Les tests 1 à 9 de `docs/architecture_temps_reel.md` § 7 (le 10, époque, à l'étape J) ; la sortie est valide au regard des types de Kamal et ne contient aucun nom de tiers.

**Fini quand.** Tests 1 à 9 verts, dont le délai : 95 % des dossiers sous 5 s sur le grand jeu d'essai plus 1 000 dossiers fictifs ; premier essai réel possible (Lounès : traiteur sur le Mac, scrutation de la v2 réelle avec un compte de service, données hors du dépôt).

### Étape J — API temps réel

**Préalables.** Droits du rôle AGENCE tranchés (n°1) ; sens du retour vers Tandem connu (n°8).

**À faire.** `docs/architecture_temps_reel.md` § 3.5 et § 6 : époques, `flux_indice`, modifications numérotées, flux d'événements, identités des nœuds vivants par les mêmes routes, routes nouvelles, rôle `TANDEM`, colonne `epoque` du journal, droits AGENCE selon la décision. Les routes échangées avec la v2 et Tandem (notification, contrôles) suivent les conventions de l'API de Kamal (noms de champs, pagination `limit` et `offset`, réponses `{items, total}`) ; les routes des analystes gardent les nôtres. FastAPI : si une montée de version est décidée (n°14), le skill officiel livré avec le paquet devient disponible, après contrôle.

**Tests écrits d'abord.** Rôles sur chaque route (DIRECTION sans nom, AGENCE selon la décision, TANDEM sans nom de tiers) ; non-fuite sur les modifications, les événements et la sortie Tandem ; reprise du flux d'événements (`Last-Event-ID`) ; 409 sur une époque close ; test 10 du § 7 côté API.

**Fini quand.** Tests de rôle et de non-fuite verts ; contrat d'API (OpenAPI) écrit et vérifié.

### Étape K — Pages

**Préalables.** Skill d'essai dans le navigateur contrôlé et installé ; décision sur une éventuelle bibliothèque de dessin copiée dans le dépôt (n°11 ; par défaut : SVG et Canvas natifs).

**À faire.** `.claude/rules/pages.md` : carte globale, carte par inscrit, vue dossier ; deux vues synchronisées (Maroc, 12 régions intégrées ; réseau centré) ; curseur de force ; filtres et marquages ; bandeau d'alertes ANALYSTE ; `EventSource` ; politique de sécurité du contenu « default-src 'self' ».

**Tests écrits d'abord.** Dans le navigateur : connexion ; arrivée en direct d'un dossier du serveur fictif ; DIRECTION sans nom ; aucune requête hors de l'origine ; rechargement sur changement d'époque.

**Fini quand.** Ces essais verts sur le jeu d'essai.

### Étape L — PostgreSQL et déploiement

**Préalables.** Feu vert de la conformité et déclaration CNDP ; hébergement au Maroc choisi ; skill PostgreSQL contrôlé (partie propre au moteur seulement).

**À faire.** Mêmes migrations sur PostgreSQL ; construction complète sur les deux moteurs et comparaison table par table (nombre de lignes, empreintes de contenu) ; miroir de la v2 identique à la base de Kamal, donc alimentable par lecture directe de ses tables (décision n°12) sans traduction ; file en base (`FOR UPDATE SKIP LOCKED`, réveil par `LISTEN/NOTIFY`) ; journal en ajout seul ; conteneurs `api`, `traiteur`, `postgres`, `nginx` ; sauvegardes ; secrets en variables d'environnement.

**Fini quand.** Construction identique sur les deux moteurs ; un essai de lecture directe sur une copie fictive du schéma de Kamal remplit le miroir sans transformation.

### Étape M — Jeton Tandem, notification de la v2, pseudonymisation

**Préalables.** Notification signée ou table d'événements sortants côté v2 (Kamal) ; décision sur le mode de pseudonymisation (n°12).

**À faire.** Jeton de service du rôle `TANDEM` (portée, durée, rotation) ; notification de la v2 branchée (la scrutation reste en filet de sécurité toutes les 15 min) ; pseudonymisation du stockage (prompt « version sécurisée », étape 7).

**Fini quand.** Délai de 15 s de bout en bout sur le serveur fictif ; tests de la pseudonymisation.

### Étape N — Performance (c4) et analytique (c7)

**Préalables.** Historique EQDOM sur 36 mois.

**À faire.** `docs/couches.md`, c4 et c7 ; les indicateurs suivent le format d'`IndicateurDossier` (valeur, fiabilité CERTAINE, EXTRAITE ou FRAGILE) et des constats notés de la synthèse de la v2 (rang, effectif, force, fiabilité, score).

**Pièges.** Le verdict Tandem n'est jamais la cible ; variables connues au moment de la décision seulement ; ni sexe ni nationalité ; rien sous 5 clients.
