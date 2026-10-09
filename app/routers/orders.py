"""Rotas de pedidos: criação (preços vêm do catálogo) e consulta."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.domain.schemas import OrderCreate, OrderRead
from app.infra.database import SessionDep
from app.repository import repo
from app.repository.orm.models import Order
from app.services import handlers

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderRead,
    status_code=201,
    summary="Cria pedido",
    description=(
        "Cria um pedido para um usuário existente. O preço unitário de cada item é copiado "
        "do produto no momento da criação. 404 se usuário ou produto não existir."
    ),
)
async def create_order(data: OrderCreate, session: SessionDep) -> Order:
    """Cria um pedido com itens, congelando o preço atual de cada produto."""
    return await handlers.create_order(session, data)


@router.get(
    "",
    response_model=list[OrderRead],
    summary="Consulta pedidos",
    description=(
        "Com `id`, devolve só aquele pedido (lista vazia se não existir). Sem `id`, lista "
        "paginada, mais recentes primeiro. `user_id` filtra pelos pedidos de um usuário."
    ),
)
async def list_orders(
    session: SessionDep,
    order_id: Annotated[UUID | None, Query(alias="id")] = None,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Order]:
    """Consulta pedidos por id e/ou usuário, ou lista paginada; sempre devolve lista."""
    return await repo.list_orders(session, order_id, user_id, limit, offset)
