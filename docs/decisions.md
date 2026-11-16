# Carte antifraude EQDOM : décisions de cadrage

SEVEN · réseaux de fraude EQDOM · séance de questions avec Lounès du 21/10/2026 · mise à jour du 11/11/2026 (décisions du 09/11 sur la pondération des liens, section 8). Version du dépôt, sans aucune donnée réelle. Ces décisions fixent ce que l'outil doit faire ; elles ne changent que sur décision de Lounès.

## 1. Usage

1. **Un outil de production pour EQDOM**, avec trois usages : vérifier qu'un demandeur n'appartient pas à un réseau de fraude ; retrouver à tout moment la fiche d'un client ; suivre des statistiques sur les profils des demandeurs.
2. **Qui est fraudeur.** Seules la liste noire et les fraudes confirmées par la cellule fraude marquent une personne comme fraudeuse. Un verdict Tandem reste un signal, jamais une étiquette.
3. **Toute inscription compte.** Une personne inscrite en liste noire garde ce statut, quel que soit le motif de l'inscription. Le contrôle cherche les liens entre le client et une personne inscrite : par son employeur (ses dirigeants au registre du commerce), par ses relevés bancaires, etc.
4. **Liste de référence : celle du 03/08/2026.** Chaque inscription porte un statut daté, actif ou retiré. Une inscription retirée reste visible dans l'historique de la fiche, mais ne compte plus pour les liens. À valider par la Direction des Risques.

## 2. Liens et réseau

5. **Trois niveaux de lien :** certain (même CIN, ou même RC et même tribunal) : alerte automatique ; probable (même nom normalisé, plus un élément qui le confirme : date de naissance, ville ou même société) : statut provisoire « homonymie », sans alerte automatique ; nom seul : ce n'est jamais un lien. *Assouplie le 09/11 (n°22) : un chemin qui passe par une homonymie non levée donne au plus une mention mineure.*
6. **Le statut « homonymie »** ne s'applique qu'aux liens probables. Seul un analyste antifraude peut le lever, avec une justification : « même personne » (le lien devient certain) ou « homonyme écarté » (le lien sort des contrôles). La décision reste attachée au couple client et personne inscrite, pour que le même homonyme ne revienne pas.
7. **On suit les rebonds.** Quand on cherche un client, on voit tout son réseau, pas seulement ses liens directs. *Précisée le 09/11 (n°20) : l'affichage n'a pas de limite de longueur, mais seuls les chemins de 3 liens au plus déclenchent une alerte.*
8. **Poids et force.** Le poids d'une arête est le poids de départ de son type, multiplié par la rareté de l'élément partagé. La force d'un chemin est le produit des poids de ses arêtes. Les arêtes trop faibles sont masquées : un curseur règle le seuil d'affichage ; les grands employeurs, les adresses de domiciliation et les autres éléments très partagés s'effacent ainsi d'eux-mêmes. Les poids et le seuil se règlent en rejouant les fraudes confirmées avec la cellule fraude. *Fixés le 09/11 : barème des liens (n°23) ; coût de taille √(2/n) sur les nœuds traversés, à la place de la rareté (n°21) ; la liste des grands employeurs reste une source de la taille d'un employeur.*
9. **Le contrôle tourne à deux moments :** à chaque nouveau dossier, il renvoie à Tandem une alerte « lien avec la liste noire », avec la force du meilleur chemin et les trois chemins les plus forts ; chaque nuit, il repasse sur toute la base et fait remonter à la cellule fraude les clients nouvellement reliés. Le sort des clients déjà financés qui remontent est une décision d'EQDOM. Mise en œuvre : `docs/architecture_temps_reel.md`.

## 3. Accès

10. **Trois niveaux d'accès :** cellule fraude : tout (fiche, réseau, liens avec la liste noire, homonymies, alertes Tandem, pièces) ; autres utilisateurs (agences, service client, Direction des Risques) : identité, coordonnées et historique des dossiers, sans rien sur la liste noire, les liens ou les alertes ; statistiques : uniquement des chiffres agrégés, jamais une personne identifiable. Chaque ouverture de fiche est enregistrée : qui, quand, quelle fiche. Les profils et leurs droits sont à fixer avec la direction informatique et la conformité d'EQDOM.

## 4. Données

11. **Périmètre :** tous les dossiers Tandem, avec les données extraites des pièces, plus l'historique clients d'EQDOM sur 36 mois, sans les pièces : identité, coordonnées, employeur, RIB et dossiers.
12. **En production, flux direct depuis la base Tandem**, mis en place par Kamal. La lecture par le navigateur ne sert qu'au prototype.
13. **Le prototype tourne sur les données réelles.** La base et la page restent des fichiers sur le Mac de Lounès, sans lien publié, jusqu'au feu vert de la conformité. Aucune donnée n'est envoyée à un tiers : pas de géolocalisation en ligne, pas de bibliothèque chargée depuis internet. *Dans le dépôt : rien de réel ; les essais réels sont lancés par Lounès, hors du dépôt.*
14. **Registre du commerce :** export ponctuel en fichiers de l'outil de Kamal (annonces légales et personnes citées). Le branchement direct viendra avec la production.
15. **Une seule base :** la base « liste noire × registre du commerce », étendue avec la couche Tandem. Elle utilise les mêmes normalisations et les mêmes règles.

## 5. Carte

16. **L'adresse qui fait foi est la plus récente et datée**, avec sa source affichée : en production, l'adresse déclarée à EQDOM ; dans le prototype, d'abord l'adresse du relevé bancaire le plus récent, puis celle des autres pièces datées, et l'adresse de la CIN seulement en dernier recours, marquée « peut-être ancienne » ; pour une société, le siège inscrit au registre du commerce. Toutes les adresses connues restent dans la fiche, avec leur source et leur date.
17. **Deux vues reliées, côte à côte :** la carte montre où (une bulle par ville, puis des arcs vers les villes des liens du client recherché) ; le panneau réseau montre qui (le graphe centré sur le client, avec les rebonds, les poids et le curseur ; les inscrits en rouge, les homonymies en pointillé). Les deux vues sont synchronisées. Le fond de carte reprend les 12 régions officielles, provinces du Sud comprises, et il est intégré à la page.

## 6. Choix par défaut (à corriger si besoin)

- **Recherche** par nom (tolérante aux variantes d'écriture), CIN, référence de dossier, RIB, raison sociale, ICE ou numéro RC.
- **Fiche client :** identité, adresses datées avec leur source ; dossiers, avec le produit, le verdict Tandem et les alertes ; employeurs, RIB, pièces reçues ; liens avec la liste noire et leurs chemins, statuts « homonymie ».
- **Statistiques :** répartition des demandeurs par âge, CSP, revenu, produit, mode de paiement, région et type de personne ; taux de dossiers suspects par segment ; le sexe et la nationalité ne servent jamais à calculer un taux de suspicion ; aucun chiffre calculé sur moins de 5 clients n'est affiché.
- **Prototype :** un sélecteur « cellule fraude / autre utilisateur » montre les deux vues ; le journal des consultations et les décisions d'analyste sont gardés dans le navigateur et exportables, en attendant leur table en production.

## 7. Décision du 22/10/2026 : les chaînes du dessin

18. **Priorité du moment.** Relier les individus de la liste noire aux sociétés, et les sociétés entre elles, selon le dessin de Lounès, jusqu'à 4 arêtes, sur les données réelles :

    PP n°1 (inscrit) –gérant– PM n°1 –associé– PP n°2 –gérant– PM n°2 –associé– PP n°3

    Ce qui compte le plus : les chaînes qui reviennent vers un autre élément de la liste noire (un second inscrit, une société inscrite, l'employeur déclaré d'un inscrit).

**Règles de méthode appliquées (à confirmer).** Une même personne d'une société à l'autre : même CIN, ou même nom + même ville du siège, si ce nom figure dans 5 sociétés au plus. Un numéro RC n'identifie une société que s'il désigne un seul nom sous son tribunal ; les RC à 1 ou 2 chiffres et ceux qui portent 3 noms incompatibles ou plus sont ignorés.

**Demandes en cours.** Kamal : extraire le CIN et la date de naissance des annonces quand elles les citent (412 CIN sur 465 000 personnes aujourd'hui). EQDOM : compléter le tribunal des sociétés inscrites (207 sur 1 433 l'ont).

## 8. Décisions du 09/11/2026 : pondération des liens et niveaux d'alerte

But : une seule formule, un seul barème, des seuils reliés à une action. Les chiffres se recalent au calibrage, en rejouant les fraudes confirmées avec la cellule fraude.

19. **Ce que déclenche le score.** Une seule alerte Tandem « lien avec la liste noire », sur les trois niveaux que les métiers lisent déjà (rapport du soir, infographie du COMEX). Le score ordonne aussi la file de la cellule fraude. Il ne refuse jamais un dossier à lui seul (loi 09-08, article 11 : aucune décision à effet juridique ne peut reposer uniquement sur un traitement automatisé qui établit un profil).

    | Niveau | Quand | Ce qui se passe |
    | --- | --- | --- |
    | Critique | la personne ou la société du dossier est inscrite, ou l'employeur est une société inscrite, par un lien certain (même CIN, même RC + tribunal, même ICE) | la cellule fraude voit le dossier avant toute décision |
    | Majeure | chemin fort vers un inscrit | dossier à regarder |
    | Mineure | chemin faible | visible dans la fiche ; ne compte que si une autre alerte Tandem se déclenche |
    | Sous le seuil | — | rien ; le lien reste en base pour la passe de nuit |

20. **Longueur et niveau maximal.** La longueur se compte en liens depuis l'identité du dossier la plus proche (demandeur, caution, gérant, société ou employeur) : 0 lien → critique ; 1 ou 2 → majeure ; 3 → mineure ; **à partir de 4 → jamais d'alerte**, mais les chemins restent calculés et affichés, sans limite de longueur, en gris avec la mention « hors alerte ». Sous ce maximum, la force décide si le niveau est atteint et range les dossiers à l'intérieur d'un niveau. Compter depuis l'employeur garde la société écran type à 2 liens. Remplace, pour les alertes, la profondeur sans limite de la n°7.

21. **Ce qui arrête l'affichage : la force, avec un coût de taille.** Le curseur de force est le seul arrêt de l'affichage. Chaque nœud traversé coûte selon sa taille n, même s'il est reconnu par son CIN : 1 jusqu'à n = 2, puis √(2/n).

    | n | 2 | 3 | 5 | 8 | 40 | 500 |
    | --- | ---: | ---: | ---: | ---: | ---: | ---: |
    | coût | 1 | 0,82 | 0,63 | 0,50 | 0,22 | 0,06 |

    n se compte sur toute la base : pour une personne, ses sociétés (rôles terminés compris) ; pour une société, ses dirigeants et associés cités ; pour un employeur, les clients EQDOM qui le déclarent, ou l'effectif de la liste des grands employeurs s'il est plus grand ; pour un téléphone, un RIB, un courriel ou une adresse, les personnes distinctes qui le portent (des personnes, pas des dossiers). Le coût ne s'applique jamais aux deux bouts du chemin. Exemples : un gérant de 8 sociétés placé entre l'employeur et une société inscrite garde 0,7 × 0,50 × 0,7 = 0,25 ; un liquidateur de 40 sociétés tombe à 0,5 × 0,22 × 0,5 = 0,06. Remplace la coupure `SOCIETES_MAX` et le 1 / log2 du rapport de cadrage. La rareté qui juge une homonymie (même nom, même ville) reste à part : elle entre dans la fiabilité.

22. **Homonymies.** La fiabilité de chaque rapprochement et de chaque passage d'une société à l'autre entre dans la force : 1 pour un même CIN ; de 0,4 à 0,9 selon la règle, multiplié par la rareté du nom, pour un rapprochement probable. Aux deux bouts du chemin seulement (l'identité du dossier au registre, la personne du registre à l'inscrit), une homonymie non levée plafonne le chemin à « mineure », avec la mention « homonymie à lever ». Levée « même personne » : le chemin retrouve son plafond ; « homonyme écarté » : il disparaît. Les passages au milieu du chemin ne jouent que sur la force. Un employeur reconnu seulement par son nom compte comme une homonymie. Tant que les 378 homonymies en attente ne sont pas levées, le registre ne produit que des mentions mineures : leur levée est à planifier avec la cellule fraude. Assouplit la n°5.

23. **Barème des liens** (poids de départ, avant coût de taille et fiabilité) :

    | Famille | Lien | Poids |
    | --- | --- | ---: |
    | Argent et comptes | même RIB | 0,9 |
    | | salaire versé par un autre que l'employeur déclaré | 0,8 |
    | | virements entre deux personnes | 0,5 pour un seul, 0,7 à partir de deux |
    | Pièces | même fichier dans deux dossiers (empreinte identique) | 0,9 |
    | Dossiers | co-emprunteurs d'un même dossier | 0,9 |
    | | caution | 0,8 |
    | | référence personnelle citée | 0,5 |
    | Contact | même téléphone mobile, même courriel | 0,8 |
    | | même numéro d'abonné à l'eau ou à l'électricité | 0,7 |
    | Sociétés | gérant ou dirigeant | 0,7 |
    | | associé (personne ou société) | 0,3 + 0,4 × part ; 0,5 si la part est inconnue |
    | | liquidateur | 0,5 |
    | Emploi | employé déclaré (attestation, bulletins de paie, CNSS) | 0,6 |
    | | signataire de l'attestation de travail | 0,5 |
    | | cabinet qui a établi la liasse fiscale | 0,4 |
    | Lieu | même logement, même téléphone fixe | 0,5 |
    | | même siège social | 0,4 |
    | | même immeuble seulement | 0,2 |

    Hors du score (dessinés sur la carte, sans poids) : apporteur, point de vente, agent de saisie (ils serviront aux statistiques, par exemple la part d'inscrits parmi les dossiers d'un apporteur) ; prélèvements d'un autre organisme de crédit. Une société associée d'une autre suit la formule de l'associé. Les sièges de domiciliation s'effacent par le coût de taille, sans liste à tenir. Les lignes argent, abonné et fichier n'existent que si Tandem extrait ces champs (à confirmer avec Kamal).

24. **Foyer.** Un foyer, c'est un conjoint déclaré, ou deux personnes du même nom de famille qui partagent le même logement, le même téléphone fixe ou le même immeuble. Entre membres d'un même foyer, l'argent et les pièces gardent leur poids plein (même RIB, virements, salaire versé par l'autre, même fichier) ; tout le reste tombe à 0,1 et ne dépasse jamais « mineure » (la fiche affiche « même foyer qu'un inscrit »). Entre deux personnes sans lien de foyer, le barème s'applique tel quel : deux inconnus déclarés au même logement restent à 0,5. Tenir compte des proches d'un inscrit est à valider avec la conformité et la cellule fraude ; le conjoint doit être déclaré, une femme mariée gardant son nom au Maroc (à vérifier avec Kamal : nom du conjoint dans le formulaire EQDOM, statut matrimonial au dos de la CNIE).

25. **Même RC et même tribunal, dénominations sans rapport : deux fiches, signalées** (Lounès, 16/11/2026). Deux mentions de société qui portent le même RC sous le même tribunal ne font une seule fiche que si leurs dénominations sont compatibles (mêmes mots, mots de l'une dans l'autre, graphies proches, ou écritures différentes). Sinon chacune a sa fiche et le couple est signalé (`RC_PARTAGE`, à vérifier) : une fusion à tort marquerait une société comme inscrite, et elle ne se défait pas. Même règle que pour un CIN porté par deux noms incompatibles.

**En attente de validation (question 8).** Proposition : tout inscrit actif pèse 1 au bout du chemin, quel que soit le motif, et l'alerte affiche la source (EQDOM, APSF, DGSN), le type de liste et le type de fraude. Exception : une inscription qui désigne une victime (identité usurpée, pièce volée ou perdue) ne compte qu'à 0 lien (un dossier qui présente cette CIN reste critique) et aucun rebond n'en part. La base de la police suivrait la même règle. Il faut le dictionnaire des motifs de la liste noire : c'est à EQDOM de dire quels codes désignent une victime. En attendant, toutes les inscriptions propagent leur réseau.

**Pas encore traités.** Seuils chiffrés « fort » et « faible » ; effet du temps (rôles terminés, demi-vie) ; même identifiant dans plusieurs dossiers déposés en peu de temps ; combinaison de plusieurs inscrits atteints (meilleur chemin ou cumul) ; liens que le JSON v2 rend possibles mais que le barème ne couvre pas (même châssis, même concessionnaire). Propositions provisoires : `docs/questions_ouvertes.md`.
