"""Cadastro e consulta de usuários e produtos."""

from uuid import uuid4

import httpx

from app.infra.database import get_read_session, get_write_session
from app.main import app
from app.services.security import hash_password, verify_password

PWD = "senha-forte-1"


async def test_create_and_get_user(client: httpx.AsyncClient):
    resp = await client.post(
        "/users", json={"name": "Ana", "email": "Ana@Mail.com", "password": PWD}
    )
    assert resp.status_code == 201
    user = resp.json()
    assert user["email"] == "ana@mail.com"
    assert "password" not in user and "password_hash" not in user
    other = (
        await client.post("/users", json={"name": "Bia", "email": "bia@mail.com", "password": PWD})
    ).json()
    assert (await client.get("/users", params={"id": user["id"]})).json() == [user]
    assert (await client.get("/users")).json() == [other, user]
    assert (await client.get("/users", params={"limit": 1, "offset": 1})).json() == [user]


async def test_duplicate_email_is_409(client: httpx.AsyncClient):
    await client.post("/users", json={"name": "Ana", "email": "ana@mail.com", "password": PWD})
    resp = await client.post(
        "/users", json={"name": "Outra", "email": "ANA@mail.com", "password": PWD}
    )
    assert resp.status_code == 409


async def test_invalid_user_is_422(client: httpx.AsyncClient):
    bad = [
        {"name": "Ana", "email": "x", "password": PWD},
        {"name": "Ana", "email": "ana@mail.com", "password": "curta"},
        {"name": "Ana", "email": "ana@mail.com"},
    ]
    for body in bad:
        assert (await client.post("/users", json=body)).status_code == 422


async def test_create_and_get_product(client: httpx.AsyncClient):
    resp = await client.post(
        "/products", json={"name": "Camiseta", "price_cents": 4990, "stock": 7}
    )
    assert resp.status_code == 201
    product = resp.json()
    assert product["stock"] == 7
    assert (await client.get("/products", params={"id": product["id"]})).json() == [product]
    assert (await client.get("/products")).json() == [product]


async def test_product_price_must_be_positive(client: httpx.AsyncClient):
    resp = await client.post("/products", json={"name": "x", "price_cents": 0})
    assert resp.status_code == 422


async def test_unknown_id_returns_empty_list(client: httpx.AsyncClient):
    assert (await client.get("/users", params={"id": str(uuid4())})).json() == []
    assert (await client.get("/products", params={"id": str(uuid4())})).json() == []


def test_password_hash_verifies():
    stored = hash_password(PWD)
    assert PWD not in stored
    assert verify_password(PWD, stored)
    assert not verify_password("outra-senha-1", stored)


async def test_response_has_process_time_header(client: httpx.AsyncClient):
    resp = await client.get("/users")
    assert float(resp.headers["X-Process-Time-Ms"]) >= 0


async def test_reads_use_read_session_and_writes_use_write_session(client: httpx.AsyncClient):
    used: list[str] = []
    for label, dep in (("read", get_read_session), ("write", get_write_session)):
        original = app.dependency_overrides[dep]

        async def tracked(original=original, label=label):
            used.append(label)
            async for session in original():
                yield session

        app.dependency_overrides[dep] = tracked

    await client.post("/products", json={"name": "x", "price_cents": 1})
    await client.get("/products")
    await client.get("/users")
    assert used == ["write", "read", "read"]
