// Carte antifraude : la carte globale (modèle pipeline/carte_globale_modele.html), servie par l'API en deux couches.
// La couche 1 (positions, types, liens, villes) arrive d'un bloc, sans aucun nom ; les noms, les fiches et la recherche
// sont demandés au moment de les montrer (cellule fraude, comptés, inscrits au journal). Même dessin, mêmes filtres et
// mêmes gestes que le modèle. Aucune ressource externe ; aucun gestionnaire d'événement écrit dans le HTML (CSP).
'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  Commun.entete('carte.html');
  const $ = (s) => document.querySelector(s);
  function message(texte) { const m = $('#message'); m.textContent = texte; m.hidden = false; }
  let D;
  try {
    D = await Commun.api('/api/carte/globale');
  } catch (e) {
    $('#outils').hidden = true;
    $('#legende').hidden = true;
    if (e.statut === 403) message('La carte antifraude est réservée à la cellule fraude.');
    else if (e.statut === 503) message('Aucune carte globale n’est chargée sur ce serveur.');
    else if (e.statut === 429) message('Trop de consultations pour l’heure : réessayez dans quelques minutes.');
    else if (e.message !== 'session') message('La carte ne répond pas. Réessayez.');
    return;
  }
  const cv = $('#toile'), ctx = cv.getContext('2d');
  const N = D.noeuds, A = D.aretes, NB = N.length, G = D.geo || null;
  N.forEach((n, i) => { n.i = i; });
  const adj = Array.from({ length: NB }, () => []);
  A.forEach((a, k) => { adj[a.a].push(k); adj[a.b].push(k); });
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  let C = {};
  function lireCouleurs() { C = { ligne: css('--ligne'), accent: css('--accent'), alerte: css('--alerte'), alerteDoux: css('--alerte-doux'), pont: css('--pont'), doux: css('--doux'), carte: css('--carte'), texte: css('--texte'), fond: css('--fond'), accentDoux: css('--accent-doux'), dossier: css('--dossier'), dossierDoux: css('--dossier-doux'), deux: css('--deux'), deuxDoux: css('--deux-doux'), plateau: css('--plateau'), plateauBord: css('--plateau-bord'), plateauBas: css('--plateau-bas'), ville: css('--ville'), cote: css('--cote'), coteBas: css('--cote-bas') }; }
  lireCouleurs();
  // coordonnées monde selon la vue : réseau (x, y) ou carte du Maroc (mx, my)
  const XR = new Float64Array(NB), YR = new Float64Array(NB), XM = new Float64Array(NB), YM = new Float64Array(NB);
  for (let i = 0; i < NB; i++) { XR[i] = N[i].x; YR[i] = N[i].y; XM[i] = N[i].mx ?? N[i].x; YM[i] = N[i].my ?? N[i].y; }
  const XM0 = Float64Array.from(XM), YM0 = Float64Array.from(YM);   // positions Maroc d'origine (avant étalement)
  let X = XR, Y = YR;
  const etat = { k: 1, tx: 0, ty: 0, choisi: -1, survol: -1, isole: -1, seuil: 0, mode: 'reseau', pente: 0, yaw: 0, cp: 1, sp: 0, lat: false };
  let visN = new Uint8Array(NB), visA = [];
  // positions écran du dernier dessin : SXg/SYg au sol (pour les liens), SX/SY du point (haut de l'épingle)
  const SXg = new Float32Array(NB), SYg = new Float32Array(NB), SX = new Float32Array(NB), SY = new Float32Array(NB);
  const maroc = () => etat.mode === 'maroc';

  // ---- noms et fiches, demandés à l'API au moment de les montrer -------------------------------------------------
  const noms = new Map();                        // indice → { nom, lat }, gardés pour la séance
  const fiches = new Map();                      // indice → fiche complète
  const fichesEnCours = new Map();               // indice → demande en cours (une seule par fiche)
  const fichesEnErreur = new Map();              // indice → message, tant que le nœud reste choisi
  const enAttente = new Set(), enVol = new Set();
  let minuterieNoms = null, demandeEnCours = false, pause = 0;
  function demanderNoms(indices) {
    for (const i of indices) if (!noms.has(i) && !enVol.has(i)) enAttente.add(i);
    if (enAttente.size && !minuterieNoms) minuterieNoms = setTimeout(chargerNoms, Math.max(120, pause - Date.now()));
  }
  async function chargerNoms() {
    minuterieNoms = null;
    if (demandeEnCours) { minuterieNoms = setTimeout(chargerNoms, 200); return; }
    const lot = [...enAttente].filter((i) => !noms.has(i)).slice(0, 400);
    enAttente.clear();
    if (!lot.length) return;
    demandeEnCours = true;
    lot.forEach((i) => enVol.add(i));
    try {
      const r = await Commun.api('/api/carte/globale/noms', { corps: { indices: lot } });
      for (const i of lot) noms.set(i, r[String(i)] || { nom: null, lat: null });
    } catch (e) {
      if (e.statut === 429 && /quota/i.test(e.detail || '')) {
        for (const i of lot) noms.set(i, { nom: null, lat: null });    // quota de l'heure atteint : plus de noms
      } else if (e.message !== 'session') {
        pause = Date.now() + 5000;                                     // débit ou réseau : on reprend plus tard
        lot.forEach((i) => enAttente.add(i));
      }
    } finally {
      lot.forEach((i) => enVol.delete(i));
      demandeEnCours = false;
      dessiner();
      if (etat.choisi >= 0) panneau(etat.choisi);
      if (enAttente.size && !minuterieNoms) minuterieNoms = setTimeout(chargerNoms, Math.max(50, pause - Date.now()));
    }
  }
  function erreurCarte(e, objet) {
    if (e.statut === 403) return `${objet} réservée à la cellule fraude.`;
    if (e.statut === 404) return `${objet} introuvable.`;
    if (e.statut === 429) return 'Trop de consultations pour l\u2019heure : réessayez dans quelques minutes.';
    if (e.statut === 503) return 'Aucune carte globale n\u2019est chargée sur ce serveur.';
    return 'La carte ne répond pas. Réessayez.';
  }
  const nomDe = (n) => { const x = noms.get(n.i); return x && x.nom ? x : null; };

  function angles() { etat.cp = Math.cos(etat.pente); etat.sp = Math.sin(etat.pente); }
  // projection : rotation autour de la verticale, puis inclinaison du plan (orthographique). z vers le haut.
  function proj(x, y, z) {
    const cy = Math.cos(etat.yaw), sy = Math.sin(etat.yaw);
    const xr = x * cy - y * sy, yr = x * sy + y * cy;
    return [xr * etat.k + etat.tx, (yr * etat.cp - (z || 0) * etat.sp) * etat.k + etat.ty];
  }
  function deproj(px, py) {
    const xr = (px - etat.tx) / etat.k, yr = (py - etat.ty) / (etat.k * etat.cp);
    const cy = Math.cos(etat.yaw), sy = Math.sin(etat.yaw);
    return [xr * cy + yr * sy, -xr * sy + yr * cy];
  }

  function filtrer() {
    const forig = $('#f-orig').value; const fbl = $('#f-bl').checked, fcert = $('#f-cert').checked, fanc = $('#f-anc').checked, ns = +$('#f-ns').value;
    const okA = new Uint8Array(A.length);
    A.forEach((a, k) => { okA[k] = (a.force >= etat.seuil && !(fanc && a.style.includes('ancien'))) ? 1 : 0; });
    // liste noire seulement : nœuds à moins de « rayon » arêtes d'un élément de la liste noire
    let dist = null;
    if (fbl) {
      const rayon = +$('#f-rayon').value; dist = new Int16Array(NB).fill(-1); let file = [];
      for (let i = 0; i < NB; i++) if (N[i].bl) { dist[i] = 0; file.push(i); }
      for (let d = 0; d < rayon && file.length; d++) { const suiv = []; for (const i of file) for (const e of adj[i]) { if (!okA[e]) continue; const j = A[e].a === i ? A[e].b : A[e].a; if (dist[j] < 0) { dist[j] = d + 1; suiv.push(j); } } file = suiv; }
    }
    visN = new Uint8Array(NB);
    for (let i = 0; i < NB; i++) {
      const n = N[i];
      if (fbl && dist[i] < 0) continue;
      if (etat.isole >= 0 && n.c !== etat.isole) continue;
      if (n.t === 'personne' && !n.bl && (n.ns || 1) < ns) continue;
      if (forig && n.t !== 'inscrit' && !(forig === 'd' ? (n.o === 'd' || n.o === 'rd') : forig === 'dd' ? n.o === 'd' : n.o === forig)) continue;
      if (n.t === 'inscrit' && fcert && !n.certain) continue;
      visN[i] = 1;
    }
    // départs certains seulement : on ne garde que les réseaux où subsiste un inscrit
    if (fcert) {
      const comps = new Set(); for (let i = 0; i < NB; i++) if (visN[i] && N[i].t === 'inscrit') comps.add(N[i].c);
      for (let i = 0; i < NB; i++) if (visN[i] && !comps.has(N[i].c)) visN[i] = 0;
    }
    visA = [];
    A.forEach((a, k) => { if (okA[k] && visN[a.a] && visN[a.b]) visA.push(k); });
    // une société ou une personne sans plus aucun lien visible n'est gardée que si elle est de la liste noire
    const deg = new Uint16Array(NB); for (const k of visA) { deg[A[k].a]++; deg[A[k].b]++; }
    for (let i = 0; i < NB; i++) if (visN[i] && !deg[i] && (!N[i].bl || (forig && N[i].t === 'inscrit'))) visN[i] = 0;
    etaler(); chiffres(); dessiner();
  }
  // vue Maroc, réseau isolé : les nœuds du réseau, serrés dans le disque de leur ville, sont étalés sur le disque pour être lisibles
  function etaler() {
    XM.set(XM0); YM.set(YM0);
    if (!G || !maroc() || etat.isole < 0) return;
    const grp = new Map();
    for (let i = 0; i < NB; i++) if (visN[i]) { const v = N[i].ville || '__cote__'; if (!grp.has(v)) grp.set(v, []); grp.get(v).push(i); }
    for (const [v, ids] of grp) {
      if (ids.length < 2) continue;
      const ville = v === '__cote__' ? G.cote : G.villes.find((w) => w.code === v); if (!ville) continue;
      let cx = 0, cy = 0; for (const i of ids) { cx += XM0[i]; cy += YM0[i]; } cx /= ids.length; cy /= ids.length;
      let ext = 0; for (const i of ids) ext = Math.max(ext, Math.hypot(XM0[i] - cx, YM0[i] - cy));
      const f = ext > 0 ? Math.min(200, 0.75 * ville.r / ext) : 1; if (f <= 1) continue;
      for (const i of ids) { XM[i] = ville.x + (XM0[i] - cx) * f; YM[i] = ville.y + (YM0[i] - cy) * f; }
    }
  }
  const villeN = new Map();                       // ville → [nœuds visibles, dont liste noire]
  let coteN = 0;
  function chiffres() {
    let ins = 0, so = 0, pe = 0, bl = 0, sansVille = 0; const comps = new Set(); villeN.clear();
    for (let i = 0; i < NB; i++) { if (!visN[i]) continue; const n = N[i]; comps.add(n.c); if (n.t === 'inscrit') ins++; else if (n.t === 'societe') so++; else pe++; if (n.bl && n.t !== 'inscrit') bl++; if (!n.ville) sansVille++;
      const v = villeN.get(n.ville) || [0, 0]; v[0]++; if (n.bl) v[1]++; villeN.set(n.ville, v); }
    coteN = sansVille;
    $('#chiffres').innerHTML = `<span class="chiffre"><b>${so.toLocaleString('fr-FR')}</b> sociétés</span> &nbsp; <span class="chiffre"><b>${pe.toLocaleString('fr-FR')}</b> personnes</span> &nbsp; <span class="chiffre"><b>${visA.length.toLocaleString('fr-FR')}</b> liens</span> &nbsp; <span class="chiffre"><b>${comps.size.toLocaleString('fr-FR')}</b> réseaux</span> &nbsp; <span class="chiffre rouge"><b>${ins}</b> inscrits, <b>${bl}</b> sociétés et personnes de la liste noire</span>` + (maroc() ? ` &nbsp; <span class="chiffre"><b>${sansVille.toLocaleString('fr-FR')}</b> sans ville connue</span>` : '');
  }
  function taille() { const r = cv.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1; cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }
  function rayon(n) { return (n.t === 'inscrit' ? 5 : 3.2) + Math.min(7, Math.sqrt(n.deg || 1) * 1.3); }

  function cheminSol(pts, z) { ctx.beginPath(); for (let i = 0; i < pts.length; i++) { const [sx, sy] = proj(pts[i][0], pts[i][1], z); if (i) ctx.lineTo(sx, sy); else ctx.moveTo(sx, sy); } ctx.closePath(); }
  function disque(cx, cy, r, z) { const pts = []; for (let i = 0; i < 40; i++) { const a = i / 40 * Math.PI * 2; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); } cheminSol(pts, z); }
  function dessinerPlateau(W, H) {
    if (!G) return;
    const k = etat.k, h = etat.sp > 0.05 ? 11 / (k * etat.sp) : 0;        // épaisseur du plateau : 11 px à l'écran
    ctx.lineJoin = 'round';
    // zone « sans ville connue », à droite de la carte
    const c = G.cote;
    if (c && coteN) {
      if (h) { ctx.fillStyle = C.coteBas; disque(c.x, c.y, c.r, -h); ctx.fill(); }
      ctx.fillStyle = C.cote; ctx.strokeStyle = C.ligne; ctx.lineWidth = 0.8; disque(c.x, c.y, c.r, 0); ctx.fill(); ctx.stroke();
    }
    // socle puis dessus des régions : la partie visible du socle fait l'épaisseur
    if (h) { ctx.fillStyle = C.plateauBas; for (const r of G.regions) { cheminSol(r.pts, -h); ctx.fill(); } }
    ctx.fillStyle = C.plateau; ctx.strokeStyle = C.plateauBord; ctx.lineWidth = Math.min(1, 0.4 + k * 0.2);
    for (const r of G.regions) { cheminSol(r.pts, 0); ctx.fill(); ctx.stroke(); }
    // disques des villes
    ctx.globalAlpha = 0.22; ctx.fillStyle = C.ville;
    for (const v of G.villes) { if (v.r * k < 2 || !villeN.has(v.code)) continue; const [sx, sy] = proj(v.x, v.y, 0); if (sx < -200 || sx > W + 200 || sy < -200 || sy > H + 200) continue; disque(v.x, v.y, v.r, 0); ctx.fill(); }
    ctx.globalAlpha = 1;
  }
  function etiquettesVilles(W, H) {
    if (!G) return;
    const k = etat.k; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.lineJoin = 'round';
    const tri = G.villes.filter((v) => villeN.has(v.code)).map((v) => [v, ...villeN.get(v.code)]).sort((a, b) => b[1] - a[1]);
    tri.forEach(([v, n, bl], i) => {
      if (i >= 14 && v.r * k < 9 && !bl) return;
      const [sx, sy] = proj(v.x, v.y - v.r, 0);
      if (sx < -60 || sx > W + 60 || sy < -20 || sy > H + 20) return;
      const taillePolice = Math.round(Math.max(10, Math.min(15, 9 + v.r * k * 0.08)));
      ctx.font = `600 ${taillePolice}px sans-serif`;
      const t = `${v.nom} · ${n.toLocaleString('fr-FR')}${bl ? ' · ' + bl + ' LN' : ''}`;
      ctx.strokeStyle = C.fond; ctx.lineWidth = 3; ctx.strokeText(t, sx, sy - 2); ctx.fillStyle = bl ? C.alerte : C.ville; ctx.fillText(t, sx, sy - 2);
    });
    const c = G.cote;
    if (c && coteN) { const [sx, sy] = proj(c.x, c.y - c.r, 0); ctx.font = '600 12px sans-serif'; const t = `Sans ville connue · ${coteN.toLocaleString('fr-FR')}`; ctx.strokeStyle = C.fond; ctx.lineWidth = 3; ctx.strokeText(t, sx, sy - 2); ctx.fillStyle = C.doux; ctx.fillText(t, sx, sy - 2); }
  }

  function dessiner() {
    const r = cv.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(r.width * dpr) || cv.height !== Math.round(r.height * dpr)) taille();
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height); ctx.restore();
    const k = etat.k, W = r.width, H = r.height, m3 = maroc();
    const focus = etat.choisi >= 0 ? etat.choisi : etat.survol;
    const proches = new Set();
    if (focus >= 0) { proches.add(focus); for (const e of adj[focus]) { proches.add(A[e].a); proches.add(A[e].b); } }
    const loin = k < (m3 ? 1.2 : 0.35);
    if (m3) dessinerPlateau(W, H);
    // positions écran de tous les nœuds visibles ; en vue Maroc, les éléments de la liste noire sont dressés sur une épingle
    const cy = Math.cos(etat.yaw), sy = Math.sin(etat.yaw), cp = etat.cp;
    const epingle = m3 && !loin ? 12 : (m3 ? 4 : 0);
    for (let i = 0; i < NB; i++) {
      if (!visN[i]) continue;
      const x = X[i], y = Y[i];
      const gx = (x * cy - y * sy) * k + etat.tx, gy = (x * sy + y * cy) * cp * k + etat.ty;
      SXg[i] = gx; SYg[i] = gy; SX[i] = gx; SY[i] = N[i].bl ? gy - epingle : gy;
    }
    // arêtes, groupées par style pour limiter les changements d'état ; en vue Maroc les liens entre villes sont des arcs
    const groupes = { base: [], ancien: [], certain: [], rap: [], dim: [] }, arcs = { base: [], ancien: [], certain: [], rap: [], dim: [] };
    for (const e of visA) {
      const a = A[e];
      const x1 = SXg[a.a], y1 = SYg[a.a], x2 = SXg[a.b], y2 = SYg[a.b];
      if ((x1 < -10 && x2 < -10) || (x1 > W + 10 && x2 > W + 10) || (y1 < -10 && y2 < -10) || (y1 > H + 10 && y2 > H + 10)) continue;
      const dim = focus >= 0 && !(a.a === focus || a.b === focus);
      const g = dim ? 'dim' : a.style.includes('certain') ? 'certain' : a.style.includes('rap') ? 'rap' : a.style.includes('ancien') ? 'ancien' : 'base';
      if (m3) {
        const dx = X[a.a] - X[a.b], dy = Y[a.a] - Y[a.b], d = Math.hypot(dx, dy);
        if (d > 40) { const [mx, my] = proj((X[a.a] + X[a.b]) / 2, (Y[a.a] + Y[a.b]) / 2, Math.min(60, d * 0.12)); arcs[g].push(x1, y1, mx, my, x2, y2); continue; }
      }
      groupes[g].push(x1, y1, x2, y2);
    }
    const trace = (pts, col, w, dash, alpha) => { if (!pts.length) return; ctx.globalAlpha = alpha; ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath(); for (let i = 0; i < pts.length; i += 4) { ctx.moveTo(pts[i], pts[i + 1]); ctx.lineTo(pts[i + 2], pts[i + 3]); } ctx.stroke(); };
    const traceArcs = (pts, col, w, dash, alpha) => { if (!pts.length) return; ctx.globalAlpha = alpha; ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath(); for (let i = 0; i < pts.length; i += 6) { ctx.moveTo(pts[i], pts[i + 1]); ctx.quadraticCurveTo(pts[i + 2], pts[i + 3], pts[i + 4], pts[i + 5]); } ctx.stroke(); };
    const lw = Math.max(0.5, Math.min(1.6, k));
    trace(groupes.dim, C.ligne, lw, [], 0.08);
    trace(groupes.base, C.ligne, lw, [], loin ? 0.45 : 0.8);
    trace(groupes.ancien, C.doux, lw, loin ? [] : [2, 4], 0.6);
    trace(groupes.rap, C.accent, lw * 1.3, loin ? [] : [5, 4], 0.9);
    trace(groupes.certain, C.accent, lw * 2, [], 0.95);
    if (m3) {
      const la = Math.max(0.7, Math.min(1.8, k * 1.2));
      traceArcs(arcs.dim, C.pont, la, [], 0.06);
      traceArcs(arcs.base, C.pont, la, [], arcs.base.length > 30000 ? 0.035 : arcs.base.length > 6000 ? 0.07 : 0.5);
      traceArcs(arcs.ancien, C.pont, la, [2, 4], 0.4);
      traceArcs(arcs.rap, C.accent, la * 1.3, [5, 4], 0.9);
      traceArcs(arcs.certain, C.accent, la * 2, [], 0.95);
    }
    ctx.setLineDash([]);
    // épingles (vue Maroc) puis nœuds
    if (m3 && epingle) {
      ctx.globalAlpha = 0.9; ctx.strokeStyle = C.alerte; ctx.lineWidth = 1; ctx.beginPath();
      for (let i = 0; i < NB; i++) { if (!visN[i] || !N[i].bl) continue; const x = SXg[i], y = SYg[i]; if (x < -12 || x > W + 12 || y < -12 || y > H + 12) continue; ctx.moveTo(x, y); ctx.lineTo(x, SY[i]); }
      ctx.stroke();
    }
    const etiquettes = [];
    for (let i = 0; i < NB; i++) {
      if (!visN[i]) continue;
      const n = N[i]; const x = SX[i], y = SY[i];
      if (x < -12 || x > W + 12 || y < -12 || y > H + 12) continue;
      const inscrit = n.t === 'inscrit', bl = !!n.bl && !inscrit;
      const rad = loin ? Math.max(inscrit ? 3.2 : (n.bl ? 2.4 : (n.o && n.o !== 'r' ? 1.8 : 1.0)), rayon(n) * k) : rayon(n) * Math.min(1.6, Math.max(0.5, k));
      ctx.globalAlpha = focus >= 0 && !proches.has(i) ? 0.18 : 1;
      // couleur d'origine : registre (gris), dossiers de l'antifraude (vert), les deux (violet) ; la liste noire reste rouge
      const oc = n.o === 'd' ? C.dossier : n.o === 'rd' ? C.deux : C.ligne, od = n.o === 'd' ? C.dossierDoux : n.o === 'rd' ? C.deuxDoux : C.carte;
      ctx.fillStyle = inscrit ? C.alerte : bl ? (loin ? C.alerte : C.alerteDoux) : (loin ? oc : od);
      ctx.strokeStyle = inscrit || bl ? C.alerte : (i === etat.choisi ? C.accent : oc);
      ctx.lineWidth = i === etat.choisi ? 3 : (bl ? 1.8 : (n.o && n.o !== 'r' ? 1.8 : 1.1));
      ctx.beginPath();
      if (n.t === 'societe') ctx.rect(x - rad, y - rad, 2 * rad, 2 * rad); else ctx.arc(x, y, rad, 0, Math.PI * 2);
      ctx.fill(); if (!loin || inscrit || bl) ctx.stroke();
      if (bl && n.o && n.o !== 'r' && !loin) { ctx.strokeStyle = oc; ctx.lineWidth = 1.2; ctx.beginPath(); if (n.t === 'societe') ctx.rect(x - rad - 3, y - rad - 3, 2 * rad + 6, 2 * rad + 6); else ctx.arc(x, y, rad + 3, 0, Math.PI * 2); ctx.stroke(); }
      if ((k >= (m3 ? 8 : 0.9) || inscrit && k >= (m3 ? 2.5 : 0.3) || (focus >= 0 && proches.has(i))) && etiquettes.length < 400) etiquettes.push([n, x, y + rad + 2, inscrit]);
    }
    ctx.globalAlpha = 1; ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.lineJoin = 'round';
    const manquants = [];
    for (const [n, x, y, gras] of etiquettes) {
      const nomA = aff(n);
      if (!nomA) { if (!noms.has(n.i)) manquants.push(n.i); continue; }
      ctx.font = `${gras ? '600 ' : ''}${Math.round(Math.max(10, Math.min(13, 11 * k)))}px sans-serif`;
      const lim = etat.lat && nomDe(n) && nomDe(n).lat ? 48 : 28;
      const t = nomA.length > lim ? nomA.slice(0, lim - 1) + '…' : nomA;
      ctx.strokeStyle = C.fond; ctx.lineWidth = 3; ctx.strokeText(t, x, y); ctx.fillStyle = C.texte; ctx.fillText(t, x, y);
    }
    if (manquants.length) demanderNoms(manquants);
    if (m3) etiquettesVilles(W, H);
  }
  function cadrer(pts, marge) {
    // pts : points monde (z = 0) ; ajuste k, tx, ty pour qu'ils tiennent dans la toile avec la rotation et l'inclinaison courantes
    const r = cv.getBoundingClientRect(); const cy = Math.cos(etat.yaw), sy = Math.sin(etat.yaw);
    let minx = 1e12, maxx = -1e12, miny = 1e12, maxy = -1e12;
    for (const [x, y] of pts) { const xr = x * cy - y * sy, yr = (x * sy + y * cy) * etat.cp; if (xr < minx) minx = xr; if (xr > maxx) maxx = xr; if (yr < miny) miny = yr; if (yr > maxy) maxy = yr; }
    minx -= marge; maxx += marge; miny -= marge; maxy += marge;
    const haut = maroc() ? 44 : 0;                  // place pour le bandeau d'aide et les étiquettes du nord
    etat.k = Math.min(r.width / (maxx - minx), (r.height - haut) / (maxy - miny), maroc() ? 40 : 2.5);
    etat.tx = (r.width - (maxx + minx) * etat.k) / 2; etat.ty = haut + (r.height - haut - (maxy + miny) * etat.k) / 2;
    dessiner();
  }
  function toutVoir(ids) {
    const pts = [];
    if (ids) ids.forEach((i) => pts.push([X[i], Y[i]]));
    else if (maroc() && G && etat.isole < 0) { for (const rg of G.regions) for (let i = 0; i < rg.pts.length; i += 6) pts.push(rg.pts[i]); const c = G.cote; if (c && c.n) pts.push([c.x + c.r, c.y - c.r], [c.x + c.r, c.y + c.r]); }
    else for (let i = 0; i < NB; i++) if (visN[i]) pts.push([X[i], Y[i]]);
    if (pts.length) cadrer(pts, maroc() ? 70 : 40);
  }
  function sous(px, py) {
    let best = -1, bd = 1e9;
    for (let i = 0; i < NB; i++) { if (!visN[i]) continue; const dx = SX[i] - px, dy = SY[i] - py; if (dx > 14 || dx < -14 || dy > 14 || dy < -14) continue; const d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } }
    return best;
  }
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // nom affiché : avec l'écriture latine entre parenthèses quand l'option est cochée et que le nom est arabe
  const aff = (n) => { const x = nomDe(n); if (!x) return ''; return (etat.lat && x.lat) ? `${x.nom} (${x.lat})` : x.nom; };
  const affHtml = (n) => { const x = nomDe(n); if (!x) return '<span class="lat">…</span>'; return (etat.lat && x.lat) ? `<bdi>${esc(x.nom)}</bdi> <span class="lat">(${esc(x.lat)})</span>` : `<bdi>${esc(x.nom)}</bdi>`; };
  const villeNom = (v) => v ? String(v).toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase()) : '';
  const lienAnnonce = (u) => /^https?:\/\/[^\s"<>]+$/.test(u || '') ? u : null;

  async function panneau(i) {
    const p = $('#panneau');
    if (i < 0) { p.style.display = 'none'; return; }
    const n = N[i];
    let f = fiches.get(i);
    if (!f) {
      if (fichesEnErreur.has(i)) {
        p.innerHTML = `<button class="fermer" type="button" data-fermer aria-label="Fermer">×</button><div class="ligne">${esc(fichesEnErreur.get(i))}</div>`;
        p.style.display = 'block';
        return;
      }
      p.innerHTML = '<div class="ligne">Chargement de la fiche…</div>'; p.style.display = 'block';
      if (!fichesEnCours.has(i)) fichesEnCours.set(i, Commun.api(`/api/carte/globale/noeud/${i}`).finally(() => fichesEnCours.delete(i)));
      const demande = fichesEnCours.get(i);
      try {
        f = await demande;
      } catch (e) {
        if (e.message === 'session') return;
        fichesEnErreur.set(i, erreurCarte(e, 'Fiche'));
        if (etat.choisi === i) panneau(i);
        return;
      }
      fiches.set(i, f);
      noms.set(i, { nom: f.nom, lat: f.lat });
      if (etat.choisi !== i) return;
    }
    const liens = adj[i].filter((e) => visA.includes(e)).map((e) => A[e]).sort((a, b) => b.force - a.force);
    demanderNoms(liens.map((a) => (a.a === i ? a.b : a.a)));
    const libelle = new Map((f.liens || []).map((l) => [l.indice, l.libelle]));
    let h = `<button class="fermer" type="button" data-fermer aria-label="Fermer">×</button><h2>${affHtml(n)}</h2>`;
    if (n.t === 'inscrit') h += `<div class="ligne">Personne inscrite${f.cin ? ' · CIN ' + esc(f.cin) : ''}${f.listes ? ' · ' + esc(f.listes) : ''}${f.motifs ? ' · ' + esc(f.motifs) : ''}</div>${n.certain ? '<span class="badge certain">lien certain</span>' : '<span class="ligne">lien probable, à valider</span>'}`;
    else if (n.t === 'societe') {
      const url = lienAnnonce(f.url);
      h += `<div class="ligne">${[f.rc ? 'RC ' + esc(f.rc) : 'RC non lu', f.tribunal ? 'tribunal ' + esc(villeNom(f.tribunal)) : '', n.ville && n.ville !== f.tribunal ? 'siège ' + esc(villeNom(n.ville)) : '', f.derniere ? 'dernière annonce ' + esc(f.derniere) : '', f.dissoute ? 'dissoute' : '', f.personnes ? f.personnes + ' personne' + (f.personnes > 1 ? 's' : '') + ' citée' + (f.personnes > 1 ? 's' : '') : ''].filter(Boolean).join(' · ')}</div>${url ? `<div class="ligne"><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Ouvrir la dernière annonce</a></div>` : ''}`;
    } else h += `<div class="ligne">${n.o === 'd' ? 'Personne lue dans un dossier de l’antifraude' : 'Personne du registre'} · présente dans ${n.ns} société${n.ns > 1 ? 's' : ''}${f.cin ? ' · CIN ' + esc(f.cin) : ''}${n.ville ? ' · ' + esc(villeNom(n.ville)) : ''}</div>`;
    if (n.bl && n.t !== 'inscrit') h += `<div class="rouge">${esc(f.liste_noire || 'liste noire')}</div>`;
    if (n.t !== 'inscrit') h += `<div class="ligne">Origine : <b class="origine-${n.o || 'r'}">${n.o === 'd' ? 'dossiers de l’antifraude' : n.o === 'rd' ? 'registre et dossiers de l’antifraude' : 'registre du commerce (annonces légales)'}</b>${f.nb_dossiers ? ' · ' + f.nb_dossiers + ' dossier' + (f.nb_dossiers > 1 ? 's' : '') + ' : ' + esc(f.dossiers) : ''}</div>`;
    if (maroc()) h += `<div class="ligne">Sur la carte : ${n.ville ? esc(villeNom(n.ville)) : 'sans ville connue (zone de droite)'}</div>`;
    h += '<ul>' + liens.map((a) => { const o = a.a === i ? a.b : a.a; return `<li><b data-choisir="${o}">${affHtml(N[o])}</b> <span class="ligne">— ${esc(libelle.get(o) || a.lib)} · force ${a.force}${maroc() && N[o].ville && N[o].ville !== n.ville ? ' · ' + esc(villeNom(N[o].ville)) : ''}</span></li>`; }).join('') + '</ul>';
    h += `<button class="petit" type="button" data-isoler="${n.c}">Isoler ce réseau (${D.reseaux[n.c]} nœuds)</button>`;
    p.innerHTML = h; p.style.display = 'block';
  }
  function centrerSur(i, kmin) {
    const r = cv.getBoundingClientRect(); if (kmin) etat.k = Math.max(etat.k, kmin);
    const cy = Math.cos(etat.yaw), sy = Math.sin(etat.yaw); const x = X[i], y = Y[i];
    etat.tx = r.width / 2 - 180 - (x * cy - y * sy) * etat.k; etat.ty = r.height / 2 - (x * sy + y * cy) * etat.cp * etat.k; dessiner();
  }
  function choisir(i) {
    if (i !== etat.choisi) fichesEnErreur.clear();          // un nouveau choix retente une fiche en erreur
    etat.choisi = i;
    if (maroc()) {
      // vue Maroc : un clic sur un élément ne laisse sur la carte que son réseau ; un clic dans le vide ramène tout
      if (i >= 0 && etat.isole !== N[i].c) {
        etat.isole = N[i].c; filtrer();
        const pts = []; for (let j = 0; j < NB; j++) if (visN[j]) pts.push([X[j], Y[j]]);
        cadrer(pts, 30); if (etat.k > 40) { etat.k = 40; centrerSur(i); }
      } else if (i < 0 && etat.isole >= 0) { etat.isole = -1; filtrer(); }
    }
    panneau(i); dessiner();
    if (i >= 0) { const r = cv.getBoundingClientRect(); const x = SX[i], y = SY[i]; if (x < 0 || x > r.width - 380 || y < 0 || y > r.height) centrerSur(i); }
  }
  function isoler(c) { etat.isole = c; filtrer(); toutVoir(); }
  // panneau : clics délégués (aucun gestionnaire écrit dans le HTML, politique de sécurité du contenu)
  $('#panneau').addEventListener('click', (e) => {
    const cible = e.target.closest('[data-choisir], [data-isoler], [data-fermer]');
    if (!cible) return;
    if (cible.dataset.choisir !== undefined) choisir(+cible.dataset.choisir);
    else if (cible.dataset.isoler !== undefined) isoler(+cible.dataset.isoler);
    else choisir(-1);
  });

  function aide() {
    $('#aide').innerHTML = maroc()
      ? 'Molette, ou touches <b>Z</b> (zoom) et <b>A</b> (dézoom) à l’endroit de la souris · glisser : déplacer · <b>clic droit</b> ou <b>Maj + glisser</b> : tourner et incliner · clic : détail et seul son réseau reste sur la carte · clic dans le vide ou <b>Échap</b> : tout revient · <b>0</b> : tout voir'
      : 'Molette, ou touches <b>Z</b> (zoom) et <b>A</b> (dézoom) à l’endroit de la souris · glisser : déplacer · clic : détail · double-clic : isoler le réseau';
  }
  function basculer(mode) {
    etat.mode = mode; const m3 = maroc();
    X = m3 ? XM : XR; Y = m3 ? YM : YR;
    etat.pente = m3 ? (+$('#pente').value) * Math.PI / 180 : 0; etat.yaw = m3 ? (+$('#rotation').value) * Math.PI / 180 : 0; angles();
    $('#btn-vue').classList.toggle('actif', m3); $('#btn-vue').textContent = m3 ? 'Vue réseau' : 'Carte du Maroc 3D';
    $('#vue3d').classList.toggle('visible', m3);
    $('#leg-arc').style.display = m3 ? 'inline-flex' : 'none';
    $('#leg-fin').textContent = m3 ? 'Chaque élément à sa ville ; sans ville connue : zone grise à droite. Épingle rouge : liste noire.' : 'Réseaux de la liste noire en haut à gauche, puis les autres du plus gros au plus petit.';
    aide(); chiffres(); if (etat.choisi >= 0) panneau(etat.choisi); toutVoir();
  }

  let glisse = null;
  cv.addEventListener('contextmenu', (e) => e.preventDefault());
  cv.addEventListener('mousedown', (e) => { glisse = { x: e.clientX, y: e.clientY, tx: etat.tx, ty: etat.ty, yaw: etat.yaw, pente: etat.pente, bouge: false, tourne: maroc() && (e.button === 2 || e.shiftKey) }; cv.classList.add('saisi'); });
  window.addEventListener('mousemove', (e) => {
    if (glisse) {
      const dx = e.clientX - glisse.x, dy = e.clientY - glisse.y; if (Math.abs(dx) + Math.abs(dy) > 3) glisse.bouge = true;
      if (glisse.tourne) {
        // on tourne autour du point saisi : on conserve sa position écran
        const r = cv.getBoundingClientRect(); const [wx, wy] = deproj(glisse.x - r.left, glisse.y - r.top);
        etat.yaw = glisse.yaw + dx * 0.006; etat.pente = Math.max(0, Math.min(75 * Math.PI / 180, glisse.pente + dy * 0.006)); angles();
        $('#rotation').value = Math.round(((etat.yaw * 180 / Math.PI + 180) % 360 + 360) % 360 - 180); $('#pente').value = Math.round(etat.pente * 180 / Math.PI);
        const [sx, sy] = proj(wx, wy, 0); etat.tx += glisse.x - r.left - sx; etat.ty += glisse.y - r.top - sy;
      } else { etat.tx = glisse.tx + dx; etat.ty = glisse.ty + dy; }
      dessiner(); return;
    }
    const r = cv.getBoundingClientRect(); const i = sous(e.clientX - r.left, e.clientY - r.top);
    if (i !== etat.survol) { etat.survol = i; dessiner(); }
    const info = $('#info');
    if (i >= 0 && e.target === cv) {
      const n = N[i]; info.style.display = 'block'; info.style.left = (e.clientX - r.left + 14) + 'px'; info.style.top = (e.clientY - r.top + 14) + 'px';
      if (!noms.has(i)) demanderNoms([i]);
      info.innerHTML = `<b>${affHtml(n)}</b><span class="doux">${n.t === 'inscrit' ? 'inscrit' : n.t === 'societe' ? 'société' + (n.ville ? ' · ' + esc(villeNom(n.ville)) : '') : 'personne · ' + n.ns + ' société' + (n.ns > 1 ? 's' : '') + (n.ville ? ' · ' + esc(villeNom(n.ville)) : '')}${n.bl && n.t !== 'inscrit' ? ' · liste noire' : ''} · ${n.deg} lien${n.deg > 1 ? 's' : ''}</span>`;
    } else info.style.display = 'none';
  });
  window.addEventListener('mouseup', (e) => { if (!glisse) return; const b = glisse.bouge, t = glisse.tourne; glisse = null; cv.classList.remove('saisi'); if (!b && !t && e.button === 0 && e.target === cv) { const r = cv.getBoundingClientRect(); choisir(sous(e.clientX - r.left, e.clientY - r.top)); } });
  cv.addEventListener('dblclick', (e) => { const r = cv.getBoundingClientRect(); const i = sous(e.clientX - r.left, e.clientY - r.top); if (i >= 0) isoler(N[i].c); else { etat.isole = -1; filtrer(); toutVoir(); } });
  const kmax = () => maroc() ? 80 : 10;
  cv.addEventListener('wheel', (e) => { e.preventDefault(); const r = cv.getBoundingClientRect(); const px = e.clientX - r.left, py = e.clientY - r.top; const f = Math.exp(-e.deltaY * 0.0015); const nk = Math.min(kmax(), Math.max(0.01, etat.k * f)); etat.tx = px - (px - etat.tx) * nk / etat.k; etat.ty = py - (py - etat.ty) * nk / etat.k; etat.k = nk; dessiner(); }, { passive: false });
  // touches Z et A : zoom et dézoom à l'endroit de la souris (au centre si la souris est hors de la carte)
  let souris = null;
  cv.addEventListener('mousemove', (e) => { const r = cv.getBoundingClientRect(); souris = [e.clientX - r.left, e.clientY - r.top]; });
  cv.addEventListener('mouseleave', () => { souris = null; $('#info').style.display = 'none'; });
  function zoomer(f) {
    const r = cv.getBoundingClientRect(); const [px, py] = souris || [r.width / 2, r.height / 2];
    const nk = Math.min(kmax(), Math.max(0.01, etat.k * f));
    etat.tx = px - (px - etat.tx) * nk / etat.k; etat.ty = py - (py - etat.ty) * nk / etat.k; etat.k = nk; dessiner();
  }
  window.addEventListener('keydown', (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) return;
    const k = e.key.toLowerCase();
    if (k === 'z' || k === '+' || k === '=') { e.preventDefault(); zoomer(1.35); }
    else if (k === 'a' || k === '-') { e.preventDefault(); zoomer(1 / 1.35); }
    else if (k === 'escape') { choisir(-1); }
    else if (k === '0') { toutVoir(); }
    else if (k === 'm') { basculer(maroc() ? 'reseau' : 'maroc'); }
  });
  let touche = null;
  cv.addEventListener('touchstart', (e) => { if (e.touches.length === 1) touche = { x: e.touches[0].clientX, y: e.touches[0].clientY, tx: etat.tx, ty: etat.ty }; }, { passive: true });
  cv.addEventListener('touchmove', (e) => { if (touche && e.touches.length === 1) { etat.tx = touche.tx + e.touches[0].clientX - touche.x; etat.ty = touche.ty + e.touches[0].clientY - touche.y; dessiner(); } }, { passive: true });
  $('#btn-def').onclick = () => { const d = $('#definitions'); const v = getComputedStyle(d).display === 'none'; d.style.display = v ? 'block' : 'none'; $('#btn-def').setAttribute('aria-expanded', String(v)); };
  $('#fermer-def').onclick = () => { $('#definitions').style.display = 'none'; $('#btn-def').setAttribute('aria-expanded', 'false'); };
  $('#recentrer').onclick = () => { etat.isole = -1; etat.choisi = -1; panneau(-1); filtrer(); toutVoir(); };
  $('#btn-vue').onclick = () => basculer(maroc() ? 'reseau' : 'maroc');
  function reglerAngles() {
    // on garde fixe le point au centre de la toile
    const r = cv.getBoundingClientRect(); const [wx, wy] = deproj(r.width / 2, r.height / 2);
    etat.pente = (+$('#pente').value) * Math.PI / 180; etat.yaw = (+$('#rotation').value) * Math.PI / 180; angles();
    const [sx, sy] = proj(wx, wy, 0); etat.tx += r.width / 2 - sx; etat.ty += r.height / 2 - sy; dessiner();
  }
  $('#pente').oninput = reglerAngles; $('#rotation').oninput = reglerAngles;
  $('#btn-plat').onclick = () => { $('#pente').value = 0; $('#rotation').value = 0; reglerAngles(); };
  for (const id of ['f-bl', 'f-cert', 'f-anc', 'f-ns', 'f-rayon', 'f-orig']) $('#' + id).onchange = () => { filtrer(); toutVoir(); };
  $('#seuil').oninput = () => { const v = +$('#seuil').value; etat.seuil = v === 0 ? 0 : Math.pow(10, -4 + 4 * v / 100); $('#seuil-v').textContent = v === 0 ? 'tout' : etat.seuil.toPrecision(2); filtrer(); };
  // recherche : envoyée au serveur (corps d'une requête POST, jamais dans l'adresse), qui ne la journalise pas
  let minuterieRecherche = null, numeroRecherche = 0;
  $('#recherche').oninput = () => {
    clearTimeout(minuterieRecherche);
    minuterieRecherche = setTimeout(async () => {
      const q = $('#recherche').value.trim(); if (q.length < 2) return;
      const moi = ++numeroRecherche;
      let r;
      try { r = await Commun.api('/api/carte/globale/recherche', { corps: { q } }); } catch (e) { return; }
      if (moi !== numeroRecherche) return;
      let hit = -1;
      for (const x of r.resultats) { if (!visN[x.indice]) continue; if (hit < 0) hit = x.indice; if (x.type === 'inscrit') { hit = x.indice; break; } }
      if (hit >= 0) { centrerSur(hit, maroc() ? 6 : 1.4); choisir(hit); }
    }, 300);
  };
  window.addEventListener('resize', () => { taille(); dessiner(); });
  new ResizeObserver(() => { taille(); dessiner(); }).observe($('#cg-main'));
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { lireCouleurs(); dessiner(); });
  try { if (localStorage.getItem('carte-globale-bl') === '1') $('#f-bl').checked = true; if (localStorage.getItem('carte-globale-lat') === '1') { $('#f-lat').checked = true; etat.lat = true; } } catch (e) { /* stockage indisponible */ }
  $('#f-lat').addEventListener('change', () => { etat.lat = $('#f-lat').checked; try { localStorage.setItem('carte-globale-lat', etat.lat ? '1' : '0'); } catch (e) { /* stockage indisponible */ } if (etat.choisi >= 0) panneau(etat.choisi); dessiner(); });
  $('#f-bl').addEventListener('change', () => { try { localStorage.setItem('carte-globale-bl', $('#f-bl').checked ? '1' : '0'); } catch (e) { /* stockage indisponible */ } });
  if (!G) { $('#btn-vue').style.display = 'none'; }
  aide(); angles(); taille(); filtrer(); toutVoir();
  // arrivée depuis une fiche client : « carte.html?n=<indice de la carte> » centre la carte sur ce nœud
  const depart = Number(Commun.parametre('n'));
  if (Number.isInteger(depart) && depart >= 0 && depart < NB && Commun.parametre('n') !== null) {
    if (!visN[depart]) { $('#f-bl').checked = false; filtrer(); }
    isoler(N[depart].c); centrerSur(depart, 1.4); choisir(depart);
  }
});
