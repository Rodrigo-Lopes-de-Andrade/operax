.PHONY: help dev dev-backend dev-frontend test lint db-test e2e build \
        sync cadastro motor revogacao ciclo sender dicionario carga-inicial

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

cadastro:       ## promove empresa, departamento e colaborador do espelho para o domínio
	cd backend && uv run python -m operax.motor.cadastro

jornada:        ## materializa app.expected_workday e reporta a cobertura (S3)
	cd backend && uv run python -m operax.motor.jornada --dias $(or $(DIAS),90)

motor:          ## jornada + detecção — MODO=sombra (padrão) | producao
	cd backend && uv run python -m operax.motor --modo=$(or $(MODO),sombra)

revogacao:      ## reconcilia indícios com batidas corrigidas na origem (retroativo)
	cd backend && uv run python -m operax.motor.revogacao --modo=$(or $(MODO),producao) --dias=$(or $(DIAS),7)

ciclo:          ## monta o ciclo de relatório por unidade e enfileira (não envia)
	cd backend && uv run python -m operax.alertas

sender:         ## consome app.alert_queue — não entrega antes do gate G4
	cd backend && uv run python -m operax.alertas.sender

carga-inicial:  ## converte a planilha de RH do cliente em templates (implantação)
	python3 scripts/rh_carga_inicial.py --planilha "$(PLANILHA)" --modelos "$(MODELOS)" --saida "$(SAIDA)"

# ---------------------------------------------------------------------------
# Fora do gate
# ---------------------------------------------------------------------------
e2e:            ## Playwright (1ª vez: npx playwright install)
	cd frontend && npx playwright test

e2e-prod:       ## Playwright contra build de produção — inclui o orçamento de 3s
	cd frontend && E2E_PROD=1 npx playwright test

build:          ## build de produção
	cd frontend && npm run build
	cd backend  && docker build -t operax-backend .
