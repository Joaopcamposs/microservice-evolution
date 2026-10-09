# AGENTS.md

Visão geral em `README.md`; roteiro em `PLANO.md`. Projeto de **estudo**: começa como uma API FastAPI mínima e evolui por etapas pequenas, só quando a necessidade (medida) aparecer. Código simples e organizado; sem abstração antes da hora.

## Documentação

`README.md` e `PLANO.md` fazem parte da entrega. Endpoint novo, tabela alterada ou etapa concluída atualizam o doc no mesmo passo. Doc desatualizada é bug. Mudança notável entra no `CHANGELOG.md`.

## Regras de código

- **Simplicidade primeiro:** sem `Protocol`, interfaces abstratas, unit of work (exceção: integrações externas em `app/services/gateways.py`, que têm Protocol e implementação fake injetada) ou camadas extras até a complexidade pedir. Mudança mínima e focada; não refatore o que não foi pedido.
- **Estrutura:** `app/routers/` (HTTP), `app/domain/` (agregados puros `user.py`, `product.py`, `order.py`, `status.py`, `errors.py`, `security.py`; `schemas.py` = Pydantic de entrada/saída), `app/services/handlers.py` (casos de uso como funções: o `*Writer` busca, o agregado decide, o handler grava e faz commit) e `app/services/effects.py` (`OrderEffects`: cobrança e e-mail depois do commit), `app/services/gateways.py` (Protocols `PaymentGateway`/`EmailSender` + injeção) e `app/services/fakes.py` (implementações fake), `app/repository/{users,products,orders}.py` (um `*Reader` só de leitura e um `*Writer` de escrita por entidade, sobre `base.Repository`; consultas ORM aqui, commit no handler), `app/repository/orm/tables.py` (tabelas Core) e `mapping.py` (mapeamento imperativo dos agregados), `app/infra/database.py`. Router só traduz HTTP; sem SQL/ORM direto nele. GET usa `ReadSessionDep` + `*Reader`; POST/PATCH usam `WriteSessionDep` (handlers + `*Writer`); leituras dentro de uma escrita (locks, ler o que acabou de gravar) usam a sessão de escrita.
- **Tipagem:** tudo tipado (parâmetros, retornos, atributos), sintaxe moderna do Python 3.13 (`list[X]`, `X | None`). Sem `Any` implícito nem `dict` solto onde um modelo cabe.
- **Agregados:** classes puras em `app/domain` (dataclass, sem import de SQLAlchemy/FastAPI) carregam as regras: criação normalizada (`User.register`), estoque (`Order.place`), transições (`Order.move_to`). Erros de regra são `DomainError`; handlers e agregados só os levantam (nada de `HTTPException` fora dos routers) e `app/routers/errors.py` mapeia cada tipo para o status HTTP. Persistência por **mapeamento imperativo** (`registry.map_imperatively`): a própria classe do domínio é mapeada à `Table`, sem camada de cópia. Em consultas use `tables.x.c.coluna` (os atributos da classe são tipados como valores).
- **ORM only:** SQLAlchemy 2.0 (`select()`, `Table`/`Column`); proibido SQL em string.
- **Ids:** UUID v7 (`uuid_utils.compat.uuid7`), gerado na aplicação. **Dinheiro:** `int` em centavos, nunca `float`.
- **Schema:** `create_all` na subida, sem Alembic nem migrações (estudo). Schema mudou: `make reset`.
- **Nomes em inglês; comentários e docstrings em português.** Todo arquivo tem docstring de módulo; toda função/classe tem docstring que explica o propósito, sem repetir o nome (`ruff` `D1` barra ausência). Dockerfile, compose e Makefile têm comentários equivalentes.
- Sem código morto, sem `print`; log com `logging` quando houver o que logar.
- Swagger: toda rota tem `summary` e `description`, e o router tem `tags`.

## Testes

- Todo código novo ou alterado leva teste. Testes usam Postgres real num compose separado (`docker-compose.test.yml`, porta 5433, tmpfs; `make test` sobe sozinho) via override de `get_write_session`/`get_read_session` (`tests/conftest.py`), com tabelas recriadas por teste. Concorrência (estoque, locks) é testada de verdade.
- Rode só o teste relacionado: `make test T=tests/test_orders.py` (`pytest -x --tb=short -q`). Nunca a suíte inteira por padrão.
- Máximo 2 tentativas no mesmo teste que falha; se continuar, pare e explique.
- Só testes que protegem comportamento real (validação, total, 404/409/422, filtros). Sem testes que espelham a implementação.

## Fluxo de trabalho

- Uma etapa do plano por vez. Decisões de evolução (fila, cache, outro serviço) exigem medição antes e depois.
- Antes de dar uma tarefa como pronta: `make ruff` e `make ty` limpos, testes relacionados passando e o fluxo exercitado.
- Nunca faça commit ou push; essa responsabilidade é do humano.
