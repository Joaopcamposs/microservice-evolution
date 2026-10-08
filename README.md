# microservice-evolution

Demonstração didática de **evolução arquitetural**: uma API de vendas FastAPI começa síncrona e simples; conforme a carga cresce e a latência degrada, migramos por etapas para API + workers assíncronos (RabbitMQ, outbox) e, se a medição justificar, serviços em Go. Cada etapa é medida antes e depois.

Roteiro completo: [`PLANO.md`](PLANO.md). Regras de código e fluxo: [`AGENTS.md`](AGENTS.md).

## Estado atual

**Etapa 0 — não iniciada.** (Atualizar este bloco a cada etapa concluída.)

## Domínio

Sistema de vendas mínimo:

- **Produto:** `id`, `name`, `price_cents`, `stock`.
- **Venda:** `id`, `customer_email`, itens (`product_id`, `quantity`, `unit_price_cents`), `total_cents`, `status`.
- **Status:** `PENDING` → `PAID` → `COMPLETED`; falha de cobrança → `PAYMENT_FAILED`.
- **Integrações fake:** cobrança (latência e taxa de falha configuráveis) e envio de e-mail (apenas latência + log). Servem para simular trabalho lento sem depender de terceiros.

## Endpoints (etapa 0)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/products` | Cadastra produto |
| `GET` | `/products` | Lista produtos |
| `POST` | `/sales` | Registra venda: valida estoque, grava, cobra (fake), envia e-mail (fake) — tudo na request |
| `GET` | `/sales/{id}` | Consulta venda |
| `GET` | `/sales` | Lista vendas (filtro por `status`, `customer_email`; paginação) |
| `GET` | `/health` | Liveness |

Swagger em `/docs`. A partir da etapa 3, `POST /sales` passa a responder `202 Accepted` e o status é consultado em `GET /sales/{id}`.

## Arquitetura

```
Etapa 0                 Etapa 3+ (alvo)
┌────────┐              ┌─────┐   ┌────────┐   ┌────────┐   ┌──────────┐
│  API   │─ cobra ─┐    │ API │──▶│ outbox │──▶│ relay  │──▶│ RabbitMQ │
│FastAPI │─ email ─┤    └──┬──┘   └────────┘   └────────┘   └────┬─────┘
└───┬────┘         │       │ Postgres (sales+outbox, 1 tx)        ▼
    ▼              ▼       ▼                               ┌────────┐
 Postgres      (fakes, lentos)                             │ router │
                                                           └─┬────┬─┘
                                                      payment│    │email
                                                         worker   worker
```

## Estrutura planejada

```
api/                  FastAPI (routes / services / repositories)
  app/
  tests/
db/init.sql           schema comentado
contracts/            envelope.schema.json (etapa 3)
bench/                cenários de carga (locust/k6) e resultados
services/             relay, router, workers (etapas 3+)
docker-compose.yml
Makefile              run, test, ruff, ty, bench, up, down
```

## Como rodar

Preenchido na etapa 0 (`make up`, `make run`). Pré-requisitos: Python 3.13, `uv`, Docker.

## Stack

Python 3.13 · FastAPI · Pydantic · SQLAlchemy 2 async + asyncpg · PostgreSQL · pytest · ruff · ty. Adicionados por etapa: RabbitMQ, Redis, Prometheus/Grafana, locust ou k6, Go.
