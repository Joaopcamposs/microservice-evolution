# microservice-evolution

Projeto de estudo de **evolução arquitetural**: uma API de pedidos FastAPI começa pequena e síncrona; conforme a necessidade (medida) aparece, evolui por etapas até API + workers assíncronos e, se valer a pena, serviços em Go. Roteiro em [`PLANO.md`](PLANO.md); regras de código em [`AGENTS.md`](AGENTS.md).

## Estado atual

**Etapa 0 — concluída:** cadastros de usuário, produto e pedido, com consulta.

**Etapa 1 — fluxo síncrono:** `POST /orders` reserva estoque, cobra e envia e-mail (fakes lentos) dentro da própria request. Sem fila nem worker; é o ponto de partida para medir a lentidão (Etapa 2). Sem autenticação.

## Domínio

- **Usuário:** `id`, `name`, `email` (único), `password` (só na entrada; guardada como hash scrypt, nunca devolvida), `created_at`.
- **Produto:** `id`, `name`, `price_cents`, `stock`, `created_at`.
- **Pedido:** `id`, `user_id`, itens (`product_id`, `quantity`, `unit_price_cents`), `status`, `history`, `total_cents` (calculado), `created_at`. O preço do item é copiado do produto na criação.
- **Status do pedido** (`app/domain/status.py`, com transições validadas): `RECEIVED → AWAITING_PAYMENT → PAID → AWAITING_SHIPMENT → SHIPPED → DELIVERED → COMPLETED`; desvio `AWAITING_PAYMENT → PAYMENT_FAILED`. `COMPLETED` e `PAYMENT_FAILED` são finais. Cada mudança grava uma linha em `order_status_history` (`status`, `created_at`, `notified_at`) e envia um e-mail; `notified_at` vazio = e-mail falhou, mas o pedido segue.
- **Fluxo em `POST /orders`:** reserva o estoque (linhas travadas com `FOR UPDATE`, ordenadas por id) → `RECEIVED` + e-mail → `AWAITING_PAYMENT` (sem e-mail: dura só a cobrança) → cobrança fake → `PAID` ou `PAYMENT_FAILED` (devolve o estoque) + e-mail. O resto do ciclo é manual, pela operação, em `PATCH /orders/{id}/status`. Cobrança e e-mail: `CHARGE_LATENCY_MS` (600), `CHARGE_FAILURE_RATE` (0.1), `EMAIL_LATENCY_MS` (200), `EMAIL_FAILURE_RATE` (0.05), latência com ±40% de variação; spans `charge` e `send_email`.
- Ids são UUID v7; dinheiro em centavos.
- **Agregados** (`app/domain`): `User.register`, `Product.create` (e-mail em minúsculas, senha em hash), `Order.place` (recebe o que o repositório carregou; reserva estoque, copia preço, `ProductsNotFound`/`InsufficientStock`), `begin_payment`/`settle_payment`, `Order.move_to` (`InvalidTransition`). Classes puras, mapeadas às tabelas por mapeamento imperativo (`app/repository/orm/mapping.py`); os handlers só orquestram: `OrderWriter.load_placement` busca tudo, o agregado decide, o handler grava e faz commit, e `OrderEffects` (cobrança, e-mail) roda depois.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/users` | Cadastra usuário (`409` se o e-mail já existe) |
| `GET` | `/users` | Consulta (`id` opcional; sem ele, lista) com paginação `limit`, `offset` |
| `POST` | `/products` | Cadastra produto (com `stock`, padrão 0) |
| `GET` | `/products` | Consulta (`id` opcional; sem ele, lista), igual a `/users` |
| `POST` | `/orders` | Cria pedido e roda o fluxo síncrono (estoque, cobrança, 2 e-mails), ~1 s (`404` se usuário ou produto não existe; `409` se faltar estoque; `422` se itens vazios, quantidade ≤ 0 ou produto repetido) |
| `PATCH` | `/orders/{id}/status` | Operação avança o pedido (`?status=SHIPPED`, dropdown no Swagger), com e-mail por mudança (`404` pedido inexistente; `409` transição inválida; `422` status desconhecido) |
| `GET` | `/orders` | Consulta (`id` opcional; sem ele, lista), filtro `user_id`, igual a `/users` |

Swagger em `/docs`. Toda resposta traz o header `X-Process-Time-Ms` (tempo de processamento da request, em ms).

## Estrutura

```
app/
  main.py               cria as tabelas na subida e registra os routers
  infra/database.py     engines e sessões de leitura/escrita
  domain/               agregados puros (User, Product, Order), status, erros, hash de senha
  repository/orm/       tabelas Core (tables.py) e mapeamento imperativo dos agregados (mapping.py)
  repository/           repositórios por entidade (users, products, orders): `*Reader` só lê, `*Writer` grava
  services/handlers.py  casos de uso (funções): busca, agregado decide, grava, commit, efeitos
  services/effects.py   efeitos do pedido (cobrança e e-mail), futuros eventos da UoW
  services/gateways.py  contratos (Protocol) de cobrança e e-mail, injetados nas rotas
  services/fakes.py     implementações fake (latência e falha por env)
  domain/schemas.py     entrada/saída (Pydantic)
  routers/              rotas HTTP (users, products, orders)
observability/           dashboards Grafana (JSON) e provisionamento
bench/                  cenário de carga k6 (`orders.js`): POST /orders + GET /orders?id=
tests/                  pytest contra Postgres de testes (docker-compose.test.yml, porta 5433)
```

## Observabilidade (OpenTelemetry + Grafana)

A API usa o OpenTelemetry nativo do FastAPI (traces, métricas e logs) mais o instrumentor do SQLAlchemy (um span por query). Tudo vai por OTLP/HTTP para o `grafana/otel-lgtm` (Grafana + Tempo + Prometheus + Loki num container), que sobe com `make up`.

- Grafana: http://localhost:3000 (admin/admin). Em **Explore**:
  - **Tempo** (traces): `{resource.service.name="orders-api"}`; um `POST /orders` mostra os spans da requisição, dependências, endpoint, queries e serialização.
  - **Prometheus** (métricas): `http_server_request_duration_seconds_bucket`, `http_server_active_requests`.
- **Dashboard "Orders API"** (pasta *Orders*, já provisionado a partir de `observability/dashboards/orders-api.json`): visão geral (req/s, % de 5xx, p50/p95/p99, requisições em andamento), vazão e latência por rota, tempo por etapa da requisição (inclui `charge` e `send_email`), banco (latência e volume de queries, uso do pool) e tabela de traces lentos + logs. Filtro por rota no topo. Editou no Grafana? Exporte o JSON e salve no arquivo, senão a próxima subida sobrescreve.
- Configuração por env no `docker-compose.yml`: `FASTAPI_OTEL_AUTO_CONFIGURE` (desliga com `false`), `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER_ARG` (fração de traces; padrão `1.0`).
- Logs da aplicação (pedido criado, mudança de status, cobrança, e-mail, estoque devolvido) saem no stdout (`docker compose logs api`) e no Loki; nível por `LOG_LEVEL` (padrão `INFO`). Falhas de cobrança e e-mail saem como `WARNING`.
- `/docs` (healthcheck do compose) fica fora da telemetria.
- Custo: ligado reduz a vazão em ~22–40% (ver `bench/RESULTS.md`). Para medir capacidade pura: `FASTAPI_OTEL_AUTO_CONFIGURE=false make bench`.

## Como rodar

Pré-requisitos: Python 3.13, `uv`, Docker.

```bash
uv sync
make up       # API + Postgres no Docker: http://localhost:8000/docs
make run      # alternativa: API local com reload (só o Postgres no Docker)
make test     # testes (sobe o Postgres de testes em docker-compose.test.yml); `make test T=tests/test_orders.py`
make ruff ty  # lint e tipos
make reset    # apaga o banco (schema mudou)
make bench    # carga com k6 (50/200/500 usuários); `make bench VUS=100 DURATION=60s` para customizar; resultados em `bench/RESULTS.md`
```

Banco configurável por `DATABASE_URL` (padrão: Postgres do compose). Leituras (`GET`) usam uma sessão própria; por padrão compartilha o engine/pool de escrita, e `READ_DATABASE_URL` aponta para outro banco (ex.: réplica de leitura, Etapa 6) com pool próprio.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 async (ORM) + asyncpg · PostgreSQL · uuid-utils · pytest (Postgres em compose separado) · ruff · ty.
