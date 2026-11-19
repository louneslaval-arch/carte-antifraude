'use strict';
// Vue 360° d'une entité : trois profils (personne salariée, personne entrepreneur, personne morale), chacun avec ses
// blocs dans l'ordre utile ; puis toutes les données du client, dossier par dossier.
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date, initiales } = Commun;
  Commun.entete('base.html');
  const main = document.getElementById('contenu');
  const indice = Commun.parametre('i');
  let f;
  try {
    f = await api(`/api/base/clients/${encodeURIComponent(indice)}`);
  } catch (e) {
    main.replaceChildren(el('p', { classe: 'carte', role: 'alert', texte: Commun.erreur(e, 'Fiche') }));
    main.removeAttribute('aria-busy');
    return;
  }
  const id = f.identite;
  const v = f.vue360 || { profil: id.type === 'personne' ? 'salarie' : 'pm', retraite: false, csp: null, aussi: [],
    revenus: { declare: null, pieces: {}, ecart: null }, controles: [] };
  const PROFILS = {
    salarie: { nom: v.retraite ? 'Personne physique · retraitée' : 'Personne physique · salariée', classe: 'profil-salarie' },
    entrepreneur: { nom: 'Personne physique · entrepreneur', classe: 'profil-entrepreneur' },
    pm: { nom: 'Personne morale', classe: 'profil-pm' },
  };
  const P = PROFILS[v.profil];
  const CSP = { SALARIE_PRIVE: 'salarié du privé', FONCTIONNAIRE: 'fonctionnaire', EMPLOYE_COMMUNE: 'employé de commune',
    MILITAIRE: 'militaire', RETRAITE_PUBLIC: 'retraité du public', RETRAITE_CIMR: 'retraité CIMR', RETRAITE_INDETERMINE: 'retraité',
    PROFESSION_LIBERALE: 'profession libérale', LOUEUR: 'loueur', AUTRE: 'autre', SOCIETE: 'société' };
  const propres = f.dossiers.filter(d => d.demandeur);
  const anomalies = v.controles.reduce((s, x) => s + x.anomalies, 0);

  // ---- en-tête ------------------------------------------------------------------------------------------------------
  const definitions = id.type === 'personne'
    ? [['CIN', id.cin], ['Date de naissance', date(id.date_naissance)], ['Adresse retenue', id.adresse],
      ['CSP', v.csp ? CSP[v.csp] || lib(v.csp) : null]]
    : [['RC', id.rc ? `${id.rc} · ${id.tribunal || ''}` : null], ['ICE', id.ice], ['Siège', id.adresse]];
  const tete = el('section', { classe: `carte identite tete-360 ${P.classe}` },
    el('div', { classe: `avatar ${id.type}${id.inscrit ? ' inscrit' : ''}`, 'aria-hidden': 'true', texte: initiales(id.nom) }),
    el('div', { classe: 'tete-texte' },
      el('div', { classe: 'surtitre', texte: 'Vue 360°' }),
      el('h1', { texte: id.nom }),
      el('div', { classe: 'puces' },
        el('span', { classe: `etiquette etiquette-profil ${P.classe}`, texte: P.nom }),
        id.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'Inscrit sur la liste noire' }) : null),
      el('dl', { classe: 'definitions' }, definitions.map(([k, x]) => [el('dt', { texte: k }), el('dd', { texte: x || '—' })])),
      v.aussi.length ? el('p', { classe: 'bandeau-aussi' }, 'Aussi ',
        v.aussi.map((s, k) => [k ? ', ' : '', `${s.role} de `, s.indice ? Commun.lienFiche(s) : s.nom])) : null));

  // ---- mur de tuiles : une quarantaine de données clés, par thème, colorées selon leur ton (calculées par l'API) ------
  const flux = fluxBancaires();
  const dirigeants = regrouper(f.personnes);
  const mur = murDeTuiles(v.tuiles || []);

  // ---- blocs --------------------------------------------------------------------------------------------------------
  const B = {
    revenus: () => carte(v.retraite ? 'Pension' : (v.profil === 'entrepreneur' ? 'Revenus d’activité' : 'Salaire et revenus'),
      barresRevenus(), f.charges.length ? [el('h3', { texte: 'Charges' }), tableau(['Charge', 'Période', 'Montant', 'Dossier'],
        f.charges.map(c => [c.nature === 'credit_source' ? 'crédit prélevé à la source' : 'échéance de crédit', periode(c),
          montant(c.montant), lienDossier(c.dossier)]))] : null,
      f.revenus.length ? el('details', {}, el('summary', { texte: `Détail des ${nombre(f.revenus.length)} montants` }),
        tableau(['Nature', 'Pièce', 'Période', 'Montant', 'Dossier'], f.revenus.map(r => [r.nature === 'declare' ? 'déclaré' : 'vérifié',
          libelleSource(r.source), periode(r), montant(r.montant), lienDossier(r.dossier)]))) : null),
    employeur: () => {
      const employeurs = f.societes.filter(s => s.role === 'salarié' || s.role === 'pensionné');
      const declares = [...new Set(f.donnees.flatMap(x => x.contexte).filter(c => c.libelle === 'Employeur déclaré'
        || c.libelle === 'Organisme de pension déclaré').map(c => String(c.valeur)))];
      return carte(v.retraite ? 'Organisme de pension' : 'Employeur',
        employeurs.length ? tableau(['Employeur', 'Rôle', 'Source'], employeurs.map(s => [s.indice ? Commun.lienFiche(s) : s.nom, s.role,
          libelleSource(s.source)])) : vide('Aucun employeur relié.'),
        declares.length ? el('p', { classe: 'note', texte: `Déclaré au dossier : ${declares.join(', ')}` }) : null,
        controlesDe(['EMP']));
    },
    activite: () => carte('Sociétés et rôles', f.societes.length
      ? tableau(['Société', 'Rôle', 'Source'], f.societes.map(s => [s.indice ? Commun.lienFiche(s) : s.nom,
        etatRole(s.role), libelleSource(s.source)])) : vide('Aucune société reliée.'),
      f.registre.length ? [el('h3', { texte: 'Au registre du commerce' }), tableau(['Société', 'Rôle', 'Parts', 'Adresse'],
        f.registre.map(m => [m.societe, m.role, m.parts, m.adresse]))] : null),
    piecesPro: () => carte('Pièces professionnelles', controlesDe(['PRO', 'IDT'], c => /^(PRO|IDT-1[0-1])/.test(c.controle))
      || vide('Aucun contrôle de pièce professionnelle sur ses dossiers.')),
    dirigeants: () => carte('Gérants, associés et bénéficiaires', dirigeants.length
      ? tableau(['Nom', 'Rôles', 'Sources', ''], dirigeants.map(p => [p.indice ? Commun.lienFiche(p) : p.nom,
        p.roles.map((r, k) => [k ? ', ' : '', etatRole(r)]), p.sources.map(libelleSource).join(', '),
        p.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'inscrit' }) : '']))
      : vide('Aucune personne reliée.'),
      controlesDe(['IDT'], c => /^IDT-(1[2-9]|2\d)/.test(c.controle))),
    registre: () => carte('Registre du commerce', f.registre.length ? tableau(['Société', 'Rôle', 'Parts', 'Adresse'],
      f.registre.map(m => [m.societe, m.role, m.parts, m.adresse])) : vide('Aucune mention au registre.'),
      identifiantsTableau()),
    banque: () => carte(v.profil === 'pm' ? 'Comptes et flux de la société' : 'Comptes bancaires',
      f.comptes.length ? tableau(['RIB', 'Banque', 'Titulaire'], f.comptes.map(c => [c.rib, c.banque || '—', c.titulaire || '—'])) : vide('Aucun compte lu.'),
      flux.mois ? el('dl', { classe: 'definitions' },
        [['Mois de relevés lus', nombre(flux.mois)], ['Crédits cumulés', montant(flux.credit)], ['Débits cumulés', montant(flux.debit)],
          ['Échéances de crédit repérées', montant(flux.echeances)]].map(([k, x]) => [el('dt', { texte: k }), el('dd', { texte: x })])) : null,
      controlesDe(['BNQ'])),
    risque: () => carte('Risque',
      el('h3', { texte: 'Liens avec la liste noire' }),
      f.chemins.length ? el('div', { classe: 'pile' }, f.chemins.map(Commun.chemin)) : vide('Aucun chemin vers un inscrit à moins de 4 liens.'),
      Commun.role() === 'ANALYSTE' ? el('p', {}, versLaCarte()) : null,
      f.liste_noire.length ? [el('h3', { texte: 'Inscription sur la liste noire' }), tableau(
        ['Libellé', 'Type de liste', 'Motif', 'Type de fraude', 'Statut', 'Première saisie', 'Inscriptions'],
        f.liste_noire.map(l => [l.label, l.typeListe, l.motif, l.type_fraude, l.statut, date(l.premiere_saisie), nombre(l.nb_inscriptions)]))] : null,
      f.incoherences.length ? [el('h3', { texte: 'Incohérences' }), tableau(['Incohérence', 'Gravité', 'Dossier', 'Autre dossier'],
        f.incoherences.map(i => [i.libelle, i.gravite, lienDossier(i.dossier), lienDossier(i.autre_dossier)]))] : null,
      controlesDe(['BLG'])),
    controles: () => carte('Contrôles de l’antifraude, par famille', v.controles.length
      ? el('div', { classe: 'familles' }, v.controles.map(familleControles))
      : vide(propres.length ? 'Aucun contrôle sur ses dossiers.' : 'Cité seulement dans les dossiers d’autres clients : leurs contrôles ne figurent pas ici.'),
      el('p', { classe: 'note', texte: 'Un contrôle en anomalie est un signal de l’antifraude, jamais une décision : seules la liste noire et les fraudes confirmées par la cellule fraude font foi.' })),
    historique: () => carte('Historique des dossiers', f.dossiers.length ? tableau(
      ['Reçu', 'Produit', 'Rôle', 'Verdict v2', ''],
      f.dossiers.map(d => [date(d.recu), d.produit, d.role, d.demandeur ? (d.verdict || '—') : '—',
        el('a', { href: `dossier.html?i=${d.indice}`, texte: 'Ouvrir' })])) : vide('Aucun dossier.'),
      f.dossiers.some(d => !d.demandeur) ? el('p', { classe: 'note', texte: `Cité dans ${nombre(f.dossiers.filter(d => !d.demandeur).length)} dossier(s) d’autres clients : leurs revenus et charges ne figurent pas sur cette fiche.` }) : null,
      f.vehicules.length ? [el('h3', { texte: 'Véhicules' }), tableau(['Pièce', 'Marque', 'Modèle', 'Prix'],
        f.vehicules.map(x => [libelleSource(x.type_piece), x.marque || '—', x.modele || '—', montant(x.prix)]))] : null,
      controlesDe(['AUT'])),
    identite: () => carte('Identité et adresses',
      el('div', { classe: 'puces' }, f.alias.map(a => el('span', { classe: 'etiquette', lang: a.ecriture === 'arabe' ? 'ar' : null, texte: `${a.nom} · ${a.nombre}` }))),
      f.adresses.length ? tableau(['Adresse', 'Rôle'], f.adresses.map(a => [a.adresse, a.role || '—'])) : null,
      v.profil === 'pm' ? null : identifiantsTableau(),
      controlesDe(['IDT'], c => v.profil === 'pm' || !/^IDT-1[0-1]/.test(c.controle) || v.profil === 'salarie')),
  };
  // Ordre des blocs : deux colonnes, la gauche pour ce qui caractérise le profil.
  const DISPOSITION = {
    salarie: [['revenus', 'employeur'], ['risque', 'banque', 'identite']],
    entrepreneur: [['activite', 'revenus', 'piecesPro'], ['risque', 'banque', 'identite']],
    pm: [['dirigeants', 'registre', 'banque'], ['risque', 'identite']],
  }[v.profil];

  const operations = f.operations.length ? carte(`Opérations des relevés (${nombre(f.operations.length)})`,
    el('details', {}, el('summary', { texte: 'Afficher les opérations' }),
      tableau(['Date', 'Type', 'Libellé', 'Débit', 'Crédit', 'Dossier'], f.operations.map(o => [date(o.date_operation),
        o.type_operation || '—', court(o.libelle), montant(o.debit), montant(o.credit), lienDossier(o.dossier)])))) : null;

  main.replaceChildren(...[el('p', { classe: 'fil' }, el('a', { href: 'base.html', texte: 'Base client' }), ' › Vue 360°'),
    tete, mur,
    el('div', { classe: 'grille grille-2' }, DISPOSITION.map(col => el('div', { classe: 'pile' }, col.map(k => B[k]())))),
    B.controles(), operations, toutesLesDonnees()].filter(Boolean));
  main.removeAttribute('aria-busy');

  // ---- éléments -----------------------------------------------------------------------------------------------------
  // Mur de données : une carte par thème (couleur et icône du thème), des tuiles sobres
  // dont le ton (à traiter, à regarder, rassurant) se lit à la pastille et à la couleur de la valeur.
  function murDeTuiles(groupes) {
    if (!groupes.length) return null;
    const THEMES = {
      'Liste noire': ['risque', 'bouclier'], 'Alertes': ['alerte', 'alerte'], 'Revenus et charges': ['argent', 'billet'],
      'Revenus et pièces': ['argent', 'billet'], 'Emploi et compte': ['emploi', 'mallette'],
      'Pension et compte': ['emploi', 'mallette'], 'Identité légale': ['legal', 'immeuble'],
      'Sociétés et activité': ['legal', 'immeuble'], 'Dirigeants': ['personnes', 'personnes'],
      'Comptes et réseau': ['reseau', 'reseau'], 'Identité': ['identite', 'carte'],
      'Historique des dossiers': ['historique', 'horloge'], 'À venir': ['avenir', 'sablier'] };
    const cartes = groupes.map(g => {
      const [theme, ico] = THEMES[g.groupe] || ['identite', 'carte'];
      const alertes = g.tuiles.filter(x => x.ton === 'critique' || x.ton === 'attention').length;
      const carte_ = el('section', { classe: `mur-carte theme-${theme}`, 'aria-label': g.groupe },
        el('header', { classe: 'mur-carte-tete' }, el('span', { classe: 'mur-icone', 'aria-hidden': 'true' }, icone(ico)),
          el('h3', { texte: g.groupe }),
          alertes ? el('span', { classe: 'mur-badge', texte: `${alertes} signal${alertes > 1 ? 'aux' : ''}` }) : null),
        el('div', { classe: 'mur-tuiles' }, g.tuiles.map(tuileMur)));
      carte_.style.gridColumn = `span ${Math.min(12, Math.max(3, g.tuiles.length * 3))}`;
      return carte_;
    });
    return el('section', { classe: 'mur', 'aria-label': 'Données clés du client' },
      el('div', { classe: 'mur-entete' }, el('h2', { texte: 'Données clés' }),
        el('p', { classe: 'note', texte: 'Lues dans les pièces, le registre du commerce et la liste noire ; la source est sous chaque valeur.' })),
      el('div', { classe: 'mur-grille-cartes' }, cartes));
  }
  function tuileMur(t) {
    const valeur = valeurTuile(t);
    const absente = t.valeur === null || t.valeur === undefined || t.valeur === '';
    const corps = [el('div', { classe: 'tuile-libelle' }, el('span', { classe: 'tuile-point', 'aria-hidden': 'true' }), t.libelle),
      el('div', { classe: `tuile-chiffre${valeur.length > 14 ? ' long' : ''}`, texte: absente ? 'à venir' : valeur }),
      t.detail ? el('div', { classe: 'tuile-detail', texte: t.detail }) : null,
      t.source ? el('div', { classe: 'tuile-via', texte: t.source }) : null];
    const attributs = { classe: `tuile ton-${t.ton}${absente ? ' absente' : ''}`,
      title: [t.detail, t.source ? `source : ${t.source}` : null].filter(Boolean).join(' · ') || null };
    return t.lien ? el('a', { ...attributs, href: t.lien, classe: `${attributs.classe} tuile-lien` }, ...corps) : el('div', attributs, ...corps);
  }
  // Icônes du mur : traits simples en SVG, dessinés ici (aucune ressource extérieure).
  function icone(nom) {
    const TRACES = {
      bouclier: 'M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z',
      alerte: 'M12 4l9 16H3L12 4zM12 10v4M12 17.5v.5',
      billet: 'M3 7h18v10H3zM12 9.5a2.5 2.5 0 110 5 2.5 2.5 0 010-5zM6 10v4M18 10v4',
      mallette: 'M4 8h16v11H4zM9 8V5h6v3M4 13h16',
      immeuble: 'M5 21V5l7-2v18M12 8h7v13M8 8h1M8 12h1M8 16h1M15 12h1M15 16h1M3 21h18',
      personnes: 'M9 11a3 3 0 100-6 3 3 0 000 6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 11a3 3 0 100-6M17 14c2.3.5 4 2.7 4 6',
      reseau: 'M6 6a2 2 0 100 .1M18 6a2 2 0 100 .1M12 18a2 2 0 100 .1M7.5 7.5l3.5 9M16.5 7.5l-3.5 9M8 6h8',
      carte: 'M3 6h18v12H3zM8 11a2 2 0 100-4 2 2 0 000 4zM5 15c.5-1.5 1.6-2 3-2s2.5.5 3 2M14 9h4M14 13h4',
      horloge: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 7v5l3 2',
      sablier: 'M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9',
      coche: 'M12 3a9 9 0 110 18 9 9 0 010-18zM8 12l3 3 5-6' };
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', TRACES[nom] || TRACES.carte);
    svg.append(p);
    return svg;
  }
  function valeurTuile(t) {
    if (t.valeur === null || t.valeur === undefined || t.valeur === '') return '—';
    switch (t.format) {
      case 'montant': return montant(t.valeur);
      case 'nombre': return nombre(t.valeur);
      case 'pourcent': return `${Math.round(t.valeur * 100)} %`;
      case 'date': return date(t.valeur);
      case 'mois': return `${nombre(t.valeur)} mois`;
      case 'ans': return `${nombre(t.valeur)} ans`;
      default: return CSP[t.valeur] || String(t.valeur);
    }
  }
  function barresRevenus() {
    const lignes = [['Déclaré', v.revenus.declare, 'declare']].concat(
      [['BULLETIN_DE_PAIE', 'Bulletin de paie'], ['ATTESTATION_TRAVAIL_SALAIRE', 'Attestation de salaire'],
        ['ATTESTATION_PENSION', 'Justificatif de pension'], ['RELEVE_BANCAIRE', 'Retrouvé sur les relevés']]
        .filter(([s]) => v.revenus.pieces[s] !== undefined).map(([s, n]) => [n, v.revenus.pieces[s], 'verifie']))
      .filter(([, m]) => m !== null && m !== undefined);
    if (!lignes.length) return vide(propres.length ? 'Aucun revenu lu.' : 'Cité seulement : les revenus des dossiers d’autres clients ne figurent pas ici.');
    const max = Math.max(...lignes.map(([, m]) => m)) || 1;
    return el('div', { classe: 'barres-revenus', role: 'list' }, lignes.map(([n, m, genre]) => {
      const barre = el('span', { classe: `barre ${genre}` });
      barre.style.width = `${Math.max(2, m / max * 100)}%`;              // CSSOM : permis par la politique de la plateforme
      return el('div', { classe: 'ligne-revenu', role: 'listitem' }, el('span', { classe: 'nom-revenu', texte: n }),
        el('span', { classe: 'piste' }, barre), el('span', { classe: 'montant-revenu', texte: montant(m) }));
    }), v.revenus.ecart !== null ? el('p', { classe: 'note', texte: `Écart entre pièces : ${Math.round(v.revenus.ecart * 100)} % (dernier montant de chaque pièce).` }) : null);
  }
  function controlesDe(familles, garder = () => true) {
    const noms = { IDT: 'Identité', BNQ: 'Relevés bancaires', BLG: 'Liste noire et géographie', EMP: 'Revenus et employeur',
      PRO: 'Pièces professionnelles', AUT: 'Véhicule' };
    const lignes = v.controles.filter(x => familles.some(p => noms[p] === x.famille)).flatMap(x => x.controles).filter(garder);
    if (!lignes.length) return null;
    const enAnomalie = lignes.filter(c => c.resultat === 'ANOMALIE').length;
    return el('details', { classe: 'controles-bloc', open: enAnomalie > 0 },
      el('summary', {}, `Contrôles (${nombre(lignes.length)})`, enAnomalie
        ? el('span', { classe: 'etiquette etiquette-rouge', texte: `${nombre(enAnomalie)} en anomalie` }) : el('span', { classe: 'etiquette ok', texte: 'tous conformes' })),
      el('ul', { classe: 'liste-controles' }, lignes.map(ligneControle)));
  }
  function familleControles(x) {
    return el('details', { classe: 'famille', open: x.anomalies > 0 },
      el('summary', {}, el('strong', { texte: x.famille }), ` · ${nombre(x.controles.length)} contrôle(s)`,
        x.anomalies ? el('span', { classe: 'etiquette etiquette-rouge', texte: `${nombre(x.anomalies)} en anomalie` }) : null),
      el('ul', { classe: 'liste-controles' }, x.controles.map(ligneControle)));
  }
  function ligneControle(c) {
    const r = { ANOMALIE: ['anomalie', 'anomalie'], CONFORME: ['conforme', 'conforme'], NON_APPLICABLE: ['neutre', 'non applicable'],
      NON_EXECUTABLE: ['neutre', 'non exécutable'], ERREUR_TECHNIQUE: ['neutre', 'erreur technique'] }[c.resultat] || ['neutre', lib(c.resultat)];
    return el('li', { classe: `controle ${r[0]}`, title: c.description ? `${c.controle} · ${c.description}` : c.controle },
      el('span', { classe: 'pastille', 'aria-hidden': 'true' }),
      el('span', { classe: 'controle-texte' }, el('code', { texte: c.controle }), ' ', c.libelle,
        c.description ? el('span', { classe: 'controle-desc', texte: c.description }) : null),
      el('span', { classe: 'controle-etat' }, r[1], c.criticite ? ` · ${String(c.criticite).toLowerCase()}` : ''),
      c.dossier ? el('a', { href: `dossier.html?i=${c.dossier}`, texte: 'dossier', 'aria-label': `Ouvrir le dossier du contrôle ${c.controle}` }) : null);
  }
  function identifiantsTableau() {
    return f.identifiants.length ? [el('h3', { texte: 'Identifiants' }), tableau(['Type', 'Valeur', 'Dossier'],
      f.identifiants.map(x => [x.type, x.valeur, lienDossier(x.dossier)]))] : null;
  }
  function fluxBancaires() {
    const t = { mois: 0, credit: 0, debit: 0, echeances: 0 };
    for (const x of f.donnees) for (const p of x.pieces) for (const m of p.mois) {
      t.mois += 1; t.credit += m.total_credit || 0; t.debit += m.total_debit || 0; t.echeances += m.echeances_credits || 0;
    }
    return t;
  }
  function regrouper(personnes) {                        // une ligne par personne, ses rôles et ses sources réunis
    const par = new Map();
    for (const p of personnes) {
      const cle = p.indice ?? p.nom;
      const x = par.get(cle) || { ...p, roles: [], sources: [] };
      if (p.role && !x.roles.includes(p.role)) x.roles.push(p.role);
      if (p.source && !x.sources.includes(p.source)) x.sources.push(p.source);
      x.inscrit = x.inscrit || p.inscrit;
      par.set(cle, x);
    }
    return [...par.values()];
  }
  function etatRole(r) {
    return /sortant|cédant|liquidateur/.test(r || '') ? el('span', { classe: 'note', texte: `${r} (terminé)` }) : r;
  }
  function toutesLesDonnees() {
    const navigation = el('div', { classe: 'onglets', role: 'tablist', 'aria-label': 'Dossiers du client' });
    const volets = el('div', {});
    const onglets = f.donnees.map((x, k) => {
      const idv = `volet-${k}`;
      const onglet = el('button', { classe: 'onglet', type: 'button', role: 'tab', id: `onglet-${k}`, 'aria-selected': String(k === 0),
        tabindex: k === 0 ? '0' : '-1', 'aria-controls': idv, texte: `Dossier ${x.reference}${x.demandeur ? '' : ' (cité)'}` });
      const volet = el('div', { id: idv, role: 'tabpanel', 'aria-labelledby': `onglet-${k}`, hidden: k !== 0 });
      let rempli = false;                                // volet construit à la première ouverture
      const ouvrir = () => {
        if (!rempli) { volet.append(voletDossier(x)); rempli = true; }
        for (const o of navigation.children) { const actif = o === onglet; o.setAttribute('aria-selected', String(actif)); o.tabIndex = actif ? 0 : -1; }
        for (const w of volets.children) w.hidden = w !== volet;
      };
      onglet.addEventListener('click', ouvrir);
      onglet.addEventListener('keydown', ev => {
        const pas = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
        if (!pas) return;
        const suivant = onglets[(k + pas + onglets.length) % onglets.length];
        suivant.ouvrir(); suivant.onglet.focus(); ev.preventDefault();
      });
      navigation.append(onglet);
      volets.append(volet);
      if (k === 0) ouvrir();
      return { onglet, ouvrir };
    });
    return carte('Toutes les données du client',
      el('p', { classe: 'note', texte: 'Chaque valeur lue dans chaque pièce de chaque dossier.' }),
      f.donnees.length ? [navigation, volets] : vide('Aucun dossier.'));
  }
  function voletDossier(x) {
    const contexte = el('dl', { classe: 'definitions' }, x.contexte.filter(c => !c.libelle.startsWith('Alertes')).map(c => [el('dt', { texte: c.libelle }), el('dd', { texte: String(c.valeur) })]));
    const pieces = x.pieces.map(p => el('details', { classe: 'piece' },
      el('summary', {}, el('strong', { texte: libelleSource(p.type) }),
        el('span', { classe: 'note', texte: ` · ${p.statut || '—'} · ${p.faits.length} valeurs` })),
      p.mois.length ? tableau(['Mois', 'Solde début', 'Solde fin', 'Crédits', 'Débits', 'Salaire repéré', 'Échéances', 'Opérations lues'],
        p.mois.map(m => [m.mois ? `${String(m.mois).padStart(2, '0')}/${m.annee}` : '—', montant(m.solde_ouverture), montant(m.solde_cloture),
          montant(m.total_credit), montant(m.total_debit), montant(m.salaire_detecte), montant(m.echeances_credits), nombre(m.nb_operations_lues)])) : null,
      tableau(['Champ', 'Valeur', ''], p.faits.map(fa => [el('code', { texte: fa.cle }), court(fa.valeur),
        fa.statut !== 'normal' ? el('span', { classe: 'etiquette', texte: fa.statut.replaceAll('_', ' ') }) : '']))));
    const lien = x.dossier ? el('p', {}, el('a', { href: `dossier.html?i=${x.dossier}`, texte: 'Ouvrir la vue du dossier' })) : null;
    if (!x.demandeur) {
      return el('div', { classe: 'pile' },
        el('p', { classe: 'note', texte: 'Dossier d’un autre client : seules les pièces qui citent cette fiche sont montrées.' }), lien,
        el('div', {}, el('h3', { texte: `Pièces qui la citent (${x.pieces.length})` }), ...pieces));
    }
    return el('div', { classe: 'pile' },
      el('div', {}, el('h3', { texte: 'Contexte déclaré' }), contexte, lien),
      el('div', {}, el('h3', { texte: `Pièces (${x.pieces.length})` }), ...pieces));
  }
  // Carte globale centrée sur le client s'il y figure (retrouvé par son CIN ou son RC), sinon sa vue réseau
  function versLaCarte() {
    const reseau = `reseau.html?i=${encodeURIComponent(indice)}`;
    return el('a', { href: reseau, texte: 'Voir son réseau sur la carte →', onclick: async ev => {
      ev.preventDefault();
      try {
        const r = await api(`/api/base/carte/${encodeURIComponent(indice)}`);
        location.href = `carte.html?n=${encodeURIComponent(r.indice)}`;
      } catch (e) {
        if (e.message !== 'session') location.href = reseau;
      }
    } });
  }
  function lib(s) { return String(s).toLowerCase().replaceAll('_', ' '); }
  function periode(x) { return x.mois ? `${String(x.mois).padStart(2, '0')}/${x.annee}` : '—'; }
  function lienDossier(i) { return i ? el('a', { href: `dossier.html?i=${i}`, texte: 'Ouvrir' }) : '—'; }
  function court(x) {
    if (x === null || x === undefined) return '—';
    const t = String(x);
    return t.length > 140 ? el('span', { title: t, texte: `${t.slice(0, 138)}…` }) : t;
  }
  function carte(titre, ...contenu) { return el('section', { classe: 'carte' }, el('h2', { texte: titre }), ...contenu); }
  function vide(t) { return el('p', { classe: 'vide', texte: t }); }
  function tableau(entetes, lignes) {
    return el('div', { classe: 'tableau-enveloppe' }, el('table', {},
      el('thead', {}, el('tr', {}, entetes.map(t => el('th', { texte: t })))),
      el('tbody', {}, lignes.map(l => el('tr', {}, l.map(c => el('td', {}, c ?? '—')))))));
  }
  function libelleSource(s) {
    return ({ v2: 'dossiers', registre: 'registre du commerce', liste_noire: 'liste noire', businessData: 'déclaration',
      BULLETIN_DE_PAIE: 'bulletin de paie', RELEVE_BANCAIRE: 'relevé bancaire', ATTESTATION_TRAVAIL_SALAIRE: 'attestation de salaire',
      ATTESTATION_PENSION: 'attestation de pension', CARTE_GRISE: 'carte grise', FACTURE_PROFORMA_VEHICULE: 'facture proforma' })[s] || s;
  }
});
