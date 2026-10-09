"""Repositórios de leitura (ORM): consultas para a API, sem passar pelo domínio.

Usam a `ReadSession` da request (banco de leitura) e devolvem modelos de saída
(`schemas`). Nunca escrevem.
"""

from uuid import UUID

from sqlalchemy import select

from app.domain.sale import SaleStatus
from app.infrastructure.db.models import ProductModel, SaleModel, UserModel
from app.infrastructure.db.sessions import BaseRepository, ReadSession
from app.schemas import ProductOut, SaleOut, UserOut


class UserReadRepository(BaseRepository[ReadSession]):
    """Consultas de usuários."""

    async def get(self, user_id: UUID) -> UserOut | None:
        """Busca um usuário por id."""
        model = await self._session.get(UserModel, user_id)
        return UserOut.model_validate(model) if model else None


class ProductReadRepository(BaseRepository[ReadSession]):
    """Consultas de produtos."""

    async def get(self, product_id: UUID) -> ProductOut | None:
        """Busca um produto por id."""
        model = await self._session.get(ProductModel, product_id)
        return ProductOut.model_validate(model) if model else None

    async def list_all(self) -> list[ProductOut]:
        """Lista todo o catálogo por id (pequeno; sem paginação)."""
        result = await self._session.scalars(select(ProductModel).order_by(ProductModel.id))
        return [ProductOut.model_validate(m) for m in result]


class SaleReadRepository(BaseRepository[ReadSession]):
    """Consultas de vendas."""

    async def get(self, sale_id: UUID) -> SaleOut | None:
        """Busca uma venda com itens por id."""
        model = await self._session.get(SaleModel, sale_id)
        return SaleOut.model_validate(model) if model else None

    async def search(
        self, status: SaleStatus | None, user_id: UUID | None, limit: int, offset: int
    ) -> list[SaleOut]:
        """Lista vendas, mais recentes primeiro, com filtros opcionais e paginação."""
        stmt = (
            select(SaleModel)
            .order_by(SaleModel.created_at.desc(), SaleModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(SaleModel.status == status)
        if user_id is not None:
            stmt = stmt.where(SaleModel.user_id == user_id)
        result = await self._session.scalars(stmt)
        return [SaleOut.model_validate(m) for m in result]
