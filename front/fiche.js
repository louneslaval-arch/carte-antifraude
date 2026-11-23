'use strict';
// Vue 360° d'une entité en étoile : au centre une silhouette (personne) ou un immeuble (société), toutes ses informations
// sur les plaques autour ; les personnes et sociétés citées se déplient en étoiles reliées. Données brutes repliées dessous.
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date } = Commun;
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
  const CSP = { SALARIE_PRIVE: 'salarié du privé', FONCTIONNAIRE: 'fonctionnaire', EMPLOYE_COMMUNE: 'employé de commune',
    MILITAIRE: 'militaire', RETRAITE_PUBLIC: 'retraité du public', RETRAITE_CIMR: 'retraité CIMR', RETRAITE_INDETERMINE: 'retraité',
    PROFESSION_LIBERALE: 'profession libérale', LOUEUR: 'loueur', AUTRE: 'autre', SOCIETE: 'société' };
  const propres = f.dossiers.filter(d => d.demandeur);

  // ---- ligne sous le nom : CSP, âge, RC, client depuis ----------------------------------------------------------------
  const pres = v.presentation || null;
  const demandes = pres ? pres.demandes : [];
  const age = (() => {
    const n = id.date_naissance && new Date(id.date_naissance), r = demandes.length && new Date(demandes[demandes.length - 1].date);
    if (!n || !r || isNaN(n) || isNaN(r)) return null;
    return r.getFullYear() - n.getFullYear() - ((r.getMonth() < n.getMonth() || (r.getMonth() === n.getMonth() && r.getDate() < n.getDate())) ? 1 : 0);
  })();
  const ligne = [v.csp && v.profil !== 'pm' ? (CSP[v.csp] || lib(v.csp)) : null, age !== null ? `${age} ans` : null,
    id.type === 'societe' && id.rc ? `RC ${id.rc}${id.tribunal ? ` · ${id.tribunal}` : ''}` : null,
    demandes.length ? `client depuis ${date(demandes[0].date)}` : null].filter(Boolean);

  // ---- données brutes, repliées sous l'étoile -------------------------------------------------------------------------
  const B = {
    controles: () => carte('Contrôles de l’antifraude, par famille', v.controles.length
      ? el('div', { classe: 'familles' }, v.controles.map(familleControles))
      : vide(propres.length ? 'Aucun contrôle sur ses dossiers.' : 'Cité seulement dans les dossiers d’autres clients : leurs contrôles ne figurent pas ici.'),
      el('p', { classe: 'note', texte: 'Un contrôle en anomalie est un signal de l’antifraude, jamais une décision : seules la liste noire et les fraudes confirmées par la cellule fraude font foi.' })),
  };

  const operations = f.operations.length ? carte(`Opérations des relevés (${nombre(f.operations.length)})`,
    el('details', {}, el('summary', { texte: 'Afficher les opérations' }),
      tableau(['Date', 'Type', 'Libellé', 'Débit', 'Crédit', 'Dossier'], f.operations.map(o => [date(o.date_operation),
        o.type_operation || '—', court(o.libelle), montant(o.debit), montant(o.credit), lienDossier(o.dossier)])))) : null;

  // Tout est sur les plaques de l'étoile ; restent repliées les seules données brutes (contrôles un par un, opérations
  // des relevés, pièces champ par champ).
  const detail = el('details', { classe: 'detail-antifraude' },
    el('summary', { texte: 'Données brutes' }), B.controles(), operations, toutesLesDonnees());

  // Vue en étoile (23/11/2026) : au centre une silhouette (personne) ou un immeuble (société), ses informations autour.
  // Une personne ou une société citée dans une bulle se déplie en une nouvelle étoile, reliée à celle d'où elle part ;
  // et ainsi de suite (une chaîne).
  const chaine = el('div', { classe: 'constellation' });
  const sources = new Map();                                 // étoile dépliée → ligne de la bulle d'où elle part
  main.replaceChildren(...[el('p', { classe: 'fil' }, el('a', { href: 'base.html', texte: 'Base client' }), ' › Vue 360°'),
    chaine, detail].filter(Boolean));
  main.removeAttribute('aria-busy');
  if (!v.etoile) chaine.append(vide('Vue 360° indisponible pour cette fiche.'));
  else {
    chaine.append(vueEtoile(f, 0, null));
    const calque = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    calque.setAttribute('class', 'constellation-ponts');
    calque.setAttribute('aria-hidden', 'true');
    chaine.prepend(calque);
    new ResizeObserver(() => relier()).observe(chaine);
    relier();
    // Une société : sa première personne (le gérant d'abord) se déplie d'office.
    const gerant = v.profil === 'pm' && chaine.querySelector('.bulle[data-cle="dirigeants"] [data-fiche]');
    if (gerant) deplier(gerant, false);
  }

  // ---- vue en étoile ------------------------------------------------------------------------------------------------
  function vueEtoile(g, niveau, source) {
    const e = g.vue360.etoile, prof = g.vue360.profil;
    const classe = { salarie: 'profil-salarie', entrepreneur: 'profil-entrepreneur', pm: 'profil-pm' }[prof];
    const THEMES_BRANCHE = { identite: ['identite', 'carte'], emploi: ['emploi', 'mallette'], activite: ['emploi', 'mallette'],
      revenus: ['argent', 'billet'], banque: ['reseau', 'billet'], flux: ['argent', 'billet'], societes: ['legal', 'immeuble'],
      legal: ['legal', 'immeuble'], dirigeants: ['personnes', 'personnes'], siege: ['identite', 'immeuble'],
      groupe: ['reseau', 'reseau'], demandes: ['historique', 'horloge'], eqdom: ['argent', 'coche'],
      liste_noire: ['risque', 'bouclier'], controles: ['alerte', 'coche'] };
    const TONS = ['critique', 'attention', 'bon', 'neutre'];
    const ligneBulle = x => {
      const ton = x.ton && (TONS.includes(x.ton) ? `ton-${x.ton}` : `verdict-${x.ton}`);
      const libelle = el('span', { classe: 'bulle-libelle' },
        ton ? el('span', { classe: `bulle-point ${ton}`, 'aria-hidden': 'true' }) : null, x.libelle);
      const precision = x.detail ? el('span', { classe: 'bulle-detail', texte: x.detail }) : null;
      const fiche = x.lien && /^fiche\.html\?i=(\d+)$/.exec(x.lien);
      if (fiche) {                                           // une personne ou une société : se déplie en étoile
        const b = el('button', { type: 'button', classe: 'bulle-ligne depliable', 'data-fiche': fiche[1], 'aria-expanded': 'false',
          title: 'Déplier son étoile' }, libelle, el('span', { classe: 'bulle-valeur', texte: valeurTuile(x) }),
          el('span', { classe: 'chevron', 'aria-hidden': 'true', texte: '›' }));
        b.dataset.libelle = x.libelle;
        b.addEventListener('click', () => deplier(b, true));
        return el('li', {}, b, precision);
      }
      const corps = [libelle, el('span', { classe: 'bulle-valeur', texte: valeurTuile(x) })];
      const attributs = { classe: 'bulle-ligne', title: x.source ? `source : ${x.source}` : null };
      return el('li', { classe: ton && TONS.includes(x.ton) ? ton : null },
        x.lien ? el('a', { ...attributs, href: x.lien }, ...corps) : el('div', attributs, ...corps), precision);
    };
    const bulle = b => {
      const [theme, ico] = THEMES_BRANCHE[b.cle] || ['historique', 'carte'];
      return el('section', { classe: `bulle theme-${theme}`, 'data-cle': b.cle, 'aria-label': b.titre },
        el('header', { classe: 'bulle-tete' }, el('span', { classe: 'bulle-icone', 'aria-hidden': 'true' }, icone(ico)),
          el('h2', { texte: b.titre }), b.resume ? el('span', { classe: 'bulle-resume', texte: b.resume }) : null),
        b.lignes.length ? el('ul', { classe: 'bulle-lignes' }, b.lignes.map(ligneBulle))
          : el('p', { classe: 'note', texte: 'Aucune en propre : cité dans le dossier d’un autre client.' }));
    };
    // Deux colonnes de hauteur voisine : chaque branche va du côté le moins chargé, l'ordre est gardé de chaque côté.
    const gauche = [], droite = [], poids = b => 2 + Math.max(1, b.lignes.length);
    let pg = 0, pd = 0;
    e.branches.forEach(b => { if (pg <= pd) { gauche.push(b); pg += poids(b); } else { droite.push(b); pd += poids(b); } });
    const sousLigne = niveau === 0 ? ligne : [g.vue360.csp && prof !== 'pm' ? (CSP[g.vue360.csp] || lib(g.vue360.csp)) : null,
      g.identite.rc ? `RC ${g.identite.rc}` : null].filter(Boolean);
    const indice = source ? source.dataset.fiche : indiceCourant();
    const centre = el('div', { classe: 'etoile-centre' },
      source ? el('span', { classe: 'etoile-parent', texte: `${source.dataset.libelle} · ${source.closest('.etoile').dataset.nom}` }) : null,
      medaillon(e.centre.figure),
      el('h1', { classe: niveau ? 'etoile-nom secondaire' : 'etoile-nom', texte: e.centre.nom }),
      el('span', { classe: 'etoile-profil', texte: e.centre.profil }),
      sousLigne.length ? el('p', { classe: 'etoile-ligne', texte: sousLigne.join(' · ') }) : null,
      niveau ? el('div', { classe: 'etoile-actions' },
        el('a', { href: `fiche.html?i=${indice}`, texte: 'Ouvrir sa fiche' }),
        (() => { const x = el('button', { type: 'button', classe: 'lien-bouton', texte: 'Replier' });
          x.addEventListener('click', () => deplier(source, false)); return x; })()) : null);
    const s = el('section', { classe: `etoile ${classe}${niveau ? ' secondaire' : ''}`, 'aria-label': `Vue 360° de ${e.centre.nom}`,
      'data-niveau': String(niveau), 'data-nom': e.centre.nom, 'data-indice': String(indice) },
      el('div', { classe: 'etoile-cote gauche' }, gauche.map(bulle)), centre,
      el('div', { classe: 'etoile-cote droite' }, droite.map(bulle)));
    if (source) sources.set(s, source);
    relierEtoile(s);
    return s;
  }
  function indiceCourant() { return indice; }
  // Déplier (ou replier) l'étoile d'une personne ou d'une société citée ; ce qui suivait dans la chaîne se referme.
  async function deplier(bouton, defiler) {
    const depart = bouton.closest('.etoile'), niveau = Number(depart.dataset.niveau);
    const ouvert = bouton.getAttribute('aria-expanded') === 'true';
    chaine.querySelectorAll('.etoile').forEach(x => { if (Number(x.dataset.niveau) > niveau) { sources.delete(x); x.remove(); } });
    chaine.querySelectorAll('.etoile-absente').forEach(x => { if (Number(x.dataset.niveau) > niveau) x.remove(); });
    depart.querySelectorAll('.depliable[aria-expanded="true"]').forEach(x => x.setAttribute('aria-expanded', 'false'));
    relier();
    if (ouvert) return;
    const deja = [...chaine.querySelectorAll('.etoile')].find(x => x.dataset.indice === bouton.dataset.fiche);
    if (deja) { deja.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }   // déjà dans la chaîne : on y va
    bouton.setAttribute('aria-expanded', 'true');
    let g;
    try {
      g = await api(`/api/base/clients/${encodeURIComponent(bouton.dataset.fiche)}`);
    } catch (err) {
      chaine.append(el('p', { classe: 'etoile-absente note', 'data-niveau': String(niveau + 1), role: 'status', texte: Commun.erreur(err, 'Fiche') }));
      return;
    }
    if (bouton.getAttribute('aria-expanded') !== 'true' || !g.vue360 || !g.vue360.etoile) return;
    const s = vueEtoile(g, niveau + 1, bouton);
    chaine.append(s);
    relier();
    if (defiler) s.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  // Silhouette (personne) ou immeuble (société), traits fins, dans un médaillon.
  function medaillon(type) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 64 64');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', type === 'maison' ? 'Société' : 'Personne');
    const trace = (d, classe) => { const p = document.createElementNS(ns, 'path'); p.setAttribute('d', d); p.setAttribute('class', classe); svg.append(p); };
    if (type === 'maison') {
      trace('M14 54V15l18-6v45M32 24h18v30', 'fond');
      trace('M14 54V15l18-6v45M32 24h18v30M8 54h48M20 19h6M20 26h6M20 33h6M20 40h6M38 31h6M38 38h6M38 45h6M21 54v-7h4v7', 'trait');
    } else {
      trace('M32 31a10 10 0 100-20 10 10 0 000 20zM12 54c0-11 9-18 20-18s20 7 20 18z', 'fond');
      trace('M32 31a10 10 0 100-20 10 10 0 000 20zM12 54c0-11 9-18 20-18s20 7 20 18', 'trait');
    }
    return el('div', { classe: 'medaillon' }, svg);
  }
  // Traits fins du médaillon vers chaque bulle, recalculés quand l'étoile change de taille.
  function relierEtoile(racine) {
    const ns = 'http://www.w3.org/2000/svg';
    const calque = document.createElementNS(ns, 'svg');
    calque.setAttribute('class', 'etoile-liens');
    calque.setAttribute('aria-hidden', 'true');
    racine.prepend(calque);
    const tracer = () => {
      calque.replaceChildren();
      if (!racine.isConnected || getComputedStyle(calque).display === 'none') return;
      const r = racine.getBoundingClientRect(), fig = racine.querySelector('.medaillon').getBoundingClientRect();
      calque.setAttribute('viewBox', `0 0 ${r.width} ${r.height}`);
      const cx = fig.left + fig.width / 2 - r.left, cy = fig.top + fig.height / 2 - r.top;
      racine.querySelectorAll('.bulle').forEach(b => {
        const q = b.getBoundingClientRect(), aGauche = b.parentElement.classList.contains('gauche');
        const ex = (aGauche ? q.right : q.left) - r.left, ey = q.top + 20 - r.top;
        const sx = cx + (aGauche ? -1 : 1) * fig.width / 2, mx = (sx + ex) / 2;
        const theme = [...b.classList].find(c => c.startsWith('theme-'));
        const chemin = document.createElementNS(ns, 'path');
        chemin.setAttribute('d', `M${sx} ${cy} C${mx} ${cy}, ${mx} ${ey}, ${ex} ${ey}`);
        chemin.setAttribute('class', 'lien');
        const point = document.createElementNS(ns, 'circle');
        point.setAttribute('cx', ex); point.setAttribute('cy', ey); point.setAttribute('r', 3);
        point.setAttribute('class', `point ${theme}`);
        calque.append(chemin, point);
      });
    };
    new ResizeObserver(tracer).observe(racine);
  }
  // Ponts entre étoiles : de la ligne de bulle dépliée, par la marge de son étoile, jusqu'au médaillon de la suivante.
  function relier() {
    const calque = chaine.querySelector('.constellation-ponts');
    if (!calque) return;
    calque.replaceChildren();
    if (getComputedStyle(calque).display === 'none') return;
    const ns = 'http://www.w3.org/2000/svg', r = chaine.getBoundingClientRect();
    calque.setAttribute('viewBox', `0 0 ${r.width} ${r.height}`);
    sources.forEach((bouton, s) => {
      if (!s.isConnected || !bouton.isConnected) return;
      const depart = bouton.closest('.etoile').getBoundingClientRect(), q = bouton.getBoundingClientRect();
      const aGauche = !!bouton.closest('.gauche'), cible = s.querySelector('.etoile-centre').getBoundingClientRect();
      const bulle = bouton.closest('.bulle').getBoundingClientRect();
      const bx = (aGauche ? bulle.left : bulle.right) - r.left, by = q.top + q.height / 2 - r.top;
      const gx = (aGauche ? depart.left + 13 : depart.right - 13) - r.left, bas = depart.bottom - r.top;
      const haut = s.getBoundingClientRect().top - r.top, cx = cible.left + cible.width / 2 - r.left, fin = cible.top - r.top - 4;
      const k = 10, sens = aGauche ? 1 : -1, milieu = (bas + haut) / 2;
      const chemin = document.createElementNS(ns, 'path');
      chemin.setAttribute('d', `M${bx} ${by} H${gx + sens * k} Q${gx} ${by} ${gx} ${by + k} V${bas} C${gx} ${milieu}, ${cx} ${milieu}, ${cx} ${haut} V${fin}`);
      chemin.setAttribute('class', `pont ${[...s.classList].find(c => c.startsWith('profil-'))}`);
      const debut = document.createElementNS(ns, 'circle');
      debut.setAttribute('cx', bx); debut.setAttribute('cy', by); debut.setAttribute('r', 3.5);
      debut.setAttribute('class', `pont-point ${[...s.classList].find(c => c.startsWith('profil-'))}`);
      calque.append(chemin, debut);
    });
  }

  // Icônes des plaques : traits simples en SVG, dessinés ici (aucune ressource extérieure).
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
  function lib(s) { return String(s).toLowerCase().replaceAll('_', ' '); }
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
