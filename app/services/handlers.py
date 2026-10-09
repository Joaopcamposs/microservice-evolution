"""Cadastros: regras de criação (validação de existência, unicidade) e commit."""

import asyncio

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import OrderCreate, ProductCreate, UserCreate
from app.domain.status import OrderStatus
from app.repository import repo
from app.repository.orm.models import Order, OrderItem, Product, User
from app.services import fakes
from app.services.security import hash_password


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Cadastra usuário (senha como hash, e-mail em minúsculas); 409 se o e-mail já existir.

    O hash (scrypt) é CPU-bound e roda em thread para não travar o event loop.
    """
    user = User(
        name=data.name,
        email=data.email.lower(),
        password_hash=await asyncio.to_thread(hash_password, data.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "e-mail já cadastrado") from exc
    return user


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    """Cadastra um produto."""
    product = Product(name=data.name, price_cents=data.price_cents, stock=data.stock)
    session.add(product)
    await session.commit()
    return product


async def create_order(session: AsyncSession, data: OrderCreate) -> Order:
    """Cria o pedido, reserva estoque, cobra e envia o e-mail, tudo dentro da request.

    404 se usuário ou produto faltar; 409 se o estoque for insuficiente. O estoque é
    reservado com as linhas travadas (`FOR UPDATE`) e o commit libera o lock antes das
    chamadas lentas. Cobrança recusada → `PAYMENT_FAILED` e estoque devolvido. Falha no
    e-mail deixa o pedido `PAID`.
    """
    user = await repo.get_user(session, data.user_id)
    if user is None:
        raise HTTPException(404, "usuário não encontrado")
    product_ids = [i.product_id for i in data.items]
    products = await repo.get_products_by_ids(session, product_ids, lock=True)
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
        items=[
            OrderItem(
                product_id=i.product_id,
                quantity=i.quantity,
                unit_price_cents=products[i.product_id].price_cents,
            )
            for i in data.items
        ],
    )
    session.add(order)
    await session.commit()

    if not await fakes.charge(order.id, order.total_cents):
        await _release_stock(session, order)
        order.status = OrderStatus.PAYMENT_FAILED
        await session.commit()
        return order
    order.status = OrderStatus.PAID
    await session.commit()

    if await fakes.send_email(order.id, user.email):
        order.status = OrderStatus.COMPLETED
        await session.commit()
    return order


async def _release_stock(session: AsyncSession, order: Order) -> None:
    """Devolve ao estoque as quantidades do pedido (UPDATE atômico, sem ler antes).

    Atualiza em ordem de `product_id`, a mesma da reserva, para não gerar deadlock.
    """
    for item in sorted(order.items, key=lambda i: i.product_id):
        await session.execute(
            update(Product)
            .where(Product.id == item.product_id)
            .values(stock=Product.stock + item.quantity)
        )
