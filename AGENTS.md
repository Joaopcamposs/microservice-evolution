# AGENTS.md

Visão geral em `README.md`; roteiro de evolução em `PLANO.md`. Projeto de demonstração, minimalista: código enxuto, sem funcionalidade extra. Começa como API FastAPI síncrona de vendas e evolui por etapas até API + workers assíncronos (e, se a medição justificar, serviços em Go).

## Documentação

`README.md`, `PLANO.md`, `ARCHITECTURE.md` e `TUTORIAL.md` fazem parte da entrega (mudou camada, fluxo, decisão técnica ou comando: atualizar o doc correspondente). Serviço criado/removido, endpoint novo, contrato (`contracts/envelope.schema.json`, quando existir), schema (`api/app/infrastructure/db/models.py`) ou tabela de roteamento alterados atualizam o README no mesmo passo. Etapa concluída é marcada em `PLANO.md`. Doc desatualizada é bug. Mudança notável entra no `CHANGELOG.md` no mesmo passo.

## Regras de código

### Tipagem
- Python: tudo tipado (parâmetros, retornos, atributos). Sem `Any` implícito nem `dict` solto onde um modelo cabe.
- Sintaxe moderna (Python 3.13): `list[Sale]`, `X | None`, `StrEnum`, `dataclass(frozen=True, slots=True)`.
- Dados são `dataclass` (domínio) ou `pydantic.BaseModel` (borda). Sem tuplas/dicts anônimos entre camadas.
- `dataclass(frozen=True, slots=True)` para value objects; agregados e entidades são `dataclass(slots=True, eq=False, kw_only=True)` herdando de `Entity` (mutáveis, mudam só por métodos de negócio).
- Go (só se a etapa 7 do plano for executada): structs com tags explícitas, erros retornados e tratados (nunca ignorados com `_`), `context.Context` como primeiro parâmetro em I/O.

### Arquitetura (DDD)
- Camadas: `domain` (agregados puros, sem SQLAlchemy/FastAPI/pydantic, regras e invariantes nos métodos do agregado) → `services` (casos de uso de escrita, orquestram agregados via `UnitOfWork`) → `infrastructure` (ORM, repositórios, UoW) → `routes` (HTTP).
- **Escrita e leitura separadas (CQRS leve):** repositórios de *escrita* carregam/salvam agregados de domínio (interfaces `Protocol` em `domain/repositories.py`); repositórios de *leitura* fazem `select` ORM e devolvem modelos de saída (`schemas.py`) sem passar pelo domínio. Rotas de leitura usam o repositório de leitura direto; rotas de escrita usam um serviço, que devolve só o id.
- **Sessões separadas:** `WriteSession` (transação, usada só pelo `UnitOfWork`) e `ReadSession` (engine AUTOCOMMIT, uma por request via `Depends`) são tipos distintos, cada um com sua engine/fábrica (`infrastructure/db/sessions.py`). Todo repositório herda de `BaseRepository[S]` (abstrato; guarda a sessão no `__init__`). Escrita nunca usa `ReadSession` e vice-versa.
- **Persistência só via ORM** SQLAlchemy 2.0 (`DeclarativeBase`, `Mapped`, `mapped_column`, `select()`); proibido SQL em string. Modelos ORM ficam em `infrastructure/db/models.py`, separados dos agregados, com `to_domain()`/`from_domain()`.
- **Ids:** UUID v7 gerado no domínio (`domain/ids.py::new_id`, via `uuid-utils` até o Python 3.14 trazer `uuid.uuid7`); `Entity.id` nunca é `None` e o banco não gera chaves. Tipo `UUID` em todo parâmetro de id.
- **Usuário:** `User` é agregado; toda `Sale` tem `user_id` (comprador) e todo `Product` tem `created_by`. O usuário que age vem do header `X-User-Id` (sem autenticação nesta demo).
- **Schema:** `Base.metadata.create_all` (`create_tables`) no `lifespan`. Sem `init.sql`. Sem Alembic nem migrações (projeto de estudo): schema mudou, `make reset` recria o banco.

### Funções e classes
- Uma responsabilidade por função; nome = verbo + objeto; sem flags booleanas que mudam o comportamento.
- Comportamento com estado ou dependências vive numa classe gerenciadora (Python) ou struct com `New...` (Go), com dependências injetadas (FastAPI `Depends`). Sem estado global mutável; estado de processo (pool de conexões, clientes) é criado no `lifespan` (FastAPI) ou no `main` (Go).
- Funções livres só para lógica pura.

### Código limpo
- Nomes em inglês; comentários e docstrings em português.
- Todo arquivo tem docstring/comentário de módulo (o que é e por quê); toda classe, função e método tem docstring que explica propósito e limites, não repete o nome. SQL, Makefile, compose e Dockerfile têm comentários equivalentes. `ruff` (regras `D1`) barra docstring ausente em Python.
- Sem código morto, sem `print`. Log estruturado: `log/slog` em JSON (Go) ou `logging` (Python), sempre com `sale_id` (e `job_id`, a partir da etapa 3) quando houver.
- Mudanças mínimas e focadas; não refatore o que não foi pedido.

## Padrões do projeto

Válidos desde a etapa 0:
- **Integrações fake isoladas:** cobrança e e-mail são classes atrás de uma interface (`Protocol`), com latência e falha simuladas e configuráveis por env. Nenhum código de domínio conhece a implementação; isso permite movê-las para workers sem tocar a regra de venda.
- **Dinheiro:** valores em centavos (`int`); nunca `float`.
- **Camadas:** `routes` (HTTP/Pydantic) → `services` (regra) → `repositories` (SQL). Rota não escreve SQL.
- **Swagger:** a API expõe `/docs` com `summary`, `description` e `tags` em cada rota.
- **Dependências por serviço:** sem imports entre serviços.

Entram nas etapas indicadas em `PLANO.md`; não antecipar:
- **Outbox (etapa 3):** a API nunca publica no RabbitMQ. Grava `sales` + `outbox` na mesma transação; só o `relay` publica.
- **Contrato único (etapa 3):** todo serviço assíncrono fala o envelope de `contracts/envelope.schema.json`. Mudança de contrato e de consumidores entra junto.
- **Router é o único que conhece workers (etapa 4):** tabela `type → worker`.
- **Idempotência (etapa 3):** workers aceitam o mesmo `job_id` mais de uma vez; resultado por `(job_id, worker)`.
- **Ack explícito (etapa 3):** ack só depois de gravar o resultado. Mensagem inválida: `reject`/`nack` sem requeue (vai para DLQ).
- **Mesma API em implementações paralelas (etapa 7):** se existir `api-go`, expõe os mesmos endpoints e respostas da `api` Python.

## Testes

- **Todo código novo ou alterado leva teste unitário** (`api/tests/unit`, sem Postgres: agregados puros e serviços com `UnitOfWork` em memória). Integração (`api/tests/integration`, Postgres real) só para o que o unitário não prova: ORM, locks, rotas.
- Rode só o teste relacionado: `make test-unit` ou `pytest -x --tb=short -q <arquivo>` (ou `go test ./...` no serviço Go). Nunca a suíte inteira por padrão.
- Máximo 2 tentativas no mesmo teste que falha; se continuar, pare e explique.
- Python: `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`).
- Antes de testes de integração: `docker ps`.
- Só testes que protegem comportamento real (invariantes do agregado, transições de estado, total, falha de cobrança com devolução de estoque, outbox, idempotência, validação). Sem testes que espelham a implementação.

## Medição

- Decisões de evolução (etapa nova, trocar para Go) exigem número: benchmark de carga reproduzível (`make bench`) antes e depois, registrado em `PLANO.md`/`CHANGELOG.md`. Sem medição, sem migração.

## Fluxo de trabalho

- Uma etapa do plano por vez, uma linguagem por etapa: nunca misture alterações Python e Go na mesma etapa.
- Antes de dar uma tarefa como pronta: `make ruff` e `make ty` limpos (Python), `go vet` e `gofmt -l` limpos (Go) e o fluxo afetado exercitado.
- Nunca faça commit ou push; essa responsabilidade é do humano.
