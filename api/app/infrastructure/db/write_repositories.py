"""Repositórios de escrita (ORM): carregam e salvam agregados dentro de uma sessão."""

from uuid import UUID

from sqlalchemy import select

from app.domain.product import Product
from app.domain.sale import Sale
from app.domain.user import User
from app.infrastructure.db.models import ProductModel, SaleModel, UserModel
from app.infrastructure.db.sessions import BaseRepository, WriteSession


class SqlUserWriteRepository(BaseRepository[WriteSession]):
    """Persistência de `User` via ORM."""

    async def add(self, user: User) -> None:
        """Insere o usuário."""
        model = UserModel.from_domain(user)
        self._session.add(model)
        await self._session.flush()

    async def get(self, user_id: UUID) -> User | None:
        """Carrega por id."""
        model = await self._session.get(UserModel, user_id)
        return model.to_domain() if model else None

    async def get_by_email(self, email: str) -> User | None:
        """Carrega por e-mail."""
        model = await self._session.scalar(select(UserModel).where(UserModel.email == email))
        return model.to_domain() if model else None


class SqlProductWriteRepository(BaseRepository[WriteSession]):
    """Persistência de `Product` via ORM."""

    async def add(self, product: Product) -> None:
        """Insere o produto."""
        model = ProductModel.from_domain(product)
        self._session.add(model)
        await self._session.flush()

    async def get_many_for_update(self, product_ids: list[UUID]) -> list[Product]:
        """Carrega com `SELECT ... FOR UPDATE`, em ordem de id (evita deadlock entre vendas)."""
        result = await self._session.scalars(
            select(ProductModel)
            .where(ProductModel.id.in_(product_ids))
            .order_by(ProductModel.id)
            .with_for_update()
        )
        return [m.to_domain() for m in result]

    async def save(self, product: Product) -> None:
        """Copia o estoque do agregado para a linha (único campo mutável)."""
        model = await self._session.get_one(ProductModel, product.id)
        model.stock = product.stock


class SqlSaleWriteRepository(BaseRepository[WriteSession]):
    """Persistência de `Sale` via ORM."""

    async def add(self, sale: Sale) -> None:
        """Insere a venda com seus itens."""
        model = SaleModel.from_domain(sale)
        self._session.add(model)
        await self._session.flush()

    async def get(self, sale_id: UUID) -> Sale | None:
        """Carrega por id, com itens."""
        model = await self._session.get(SaleModel, sale_id)
        return model.to_domain() if model else None

    async def save(self, sale: Sale) -> None:
        """Copia o status do agregado para a linha (itens são imutáveis)."""
        model = await self._session.get_one(SaleModel, sale.id)
        model.status = sale.status
