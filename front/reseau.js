'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api } = Commun;
  Commun.entete('reseau.html');
  const NS = 'http://www.w3.org/2000/svg';
  const scene = document.getElementById('scene');
  const indice = Commun.parametre('i');

  if (Commun.role() !== 'ANALYSTE') {
    document.getElementById('sous-titre').textContent = 'La carte des réseaux est réservée à la cellule fraude.';
    scene.hidden = true;
    return;
  }
  const choix = document.getElementById('choix');
  const select = document.getElementById('client');
  choix.hidden = false;
  // Clients reliés à la liste noire (à 3 liens au plus), par ordre alphabétique ; les niveaux restent masqués.
  const relies = [];
  for (const niveau of ['critique', 'majeure', 'mineure']) {
    const r = await api('/api/base/clients', { corps: { niveau, taille: 200, tri: 'alpha' } });
    relies.push(...r.items);
  }
  relies.sort((a, b) => a.nom.localeCompare(b.nom, 'fr'));
  for (const c of relies) select.append(el('option', { value: c.indice, texte: c.nom }));
  select.addEventListener('change', () => { if (select.value) location.href = `reseau.html?i=${select.value}`; });
  if (!indice) {
    if (select.options.length > 1) location.replace(`reseau.html?i=${select.options[1].value}`);
    return;
  }
  select.value = indice;
  if (select.value !== indice) select.append(el('option', { value: indice, texte: 'Client affiché', selected: true }));
  let r;
  try {
    r = await api(`/api/base/reseau/${encodeURIComponent(indice)}`);
  } catch (e) {
    document.getElementById('sous-titre').textContent = Commun.erreur(e, 'Réseau');
    scene.hidden = true;
    return;
  }
  const depart = r.noeuds.find(n => n.depart);
  document.getElementById('titre').textContent = `Réseau de ${depart ? depart.nom : 'ce client'}`;
  dessiner(r);

  function dessiner({ noeuds, liens }) {
    const L = scene.clientWidth || 1000, H = scene.clientHeight || 640;
    scene.setAttribute('viewBox', `0 0 ${L} ${H}`);
    const parId = new Map(noeuds.map((n, k) => {
      const angle = k * 2.399963;                                   // angle d'or : départ déterministe
      const rayon = n.depart ? 0 : 90 + n.niveau * 150 + (k % 5) * 6;
      return [String(n.id), Object.assign(n, { x: L / 2 + rayon * Math.cos(angle), y: H / 2 + rayon * Math.sin(angle), vx: 0, vy: 0 })];
    }));
    const aretes = liens.map(l => ({ a: parId.get(String(l.de)), b: parId.get(String(l.vers)), code: l.code })).filter(l => l.a && l.b);
    for (let pas = 0; pas < 320; pas++) {                          // simulation de forces simple, sans bibliothèque
      const t = 1 - pas / 320;
      for (const a of noeuds) for (const b of noeuds) {
        if (a === b) continue;
        const dx = a.x - b.x, dy = a.y - b.y, d2 = Math.max(dx * dx + dy * dy, 25);
        const f = 5200 / d2;
        a.vx += dx / Math.sqrt(d2) * f; a.vy += dy / Math.sqrt(d2) * f;
      }
      for (const { a, b } of aretes) {
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.max(Math.hypot(dx, dy), 1), f = (d - 150) * 0.02;
        a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
      }
      for (const n of noeuds) {
        n.vx += (L / 2 - n.x) * 0.002; n.vy += (H / 2 - n.y) * 0.002;
        if (n.depart) { n.vx = 0; n.vy = 0; continue; }
        n.x = Math.min(L - 30, Math.max(30, n.x + n.vx * t)); n.y = Math.min(H - 24, Math.max(24, n.y + n.vy * t));
        n.vx *= 0.55; n.vy *= 0.55;
      }
      for (const a of noeuds) for (const b of noeuds) {            // écart minimal : aucun nœud ne recouvre un autre
        if (a === b || a.depart) continue;
        const dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) || 1, min = 72;
        if (d < min) { const p = (min - d) / (b.depart ? 1 : 2); a.x += dx / d * p; a.y += dy / d * p; }
      }
    }
    const groupeLiens = svg('g'), groupeNoeuds = svg('g');
    scene.replaceChildren(groupeLiens, groupeNoeuds);
    const traits = aretes.map(l => {
      const ligne = svg('line', { stroke: l.code === 'RIB' ? '#e2541c' : '#c3c8d6', 'stroke-width': l.code === 'RIB' ? 2 : 1.4,
        'stroke-dasharray': l.code === 'homonymie' ? '4 4' : null });
      ligne.append(svg('title', {}, l.code));
      groupeLiens.append(ligne);
      return [ligne, l];
    });
    const formes = noeuds.map(n => {
      const g = svg('g', { class: 'noeud', tabindex: n.type === 'identifiant' ? null : 0, role: n.type === 'identifiant' ? null : 'link',
        'aria-label': n.type === 'identifiant' ? null : `${n.nom}${n.inscrit ? ', inscrit' : ''}` });
      const couleur = n.depart ? '#14161f' : n.inscrit ? '#EE3B45' : n.type === 'societe' ? '#8b92a8' : n.type === 'identifiant' ? '#c3c8d6' : '#4a4f63';
      const taille = n.depart ? 13 : n.inscrit ? 11 : 8;
      const forme = n.type === 'societe' ? svg('rect', { x: -taille, y: -taille, width: taille * 2, height: taille * 2, rx: 3, fill: couleur })
        : n.type === 'identifiant' ? svg('rect', { x: -6, y: -6, width: 12, height: 12, fill: couleur, transform: 'rotate(45)' })
        : svg('circle', { r: taille, fill: couleur });
      if (n.depart) forme.setAttribute('stroke', '#d6d9e3'), forme.setAttribute('stroke-width', 5);
      g.append(forme);
      if (n.type !== 'identifiant' || n.niveau === 0) {
        g.append(svg('text', { y: taille + 14, 'text-anchor': 'middle', 'font-size': n.depart || n.inscrit ? 12 : 10.5,
          'font-weight': n.depart || n.inscrit ? 700 : 500, fill: n.inscrit ? '#b4141e' : '#4a4f63' }, raccourcir(n.nom)));
      } else {
        g.append(svg('title', {}, `même ${n.nom.toLowerCase()}`));
      }
      if (n.autres) {                                 // nœud replié : ses autres voisins ne sont que comptés
        g.append(svg('text', { y: taille + 27, 'text-anchor': 'middle', 'font-size': 10, fill: '#7a8096' },
          `+ ${n.autres} autre${n.autres > 1 ? 's' : ''} non affiché${n.autres > 1 ? 's' : ''}`));
      }
      if (n.type !== 'identifiant') {
        const ouvrir = () => { location.href = `fiche.html?i=${n.id}`; };
        g.addEventListener('click', ev => { if (!g.deplace) ouvrir(); g.deplace = false; ev.stopPropagation(); });
        g.addEventListener('keydown', ev => { if (ev.key === 'Enter') ouvrir(); });
      }
      glisser(g, n);
      groupeNoeuds.append(g);
      return [g, n];
    });
    function placer() {
      for (const [ligne, l] of traits) {
        ligne.setAttribute('x1', l.a.x); ligne.setAttribute('y1', l.a.y); ligne.setAttribute('x2', l.b.x); ligne.setAttribute('y2', l.b.y);
      }
      for (const [g, n] of formes) g.setAttribute('transform', `translate(${n.x.toFixed(1)} ${n.y.toFixed(1)})`);
    }
    function glisser(g, n) {
      g.addEventListener('pointerdown', ev => {
        g.setPointerCapture(ev.pointerId);
        const bouger = e => {
          const p = scene.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
          const q = p.matrixTransform(scene.getScreenCTM().inverse());
          n.x = q.x; n.y = q.y; g.deplace = true; placer();
        };
        g.addEventListener('pointermove', bouger);
        g.addEventListener('pointerup', () => g.removeEventListener('pointermove', bouger), { once: true });
      });
    }
    placer();
  }
  function svg(balise, attributs = {}, texte) {
    const n = document.createElementNS(NS, balise);
    for (const [k, v] of Object.entries(attributs)) if (v !== null && v !== undefined) n.setAttribute(k, v);
    if (texte !== undefined) n.textContent = texte;
    return n;
  }
  function raccourcir(t) { return t && t.length > 24 ? `${t.slice(0, 22)}…` : t; }
});
