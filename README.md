# microservice-evolution

Demonstração didática de **evolução arquitetural**: uma API de vendas FastAPI começa síncrona e simples; conforme a carga cresce e a latência degrada, migramos por etapas para API + workers assíncronos (RabbitMQ, outbox) e, se a medição justificar, serviços em Go. Cada etapa é medida antes e depois.

Roteiro completo: [`PLANO.md`](PLANO.md). Como a arquitetura funciona e por quê: [`ARCHITECTURE.md`](ARCHITECTURE.md). Passo a passo para rodar e estudar: [`TUTORIAL.md`](TUTORIAL.md). Regras de código e fluxo: [`AGENTS.md`](AGENTS.md).

## Estado atual

**Etapa 0 — concluída** (API síncrona; próxima: etapa 1, carga e medição). (Atualizar este bloco a cada etapa concluída.)

## Domínio

Sistema de vendas mínimo:

- **Ids:** todos os `id` são UUID v7 (ordenável por tempo), gerados no domínio ao criar o objeto, não pelo banco.
- **Usuário:** `id`, `name`, `email` (único). É o comprador das vendas e o autor dos produtos.
- **Produto:** `id`, `name`, `price_cents`, `stock`, `created_by` (usuário).
- **Venda:** `id`, `user_id` (comprador), itens (`product_id`, `quantity`, `unit_price_cents`), `total_cents`, `status`.
- **Status:** `PENDING` → `PAID` → `COMPLETED`; falha de cobrança → `PAYMENT_FAILED`.
- **Integrações fake:** cobrança (latência e taxa de falha configuráveis) e envio de e-mail (apenas latência + log). Servem para simular trabalho lento sem depender de terceiros.

## Endpoints (etapa 0)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/users` | Cadastra usuário (e-mail único) |
| `GET` | `/users/{id}` | Consulta usuário |
| `POST` | `/products` | Cadastra produto (header `X-User-Id`) |
| `GET` | `/products` | Lista produtos |
| `POST` | `/sales` | Registra venda do usuário `X-User-Id`: valida estoque, grava, cobra (fake), envia e-mail (fake) — tudo na request |
| `GET` | `/sales/{id}` | Consulta venda |
| `GET` | `/sales` | Lista vendas (filtro por `status`, `user_id`; paginação) |
| `GET` | `/health` | Liveness |

Swagger em `/docs`. O usuário que age vem do header `X-User-Id` (sem autenticação; demo). A partir da etapa 3, `POST /sales` passa a responder `202 Accepted` e o status é consultado em `GET /sales/{id}`.

## Arquitetura

DDD com agregados puros (`domain/`, sem SQLAlchemy). Escrita e leitura separadas: serviços de escrita carregam/salvam agregados por repositórios de escrita e `UnitOfWork`; consultas da API usam repositórios de leitura (ORM `select`) que devolvem os modelos de saída. Sessões separadas: `WriteSession` (transacional, via `UnitOfWork`) e `ReadSession` (AUTOCOMMIT, por request), cada uma com sua engine — `DATABASE_READ_URL` (opcional, padrão = `DATABASE_URL`) permite apontar leituras para uma réplica na etapa 5; todos os repositórios herdam de `BaseRepository`. Persistência só via ORM SQLAlchemy 2.0; tabelas criadas por `create_all` (sem Alembic: projeto de estudo; schema mudou, `make reset`).

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
api/
  app/
    domain/           agregados puros (User, Product, Sale), erros, contratos dos repositórios de escrita
    services/         casos de uso de escrita (orquestram agregados via UnitOfWork)
    infrastructure/db/  Base ORM, modelos, repositórios de escrita e leitura, UnitOfWork, create_tables
    integrations/     cobrança e e-mail fake
    routes/           HTTP (leitura -> repo de leitura; escrita -> serviço)
  tests/unit          sem banco (agregados e serviços com UoW em memória)
  tests/integration   Postgres real (ORM, locks, rotas)
contracts/            envelope.schema.json (etapa 3)
bench/                cenários de carga (locust/k6) e resultados
services/             relay, router, workers (etapas 3+)
docker-compose.yml
Makefile              run, test, ruff, ty, bench, up, down
```

## Como rodar

Pré-requisitos: Python 3.13, `uv`, Docker.

```bash
make up      # Postgres (tabelas criadas pela API na subida)
make run     # API em http://localhost:8000  (Swagger em /docs)
make test-unit # testes unitários (sem banco)
make test    # todos; integração usa o banco isolado sales_test
make ruff ty # lint e tipos
make reset   # apaga o volume do banco (a API recria as tabelas na subida)
```

`POST /sales` leva ~0,4–1,1 s por causa das integrações fake. Configuração por env: `DATABASE_URL`, `DATABASE_READ_URL`, `PAYMENT_LATENCY_MIN_MS`/`MAX_MS`, `PAYMENT_FAILURE_RATE`, `EMAIL_LATENCY_MIN_MS`/`MAX_MS`.

Regras da etapa 0: usuário inexistente → `404`; venda com cobrança recusada fica `PAYMENT_FAILED` (resposta `201`) e o estoque é devolvido; estoque insuficiente ou e-mail repetido → `409`; dado inválido (ex.: produto repetido nos itens) → `422`; produto inexistente → `404`.

## Stack

Python 3.13 · uuid-utils (UUID v7) · FastAPI · Pydantic · SQLAlchemy 2.0 async (ORM) + asyncpg · PostgreSQL · pytest · ruff · ty. Adicionados por etapa: RabbitMQ, Redis, Prometheus/Grafana, locust ou k6, Go.
