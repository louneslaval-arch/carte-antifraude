"""Base de l'interface (PostgreSQL en service, SQLite en test) : comptes, révocations, journal d'audit.

Aucune donnée métier ici : le journal ne porte que des indices de nœud, jamais un nom ni un CIN.
"""

from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def maintenant():
    """Heure UTC sans fuseau : même représentation dans PostgreSQL et SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Modele(DeclarativeBase):
    pass


class Utilisateur(Modele):
    __tablename__ = 'utilisateur'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identifiant: Mapped[str] = mapped_column(String(64), unique=True)
    hachage: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    echecs: Mapped[int] = mapped_column(Integer, default=0)
    verrouille: Mapped[bool] = mapped_column(Boolean, default=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


class Revocation(Modele):
    """Session fermée : tous les jetons qui portent ce numéro de session sont refusés jusqu'à `expire`."""
    __tablename__ = 'revocation'
    sid: Mapped[str] = mapped_column(String(64), primary_key=True)
    expire: Mapped[datetime] = mapped_column(DateTime, index=True)


class Journal(Modele):
    __tablename__ = 'journal'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime, default=maintenant, index=True)
    utilisateur: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(32))
    nombre: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(64), default='')


class JournalIndice(Modele):
    """Indices de nœud servis par une ligne du journal (sert aussi au calcul des quotas)."""
    __tablename__ = 'journal_indice'
    journal_id: Mapped[int] = mapped_column(ForeignKey('journal.id', ondelete='CASCADE'), primary_key=True)
    indice: Mapped[int] = mapped_column(Integer, primary_key=True)


def ouvrir(url):
    """Moteur et fabrique de sessions ; crée les tables manquantes."""
    moteur = create_engine(url, future=True)
    if moteur.dialect.name == 'sqlite':
        @event.listens_for(moteur, 'connect')
        def _cles_etrangeres(con, _):
            con.execute('PRAGMA foreign_keys = ON')
    Modele.metadata.create_all(moteur)
    return sessionmaker(moteur, expire_on_commit=False)
