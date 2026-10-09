"""Agregados de domínio: regras testadas sem banco nem HTTP."""

from uuid import uuid4

import pytest

from app.domain.errors import InsufficientStock, InvalidTransition
from app.domain.order import Order
from app.domain.product import Product
from app.domain.security import PasswordHasher
from app.domain.status import OrderStatus
from app.domain.user import User


def make_product(stock: int = 5, price_cents: int = 1000) -> Product:
    """Produto de teste."""
    return Product.create("p", price_cents, stock)


def test_user_register_normalizes_and_hashes() -> None:
    """E-mail vira minúsculo, nome é aparado e a senha só existe como hash verificável."""
    user = User.register("  Ana ", "  Ana@Example.COM ", "senha-forte-1")
    assert (user.name, user.email) == ("Ana", "ana@example.com")
    assert user.password_hash != "senha-forte-1"
    assert PasswordHasher.verify("senha-forte-1", user.password_hash)


def test_product_create_normalizes_and_rejects_invalid() -> None:
    """Nome é aparado; preço não positivo e estoque negativo são recusados."""
    assert Product.create("  Caneta ", 300).name == "Caneta"
    with pytest.raises(ValueError):
        Product.create("p", 0)
    with pytest.raises(ValueError):
        Product.create("p", 100, stock=-1)


def test_order_place_reserves_stock_and_copies_price() -> None:
    """Montar o pedido tira do estoque, copia o preço e abre o histórico em RECEIVED."""
    a, b = make_product(stock=5, price_cents=1000), make_product(stock=2, price_cents=250)
    order = Order.place(uuid4(), [(a, 3), (b, 2)])
    assert (a.stock, b.stock) == (2, 0)
    assert order.total_cents == 3 * 1000 + 2 * 250
    assert order.status is OrderStatus.RECEIVED
    assert [h.status for h in order.history] == [OrderStatus.RECEIVED]


def test_order_place_reports_all_short_products_without_reserving() -> None:
    """Faltando estoque em qualquer item, nada é reservado e todos os faltantes são listados."""
    ok, short1, short2 = make_product(stock=5), make_product(stock=1), make_product(stock=0)
    with pytest.raises(InsufficientStock) as exc:
        Order.place(uuid4(), [(ok, 1), (short1, 2), (short2, 1)])
    assert exc.value.product_ids == [short1.id, short2.id]
    assert (ok.stock, short1.stock, short2.stock) == (5, 1, 0)


def test_order_move_to_validates_and_records_history() -> None:
    """Transição válida muda o estado e grava histórico; inválida levanta e não muda nada."""
    order = Order.place(uuid4(), [(make_product(), 1)])
    order.move_to(OrderStatus.AWAITING_PAYMENT)
    with pytest.raises(InvalidTransition):
        order.move_to(OrderStatus.COMPLETED)
    assert order.status is OrderStatus.AWAITING_PAYMENT
    assert [h.status for h in order.history] == [OrderStatus.RECEIVED, OrderStatus.AWAITING_PAYMENT]


def test_order_mark_notified_only_touches_last_entry() -> None:
    """O e-mail confirmado marca só a entrada do estado atual."""
    order = Order.place(uuid4(), [(make_product(), 1)])
    order.move_to(OrderStatus.AWAITING_PAYMENT)
    order.mark_notified()
    assert order.history[0].notified_at is None
    assert order.history[1].notified_at is not None
