"""Cadastros: regras de criação (validação de existência, unicidade) e commit."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import OrderCreate, ProductCreate, UserCreate
from app.domain.status import OrderStatus
from app.repository.orders import OrderWriter
from app.repository.orm.models import Order, OrderItem, OrderStatusChange, Product, User
from app.repository.products import ProductWriter
from app.repository.users import UserReader, UserWriter
from app.services import fakes
from app.services.security import hash_password

logger = logging.getLogger(__name__)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Cadastra usuário (senha como hash, e-mail em minúsculas); 409 se o e-mail já existir.

    O hash (scrypt) é CPU-bound e roda em thread para não travar o event loop.
    """
    user = UserWriter(session).add(
        name=data.name,
        email=data.email.lower(),
        password_hash=await asyncio.to_thread(hash_password, data.password),
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "e-mail já cadastrado") from exc
    return user


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    """Cadastra um produto."""
    product = ProductWriter(session).add(data.name, data.price_cents, data.stock)
    await session.commit()
    return product


async def create_order(session: AsyncSession, data: OrderCreate) -> Order:
    """Cria o pedido, reserva estoque e cobra, tudo dentro da request.

    404 se usuário ou produto faltar; 409 se o estoque for insuficiente. O estoque é
    reservado com as linhas travadas (`FOR UPDATE`) e o commit libera o lock antes das
    chamadas lentas. Cada estado grava histórico; e-mails de RECEIVED e do resultado da
    cobrança (PAID ou PAYMENT_FAILED). AWAITING_PAYMENT dura só a cobrança e não tem e-mail.
    """
    user = await UserReader(session).get(data.user_id)
    if user is None:
        raise HTTPException(404, "usuário não encontrado")
    product_ids = [i.product_id for i in data.items]
    products = await ProductWriter(session).get_for_update(product_ids)
    missing = set(product_ids) - products.keys()
    if missing:
        raise HTTPException(404, f"produtos não encontrados: {sorted(str(m) for m in missing)}")
    short = [str(i.product_id) for i in data.items if products[i.product_id].stock < i.quantity]
    if short:
        raise HTTPException(409, f"estoque insuficiente: {short}")
    for item in data.items:
        products[item.product_id].stock -= item.quantity
    order = Order(
        user_id=data.user_id,
        status=OrderStatus.RECEIVED,
        history=[OrderStatusChange(status=OrderStatus.RECEIVED)],
        items=[
            OrderItem(
                product_id=i.product_id,
                quantity=i.quantity,
                unit_price_cents=products[i.product_id].price_cents,
            )
            for i in data.items
        ],
    )
    OrderWriter(session).add(order)
    await session.commit()
    logger.info("pedido criado order_id=%s total_cents=%d", order.id, order.total_cents)
    await _notify(order, user)

    await _move(session, order, OrderStatus.AWAITING_PAYMENT)
    await session.commit()
    approved = await fakes.charge(order.id, order.total_cents)
    await _move(session, order, OrderStatus.PAID if approved else OrderStatus.PAYMENT_FAILED)
    await session.commit()
    await _notify(order, user)
    await session.commit()
    return order


async def update_order_status(session: AsyncSession, order_id: UUID, target: OrderStatus) -> Order:
    """Move o pedido para `target` (interface da operação) e envia o e-mail da mudança.

    404 se o pedido não existe; 409 se a transição não é permitida. A linha do pedido fica
    travada, então duas atualizações simultâneas não passam as duas pelo mesmo estado.
    """
    order = await OrderWriter(session).get_for_update(order_id)
    if order is None:
        raise HTTPException(404, "pedido não encontrado")
    if not order.status.can_transition_to(target):
        allowed = sorted(s.value for s in order.status.next_states)
        raise HTTPException(409, f"{order.status} → {target} não permitido; possíveis: {allowed}")
    user = await UserReader(session).get(order.user_id)
    assert user is not None  # FK garante
    await _move(session, order, target)
    await session.commit()
    await _notify(order, user)
    await session.commit()
    return order


async def _move(session: AsyncSession, order: Order, target: OrderStatus) -> None:
    """Muda o estado, grava no histórico e, se a cobrança falhou, devolve o estoque."""
    logger.info("pedido order_id=%s status %s → %s", order.id, order.status, target)
    order.status = target
    order.history.append(OrderStatusChange(status=target))
    if target is OrderStatus.PAYMENT_FAILED:
        await ProductWriter(session).release_stock(order.items)
        logger.info("estoque devolvido order_id=%s", order.id)


async def _notify(order: Order, user: User) -> None:
    """Envia o e-mail do estado atual; só marca `notified_at` se o envio der certo."""
    entry = order.history[-1]
    if await fakes.send_email(order.id, user.email, order.status):
        entry.notified_at = datetime.now(UTC)
