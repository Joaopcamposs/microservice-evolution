"""Integração API + ORM + Postgres: rotas, locks, persistência e mapeamento de erros."""

from uuid import uuid4

import httpx


async def _user(client: httpx.AsyncClient, email: str = "ana@mail.com") -> str:
    resp = await client.post("/users", json={"name": "Ana", "email": email})
    return resp.json()["id"]


async def _product(client: httpx.AsyncClient, user_id: str, price: int, stock: int) -> str:
    resp = await client.post(
        "/products",
        json={"name": "p", "price_cents": price, "stock": stock},
        headers={"X-User-Id": user_id},
    )
    return resp.json()["id"]


async def _buy(
    client: httpx.AsyncClient, user_id: str, items: list[dict[str, object]]
) -> httpx.Response:
    return await client.post("/sales", json={"items": items}, headers={"X-User-Id": user_id})


async def test_sale_total_completion_and_ownership(client: httpx.AsyncClient):
    user = await _user(client)
    a = await _product(client, user, 1000, 10)
    b = await _product(client, user, 250, 10)
    resp = await _buy(
        client, user, [{"product_id": a, "quantity": 2}, {"product_id": b, "quantity": 3}]
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_cents"] == 2750
    assert body["status"] == "COMPLETED"
    assert body["user_id"] == user
    products = {p["id"]: p for p in (await client.get("/products")).json()}
    assert (products[a]["stock"], products[a]["created_by"]) == (8, user)
    assert products[b]["stock"] == 7


async def test_insufficient_stock_is_409_without_side_effects(client: httpx.AsyncClient):
    user = await _user(client)
    a = await _product(client, user, 1000, 1)
    resp = await _buy(client, user, [{"product_id": a, "quantity": 2}])
    assert resp.status_code == 409
    assert (await client.get("/sales")).json() == []
    assert (await client.get("/products")).json()[0]["stock"] == 1


async def test_payment_failure_restores_stock(failing_client: httpx.AsyncClient):
    user = await _user(failing_client)
    a = await _product(failing_client, user, 1000, 5)
    resp = await _buy(failing_client, user, [{"product_id": a, "quantity": 2}])
    assert resp.json()["status"] == "PAYMENT_FAILED"
    assert (await failing_client.get("/products")).json()[0]["stock"] == 5


async def test_list_filters_by_user_and_status(client: httpx.AsyncClient):
    ana = await _user(client)
    bob = await _user(client, "bob@mail.com")
    a = await _product(client, ana, 100, 10)
    for buyer in (ana, bob, ana):
        await _buy(client, buyer, [{"product_id": a, "quantity": 1}])
    assert len((await client.get("/sales", params={"user_id": ana})).json()) == 2
    assert (await client.get("/sales", params={"status": "PAYMENT_FAILED"})).json() == []
    assert len((await client.get("/sales", params={"limit": 1})).json()) == 1


async def test_unknown_user_and_duplicate_email(client: httpx.AsyncClient):
    assert (
        await _buy(client, str(uuid4()), [{"product_id": str(uuid4()), "quantity": 1}])
    ).status_code == 404
    await _user(client)
    dup = await client.post("/users", json={"name": "X", "email": "ana@mail.com"})
    assert dup.status_code == 409
