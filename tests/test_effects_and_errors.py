"""Efeitos do pedido (cobrança e e-mail) e tradução dos erros de domínio, sem banco."""

from uuid import uuid4

import pytest
from starlette.requests import Request

from app.domain.errors import DomainError, InsufficientStock
from app.domain.order import Order
from app.domain.product import Product
from app.domain.schemas import OrderItemCreate
from app.domain.user import User
from app.routers.errors import DomainErrorHandler
from app.services.effects import OrderEffects
from app.services.fakes import FakeEmailSender, FakePaymentGateway

REQUEST = Request({"type": "http"})


def all_subclasses(cls: type[DomainError]) -> set[type[DomainError]]:
    """Todos os descendentes de `cls`, em qualquer nível."""
    return {sub for direct in cls.__subclasses__() for sub in {direct, *all_subclasses(direct)}}


def make_order() -> tuple[Order, User]:
    """Pedido de um item (R$ 10,00) e seu usuário."""
    product = Product.create("p", 1000, 5)
    order = Order.place(
        uuid4(), [OrderItemCreate(product_id=product.id, quantity=2)], {product.id: product}
    )
    return order, User.register("Ana", "ana@example.com", "senha-forte-1")


@pytest.mark.parametrize("failure_rate, notified", [(0.0, True), (1.0, False)])
async def test_notify_marks_only_when_email_is_sent(failure_rate: float, notified: bool) -> None:
    """`notified_at` só é preenchido se o e-mail saiu; a falha não levanta erro."""
    effects = OrderEffects(
        FakePaymentGateway(0, 0.0), FakeEmailSender(latency_ms=0, failure_rate=failure_rate)
    )
    order, user = make_order()
    await effects.notify(order, user)
    assert (order.history[-1].notified_at is not None) is notified


@pytest.mark.parametrize("failure_rate, approved", [(0.0, True), (1.0, False)])
async def test_charge_reports_gateway_result(failure_rate: float, approved: bool) -> None:
    """A cobrança devolve o veredito da integração."""
    effects = OrderEffects(
        FakePaymentGateway(latency_ms=0, failure_rate=failure_rate), FakeEmailSender(0, 0.0)
    )
    order, _ = make_order()
    assert await effects.charge(order) is approved


def test_every_domain_error_has_an_http_status() -> None:
    """Erro novo sem status mapeado viraria 500; este teste obriga a mapear."""
    assert all_subclasses(DomainError) == set(DomainErrorHandler.STATUS)


async def test_unmapped_domain_error_is_500() -> None:
    """Um `DomainError` fora da tabela responde 500, nunca vaza como exceção."""

    class Unmapped(DomainError):
        """Erro de teste sem status."""

    response = await DomainErrorHandler.handle(REQUEST, Unmapped("x"))
    assert response.status_code == 500


async def test_domain_error_message_goes_in_detail() -> None:
    """A resposta usa o `__str__` do erro no campo `detail`."""
    response = await DomainErrorHandler.handle(REQUEST, InsufficientStock([uuid4()]))
    assert response.status_code == 409
    assert b"estoque insuficiente" in bytes(response.body)
