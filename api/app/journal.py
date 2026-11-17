"""Journal d'audit : qui a reçu quels indices, quand, depuis où. Jamais d'identité métier."""

from datetime import timedelta

from sqlalchemy import delete, func, select

from .base import Journal, JournalIndice, Revocation, maintenant


def ecrire(fabrique, utilisateur, role, action, indices=(), ip='', nombre=None, epoque=''):
    indices = sorted(set(indices))
    with fabrique.begin() as s:
        ligne = Journal(utilisateur=utilisateur, role=role, action=action, ip=ip or '', epoque=epoque or '',
                        nombre=len(indices) if nombre is None else nombre)
        s.add(ligne)
        s.flush()
        s.add_all(JournalIndice(journal_id=ligne.id, indice=i) for i in indices)


def indices_servis(fabrique, utilisateur, actions, depuis=timedelta(hours=1)):
    """Couples (époque, indice) distincts déjà servis à cet utilisateur pour ces actions pendant la période : un même
    entier désigne des nœuds différents d'une publication (ou de la base client) à l'autre."""
    with fabrique() as s:
        return set(s.execute(select(Journal.epoque, JournalIndice.indice).join(Journal).where(
            Journal.utilisateur == utilisateur, Journal.action.in_(actions),
            Journal.horodatage >= maintenant() - depuis)).all())


def nombre_actions(fabrique, utilisateur, actions, depuis=timedelta(hours=1)):
    with fabrique() as s:
        return s.scalar(select(func.count()).select_from(Journal).where(
            Journal.utilisateur == utilisateur, Journal.action.in_(actions),
            Journal.horodatage >= maintenant() - depuis))


def purger(fabrique, jours):
    """Retire les lignes plus anciennes que la durée de conservation, et les révocations de jetons expirés."""
    with fabrique.begin() as s:
        s.execute(delete(Revocation).where(Revocation.expire < maintenant()))
        limite = maintenant() - timedelta(days=jours)
        anciens = select(Journal.id).where(Journal.horodatage < limite)
        s.execute(delete(JournalIndice).where(JournalIndice.journal_id.in_(anciens)))
        return s.execute(delete(Journal).where(Journal.horodatage < limite)).rowcount
