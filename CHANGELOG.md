# Changelog

## Não lançado

- Docs: `ARCHITECTURE.md` (camadas, fluxo, decisões, limitações) e `TUTORIAL.md` (execução, leitura guiada, experimentos). Alembic removido do plano (projeto de estudo).
- Etapa 0: API FastAPI síncrona (usuários, produtos, vendas, cobrança e e-mail fake), Postgres via compose.
- DDD com agregados puros (`User`, `Product`, `Sale`), `UnitOfWork`, repositórios de escrita e leitura separados, ORM SQLAlchemy 2.0 (`create_all`, sem `init.sql`), `X-User-Id` identifica o ator.
- Ids são UUID v7 gerados no domínio (`uuid-utils`); `X-User-Id`, paths e filtros usam UUID.
- `BaseRepository` abstrato; `WriteSession`/`ReadSession` separadas, com engines próprias (`DATABASE_READ_URL` opcional); leitura em sessão por request.
- 27 testes unitários + 5 de integração.
- Planejamento inicial: `AGENTS.md` adaptado, `README.md` e `PLANO.md` criados.
