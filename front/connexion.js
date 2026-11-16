'use strict';
document.addEventListener('DOMContentLoaded', () => {
  Commun.entete(null);
  const f = document.getElementById('formulaire');
  f.addEventListener('submit', async ev => {
    ev.preventDefault();
    const erreur = document.getElementById('erreur');
    erreur.textContent = '';
    const r = await fetch('/api/auth/connexion', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifiant: f.identifiant.value, mot_de_passe: f.mot_de_passe.value }),
    });
    if (!r.ok) { erreur.textContent = 'Identifiant ou mot de passe incorrect.'; return; }
    const corps = await r.json();
    try { sessionStorage.setItem('carte_role', corps.role); } catch (e) { /* rien */ }
    const retour = Commun.parametre('retour') || 'index.html';
    location.href = /^[a-z_]+\.html(\?i=\d+)?$/.test(retour) ? retour : 'index.html';
  });
});
