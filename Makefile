# Atalhos de desenvolvimento. Uso: make <alvo>.
.PHONY: up down reset run test ruff ty

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

# Testes (usam SQLite em memória, sem Docker). Uso: make test T=tests/test_orders.py
test:
	uv run pytest -x --tb=short -q $(T)

# Lint + formatação.
ruff:
	uv run ruff check . && uv run ruff format --check .

# Checagem de tipos.
ty:
	uv run ty check app tests
