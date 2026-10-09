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
- Observabilidade: OpenTelemetry nativo do FastAPI (`fastapi[opentelemetry]`) + `opentelemetry-instrumentation-sqlalchemy` (com `skip_dep_check`, pois declara suporte só até SQLAlchemy 2.0) exportando para `grafana/otel-lgtm` no compose (Grafana em :3000). Custo medido: -22% a -40% de vazão (ver `bench/RESULTS.md`).
- Dashboard Grafana "Orders API" provisionado por arquivo (`observability/`): RED, por rota, etapas da requisição, banco/pool, traces lentos e logs.
- API com healthcheck no compose (o k6 espera a API ficar saudável).
- A versão com DDD/UoW/CQRS ficou na branch `major-complexo`.
