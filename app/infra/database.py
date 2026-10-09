"""Conexão com o banco: engines (com tracing OTel), sessões de leitura e escrita, base ORM."""

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

# Escrita; leituras dentro de uma escrita (locks, ler o que acabou de gravar) usam esta também.
engine = create_async_engine(DATABASE_URL, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW)
# Leitura: por padrão o mesmo banco e o mesmo pool; com `READ_DATABASE_URL` (ex.: réplica) usa
# um engine próprio.
READ_DATABASE_URL = os.environ.get("READ_DATABASE_URL")
read_engine = (
    create_async_engine(READ_DATABASE_URL, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW)
    if READ_DATABASE_URL
    else engine
)
# Um span por query, filho do span da requisição. Uma única chamada: o instrumentor é singleton
# e ignora (com aviso) uma segunda. Exige SQLAlchemy < 2.1 (ver `pyproject.toml`).
SQLAlchemyInstrumentor().instrument(engines=[e.sync_engine for e in {engine, read_engine}])
WriteSession = async_sessionmaker(engine, expire_on_commit=False)
# Sem autoflush: a sessão de leitura nunca grava.
ReadSession = async_sessionmaker(read_engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos; guarda o `metadata` usado em `create_all`."""


async def get_write_session() -> AsyncGenerator[AsyncSession]:
    """Dependência FastAPI: sessão de escrita, uma por request, fechada ao final."""
    async with WriteSession() as session:
        yield session


async def get_read_session() -> AsyncGenerator[AsyncSession]:
    """Dependência FastAPI: sessão de leitura, uma por request, fechada ao final."""
    async with ReadSession() as session:
        yield session


WriteSessionDep = Annotated[AsyncSession, Depends(get_write_session)]
ReadSessionDep = Annotated[AsyncSession, Depends(get_read_session)]
