'use strict';
document.addEventListener('DOMContentLoaded', async () => {
  const { el, api, nombre, montant, date, niveau, initiales } = Commun;
  Commun.entete('base.html');
  const main = document.getElementById('contenu');
  const indice = Commun.parametre('i');
  let f;
  try {
    f = await api(`/api/base/clients/${encodeURIComponent(indice)}`);
  } catch (e) {
    main.replaceChildren(el('p', { classe: 'carte', texte: e.statut === 403 ? 'Fiche réservée à la cellule fraude.' : 'Fiche introuvable.' }));
    return;
  }
  const id = f.identite;
  const meilleur = f.chemins[0];
  const definitions = id.type === 'personne'
    ? [['CIN', id.cin], ['Date de naissance', date(id.date_naissance)], ['Adresse retenue', id.adresse]]
    : [['RC', id.rc ? `${id.rc} · ${id.tribunal || ''}` : null], ['ICE', id.ice], ['Siège', id.adresse]];
  const tete = el('section', { classe: 'carte identite' },
    el('div', { classe: `avatar ${id.type}${id.inscrit ? ' inscrit' : ''}`, 'aria-hidden': 'true', texte: initiales(id.nom) }),
    el('div', {},
      el('h1', { texte: id.nom }),
      el('div', { classe: 'puces' },
        id.inscrit ? el('span', { classe: 'etiquette etiquette-rouge', texte: 'Inscrit sur la liste noire' }) : null,
        meilleur ? niveau(meilleur.niveau, `Lien : ${meilleur.niveau_libelle}`) : niveau(null, 'Aucun lien avec la liste noire'),
        el('span', { classe: 'etiquette', texte: id.type === 'personne' ? 'Personne' : 'Société' }),
        Object.entries(f.sources).map(([s, n]) => el('span', { classe: 'etiquette', texte: `mentions (${libelleSource(s)}) : ${n}` }))),
      el('dl', { classe: 'definitions' }, definitions.map(([k, v]) => [el('dt', { texte: k }), el('dd', { texte: v || '—' })]))),
    null);

  const dossiers = carte('Dossiers', f.dossiers.length ? tableau(
    ['Reçu', 'Produit', 'Rôle', 'Niveau', 'Verdict v2', 'Incohérences', ''],
    f.dossiers.map(d => [date(d.recu), d.produit, d.role, niveau(d.niveau, d.niveau_libelle), d.verdict || '—',
      d.incoherences ? nombre(d.incoherences) : '—', el('a', { href: `dossier.html?i=${d.indice}`, texte: 'Ouvrir' })])) : vide('Aucun dossier.'));

  const chemins = carte('Liens avec la liste noire', f.chemins.length
    ? el('div', { classe: 'pile' }, f.chemins.map(Commun.chemin)) : vide('Aucun chemin vers un inscrit à moins de 4 liens.'));

  const revenusVerifies = f.revenus.filter(r => r.nature === 'verifie');
  const revenus = carte('Revenus', f.revenus.length ? tableau(['Nature', 'Source', 'Période', 'Montant'],
    f.revenus.map(r => [r.nature === 'declare' ? 'déclaré' : 'vérifié', libelleSource(r.source),
      r.mois ? `${String(r.mois).padStart(2, '0')}/${r.annee}` : '—', montant(r.montant)])) : vide('Aucun revenu lu.'),
    revenusVerifies.length ? el('p', { classe: 'note', texte: `${revenusVerifies.length} montant(s) vérifié(s) sur pièce.` }) : null);

  const liens = f.personnes.length ? f.personnes : f.societes;
  const relations = carte(f.personnes.length ? 'Personnes de la société' : 'Sociétés', liens.length
    ? tableau(['Nom', 'Rôle', 'Source'], liens.map(s => [s.indice ? Commun.lienFiche(s) : s.nom, s.role, libelleSource(s.source)]))
    : vide('Aucune.'));

  const comptes = carte('Comptes et véhicules', el('div', {},
    f.comptes.length ? tableau(['RIB', 'Banque', 'Titulaire'], f.comptes.map(c => [c.rib, c.banque || '—', c.titulaire || '—'])) : vide('Aucun compte lu.'),
    f.vehicules.length ? tableau(['Pièce', 'Marque', 'Modèle', 'Prix'], f.vehicules.map(v => [libelleSource(v.type_piece), v.marque || '—', v.modele || '—', montant(v.prix)])) : null));

  const graphies = carte('Graphies et adresses', el('div', {},
    el('div', { classe: 'puces' }, f.alias.map(a => el('span', { classe: 'etiquette', lang: a.ecriture === 'arabe' ? 'ar' : null, texte: `${a.nom} · ${a.nombre}` }))),
    f.adresses.length ? tableau(['Adresse', 'Source', 'Rôle'], f.adresses.map(a => [a.adresse, libelleSource(a.source), a.role || '—'])) : null));

  const listeNoire = f.liste_noire.length ? carte('Inscription sur la liste noire', tableau(
    ['Libellé', 'Type de liste', 'Motif', 'Type de fraude', 'Statut', 'Première saisie', 'Inscriptions'],
    f.liste_noire.map(l => [l.label, l.typeListe, l.motif, l.type_fraude, l.statut, date(l.premiere_saisie), nombre(l.nb_inscriptions)]))) : null;
  const registre = carte('Registre du commerce', f.registre.length ? tableau(['Société', 'Rôle', 'Parts', 'Adresse'],
    f.registre.map(m => [m.societe, m.role, m.parts, m.adresse])) : vide('Aucune mention au registre.'));

  const navigation = el('div', { classe: 'onglets', role: 'tablist', 'aria-label': 'Dossiers du client' });
  const volets = el('div', {});
  f.donnees.forEach((x, k) => {
    const id = `volet-${k}`;
    const onglet = el('button', { classe: 'onglet', type: 'button', role: 'tab', 'aria-selected': String(k === 0),
      'aria-controls': id, texte: `Dossier ${x.reference}${x.demandeur ? '' : ' (cité)'}` });
    const volet = el('div', { id, role: 'tabpanel', hidden: k !== 0 }, voletDossier(x));
    onglet.addEventListener('click', () => {
      for (const o of navigation.children) o.setAttribute('aria-selected', String(o === onglet));
      for (const v of volets.children) v.hidden = v !== volet;
    });
    navigation.append(onglet);
    volets.append(volet);
  });
  const toutes = carte('Toutes les données du client',
    el('p', { classe: 'note', texte: 'Chaque valeur lue dans chaque pièce, avec son origine : lue par l’amont, relue de façon ciblée, ou fusion des deux.' }),
    f.donnees.length ? [navigation, volets] : vide('Aucun dossier.'));

  main.replaceChildren(el('p', { classe: 'fil' }, el('a', { href: 'base.html', texte: 'Base client' }), ' › Fiche client'),
    tete, el('div', { classe: 'grille grille-2' }, el('div', { classe: 'pile' }, dossiers, chemins, listeNoire, registre),
      el('div', { classe: 'pile' }, revenus, relations, comptes, graphies)), toutes);

  function voletDossier(x) {
    const contexte = el('dl', { classe: 'definitions' }, x.contexte.map(c => [el('dt', { texte: c.libelle }), el('dd', { texte: String(c.valeur) })]));
    const pieces = x.pieces.map(p => el('details', { classe: 'piece' },
      el('summary', {}, el('strong', { texte: libelleSource(p.type) }),
        el('span', { classe: 'note', texte: ` · ${p.source === 'REANALYSE' ? 'relue' : 'amont'} · ${p.statut || '—'} · ${p.faits.length} valeurs` })),
      p.mois.length ? tableau(['Mois', 'Solde début', 'Solde fin', 'Crédits', 'Débits', 'Salaire repéré', 'Échéances', 'Opérations lues'],
        p.mois.map(m => [m.mois ? `${String(m.mois).padStart(2, '0')}/${m.annee}` : '—', montant(m.solde_ouverture), montant(m.solde_cloture),
          montant(m.total_credit), montant(m.total_debit), montant(m.salaire_detecte), montant(m.echeances_credits), nombre(m.nb_operations_lues)])) : null,
      tableau(['Champ', 'Valeur', 'Origine', ''], p.faits.map(fa => [el('code', { texte: fa.cle }), court(fa.valeur), fa.origine,
        fa.statut !== 'normal' ? el('span', { classe: 'etiquette', texte: fa.statut.replaceAll('_', ' ') }) : '']))));
    const controles = x.controles.length ? el('div', { classe: 'puces' }, x.controles.map(c =>
      el('span', { classe: 'etiquette' + (c.resultat && c.resultat !== 'OK' ? ' etiquette-rouge' : ''), title: c.explication || '',
        texte: `${c.controle} · ${c.resultat || '—'}` }))) : vide('Aucun contrôle.');
    return el('div', { classe: 'pile' },
      el('div', {}, el('h3', { texte: 'Contexte déclaré' }), contexte, x.dossier ? el('p', {}, el('a', { href: `dossier.html?i=${x.dossier}`, texte: 'Ouvrir la vue du dossier' })) : null),
      el('div', {}, el('h3', { texte: `Pièces (${x.pieces.length})` }), ...pieces),
      el('div', {}, el('h3', { texte: 'Contrôles de la v2' }), controles));
  }
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
