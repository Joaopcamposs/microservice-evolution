# Tutorial

Guia para rodar, explorar e entender o projeto. Leia junto com [`ARCHITECTURE.md`](ARCHITECTURE.md) (o "porquê") e [`PLANO.md`](PLANO.md) (o "para onde vai").

## 1. Rodando

Pré-requisitos: Python 3.13, [`uv`](https://docs.astral.sh/uv/), Docker.

```bash
uv sync          # instala dependências
make up          # Postgres em Docker (porta 5432)
make run         # API em http://localhost:8000  → Swagger em /docs
```

As tabelas são criadas pela própria API na subida (`create_tables`). Se mudar um modelo ORM: `make reset && make up` (apaga o banco).

## 2. Usando a API (curl)

```bash
H='content-type: application/json'

# 1) usuário (guarde o id)
curl -s -XPOST localhost:8000/users -H "$H" -d '{"name":"Ana","email":"ana@mail.com"}'
export U=<id devolvido>

# 2) produto, cadastrado em nome do usuário (header X-User-Id)
curl -s -XPOST localhost:8000/products -H "$H" -H "X-User-Id: $U" \
     -d '{"name":"Camiseta","price_cents":4990,"stock":10}'
export P=<id devolvido>

# 3) venda (demora ~0,4–1,1 s: cobrança e e-mail fake rodam na request)
curl -s -XPOST localhost:8000/sales -H "$H" -H "X-User-Id: $U" \
     -d "{\"items\":[{\"product_id\":\"$P\",\"quantity\":2}]}"

# 4) consultas
curl -s localhost:8000/sales/<id>
curl -s "localhost:8000/sales?user_id=$U&status=COMPLETED&limit=10"
curl -s localhost:8000/products
```

Tudo também funciona pelo Swagger (`/docs`); lá, preencha o header `X-User-Id`.

## 3. Rodando os testes

```bash
make test-unit                        # rápido, sem Docker
make test T=api/tests/integration     # precisa de `make up`
make ruff && make ty                  # lint/formatação e tipos
```

## 4. Lendo o código: ordem sugerida

1. `domain/sale.py` — o coração: invariantes e máquina de estados, sem nenhum framework.
2. `domain/product.py`, `domain/user.py`, `domain/errors.py`.
3. `domain/repositories.py` — *contratos* de persistência (`Protocol`).
4. `services/sales.py` — o fluxo de venda em 3 transações; compare com o diagrama da seção 6 do ARCHITECTURE.
5. `infrastructure/db/sessions.py` → `models.py` → `write_repositories.py` → `unit_of_work.py` → `read_repositories.py`.
6. `routes/sales.py`, `deps.py`, `main.py` — como tudo é ligado.
7. `tests/unit/fakes.py` + `test_services.py` — veja como o `UnitOfWork` em memória substitui o banco.

## 5. Conceitos usados (glossário rápido)

- **Agregado:** grupo de objetos tratado como uma unidade de consistência, com uma raiz (`Sale` + `SaleItem`). Só se muda por métodos da raiz.
- **Value object:** objeto imutável sem identidade (`SaleItem`).
- **Repositório:** coleção de agregados que esconde a persistência. *Escrita* devolve agregados; *leitura* devolve DTOs.
- **Unit of Work:** "uma transação de negócio": tudo dentro dela confirma junto ou desfaz junto.
- **CQRS leve:** caminhos separados para comandos (mudam estado) e consultas (só leem), sem barramento de eventos.
- **UUID v7:** id aleatório com timestamp nos bits iniciais; ordena por tempo e é gerado sem consultar o banco.
- **Fake:** implementação simulada de um serviço externo (cobrança, e-mail) com latência e falha configuráveis.

## 6. Experimentos para entender os limites

1. **Latência:** `time curl -XPOST .../sales ...`. Troque as variáveis e reinicie:
   `PAYMENT_LATENCY_MIN_MS=2000 PAYMENT_LATENCY_MAX_MS=2000 make run`.
2. **Cobrança recusada:** `PAYMENT_FAILURE_RATE=1 make run`, faça uma venda e veja `PAYMENT_FAILED` e o estoque devolvido em `GET /products`.
3. **Estoque:** produto com `stock: 1`, peça `quantity: 2` → `409`, e nada muda no banco.
4. **Concorrência:** com `stock: 1`, dispare duas vendas simultâneas (dois terminais ou `curl ... &`). Só uma conclui; a outra recebe `409` — efeito do `SELECT ... FOR UPDATE`.
5. **Falha no meio (motivação do outbox):** `PAYMENT_LATENCY_MIN_MS=10000 PAYMENT_LATENCY_MAX_MS=10000 make run`, inicie uma venda e **mate a API de forma abrupta** durante a espera (`pkill -9 -f uvicorn`; um Ctrl-C simples espera a request terminar). Suba de novo e consulte `GET /sales?status=PENDING`: a venda ficou presa e o estoque continua reservado. Nada a recupera — é exatamente o problema que a etapa 3 resolve.
6. **Variedade de erros:** UUID inválido no header (`422`), `X-User-Id` inexistente (`404`), e-mail repetido (`409`).

## 7. Exercício guiado: adicionar um recurso

Para fixar as camadas, adicione "cancelar venda" (`POST /sales/{id}/cancel`), na ordem:

1. **Domínio:** `Sale.cancel()` permitido só em `COMPLETED`/`PAID`; teste unitário das transições.
2. **Serviço:** `SaleService.cancel_sale(sale_id)` — carregar a venda, cancelar, devolver estoque (`Product.restore`) numa transação; teste com os fakes.
3. **Rota:** `POST /sales/{id}/cancel` com `summary`/`description`; devolva o `SaleOut` lendo pelo repositório de leitura.
4. **Modelo:** novo status no `SaleStatus` muda o `Enum` do ORM → `make reset`.
5. **Docs:** README (endpoint), CHANGELOG.

## 8. Para onde vai

Etapa 1: medir (k6), ver o p95 explodir sob carga. Etapa 3: tirar cobrança e e-mail da request com fila + outbox + workers. Depois: router, cache/leitura, resiliência e, só se a medição pedir, componentes em Go. Detalhes em [`PLANO.md`](PLANO.md).
