// Démonstration autonome : les pages de la plateforme, sans serveur. Chargé après commun.js, ce script remplace les
// appels à l'API par des réponses calculées à l'avance (dossier « donnees/ », un fichier par fiche, dossier, réseau),
// chargées à la demande par des balises <script> (ce qui marche en ouvrant les pages directement depuis le disque).
// Données entièrement fictives. Écrit par outils/demo/exporter_autonome.py ; jamais servi par la plateforme.
'use strict';
(() => {
  const recus = new Map(), attentes = new Map();
  window.Demo = {
    recevoir(cle, valeur) {
      recus.set(cle, valeur);
      for (const r of attentes.get(cle) || []) r(valeur);
      attentes.delete(cle);
    },
  };
  function charger(cle) {
    if (recus.has(cle)) return Promise.resolve(recus.get(cle));
    return new Promise((resoudre, rejeter) => {
      const premier = !attentes.has(cle);
      attentes.set(cle, [...(attentes.get(cle) || []), resoudre]);
      if (!premier) return;
      const s = document.createElement('script');
      s.src = `donnees/${cle}.js`;
      s.onerror = () => { attentes.delete(cle); rejeter(erreur(404)); };
      document.head.append(s);
    });
  }
  function erreur(statut) { const e = new Error('http'); e.statut = statut; e.detail = ''; return e; }

  // ---- la liste des clients : filtres, tri et pages, comme le serveur ------------------------------------------------
  const RANG = { critique: 0, majeure: 1, mineure: 2, affiche: 3, hors_alerte: 4, aucun: 5 };
  function trier(lignes, tri) {
    const nom = (c) => (c.nom || '').toUpperCase();
    const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
    if (!tri || tri === 'gravite') return lignes;
    if (tri === 'alpha' || tri === 'alpha_inverse') {
      const s = [...lignes].sort((a, b) => cmp(nom(a), nom(b)) || a.indice - b.indice);
      return tri === 'alpha' ? s : s.reverse();
    }
    if (tri === 'dossiers') return [...lignes].sort((a, b) => b.dossiers - a.dossiers || cmp(nom(a), nom(b)));
    const cle = tri === 'revenu' ? 'revenu' : 'derniere_demande';
    const presents = lignes.filter((c) => c[cle] !== null && c[cle] !== undefined).sort((a, b) => cmp(nom(a), nom(b)));
    presents.sort((a, b) => (tri === 'ancien' ? cmp(a[cle], b[cle]) : cmp(b[cle], a[cle])));
    return [...presents, ...lignes.filter((c) => c[cle] === null || c[cle] === undefined).sort((a, b) => cmp(nom(a), nom(b)))];
  }
  async function clients(corps) {
    let lignes = (await charger('clients')).items;
    if (corps.texte) { const t = corps.texte.trim().toUpperCase(); lignes = lignes.filter((c) => (c.nom || '').toUpperCase().includes(t)); }
    if (corps.type) lignes = lignes.filter((c) => c.type === corps.type);
    if (corps.niveau) lignes = lignes.filter((c) => (c.niveau || 'aucun') === corps.niveau);
    if (corps.produit) lignes = lignes.filter((c) => c.produits.includes(corps.produit));
    if (corps.avec_incoherence) lignes = lignes.filter((c) => c.incoherences);
    lignes = trier(lignes, corps.tri);
    const page = corps.page || 1, taille = corps.taille || 50, debut = (page - 1) * taille;
    return { total: lignes.length, page, taille, items: lignes.slice(debut, debut + taille).map(({ carte, ...c }) => c) };
  }

  // ---- la carte globale : noms, fiches et recherche dans les données jointes ------------------------------------------
  async function recherche(q) {
    const r = await charger('carte/recherche');
    const nettoye = q.trim().toUpperCase().replace(/\s+/g, ' '), compact = nettoye.replace(/ /g, '');
    const exacte = /^[A-Z]{0,2}\d{3,}$/.test(compact);
    if (!exacte && nettoye.length < 3) throw erreur(422);
    const vus = new Set(), sortie = [];
    for (const [i, champ, valeur] of r.lignes) {
      const ok = exacte ? (champ === 'cin' || champ === 'rc') && valeur === compact : champ === 'nom' && valeur.includes(nettoye);
      if (ok && !vus.has(i)) { vus.add(i); sortie.push({ indice: i, type: r.types[i], nom: r.noms[i] }); }
    }
    sortie.sort((a, b) => ((a.nom || '') < (b.nom || '') ? -1 : 1));
    return { resultats: sortie.slice(0, 50) };
  }

  async function api(chemin, options = {}) {
    const corps = options.corps || {};
    let m;
    if (chemin === '/api/base/resume') return charger('resume');
    if (chemin === '/api/base/clients') return clients(corps);
    if ((m = chemin.match(/^\/api\/base\/(clients|dossiers|reseau)\/(\d+)$/))) {
      return charger(`${{ clients: 'fiche', dossiers: 'dossier', reseau: 'reseau' }[m[1]]}/${m[2]}`);
    }
    if ((m = chemin.match(/^\/api\/base\/carte\/(\d+)$/))) {
      const c = (await charger('clients')).items.find((x) => String(x.indice) === m[1]);
      if (!c || c.carte === null || c.carte === undefined) throw erreur(404);
      return { indice: c.carte };
    }
    if (chemin === '/api/carte/globale') return charger('carte/geometrie');
    if (chemin === '/api/carte/globale/noms') {
      const noms = await charger('carte/noms');
      return Object.fromEntries(corps.indices.filter((i) => noms[i]).map((i) => [String(i), noms[i]]));
    }
    if ((m = chemin.match(/^\/api\/carte\/globale\/noeud\/(\d+)$/))) {
      const f = (await charger('carte/fiches'))[m[1]];
      if (!f) throw erreur(404);
      return f;
    }
    if (chemin === '/api/carte/globale/recherche') return recherche(corps.q || '');
    throw erreur(404);
  }

  try { sessionStorage.setItem('carte_role', 'ANALYSTE'); } catch (e) { /* stockage indisponible */ }
  Commun.api = api;
  Commun.role = () => 'ANALYSTE';                  // même si le navigateur refuse le stockage (page ouverte du disque)
  // bandeau : la démonstration ne peut pas être prise pour de vraies données
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.createElement('div');
    b.textContent = 'Démonstration · données fictives (noms inventés, CIN en « ZZ ») · aucune personne ni société réelle';
    Object.assign(b.style, { position: 'fixed', left: '50%', bottom: '10px', transform: 'translateX(-50%)', zIndex: 50,
      background: '#fff4d6', color: '#7a5300', border: '1px solid #f0d58a', borderRadius: '6px', padding: '4px 12px',
      font: '600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', pointerEvents: 'none' });
    document.body.append(b);
  });
})();
