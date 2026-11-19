// Démonstration en un seul fichier : routeur et réponses de l'API, lues dans les données jointes à la page (JSON).
// Chaque page (portail, base client, vue 360°, dossier) est un gabarit ; l'adresse dit laquelle afficher
// (#base, #fiche?i=…). Toute navigation passe par Commun.aller ; une page absente du fichier est signalée.
// Données entièrement fictives. Assemblé par outils/demo/fichier_unique.py ; jamais servi par la plateforme.
'use strict';
const DemoUnique = (() => {
  const INCLUSES = ['index', 'base', 'fiche', 'dossier'];
  const NOMS = { carte: 'la carte antifraude', reseau: 'la vue réseau', statistiques: 'les statistiques',
    connexion: 'la connexion' };
  let donnees = {};

  function erreur(statut) { const e = new Error('http'); e.statut = statut; e.detail = ''; return e; }
  function lire(cle) { return cle in donnees ? Promise.resolve(donnees[cle]) : Promise.reject(erreur(404)); }

  // ---- la liste des clients : filtres, tri et pages, comme le serveur ------------------------------------------------
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
    let lignes = (await lire('clients')).items;
    if (corps.texte) { const t = corps.texte.trim().toUpperCase(); lignes = lignes.filter((c) => (c.nom || '').toUpperCase().includes(t)); }
    if (corps.type) lignes = lignes.filter((c) => c.type === corps.type);
    if (corps.niveau) lignes = lignes.filter((c) => (c.niveau || 'aucun') === corps.niveau);
    if (corps.produit) lignes = lignes.filter((c) => c.produits.includes(corps.produit));
    if (corps.avec_incoherence) lignes = lignes.filter((c) => c.incoherences);
    lignes = trier(lignes, corps.tri);
    const page = corps.page || 1, taille = corps.taille || 50, debut = (page - 1) * taille;
    return { total: lignes.length, page, taille, items: lignes.slice(debut, debut + taille) };
  }
  async function api(chemin, options = {}) {
    const corps = options.corps || {};
    let m;
    if (chemin === '/api/base/resume') return lire('resume');
    if (chemin === '/api/base/clients') return clients(corps);
    if ((m = chemin.match(/^\/api\/base\/(clients|dossiers)\/(\d+)$/))) {
      return lire(`${m[1] === 'clients' ? 'fiche' : 'dossier'}/${m[2]}`);
    }
    throw erreur(404);                               // carte et réseau : pas dans ce fichier
  }

  // ---- navigation ----------------------------------------------------------------------------------------------------
  function message(texte) {
    let b = document.getElementById('demo-message');
    if (!b) {
      b = document.createElement('div');
      b.id = 'demo-message';
      b.setAttribute('role', 'status');
      Object.assign(b.style, { position: 'fixed', left: '50%', top: '16px', transform: 'translateX(-50%)', zIndex: 60,
        background: '#14161f', color: '#fff', borderRadius: '8px', padding: '10px 16px', maxWidth: '90vw',
        font: '500 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', boxShadow: '0 6px 24px rgba(0,0,0,.25)' });
      document.body.append(b);
    }
    b.textContent = texte;
    b.hidden = false;
    clearTimeout(message.minuterie);
    message.minuterie = setTimeout(() => { b.hidden = true; }, 3500);
  }
  function aller(href) {
    const m = String(href).match(/(?:^|\/)([a-z_-]+)\.html(\?[^#]*)?$/);
    if (!m || !INCLUSES.includes(m[1])) {
      message(`${m && NOMS[m[1]] ? NOMS[m[1]][0].toUpperCase() + NOMS[m[1]].slice(1) : 'Cette page'} n’est pas dans ce fichier `
        + ': il contient le portail, la base client, la vue 360° et les dossiers.');
      return;
    }
    const cible = `#${m[1]}${m[2] || ''}`;
    if (location.hash === cible) location.reload(); else location.hash = cible;
  }

  function demarrer() {
    donnees = JSON.parse(document.getElementById('donnees').textContent);
    const [nom, requete] = location.hash.slice(1).split('?');
    const page = INCLUSES.includes(nom) ? nom : 'index';
    const params = new URLSearchParams(requete || '');
    try { sessionStorage.setItem('carte_role', 'ANALYSTE'); } catch (e) { /* stockage indisponible */ }
    Object.assign(Commun, { api, aller, role: () => 'ANALYSTE', parametre: (n) => params.get(n) });
    window.addEventListener('hashchange', () => location.reload());
    document.addEventListener('click', (ev) => {
      const a = ev.target.closest && ev.target.closest('a[href]');
      if (!a) return;
      const href = a.getAttribute('href');
      if (!href || href.startsWith('#') || /^[a-z]+:/i.test(href)) return;
      ev.preventDefault();
      aller(href);
    }, true);

    const gabarit = document.getElementById(`page-${page}`);
    document.body.className = gabarit.dataset.classe || '';
    document.title = gabarit.dataset.titre;
    document.body.prepend(gabarit.content.cloneNode(true));
    // le script de la page attend DOMContentLoaded : on le lui donne tout de suite, la page est déjà en place
    const ajouter = document.addEventListener;
    document.addEventListener = function (type, rappel, options) {
      if (type === 'DOMContentLoaded') return rappel();
      return ajouter.call(this, type, rappel, options);
    };
    try { PAGES_DEMO[page](); } finally { document.addEventListener = ajouter; }

    const b = document.createElement('div');
    b.textContent = 'Démonstration · données fictives (noms inventés, CIN en « ZZ ») · aucune personne ni société réelle';
    Object.assign(b.style, { position: 'fixed', left: '50%', bottom: '10px', transform: 'translateX(-50%)', zIndex: 50,
      background: '#fff4d6', color: '#7a5300', border: '1px solid #f0d58a', borderRadius: '6px', padding: '4px 12px',
      font: '600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', pointerEvents: 'none' });
    document.body.append(b);
  }
  return { demarrer };
})();
