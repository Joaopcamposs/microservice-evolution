"""Repositórios de produto: `ProductReader` só lê, `ProductWriter` grava e trava estoque."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select, update

from app.domain.order import OrderItem
from app.domain.product import Product
from app.repository.base import Repository
from app.repository.orm.tables import products


class ProductReader(Repository):
    """Consultas de produto, sem efeito colateral."""

    async def list(self, product_id: UUID | None, limit: int, offset: int) -> list[Product]:
        """Lista produtos, mais recentes primeiro; `product_id` filtra."""
        stmt = select(Product).order_by(products.c.id.desc()).limit(limit).offset(offset)
        if product_id is not None:
            stmt = stmt.where(products.c.id == product_id)
        return list(await self.session.scalars(stmt))


class ProductWriter(Repository):
    """Gravações de produto; o commit é de quem chama."""

    def add(self, product: Product) -> None:
        """Registra o produto na sessão (vai ao banco no commit)."""
        self.session.add(product)

    async def get_for_update(self, ids: list[UUID]) -> dict[UUID, Product]:
        """Busca e trava os produtos (`FOR UPDATE`) até o fim da transação.

        Ids inexistentes ficam fora do resultado. A ordem por id é a mesma em toda
        operação, para que pedidos concorrentes não se bloqueiem em ciclo (deadlock).
        """
        stmt = (
            select(Product).where(products.c.id.in_(ids)).order_by(products.c.id).with_for_update()
        )
        return {p.id: p for p in await self.session.scalars(stmt)}

    async def release_stock(self, items: Iterable[OrderItem]) -> None:
        """Devolve ao estoque a quantidade dos itens (UPDATE atômico, sem ler antes).

        Atualiza em ordem de `product_id`, a mesma da reserva, para não gerar deadlock.
        """
        for item in sorted(items, key=lambda i: i.product_id):
            await self.session.execute(
                update(Product)
                .where(products.c.id == item.product_id)
                .values(stock=products.c.stock + item.quantity)
            )
