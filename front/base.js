'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date, niveau } = Commun;
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
  document.getElementById('c-lies').textContent = nombre(resume.dossiers_lies);   // dossiers actifs, calculé par l'API
  Commun.barres(document.getElementById('r-niveaux'), resume.niveaux, 'niveau', l => `niveau-${l.niveau}`);
  Commun.barres(document.getElementById('r-produits'), resume.produits.slice(0, 6));

  if (Commun.role() !== 'ANALYSTE') { document.getElementById('reserve').hidden = false; return; }
  document.getElementById('liste').hidden = false;
  const etat = { page: 1, taille: 25, niveau: null };
  const choix = document.getElementById('produit');
  for (const p of resume.produits) choix.append(el('option', { value: p.valeur, texte: p.valeur }));
  const puces = document.getElementById('puces');
  const niveaux = [[null, 'Tous'], ['critique', 'Critique'], ['majeure', 'Majeure'], ['mineure', 'Mineure'], ['aucun', 'Aucun lien']];
  for (const [code, libelle] of niveaux) {
    puces.append(el('button', { classe: 'puce', type: 'button', 'aria-pressed': String(code === null), texte: libelle,
      onclick: ev => {
        etat.niveau = code; etat.page = 1;
        for (const b of puces.children) b.setAttribute('aria-pressed', String(b === ev.currentTarget));
        charger();
      } }));
  }
  let minuterie = null;
  const relancer = () => { clearTimeout(minuterie); minuterie = setTimeout(() => { etat.page = 1; charger(); }, 250); };
  for (const id of ['texte', 'type', 'produit']) document.getElementById(id).addEventListener('input', relancer);
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
    for (const id of ['type', 'produit']) { const v = document.getElementById(id).value; if (v) corps[id] = v; }
    if (etat.niveau) corps.niveau = etat.niveau;
    const tbody = document.getElementById('lignes');
    let r;
    try {
      r = await api('/api/base/clients', { corps });
    } catch (e) {
      if (moi !== numero) return;
      tbody.replaceChildren(el('tr', {}, el('td', { colspan: 7, classe: 'vide', role: 'alert', texte: messageErreur(e) })));
      document.getElementById('compte').textContent = '';
      precedent.disabled = etat.page <= 1;
      return;
    }
    if (moi !== numero) return;
    if (!r.items.length) {
      tbody.replaceChildren(el('tr', {}, el('td', { colspan: 7, classe: 'vide', texte: 'Aucun client ne correspond.' })));
    } else {
      tbody.replaceChildren(...r.items.map(c => {
        const lien = el('a', { href: `fiche.html?i=${c.indice}`, texte: c.nom });
        const tr = el('tr', { classe: 'cliquable' },
          el('td', {}, lien, c.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'inscrit' }) : null,
            el('div', { classe: 'note', texte: c.type === 'societe' ? 'Société' : 'Personne' })),
          el('td', {}, niveau(c.niveau, c.niveau_libelle)),
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
  charger();

  function messageErreur(e) {
    if (e.statut === 429) return 'Trop de demandes pour l’heure : réessayez dans quelques minutes.';
    if (e.statut === 503) return 'La base client n’est pas chargée.';
    return 'La base client ne répond pas. Réessayez.';
  }
});
