"""Dublês em memória: UnitOfWork com rollback por snapshot, pagamento e e-mail controláveis."""

import copy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domain.product import Product
from app.domain.sale import Sale
from app.domain.user import User


@dataclass(slots=True)
class Store:
    """Estado compartilhado entre unidades de trabalho (equivale ao banco)."""

    users: dict[UUID, User] = field(default_factory=dict)
    products: dict[UUID, Product] = field(default_factory=dict)
    sales: dict[UUID, Sale] = field(default_factory=dict)


class InMemoryUsers:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def add(self, user: User) -> None:
        self._store.users[user.id] = copy.deepcopy(user)

    async def get(self, user_id: UUID) -> User | None:
        return copy.deepcopy(self._store.users.get(user_id))

    async def get_by_email(self, email: str) -> User | None:
        return next(
            (copy.deepcopy(u) for u in self._store.users.values() if u.email == email), None
        )


class InMemoryProducts:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def add(self, product: Product) -> None:
        self._store.products[product.id] = copy.deepcopy(product)

    async def get_many_for_update(self, product_ids: list[UUID]) -> list[Product]:
        return [
            copy.deepcopy(self._store.products[i])
            for i in sorted(product_ids)
            if i in self._store.products
        ]

    async def save(self, product: Product) -> None:
        self._store.products[product.id] = copy.deepcopy(product)


class InMemorySales:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def add(self, sale: Sale) -> None:
        self._store.sales[sale.id] = copy.deepcopy(sale)

    async def get(self, sale_id: UUID) -> Sale | None:
        return copy.deepcopy(self._store.sales.get(sale_id))

    async def save(self, sale: Sale) -> None:
        self._store.sales[sale.id] = copy.deepcopy(sale)


class InMemoryUnitOfWork:
    """UoW que restaura o `Store` ao estado inicial se o bloco levantar exceção."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._snapshot: Store | None = None
        self.users = InMemoryUsers(store)
        self.products = InMemoryProducts(store)
        self.sales = InMemorySales(store)

    async def __aenter__(self) -> Self:
        self._snapshot = copy.deepcopy(self._store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None and self._snapshot is not None:
            self._store.users = self._snapshot.users
            self._store.products = self._snapshot.products
            self._store.sales = self._snapshot.sales


class StubPayment:
    """Cobrança com resultado fixo; guarda as cobranças recebidas."""

    def __init__(self, approved: bool) -> None:
        self._approved = approved
        self.charges: list[tuple[UUID, int]] = []

    async def charge(self, sale_id: UUID, amount_cents: int) -> bool:
        self.charges.append((sale_id, amount_cents))
        return self._approved


class SpyEmail:
    """E-mail que só registra os envios."""

    def __init__(self) -> None:
        self.sent: list[tuple[UUID, str]] = []

    async def send_confirmation(self, sale_id: UUID, to: str) -> None:
        self.sent.append((sale_id, to))
