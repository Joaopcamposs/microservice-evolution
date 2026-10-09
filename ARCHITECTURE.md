# Arquitetura (estado: etapa 0)

Mapa do que existe hoje e **por que** está assim. O roteiro do que vem depois está em [`PLANO.md`](PLANO.md); o passo a passo para usar e estudar o código está em [`TUTORIAL.md`](TUTORIAL.md).

## 1. Visão geral

Um único processo FastAPI, um Postgres. Registrar uma venda executa tudo dentro da request: reserva de estoque, cobrança (fake), e-mail (fake). É propositalmente simples e lento: o objetivo do projeto é medir esse limite e evoluir a arquitetura por etapas.

```
HTTP ──► routes ──► services ──► domain (agregados)
            │           │
            │           └──► UnitOfWork ──► repositórios de ESCRITA ──► WriteSession ──► Postgres
            │           └──► integrations (cobrança fake, e-mail fake)
            └──► repositórios de LEITURA ──► ReadSession ──► Postgres (ou réplica)
```

## 2. Camadas e regra de dependência

Dependências apontam **para dentro**: `domain` não importa nada do resto.

| Camada | Pasta | Responsabilidade | Pode importar |
|---|---|---|---|
| Domínio | `app/domain/` | Agregados `User`, `Product`, `Sale`; invariantes; erros; contratos (`Protocol`) dos repositórios de escrita e do `UnitOfWork`; geração de ids | só stdlib |
| Aplicação | `app/services/` | Casos de uso de escrita: orquestram agregados dentro de transações | domain, schemas, integrations (contratos) |
| Infraestrutura | `app/infrastructure/db/` | ORM, repositórios, sessões, `UnitOfWork` | domain, schemas |
| Integrações | `app/integrations/` | Cobrança e e-mail (contrato + implementação fake) | config |
| Borda | `app/routes/`, `app/schemas.py`, `app/deps.py`, `app/main.py` | HTTP, validação de entrada, formato de saída, montagem das peças | tudo |

`main.py` é a **raiz de composição**: único lugar que conhece as implementações concretas e as injeta.

## 3. Mapa de arquivos

```
api/app/
  main.py                       create_app(): lifespan (engines, tabelas, serviços), handler de erros de domínio
  config.py                     Settings (env): URLs do banco, latência/falha das integrações fake
  deps.py                       Depends: serviços, ReadSession por request, repositórios de leitura, X-User-Id
  schemas.py                    Pydantic: entrada (UserIn, ProductIn, SaleIn) e saída (UserOut, ProductOut, SaleOut)
  routes/{users,products,sales}.py
  services/{users,products,sales}.py
  domain/
    base.py                     Entity (id UUID v7 nasce com o objeto)
    ids.py                      new_id() -> UUID v7
    user.py product.py sale.py  agregados com regras
    errors.py                   exceções de negócio
    repositories.py             Protocols: *WriteRepository e UnitOfWork
  infrastructure/db/
    base.py                     Base(DeclarativeBase) e Model (id + created_at)
    models.py                   Tabelas ORM + to_domain()/from_domain()
    sessions.py                 WriteSession, ReadSession, BaseRepository[S], engines e fábricas
    write_repositories.py       carregam/salvam agregados
    read_repositories.py        consultas -> schemas de saída
    unit_of_work.py             transação: commit ou rollback
    schema.py                   create_tables()
  integrations/{payment,email}.py
api/tests/unit/                 sem banco
api/tests/integration/          Postgres real
```

## 4. Domínio (DDD)

Cada agregado é um `dataclass` mutável **sem** dependência de framework. Mudanças de estado só acontecem por métodos que checam as regras.

- **User** — `register(name, email)`: nome obrigatório, e-mail válido, normalizado em minúsculas. Unicidade do e-mail é regra *entre* agregados, então é checada no serviço (e garantida por `UNIQUE` no banco).
- **Product** — `create(...)` valida preço > 0 e estoque ≥ 0; `reserve(q)` baixa estoque (erro se insuficiente, sem alterar nada); `restore(q)` devolve. Guarda `created_by` (usuário).
- **Sale** — raiz do agregado com `items` (value objects `SaleItem`, imutáveis, com preço congelado). `place(user_id, items)` exige itens, quantidades/preços positivos e produtos distintos. `total_cents` é derivado. Ciclo de vida:

```
PENDING ──mark_paid──► PAID ──complete──► COMPLETED
   └──mark_payment_failed──► PAYMENT_FAILED   (terminal)
```
Transição inválida levanta `InvalidSaleTransitionError`.

Dinheiro é sempre `int` em **centavos**.

## 5. Escrita × leitura (CQRS leve)

- **Escrita:** rota → serviço → `UnitOfWork` → repositórios de escrita → agregados. O serviço devolve apenas o **id**.
- **Leitura:** rota → repositório de leitura → `select` ORM → schema Pydantic. Não instancia agregado: não precisa de invariantes para ler, e evita mapear objeto de domínio só para serializar.
- Depois de escrever, a rota `POST` relê o recurso pelo repositório de leitura para montar a resposta.

### Sessões

`WriteSession` e `ReadSession` são subclasses diferentes de `AsyncSession` (o type checker impede trocar uma pela outra), cada uma com sua engine:

| | WriteSession | ReadSession |
|---|---|---|
| Uso | `UnitOfWork` (repositórios de escrita) | uma por request (`Depends` com `yield`) |
| Transação | sim; commit/rollback no fim do `async with` | não (engine em `AUTOCOMMIT`) |
| URL | `DATABASE_URL` | `DATABASE_READ_URL`, ou `DATABASE_URL` se vazio |

`BaseRepository[S]` é a base abstrata: guarda a sessão recebida no `__init__`.

### UnitOfWork

`async with uow_factory() as uow:` abre sessão + transação e expõe `uow.users/products/sales`. Saiu sem exceção → commit; com exceção → rollback. Os serviços dependem só do `Protocol`, por isso os testes unitários usam um `UnitOfWork` em memória.

## 6. Fluxo de `POST /sales`

```
route.create_sale(X-User-Id, itens)
 └ SaleService.create_sale
    1. [tx 1] _place_sale
        - carrega User (404 se não existe)
        - SELECT ... FOR UPDATE nos produtos, ordenados por id (serializa vendas do mesmo item, evita deadlock)
        - Product.reserve(q) em cada item (409 se faltar estoque)
        - Sale.place(...) -> PENDING; salva produtos e venda        ─ commit
    2. PaymentGateway.charge(...)   (fake: 300–800 ms, 10 % de recusa)   ← fora de transação
    3a. recusada: [tx 2] mark_payment_failed + Product.restore em cada item   ─ commit
    3b. aprovada: [tx 2] mark_paid ─ commit
                  EmailSender.send_confirmation(...) (fake: 100–300 ms)
                  [tx 3] complete ─ commit
 └ route relê a venda (ReadSession) e responde 201
```
A cobrança e o e-mail ficam **fora** de transação de propósito: não se segura conexão/lock de banco enquanto se espera sistema externo.

## 7. Erros → HTTP

Um handler único em `main.py` mapeia exceções de domínio:

| Erro | HTTP |
|---|---|
| `UserNotFoundError`, `ProductNotFoundError` | 404 |
| `EmailAlreadyRegisteredError`, `InsufficientStockError`, `InvalidSaleTransitionError` | 409 |
| `InvalidValueError` | 422 |
| outro `DomainError` | 500 |

Validação de formato (UUID malformado, campo faltando) é do FastAPI/Pydantic → 422.

## 8. Decisões técnicas

| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| Agregados puros + modelos ORM separados | Domínio = modelo SQLAlchemy | Domínio testável sem banco e sem framework; custo: `to_domain/from_domain` |
| ORM SQLAlchemy 2.0 async, sem SQL em string | `asyncpg` com SQL direto | Pedido do projeto; tipagem `Mapped[...]`; sem injeção por construção |
| `create_all`, sem Alembic | Alembic | Projeto de estudo; schema mudou → `make reset` |
| UUID v7 gerado no domínio | `BIGSERIAL` / UUID v4 | Id existe antes de persistir (sem `flush` só para obter id); v7 é ordenável por tempo → melhor localidade de índice que v4 |
| `uuid-utils` | implementar v7 à mão | Python 3.13 não tem `uuid.uuid7` (vem no 3.14); troca de 1 linha depois |
| Escrita/leitura separadas, sessões distintas | Um repositório só | Prepara réplica de leitura (etapa 5); deixa explícito o que escreve |
| `UnitOfWork` como `Protocol` | Serviço usando `AsyncSession` | Serviços testáveis com fake em memória |
| Integrações fake atrás de `Protocol` | Chamar o sleep direto no serviço | Mover cobrança/e-mail para workers sem tocar a regra de venda |
| `SELECT ... FOR UPDATE` no estoque | Lock otimista / `UPDATE ... WHERE stock >= q` | Simples e correto; contenção só aparece com muita carga no mesmo produto |
| Ator por header `X-User-Id` | Autenticação (JWT) | Foco é arquitetura; auth seria distração |
| Cobrança recusada → `201` com `PAYMENT_FAILED` | `402` | A venda existe e é consultável |

## 9. Testes

- **Unitários** (`tests/unit`, ~0,3 s, sem Docker): invariantes dos agregados, ids, serviços com `UnitOfWork`/pagamento/e-mail falsos (inclui rollback em estoque insuficiente e devolução de estoque na recusa), sessões/config.
- **Integração** (`tests/integration`, exige `make up`): rotas reais + ORM + Postgres (`sales_test`, recriado por sessão; tabelas recriadas por teste). Cobre o que o unitário não prova: mapeamento ORM, `FOR UPDATE`, filtros, códigos HTTP.

## 10. Limitações conhecidas (e por que importam para o estudo)

1. **Latência da request = soma das integrações** (~0,4–1,1 s). É o gargalo a ser medido na etapa 1 e removido na 3.
2. **Sem atomicidade entre passos:** se o processo morrer entre `charge` e `mark_paid`, a venda fica `PENDING` com estoque reservado e possivelmente cobrada. É a motivação do outbox (etapa 3).
3. **Sem idempotência na cobrança:** repetir o fluxo cobraria duas vezes (etapa 2/3).
4. **Leitura após escrita:** com réplica real, o `GET` interno do `POST` pode ver dados antigos.
5. **Sem autenticação**, sem rate limit, sem paginação por keyset (offset), sem índices além de PK/unique.
