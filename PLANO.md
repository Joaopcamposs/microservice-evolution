# Plano de evolução

Princípio: **só migra quando a medição mostra o gargalo.** Cada etapa tem objetivo, entrega, critério de pronto e o que ela deliberadamente *não* faz. Uma etapa por vez; marcar `[x]` ao concluir.

Cenário de carga padrão (`bench/`): N usuários concorrentes fazendo `POST /orders` (1–3 itens) + `GET /orders/{id}`. Métricas: throughput (req/s), p50/p95/p99, taxa de erro, tempo até pedido `COMPLETED`.

---

## [x] Etapa 0 — Cadastros

**Entrega:** API FastAPI + Postgres com cadastro e consulta de usuário, produto e pedido (ver README). Código simples, sem abstrações extras; testes com SQLite em memória (migrados para Postgres na etapa 1).
**Não faz:** estoque, cobrança, e-mail, status, autenticação.

## [x] Etapa 1 — Fluxo de pedido síncrono

**Objetivo:** dar ao pedido o trabalho que mais tarde ficará lento.
**Entrega:**
- Estoque no produto; criar pedido reserva estoque (lock de linha) e falha com `409` se faltar.
- Status do pedido com transições validadas: `RECEIVED → AWAITING_PAYMENT → PAID → AWAITING_SHIPMENT → SHIPPED → DELIVERED → COMPLETED` / `PAYMENT_FAILED`; histórico em `order_status_history`; `PATCH /orders/{id}/status` para a operação avançar o pedido.
- Cobrança fake e e-mail fake (latência e taxa de falha por env), chamados dentro da request; um e-mail por mudança de status (na criação: recebido e resultado da cobrança); recusa devolve o estoque.
- Spans OTel manuais `charge` e `send_email`.
- Testes contra Postgres real (compose separado): estoque, recusa, transições e concorrência (sem overselling). Só abstrair (ex.: extrair um módulo de serviço) se o router ficar difícil de ler.

**Pronto quando:** `POST /orders` leva ~0,4–1,1 s e o fluxo completo funciona.

## [x] Etapa 2 — Carga, medição e observabilidade

**Objetivo:** provar o problema com números.
**Entrega:**
- `bench/` (k6) com o cenário padrão; `make bench`.
- Logs com `order_id` na mensagem (filtráveis no Loki; campos estruturados ficam para depois); latência por etapa (cobrança, e-mail, banco) via traces/métricas OpenTelemetry no Grafana (HTTP, queries e spans manuais `charge`/`send_email` já no dashboard).
- Baseline registrado em `CHANGELOG.md`: com 50/200/500 usuários, onde p95 explode e por quê (workers uvicorn ocupados esperando fakes).
- Ajustes baratos *antes* de arquitetura: pool de conexões, índices, mais processos uvicorn. Medir de novo. (Workers e pool medidos em `bench/RESULTS.md`; índices: ver conclusão.)

**Pronto quando:** existe tabela baseline vs. ajustes baratos e conclusão escrita de que o gargalo é I/O externo síncrono.
**Não faz:** mudança de arquitetura.

**Conclusão (números em `bench/RESULTS.md`):**
- Ajustes baratos funcionaram: 4 workers + pool maior levaram a vazão de cadastros de ~550 para ~1450 req/s (p95 com 500 usuários: 5,4 s → 1,3 s). Daí em diante, mais processo/pool não resolve.
- Com o fluxo da Etapa 1, o `POST /orders` leva ~1,0 s (p50 1,02–1,03 s com 50 usuários) e a configuração dos fakes soma 600 ms de cobrança + 2 × 200 ms de e-mail = 1,0 s: **praticamente todo o tempo da request é espera de I/O externo síncrono**, não CPU nem banco (o `GET` fica em ~8 ms de p95 com 50 usuários).
- A vazão é limitada pela latência por request: com 50 usuários, ~93 req/s; com 200–500, satura em ~300–380 req/s, e o p95 do `POST` sobe de 1,3 s para 1,8 s e 4,2–4,8 s. Sem erro (0%) e sem deadlock.
- **Índices:** não criados. Nenhuma consulta filtra por `status` ou `created_at` (a listagem ordena por `id`, UUID v7, que já ordena por criação, e filtra por `id`/`user_id`, ambos indexados). Criar sem consulta que use só custaria escrita. Reavaliar na Etapa 6 se aparecer filtro por status.
- **Saturação com 500 usuários** (`docker stats` durante o k6, VM com 10 CPUs): a API usa ~320–350% de CPU (4 workers, ~80% cada), o Postgres ~45–50% de um núcleo e o k6 ~11%. O recurso que satura é a **CPU dos workers da API** (event loop: serialização, SQLAlchemy, OTel e milhares de corrotinas esperando I/O), não o banco: o `GET`, que leva ~8 ms com 50 usuários, sobe para p50 373 ms / p95 1,17 s por fila no event loop, e o `POST` p95 fica em ~4 s. Sem timeout de pool nos logs. Mais workers ajudariam até acabar a CPU da VM; tirar o trabalho lento da request (Etapas 3–4) reduz o tempo de cada request ocupando recursos.
- Meta de latência: sem meta fixa; os números vão subindo etapa a etapa e cada medição fica registrada em `bench/RESULTS.md`. Métrica "tempo até `COMPLETED`" só faz sentido com fluxo assíncrono (Etapa 3). Logs estruturados (campos no Loki) ficam para a Etapa 4, quando `job_id` precisar correlacionar API, relay e workers.
- Dashboard Grafana conferido: todas as linhas e painéis renderizam com dados reais (RED, por rota, etapas `charge`/`send_email`, queries, pool com 20 conexões em uso sob carga).

## [ ] Etapa 3 — Desacoplar na mesma base de código (modular)

**Objetivo:** preparar o corte sem introduzir infraestrutura.
**Entrega:**
- [x] Fluxo cortado em `handlers.py`: `register_order` (rápido, transacional: carrega, `Order.place`, commit) e `settle_order` (lento: cobrança e e-mail via `OrderEffects`); `create_order` chama as duas em sequência, contrato do `POST /orders` intacto (201 com `PAID`/`PAYMENT_FAILED`).
- [x] `settle_order` idempotente: trava o pedido (`FOR UPDATE`), só `RECEIVED` é liquidado (vai a `AWAITING_PAYMENT` e comita, liberando o lock antes da cobrança); chamadas repetidas ou concorrentes viram no-op. Cobrança usa `order_id` como chave de idempotência (o fake devolve o resultado da primeira). Pedido preso em `AWAITING_PAYMENT` após queda não é retomado (motivação da etapa 4).
- [ ] Experimento: `settle_order` via `BackgroundTasks`. Medir: latência cai, mas pedidos ficam presos em `AWAITING_PAYMENT` se o processo morrer — documentar a falha como motivação da etapa 4.

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
