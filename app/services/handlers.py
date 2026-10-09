"""Cadastros: regras de criação (validação de existência, unicidade) e commit."""

import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import InsufficientStock, InvalidTransition
from app.domain.order import Order
from app.domain.product import Product
from app.domain.schemas import OrderCreate, ProductCreate, UserCreate
from app.domain.status import OrderStatus
from app.domain.user import User
from app.repository.orders import OrderWriter
from app.repository.products import ProductWriter
from app.repository.users import UserReader, UserWriter
from app.services.gateways import EmailSender, PaymentGateway

logger = logging.getLogger(__name__)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Cadastra usuário pelo agregado (e-mail normalizado, senha em hash); 409 se o e-mail existir.

    O hash (scrypt) é CPU-bound e roda em thread para não travar o event loop.
    """
    user = await asyncio.to_thread(User.register, data.name, data.email, data.password)
    UserWriter(session).add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "e-mail já cadastrado") from exc
    return user


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    """Cadastra um produto."""
    product = Product.create(data.name, data.price_cents, data.stock)
    ProductWriter(session).add(product)
    await session.commit()
    return product


async def create_order(
    session: AsyncSession, data: OrderCreate, payment: PaymentGateway, email: EmailSender
) -> Order:
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
    try:
        order = Order.place(
            data.user_id, [(products[i.product_id], i.quantity) for i in data.items]
        )
    except InsufficientStock as exc:
        raise HTTPException(409, str(exc)) from exc
    OrderWriter(session).add(order)
    await session.commit()
    logger.info("pedido criado order_id=%s total_cents=%d", order.id, order.total_cents)
    await _notify(order, user, email)

    await _move(session, order, OrderStatus.AWAITING_PAYMENT)
    await session.commit()
    approved = await payment.charge(order.id, order.total_cents)
    await _move(session, order, OrderStatus.PAID if approved else OrderStatus.PAYMENT_FAILED)
    await session.commit()
    await _notify(order, user, email)
    await session.commit()
    return order


async def update_order_status(
    session: AsyncSession, order_id: UUID, target: OrderStatus, email: EmailSender
) -> Order:
    """Move o pedido para `target` (interface da operação) e envia o e-mail da mudança.

    404 se o pedido não existe; 409 se a transição não é permitida. A linha do pedido fica
    travada, então duas atualizações simultâneas não passam as duas pelo mesmo estado.
    """
    order = await OrderWriter(session).get_for_update(order_id)
    if order is None:
        raise HTTPException(404, "pedido não encontrado")
    user = await UserReader(session).get(order.user_id)
    assert user is not None  # FK garante
    try:
        await _move(session, order, target)
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    await _notify(order, user, email)
    await session.commit()
    return order


async def _move(session: AsyncSession, order: Order, target: OrderStatus) -> None:
    """Muda o estado, grava no histórico e, se a cobrança falhou, devolve o estoque."""
    previous = order.status
    order.move_to(target)
    logger.info("pedido order_id=%s status %s → %s", order.id, previous, target)
    if target is OrderStatus.PAYMENT_FAILED:
        await ProductWriter(session).release_stock(order.items)
        logger.info("estoque devolvido order_id=%s", order.id)


async def _notify(order: Order, user: User, email: EmailSender) -> None:
    """Envia o e-mail do estado atual; só marca `notified_at` se o envio der certo."""
    if await email.send(order.id, user.email, order.status):
        order.mark_notified()
