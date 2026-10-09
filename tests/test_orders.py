"""Pedidos: total, preço congelado, validações, estoque, cobrança, e-mail e concorrência."""

import asyncio
from uuid import uuid4

import httpx

from app.services import fakes


async def _user(client: httpx.AsyncClient, email: str = "ana@mail.com") -> str:
    return (
        await client.post(
            "/users", json={"name": "Ana", "email": email, "password": "senha-forte-1"}
        )
    ).json()["id"]


async def _product(client: httpx.AsyncClient, price_cents: int, stock: int = 100) -> str:
    resp = await client.post(
        "/products", json={"name": "p", "price_cents": price_cents, "stock": stock}
    )
    return resp.json()["id"]


async def _stock(client: httpx.AsyncClient, product_id: str) -> int:
    return (await client.get("/products", params={"id": product_id})).json()[0]["stock"]


def _order(user: str, product: str, quantity: int = 1) -> dict:
    return {"user_id": user, "items": [{"product_id": product, "quantity": quantity}]}


async def test_order_total_and_frozen_price(client: httpx.AsyncClient):
    user, a, b = await _user(client), await _product(client, 1000), await _product(client, 250)
    resp = await client.post(
        "/orders",
        json={
            "user_id": user,
            "items": [{"product_id": a, "quantity": 2}, {"product_id": b, "quantity": 3}],
        },
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["total_cents"] == 2 * 1000 + 3 * 250
    assert {i["product_id"]: i["unit_price_cents"] for i in order["items"]} == {a: 1000, b: 250}
    assert (await client.get("/orders", params={"id": order["id"]})).json() == [order]


async def test_order_requires_existing_user_and_products(client: httpx.AsyncClient):
    user, product = await _user(client), await _product(client, 100)
    ghost_user = {"user_id": str(uuid4()), "items": [{"product_id": product, "quantity": 1}]}
    ghost_product = {"user_id": user, "items": [{"product_id": str(uuid4()), "quantity": 1}]}
    assert (await client.post("/orders", json=ghost_user)).status_code == 404
    assert (await client.post("/orders", json=ghost_product)).status_code == 404


async def test_order_rejects_empty_zero_and_repeated_items(client: httpx.AsyncClient):
    user, product = await _user(client), await _product(client, 100)
    item = {"product_id": product, "quantity": 1}
    for items in ([], [{"product_id": product, "quantity": 0}], [item, item]):
        resp = await client.post("/orders", json={"user_id": user, "items": items})
        assert resp.status_code == 422


async def test_list_orders_filters_by_user(client: httpx.AsyncClient):
    ana, bob = await _user(client), await _user(client, "bob@mail.com")
    product = await _product(client, 100)
    for buyer in (ana, bob, ana):
        await client.post(
            "/orders", json={"user_id": buyer, "items": [{"product_id": product, "quantity": 1}]}
        )
    assert len((await client.get("/orders", params={"user_id": ana})).json()) == 2
    assert len((await client.get("/orders", params={"limit": 1})).json()) == 1


def _history(order: dict) -> list[tuple[str, bool]]:
    """Lista (status, e-mail confirmado?) do histórico do pedido."""
    return [(h["status"], h["notified_at"] is not None) for h in order["history"]]


async def test_order_reserves_stock_and_is_paid(client: httpx.AsyncClient):
    user, product = await _user(client), await _product(client, 100, stock=5)
    resp = await client.post("/orders", json=_order(user, product, 2))
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "PAID"
    # E-mail em RECEIVED e no resultado; AWAITING_PAYMENT só registra.
    assert _history(order) == [("RECEIVED", True), ("AWAITING_PAYMENT", False), ("PAID", True)]
    assert await _stock(client, product) == 3


async def test_insufficient_stock_is_409_and_keeps_stock(client: httpx.AsyncClient):
    user = await _user(client)
    ok, scarce = await _product(client, 100, stock=10), await _product(client, 100, stock=1)
    items = [{"product_id": ok, "quantity": 2}, {"product_id": scarce, "quantity": 2}]
    resp = await client.post("/orders", json={"user_id": user, "items": items})
    assert resp.status_code == 409
    assert await _stock(client, ok) == 10 and await _stock(client, scarce) == 1
    assert (await client.get("/orders")).json() == []


async def test_refused_charge_fails_order_and_returns_stock(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(fakes, "CHARGE_FAILURE_RATE", 1.0)
    user, product = await _user(client), await _product(client, 100, stock=5)
    resp = await client.post("/orders", json=_order(user, product, 3))
    assert resp.status_code == 201
    assert resp.json()["status"] == "PAYMENT_FAILED"
    assert _history(resp.json())[-1] == ("PAYMENT_FAILED", True)
    assert await _stock(client, product) == 5


async def test_email_failure_does_not_block_order(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(fakes, "EMAIL_FAILURE_RATE", 1.0)
    user, product = await _user(client), await _product(client, 100, stock=5)
    order = (await client.post("/orders", json=_order(user, product))).json()
    assert order["status"] == "PAID"
    assert not any(notified for _, notified in _history(order))
    assert await _stock(client, product) == 4


async def test_concurrent_orders_for_last_item_only_one_wins(client: httpx.AsyncClient):
    user, product = await _user(client), await _product(client, 100, stock=1)
    results = await asyncio.gather(
        *(client.post("/orders", json=_order(user, product)) for _ in range(2))
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await _stock(client, product) == 0


async def test_concurrent_orders_never_oversell(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(fakes, "CHARGE_LATENCY_MS", 20)  # força as requests a se sobreporem
    user, product = await _user(client), await _product(client, 100, stock=5)
    results = await asyncio.gather(
        *(client.post("/orders", json=_order(user, product)) for _ in range(12))
    )
    codes = [r.status_code for r in results]
    assert codes.count(201) == 5 and codes.count(409) == 7
    assert await _stock(client, product) == 0
    assert len((await client.get("/orders", params={"limit": 100})).json()) == 5


async def test_concurrent_refused_orders_with_opposite_item_order_do_not_deadlock(
    client: httpx.AsyncClient, monkeypatch
):
    monkeypatch.setattr(fakes, "CHARGE_FAILURE_RATE", 1.0)
    user = await _user(client)
    a, b = await _product(client, 100, stock=50), await _product(client, 100, stock=50)
    forward = [{"product_id": a, "quantity": 1}, {"product_id": b, "quantity": 1}]
    results = await asyncio.gather(
        *(
            client.post("/orders", json={"user_id": user, "items": items})
            for items in [forward, forward[::-1]] * 15
        )
    )
    assert {r.status_code for r in results} == {201}
    assert await _stock(client, a) == 50 and await _stock(client, b) == 50


async def _paid_order(client: httpx.AsyncClient) -> str:
    user, product = await _user(client), await _product(client, 100, stock=5)
    return (await client.post("/orders", json=_order(user, product))).json()["id"]


def _patch(client: httpx.AsyncClient, order_id: str, status: str):
    return client.patch(f"/orders/{order_id}/status", params={"status": status})


async def test_operator_walks_order_to_completed_with_email_each_step(
    client: httpx.AsyncClient,
):
    order_id = await _paid_order(client)
    for status in ("AWAITING_SHIPMENT", "SHIPPED", "DELIVERED", "COMPLETED"):
        resp = await _patch(client, order_id, status)
        assert resp.status_code == 200
        assert resp.json()["status"] == status
    history = _history(resp.json())
    assert [s for s, _ in history] == [
        "RECEIVED", "AWAITING_PAYMENT", "PAID",
        "AWAITING_SHIPMENT", "SHIPPED", "DELIVERED", "COMPLETED",
    ]  # fmt: skip
    assert all(notified for status, notified in history if status != "AWAITING_PAYMENT")
    assert (await client.get("/orders", params={"id": order_id})).json() == [resp.json()]


async def test_invalid_transition_is_409_and_changes_nothing(client: httpx.AsyncClient):
    order_id = await _paid_order(client)
    for status in ("SHIPPED", "COMPLETED", "PAID", "RECEIVED"):
        assert (await _patch(client, order_id, status)).status_code == 409
    order = (await client.get("/orders", params={"id": order_id})).json()[0]
    assert order["status"] == "PAID" and len(order["history"]) == 3


async def test_failed_payment_order_is_final(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(fakes, "CHARGE_FAILURE_RATE", 1.0)
    user, product = await _user(client), await _product(client, 100)
    order = (await client.post("/orders", json=_order(user, product))).json()
    assert (await _patch(client, order["id"], "AWAITING_SHIPMENT")).status_code == 409


async def test_status_update_unknown_order_or_status(client: httpx.AsyncClient):
    assert (await _patch(client, str(uuid4()), "SHIPPED")).status_code == 404
    order_id = await _paid_order(client)
    assert (await _patch(client, order_id, "INEXISTENTE")).status_code == 422


async def test_status_update_email_failure_keeps_transition(client: httpx.AsyncClient, monkeypatch):
    order_id = await _paid_order(client)
    monkeypatch.setattr(fakes, "EMAIL_FAILURE_RATE", 1.0)
    order = (await _patch(client, order_id, "AWAITING_SHIPMENT")).json()
    assert order["status"] == "AWAITING_SHIPMENT"
    assert _history(order)[-1] == ("AWAITING_SHIPMENT", False)


async def test_concurrent_status_updates_only_one_wins(client: httpx.AsyncClient):
    order_id = await _paid_order(client)
    results = await asyncio.gather(
        *(_patch(client, order_id, "AWAITING_SHIPMENT") for _ in range(5))
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]
    order = (await client.get("/orders", params={"id": order_id})).json()[0]
    assert [h["status"] for h in order["history"]].count("AWAITING_SHIPMENT") == 1


async def test_payment_and_email_steps_are_logged(client: httpx.AsyncClient, caplog, monkeypatch):
    monkeypatch.setattr(fakes, "CHARGE_FAILURE_RATE", 1.0)
    user, product = await _user(client), await _product(client, 100)
    with caplog.at_level("INFO", logger="app"):
        order = (await client.post("/orders", json=_order(user, product))).json()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert f"cobrança recusada order_id={order['id']}" in text
    assert "estoque devolvido" in text
    assert f"e-mail enviado order_id={order['id']} status=PAYMENT_FAILED" in text
