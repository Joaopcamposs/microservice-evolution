"""Ponto de entrada FastAPI: cria as tabelas na subida e registra as rotas."""

from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select

from app.infra.database import Base, engine
from app.routers import orders, products, users

SCHEMA_LOCK_ID = 7_001  # chave arbitrária do lock consultivo


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Cria as tabelas ausentes na subida e libera o pool ao desligar.

    Com vários workers subindo juntos num banco vazio, um lock consultivo do Postgres
    serializa o `create_all` (senão dois workers tentam criar a mesma tabela).
    """
    async with engine.begin() as conn:
        await conn.execute(select(func.pg_advisory_xact_lock(SCHEMA_LOCK_ID)))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def is_healthcheck(scope: MutableMapping[str, Any]) -> bool:
    """Exclui da telemetria o healthcheck do compose (`/docs`), que só geraria ruído."""
    return scope.get("path") == "/docs"


app = FastAPI(
    title="Orders API",
    description="Cadastro de usuários, produtos e pedidos.",
    lifespan=lifespan,
    telemetry={"exclude": is_healthcheck},
)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(orders.router)
