# OperaX — Plano de sprints

Uma linha do tempo só, com quatro trilhas: **banco**, **backend** (FastAPI no
Railway — sync, motor, alertas, assistente), **frontend** (Next.js na Vercel) e
**produto/comercial**. O que estava separado como "sprint de banco" e "sprint de
produto" vira sequência única, porque as dependências são reais e ignorá-las é o
que produz retrabalho.

Estimativas em dias úteis, para uma pessoa dedicada. Contagem começa a partir do
recebimento dos acessos.

---

## Gates — pontos onde a sprint seguinte não começa

Não são recomendações. Cada um existe porque violá-lo custa mais caro do que
esperar.

| Gate | Condição | Bloqueia | Por quê |
|---|---|---|---|
| **G1** | Diagnóstico rodado e convenção PascalCase confirmada | S0 | As migrations 00 e 03 selecionam por essa convenção |
| **G2** | Suíte de isolamento verde | S3 | Motor grava dado real; RLS errada vira vazamento |
| **G3** | Jornada esperada com ≥80% de confiança | S4 | Sem escala correta, o motor é gerador de falso positivo |
| **G4** | Falso positivo ≤5% em duas execuções de sombra | S6 | Primeiro relatório errado mata a credibilidade e não se recupera |
| **G5** | Regras homologadas com cliente + jurídico/RH | envio real | Alerta nominal indevido é risco trabalhista |
| **G6** | Cláusula de IP assinada | comercializar | Sem ela é projeto sob encomenda, não produto |

---

## S0 — Diagnóstico e blindagem · 2–3 dias

**Objetivo:** fechar a exposição de dado pessoal e montar a fundação, sem quebrar
nada que já roda.

| Trilha | Entrega |
|---|---|
| Banco | `scripts/00_diagnostico.sql` rodado e commitado; migrations `00`, `01`, `02` |
| Infra | Exposed schemas reduzido a `public` e `graphql_public` |
| Produto | Redação da cláusula de IP e licenciamento |

Não quebra o worker: `service_role` tem grants próprios e ignora RLS. O frontend
ainda não existe.

**Aceite**

- Nenhuma tabela do espelho legível pela chave pública (a própria migration falha
  se sobrar).
- Advisor do Supabase sem alerta de tabela exposta.
- Tenant `kastro-park` criado com a matriz de sensibilidade populada.

**⚠️ G1** — se a convenção de nomes não for PascalCase, ajustar o predicado das
migrations `00` e `03` antes de aplicar.

---

## S1 — Isolamento e ajuste do worker · 3–5 dias

**Objetivo:** mover o espelho para schema privado e apontar o worker para lá.

| Trilha | Entrega |
|---|---|
| Banco | Migrations `03` e `04` |
| Backend | `operax/sync/` aponta para o schema `secullum`; `core/tenant.py` injeta `tenant_id` em todo acesso |
| Dados | Cadastrar unidades reais; preencher o mapeamento Departamento → unidade |

**A migration `03` quebra o worker.** Banco e código no mesmo PR.

O mapeamento de unidades é trabalho de curadoria com o cliente, não de código. É
onde os ~26% de divergência entre empresa e departamento são resolvidos de uma vez.

**Aceite**

- Ciclo completo de sincronização sem erro.
- Zero colaborador ativo sem unidade, ou fila de pendência de mapeamento visível.
- `public` sem nenhuma tabela.

---

## S2 — Modelo completo e superfície de API · 3–5 dias

**Objetivo:** o resto do modelo e a API pronta para o frontend consumir.

| Trilha | Entrega |
|---|---|
| Banco | Migrations `05` a `11` |
| Banco | Suíte `testar_migrations.sh` no CI |
| Doc | Dicionário de dados regenerado |

**Aceite**

- 14 migrations aplicam limpas em banco descartável.
- 23 asserções funcionais e 11 estruturais passando.
- Views e RPCs respondendo com um usuário de teste autenticado.

**⚠️ G2** — a suíte verde é pré-requisito para qualquer gravação de dado real.

---

## S3 — Jornada esperada · 5 dias

**Objetivo:** materializar o que era esperado de cada colaborador em cada dia.
Sem isso, o motor não tem contra o que comparar.

| Trilha | Entrega |
|---|---|
| Backend | `operax/motor/jornada.py` preenche `app.expected_workday` a partir de Horario/HorarioDia e afastamentos |
| Backend | Cálculo do grau de confiança por linha |
| Produto | Relatório de cobertura: % de colaboradores com confiança ≥80 |

**Este é o sprint que decide o cronograma real.** Estacionamento opera em 12x36 e
revezamento. Se `HorarioDia` descreve semana fixa, a escala não cabe e a confiança
despenca.

Se mais de 20% ficar abaixo de 80, entra um sub-sprint de cadastro manual de
escala — trabalho de implantação que precisa estar dimensionado na proposta, não
absorvido em silêncio.

**Aceite**

- `app.expected_workday` preenchida para os últimos 90 dias.
- Percentual de confiança medido e reportado.
- Precedência verificada: afastamento > folga > jornada.

**⚠️ G3**

---

## S4 — Motor em modo sombra · 5–10 dias

**Objetivo:** detectar desvio sem publicar nada, e medir o erro.

| Trilha | Entrega |
|---|---|
| Backend | `operax/motor/deteccao.py` conforme a spec |
| Backend | Gravação idempotente com `on conflict` |
| Backend | `operax/motor/revogacao.py` para correção retroativa |
| Produto | Comparativo sombra × apuração do Secullum, com divergências classificadas |

A duração varia porque depende de quantas rodadas de correção forem necessárias.
Uma semana de dados por rodada.

**Aceite**

- Reprocessar o mesmo período duas vezes não altera contagem.
- Toda divergência classificada em escala errada, tolerância errada ou bug.
- Falso positivo ≤5% em duas execuções seguidas.

**⚠️ G4** — nenhum alerta ou relatório sai antes disso.

---

## S5 — Dashboard · 7–10 dias

**Objetivo:** a tela. Pode começar em paralelo ao S4 usando dados de sombra.

| Trilha | Entrega |
|---|---|
| Frontend | Projeto Next.js 16 na Vercel, autenticação Supabase |
| Backend | Endpoints FastAPI para dado individual e sensível (`server/routers/`) |
| Frontend | Filtros empresa → unidade → período, estado na query string |
| Frontend | KPIs, tendência, rankings, recorrência, drill-down |
| Frontend | Consulta individual do colaborador |
| Frontend | Monitor diário, com indicador de idade do dado (`fn_data_freshness`) |
| Frontend | Tela de TV, só agregado, sem nome |

**Aceite**

- Dashboard abre em menos de 3 s no período padrão.
- Link com query string abre já filtrado.
- Supervisor de unidade não enxerga outra unidade nem dado sensível — verificado
  na tela, não só no banco.
- Nenhum nome de colaborador na tela de TV.

---

## S6 — Alertas e relatório consolidado · 5–7 dias

**Objetivo:** o produto começa a falar com o gestor.

| Trilha | Entrega |
|---|---|
| Backend | `operax/alertas/outbox.py` enfileira em `app.alert_queue` |
| Backend | `operax/alertas/sender.py` com `skip locked`, backoff e idempotência |
| Backend | `operax/alertas/ciclo.py` monta o ciclo com reserva transacional |
| Backend | Link profundo para o dashboard filtrado |
| Frontend | Tela de configuração de regras e destinos |
| Produto | Homologação das regras com cliente, jurídico e RH |

Toda regra nasce desligada. Rodar primeiro em modo de teste, com destino no
próprio Owner.

**Aceite**

- Reprocessar período não reenvia mensagem.
- Falha de rede não duplica nem perde.
- Regra individual com destino de grupo é rejeitada pelo banco.
- Relatório declara ocorrências de dias anteriores quando houver.
- Custo por mensagem sendo registrado.

**⚠️ G5**

---

## S7 — Assistente de IA · 3–5 dias

| Trilha | Entrega |
|---|---|
| Backend | `operax/agente/` com `create_agent`: pergunta → métrica → execução como o usuário → texto |
| Backend | `POST /assistente/perguntar` com streaming SSE |
| Frontend | Interface de conversa consumindo o SSE via `fetch` + `ReadableStream` |
| Backend | Registro em `app.ai_query`: métrica, parâmetros, latência e tokens |

**Aceite**

- Pergunta fora do catálogo recebe recusa, não número inventado.
- Usuário sem o domínio sensível é recusado antes da consulta.
- Resposta informa período e filtros usados.
- Custo de tokens visível.

---

## S8 — Homologação, treinamento e produção · 3–5 dias

| Trilha | Entrega |
|---|---|
| Produto | Roteiro de homologação por funcionalidade |
| Produto | Treinamento dos usuários indicados |
| Produto | Runbook de suporte e escalonamento |
| Infra | Backup testado com restauração real, não só configurado |
| Infra | Monitoramento dos sinais da spec |

**Aceite:** critérios do item 18 da proposta comercial atendidos e homologados
pelo responsável do cliente.

---

## Fase 3 — Folha via Excel, documentos e acordos · a definir

**Não depende mais de acesso ao Domínio.** O escopo decidiu: a v1 é upload de
relatório em Excel. O que destrava a fase é a contabilidade mandar uma planilha
de exemplo — não a Thomson Reuters liberar API.

Entregáveis novos que não existiam em nenhum sprint:

| Trilha | Entrega |
|---|---|
| Produto | Template padronizado publicado (§6 do escopo obriga a contratada a fornecer) |
| Backend | `operax/imports/`: parser, validação de campos obrigatórios, duplicidade |
| Backend | Devolutiva de erro por linha em `app.file_import.report` |
| Frontend | Tela de upload com preview antes de confirmar |
| Produto | **Mapa de código de evento de folha → categoria**, curado com a contabilidade |

O último é bloqueante: sem ele, 8 dos 16 indicadores de 5.3 não saem. É curadoria,
igual ao mapa de unidades, e precisa estar dimensionado como atividade de
implantação — não absorvido em silêncio.

O modelo de dados já existe (migrations `07` e `08`) mas **não foi validado contra
dado real**. Parte vai mudar quando o primeiro layout chegar.

---

## Linha do tempo

```
S0 ██                                                    2–3d   banco + comercial
S1  ████                                                 3–5d   banco + backend
S2     ████                                              3–5d   banco
S3        █████                                          5d     backend   ← decide o cronograma
S4             ██████████                                5–10d  backend
S5             ██████████████                            7–10d  frontend  (paralelo ao S4)
S6                       ███████                         5–7d   backend + frontend
S7                              █████                    3–5d   frontend
S8                                   █████               3–5d   produto
                                                         ─────
                                            total ~33–50 dias úteis
```

A proposta comercial fala em 30 a 45 dias corridos. **Dias corridos e dias úteis
não são a mesma coisa** — 33 a 50 dias úteis são 7 a 10 semanas. O intervalo da
proposta só fecha se S5 correr de fato em paralelo com S4 e se o S3 não exigir
cadastro manual de escala.

Se o S3 revelar que a escala precisa ser cadastrada à mão, isso é escopo adicional
e precisa ser conversado com o cliente **no momento em que for descoberto**, não
no fechamento.

---

## Definition of done

Vale para toda entrega, em qualquer trilha:

1. `make test && make lint` verde. Se tocou banco, policy, view ou grant: `make db-test` também.
2. Dicionário de dados regenerado se o schema mudou.
3. Nenhum dado sensível em view de `public` — verificado pela suíte.
4. Nenhuma consulta com `service_role` sem filtro de `tenant_id` — e `service_role` só existe no backend FastAPI.
5. Vocabulário: *desvio* e *indício*, nunca "hora extra".
6. Pendência que dependa da API do Secullum marcada com ⏳ e listada na spec.
