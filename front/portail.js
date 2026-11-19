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
  const centre = el('a', { classe: 'ilot ilot-centre', href: C.centre.lien, 'aria-label': `${C.centre.nom} : chercher un client et ouvrir sa vue 360°` },
    el('div', { classe: 'ilot-nom', texte: C.centre.nom }),
    el('div', { classe: 'ilot-accroche', texte: C.centre.accroche }),
    (C.centre.profils || []).length ? el('div', { classe: 'centre-profils' },
      C.centre.profils.map(p => el('span', { texte: p }))) : null,
    el('div', { classe: 'centre-chiffres', id: 'centre-chiffres' }),
    el('div', { classe: 'centre-maj', id: 'centre-maj' }));
  ajouter(centre, C.centre, 'centre');

  C.modules.forEach((m, k) => {
    const libelleEtat = { actif: 'actif', a_venir: 'à venir', source: 'source', libre: 'place libre' }[m.etat];
    const b = el('button', { type: 'button', classe: `ilot ilot-module ilot-flotte etat-${m.etat}`,
      'aria-label': `${m.nom} : ${m.accroche}` },
      el('span', { classe: 'ilot-nom' }, m.etat === 'actif' ? el('span', { classe: 'point-actif', 'aria-hidden': 'true' }) : null, m.nom),
      el('span', { classe: 'etat', texte: libelleEtat }));
    flotter(b, k + 1);
    b.addEventListener('click', () => (m.etat === 'actif' && m.lien ? (location.href = m.lien) : ouvrir(m, b, 'module')));
    ajouter(b, m, 'module');
  });

  C.usages.forEach((u, k) => {
    const b = el('button', { type: 'button', classe: `ilot ilot-usage ilot-flotte${u.enCours ? ' en-cours' : ''}`,
      'aria-label': `${u.nom} : ${u.accroche}` },
      el('span', { classe: 'numero', texte: u.n }), el('span', { classe: 'ilot-nom', texte: u.nom }));
    b.style.width = b.style.height = `${u.taille}px`;
    flotter(b, k + 7);
    b.addEventListener('click', () => ouvrir(u, b, 'usage'));
    ajouter(b, u, 'usage');
  });

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
    centreXY = { x: cx, y: cy };
    for (const i of ilots) {
      const x = i.donnee.x / 100 * L, y = i.donnee.y / 100 * H;
      i.x = x; i.y = y;
      i.element.style.left = `${x}px`;
      i.element.style.top = `${y}px`;
      if (i.genre === 'centre') continue;
      const chemin = document.createElementNS(NS, 'path');
      chemin.setAttribute('class', `courbe${i.genre === 'usage' ? ' courbe-usage' : ''}`);
      if (i.donnee.etat === 'source') chemin.setAttribute('marker-end', 'url(#fleche)');
      courbes.append(chemin);
      i.courbe = chemin;
      if (i.genre === 'usage') {                                // trait rouge qui file vers le centre à l'illumination
        const flux = document.createElementNS(NS, 'path');
        flux.setAttribute('class', 'courbe-flux');
        courbes.append(flux);
        i.flux = flux;
      }
      tracer(i);
      if (i.flux) {
        const longueur = i.flux.getTotalLength();
        i.flux.style.strokeDasharray = `${longueur}`;
        i.flux.style.setProperty('--longueur', `${longueur}`);
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
  // Courbe d'un îlot, avec son décalage éventuel (îlot saisi) et celui du centre.
  let centreXY = { x: 0, y: 0 };
  function tracer(i) {
    if (!i.courbe) return;
    const c = ilots[0];
    const x = i.x + (i.dx || 0), y = i.y + (i.dy || 0);
    const cx = centreXY.x + (c.dx || 0), cy = centreXY.y + (c.dy || 0);
    const [ax, ay, bx, by] = i.donnee.etat === 'source' ? [x, y, cx, cy] : [cx, cy, x, y];   // Reco : vers le centre
    const mx = (ax + bx) / 2 + (ay - by) * 0.18, my = (ay + by) / 2 + (bx - ax) * 0.18;
    const f = v => v.toFixed(1);
    i.courbe.setAttribute('d', `M${f(ax)},${f(ay)} Q${f(mx)},${f(my)} ${f(bx)},${f(by)}`);
    if (i.flux) i.flux.setAttribute('d', `M${f(bx)},${f(by)} Q${f(mx)},${f(my)} ${f(ax)},${f(ay)}`);
  }

  // ---- saisir une bulle : elle suit le pointeur, sa courbe aussi ; relâchée, elle revient en place (ressort) -------
  function deplacer(i, dx, dy) {
    i.dx = dx; i.dy = dy;
    i.element.style.setProperty('--dx', `${dx}px`);
    i.element.style.setProperty('--dy', `${dy}px`);
    if (i.genre === 'centre') ilots.forEach(tracer); else tracer(i);
  }
  function revenir(i) {
    cancelAnimationFrame(i.ressort);
    if (reduit.matches) { deplacer(i, 0, 0); i.element.classList.remove('saisi'); return; }
    let vx = 0, vy = 0, avant = performance.now();
    const pas = t => {
      const dt = Math.min(0.032, (t - avant) / 1000); avant = t;
      vx += (-170 * i.dx - 14 * vx) * dt; vy += (-170 * i.dy - 14 * vy) * dt;          // raideur, amortissement
      const dx = i.dx + vx * dt, dy = i.dy + vy * dt;
      if (Math.hypot(dx, dy) < 0.3 && Math.hypot(vx, vy) < 5) { deplacer(i, 0, 0); i.element.classList.remove('saisi'); return; }
      deplacer(i, dx, dy);
      i.ressort = requestAnimationFrame(pas);
    };
    i.ressort = requestAnimationFrame(pas);
  }
  for (const i of ilots) {
    const e = i.element;
    let depart = null, tire = false;
    e.setAttribute('draggable', 'false');
    e.addEventListener('dragstart', ev => ev.preventDefault());
    e.addEventListener('pointerdown', ev => {
      if (etroit.matches || ev.button !== 0) return;
      cancelAnimationFrame(i.ressort);
      depart = { x: ev.clientX - (i.dx || 0), y: ev.clientY - (i.dy || 0), px: ev.clientX, py: ev.clientY };
      tire = false;
    });
    e.addEventListener('pointermove', ev => {
      if (!depart) return;
      if (!tire && Math.hypot(ev.clientX - depart.px, ev.clientY - depart.py) < 5) return;   // un clic reste un clic
      if (!tire) { tire = true; try { e.setPointerCapture(ev.pointerId); } catch (x) { /* pointeur déjà relâché */ } e.classList.add('saisi'); }
      deplacer(i, ev.clientX - depart.x, ev.clientY - depart.y);
    });
    const lacher = () => { if (!depart) return; depart = null; if (tire) revenir(i); };
    e.addEventListener('pointerup', lacher);
    e.addEventListener('pointercancel', lacher);
    e.addEventListener('click', ev => {            // une bulle qu'on vient de déplacer ne s'ouvre pas
      if (tire) { ev.preventDefault(); ev.stopImmediatePropagation(); tire = false; }
    }, true);
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
