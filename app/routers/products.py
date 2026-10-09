"""Rotas de produtos: cadastro e consulta."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.domain.schemas import ProductCreate, ProductRead
from app.infra.database import SessionDep
from app.repository import repo
from app.repository.orm.models import Product
from app.services import handlers

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "",
    response_model=ProductRead,
    status_code=201,
    summary="Cadastra produto",
    description="Cria um produto com preço em centavos.",
)
async def create_product(data: ProductCreate, session: SessionDep) -> Product:
    """Cadastra um produto."""
    return await handlers.create_product(session, data)


@router.get(
    "",
    response_model=list[ProductRead],
    summary="Consulta produtos",
    description=(
        "Com `id`, devolve só aquele produto (lista vazia se não existir). "
        "Sem `id`, lista paginada, mais recentes primeiro."
    ),
)
async def list_products(
    session: SessionDep,
    product_id: Annotated[UUID | None, Query(alias="id")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Product]:
    """Consulta produtos por id ou lista paginada; sempre devolve lista."""
    return await repo.list_products(session, product_id, limit, offset)
