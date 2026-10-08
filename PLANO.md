# Plano de evolução

Princípio: **só migra quando a medição mostra o gargalo.** Cada etapa tem objetivo, entrega, critério de pronto e o que ela deliberadamente *não* faz. Uma etapa por vez; marcar `[x]` ao concluir.

Cenário de carga padrão (`bench/`): N usuários concorrentes fazendo `POST /sales` (1–3 itens) + `GET /sales/{id}`. Métricas: throughput (req/s), p50/p95/p99, taxa de erro, tempo até venda `COMPLETED`.

---

## [ ] Etapa 0 — Monólito síncrono

**Objetivo:** API funcional, simples e correta.
**Entrega:**
- Projeto `uv` + FastAPI, `docker-compose` com Postgres, `db/init.sql`, `Makefile` (`run`, `test`, `ruff`, `ty`).
- Produtos e vendas (endpoints do README), estoque decrementado na transação.
- `PaymentGateway` e `EmailSender` fakes (`Protocol` + implementação), latência (ex.: 300–800 ms / 100–300 ms) e taxa de falha (ex.: 10 %) via env.
- `POST /sales` faz tudo na request: valida → grava `PENDING` → cobra → `PAID` ou `PAYMENT_FAILED` → e-mail → `COMPLETED`.
- Testes: total correto, estoque insuficiente, falha de cobrança, listagem filtrada.

**Pronto quando:** fluxo exercitado via `/docs`, `make ruff` e `make ty` limpos, testes passando.
**Não faz:** fila, cache, autenticação.

## [ ] Etapa 1 — Carga, medição e observabilidade

**Objetivo:** provar o problema com números.
**Entrega:**
- `bench/` (locust ou k6) com o cenário padrão; `make bench`.
- Logs estruturados com `sale_id`; métrica de latência por etapa (cobrança, e-mail, banco) — endpoint `/metrics` Prometheus opcional.
- Baseline registrado em `CHANGELOG.md`: com 50/200/500 usuários, onde p95 explode e por quê (workers uvicorn ocupados esperando fakes).
- Ajustes baratos *antes* de arquitetura: pool de conexões, índices (`status`, `customer_email`, `created_at`), mais processos uvicorn. Medir de novo.

**Pronto quando:** existe tabela baseline vs. ajustes baratos e conclusão escrita de que o gargalo é I/O externo síncrono.
**Não faz:** mudança de arquitetura.

## [ ] Etapa 2 — Desacoplar na mesma base de código (modular)

**Objetivo:** preparar o corte sem introduzir infraestrutura.
**Entrega:**
- Separar fluxo em passos explícitos no `SaleService`: `register_sale` (rápido, transacional) vs. `settle_sale` (cobrança + e-mail, lento).
- Estados persistidos entre os passos; `settle_sale` idempotente (chamável 2× sem cobrar 2×; chave de idempotência na cobrança).
- Experimento: `settle_sale` via `BackgroundTasks`. Medir: latência cai, mas vendas ficam presas em `PENDING` se o processo morrer — documentar a falha como motivação da etapa 3.

**Pronto quando:** `POST /sales` rápido, falha demonstrada (matar processo no meio) e registrada.
**Não faz:** broker.

## [ ] Etapa 3 — Fila + outbox + worker (API + workers async)

**Objetivo:** durabilidade e escala horizontal do trabalho lento.
**Entrega:**
- RabbitMQ no compose.
- Tabela `outbox`; `POST /sales` grava `sales` + `outbox` na mesma transação e responde `202`.
- Serviço `relay`: lê outbox (`FOR UPDATE SKIP LOCKED`), publica, marca enviado.
- `contracts/envelope.schema.json` (`job_id`, `sale_id`, `type`, `payload`, `created_at`, `attempt`).
- Worker Python `payment` (consome, cobra, grava resultado por `(job_id, worker)`, ack depois de gravar). Worker `email` encadeado após pagamento.
- Idempotência, retry com backoff, DLQ para mensagem inválida/esgotada.
- Testes: outbox atômico, idempotência (mesmo `job_id` 2×), nack de mensagem inválida.

**Pronto quando:** `make bench` mostra p95 de `POST /sales` estável sob carga; matar worker/relay no meio não perde venda; `docker compose up --scale payment=N` aumenta vazão de conclusão.
**Não faz:** router, Go.

## [ ] Etapa 4 — Router e múltiplos tipos de trabalho

**Objetivo:** novo tipo de job não exige mudar a API.
**Entrega:**
- Serviço `router`: único que conhece `type → worker` (tabela de roteamento no README).
- Novos jobs de exemplo: `invoice` (nota fiscal fake), `stock_sync`. Filas e DLQ por worker.
- Relay publica só em exchange do router.

**Pronto quando:** adicionar um worker = nova linha na tabela + novo serviço, sem tocar API/relay.

## [ ] Etapa 5 — Leitura e dados sob volume

**Objetivo:** com escrita resolvida, o gargalo migra para leitura/banco.
**Entrega (cada item só se a medição pedir):**
- Seed de milhões de vendas; paginação keyset em `GET /sales`.
- Cache Redis em `GET /sales/{id}` (invalidação por evento de status).
- Particionamento por data ou réplica de leitura; limpeza/arquivamento do `outbox`.

**Pronto quando:** p95 de leitura medido antes/depois por técnica aplicada.

## [ ] Etapa 6 — Resiliência e operação

**Entrega:** circuit breaker/timeout na cobrança, rate limit na API, health/readiness, métricas por fila (profundidade, tempo na fila), dashboard Grafana, tracing com `sale_id`/`job_id` propagado no envelope.

**Pronto quando:** injetar falha na cobrança (100 % de erro por 1 min) não derruba a API e as vendas se recuperam sozinhas.

## [ ] Etapa 7 — Go onde a medição justificar

**Pré-condição:** profiling mostra CPU/memória/latência de um componente como gargalo que Python não resolve com mais réplicas. Candidatos prováveis, em ordem: `relay` (alto volume, loop simples), `router`, worker de cobrança CPU-bound, por fim `api-go`.
**Entrega:**
- Reimplementar *um* componente em Go (`services/relay-go`) com o mesmo contrato; rodar lado a lado com o Python (mesma fila, mesmo envelope).
- Benchmark Python vs. Go (vazão, p99, RAM por réplica, custo de manutenção) registrado em `CHANGELOG.md`.
- Decisão explícita: manter, trocar ou descartar o Go.

**Pronto quando:** decisão documentada com números. Se o ganho não compensar, o Go não entra — isso também é resultado válido.

---

## Ordem e dependências

`0 → 1 → 2 → 3 → 4 → 5/6 (qualquer ordem) → 7`

## Decisões em aberto

- Locust (Python) vs. k6 para carga — sugestão: k6 (não compete por CPU com o app, scripts curtos).
- SQLAlchemy async vs. psycopg puro — sugestão: SQLAlchemy 2 async.
- Biblioteca de mensagens nos workers: `aio-pika` direto (mais didático) vs. Celery/TaskIQ — sugestão: `aio-pika`; Celery/TaskIQ só como comparação opcional na etapa 4.
