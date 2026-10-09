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
