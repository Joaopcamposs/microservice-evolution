"""Ponto de entrada FastAPI: cria as tabelas na subida e registra as rotas."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infra.database import Base, engine
from app.routers import orders, products, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Cria as tabelas ausentes na subida e libera o pool ao desligar."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Orders API", description="Cadastro de usuários, produtos e pedidos.", lifespan=lifespan
)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(orders.router)
