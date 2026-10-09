"""Contratos dos repositórios de *escrita* e da unidade de trabalho.

Repositórios de escrita carregam e salvam agregados. Leitura (consultas para a API)
não passa por aqui: usa repositórios de leitura da infraestrutura.
"""

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from app.domain.product import Product
from app.domain.sale import Sale
from app.domain.user import User


class UserWriteRepository(Protocol):
    """Persistência do agregado `User`."""

    async def add(self, user: User) -> None:
        """Persiste um usuário novo."""
        ...

    async def get(self, user_id: UUID) -> User | None:
        """Carrega um usuário; `None` se não existir."""
        ...

    async def get_by_email(self, email: str) -> User | None:
        """Carrega um usuário pelo e-mail; `None` se não existir."""
        ...


class ProductWriteRepository(Protocol):
    """Persistência do agregado `Product`."""

    async def add(self, product: Product) -> None:
        """Persiste um produto novo."""
        ...

    async def get_many_for_update(self, product_ids: list[UUID]) -> list[Product]:
        """Carrega produtos travando-os até o fim da transação (evita venda dupla de estoque)."""
        ...

    async def save(self, product: Product) -> None:
        """Grava o estado atual de um produto já persistido."""
        ...


class SaleWriteRepository(Protocol):
    """Persistência do agregado `Sale`."""

    async def add(self, sale: Sale) -> None:
        """Persiste uma venda nova com seus itens."""
        ...

    async def get(self, sale_id: UUID) -> Sale | None:
        """Carrega uma venda com itens; `None` se não existir."""
        ...

    async def save(self, sale: Sale) -> None:
        """Grava o estado atual (status) de uma venda já persistida."""
        ...


class UnitOfWork(Protocol):
    """Transação que agrupa os repositórios: commit ao sair sem erro, rollback com erro."""

    @property
    def users(self) -> UserWriteRepository:
        """Repositório de usuários da transação corrente."""
        ...

    @property
    def products(self) -> ProductWriteRepository:
        """Repositório de produtos da transação corrente."""
        ...

    @property
    def sales(self) -> SaleWriteRepository:
        """Repositório de vendas da transação corrente."""
        ...

    async def __aenter__(self) -> Self:
        """Abre a transação."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Faz commit se não houve exceção; rollback caso contrário."""
        ...
