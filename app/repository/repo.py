"""Consultas ao banco via ORM: funções que só leem, sem regra de negócio nem commit."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.orm.models import Order, Product, User


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    """Busca um usuário pelo id; `None` se não existir."""
    return await session.get(User, user_id)


async def list_users(
    session: AsyncSession, user_id: UUID | None, limit: int, offset: int
) -> list[User]:
    """Lista usuários, mais recentes primeiro (UUID v7 ordena por criação); `user_id` filtra."""
    stmt = select(User).order_by(User.id.desc()).limit(limit).offset(offset)
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    return list(await session.scalars(stmt))


async def list_products(
    session: AsyncSession, product_id: UUID | None, limit: int, offset: int
) -> list[Product]:
    """Lista produtos, mais recentes primeiro; `product_id` filtra."""
    stmt = select(Product).order_by(Product.id.desc()).limit(limit).offset(offset)
    if product_id is not None:
        stmt = stmt.where(Product.id == product_id)
    return list(await session.scalars(stmt))


async def get_products_by_ids(
    session: AsyncSession, ids: list[UUID], lock: bool = False
) -> dict[UUID, Product]:
    """Busca vários produtos de uma vez; ids inexistentes ficam fora do resultado.

    Com `lock`, trava as linhas (`FOR UPDATE`) até o fim da transação, em ordem de id
    para que pedidos concorrentes não se bloqueiem em ciclo (deadlock).
    """
    stmt = select(Product).where(Product.id.in_(ids)).order_by(Product.id)
    if lock:
        stmt = stmt.with_for_update()
    return {p.id: p for p in await session.scalars(stmt)}


async def get_order(session: AsyncSession, order_id: UUID, lock: bool = False) -> Order | None:
    """Busca um pedido pelo id; com `lock`, trava a linha (`FOR UPDATE`) até o fim da transação."""
    return await session.get(Order, order_id, with_for_update=lock)


async def list_orders(
    session: AsyncSession, order_id: UUID | None, user_id: UUID | None, limit: int, offset: int
) -> list[Order]:
    """Lista pedidos, mais recentes primeiro; `order_id` e `user_id` opcionais filtram."""
    stmt = select(Order).order_by(Order.id.desc()).limit(limit).offset(offset)
    if order_id is not None:
        stmt = stmt.where(Order.id == order_id)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    return list(await session.scalars(stmt))
