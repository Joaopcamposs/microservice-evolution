"""Cadastros: regras de criação (validação de existência, unicidade) e commit."""

import asyncio

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import OrderCreate, ProductCreate, UserCreate
from app.repository import repo
from app.repository.orm.models import Order, OrderItem, Product, User
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
    product = Product(name=data.name, price_cents=data.price_cents)
    session.add(product)
    await session.commit()
    return product


async def create_order(session: AsyncSession, data: OrderCreate) -> Order:
    """Cria pedido congelando o preço atual de cada produto; 404 se usuário ou produto faltar."""
    if await repo.get_user(session, data.user_id) is None:
        raise HTTPException(404, "usuário não encontrado")
    product_ids = [i.product_id for i in data.items]
    products = await repo.get_products_by_ids(session, product_ids)
    missing = set(product_ids) - products.keys()
    if missing:
        raise HTTPException(404, f"produtos não encontrados: {sorted(str(m) for m in missing)}")
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
    return order
