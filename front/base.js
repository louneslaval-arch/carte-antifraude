'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date } = Commun;
  Commun.entete('base.html');
  let resume;
  try {
    resume = await api('/api/base/resume');
  } catch (e) {
    document.querySelector('main').prepend(el('p', { classe: 'carte', role: 'alert', texte: messageErreur(e) }));
    return;
  }
  document.getElementById('c-clients').textContent = nombre(resume.clients);
  document.getElementById('c-dossiers').textContent = nombre(resume.dossiers);
  document.getElementById('c-inscrits').textContent = nombre(resume.inscrits);
  document.getElementById('fictive').hidden = !resume.fictive;
  Commun.barres(document.getElementById('r-produits'), resume.produits.slice(0, 6));

  if (Commun.role() !== 'ANALYSTE') { document.getElementById('reserve').hidden = false; return; }
  document.getElementById('liste').hidden = false;
  const etat = { page: 1, taille: 25, mode: 'dossiers' };
  // Deux façons de lire la base : par dossier (par défaut, une ligne par dossier) ou par client (ses dossiers regroupés).
  const COLONNES = {
    dossiers: [['Dossier'], ['Demandeur'], ['Produit'], ['Revenu déclaré', 'nombre'], ['Reçu le'], ['Ville']],
    clients: [['Client'], ['Dossiers', 'nombre'], ['Produits'], ['Revenu vérifié', 'nombre'], ['Dernière demande'], ['Ville']] };
  const boutons = { dossiers: document.getElementById('mode-dossiers'), clients: document.getElementById('mode-clients') };
  function choisirMode(mode) {
    etat.mode = mode; etat.page = 1;
    for (const [m, b] of Object.entries(boutons)) b.setAttribute('aria-pressed', String(m === mode));
    document.getElementById('titre-liste').textContent = mode === 'dossiers' ? 'Dossiers' : 'Clients';
    document.getElementById('texte').placeholder = mode === 'dossiers' ? 'Nom du demandeur ou référence du dossier' : 'Rechercher un nom';
    document.getElementById('tri-revenu').textContent = mode === 'dossiers' ? 'Revenu déclaré' : 'Revenu vérifié';
    document.getElementById('entetes').replaceChildren(el('tr', {}, COLONNES[mode].map(([t, c]) => el('th', { classe: c || null, texte: t }))));
    charger();
  }
  for (const [m, b] of Object.entries(boutons)) b.addEventListener('click', () => { if (etat.mode !== m) choisirMode(m); });
  const choix = document.getElementById('produit');
  for (const p of resume.produits) choix.append(el('option', { value: p.valeur, texte: p.valeur }));
  let minuterie = null;
  const relancer = () => { clearTimeout(minuterie); minuterie = setTimeout(() => { etat.page = 1; charger(); }, 250); };
  for (const id of ['texte', 'type', 'produit', 'tri']) document.getElementById(id).addEventListener('input', relancer);
  document.getElementById('filtres').addEventListener('submit', ev => ev.preventDefault());
  const precedent = document.getElementById('precedent'), suivant = document.getElementById('suivant');
  precedent.addEventListener('click', () => { if (etat.page > 1) { etat.page -= 1; charger(); } });
  suivant.addEventListener('click', () => { etat.page += 1; charger(); });
  let numero = 0;                                   // seule la réponse à la dernière demande s'affiche

  async function charger() {
    const moi = ++numero;
    precedent.disabled = suivant.disabled = true;
    const corps = { page: etat.page, taille: etat.taille };
    const texte = document.getElementById('texte').value.trim();
    if (texte) corps.texte = texte;
    for (const id of ['type', 'produit', 'tri']) { const v = document.getElementById(id).value; if (v) corps[id] = v; }
    const tbody = document.getElementById('lignes');
    const mode = etat.mode;
    let r;
    try {
      r = await api(mode === 'dossiers' ? '/api/base/dossiers' : '/api/base/clients', { corps });
    } catch (e) {
      if (moi !== numero) return;
      tbody.replaceChildren(el('tr', {}, el('td', { colspan: 6, classe: 'vide', role: 'alert', texte: messageErreur(e) })));
      document.getElementById('compte').textContent = '';
      precedent.disabled = etat.page <= 1;
      return;
    }
    if (moi !== numero) return;
    if (!r.items.length) {
      tbody.replaceChildren(el('tr', {}, el('td', { colspan: 6, classe: 'vide',
        texte: mode === 'dossiers' ? 'Aucun dossier ne correspond.' : 'Aucun client ne correspond.' })));
    } else if (mode === 'dossiers') {
      tbody.replaceChildren(...r.items.map(x => {
        const lien = el('a', { href: `dossier.html?i=${x.indice}`, texte: x.reference });
        const tr = el('tr', { classe: 'cliquable' },
          el('td', {}, lien, x.actif ? null : el('span', { classe: 'etiquette', texte: 'archivé' }),
            x.incoherences ? el('div', { classe: 'note', texte: `${nombre(x.incoherences)} incohérence(s)` }) : null),
          el('td', {}, x.nom, x.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'inscrit' }) : null,
            el('div', { classe: 'note', texte: x.type === 'societe' ? 'Société' : 'Personne' })),
          el('td', {}, x.produit ? el('span', { classe: 'etiquette', texte: x.produit }) : '—'),
          el('td', { classe: 'nombre', texte: montant(x.revenu_declare) }),
          el('td', { texte: date(x.recu) }),
          el('td', { texte: x.ville || '—' }));
        tr.addEventListener('click', ev => { if (ev.target.tagName !== 'A') location.href = lien.href; });
        return tr;
      }));
    } else {
      tbody.replaceChildren(...r.items.map(c => {
        const lien = el('a', { href: `fiche.html?i=${c.indice}`, texte: c.nom });
        const tr = el('tr', { classe: 'cliquable' },
          el('td', {}, lien, c.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'inscrit' }) : null,
            el('div', { classe: 'note', texte: c.type === 'societe' ? 'Société' : 'Personne' })),
          el('td', { classe: 'nombre', texte: nombre(c.dossiers) }),
          el('td', {}, c.produits.map(p => el('span', { classe: 'etiquette', texte: p }))),
          el('td', { classe: 'nombre', texte: montant(c.revenu) }),
          el('td', { texte: date(c.derniere_demande) }),
          el('td', { texte: c.ville || '—' }));
        tr.addEventListener('click', ev => { if (ev.target.tagName !== 'A') location.href = lien.href; });
        return tr;
      }));
    }
    const fin = Math.min(r.page * r.taille, r.total);
    document.getElementById('compte').textContent = r.total ? `${(r.page - 1) * r.taille + 1}–${fin} sur ${nombre(r.total)}` : '';
    document.getElementById('precedent').disabled = r.page <= 1;
    document.getElementById('suivant').disabled = fin >= r.total;
  }
  choisirMode('dossiers');

  function messageErreur(e) {
    if (e.statut === 429) return 'Trop de demandes pour l’heure : réessayez dans quelques minutes.';
    if (e.statut === 503) return 'La base client n’est pas chargée.';
    return 'La base client ne répond pas. Réessayez.';
  }
});
