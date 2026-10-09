# Changelog

## Não lançado

- Planejamento inicial: `AGENTS.md`, `README.md` e `PLANO.md`.
- Etapa 0 (versão simples): cadastros e consultas de usuário, produto e pedido (FastAPI + SQLAlchemy async + Postgres, UUID v7). Testes com SQLite em memória.
- Usuário com senha (hash scrypt, nunca devolvida) e e-mail validado com `EmailStr`. Schema mudou: `make reset`.
- A versão com DDD/UoW/CQRS ficou na branch `major-complexo`.
