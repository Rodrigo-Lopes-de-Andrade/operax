.PHONY: help dev dev-backend dev-frontend test lint db-test e2e build \
        sync motor sender dicionario

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Desenvolvimento
# ---------------------------------------------------------------------------
dev:            ## backend + frontend
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:    ## só a API FastAPI
	cd backend && uv run uvicorn server.main:app --reload --port 8000

dev-frontend:   ## só a UI
	cd frontend && npm run dev

# ---------------------------------------------------------------------------
# Gate de conclusão — rode os dois antes de declarar qualquer tarefa pronta
# ---------------------------------------------------------------------------
test:           ## pytest + Vitest
	cd backend  && uv run pytest -q
	cd frontend && npx vitest run

lint:           ## Ruff + Prettier + tsc --noEmit
	cd backend  && uv run ruff check . && uv run ruff format --check .
	cd frontend && npx prettier --check . && npx tsc --noEmit

# ---------------------------------------------------------------------------
# Banco — obrigatório em qualquer PR que toque policy, view, grant ou migration
# ---------------------------------------------------------------------------
db-test:        ## migrations + isolamento + dicionário + refs da documentação
	./scripts/testar_migrations.sh

dicionario:     ## regenera docs/DICIONARIO-DE-DADOS.md a partir do banco
	python3 scripts/gerar_dicionario.py

# ---------------------------------------------------------------------------
# Tarefas do backend (sob demanda em dev; agendadas no Railway)
# ---------------------------------------------------------------------------
sync:           ## espelha a origem em `secullum`
	cd backend && uv run python -m operax.sync

motor:          ## detecção — MODO=sombra (padrão) | producao
	cd backend && uv run python -m operax.motor --modo=$(or $(MODO),sombra)

sender:         ## consome app.alerta_fila
	cd backend && uv run python -m operax.alertas.sender

# ---------------------------------------------------------------------------
# Fora do gate
# ---------------------------------------------------------------------------
e2e:            ## Playwright (1ª vez: npx playwright install)
	cd frontend && npx playwright test

build:          ## build de produção
	cd frontend && npm run build
	cd backend  && docker build -t operax-backend .
