"""Criação e consulta de pedidos: total, preço congelado, validações e filtro."""

from uuid import uuid4

import httpx


async def _user(client: httpx.AsyncClient, email: str = "ana@mail.com") -> str:
    return (
        await client.post(
            "/users", json={"name": "Ana", "email": email, "password": "senha-forte-1"}
        )
    ).json()["id"]


async def _product(client: httpx.AsyncClient, price_cents: int) -> str:
    return (await client.post("/products", json={"name": "p", "price_cents": price_cents})).json()[
        "id"
    ]


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
