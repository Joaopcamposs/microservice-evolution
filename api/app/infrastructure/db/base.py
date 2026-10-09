"""Classes base do ORM (estilo SQLAlchemy 2.0): `Base` e `Model` (id + created_at)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa única; guarda o `metadata` usado por `create_tables`."""


class Model(Base):
    """Base abstrata das tabelas: `id` UUID (gerado pelo domínio) e `created_at` do banco."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
