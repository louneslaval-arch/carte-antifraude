'use strict';
// Vue simple d'un dossier, quand il n'a pas de demandeur reconnu (pas d'étoile possible) : fiche.js l'appelle.
window.VueDossierSimple = (d, main) => {
  const { el, nombre, montant, date } = Commun;
  const e = d.entete;
  const demandeur = d.parties.find(p => p.demandeur);
  const chiffres = el('section', { classe: 'grille grille-3' },
    chiffre(e.produit || '—', 'produit'), chiffre(montant(e.revenu_declare), 'revenu déclaré'),
    chiffre(e.verdict || '—', `verdict de la v2${e.analyse && e.analyse !== 'COMPLETE' ? ` (analyse : ${e.analyse.toLowerCase().replaceAll('_', ' ')})` : ''}`));
  const tete = el('section', { classe: 'carte' },
    el('div', { classe: 'chemin-entete' },
      e.actif ? null : el('span', { classe: 'etiquette', texte: 'archivé' }),
      el('span', { texte: `Reçu le ${date(e.recu)} · ${e.ville || 'agence non renseignée'} · ${e.csp || ''}` })),
    el('h1', { texte: `Dossier ${e.reference}` }),
    demandeur ? el('p', { classe: 'sous-titre' }, 'Demandeur : ', Commun.lienFiche(demandeur)) : null);

  const parties = carte('Parties du dossier', tableau(['Nom', 'Rôle', ''], d.parties.map(p =>
    [Commun.lienFiche(p), p.role, p.demandeur ? el('span', { classe: 'etiquette', texte: 'demandeur' }) : ''])));
  const chemins = carte('Liens avec la liste noire', d.chemins.length
    ? el('div', { classe: 'pile' }, d.chemins.map(Commun.chemin)) : vide('Aucun chemin vers un inscrit.'));
  const pieces = carte('Pièces lues', tableau(['Pièce', 'Lecture', 'Champs'],
    d.pieces.map(p => [p.type, p.statut || '—', nombre(p.champs)])));
  const revenus = carte('Revenus et charges', el('div', {},
    d.revenus.length ? tableau(['Nature', 'Pièce', 'Période', 'Montant'], d.revenus.map(r => [r.nature, r.source,
      r.mois ? `${String(r.mois).padStart(2, '0')}/${r.annee}` : '—', montant(r.montant)])) : vide('Aucun revenu.'),
    d.charges.length ? tableau(['Charge', 'Période', 'Montant'], d.charges.map(c => [c.nature === 'credit_source' ? 'crédit prélevé à la source' : 'échéance de crédit',
      c.mois ? `${String(c.mois).padStart(2, '0')}/${c.annee}` : '—', montant(c.montant)])) : null));
  const operations = carte('Opérations du relevé', d.operations.length ? tableau(['Date', 'Type', 'Libellé', 'Débit', 'Crédit'],
    d.operations.map(o => [date(o.date_operation), o.type_operation, o.libelle, montant(o.debit), montant(o.credit)]))
    : vide('Relevé non relu : aucune opération lue.'));

  main.replaceChildren(el('p', { classe: 'fil' }, el('a', { href: 'base.html', texte: 'Base client' }), ' › Dossier'),
    tete, chiffres, el('div', { classe: 'grille grille-2' },
      el('div', { classe: 'pile' }, parties, chemins),
      el('div', { classe: 'pile' }, revenus, pieces, operations)));

  function chiffre(v, l, accent) {
    return el('div', { classe: 'carte chiffre' + (accent ? ' chiffre-accent' : '') },
      el('span', { classe: 'chiffre-valeur', texte: v }), el('span', { classe: 'chiffre-libelle', texte: l }));
  }
  function carte(titre, ...contenu) { return el('section', { classe: 'carte' }, el('h2', { texte: titre }), ...contenu); }
  function vide(t) { return el('p', { classe: 'vide', texte: t }); }
  function tableau(entetes, lignes) {
    return el('div', { classe: 'tableau-enveloppe' }, el('table', {},
      el('thead', {}, el('tr', {}, entetes.map(t => el('th', { texte: t })))),
      el('tbody', {}, lignes.map(l => el('tr', {}, l.map(c => el('td', {}, c ?? '—')))))));
  }
};
