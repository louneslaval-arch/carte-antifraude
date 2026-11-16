from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from .. import journal
from ..auth import Session, exige
from ..base import Journal, JournalIndice
from ..graphe import PublicationRefusee, charger

routeur = APIRouter(prefix='/api/admin')


@routeur.post('/recharger')
def recharger(request: Request, session: Session = Depends(exige('admin'))):
    """Recharge la publication courante sans redémarrer ; en cas de refus, l'ancienne reste servie."""
    etat = request.app.state.etat
    if not etat.reglages.publication:
        raise HTTPException(409, 'CARTE_PUBLICATION non défini')
    try:
        nouvelle = charger(etat.reglages.publication, etat.reglages.donnees_reelles)
    except PublicationRefusee as e:
        journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recharger_refus', ip=session.ip)
        raise HTTPException(409, f'Publication refusée : {e}') from None
    etat.publication = nouvelle
    purges = journal.purger(etat.base, etat.reglages.journal_jours)
    journal.ecrire(etat.base, session.utilisateur, session.role.value, 'recharger', ip=session.ip)
    return {'date_publication': nouvelle.manifeste['date_publication'], 'noeuds': nouvelle.noeuds,
            'journal_purge': purges}


@routeur.get('/journal')
def lire_journal(request: Request, session: Session = Depends(exige('admin')),
                 utilisateur: Optional[str] = Query(None, max_length=64), du: Optional[date] = None,
                 au: Optional[date] = None, page: int = Query(1, ge=1), taille: int = Query(100, ge=1, le=500)):
    filtres = []
    if utilisateur:
        filtres.append(Journal.utilisateur == utilisateur)
    if du:
        filtres.append(Journal.horodatage >= datetime.combine(du, datetime.min.time()))
    if au:
        filtres.append(Journal.horodatage < datetime.combine(au + timedelta(days=1), datetime.min.time()))
    with request.app.state.etat.base() as s:
        total = s.scalar(select(func.count()).select_from(Journal).where(*filtres))
        lignes = s.scalars(select(Journal).where(*filtres).order_by(Journal.id.desc())
                           .offset((page - 1) * taille).limit(taille)).all()
        indices = {}
        for j, i in s.execute(select(JournalIndice.journal_id, JournalIndice.indice)
                              .where(JournalIndice.journal_id.in_([l.id for l in lignes]))
                              .order_by(JournalIndice.indice)):
            indices.setdefault(j, []).append(i)
    return {'total': total, 'page': page, 'lignes': [
        dict(id=l.id, horodatage=l.horodatage.isoformat(timespec='seconds') + 'Z', utilisateur=l.utilisateur,
             role=l.role, action=l.action, nombre=l.nombre, ip=l.ip, indices=indices.get(l.id, []))
        for l in lignes]}
