"""Ponto de entrada FastAPI: monta engine, UoW, serviços, integrações fake e rotas."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.domain.errors import (
    DomainError,
    EmailAlreadyRegisteredError,
    InsufficientStockError,
    InvalidSaleTransitionError,
    InvalidValueError,
    ProductNotFoundError,
    UserNotFoundError,
)
from app.infrastructure.db.schema import create_tables
from app.infrastructure.db.sessions import (
    create_read_engine,
    create_read_session_factory,
    create_write_engine,
    create_write_session_factory,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.integrations.email import FakeEmailSender
from app.integrations.payment import FakePaymentGateway
from app.routes import products, sales, users
from app.services.products import ProductService
from app.services.sales import SaleService
from app.services.users import UserService

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    UserNotFoundError: 404,
    ProductNotFoundError: 404,
    EmailAlreadyRegisteredError: 409,
    InsufficientStockError: 409,
    InvalidSaleTransitionError: 409,
    InvalidValueError: 422,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a aplicação; `settings` permite injetar configuração (testes)."""
    resolved = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Cria o estado de processo (engine, tabelas, serviços) e o libera ao desligar."""
        write_engine = create_write_engine(resolved.database_url)
        read_engine = create_read_engine(resolved.read_url)
        await create_tables(write_engine)
        write_factory = create_write_session_factory(write_engine)

        def new_uow() -> SqlAlchemyUnitOfWork:
            """Fábrica de unidades de trabalho (uma por operação de negócio)."""
            return SqlAlchemyUnitOfWork(write_factory)

        app.state.write_engine = write_engine
        app.state.read_session_factory = create_read_session_factory(read_engine)
        app.state.user_service = UserService(new_uow)
        app.state.product_service = ProductService(new_uow)
        app.state.sale_service = SaleService(
            new_uow, FakePaymentGateway(resolved), FakeEmailSender(resolved)
        )
        yield
        await write_engine.dispose()
        await read_engine.dispose()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title="Sales API", description="API de vendas (etapa 0: síncrona).", lifespan=lifespan
    )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        """Traduz erro de domínio em status HTTP (500 se o tipo não estiver mapeado)."""
        return JSONResponse({"detail": str(exc)}, status_code=_STATUS_BY_ERROR.get(type(exc), 500))

    app.include_router(users.router)
    app.include_router(products.router)
    app.include_router(sales.router)

    @app.get(
        "/health",
        tags=["health"],
        summary="Liveness",
        description="Responde 200 se o processo está de pé.",
    )
    async def health() -> dict[str, str]:
        """Liveness simples."""
        return {"status": "ok"}

    return app


app = create_app()
