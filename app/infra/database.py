"""Conexão com o banco: engine (com tracing OTel), sessão por request e base dos modelos ORM."""

import os
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app")

# Pool por processo: com N workers uvicorn, o total é N x (POOL_SIZE + MAX_OVERFLOW)
# e precisa caber no `max_connections` do Postgres (100 por padrão).
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))

engine = create_async_engine(DATABASE_URL, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW)
# Um span por query, filho do span da requisição (sem exporter configurado, é no-op).
# `skip_dep_check`: o instrumentor declara suporte só até SQLAlchemy 2.0; aqui usamos o 2.1.
SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, skip_dep_check=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos; guarda o `metadata` usado em `create_all`."""


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Dependência FastAPI: uma sessão por request, fechada ao final."""
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
