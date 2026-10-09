# Changelog

## Não lançado

- Etapa 2 fechada de vez: diagnóstico de saturação com 500 usuários (CPU dos workers da API, ~80% cada; Postgres folgado) em `bench/RESULTS.md` e `PLANO.md`; dashboard Grafana conferido; sem meta fixa de latência; logs estruturados adiados para a Etapa 4.
- Etapa 3 (partes 1–2): `create_order` cortado em `register_order` (rápido) e `settle_order` (lento, idempotente: lock da linha, só `RECEIVED` é liquidado). Cobrança fake idempotente por `order_id`. Contrato da API inalterado. Testes: fase rápida sem cobrança, liquidação concorrente cobra uma vez, id inexistente, dedupe do gateway.
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
- Agregados de domínio (`User`, `Product` via `Product.create`, `Order` em `app/domain/`), puros e testados sem banco; regras saem dos handlers (`User.register`, `Order.place`, `Order.move_to`, erros `DomainError`). Persistência por mapeamento imperativo: `models.py` (declarativo) vira `tables.py` (Core) + `mapping.py`; `Base` removida, `create_all` usa `metadata`. `PasswordHasher` movido para `app/domain/security.py`. Sem mudança de schema além de `created_at` agora gerado na aplicação (sem `server_default`): `make reset`.
- `create_order` enxuto: `OrderWriter.load_placement` busca usuário e produtos (travados), `Order.place` decide (`ProductsNotFound`, `InsufficientStock`), handler grava e faz commit. Cobrança e e-mail saem para `OrderEffects` (`app/services/effects.py`, injetado por `EffectsDep`), preparando a virada em eventos. `Order.begin_payment`, `settle_payment` e `releases_stock` substituem a lógica de estados no handler.
- Handlers sem HTTP: `UserNotFound`, `OrderNotFound`, `EmailAlreadyExists` (+ os erros dos agregados) viram 404/409 num único `exception_handler` (`app/routers/errors.py`). `OrderWriter.load_for_update` devolve `(pedido, usuário)` travado, no molde de `load_placement`.
- Bench após as refatorações de domínio: duas rodadas, 93–94/304–305/314–354 req/s com 50/200/500 usuários, 0% de erro (antes 92/295/378). Empate; a diferença com 500 usuários está dentro da variação entre rodadas. Detalhes em `bench/RESULTS.md`.
- Testes de `OrderEffects` e da tabela de erros HTTP (todo `DomainError` precisa de status mapeado). `PLANO.md` (Etapa 3) descreve o corte `register_order`/`settle_order` sobre o código atual.
- Etapa 2 fechada no `PLANO.md`: conclusão escrita (gargalo = cobrança + e-mails síncronos, ~1,0 s do `POST /orders`), índices em `status`/`created_at` descartados por falta de consulta que os use, texto de spans/logs corrigido.
