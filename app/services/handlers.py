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
    """Cria o pedido e o liquida (cobrança e e-mails) dentro da request.

    Duas fases, que a Etapa 3 do plano separa: `register_order` (rápida, transacional) e
    `settle_order` (lenta, idempotente).
    """
    order = await register_order(session, data)
    return await settle_order(session, order.id, effects)


async def register_order(session: AsyncSession, data: OrderCreate) -> Order:
    """Fase rápida: valida, reserva o estoque e grava o pedido em `RECEIVED`.

    Busca o necessário (usuário e produtos travados com `FOR UPDATE`) e o agregado decide
    (`Order.place`). O commit libera os locks; nada lento acontece aqui.
    """
    writer = OrderWriter(session)
    user, products = await writer.load_placement(data.user_id, data.product_ids)
    if user is None:
        raise UserNotFound
    order = Order.place(data.user_id, data.items, products)
    writer.add(order)
    await session.commit()
    logger.info("pedido criado order_id=%s total_cents=%d", order.id, order.total_cents)
    return order


async def settle_order(session: AsyncSession, order_id: UUID, effects: OrderEffects) -> Order:
    """Fase lenta: e-mail de RECEIVED, cobrança e e-mail do resultado (PAID ou PAYMENT_FAILED).

    Idempotente: só um pedido em `RECEIVED` é liquidado; chamar de novo (ou em paralelo) não
    cobra nem envia nada, pois quem chega depois espera o lock e já vê outro estado.
    A reivindicação (`RECEIVED` → `AWAITING_PAYMENT`, commit) segura o lock só durante o e-mail
    de RECEIVED; a cobrança roda sem lock. AWAITING_PAYMENT dura só a cobrança e não tem e-mail.
    Um pedido que fica em `AWAITING_PAYMENT` por queda do processo não é retomado (Etapa 4).
    """
    loaded = await OrderWriter(session).load_for_update(order_id)
    if loaded is None:
        raise OrderNotFound
    order, user = loaded
    if order.status is not OrderStatus.RECEIVED:
        await session.commit()  # libera o lock
        logger.info("pedido order_id=%s já liquidado ou em curso (%s)", order.id, order.status)
        return order

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
