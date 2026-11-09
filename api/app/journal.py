"""Journal d'audit : qui a reçu quels indices, quand, depuis où. Jamais d'identité métier."""

from datetime import timedelta

from sqlalchemy import delete, func, select

from .base import Journal, JournalIndice, maintenant


def ecrire(fabrique, utilisateur, role, action, indices=(), ip='', nombre=None):
    indices = sorted(set(indices))
    with fabrique.begin() as s:
        ligne = Journal(utilisateur=utilisateur, role=role, action=action, ip=ip or '',
                        nombre=len(indices) if nombre is None else nombre)
        s.add(ligne)
        s.flush()
        s.add_all(JournalIndice(journal_id=ligne.id, indice=i) for i in indices)


def indices_servis(fabrique, utilisateur, action, depuis=timedelta(hours=1)):
    """Indices distincts déjà servis à cet utilisateur pour cette action pendant la période."""
    with fabrique() as s:
        return set(s.scalars(select(JournalIndice.indice).join(Journal).where(
            Journal.utilisateur == utilisateur, Journal.action == action,
            Journal.horodatage >= maintenant() - depuis)))


def nombre_actions(fabrique, utilisateur, actions, depuis=timedelta(hours=1)):
    with fabrique() as s:
        return s.scalar(select(func.count()).select_from(Journal).where(
            Journal.utilisateur == utilisateur, Journal.action.in_(actions),
            Journal.horodatage >= maintenant() - depuis))


def purger(fabrique, jours):
    """Retire les lignes plus anciennes que la durée de conservation."""
    with fabrique.begin() as s:
        limite = maintenant() - timedelta(days=jours)
        anciens = select(Journal.id).where(Journal.horodatage < limite)
        s.execute(delete(JournalIndice).where(JournalIndice.journal_id.in_(anciens)))
        return s.execute(delete(Journal).where(Journal.horodatage < limite)).rowcount
