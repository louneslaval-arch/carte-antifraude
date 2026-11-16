// Portail : place les îlots, trace les courbes, anime (flottement, illumination), ouvre les panneaux.
'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const { el } = Commun;
  const C = CONTENU_PORTAIL;
  const NS = 'http://www.w3.org/2000/svg';
  const reduit = window.matchMedia('(prefers-reduced-motion: reduce)');
  const etroit = window.matchMedia('(max-width: 900px)');
  Commun.entete('index.html', true);
  document.getElementById('titre').textContent = C.titre;
  document.getElementById('introduction').textContent = C.introduction;

  const scene = document.getElementById('scene');
  const courbes = document.getElementById('courbes');
  const ilots = [];                                           // [{ element, donnee, genre, courbe }]

  // ---- tuile centrale, puis modules, puis usages : c'est aussi l'ordre de tabulation -----------------------------
  const centre = el('a', { classe: 'ilot ilot-centre', href: C.centre.lien, 'aria-label': `${C.centre.nom} : ouvrir la base client` },
    el('div', { classe: 'ilot-nom', texte: C.centre.nom }),
    el('div', { classe: 'ilot-accroche', texte: C.centre.accroche }),
    el('div', { classe: 'centre-chiffres', id: 'centre-chiffres' }),
    el('div', { classe: 'centre-maj', id: 'centre-maj' }));
  ajouter(centre, C.centre, 'centre');

  C.modules.forEach((m, k) => {
    const libelleEtat = { actif: 'actif', a_venir: 'à venir', source: 'source', libre: 'place libre' }[m.etat];
    const b = el('button', { type: 'button', classe: `ilot ilot-module ilot-flotte etat-${m.etat}`,
      'aria-label': `${m.nom} : ${m.accroche}` },
      el('span', { classe: 'ilot-nom' }, m.etat === 'actif' ? el('span', { classe: 'point-actif', 'aria-hidden': 'true' }) : null, m.nom),
      el('span', { classe: 'ilot-accroche', texte: m.accroche }),
      el('span', { classe: 'etat', texte: libelleEtat }));
    flotter(b, k + 1);
    b.addEventListener('click', () => (m.etat === 'actif' && m.lien ? (location.href = m.lien) : ouvrir(m, b, 'module')));
    ajouter(b, m, 'module');
  });

  C.usages.forEach((u, k) => {
    const b = el('button', { type: 'button', classe: `ilot ilot-usage ilot-flotte${u.enCours ? ' en-cours' : ''}`,
      'aria-label': `${u.nom} : ${u.accroche}` },
      el('span', { classe: 'numero', texte: u.n }), el('span', { classe: 'ilot-nom', texte: u.nom }),
      el('span', { classe: 'ilot-accroche', texte: u.accroche }));
    b.style.width = b.style.height = `${u.taille}px`;
    flotter(b, k + 7);
    b.addEventListener('click', () => ouvrir(u, b, 'usage'));
    ajouter(b, u, 'usage');
  });

  document.getElementById('prealables').append(...C.prealables.map(p =>
    el('li', { classe: p.n === '2' ? 'coeur' : '' }, el('span', { classe: 'n', texte: p.n }),
      el('h3', { texte: p.nom }), el('p', { texte: p.texte }))));

  function ajouter(element, donnee, genre) {
    scene.append(element);
    ilots.push({ element, donnee, genre });
  }
  function flotter(element, graine) {
    // amplitude de quelques pixels, 6 à 10 s par cycle, un décalage propre à chaque îlot
    element.style.setProperty('--duree', `${6 + ((graine * 37) % 41) / 10}s`);
    element.style.setProperty('--retard', `-${((graine * 53) % 90) / 10}s`);
    element.style.setProperty('--amplitude', `${4 + (graine % 4)}px`);
  }

  // ---- placement et courbes, recalculés au redimensionnement -------------------------------------------------------
  function placer() {
    courbes.replaceChildren();
    if (etroit.matches) { for (const i of ilots) i.element.style.left = i.element.style.top = ''; return; }
    const L = scene.clientWidth, H = scene.clientHeight;
    courbes.setAttribute('viewBox', `0 0 ${L} ${H}`);
    const cx = C.centre.x / 100 * L, cy = C.centre.y / 100 * H;
    for (const i of ilots) {
      const x = i.donnee.x / 100 * L, y = i.donnee.y / 100 * H;
      i.element.style.left = `${x}px`;
      i.element.style.top = `${y}px`;
      if (i.genre === 'centre') continue;
      const source = i.donnee.etat === 'source';                // Reco : son lien va vers le centre
      const [ax, ay, bx, by] = source ? [x, y, cx, cy] : [cx, cy, x, y];
      const mx = (ax + bx) / 2 + (ay - by) * 0.18, my = (ay + by) / 2 + (bx - ax) * 0.18;
      const d = `M${ax.toFixed(1)},${ay.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${bx.toFixed(1)},${by.toFixed(1)}`;
      const chemin = document.createElementNS(NS, 'path');
      chemin.setAttribute('d', d);
      chemin.setAttribute('class', `courbe${i.genre === 'usage' ? ' courbe-usage' : ''}`);
      if (source) chemin.setAttribute('marker-end', 'url(#fleche)');
      courbes.append(chemin);
      i.courbe = chemin;
      if (i.genre === 'usage') {                                // trait rouge qui file vers le centre à l'illumination
        const flux = document.createElementNS(NS, 'path');
        flux.setAttribute('d', `M${bx.toFixed(1)},${by.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${ax.toFixed(1)},${ay.toFixed(1)}`);
        flux.setAttribute('class', 'courbe-flux');
        courbes.append(flux);
        const longueur = flux.getTotalLength();
        flux.style.strokeDasharray = `${longueur}`;
        flux.style.setProperty('--longueur', `${longueur}`);
        i.flux = flux;
      }
    }
    const defs = document.createElementNS(NS, 'defs');
    const marqueur = document.createElementNS(NS, 'marker');
    for (const [k, v] of Object.entries({ id: 'fleche', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto' })) marqueur.setAttribute(k, v);
    const pointe = document.createElementNS(NS, 'path');
    pointe.setAttribute('d', 'M0,0 L10,5 L0,10 z');
    pointe.setAttribute('fill', 'rgba(255,255,255,.4)');
    marqueur.append(pointe);
    defs.append(marqueur);
    courbes.prepend(defs);
  }
  for (const i of ilots) {
    const actif = on => i.courbe && i.courbe.classList.toggle('active', on);
    i.element.addEventListener('mouseenter', () => actif(true));
    i.element.addEventListener('mouseleave', () => actif(false));
    i.element.addEventListener('focus', () => actif(true));
    i.element.addEventListener('blur', () => actif(false));
  }
  let attente = null;
  window.addEventListener('resize', () => { clearTimeout(attente); attente = setTimeout(placer, 120); });
  etroit.addEventListener('change', placer);
  placer();

  // ---- illumination : un usage au hasard toutes les 1,5 à 2 s, un seul à la fois --------------------------------------
  let survol = false, panneauOuvert = false, minuterie = null, precedent = null;
  scene.addEventListener('mouseenter', () => { survol = true; });
  scene.addEventListener('mouseleave', () => { survol = false; });
  function cycle() {
    clearTimeout(minuterie);
    if (reduit.matches || document.hidden) return;
    minuterie = setTimeout(() => {
      if (!survol && !panneauOuvert && !etroit.matches) {
        const usages = ilots.filter(i => i.genre === 'usage' && i !== precedent);
        const choisi = usages[Math.floor(Math.random() * usages.length)];
        precedent = choisi;
        choisi.element.classList.add('illumine');
        if (choisi.flux) { choisi.flux.classList.remove('anime'); void choisi.flux.getBBox(); choisi.flux.classList.add('anime'); }
        setTimeout(() => choisi.element.classList.remove('illumine'), 1200);
      }
      cycle();
    }, 1500 + Math.random() * 500);
  }
  document.addEventListener('visibilitychange', () => {
    for (const i of ilots) i.element.style.animationPlayState = document.hidden ? 'paused' : '';
    cycle();
  });
  reduit.addEventListener('change', cycle);
  cycle();

  // ---- panneau de détail -------------------------------------------------------------------------------------------
  const panneau = document.getElementById('panneau'), voile = document.getElementById('voile');
  let declencheur = null;
  function ouvrir(d, bouton, genre) {
    declencheur = bouton;
    panneauOuvert = true;
    const etat = genre === 'usage' ? (d.enCours ? 'usage · en cours' : `usage ${d.n}`)
      : ({ actif: 'module actif', a_venir: 'module à venir', source: 'source de la base', libre: 'place libre' })[d.etat];
    document.getElementById('panneau-etat').textContent = etat;
    document.getElementById('panneau-titre').textContent = d.nom;
    document.getElementById('panneau-accroche').textContent = d.accroche;
    document.getElementById('panneau-contexte').textContent = d.contexte;
    document.getElementById('panneau-usages').replaceChildren(...(d.usages.length ? d.usages : [{ nom: 'À définir avec les métiers' }]).map(u =>
      el('li', {}, el('span', { texte: u.nom }),
        u.etat ? el('span', { classe: `marque-etat${u.etat === 'en cours' ? ' en-cours' : ''}`, texte: u.etat }) : null)));
    document.getElementById('panneau-donnees').replaceChildren(...(d.donnees.length ? d.donnees : [{ nom: '—', source: '' }]).map(x =>
      el('li', {}, el('span', { texte: x.nom }), el('span', { classe: 'source', texte: x.source }))));
    const lien = document.getElementById('panneau-lien');
    lien.replaceChildren(d.lien ? el('a', { classe: 'bouton-portail', href: d.lien, texte: `Ouvrir ${d.nom}` }) : '');
    panneau.hidden = voile.hidden = false;
    panneau.focus();
  }
  function fermer() {
    if (panneau.hidden) return;
    panneau.hidden = voile.hidden = true;
    panneauOuvert = false;
    if (declencheur) declencheur.focus();
  }
  document.getElementById('fermer').addEventListener('click', fermer);
  voile.addEventListener('click', fermer);
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') fermer();
    if (ev.key === 'Tab' && !panneau.hidden) {                // le focus reste dans le panneau ouvert
      const focusables = [...panneau.querySelectorAll('button, a[href]')];
      const premier = focusables[0], dernier = focusables[focusables.length - 1];
      if (ev.shiftKey && document.activeElement === premier) { ev.preventDefault(); dernier.focus(); }
      else if (!ev.shiftKey && document.activeElement === dernier) { ev.preventDefault(); premier.focus(); }
    }
  });

  // ---- chiffres agrégés de la tuile centrale (jamais sous 5, aucun nom) ---------------------------------------------
  (async () => {
    const zone = document.getElementById('centre-chiffres');
    try {
      const r = await Commun.api('/api/base/resume', { sansRedirection: true });
      zone.replaceChildren(
        el('div', {}, el('strong', { texte: Commun.nombre(r.clients) }), el('span', { texte: 'clients' })),
        el('div', {}, el('strong', { texte: Commun.nombre(r.dossiers) }), el('span', { texte: 'dossiers' })),
        el('div', {}, el('strong', { texte: Commun.nombre(r.inscrits) }), el('span', { texte: 'inscrits' })));
      document.getElementById('centre-maj').textContent = `mise à jour ${Commun.date(r.mise_a_jour)}`;
    } catch (e) {
      zone.replaceChildren(el('span', { classe: 'centre-maj', texte: 'Connectez-vous pour voir les chiffres' }));
    }
  })();
});
