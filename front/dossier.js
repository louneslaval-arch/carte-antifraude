'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date } = Commun;
  Commun.entete('base.html');
  const main = document.getElementById('contenu');
  let d;
  try {
    d = await api(`/api/base/dossiers/${encodeURIComponent(Commun.parametre('i'))}`);
  } catch (e) {
    main.replaceChildren(el('p', { classe: 'carte', role: 'alert', texte: Commun.erreur(e, 'Dossier') }));
    return;
  }
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
    ? Commun.listeChemins(d.chemins) : vide('Aucun chemin vers un inscrit.'));
  const incoherences = carte('Incohérences détectées', d.incoherences.length
    ? tableau(['Signal', 'Gravité', 'Autre dossier'], d.incoherences.map(i => [
      i.libelle || i.type, i.gravite || '—',
      Number.isInteger(i.autre_dossier) ? el('a', { href: `dossier.html?i=${i.autre_dossier}`, texte: 'Consulter' }) : '—',
    ])) : vide('Aucune incohérence détectée.'));
  const relationsC7 = carte('Relations complémentaires vérifiées (C7)', (d.relations_c7 || []).length
    ? tableau(['Relation', 'Fiche associée'], d.relations_c7.map(r => [
      r.libelle || r.code, r.fiche_associee ? 'Oui' : 'Non ou non résolue',
    ])) : vide('Aucune relation complémentaire déclarée par Tandem.'));
  const alertesC6 = carte('Signaux calculés (C6)', (d.alertes_c6 || []).length
    ? tableau(['Signal', 'Niveau', 'Explication'], d.alertes_c6.map(a => [
      a.libelle || a.code, a.niveau || '—', a.justification || '—',
    ])) : vide('Aucun signal C6 calculé pour ce dossier.'));
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
      el('div', { classe: 'pile' }, parties, chemins, incoherences, relationsC7, alertesC6),
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
});
