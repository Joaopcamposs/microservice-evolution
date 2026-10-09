"""Invariantes dos agregados User e Product."""

from uuid import UUID

import pytest

from app.domain.errors import InsufficientStockError, InvalidValueError
from app.domain.product import Product
from app.domain.user import User

OWNER = UUID(int=1)


def test_user_register_normalizes_and_validates():
    user = User.register("  Ana ", "Ana@Mail.COM")
    assert (user.name, user.email) == ("Ana", "ana@mail.com")


@pytest.mark.parametrize(("name", "email"), [("", "a@b.com"), ("Ana", "sem-arroba")])
def test_user_register_rejects_invalid(name: str, email: str):
    with pytest.raises(InvalidValueError):
        User.register(name, email)


@pytest.mark.parametrize(("price", "stock"), [(0, 1), (-5, 1), (100, -1)])
def test_product_create_rejects_invalid(price: int, stock: int):
    with pytest.raises(InvalidValueError):
        Product.create("x", price, stock, created_by=OWNER)


def test_product_reserve_and_restore():
    product = Product.create("x", 100, 5, created_by=OWNER)
    product.reserve(3)
    assert product.stock == 2
    product.restore(3)
    assert product.stock == 5


def test_product_reserve_beyond_stock_changes_nothing():
    product = Product.create("x", 100, 2, created_by=OWNER)
    with pytest.raises(InsufficientStockError):
        product.reserve(3)
    assert product.stock == 2
