'use strict';

document.addEventListener('DOMContentLoaded', async () => {
  Commun.entete('carte-pg.html');
  const canvas = document.getElementById('reseau-pg');
  const ctx = canvas.getContext('2d');
  const status = document.getElementById('statut');
  const detail = document.getElementById('identite-pg');
  const filter = document.getElementById('bl-seulement');
  let nodes = [], edges = [], highlighted = new Set();
  let scale = 1, dx = 0, dy = 0, width = 1, height = 1, chosen = -1;
  let down = null, moved = false;

  // Le layout initial PostgreSQL range 5 000+ composantes en lignes très hautes.
  // Les repacker localement évite la colonne verticale lors du zoom global.
  function placerReseaux() {
    const groupes = new Map();
    nodes.forEach((n, i) => {
      if (filter.checked && !highlighted.has(i)) return;
      if (!groupes.has(n.c)) groupes.set(n.c, []);
      groupes.get(n.c).push(n);
    });
    const groupesTries = [...groupes.values()].sort((a, b) => b.length - a.length);
    const visibles = groupesTries.reduce((n, g) => n + g.length, 0);
    const taille = 20, marge = 45;
    const largeurMax = Math.max(500, Math.sqrt(visibles) * taille * 1.5);
    let x = marge, y = marge, hauteurLigne = 0;
    for (const groupe of groupesTries) {
      const colonnes = Math.max(1, Math.ceil(Math.sqrt(groupe.length)));
      const lignes = Math.ceil(groupe.length / colonnes);
      const largeur = colonnes * taille + marge;
      const hauteur = lignes * taille + marge;
      if (x + largeur > largeurMax && x > marge) {
        x = marge; y += hauteurLigne; hauteurLigne = 0;
      }
      groupe.forEach((n, i) => {
        n.x = x + (i % colonnes) * taille;
        n.y = y + Math.floor(i / colonnes) * taille;
      });
      x += largeur;
      hauteurLigne = Math.max(hauteurLigne, hauteur);
    }
  }

  function fit() {
    if (!nodes.length) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < nodes.length; i++) {
      if (filter.checked && !highlighted.has(i)) continue;
      const n = nodes[i];
      minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y);
    }
    scale = Math.min((width - 60) / Math.max(1, maxX - minX), (height - 60) / Math.max(1, maxY - minY), 2);
    dx = width / 2 - scale * (minX + maxX) / 2;
    dy = height / 2 - scale * (minY + maxY) / 2;
    draw();
  }

  function resize() {
    const r = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, r.width); height = Math.max(1, r.height);
    canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    if (!nodes.length) return;
    ctx.save(); ctx.translate(dx, dy); ctx.scale(scale, scale);
    const filtered = filter.checked;
    ctx.lineWidth = Math.max(.45, 1 / scale);
    for (const a of edges) {
      if (filtered && (!highlighted.has(a.a) || !highlighted.has(a.b))) continue;
      const p = nodes[a.a], q = nodes[a.b];
      if (!p || !q) continue;
      ctx.strokeStyle = a.type === 'liste_noire' ? '#d65757' : '#b6c4d3';
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
    }
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (filtered && !highlighted.has(i)) continue;
      ctx.fillStyle = n.bl ? '#c53945' : n.t === 'societe' ? '#3758a2' : n.t === 'dossier' ? '#8b6c52' : '#25907d';
      const radius = (i === chosen ? 6 : 3.5) / Math.max(.5, Math.sqrt(scale));
      ctx.beginPath(); ctx.arc(n.x, n.y, radius, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  function point(e) {
    const r = canvas.getBoundingClientRect();
    return {x: e.clientX - r.left, y: e.clientY - r.top};
  }
  canvas.addEventListener('pointerdown', e => {
    down = point(e); moved = false;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => {
    if (!down) return;
    const p = point(e), x = p.x - down.x, y = p.y - down.y;
    if (Math.abs(x) + Math.abs(y) > 2) moved = true;
    dx += x; dy += y; down = p; draw();
  });
  canvas.addEventListener('pointerup', async e => {
    if (!down) return;
    down = null;
    if (moved) return;
    const p = point(e);
    let index = -1, distance = 15 * 15;
    for (let i = 0; i < nodes.length; i++) {
      if (filter.checked && !highlighted.has(i)) continue;
      const n = nodes[i], x = n.x * scale + dx - p.x, y = n.y * scale + dy - p.y;
      const d = x * x + y * y;
      if (d < distance) { index = i; distance = d; }
    }
    if (index === -1) return;
    chosen = index; draw();
    const node = nodes[index];
    detail.textContent = 'Lecture de l’identité…';
    try {
      const result = await Commun.api('/api/graphe-pg/identites', {corps: {ids: [node.id]}});
      const nom = result.noms[node.id] || 'Nom non renseigné';
      detail.textContent = `${nom} · ${node.bl ? 'Entité liste noire' : node.t === 'societe' ? 'Société' : node.t === 'dossier' ? 'Dossier' : 'Personne'}`;
    } catch (error) {
      if (error.message !== 'session') detail.textContent = 'Nom indisponible : accès refusé ou erreur de publication.';
    }
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const p = point(e), factor = Math.exp(-Math.sign(e.deltaY) * .14);
    const next = Math.max(.05, Math.min(12, scale * factor));
    dx = p.x - (p.x - dx) * next / scale;
    dy = p.y - (p.y - dy) * next / scale;
    scale = next; draw();
  }, {passive: false});
  document.getElementById('tout-voir').addEventListener('click', fit);
  filter.addEventListener('change', () => {placerReseaux(); fit();});
  window.addEventListener('resize', () => {resize(); fit();});

  try {
    const [geo, stats] = await Promise.all([
      Commun.api('/api/graphe-pg/geometrie'),
      Commun.api('/api/graphe-pg/resume'),
    ]);
    if (geo.type !== 'graphe_af_postgresql' || !Array.isArray(geo.noeuds) || !Array.isArray(geo.aretes)) throw Error('format');
    nodes = geo.noeuds;
    edges = geo.aretes;
    // Conserver seulement les composantes signalées dans la couche géométrique.
    const sensitiveNetworks = new Set(geo.reseaux_bl || []);
    highlighted = new Set(nodes.flatMap((n, i) => sensitiveNetworks.has(n.c) ? [i] : []));
    filter.checked = highlighted.size > 0;
    status.textContent = `${stats.noeuds.toLocaleString('fr-FR')} nœuds · ${stats.aretes.toLocaleString('fr-FR')} liens`;
    placerReseaux(); resize(); fit();
  } catch (error) {
    if (error.message !== 'session') {
      status.textContent = error.statut === 503 ? 'Publication PostgreSQL indisponible.' :
        error.statut === 403 ? 'Accès réservé à la cellule fraude.' : 'Chargement du graphe impossible.';
    }
  }
});
