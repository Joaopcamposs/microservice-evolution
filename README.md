# microservice-evolution

Projeto de estudo de **evolução arquitetural**: uma API de pedidos FastAPI começa pequena e síncrona; conforme a necessidade (medida) aparece, evolui por etapas até API + workers assíncronos e, se valer a pena, serviços em Go. Roteiro em [`PLANO.md`](PLANO.md); regras de código em [`AGENTS.md`](AGENTS.md).

## Estado atual

**Etapa 0 — concluída:** cadastros de usuário, produto e pedido, com consulta. Sem estoque, cobrança, e-mail, autenticação ou status.

## Domínio

- **Usuário:** `id`, `name`, `email` (único), `password` (só na entrada; guardada como hash scrypt, nunca devolvida), `created_at`.
- **Produto:** `id`, `name`, `price_cents`, `created_at`.
- **Pedido:** `id`, `user_id`, itens (`product_id`, `quantity`, `unit_price_cents`), `total_cents` (calculado), `created_at`. O preço do item é copiado do produto na criação.
- Ids são UUID v7; dinheiro em centavos.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/users` | Cadastra usuário (`409` se o e-mail já existe) |
| `GET` | `/users` | Consulta (`id` opcional; sem ele, lista) com paginação `limit`, `offset` |
| `POST` | `/products` | Cadastra produto |
| `GET` | `/products` | Consulta (`id` opcional; sem ele, lista), igual a `/users` |
| `POST` | `/orders` | Cria pedido (`404` se usuário ou produto não existe; `422` se itens vazios, quantidade ≤ 0 ou produto repetido) |
| `GET` | `/orders` | Consulta (`id` opcional; sem ele, lista), filtro `user_id`, igual a `/users` |

Swagger em `/docs`.

## Estrutura

```
app/
  main.py               cria as tabelas na subida e registra os routers
  infra/database.py     engine, sessão por request, Base
  repository/orm/       tabelas ORM (models.py)
  repository/repo.py    consultas (só leitura)
  services/handlers.py  cadastros: regras de criação e commit
  domain/schemas.py     entrada/saída (Pydantic)
  routers/              rotas HTTP (users, products, orders)
tests/           SQLite em memória (sem Docker)
```

## Como rodar

Pré-requisitos: Python 3.13, `uv`, Docker.

```bash
uv sync
make up       # API + Postgres no Docker: http://localhost:8000/docs
make run      # alternativa: API local com reload (só o Postgres no Docker)
make test     # testes (sem Docker)
make ruff ty  # lint e tipos
make reset    # apaga o banco (schema mudou)
```

Banco configurável por `DATABASE_URL` (padrão: Postgres do compose).

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 async (ORM) + asyncpg · PostgreSQL · uuid-utils · pytest (SQLite em memória) · ruff · ty.
