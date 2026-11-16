'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date, initiales } = Commun;
  Commun.entete('base.html');
  const main = document.getElementById('contenu');
  const indice = Commun.parametre('i');
  let f;
  try {
    f = await api(`/api/base/clients/${encodeURIComponent(indice)}`);
  } catch (e) {
    main.replaceChildren(el('p', { classe: 'carte', role: 'alert', texte: Commun.erreur(e, 'Fiche') }));
    main.removeAttribute('aria-busy');
    return;
  }
  const id = f.identite;
  const definitions = id.type === 'personne'
    ? [['CIN', id.cin], ['Date de naissance', date(id.date_naissance)], ['Adresse retenue', id.adresse]]
    : [['RC', id.rc ? `${id.rc} · ${id.tribunal || ''}` : null], ['ICE', id.ice], ['Siège', id.adresse]];
  const tete = el('section', { classe: 'carte identite' },
    el('div', { classe: `avatar ${id.type}${id.inscrit ? ' inscrit' : ''}`, 'aria-hidden': 'true', texte: initiales(id.nom) }),
    el('div', {},
      el('h1', { texte: id.nom }),
      el('div', { classe: 'puces' },
        id.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'Inscrit sur la liste noire' }) : null,
        el('span', { classe: 'etiquette', texte: id.type === 'personne' ? 'Personne' : 'Société' })),
      el('dl', { classe: 'definitions' }, definitions.map(([k, v]) => [el('dt', { texte: k }), el('dd', { texte: v || '—' })]))),
    null);

  const cites = f.dossiers.filter(d => !d.demandeur).length;
  const dossiers = carte('Dossiers', f.dossiers.length ? tableau(
    ['Reçu', 'Produit', 'Rôle', 'Verdict v2', ''],
    f.dossiers.map(d => [date(d.recu), d.produit, d.role,
      d.demandeur ? (d.verdict || '—') : '—',
      el('a', { href: `dossier.html?i=${d.indice}`, texte: 'Ouvrir' })])) : vide('Aucun dossier.'),
    cites ? el('p', { classe: 'note', texte: `Cité dans ${nombre(cites)} dossier(s) d’autres clients : leurs revenus et charges ne figurent pas sur cette fiche.` }) : null);

  const chemins = carte('Liens avec la liste noire', f.chemins.length
    ? el('div', { classe: 'pile' }, f.chemins.map(Commun.chemin)) : vide('Aucun chemin vers un inscrit à moins de 4 liens.'),
    Commun.role() === 'ANALYSTE' ? el('p', {}, el('a', { href: `reseau.html?i=${encodeURIComponent(indice)}`, texte: 'Voir son réseau sur la carte →' })) : null);

  const revenusVerifies = f.revenus.filter(r => r.nature === 'verifie');
  const revenus = carte('Revenus et charges', f.revenus.length ? tableau(['Nature', 'Pièce', 'Période', 'Montant', 'Dossier'],
    f.revenus.map(r => [r.nature === 'declare' ? 'déclaré' : 'vérifié', libelleSource(r.source), periode(r), montant(r.montant),
      lienDossier(r.dossier)])) : vide('Aucun revenu lu.'),
    revenusVerifies.length ? el('p', { classe: 'note', texte: `${revenusVerifies.length} montant(s) vérifié(s) sur pièce.` }) : null,
    f.charges.length ? tableau(['Charge', 'Période', 'Montant', 'Dossier'], f.charges.map(c => [
      c.nature === 'credit_source' ? 'crédit prélevé à la source' : 'échéance de crédit', periode(c), montant(c.montant),
      lienDossier(c.dossier)])) : null);


  const identifiants = carte('Identifiants', f.identifiants.length ? tableau(['Type', 'Valeur', 'Dossier'],
    f.identifiants.map(x => [x.type, x.valeur, lienDossier(x.dossier)])) : vide('Aucun identifiant lu (le RIB, masqué, est dans les comptes).'));

  const operations = f.operations.length ? carte(`Opérations des relevés (${nombre(f.operations.length)})`,
    el('details', {}, el('summary', { texte: 'Afficher les opérations' }),
      tableau(['Date', 'Type', 'Libellé', 'Débit', 'Crédit', 'Dossier'], f.operations.map(o => [date(o.date_operation),
        o.type_operation || '—', court(o.libelle), montant(o.debit), montant(o.credit), lienDossier(o.dossier)])))) : null;

  const liens = f.personnes.length ? f.personnes : f.societes;
  const relations = carte(f.personnes.length ? 'Personnes de la société' : 'Sociétés', liens.length
    ? tableau(['Nom', 'Rôle'], liens.map(s => [s.indice ? Commun.lienFiche(s) : s.nom, s.role]))
    : vide('Aucune.'));

  const comptes = carte('Comptes et véhicules', el('div', {},
    f.comptes.length ? tableau(['RIB', 'Banque', 'Titulaire'], f.comptes.map(c => [c.rib, c.banque || '—', c.titulaire || '—'])) : vide('Aucun compte lu.'),
    f.vehicules.length ? tableau(['Pièce', 'Marque', 'Modèle', 'Prix'], f.vehicules.map(v => [libelleSource(v.type_piece), v.marque || '—', v.modele || '—', montant(v.prix)])) : null));

  const graphies = carte('Graphies et adresses', el('div', {},
    el('div', { classe: 'puces' }, f.alias.map(a => el('span', { classe: 'etiquette', lang: a.ecriture === 'arabe' ? 'ar' : null, texte: `${a.nom} · ${a.nombre}` }))),
    f.adresses.length ? tableau(['Adresse', 'Rôle'], f.adresses.map(a => [a.adresse, a.role || '—'])) : null));

  const listeNoire = f.liste_noire.length ? carte('Inscription sur la liste noire', tableau(
    ['Libellé', 'Type de liste', 'Motif', 'Type de fraude', 'Statut', 'Première saisie', 'Inscriptions'],
    f.liste_noire.map(l => [l.label, l.typeListe, l.motif, l.type_fraude, l.statut, date(l.premiere_saisie), nombre(l.nb_inscriptions)]))) : null;
  const registre = carte('Registre du commerce', f.registre.length ? tableau(['Société', 'Rôle', 'Parts', 'Adresse'],
    f.registre.map(m => [m.societe, m.role, m.parts, m.adresse])) : vide('Aucune mention au registre.'));

  const navigation = el('div', { classe: 'onglets', role: 'tablist', 'aria-label': 'Dossiers du client' });
  const volets = el('div', {});
  const onglets = f.donnees.map((x, k) => {
    const id = `volet-${k}`;
    const onglet = el('button', { classe: 'onglet', type: 'button', role: 'tab', id: `onglet-${k}`, 'aria-selected': String(k === 0),
      tabindex: k === 0 ? '0' : '-1', 'aria-controls': id, texte: `Dossier ${x.reference}${x.demandeur ? '' : ' (cité)'}` });
    const volet = el('div', { id, role: 'tabpanel', 'aria-labelledby': `onglet-${k}`, hidden: k !== 0 });
    let rempli = false;                                // volet construit à la première ouverture
    const ouvrir = () => {
      if (!rempli) { volet.append(voletDossier(x)); rempli = true; }
      for (const o of navigation.children) { const actif = o === onglet; o.setAttribute('aria-selected', String(actif)); o.tabIndex = actif ? 0 : -1; }
      for (const v of volets.children) v.hidden = v !== volet;
    };
    onglet.addEventListener('click', ouvrir);
    onglet.addEventListener('keydown', ev => {
      const pas = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
      if (!pas) return;
      const suivant = onglets[(k + pas + onglets.length) % onglets.length];
      suivant.ouvrir(); suivant.onglet.focus(); ev.preventDefault();
    });
    navigation.append(onglet);
    volets.append(volet);
    if (k === 0) ouvrir();
    return { onglet, ouvrir };
  });
  const toutes = carte('Toutes les données du client',
    el('p', { classe: 'note', texte: 'Chaque valeur lue dans chaque pièce de chaque dossier.' }),
    f.donnees.length ? [navigation, volets] : vide('Aucun dossier.'));

  main.replaceChildren(...[el('p', { classe: 'fil' }, el('a', { href: 'base.html', texte: 'Base client' }), ' › Fiche client'),
    tete, el('div', { classe: 'grille grille-2' }, el('div', { classe: 'pile' }, dossiers, chemins, listeNoire, registre),
      el('div', { classe: 'pile' }, revenus, identifiants, relations, comptes, graphies)), operations, toutes].filter(Boolean));
  main.removeAttribute('aria-busy');

  function voletDossier(x) {
    const contexte = el('dl', { classe: 'definitions' }, x.contexte.filter(c => !c.libelle.startsWith('Alertes')).map(c => [el('dt', { texte: c.libelle }), el('dd', { texte: String(c.valeur) })]));
    const pieces = x.pieces.map(p => el('details', { classe: 'piece' },
      el('summary', {}, el('strong', { texte: libelleSource(p.type) }),
        el('span', { classe: 'note', texte: ` · ${p.statut || '—'} · ${p.faits.length} valeurs` })),
      p.mois.length ? tableau(['Mois', 'Solde début', 'Solde fin', 'Crédits', 'Débits', 'Salaire repéré', 'Échéances', 'Opérations lues'],
        p.mois.map(m => [m.mois ? `${String(m.mois).padStart(2, '0')}/${m.annee}` : '—', montant(m.solde_ouverture), montant(m.solde_cloture),
          montant(m.total_credit), montant(m.total_debit), montant(m.salaire_detecte), montant(m.echeances_credits), nombre(m.nb_operations_lues)])) : null,
      tableau(['Champ', 'Valeur', ''], p.faits.map(fa => [el('code', { texte: fa.cle }), court(fa.valeur),
        fa.statut !== 'normal' ? el('span', { classe: 'etiquette', texte: fa.statut.replaceAll('_', ' ') }) : '']))));
    const lien = x.dossier ? el('p', {}, el('a', { href: `dossier.html?i=${x.dossier}`, texte: 'Ouvrir la vue du dossier' })) : null;
    if (!x.demandeur) {
      return el('div', { classe: 'pile' },
        el('p', { classe: 'note', texte: 'Dossier d’un autre client : seules les pièces qui citent cette fiche sont montrées.' }), lien,
        el('div', {}, el('h3', { texte: `Pièces qui la citent (${x.pieces.length})` }), ...pieces));
    }
    return el('div', { classe: 'pile' },
      el('div', {}, el('h3', { texte: 'Contexte déclaré' }), contexte, lien),
      el('div', {}, el('h3', { texte: `Pièces (${x.pieces.length})` }), ...pieces));
  }
  function periode(x) { return x.mois ? `${String(x.mois).padStart(2, '0')}/${x.annee}` : '—'; }
  function lienDossier(i) { return i ? el('a', { href: `dossier.html?i=${i}`, texte: 'Ouvrir' }) : '—'; }
  function court(v) {
    if (v === null || v === undefined) return '—';
    const t = String(v);
    return t.length > 140 ? el('span', { title: t, texte: `${t.slice(0, 138)}…` }) : t;
  }

  function carte(titre, ...contenu) { return el('section', { classe: 'carte' }, el('h2', { texte: titre }), ...contenu); }
  function vide(t) { return el('p', { classe: 'vide', texte: t }); }
  function tableau(entetes, lignes) {
    return el('div', { classe: 'tableau-enveloppe' }, el('table', {},
      el('thead', {}, el('tr', {}, entetes.map(t => el('th', { texte: t })))),
      el('tbody', {}, lignes.map(l => el('tr', {}, l.map(c => el('td', {}, c ?? '—')))))));
  }
  function libelleSource(s) {
    return ({ v2: 'dossiers', registre: 'registre du commerce', liste_noire: 'liste noire', businessData: 'déclaration',
      BULLETIN_DE_PAIE: 'bulletin de paie', RELEVE_BANCAIRE: 'relevé bancaire', ATTESTATION_TRAVAIL_SALAIRE: 'attestation de salaire',
      ATTESTATION_PENSION: 'attestation de pension', CARTE_GRISE: 'carte grise', FACTURE_PROFORMA_VEHICULE: 'facture proforma' })[s] || s;
  }
});
