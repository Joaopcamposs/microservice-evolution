"""Agregados de domínio: regras testadas sem banco nem HTTP."""

from uuid import UUID, uuid4

import pytest

from app.domain.errors import InsufficientStock, InvalidTransition, ProductsNotFound
from app.domain.order import Order
from app.domain.product import Product
from app.domain.schemas import OrderItemCreate
from app.domain.security import PasswordHasher
from app.domain.status import OrderStatus
from app.domain.user import User


def make_product(stock: int = 5, price_cents: int = 1000) -> Product:
    """Produto de teste."""
    return Product.create("p", price_cents, stock)


def item(product: Product, quantity: int) -> OrderItemCreate:
    """Item pedido de um produto."""
    return OrderItemCreate(product_id=product.id, quantity=quantity)


def by_id(*products: Product) -> dict[UUID, Product]:
    """Indexa produtos por id, como o repositório entrega ao agregado."""
    return {p.id: p for p in products}


def place_one() -> Order:
    """Pedido de teste com um item."""
    product = make_product()
    return Order.place(uuid4(), [item(product, 1)], by_id(product))


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
    order = Order.place(uuid4(), [item(a, 3), item(b, 2)], by_id(a, b))
    assert (a.stock, b.stock) == (2, 0)
    assert order.total_cents == 3 * 1000 + 2 * 250
    assert order.status is OrderStatus.RECEIVED
    assert [h.status for h in order.history] == [OrderStatus.RECEIVED]


def test_order_place_reports_all_short_products_without_reserving() -> None:
    """Faltando estoque em qualquer item, nada é reservado e todos os faltantes são listados."""
    ok, short1, short2 = make_product(stock=5), make_product(stock=1), make_product(stock=0)
    with pytest.raises(InsufficientStock) as exc:
        Order.place(
            uuid4(), [item(ok, 1), item(short1, 2), item(short2, 1)], by_id(ok, short1, short2)
        )
    assert exc.value.product_ids == [short1.id, short2.id]
    assert (ok.stock, short1.stock, short2.stock) == (5, 1, 0)


def test_order_move_to_validates_and_records_history() -> None:
    """Transição válida muda o estado e grava histórico; inválida levanta e não muda nada."""
    order = place_one()
    order.move_to(OrderStatus.AWAITING_PAYMENT)
    with pytest.raises(InvalidTransition):
        order.move_to(OrderStatus.COMPLETED)
    assert order.status is OrderStatus.AWAITING_PAYMENT
    assert [h.status for h in order.history] == [OrderStatus.RECEIVED, OrderStatus.AWAITING_PAYMENT]


def test_order_mark_notified_only_touches_last_entry() -> None:
    """O e-mail confirmado marca só a entrada do estado atual."""
    order = place_one()
    order.move_to(OrderStatus.AWAITING_PAYMENT)
    order.mark_notified()
    assert order.history[0].notified_at is None
    assert order.history[1].notified_at is not None


def test_order_place_rejects_unknown_products() -> None:
    """Item cujo produto não foi carregado levanta ProductsNotFound e não reserva nada."""
    known, ghost = make_product(), uuid4()
    with pytest.raises(ProductsNotFound) as exc:
        Order.place(
            uuid4(), [item(known, 1), OrderItemCreate(product_id=ghost, quantity=1)], by_id(known)
        )
    assert exc.value.product_ids == [ghost]
    assert known.stock == 5


def test_order_payment_flow_and_stock_release_flag() -> None:
    """Cobrança aprovada vai a PAID; recusada vai a PAYMENT_FAILED e pede devolução de estoque."""
    paid, failed = place_one(), place_one()
    for order, approved in ((paid, True), (failed, False)):
        order.begin_payment()
        order.settle_payment(approved)
    assert (paid.status, paid.releases_stock) == (OrderStatus.PAID, False)
    assert (failed.status, failed.releases_stock) == (OrderStatus.PAYMENT_FAILED, True)
