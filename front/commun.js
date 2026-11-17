// Commun aux écrans : en-tête, appels à l'API (cookie de session), mise en forme. Aucune ressource externe.
'use strict';

const Commun = (() => {
  const PAGES = [
    ['index.html', 'Portail'],
    ['base.html', 'Base client'],
    ['carte.html', 'Carte antifraude'],
  ];

  function el(balise, attributs = {}, ...enfants) {
    const n = document.createElement(balise);
    for (const [k, v] of Object.entries(attributs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'classe') n.className = v;
      else if (k === 'texte') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const e of enfants.flat(Infinity)) {
      if (e === null || e === undefined || e === false) continue;
      n.append(e instanceof Node ? e : document.createTextNode(String(e)));
    }
    return n;
  }

  function role() {
    try { return sessionStorage.getItem('carte_role'); } catch (e) { return null; }
  }

  function retourConnexion() {
    const retour = encodeURIComponent(location.pathname.split('/').pop() + location.search);
    location.href = `connexion.html?retour=${retour}`;
  }

  async function api(chemin, options = {}) {
    const init = { credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (options.corps !== undefined) {
      init.method = 'POST';
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.corps);
    }
    const r = await fetch(chemin, init);
    if (r.status === 401 && !options.sansRedirection) { retourConnexion(); throw new Error('session'); }
    if (!r.ok) { const e = new Error('http'); e.statut = r.status; throw e; }
    return r.status === 204 ? null : r.json();
  }

  async function deconnecter() {
    try { await fetch('/api/auth/deconnexion', { method: 'POST', credentials: 'same-origin' }); } catch (e) { /* rien */ }
    try { sessionStorage.removeItem('carte_role'); } catch (e) { /* rien */ }
    location.href = 'index.html';
  }

  function entete(courante, sombre = false) {
    const nav = el('nav', { 'aria-label': 'Navigation principale' },
      PAGES.filter(([lien]) => lien !== 'carte.html' || role() === 'ANALYSTE').map(([lien, libelle]) => el('a', { href: lien, 'aria-current': lien === courante ? 'page' : null, texte: libelle })));
    const langue = el('div', { classe: 'langue', role: 'group', 'aria-label': 'Langue' },
      el('button', { type: 'button', 'aria-pressed': 'true', texte: 'Fr' }),
      el('button', { type: 'button', 'aria-pressed': 'false', disabled: true, title: 'Arabe : bientôt',
        'aria-label': 'Arabe (bientôt)', texte: 'AR' }));
    const r = role();
    const droite = el('div', { classe: 'entete-droite' }, langue,
      r ? el('span', { classe: 'role', texte: r.toLowerCase() }) : el('a', { href: 'connexion.html', texte: 'Se connecter' }),
      r ? el('button', { classe: 'bouton-lien', type: 'button', onclick: deconnecter, texte: 'Déconnexion' }) : null);
    const tete = el('header', { classe: 'entete' + (sombre ? ' entete-sombre' : '') },
      el('a', { classe: 'marque', href: 'index.html', 'aria-label': 'EQDOM, plateforme clients : accueil' },
        el('span', { classe: 'marque-carre', 'aria-hidden': 'true', texte: 'E' }),
        el('span', {}, el('span', { classe: 'marque-nom', texte: 'EQDOM' }), ' ',
          el('span', { classe: 'marque-sous', texte: 'Plateforme clients' }))),
      nav, droite);
    document.body.prepend(tete);
  }

  const nombreFr = new Intl.NumberFormat('fr-FR');
  const montantFr = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });

  function nombre(n) { return typeof n === 'number' ? nombreFr.format(n) : (n ?? '—'); }
  function montant(n) { return typeof n === 'number' ? `${montantFr.format(n)} DH` : '—'; }
  function date(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function niveau(code, libelle) {
    const c = code || 'aucun';
    return el('span', { classe: `niveau niveau-${c}`, texte: libelle || c });
  }
  function initiales(nom) {
    return (nom || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(m => m[0]).join('').toUpperCase();
  }
  function erreur(e, objet) {
    if (e.statut === 403) return `${objet} réservé${objet.endsWith('e') ? 'e' : ''} à la cellule fraude.`;
    if (e.statut === 404) return `${objet} introuvable.`;
    if (e.statut === 429) return 'Trop de consultations pour l’heure : réessayez dans quelques minutes.';
    return 'La base client ne répond pas. Réessayez.';
  }
  function parametre(nom) { return new URLSearchParams(location.search).get(nom); }
  function barres(conteneur, lignes, cle = 'valeur', classe = () => '') {
    const valeur = l => (typeof l.nombre === 'number' ? l.nombre : 4);
    const max = Math.max(1, ...lignes.map(valeur));
    conteneur.replaceChildren(...lignes.map(l => {
      const plein = el('div', { classe: `barre-plein ${classe(l)}` });
      requestAnimationFrame(() => { plein.style.width = `${valeur(l) / max * 100}%`; });
      return el('div', { classe: 'barre' }, el('span', { texte: l.libelle || l[cle] }),
        el('div', { classe: 'barre-piste' }, plein), el('span', { classe: 'barre-valeur', texte: nombre(l.nombre) }));
    }));
  }
  function lienFiche(n) {
    const a = el('a', { classe: 'chemin-noeud' + (n.inscrit ? ' inscrit' : ''), href: `fiche.html?i=${n.indice}`, texte: n.nom });
    if (n.inscrit) a.title = 'Inscrit sur la liste noire';
    return a;
  }
  function chemin(ch) {
    const ligne = el('div', { classe: 'chemin' });
    const premier = ch.etapes[0];
    if (premier) ligne.append(lienFiche(premier.de));
    for (const e of ch.etapes) {
      const libelle = e.type === 'homonymie' ? 'homonymie à lever'
        : e.type === 'identifiant' ? `même ${e.code.toLowerCase()}` : e.code;
      ligne.append(el('span', { classe: 'chemin-lien', texte: libelle }), lienFiche(e.vers));
    }
    return el('div', { classe: 'carte' },
      el('div', { classe: 'chemin-entete' },
        el('span', { texte: `${ch.longueur} lien${ch.longueur > 1 ? 's' : ''} · force ${String(ch.force).replace('.', ',')}` }),
        ch.homonymie ? el('span', { classe: 'etiquette', texte: 'homonymie à lever' }) : null,
        ch.foyer ? el('span', { classe: 'etiquette', texte: 'même foyer qu’un inscrit' }) : null),
      ch.etapes.length ? ligne
        : el('div', { classe: 'chemin' }, el('span', { classe: 'chemin-noeud inscrit', texte: `${ch.inscrit.nom} (inscrit)` })));
  }

  return { el, api, entete, nombre, montant, date, niveau, initiales, parametre, barres, chemin, lienFiche, role, erreur };
})();
