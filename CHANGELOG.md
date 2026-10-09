# Changelog

## Não lançado

- Planejamento inicial: `AGENTS.md`, `README.md` e `PLANO.md`.
- Etapa 0 (versão simples): cadastros e consultas de usuário, produto e pedido (FastAPI + SQLAlchemy async + Postgres, UUID v7). Testes com SQLite em memória.
- Usuário com senha (hash scrypt, nunca devolvida) e e-mail validado com `EmailStr`. Schema mudou: `make reset`.
- Carga (`make bench`, k6 no compose): cenário POST /orders + GET /orders?id=, 30 s por patamar. Baseline com 1 worker uvicorn, pool padrão do SQLAlchemy, Docker local (k6 e API na mesma máquina):

  | Usuários | req/s | p50 | p95 | p99 | erros |
  |---|---|---|---|---|---|
  | 50 | 568 | 31 ms | 317 ms | 524 ms | 0% |
  | 200 | 538 | 33 ms | 1,63 s | 2,66 s | 0% |
  | 500 | 391 | 48 ms | 5,4 s | 9,1 s | 0% |

  Vazão satura perto de 550 req/s e a latência de cauda cresce com a fila. Detalhes por endpoint em `bench/RESULTS.md`.
- Workers e pool configuráveis por env (`WEB_CONCURRENCY`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`); compose passa a usar 4 workers. Vazão de ~550 para ~1450 req/s (p95 com 500 usuários: 5,4 s → 1,3 s). Tabela completa em `bench/RESULTS.md`.
- Observabilidade: OpenTelemetry nativo do FastAPI (`fastapi[opentelemetry]`) + `opentelemetry-instrumentation-sqlalchemy` (suporta SQLAlchemy até 2.0) exportando para `grafana/otel-lgtm` no compose (Grafana em :3000). Custo medido: -22% a -40% de vazão (ver `bench/RESULTS.md`).
- Dashboard Grafana "Orders API" provisionado por arquivo (`observability/`): RED, por rota, etapas da requisição, banco/pool, traces lentos e logs.
- API com healthcheck no compose (o k6 espera a API ficar saudável).
- Testes passam de SQLite para Postgres real em compose separado (`docker-compose.test.yml`, porta 5433, tmpfs; `make test-db`), incluindo testes de concorrência. `aiosqlite` removido.
- Etapa 1 (fluxo síncrono): `stock` no produto, reserva com `SELECT ... FOR UPDATE` (409 sem estoque), `status` do pedido (`PENDING → PAID → COMPLETED` / `PAYMENT_FAILED`), cobrança e e-mail fakes dentro da request (latência/falha por env, spans OTel `charge` e `send_email`); recusa devolve estoque. Schema mudou: `make reset`.
- A versão com DDD/UoW/CQRS ficou na branch `major-complexo`.
- Status completos com máquina de estados (`app/domain/status.py`), histórico em `order_status_history` (`notified_at` mostra se o e-mail foi confirmado) e `PATCH /orders/{id}/status?status=...` (dropdown no Swagger) para a operação; e-mail a cada mudança. `POST /orders` termina em `PAID`/`PAYMENT_FAILED` (substitui `PENDING`/`COMPLETED`). Schema mudou: `make reset`.
- Header `X-Process-Time-Ms` em toda resposta (middleware ASGI em `app/infra/timing.py`).
- Logs de pedido criado, mudanças de status, cobrança, e-mail e devolução de estoque (`LOG_LEVEL`; stdout e Loki).
- Repositórios por entidade (`app/repository/{users,products,orders}.py`), `*Reader` (só leitura) e `*Writer` (escrita/locks) sobre `Repository`; sessões separadas de leitura (GET) e escrita (POST/PATCH), com `READ_DATABASE_URL` opcional. `repo.py` removido.
- Cobrança e e-mail como `PaymentGateway` e `EmailSender` (Protocol, `services/gateways.py`) com implementações `FakePaymentGateway`/`FakeEmailSender`, injetadas por `Depends`; os testes trocam as instâncias via `dependency_overrides` em vez de `monkeypatch`.
- Bench da Etapa 1 (OTel 100%): `POST /orders` ~0,8 s; 120 req/s com 50 usuários, ~450 req/s com 500 (p95 3,3 s). O bench revelou um deadlock na devolução de estoque (corrigido: updates em ordem de id). Detalhes em `bench/RESULTS.md`.
- `create_all` na subida protegido por lock consultivo do Postgres: vários workers num banco vazio disputavam a criação das tabelas.
- SQLAlchemy fixado em `>=2.0.40,<2.1` (era 2.1.4): o instrumentor OTel não suporta a 2.1, e o `skip_dep_check` que o contornava saiu.
