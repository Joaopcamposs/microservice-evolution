"""Máquina de estados do pedido: transições permitidas e estados finais."""

from app.domain.status import OrderStatus


def test_happy_path_is_linear():
    path = ["RECEIVED", "AWAITING_PAYMENT", "PAID", "AWAITING_SHIPMENT", "SHIPPED", "DELIVERED"]
    for current, nxt in zip(path, path[1:] + ["COMPLETED"], strict=True):
        assert OrderStatus(current).can_transition_to(OrderStatus(nxt))


def test_payment_can_fail_only_from_awaiting_payment():
    assert OrderStatus.AWAITING_PAYMENT.can_transition_to(OrderStatus.PAYMENT_FAILED)
    assert not OrderStatus.PAID.can_transition_to(OrderStatus.PAYMENT_FAILED)


def test_final_states_and_no_skipping_or_going_back():
    assert not OrderStatus.COMPLETED.next_states
    assert not OrderStatus.PAYMENT_FAILED.next_states
    assert not OrderStatus.PAID.can_transition_to(OrderStatus.SHIPPED)
    assert not OrderStatus.SHIPPED.can_transition_to(OrderStatus.PAID)
    assert not OrderStatus.PAID.can_transition_to(OrderStatus.PAID)
