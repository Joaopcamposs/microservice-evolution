"""Criação do schema a partir dos modelos ORM (`create_all`).

Escolha da demo: sem migrações (nem Alembic). `create_all` só cria tabelas ausentes;
quando o schema mudar, recria-se o banco (`make reset`).
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.db import models  # noqa: F401  (registra as tabelas no metadata)
from app.infrastructure.db.base import Base


async def create_tables(engine: AsyncEngine) -> None:
    """Cria as tabelas que ainda não existem."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
