"""Invariantes, total e transições de estado do agregado Sale."""

from uuid import UUID

import pytest

from app.domain.errors import InvalidSaleTransitionError, InvalidValueError
from app.domain.sale import Sale, SaleItem, SaleStatus

USER, P1, P2 = UUID(int=1), UUID(int=10), UUID(int=11)


def _sale() -> Sale:
    return Sale.place(USER, [SaleItem(P1, 2, 1000), SaleItem(P2, 3, 250)])


def test_place_computes_total_and_starts_pending():
    sale = _sale()
    assert sale.total_cents == 2 * 1000 + 3 * 250
    assert sale.status is SaleStatus.PENDING


@pytest.mark.parametrize(
    "items",
    [[], [SaleItem(P1, 0, 100)], [SaleItem(P1, 1, 100), SaleItem(P1, 2, 100)]],
    ids=["vazia", "quantidade-zero", "produto-repetido"],
)
def test_place_rejects_invalid_items(items: list[SaleItem]):
    with pytest.raises(InvalidValueError):
        Sale.place(USER, items)


def test_happy_path_transitions():
    sale = _sale()
    sale.mark_paid()
    sale.complete()
    assert sale.status is SaleStatus.COMPLETED


def test_payment_failed_is_terminal():
    sale = _sale()
    sale.mark_payment_failed()
    with pytest.raises(InvalidSaleTransitionError):
        sale.mark_paid()


def test_cannot_complete_without_paying():
    with pytest.raises(InvalidSaleTransitionError):
        _sale().complete()
