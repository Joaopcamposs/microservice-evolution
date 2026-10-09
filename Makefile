# Atalhos de desenvolvimento. Uso: make <alvo>.
.PHONY: up down reset run test test-unit ruff ty

# Sobe o Postgres e espera ficar saudável.
up:
	docker compose up -d --wait

# Para os containers (mantém o volume).
down:
	docker compose down

# Apaga o volume do banco (a API recria as tabelas na subida).
reset:
	docker compose down -v

# API em modo desenvolvimento (precisa do Postgres: make up).
run:
	uv run uvicorn app.main:app --app-dir api --reload

# Todos os testes (integração precisa do Postgres: make up). Uso: make test T=api/tests/unit
test:
	uv run pytest -x --tb=short -q $(T)

# Lint + formatação.
ruff:
	uv run ruff check . && uv run ruff format --check .

# Checagem de tipos.
ty:
	uv run ty check api

# Só testes unitários (sem Postgres).
test-unit:
	uv run pytest -x --tb=short -q api/tests/unit
