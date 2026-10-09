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


async def test_order_reserves_stock_and_completes(client: httpx.AsyncClient):
    user, product = await _user(client), await _product(client, 100, stock=5)
    resp = await client.post("/orders", json=_order(user, product, 2))
    assert resp.status_code == 201
    assert resp.json()["status"] == "COMPLETED"
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
    assert await _stock(client, product) == 5


async def test_email_failure_keeps_order_paid(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(fakes, "EMAIL_FAILURE_RATE", 1.0)
    user, product = await _user(client), await _product(client, 100, stock=5)
    order = (await client.post("/orders", json=_order(user, product))).json()
    assert order["status"] == "PAID"
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
