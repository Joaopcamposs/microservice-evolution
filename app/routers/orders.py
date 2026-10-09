"""Rotas de pedidos: criação (preços vêm do catálogo) e consulta."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.domain.schemas import OrderCreate, OrderRead
from app.domain.status import OrderStatus
from app.infra.database import ReadSessionDep, WriteSessionDep
from app.repository.orders import OrderReader
from app.repository.orm.models import Order
from app.services import handlers

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderRead,
    status_code=201,
    summary="Cria pedido",
    description=(
        "Cria um pedido para um usuário existente, reserva o estoque e cobra na própria "
        "requisição (cobrança e e-mail são fakes, lentos). Envia e-mail de pedido recebido e do "
        "resultado da cobrança: o pedido volta `PAID` ou `PAYMENT_FAILED` (que devolve o "
        "estoque). O preço unitário é copiado do produto. 404 se usuário ou produto não "
        "existir; 409 se faltar estoque."
    ),
)
async def create_order(data: OrderCreate, session: WriteSessionDep) -> Order:
    """Cria o pedido e executa o fluxo síncrono (estoque, cobrança, e-mails)."""
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
    session: ReadSessionDep,
    order_id: Annotated[UUID | None, Query(alias="id")] = None,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Order]:
    """Consulta pedidos por id e/ou usuário, ou lista paginada; sempre devolve lista."""
    return await OrderReader(session).list(order_id, user_id, limit, offset)


@router.patch(
    "/{order_id}/status",
    response_model=OrderRead,
    summary="Atualiza o status do pedido",
    description=(
        "Interface da operação para avançar o pedido (ex.: `AWAITING_SHIPMENT` → `SHIPPED`); "
        "o novo status vai no parâmetro `status` (lista de opções no Swagger). "
        "Cada mudança é gravada no histórico e dispara um e-mail. 404 se o pedido não existe; "
        "409 se a transição não é permitida a partir do status atual."
    ),
)
async def update_order_status(
    order_id: UUID, status: OrderStatus, session: WriteSessionDep
) -> Order:
    """Muda o status do pedido seguindo as transições permitidas."""
    return await handlers.update_order_status(session, order_id, status)
