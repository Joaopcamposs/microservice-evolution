"""Casos de uso: busca o necessário, o agregado decide, grava, commit e dispara efeitos."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import EmailAlreadyExists, OrderNotFound, UserNotFound
from app.domain.order import Order
from app.domain.product import Product
from app.domain.schemas import OrderCreate, ProductCreate, UserCreate
from app.domain.status import OrderStatus
from app.domain.user import User
from app.repository.orders import OrderWriter
from app.repository.products import ProductWriter
from app.repository.users import UserWriter
from app.services.effects import OrderEffects

logger = logging.getLogger(__name__)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Cadastra usuário pelo agregado (e-mail normalizado, senha em hash).

    Levanta `EmailAlreadyExists` se o e-mail já existir.

    O hash (scrypt) é CPU-bound e roda em thread para não travar o event loop.
    """
    user = await asyncio.to_thread(User.register, data.name, data.email, data.password)
    UserWriter(session).add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise EmailAlreadyExists from exc
    return user


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    """Cadastra um produto."""
    product = Product.create(data.name, data.price_cents, data.stock)
    ProductWriter(session).add(product)
    await session.commit()
    return product


async def create_order(session: AsyncSession, data: OrderCreate, effects: OrderEffects) -> Order:
    """Cria o pedido, reserva estoque e cobra, tudo dentro da request.

    Busca o necessário (usuário e produtos travados com `FOR UPDATE`), o agregado decide
    (`Order.place`) e, se der certo, grava e faz commit, o que libera os locks antes
    das chamadas lentas. Depois vêm os efeitos: e-mail de RECEIVED e, após a cobrança, o do
    resultado (PAID ou PAYMENT_FAILED). AWAITING_PAYMENT dura só a cobrança e não tem e-mail.
    """
    writer = OrderWriter(session)
    user, products = await writer.load_placement(data.user_id, data.product_ids)
    if user is None:
        raise UserNotFound
    order = Order.place(data.user_id, data.items, products)
    writer.add(order)
    await session.commit()
    logger.info("pedido criado order_id=%s total_cents=%d", order.id, order.total_cents)

    await effects.notify(order, user)
    order.begin_payment()
    await session.commit()
    order.settle_payment(await effects.charge(order))
    await _after_move(session, order)
    await session.commit()
    await effects.notify(order, user)
    await session.commit()
    return order


async def update_order_status(
    session: AsyncSession, order_id: UUID, target: OrderStatus, effects: OrderEffects
) -> Order:
    """Move o pedido para `target` (interface da operação) e envia o e-mail da mudança.

    Levanta `OrderNotFound` ou `InvalidTransition` (transição não permitida). A linha do pedido
    fica travada, então duas atualizações simultâneas não passam as duas pelo mesmo estado.
    """
    loaded = await OrderWriter(session).load_for_update(order_id)
    if loaded is None:
        raise OrderNotFound
    order, user = loaded
    order.move_to(target)
    await _after_move(session, order)
    await session.commit()
    await effects.notify(order, user)
    await session.commit()
    return order


async def _after_move(session: AsyncSession, order: Order) -> None:
    """Registra a mudança de estado no log e devolve o estoque se a cobrança foi recusada."""
    logger.info("pedido order_id=%s status=%s", order.id, order.status)
    if order.releases_stock:
        await ProductWriter(session).release_stock(order.items)
        logger.info("estoque devolvido order_id=%s", order.id)
