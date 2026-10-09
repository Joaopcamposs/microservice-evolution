"""Casos de uso com UnitOfWork em memória: usuário, produto e fluxo completo de venda."""

from uuid import UUID, uuid4

import pytest

from app.domain.errors import (
    EmailAlreadyRegisteredError,
    InsufficientStockError,
    ProductNotFoundError,
    UserNotFoundError,
)
from app.domain.sale import SaleStatus
from app.schemas import ProductIn, SaleItemIn, UserIn
from app.services.products import ProductService
from app.services.sales import SaleService
from app.services.users import UserService
from tests.unit.fakes import InMemoryUnitOfWork, SpyEmail, Store, StubPayment


class World:
    """Monta serviços sobre um Store único, com usuário e produto já cadastrados."""

    def __init__(self, approved: bool = True) -> None:
        self.store = Store()
        self.payment = StubPayment(approved)
        self.email = SpyEmail()
        factory = lambda: InMemoryUnitOfWork(self.store)  # noqa: E731
        self.users = UserService(factory)
        self.products = ProductService(factory)
        self.sales = SaleService(factory, self.payment, self.email)

    async def seed(self, stock: int = 5) -> tuple[UUID, UUID]:
        user_id = await self.users.register_user(UserIn(name="Ana", email="ana@mail.com"))
        product_id = await self.products.create_product(
            user_id, ProductIn(name="Camiseta", price_cents=1000, stock=stock)
        )
        return user_id, product_id


async def test_duplicate_email_is_rejected():
    world = World()
    await world.seed()
    with pytest.raises(EmailAlreadyRegisteredError):
        await world.users.register_user(UserIn(name="Outra", email="ANA@mail.com"))


async def test_product_requires_existing_user():
    with pytest.raises(UserNotFoundError):
        await World().products.create_product(uuid4(), ProductIn(name="x", price_cents=1, stock=1))


async def test_sale_completes_charges_total_and_notifies_user():
    world = World()
    user_id, product_id = await world.seed(stock=5)
    sale_id = await world.sales.create_sale(
        user_id, [SaleItemIn(product_id=product_id, quantity=2)]
    )
    sale = world.store.sales[sale_id]
    assert sale.status is SaleStatus.COMPLETED
    assert sale.user_id == user_id
    assert world.payment.charges == [(sale_id, 2000)]
    assert world.email.sent == [(sale_id, "ana@mail.com")]
    assert world.store.products[product_id].stock == 3


async def test_declined_payment_restores_stock_and_skips_email():
    world = World(approved=False)
    user_id, product_id = await world.seed(stock=5)
    sale_id = await world.sales.create_sale(
        user_id, [SaleItemIn(product_id=product_id, quantity=2)]
    )
    assert world.store.sales[sale_id].status is SaleStatus.PAYMENT_FAILED
    assert world.store.products[product_id].stock == 5
    assert world.email.sent == []


async def test_insufficient_stock_rolls_back_and_never_charges():
    world = World()
    user_id, product_id = await world.seed(stock=1)
    with pytest.raises(InsufficientStockError):
        await world.sales.create_sale(user_id, [SaleItemIn(product_id=product_id, quantity=2)])
    assert world.store.sales == {}
    assert world.store.products[product_id].stock == 1
    assert world.payment.charges == []


async def test_sale_requires_existing_user_and_product():
    world = World()
    user_id, product_id = await world.seed()
    with pytest.raises(UserNotFoundError):
        await world.sales.create_sale(uuid4(), [SaleItemIn(product_id=product_id, quantity=1)])
    with pytest.raises(ProductNotFoundError):
        await world.sales.create_sale(user_id, [SaleItemIn(product_id=uuid4(), quantity=1)])
