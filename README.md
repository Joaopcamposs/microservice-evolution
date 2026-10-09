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
observability/           dashboards Grafana (JSON) e provisionamento
bench/                  cenário de carga k6 (`orders.js`): POST /orders + GET /orders?id=
tests/           SQLite em memória (sem Docker)
```

## Observabilidade (OpenTelemetry + Grafana)

A API usa o OpenTelemetry nativo do FastAPI (traces, métricas e logs) mais o instrumentor do SQLAlchemy (um span por query). Tudo vai por OTLP/HTTP para o `grafana/otel-lgtm` (Grafana + Tempo + Prometheus + Loki num container), que sobe com `make up`.

- Grafana: http://localhost:3000 (admin/admin). Em **Explore**:
  - **Tempo** (traces): `{resource.service.name="orders-api"}`; um `POST /orders` mostra os spans da requisição, dependências, endpoint, queries e serialização.
  - **Prometheus** (métricas): `http_server_request_duration_seconds_bucket`, `http_server_active_requests`.
- **Dashboard "Orders API"** (pasta *Orders*, já provisionado a partir de `observability/dashboards/orders-api.json`): visão geral (req/s, % de 5xx, p50/p95/p99, requisições em andamento), vazão e latência por rota, tempo por etapa da requisição, banco (latência e volume de queries, uso do pool) e tabela de traces lentos + logs. Filtro por rota no topo. Editou no Grafana? Exporte o JSON e salve no arquivo, senão a próxima subida sobrescreve.
- Configuração por env no `docker-compose.yml`: `FASTAPI_OTEL_AUTO_CONFIGURE` (desliga com `false`), `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER_ARG` (fração de traces; padrão `1.0`).
- `/docs` (healthcheck do compose) fica fora da telemetria.
- Custo: ligado reduz a vazão em ~22–40% (ver `bench/RESULTS.md`). Para medir capacidade pura: `FASTAPI_OTEL_AUTO_CONFIGURE=false make bench`.

## Como rodar

Pré-requisitos: Python 3.13, `uv`, Docker.

```bash
uv sync
make up       # API + Postgres no Docker: http://localhost:8000/docs
make run      # alternativa: API local com reload (só o Postgres no Docker)
make test     # testes (sem Docker)
make ruff ty  # lint e tipos
make reset    # apaga o banco (schema mudou)
make bench    # carga com k6 (50/200/500 usuários); `make bench VUS=100 DURATION=60s` para customizar; resultados em `bench/RESULTS.md`
```

Banco configurável por `DATABASE_URL` (padrão: Postgres do compose).

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 async (ORM) + asyncpg · PostgreSQL · uuid-utils · pytest (SQLite em memória) · ruff · ty.
