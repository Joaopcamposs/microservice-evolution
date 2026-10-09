"""Dependências FastAPI: serviços e repositórios de leitura criados no `lifespan`."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.infrastructure.db.read_repositories import (
    ProductReadRepository,
    SaleReadRepository,
    UserReadRepository,
)
from app.infrastructure.db.sessions import ReadSession
from app.services.products import ProductService
from app.services.sales import SaleService
from app.services.users import UserService


def get_user_service(request: Request) -> UserService:
    """Serviço de cadastro de usuários."""
    return request.app.state.user_service


def get_product_service(request: Request) -> ProductService:
    """Serviço de cadastro de produtos."""
    return request.app.state.product_service


def get_sale_service(request: Request) -> SaleService:
    """Serviço de vendas."""
    return request.app.state.sale_service


async def get_read_session(request: Request) -> AsyncGenerator[ReadSession]:
    """Abre uma `ReadSession` por request e a fecha ao final."""
    async with request.app.state.read_session_factory() as session:
        yield session


ReadSessionDep = Annotated[ReadSession, Depends(get_read_session)]


def get_user_reader(session: ReadSessionDep) -> UserReadRepository:
    """Consultas de usuários na sessão de leitura da request."""
    return UserReadRepository(session)


def get_product_reader(session: ReadSessionDep) -> ProductReadRepository:
    """Consultas de produtos na sessão de leitura da request."""
    return ProductReadRepository(session)


def get_sale_reader(session: ReadSessionDep) -> SaleReadRepository:
    """Consultas de vendas na sessão de leitura da request."""
    return SaleReadRepository(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
SaleServiceDep = Annotated[SaleService, Depends(get_sale_service)]
UserReaderDep = Annotated[UserReadRepository, Depends(get_user_reader)]
ProductReaderDep = Annotated[ProductReadRepository, Depends(get_product_reader)]
SaleReaderDep = Annotated[SaleReadRepository, Depends(get_sale_reader)]
CurrentUserId = Annotated[
    UUID,
    Header(alias="X-User-Id", description="Id do usuário que executa a ação (sem autenticação)."),
]
