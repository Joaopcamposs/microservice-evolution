# Plano de evolução

Princípio: **só migra quando a medição mostra o gargalo.** Cada etapa tem objetivo, entrega, critério de pronto e o que ela deliberadamente *não* faz. Uma etapa por vez; marcar `[x]` ao concluir.

Cenário de carga padrão (`bench/`): N usuários concorrentes fazendo `POST /orders` (1–3 itens) + `GET /orders/{id}`. Métricas: throughput (req/s), p50/p95/p99, taxa de erro, tempo até pedido `COMPLETED`.

---

## [x] Etapa 0 — Cadastros

**Entrega:** API FastAPI + Postgres com cadastro e consulta de usuário, produto e pedido (ver README). Código simples, sem abstrações extras; testes com SQLite em memória.
**Não faz:** estoque, cobrança, e-mail, status, autenticação.

## [ ] Etapa 1 — Fluxo de pedido síncrono

**Objetivo:** dar ao pedido o trabalho que mais tarde ficará lento.
**Entrega:**
- Estoque no produto; criar pedido reserva estoque (lock de linha) e falha com `409` se faltar.
- Status do pedido: `PENDING → PAID → COMPLETED` / `PAYMENT_FAILED`.
- Cobrança fake e e-mail fake (latência e taxa de falha por env), chamados dentro da request; recusa devolve o estoque.
- Testes: estoque, recusa, transições. Só abstrair (ex.: extrair um módulo de serviço) se o router ficar difícil de ler.

**Pronto quando:** `POST /orders` leva ~0,4–1,1 s e o fluxo completo funciona.

## [ ] Etapa 2 — Carga, medição e observabilidade

**Objetivo:** provar o problema com números.
**Entrega:**
- `bench/` (locust ou k6) com o cenário padrão; `make bench`.
- Logs estruturados com `order_id`; métrica de latência por etapa (cobrança, e-mail, banco) — endpoint `/metrics` Prometheus opcional.
- Baseline registrado em `CHANGELOG.md`: com 50/200/500 usuários, onde p95 explode e por quê (workers uvicorn ocupados esperando fakes).
- Ajustes baratos *antes* de arquitetura: pool de conexões, índices (`status`, `user_id`, `created_at`), mais processos uvicorn. Medir de novo. (Workers e pool já medidos em `bench/RESULTS.md`.)

**Pronto quando:** existe tabela baseline vs. ajustes baratos e conclusão escrita de que o gargalo é I/O externo síncrono.
**Não faz:** mudança de arquitetura.

## [ ] Etapa 3 — Desacoplar na mesma base de código (modular)

**Objetivo:** preparar o corte sem introduzir infraestrutura.
**Entrega:**
- Separar fluxo em passos explícitos no `OrderService`: `register_order` (rápido, transacional) vs. `settle_order` (cobrança + e-mail, lento).
- Estados persistidos entre os passos; `settle_order` idempotente (chamável 2× sem cobrar 2×; chave de idempotência na cobrança).
- Experimento: `settle_order` via `BackgroundTasks`. Medir: latência cai, mas pedidos ficam presos em `PENDING` se o processo morrer — documentar a falha como motivação da etapa 4.

**Pronto quando:** `POST /orders` rápido, falha demonstrada (matar processo no meio) e registrada.
**Não faz:** broker.

## [ ] Etapa 4 — Fila + outbox + worker (API + workers async)

**Objetivo:** durabilidade e escala horizontal do trabalho lento.
**Entrega:**
- RabbitMQ no compose.
- Tabela `outbox`; `POST /orders` grava `orders` + `outbox` na mesma transação e responde `202`.
- Serviço `relay`: lê outbox (`FOR UPDATE SKIP LOCKED`), publica, marca enviado.
- `contracts/envelope.schema.json` (`job_id`, `order_id`, `type`, `payload`, `created_at`, `attempt`).
- Worker Python `payment` (consome, cobra, grava resultado por `(job_id, worker)`, ack depois de gravar). Worker `email` encadeado após pagamento.
- Idempotência, retry com backoff, DLQ para mensagem inválida/esgotada.
- Testes: outbox atômico, idempotência (mesmo `job_id` 2×), nack de mensagem inválida.

**Pronto quando:** `make bench` mostra p95 de `POST /orders` estável sob carga; matar worker/relay no meio não perde pedido; `docker compose up --scale payment=N` aumenta vazão de conclusão.
**Não faz:** router, Go.

## [ ] Etapa 5 — Router e múltiplos tipos de trabalho

**Objetivo:** novo tipo de job não exige mudar a API.
**Entrega:**
- Serviço `router`: único que conhece `type → worker` (tabela de roteamento no README).
- Novos jobs de exemplo: `invoice` (nota fiscal fake), `stock_sync`. Filas e DLQ por worker.
- Relay publica só em exchange do router.

**Pronto quando:** adicionar um worker = nova linha na tabela + novo serviço, sem tocar API/relay.

## [ ] Etapa 6 — Leitura e dados sob volume

**Objetivo:** com escrita resolvida, o gargalo migra para leitura/banco.
**Entrega (cada item só se a medição pedir):**
- Seed de milhões de pedidos; paginação keyset em `GET /orders`.
- Cache Redis em `GET /orders/{id}` (invalidação por evento de status).
- Particionamento por data ou réplica de leitura; limpeza/arquivamento do `outbox`.

**Pronto quando:** p95 de leitura medido antes/depois por técnica aplicada.

## [ ] Etapa 7 — Resiliência e operação

**Entrega:** circuit breaker/timeout na cobrança, rate limit na API, health/readiness, métricas por fila (profundidade, tempo na fila), dashboard Grafana, tracing com `order_id`/`job_id` propagado no envelope.

**Pronto quando:** injetar falha na cobrança (100 % de erro por 1 min) não derruba a API e as pedidos se recuperam sozinhas.

## [ ] Etapa 8 — Go onde a medição justificar

**Pré-condição:** profiling mostra CPU/memória/latência de um componente como gargalo que Python não resolve com mais réplicas. Candidatos prováveis, em ordem: `relay` (alto volume, loop simples), `router`, worker de cobrança CPU-bound, por fim `api-go`.
**Entrega:**
- Reimplementar *um* componente em Go (`services/relay-go`) com o mesmo contrato; rodar lado a lado com o Python (mesma fila, mesmo envelope).
- Benchmark Python vs. Go (vazão, p99, RAM por réplica, custo de manutenção) registrado em `CHANGELOG.md`.
- Decisão explícita: manter, trocar ou descartar o Go.

**Pronto quando:** decisão documentada com números. Se o ganho não compensar, o Go não entra — isso também é resultado válido.

---

## Ordem e dependências

`0 → 1 → 2 → 3 → 4 → 5 → 6/7 (qualquer ordem) → 8`

## Decisões em aberto

- ~~Locust vs. k6~~ — decidido: k6 (binário único em Go, roda no compose sem dependências Python, scripts curtos, percentis e limiares embutidos). Resultados em `bench/RESULTS.md`.
- ~~ORM vs. SQL~~ — decidido: SQLAlchemy 2.0 async, `create_all`, sem Alembic (estudo).
- Biblioteca de mensagens nos workers: `aio-pika` direto (mais didático) vs. Celery/TaskIQ — sugestão: `aio-pika`; Celery/TaskIQ só como comparação opcional na etapa 5.
