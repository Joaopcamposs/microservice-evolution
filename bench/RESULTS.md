# Resultados de carga

Registro das medições do `make bench`. Cada linha nova entra com data e a mudança que a motivou, para comparar antes e depois.

## 2026-10-09 — Baseline (etapa 0, só cadastros)

**Ambiente:** Docker local (Mac, 10 CPUs), k6 e API na mesma máquina, Postgres 17 em container.
**API:** 1 worker uvicorn, pool padrão do SQLAlchemy (5 + 10 de overflow), sem estoque, cobrança ou e-mail.
**Cenário:** `bench/orders.js` — cada usuário virtual faz `POST /orders` (1–3 itens) e depois `GET /orders?id=`, por 30 s. Massa: 10 usuários e 10 produtos criados no `setup`.

### Geral

| Usuários | req/s | iterações/s | p50 | p95 | p99 | máx | erros |
|---|---|---|---|---|---|---|---|
| 50 | 568 | 284 | 31 ms | 317 ms | 524 ms | 1,25 s | 0% |
| 200 | 538 | 269 | 33 ms | 1,63 s | 2,66 s | 5,15 s | 0% |
| 500 | 391 | 195 | 48 ms | 5,4 s | 9,1 s | 20 s | 0% |

### Por endpoint (p50 / p95 / p99)

| Usuários | `POST /orders` | `GET /orders?id=` |
|---|---|---|
| 50 | 35 ms / 327 ms / 548 ms | 20 ms / 305 ms / 511 ms |
| 200 | 38 ms / 1,66 s / 2,67 s | 21 ms / 1,58 s / 2,62 s |
| 500 | 76 ms / 6,05 s / 9,85 s | 31 ms / 4,79 s / 8,79 s |

### Leitura

- A vazão satura em torno de 550 req/s já com 50 usuários; acima disso só a fila cresce (e a vazão cai com 500).
- A mediana quase não muda e a cauda explode: poucas requisições esperam muito. Os dois endpoints sofrem igual.
- **Causa não medida.** Suspeitas: worker único do uvicorn e pool de 15 conexões. Próximo passo: variar workers e pool, uma mudança por vez.
- Os números valem para comparação entre rodadas, não como valor absoluto (k6 e API disputam CPU; Docker no Mac tem overhead).

## 2026-10-09 — Workers e pool (uma variável por vez)

Mesmo ambiente e cenário do baseline. Variáveis: `WEB_CONCURRENCY` (workers uvicorn), `DB_POOL_SIZE` e `DB_MAX_OVERFLOW` (por worker).

| Config | Workers | Pool + overflow | Conexões máx. | 50 usuários | 200 usuários | 500 usuários |
|---|---|---|---|---|---|---|
| A (baseline) | 1 | 5 + 10 | 15 | 568 req/s · p95 317 ms | 538 req/s · p95 1,63 s | 391 req/s · p95 5,4 s |
| B (só pool) | 1 | 20 + 20 | 40 | 591 req/s · p95 169 ms | 561 req/s · p95 1,47 s | 499 req/s · p95 4,95 s |
| C (só workers) | 4 | 5 + 10 | 60 | 1457 req/s · p95 64 ms | 1453 req/s · p95 468 ms | 1449 req/s · p95 1,32 s |
| D (workers + pool) | 4 | 15 + 10 | 100 | 1815 req/s · p95 44 ms | 1741 req/s · p95 311 ms | 1574 req/s · p95 1,2 s |

Todas sem erros (0%). p99 com 500 usuários: A 9,1 s · B 8,4 s · C 2,35 s · D 2,16 s.

### Leitura

- **O gargalo principal era CPU do processo Python:** 4 workers multiplicam a vazão por ~2,6x (A→C) e derrubam o p95 com 500 usuários de 5,4 s para 1,3 s.
- **Pool maior sozinho ajuda pouco** (B: +4% a +28% de vazão, p95 melhor com 50 usuários): com um worker só, 15 conexões já sobravam.
- **Pool maior com 4 workers rende mais** (C→D: +20% com 50 usuários, +9% com 500), mas D chega a 100 conexões, o `max_connections` padrão do Postgres; sem folga para outros clientes. O padrão do compose ficou em C (60 conexões).
- Mesmo com 4 workers a cauda ainda cresce com 500 usuários (p95 > 1 s): a fila só foi empurrada para mais longe. Dez núcleos são divididos com k6 e Postgres, então 4 workers pode já estar perto do teto desta máquina.
- Não medido ainda: 8 workers, Postgres como gargalo (CPU/`max_connections`), custo de cada etapa dentro da requisição.

## 2026-10-09 — Custo do OpenTelemetry

Mesma config da C (4 workers, pool 5 + 10). OTel nativo do FastAPI (traces, métricas, logs) + `SQLAlchemyInstrumentor`, exportando OTLP para o `grafana/otel-lgtm` (que roda na mesma máquina e consome CPU também). `OTEL_TRACES_SAMPLER_ARG` controla só a fração de traces; métricas seguem sempre ligadas.

| Config | 50 usuários | 200 usuários | 500 usuários |
|---|---|---|---|
| C (sem OTel) | 1457 req/s · p95 64 ms | 1453 req/s · p95 468 ms | 1449 req/s · p95 1,32 s |
| E (OTel, 100% dos traces) | 979 req/s · p95 178 ms | 911 req/s · p95 735 ms | 885 req/s · p95 2,2 s |
| F (OTel, 10% dos traces) | 1146 req/s · p95 116 ms | 1122 req/s · p95 615 ms | 1118 req/s · p95 1,73 s |

Todas sem erros (0%).

### Leitura

- **Observar custa caro aqui:** 100% dos traces derrubam a vazão em ~35–40%; 10% ainda custa ~22%. Parte vem de cada requisição gerar ~9 spans (HTTP, dependências, endpoint, queries, serialização) e das métricas/logs; parte da CPU que o container do Grafana toma da mesma máquina.
- **Amostragem alivia, mas não zera:** a diferença E→F (~+25%) é o custo dos spans; o que sobra em F é métricas, contexto e o coletor.
- **Regra daqui em diante:** comparar benchmarks sempre com a mesma configuração de OTel; para medir limite de capacidade pura, rodar com `FASTAPI_OTEL_AUTO_CONFIGURE=false`. Para investigar gargalo, usar OTel ligado e olhar os traces.

## 2026-10-09 — Etapa 1: fluxo síncrono (estoque + cobrança + e-mail fakes)

Config: 4 workers, pool 5 + 10, OTel ligado com 100% dos traces (comparável à linha E). `POST /orders` agora reserva estoque (`FOR UPDATE`), cobra (600 ms ±40%, 10% de recusa) e envia e-mail (200 ms ±40%, 5% de falha) dentro da request. Produtos do bench com estoque de 100 milhões (sem 409).

| Usuários | req/s | POST /orders p50 | p95 | p99 | GET /orders?id p95 | erros |
|---|---|---|---|---|---|---|
| 50 | 120 | 806 ms | 1,05 s | 1,10 s | 7,6 ms | 0% |
| 200 | 391 | 926 ms | 1,52 s | 1,87 s | 51 ms | 0% |
| 500 | 451 | 1,61 s | 3,32 s | 4,76 s | 763 ms | 0% |

### Leitura

- **`POST /orders` leva ~0,8 s** (meta da etapa: 0,4–1,1 s); quase tudo é espera de cobrança + e-mail, não CPU nem banco.
- **A vazão cai de ~885 para ~120 req/s com 50 usuários** (E → agora): cada VU passa quase todo o tempo esperando os fakes. É o problema que as próximas etapas devem resolver (tirar o trabalho lento da request).
- **Com 500 usuários a API satura** (~450 req/s): a espera não ocupa CPU, mas a fila de requisições e o `GET` rápido também sofrem (p95 de 763 ms contra 7,6 ms com 50).
- **Bug achado pelo bench:** a primeira rodada deu ~8,6% de 5xx com 200/500 usuários — `deadlock detected`. A devolução de estoque (cobrança recusada) atualizava produtos fora da ordem de id usada na reserva. Corrigido ordenando por `product_id` e coberto por teste de concorrência.
