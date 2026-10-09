# Atalhos de desenvolvimento. Uso: make <alvo>.
.PHONY: up down reset run test test-db bench ruff ty

# Sobe API + Postgres (reconstrói a imagem) e espera ficar saudável.
up:
	docker compose up -d --build --wait

# Para API e Postgres (mantém os dados).
down:
	docker compose down

# Apaga os dados (as tabelas são recriadas pela API na subida).
reset:
	docker compose down -v

# API local com reload (precisa do Postgres: docker compose up -d --wait postgres).
run:
	uv run uvicorn app.main:app --reload

# Sobe o Postgres de testes (compose separado, porta 5433, dados em tmpfs).
test-db:
	docker compose -f docker-compose.test.yml up -d --wait

# Testes contra o Postgres de testes (sobe sozinho). Uso: make test T=tests/test_orders.py
test: test-db
	uv run pytest -x --tb=short -q $(T)

# Carga com k6 contra a API do compose (sobe tudo antes). Uso: make bench VUS="50 200 500" DURATION=30s
VUS ?= 50 200 500
DURATION ?= 30s
bench: up
	for v in $(VUS); do \
		echo "== $$v usuários concorrentes =="; \
		docker compose run --rm -e VUS=$$v -e DURATION=$(DURATION) k6; \
	done

# Lint + formatação.
ruff:
	uv run ruff check . && uv run ruff format --check .

# Checagem de tipos.
ty:
	uv run ty check app tests
