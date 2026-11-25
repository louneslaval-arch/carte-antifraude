'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const { el, api, nombre, date } = Commun;
  Commun.entete('dossiers.html');
  const lignes = document.getElementById('dossiers-lignes');
  const compte = document.getElementById('dossiers-compte');
  const precedent = document.getElementById('dossiers-precedent');
  const suivant = document.getElementById('dossiers-suivant');
  let page = 1;

  if (Commun.role() !== 'ANALYSTE') {
    lignes.replaceChildren(el('tr', {}, el('td', { colspan: 6, classe: 'vide',
      texte: 'La liste des dossiers est réservée à la cellule fraude.' })));
    precedent.disabled = suivant.disabled = true;
    return;
  }

  precedent.addEventListener('click', () => { if (page > 1) { page--; charger(); } });
  suivant.addEventListener('click', () => { page++; charger(); });
  async function charger() {
    precedent.disabled = suivant.disabled = true;
    try {
      const r = await api(`/api/base/dossiers/liste?page=${page}&taille=25`);
      lignes.replaceChildren(...(r.items.length ? r.items.map(d => {
        const lien = el('a', { href: `dossier.html?i=${d.indice}`, texte: d.reference });
        const tr = el('tr', { classe: 'cliquable' },
          el('td', {}, lien), el('td', { texte: d.produit || '—' }),
          el('td', { texte: date(d.recu) }),
          el('td', { texte: d.avec_demandeur ? 'Associé' : 'Non associé' }),
          el('td', { classe: 'nombre', texte: nombre(d.alertes) }),
          el('td', { classe: 'nombre', texte: nombre(d.relations) }));
        tr.addEventListener('click', ev => { if (ev.target.tagName !== 'A') location.href = lien.href; });
        return tr;
      }) : [el('tr', {}, el('td', { colspan: 6, classe: 'vide', texte: 'Aucun dossier.' }))]));
      const fin = Math.min(r.page * r.taille, r.total);
      compte.textContent = r.total ? `${(r.page - 1) * r.taille + 1}–${fin} sur ${nombre(r.total)}` : '0 dossier';
      precedent.disabled = page <= 1;
      suivant.disabled = fin >= r.total;
    } catch (e) {
      lignes.replaceChildren(el('tr', {}, el('td', { colspan: 6, classe: 'vide', role: 'alert',
        texte: e.statut === 403 ? 'Accès réservé à la cellule fraude.' : 'Chargement des dossiers impossible.' })));
      compte.textContent = '';
      precedent.disabled = page <= 1;
    }
  }
  charger();
});
